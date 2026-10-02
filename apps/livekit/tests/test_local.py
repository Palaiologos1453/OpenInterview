import asyncio
import base64
import json
from pathlib import Path
import sys
import unittest

import httpx
from livekit import rtc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import InterviewBackend  # noqa: E402
from local_config import loopback_url  # noqa: E402
from local_plugins import LocalCosyVoice, LocalSenseVoice  # noqa: E402


class LocalOnlyTests(unittest.TestCase):
    def test_external_cloud_urls_are_rejected(self):
        for url in ["https://example.com", "ws://my.livekit.cloud", "http://127.0.0.1.example.com", "http://user:pass@localhost", "http://localhost?remote=1"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                loopback_url(url)
        self.assertEqual(loopback_url("http://127.0.0.1:8010/"), "http://127.0.0.1:8010")


class LocalPluginsTests(unittest.IsolatedAsyncioTestCase):
    async def test_stt_forces_local_provider_and_sends_pcm(self):
        def handle(request):
            body = json.loads(request.content)
            self.assertEqual(body["provider_config"]["asr"]["provider"], "sensevoice")
            self.assertEqual(body["audio_encoding"], "pcm_s16le")
            self.assertEqual(base64.b64decode(body["audio_base64"]), b"\0\0" * 160)
            return httpx.Response(200, json={"text": "我的项目"})

        backend = InterviewBackend("http://127.0.0.1", transport=httpx.MockTransport(handle))
        try:
            recognizer = LocalSenseVoice(backend)
            result = await recognizer.recognize(rtc.AudioFrame(b"\0\0" * 160, 16000, 1, 160))
            self.assertEqual(result.alternatives[0].text, "我的项目")
        finally:
            await backend.close()

    async def test_pcm_is_emitted_before_backend_finishes(self):
        release = asyncio.Event()
        closed = asyncio.Event()

        class Backend:
            async def speech(self, text):
                try:
                    yield {"sample_rate": 24000, "data": base64.b64encode(b"\x01\x01" * 2400).decode()}
                    await release.wait()
                finally:
                    closed.set()

        tts = LocalCosyVoice(Backend())
        stream = tts.synthesize("你好")
        try:
            event = await asyncio.wait_for(anext(stream), 2)
            self.assertGreater(event.frame.samples_per_channel, 0)
            self.assertFalse(release.is_set())
        finally:
            release.set()
            await stream.aclose()
        self.assertTrue(closed.is_set())

    async def test_truncated_tts_response_is_not_success(self):
        backend = InterviewBackend("http://127.0.0.1", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text='{"type":"chunk","sample_width":2,"channels":1,"data":"AAA="}\n')))
        try:
            with self.assertRaisesRegex(RuntimeError, "without completion"):
                _ = [event async for event in backend.speech("hello")]
        finally:
            await backend.close()

    async def test_submission_uses_stable_request_id(self):
        def handle(request):
            body = json.loads(request.content)
            self.assertEqual(body, {"answer": "回答", "request_id": "turn-123"})
            return httpx.Response(200, json={"turn_index": 1})
        backend = InterviewBackend("http://127.0.0.1", transport=httpx.MockTransport(handle))
        try:
            self.assertEqual(await backend.answer("session", "回答", "turn-123"), {"turn_index": 1})
        finally:
            await backend.close()
