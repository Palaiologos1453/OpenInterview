import asyncio
import base64
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speculation import ReplyPreparation, PreparedSpeech  # noqa: E402
from incremental_stt import IncrementalSenseVoice  # noqa: E402
from livekit import rtc  # noqa: E402
from livekit.agents import vad, stt  # noqa: E402


def pcm():
    return {"data": base64.b64encode(b"\0\0" * 480).decode(), "sample_rate": 24000, "channels": 1, "sample_width": 2}


class SpeculationTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefetch_requires_two_predictions_and_exact_committed_question(self):
        calls = []
        class Backend:
            async def preview(self, sid, text, index):
                calls.append((text, index))
                return {"next_question": "为什么这样选型？", "base_turn_index": index, "is_finished": False}
            async def speech(self, text):
                yield pcm()
        prep = ReplyPreparation(Backend(), "s1")
        prep.observe("我首先介绍背景和技术选型依据")
        await prep.preview_task
        self.assertIsNone(prep.prepared)
        prep.observe("我首先介绍背景和技术选型依据，然后补充结果")
        await prep.preview_task
        await prep.prepared.task
        self.assertEqual(prep.metrics["prefetch_started"], 1)
        await prep.seal()
        speech = await prep.take({"next_question": "为什么这样选型？", "turn_index": 1})
        self.assertIsNotNone(speech)
        self.assertEqual(len([chunk async for chunk in speech.events()]), 1)
        self.assertEqual(prep.metrics["prefetch_hits"], 1)
        await prep.close()

    async def test_corrected_answer_cannot_play_stale_audio(self):
        for question, turn in [("新的追问", 1), ("旧的追问", 2)]:
            class Backend:
                async def speech(self, text):
                    yield pcm()
            prep = ReplyPreparation(Backend(), "s1")
            prep.prepared = PreparedSpeech(prep.backend, "旧的追问")
            await prep.prepared.task
            result = await prep.take({"next_question": question, "turn_index": turn})
            self.assertIsNone(result)
            await prep.close()

    async def test_speculative_audio_is_bounded_and_never_output_before_take(self):
        class Backend:
            async def speech(self, text):
                for _ in range(100):
                    yield pcm()
        speech = PreparedSpeech(Backend(), "question", max_seconds=0.05)
        await speech.task
        self.assertIsNotNone(speech.error)
        self.assertLessEqual(len(speech.chunks), 2)
        await speech.close()

    async def test_slow_preview_does_not_accumulate_requests(self):
        started = asyncio.Event()
        class Backend:
            async def preview(self, *args):
                started.set()
                await asyncio.Event().wait()
        prep = ReplyPreparation(Backend(), "s1")
        prep.observe("这里是第一段足够长度的识别结果")
        await started.wait()
        for _ in range(10):
            prep.observe("这里是修正后的足够长度识别结果")
        self.assertEqual(prep.metrics["preview_calls"], 1)
        await prep.close()


class FakeVad:
    def __init__(self, events):
        self.events = events
    def stream(self):
        return self
    def push_frame(self, frame):
        pass
    def flush(self):
        pass
    def end_input(self):
        pass
    async def aclose(self):
        pass
    def __aiter__(self):
        return self.events()


def event(kind, frames):
    return SimpleNamespace(type=kind, frames=frames, silence_duration=0.8, inference_duration=0)


class IncrementalTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_asr_skips_snapshots_instead_of_queueing_them(self):
        release, started = asyncio.Event(), asyncio.Event()
        calls = []
        frame = rtc.AudioFrame(b"\0\0" * 16000, 16000, 1, 16000)
        class Backend:
            async def recognize(self, data, rate, channels, *, persist=True):
                calls.append(persist)
                if not persist:
                    started.set()
                    await release.wait()
                return "识别结果"
        async def observe(ev):
            pass
        async def events():
            yield event(vad.VADEventType.START_OF_SPEECH, [frame])
            yield event(vad.VADEventType.INFERENCE_DONE, [frame])
            await started.wait()
            for _ in range(25):
                yield event(vad.VADEventType.INFERENCE_DONE, [frame])
            self.assertEqual(calls, [False])
            release.set()
            yield event(vad.VADEventType.END_OF_SPEECH, [frame])
        stream = IncrementalSenseVoice(Backend(), FakeVad(events), observe, interval=.5).stream()
        stream.end_input()
        try:
            _ = [ev async for ev in stream]
        finally:
            await stream.aclose()
        self.assertEqual(calls, [False, True])

    async def test_partial_before_eos_final_corrects_without_committing_partial(self):
        partial_seen = asyncio.Event()
        observed = []
        requests = []
        frame = rtc.AudioFrame(b"\0\0" * 16000, 16000, 1, 16000)
        class Backend:
            async def recognize(self, data, rate, channels, *, persist=True):
                requests.append(persist)
                return "最终修正回答" if persist else "临时识别"
        async def observer(ev):
            observed.append(ev)
            if ev["type"] == "partial":
                partial_seen.set()
        async def events():
            yield event(vad.VADEventType.START_OF_SPEECH, [frame])
            yield event(vad.VADEventType.INFERENCE_DONE, [frame])
            await asyncio.wait_for(partial_seen.wait(), 2)
            yield event(vad.VADEventType.END_OF_SPEECH, [frame, frame])
        provider = IncrementalSenseVoice(Backend(), FakeVad(events), observer, interval=0.5)
        stream = provider.stream()
        stream.end_input()
        try:
            received = [ev async for ev in stream]
        finally:
            await stream.aclose()
        types = [ev.type for ev in received]
        self.assertLess(types.index(stt.SpeechEventType.INTERIM_TRANSCRIPT), types.index(stt.SpeechEventType.END_OF_SPEECH))
        self.assertEqual(received[-1].alternatives[0].text, "最终修正回答")
        self.assertEqual(requests, [False, True])
        self.assertEqual([e["type"] for e in observed], ["speech_start", "partial", "final"])

    async def test_late_partial_cannot_overwrite_final(self):
        release = asyncio.Event()
        partial_started = asyncio.Event()
        observed = []
        frame = rtc.AudioFrame(b"\0\0" * 16000, 16000, 1, 16000)
        class Backend:
            async def recognize(self, data, rate, channels, *, persist=True):
                if not persist:
                    partial_started.set()
                    await release.wait()
                return "最终文本" if persist else "过期文本"
        async def observer(ev):
            observed.append(ev)
        async def events():
            yield event(vad.VADEventType.START_OF_SPEECH, [frame])
            yield event(vad.VADEventType.INFERENCE_DONE, [frame])
            await partial_started.wait()
            asyncio.get_running_loop().call_later(.01, release.set)
            yield event(vad.VADEventType.END_OF_SPEECH, [frame])
        stream = IncrementalSenseVoice(Backend(), FakeVad(events), observer, interval=.5).stream()
        stream.end_input()
        try:
            received = [ev async for ev in stream]
        finally:
            await stream.aclose()
        self.assertNotIn("partial", [ev["type"] for ev in observed])
        self.assertEqual(received[-1].alternatives[0].text, "最终文本")
