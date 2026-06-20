import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from fastapi.testclient import TestClient

_TEST_DB_DIR = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["OPENINTERVIEW_DB_PATH"] = str(Path(_TEST_DB_DIR.name) / "test.sqlite")

from openinterview_api.main import app  # noqa: E402
from openinterview_api.schemas import MAX_AUDIO_BASE64_CHARS  # noqa: E402
from openinterview_api.schemas import ProviderSettings  # noqa: E402
from openinterview_api.settings import project_root  # noqa: E402
from openinterview_api.services.voice_config import (  # noqa: E402
    asr_model_dir,
    cosyvoice_runtime_path,
    tts_model_dir,
    vad_model_path,
)
from openinterview_api.storage import Storage  # noqa: E402
from openinterview_api.voice.voice_profiles import load_voice_profiles  # noqa: E402


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

    def test_start_does_not_require_llm_config_by_default(self):
        response = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["next_question"])

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

    def test_turn_after_finished_is_rejected(self):
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
        last_turn = None
        turn_count = 0
        for _ in range(10):
            last_turn = client.post(
                f"/v1/interviews/{session_id}/turn",
                json={"answer": "首先说明背景，再讲方案、结果、边界和验证方式。"},
            )
            self.assertEqual(last_turn.status_code, 200)
            turn_count += 1
            if last_turn.json()["is_finished"]:
                break
        self.assertTrue(last_turn.json()["is_finished"])

        rejected = client.post(
            f"/v1/interviews/{session_id}/turn",
            json={"answer": "结束后不应该继续写入。"},
        )
        self.assertEqual(rejected.status_code, 409)

        report = client.get(f"/v1/interviews/{session_id}/report")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(len(report.json()["turns"]), turn_count)

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
        self.assertGreaterEqual(payload["total"], 700)
        self.assertTrue(any(item["topic"] == "java-basis" for item in payload["topics"]))
        self.assertFalse(payload["gaps"])

        ai_response = client.get("/v1/questions/coverage?direction_id=ai_application")
        self.assertEqual(ai_response.status_code, 200)
        ai_payload = ai_response.json()
        self.assertEqual(ai_payload["direction_id"], "ai_application")
        self.assertGreaterEqual(ai_payload["total"], 250)
        self.assertTrue(any(item["topic"] == "rag" for item in ai_payload["topics"]))
        self.assertFalse(ai_payload["gaps"])

        backend_payload = response.json()
        backend_status = {item["topic"]: item["status"] for item in backend_payload["topics"]}
        for topic in ["cache", "mybatis", "java-collection", "system-design", "operating-system", "security"]:
            self.assertEqual(backend_status.get(topic), "ok")

    def test_provider_defaults_are_local_text_first(self):
        settings = ProviderSettings()
        self.assertEqual(settings.llm.provider, "openai_compatible")
        self.assertFalse(settings.llm.allow_fallback)
        self.assertEqual(settings.asr.provider, "browser")
        self.assertEqual(settings.tts.provider, "browser")

    def test_turn_does_not_call_llm_feedback_during_interview(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
                "provider_config": {
                    "llm": {
                        "provider": "openai_compatible",
                        "api_base": "http://127.0.0.1:9/v1",
                        "model": "test-model",
                        "api_key": "test-key",
                    },
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        session_id = interview.json()["session_id"]
        with patch("openinterview_api.interview_engine.build_llm_adapter", return_value=_EmptyLLMAdapter()):
            turn = client.post(
                f"/v1/interviews/{session_id}/turn",
                json={"answer": "我会先说明思路，再做取舍。"},
            )

        self.assertEqual(turn.status_code, 200)
        self.assertEqual(turn.json()["interviewer_message"], "")
        self.assertTrue(turn.json()["next_question"])
        self.assertIsNone(turn.json()["provider_notice"])

    def test_report_llm_summary_failure_falls_back_to_local_summary(self):
        interview = client.post(
            "/v1/interviews",
            json={
                "direction_id": "backend",
                "difficulty_id": "campus",
                "mode_id": "comprehensive",
                "provider_config": {
                    "llm": {
                        "provider": "openai_compatible",
                        "api_base": "http://127.0.0.1:9/v1",
                        "model": "test-model",
                        "api_key": "test-key",
                    },
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(interview.status_code, 200)
        session_id = interview.json()["session_id"]
        turn = client.post(
            f"/v1/interviews/{session_id}/turn",
            json={"answer": "我会先说明思路，再做取舍。"},
        )
        self.assertEqual(turn.status_code, 200)

        with patch("openinterview_api.interview_engine.build_llm_adapter", return_value=_EmptyLLMAdapter()):
            report = client.get(f"/v1/interviews/{session_id}/report")

        self.assertEqual(report.status_code, 200)
        self.assertTrue(report.json()["ai_summary"])
        self.assertIn("turns", report.json())

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

    def test_voice_config_api_reads_and_writes_local_paths(self):
        previous = {
            key: os.environ.get(key)
            for key in [
                "OPENINTERVIEW_VOICE_MODELS_CONFIG",
                "OPENINTERVIEW_VAD_MODEL",
                "OPENINTERVIEW_ASR_MODEL_DIR",
                "OPENINTERVIEW_TTS_MODEL_DIR",
                "OPENINTERVIEW_COSYVOICE_PATH",
            ]
        }
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                config_path = Path(temp_dir) / "voice-models.local.yaml"
                os.environ["OPENINTERVIEW_VOICE_MODELS_CONFIG"] = str(config_path)
                os.environ.pop("OPENINTERVIEW_VAD_MODEL", None)
                os.environ.pop("OPENINTERVIEW_ASR_MODEL_DIR", None)
                os.environ.pop("OPENINTERVIEW_TTS_MODEL_DIR", None)
                os.environ.pop("OPENINTERVIEW_COSYVOICE_PATH", None)

                saved = client.post(
                    "/v1/voice/config",
                    json={
                        "vad_model": "D:/voice/vad.onnx",
                        "asr_model_dir": "D:/voice/asr",
                        "tts_model_dir": "D:/voice/tts",
                        "cosyvoice_path": "D:/voice/CosyVoice",
                    },
                )
                self.assertEqual(saved.status_code, 200)
                payload = saved.json()
                self.assertEqual(payload["vad_model"].replace("\\", "/"), "D:/voice/vad.onnx")
                self.assertEqual(payload["asr_model_dir"].replace("\\", "/"), "D:/voice/asr")
                self.assertEqual(payload["tts_model_dir"].replace("\\", "/"), "D:/voice/tts")
                self.assertEqual(payload["cosyvoice_path"].replace("\\", "/"), "D:/voice/CosyVoice")
                self.assertTrue(config_path.exists())

                loaded = client.get("/v1/voice/config")
                self.assertEqual(loaded.status_code, 200)
                self.assertEqual(loaded.json()["editable_models_config"], str(config_path))
                self.assertEqual(str(vad_model_path()).replace("\\", "/"), "D:/voice/vad.onnx")
                self.assertEqual(str(asr_model_dir()).replace("\\", "/"), "D:/voice/asr")
                self.assertEqual(str(tts_model_dir()).replace("\\", "/"), "D:/voice/tts")
                self.assertEqual(str(cosyvoice_runtime_path()).replace("\\", "/"), "D:/voice/CosyVoice")
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
        self.assertEqual(
            profiles[0].resolved_reference_audio(),
            project_root() / "voices" / "custom.wav",
        )
        payload = profiles[0].as_dict()
        self.assertTrue(payload["requires_reference_audio"])
        self.assertTrue(payload["uses_reference_audio"])
        self.assertFalse(payload["reference_audio_exists"])
        self.assertEqual(payload["reference_audio_path"], str(project_root() / "voices" / "custom.wav"))

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
            storage.save_report("s1", {"session_id": "s1", "overall_score": 75, "turns": []})

            exported = storage.export_interviews()
            deleted = storage.clear_interviews()
            imported = storage.import_interviews(exported)

            self.assertEqual(exported["schema_version"], 3)
            self.assertEqual(len(exported["interviews"]), 1)
            self.assertEqual(exported["interviews"][0]["report"]["overall_score"], 75)
            self.assertEqual(len(exported["turns"]), 1)
            self.assertEqual(deleted, 1)
            self.assertEqual(imported["interviews"], 1)
            self.assertEqual(imported["turns"], 1)
            self.assertEqual(storage.get_interview("s1")["report"]["overall_score"], 75)
            self.assertEqual(storage.get_interview_turns("s1")[0]["question_meta"]["id"], "q1")

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

    def test_audio_base64_validation(self):
        bad = client.post(
            "/v1/vad/detect",
            json={"audio_base64": "not base64!", "filename": "bad.wav"},
        )
        self.assertEqual(bad.status_code, 400)

        too_large = client.post(
            "/v1/asr/transcribe",
            json={
                "audio_base64": "A" * (MAX_AUDIO_BASE64_CHARS + 1),
                "filename": "too-large.wav",
                "provider_config": {
                    "llm": {"provider": "mock"},
                    "asr": {"provider": "browser"},
                    "tts": {"provider": "browser"},
                },
            },
        )
        self.assertEqual(too_large.status_code, 422)

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
        self.assertIn("timings", payload)
        self.assertIn("convert_ms", payload["timings"])
        self.assertIn("vad_ms", payload["timings"])

    def test_realtime_audio_turn_accepts_pcm_s16le(self):
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
                "audio_base64": _silence_pcm_base64(),
                "filename": "silence.pcm",
                "audio_encoding": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
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
        self.assertIn("convert_ms", payload["timings"])
        self.assertIn("vad_ms", payload["timings"])

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
            for _ in range(10):
                payload = websocket.receive_json()
                seen.append(payload["type"])
                if payload["type"] == "done":
                    self.assertTrue(payload["skipped"])
                    self.assertEqual(payload["reason"], "no_speech")
                    self.assertIn("timings", payload)
                    break
            self.assertIn("vad_start", seen)
            self.assertIn("vad_final", seen)
            self.assertIn("timing", seen)
            self.assertIn("done", seen)

    def test_realtime_duplex_websocket_accepts_pcm_s16le(self):
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
                    "mime_type": "audio/pcm",
                    "audio_encoding": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "partial_interval_chunks": 1,
                }
            )
            self.assertEqual(websocket.receive_json()["type"], "listening")
            websocket.send_json(
                {
                    "type": "audio",
                    "audio_encoding": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "data": _silence_pcm_base64(),
                }
            )
            self.assertEqual(websocket.receive_json()["type"], "asr_partial")
            websocket.send_json({"type": "commit"})
            seen = []
            for _ in range(10):
                payload = websocket.receive_json()
                seen.append(payload["type"])
                if payload["type"] == "done":
                    self.assertTrue(payload["skipped"])
                    self.assertEqual(payload["reason"], "no_speech")
                    self.assertIn("timings", payload)
                    break
            self.assertIn("vad_start", seen)
            self.assertIn("vad_final", seen)
            self.assertIn("timing", seen)
            self.assertIn("done", seen)


def _silence_wav_base64() -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _silence_pcm_base64() -> str:
    return base64.b64encode(b"\x00\x00" * 16000).decode("ascii")


class _EmptyLLMAdapter:
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        del messages, temperature
        return ""


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
