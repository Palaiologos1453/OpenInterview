import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
import wave
import zipfile

from fastapi.testclient import TestClient

from openinterview_api.main import app
from openinterview_api.schemas import ProviderSettings
from openinterview_api.settings import project_root
from openinterview_api.services.voice_config import asr_model_dir, tts_model_dir, vad_model_path
from openinterview_api.storage import Storage
from openinterview_api.voice.voice_profiles import load_voice_profiles


client = TestClient(app)


class OpenInterviewAPITest(unittest.TestCase):
    def test_catalog_includes_voice_profiles(self):
        response = client.get("/v1/catalog")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("voice_profiles", payload)
        self.assertNotIn("coding", {item["id"] for item in payload["modes"]})
        direction_ids = {item["id"] for item in payload["directions"]}
        self.assertEqual(direction_ids, {"backend", "ai_application"})
        mode_names = {item["id"]: item["name"] for item in payload["modes"]}
        self.assertEqual(mode_names["fundamentals"], "单纯八股")
        self.assertEqual(mode_names["project_deep_dive"], "简历拷打")
        style_ids = {item["id"] for item in payload["interviewer_styles"]}
        self.assertEqual(
            style_ids,
            {"small_company_basic", "fundamental_chain", "resume_truth_probe", "system_design"},
        )

    def test_health_does_not_expose_code_runner(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("enable_code_runner", response.json())

    def test_resume_analyze(self):
        response = client.post(
            "/v1/resume/analyze",
            json={
                "text": (
                    "项目：Redis 缓存平台。负责缓存一致性和接口优化。"
                    "使用 Java、MySQL、Redis，优化接口延迟降低 30%，线上压测发现过缓存击穿问题。"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("Java", payload["tech_stack"])
        self.assertTrue(payload["highlights"])
        self.assertTrue(payload["project_cards"])
        self.assertTrue(payload["contributions"])
        self.assertTrue(payload["metric_questions"])
        self.assertTrue(payload["tech_choice_questions"])
        self.assertTrue(payload["incident_questions"])

    def test_start_requires_real_llm_config_by_default(self):
        response = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_start_allows_explicit_mock_for_development(self):
        response = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
                "interviewer_style_id": "fundamental_chain",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("八股连环追问型", response.json()["opening_message"])

    def test_report_response_includes_interviewer_style(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "fundamentals",
                "interviewer_style_id": "system_design",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        session_id = interview.json()["session_id"]
        turn = client.post(
            f"/v1/interviews/{session_id}/turn",
            json={"answer": "先澄清约束，再说明容量、模块、数据一致性和监控兜底。"},
        )
        self.assertEqual(turn.status_code, 200)

        report = client.get(f"/v1/interviews/{session_id}/report")

        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["interviewer_style"], "系统设计型")

    def test_llm_connection_test_allows_mock(self):
        response = client.post(
            "/v1/providers/llm/test",
            json={
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(response.json()["real_llm"])
        self.assertIn("diagnostic", response.json())

    def test_llm_connection_test_returns_diagnostic_for_bad_config(self):
        response = client.post(
            "/v1/providers/llm/test",
            json={
                "provider_config": {
                    "llm": {
                        "provider": "openai_compatible",
                        "api_base": "http://127.0.0.1:9/v1",
                        "model": "missing-model",
                        "api_key": "bad-key",
                        "timeout_seconds": 5,
                    },
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("hint", payload["diagnostic"])

    def test_resume_extract_txt_and_docx(self):
        txt = client.post(
            "/v1/resume/extract",
            files={"file": ("resume.txt", "项目：订单系统，负责 Java 和 Redis。".encode("utf-8"), "text/plain")},
        )
        self.assertEqual(txt.status_code, 200)
        self.assertIn("订单系统", txt.json()["text"])

        docx = client.post(
            "/v1/resume/extract",
            files={
                "file": (
                    "resume.docx",
                    _minimal_docx_bytes("项目：支付系统，负责 Spring Boot 和 MySQL。"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(docx.status_code, 200)
        self.assertIn("支付系统", docx.json()["text"])

    def test_questions_exclude_coding_items(self):
        response = client.get("/v1/questions")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["questions"])
        self.assertTrue(all(item.get("type") != "coding" for item in response.json()["questions"]))
        self.assertTrue(all("backend" in item.get("directions", []) for item in response.json()["questions"]))
        ai_questions = client.get("/v1/questions?direction_id=ai_application")
        self.assertEqual(ai_questions.status_code, 200)
        self.assertTrue(ai_questions.json()["questions"])
        self.assertTrue(
            all("ai_application" in item.get("directions", []) for item in ai_questions.json()["questions"])
        )
        hidden = client.get("/v1/questions?direction_id=frontend")
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.json()["questions"], [])
        frontend_question = client.get("/v1/questions/frontend-url-render")
        self.assertEqual(frontend_question.status_code, 404)
        ai_question = client.get("/v1/questions/ai-rag-pipeline-design")
        self.assertEqual(ai_question.status_code, 200)
        self.assertEqual(ai_question.json()["topic"], "rag")

    def test_question_coverage(self):
        response = client.get("/v1/questions/coverage")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["total"], 50)
        self.assertTrue(any(item["topic"] == "java-basis" for item in payload["topics"]))

        ai_response = client.get("/v1/questions/coverage?direction_id=ai_application")
        self.assertEqual(ai_response.status_code, 200)
        ai_payload = ai_response.json()
        self.assertEqual(ai_payload["direction_id"], "ai_application")
        self.assertGreaterEqual(ai_payload["total"], 16)
        self.assertTrue(any(item["topic"] == "rag" for item in ai_payload["topics"]))

    def test_provider_defaults_are_local_text_first(self):
        settings = ProviderSettings()
        self.assertEqual(settings.llm.provider, "openai_compatible")
        self.assertEqual(settings.asr.provider, "browser")
        self.assertEqual(settings.tts.provider, "browser")

    def test_voice_model_config_env_overrides(self):
        previous = {
            key: os.environ.get(key)
            for key in [
                "OPENINTERVIEW_VOICE_MODELS_CONFIG",
                "OPENINTERVIEW_VAD_MODEL",
                "OPENINTERVIEW_ASR_MODEL_DIR",
                "OPENINTERVIEW_TTS_MODEL_DIR",
            ]
        }
        try:
            os.environ["OPENINTERVIEW_VAD_MODEL"] = "D:/voice/vad.onnx"
            os.environ["OPENINTERVIEW_ASR_MODEL_DIR"] = "D:/voice/asr"
            os.environ["OPENINTERVIEW_TTS_MODEL_DIR"] = "D:/voice/tts"

            self.assertEqual(str(vad_model_path()).replace("\\", "/"), "D:/voice/vad.onnx")
            self.assertEqual(str(asr_model_dir()).replace("\\", "/"), "D:/voice/asr")
            self.assertEqual(str(tts_model_dir()).replace("\\", "/"), "D:/voice/tts")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_voice_model_config_file_overrides(self):
        previous = {
            key: os.environ.get(key)
            for key in [
                "OPENINTERVIEW_VOICE_MODELS_CONFIG",
                "OPENINTERVIEW_VAD_MODEL",
                "OPENINTERVIEW_ASR_MODEL_DIR",
                "OPENINTERVIEW_TTS_MODEL_DIR",
            ]
        }
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                config_path = Path(temp_dir) / "voice-models.local.yaml"
                config_path.write_text(
                    """
vad:
  default:
    local_file: vad/local.onnx
asr:
  default:
    local_dir: asr/local
tts:
  default:
    local_dir: tts/local
""".strip(),
                    encoding="utf-8",
                )
                os.environ["OPENINTERVIEW_VOICE_MODELS_CONFIG"] = str(config_path)
                os.environ.pop("OPENINTERVIEW_VAD_MODEL", None)
                os.environ.pop("OPENINTERVIEW_ASR_MODEL_DIR", None)
                os.environ.pop("OPENINTERVIEW_TTS_MODEL_DIR", None)

                self.assertEqual(vad_model_path(), project_root() / "vad" / "local.onnx")
                self.assertEqual(asr_model_dir(), project_root() / "asr" / "local")
                self.assertEqual(tts_model_dir(), project_root() / "tts" / "local")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_voice_profiles_can_load_local_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            path = Path(temp_dir) / "voice-profiles.local.yaml"
            path.write_text(
                """
voice_profiles:
  - id: custom
    name: 自定义
    persona: 技术面
    gender: unknown
    style: calm
    provider: cosyvoice
    mode: zero_shot
    reference_audio: voices/custom.wav
    reference_text: 你好，我是面试官。
""".strip(),
                encoding="utf-8",
            )

            profiles = load_voice_profiles(path)

        self.assertEqual(profiles[0].id, "custom")
        self.assertEqual(profiles[0].reference_audio, "voices/custom.wav")

    def test_storage_persists_question_meta(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            storage = Storage(Path(temp_dir) / "test.sqlite")
            storage.create_interview(
                "s1",
                {
                    "direction_id": "backend",
                    "difficulty_id": "campus",
                    "provider_config": {"llm": {"provider": "mock"}},
                },
            )
            storage.save_turn(
                "s1",
                turn_index=1,
                question="Q",
                answer="A",
                feedback="F",
                tags=["Java"],
                score=80,
                question_meta={"id": "q1", "topic": "java"},
            )

            turns = storage.get_interview_turns("s1")

        self.assertEqual(turns[0]["question_meta"]["id"], "q1")

    def test_storage_exports_and_clears_interviews(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            storage = Storage(Path(temp_dir) / "test.sqlite")
            storage.create_interview(
                "s1",
                {
                    "direction_id": "backend",
                    "difficulty_id": "campus",
                    "provider_config": {"llm": {"provider": "mock"}},
                },
            )
            storage.save_turn(
                "s1",
                turn_index=1,
                question="Q",
                answer="A",
                feedback="F",
                tags=["Java"],
                score=80,
                question_meta={"id": "q1"},
            )

            exported = storage.export_interviews()
            deleted = storage.clear_interviews()

            self.assertEqual(exported["schema_version"], 3)
            self.assertEqual(len(exported["interviews"]), 1)
            self.assertEqual(len(exported["turns"]), 1)
            self.assertEqual(deleted, 1)
            self.assertEqual(storage.list_interviews(), [])

    def test_review_items_and_markdown_export(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "fundamentals",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        session_id = interview.json()["session_id"]
        turn = client.post(
            f"/v1/interviews/{session_id}/turn",
            json={"answer": "不太清楚。"},
        )
        self.assertEqual(turn.status_code, 200)

        md = client.get(f"/v1/interviews/{session_id}/report.md")
        self.assertEqual(md.status_code, 200)
        self.assertIn("OpenInterview 面试报告", md.text)

        created = client.post(f"/v1/interviews/{session_id}/review-items")
        self.assertEqual(created.status_code, 200)
        self.assertGreaterEqual(created.json()["created"], 1)
        items = client.get("/v1/review-items")
        self.assertEqual(items.status_code, 200)
        self.assertTrue(items.json()["items"])
        item_id = items.json()["items"][0]["id"]
        patched = client.patch(f"/v1/review-items/{item_id}", json={"status": "mastered"})
        self.assertEqual(patched.status_code, 200)

    def test_vad_accepts_wav(self):
        audio = _silence_wav_base64()
        response = client.post(
            "/v1/vad/detect",
            json={"audio_base64": audio, "filename": "silence.wav"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("segments", response.json())

    def test_readiness_smoke_lightweight(self):
        response = client.get("/v1/readiness/smoke")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["include_voice"])
        self.assertIn("vad", payload["checks"])

    def test_realtime_state_machine(self):
        created = client.post("/v1/realtime/sessions", json={})
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["id"]
        event = client.post(
            f"/v1/realtime/sessions/{session_id}/events",
            json={"type": "tts_start", "payload": {"audio_id": "a1"}},
        )
        self.assertEqual(event.status_code, 200)
        self.assertEqual(event.json()["state"], "speaking")
        cancel = client.post(
            f"/v1/realtime/sessions/{session_id}/events",
            json={"type": "cancel", "payload": {}},
        )
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()["state"], "cancelled")

    def test_realtime_audio_turn_skips_silence(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "sensevoice"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        realtime = client.post(
            "/v1/realtime/sessions",
            json={"interview_id": interview.json()["session_id"]},
        )
        self.assertEqual(realtime.status_code, 200)

        response = client.post(
            f"/v1/realtime/sessions/{realtime.json()['id']}/audio-turn",
            json={
                "audio_base64": _silence_wav_base64(),
                "filename": "silence.wav",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "sensevoice"},
                    "tts": {"provider": "browser"},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["skipped"])
        self.assertEqual(payload["reason"], "no_speech")
        self.assertEqual(payload["transcript"], "")
        self.assertIsNone(payload["turn"])

    def test_realtime_duplex_websocket_skips_silence(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "sensevoice"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        realtime = client.post(
            "/v1/realtime/sessions",
            json={"interview_id": interview.json()["session_id"]},
        )
        self.assertEqual(realtime.status_code, 200)

        with client.websocket_connect(
            f"/v1/realtime/sessions/{realtime.json()['id']}/duplex"
        ) as websocket:
            self.assertEqual(websocket.receive_json()["type"], "ready")
            websocket.send_json(
                {
                    "type": "start",
                    "provider_config": {
                        "llm": {"provider": "mock"},
                        "asr": {"provider": "sensevoice"},
                        "tts": {"provider": "browser"},
                    },
                    "mime_type": "audio/wav",
                    "partial_interval_chunks": 1,
                }
            )
            self.assertEqual(websocket.receive_json()["type"], "listening")
            websocket.send_json({"type": "audio", "data": _silence_wav_base64()})
            self.assertEqual(websocket.receive_json()["type"], "asr_partial")
            websocket.send_json({"type": "commit"})
            seen = []
            for _ in range(5):
                payload = websocket.receive_json()
                seen.append(payload["type"])
                if payload["type"] == "done":
                    self.assertTrue(payload["skipped"])
                    self.assertEqual(payload["reason"], "no_speech")
                    break
            self.assertIn("vad_start", seen)
            self.assertIn("vad_final", seen)
            self.assertIn("done", seen)


def _silence_wav_base64() -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _minimal_docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>'''
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Types/>")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
