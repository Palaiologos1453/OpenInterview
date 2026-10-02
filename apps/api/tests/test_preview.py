from copy import deepcopy
import unittest
from unittest.mock import patch

from test_api import client
from openinterview_api.main import session_store, storage


class PreviewTests(unittest.TestCase):
    def test_preview_is_read_only_and_final_answer_remains_authoritative(self):
        started = client.post("/v1/interviews", json={"mode_id": "fundamentals"}).json()
        sid = started["session_id"]
        before = deepcopy(session_store.get(sid))
        with patch.object(storage, "save_turn", side_effect=AssertionError("preview wrote a turn")):
            preview = client.post(f"/v1/interviews/{sid}/preview", json={"answer": "我还不太清楚", "expected_turn_index": 0})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(before, session_store.get(sid))
        self.assertEqual(storage.get_interview_turns(sid), [])
        answer = client.post(f"/v1/interviews/{sid}/turn", json={"answer": "我还不太清楚", "request_id": "final-1"})
        self.assertEqual(answer.json()["next_question"], preview.json()["next_question"])
        self.assertEqual(len(storage.get_interview_turns(sid)), 1)
        self.assertEqual(client.post(f"/v1/interviews/{sid}/preview", json={"answer": "旧的识别结果", "expected_turn_index": 0}).status_code, 409)

    def test_partial_asr_is_not_persisted(self):
        import base64
        from types import SimpleNamespace
        adapter = SimpleNamespace(transcribe=lambda *a, **kw: "临时转录")
        with patch("openinterview_api.main.build_asr_adapter", return_value=adapter), \
             patch.object(storage, "save_transcript") as save, patch.object(storage, "save_trace") as trace:
            response = client.post("/v1/asr/transcribe", json={
                "audio_base64": base64.b64encode(b"\0\0" * 160).decode(), "audio_encoding": "pcm_s16le",
                "persist": False, "provider_config": {"asr": {"provider": "sensevoice"}}})
        self.assertEqual(response.status_code, 200)
        save.assert_not_called()
        trace.assert_not_called()
