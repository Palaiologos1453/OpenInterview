import asyncio
from collections import OrderedDict, deque
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import anyio

from openinterview_api.services.duplex import DuplexRealtimeConnection, _question_prefix
from openinterview_api.services.realtime import RealtimeSession
from openinterview_api.services.tts_stream import iterate_tts_chunks
from openinterview_api.voice.cosyvoice_worker import _Runtime
from openinterview_api.voice.local_tts import CosyVoiceWorker, CosyVoiceTTS


def chunk(index=0):
    return {"type": "chunk", "index": index, "sample_rate": 24000,
            "channels": 1, "sample_width": 2, "data": "AAA="}


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def test_interruption_prefix_aligns_to_punctuation(self):
        self.assertEqual(_question_prefix("请说明项目背景、你的职责和最终指标。", 8), "请说明项目背景、")
        self.assertEqual(_question_prefix("请说明项目背景、你的职责和最终指标。", 100), "请说明项目背景、你的职责和最终指标。")
    def connection(self):
        connection = DuplexRealtimeConnection(
            websocket=Mock(), realtime_session=RealtimeSession(),
            interview_session=SimpleNamespace(turn_index=0), engine=Mock(), storage=Mock())
        self.events = []

        async def send(event):
            self.events.append(event)

        connection._send = send
        return connection

    async def test_first_chunk_reaches_socket_before_next_chunk_is_generated(self):
        connection = self.connection()

        def stream():
            yield chunk()
            self.assertIn("tts_pcm_chunk", [event["type"] for event in self.events])
            yield chunk(1)

        adapter = SimpleNamespace(synthesize_stream=lambda *a, **kw: stream())
        with patch("openinterview_api.services.duplex.build_tts_adapter", return_value=adapter):
            await connection._stream_tts("第一句。第二句。", {"tts": {"provider": "cosyvoice"}}, 0, Path("unused.wav"))
        types = [event["type"] for event in self.events]
        self.assertEqual(types.count("tts_pcm_chunk"), 2)
        self.assertLess(types.index("tts_pcm_chunk"), types.index("tts_segment_done"))
        self.assertEqual(types[-1], "tts_done")

    async def test_cancellation_closes_stream_without_sending_late_chunk(self):
        connection = self.connection()
        closed = []

        def stream():
            try:
                yield chunk()
                connection.cancel_generation += 1
                yield chunk(1)
            finally:
                closed.append(True)

        await connection._stream_tts_chunks(stream(), 0)
        self.assertEqual(sum(event["type"] == "tts_pcm_chunk" for event in self.events), 1)
        self.assertEqual(closed, [True])

    async def test_commit_does_not_block_cancel_message(self):
        connection = self.connection()
        entered, release = asyncio.Event(), asyncio.Event()

        async def finalize(message):
            entered.set()
            await release.wait()

        connection._finalize_audio_turn = finalize
        await connection._handle_message({"type": "commit"})
        await asyncio.wait_for(entered.wait(), 1)
        await connection._handle_message({"type": "cancel"})
        self.assertEqual(connection.cancel_generation, 1)
        self.assertEqual(self.events[-1]["type"], "cancelled")
        release.set()
        await connection.turn_task

    async def test_interrupt_stops_generation_and_marks_turn(self):
        connection = self.connection()
        connection.realtime_session.interview_id = "i1"
        connection.active_turn_index = 2
        connection.storage.mark_turn_interrupted = Mock()
        await connection._handle_message({
            "type": "interrupt", "reason": "barge_in", "played_ms": 420, "played_chars": 12,
        })
        self.assertEqual(connection.cancel_generation, 1)
        connection.storage.mark_turn_interrupted.assert_called_once_with(
            "i1", 2, played_ms=420.0, played_chars=12, reason="barge_in",
            interrupted_question=""
        )
        self.assertEqual(self.events[-1]["type"], "interrupted")

    async def test_disconnect_closes_generator_after_inflight_next(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()

        def stream():
            try:
                entered.set()
                release.wait(timeout=2)
                yield chunk()
            finally:
                closed.set()

        async def consume():
            iterator = iterate_tts_chunks(stream())
            try:
                async for _ in iterator:
                    await anyio.sleep(0)
            finally:
                await iterator.aclose()

        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            self.assertTrue(await anyio.to_thread.run_sync(entered.wait, 2))
            group.cancel_scope.cancel()
            release.set()
        self.assertTrue(closed.is_set())


class WorkerTests(unittest.TestCase):
    def worker(self, events):
        worker = CosyVoiceWorker.__new__(CosyVoiceWorker)
        worker.lock = threading.Lock()
        worker.closed = False
        worker.events = queue.Queue()
        worker.diagnostics = deque()
        worker.process = Mock()
        worker.process.poll.return_value = None
        worker.close = Mock(side_effect=lambda: setattr(worker, "closed", True))

        def write(line):
            request = json.loads(line)
            self.assertTrue(request["stream"])
            for event in events:
                worker.events.put({"id": request["id"], **event})

        worker.process.stdin.write.side_effect = write
        return worker

    def test_worker_reuses_protocol_after_complete_stream(self):
        worker = self.worker([chunk(), {"type": "result", "output": None}])
        for _ in range(2):
            self.assertEqual(len(list(worker.synthesize_stream("你好", Path("unused.wav")))), 1)
        worker.close.assert_not_called()
        self.assertFalse(worker.lock.locked())

    def test_early_close_drains_old_audio_and_reuses_worker(self):
        worker = self.worker([chunk(), chunk(1), {"type": "result"}])
        stream = worker.synthesize_stream("你好", Path("unused.wav"))
        next(stream)
        stream.close()
        self.assertTrue(worker.lock.acquire(timeout=2))
        worker.lock.release()
        worker.close.assert_not_called()
        self.assertTrue(worker.events.empty())
        self.assertEqual(len(list(worker.synthesize_stream("下一题", Path("unused.wav")))), 2)

    def test_mismatched_request_id_discards_worker(self):
        worker = self.worker([{"type": "chunk", "id": "wrong"}])
        with self.assertRaisesRegex(RuntimeError, "ID mismatch"):
            list(worker.synthesize_stream("你好", Path("unused.wav")))
        worker.close.assert_called_once()

    def test_read_deadline_and_unexpected_exit_are_diagnostic(self):
        worker = self.worker([])
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            worker._receive(monotonic())
        worker.diagnostics.append("CUDA failure")
        worker.events.put({"type": "eof"})
        with self.assertRaisesRegex(RuntimeError, "CUDA failure"):
            worker._receive(monotonic() + 1)

    def test_stdout_diagnostics_do_not_corrupt_protocol(self):
        worker = self.worker([])
        worker.process.stdout = io.StringIO('library log\n{"type":"ready"}\n')
        worker._read_stdout()
        self.assertEqual(worker.events.get()["type"], "ready")
        self.assertEqual(list(worker.diagnostics), ["library log"])

    def test_failed_partial_stream_is_not_replayed(self):
        def failing(*args, **kwargs):
            yield chunk()
            raise RuntimeError("failed halfway")

        with tempfile.TemporaryDirectory() as tmp:
            adapter = CosyVoiceTTS(Path(tmp))
            with patch("openinterview_api.voice.local_tts._cached_worker", return_value=SimpleNamespace(synthesize_stream=failing)):
                stream = adapter.synthesize_stream("你好", Path(tmp) / "unused.wav")
                self.assertEqual(next(stream)["type"], "chunk")
                with self.assertRaisesRegex(RuntimeError, "failed halfway"):
                    next(stream)

    def test_prompt_cache_keys_content_settings_and_file_version(self):
        runtime = _Runtime.__new__(_Runtime)
        runtime.model = Mock()
        runtime.prompt_cache = OrderedDict()
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "prompt.wav"
            ref.write_bytes(b"one")
            first = runtime._cached_prompt(str(ref), "hello")
            self.assertEqual(runtime._cached_prompt(str(ref), "hello"), first)
            runtime.model.add_zero_shot_spk.assert_called_once()
            self.assertNotEqual(runtime._cached_prompt(str(ref), "different style"), first)
            ref.write_bytes(b"changed reference")
            self.assertNotEqual(runtime._cached_prompt(str(ref), "hello"), first)

    def test_runtime_emits_before_finishing_and_resets_first_chunk_size(self):
        runtime = _Runtime.__new__(_Runtime)
        runtime.model = Mock()
        runtime.initial_token_hop_len = 25
        runtime.model.model.token_hop_len = 100
        runtime.sample_rate = 24000
        runtime.cosyvoice_path = None
        runtime._cached_prompt = Mock(return_value="cached")
        emitted = []

        def inference(*args, **kwargs):
            self.assertEqual(runtime.model.model.token_hop_len, 25)
            self.assertEqual(kwargs["zero_shot_spk_id"], "cached")
            yield {"tts_speech": object()}
            self.assertEqual(len(emitted), 1)
            yield {"tts_speech": object()}

        runtime.model.inference_instruct2.side_effect = inference
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "should-not-exist.wav"
            with patch("openinterview_api.voice.cosyvoice_worker._tensor_to_pcm16", return_value=b"\0\0"):
                runtime.synthesize({"text": "hello", "output": str(path), "stream": True,
                    "reference_audio": "reference.wav", "style_prompt": "calm"}, emit=emitted.append)
            self.assertFalse(path.exists())
            self.assertEqual(len(emitted), 2)
