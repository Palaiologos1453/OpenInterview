import json
import unittest
from unittest.mock import patch

from openinterview_api.interview_engine import CampusInterviewEngine, InterviewConfig


class _SemanticProvider:
    def complete(self, messages, **kwargs):
        context = json.loads(messages[1]["content"])
        source_id = context["current_answer_id"]
        track = context["track"]
        finding = {
            "target": "个人贡献" if track == "project" else "机制",
            "project": "未命名项目" if track == "project" else None,
            "observation": context["sources"][source_id],
            "status": "candidate_claim" if track == "project" else "needs_clarification",
            "evidence": [{"source_id": source_id, "quote": context["sources"][source_id]}],
        }
        return json.dumps({
            "track": track,
            "action": "probe",
            "question_kind": "grounded",
            "question": "请具体说明一个关键边界？",
            "assessment": "partial",
            "score": 60,
            "feedback": "补充边界和验证方式。",
            "evidence": [{"source_id": source_id, "quote": context["sources"][source_id]}],
            "knowledge_refs": [],
            "knowledge_findings": [finding] if track == "knowledge" else [],
            "project_claims": [finding] if track == "project" else [],
        }, ensure_ascii=False)


class InterviewModeTests(unittest.TestCase):
    def test_speed_mode_does_not_require_cloud_llm(self):
        engine = CampusInterviewEngine()
        result = engine.start(InterviewConfig(
            direction_id="backend", difficulty_id="campus", mode_id="fundamentals",
            interview_mode="speed", provider_config={"llm": {"provider": "mock"}},
        ))
        session = result["session"]
        self.assertEqual(result["payload"]["interview_mode"], "speed")
        self.assertEqual(session.config.interview_strategy, "rules")
        self.assertLess(session.turn_index, 1)

    def test_deep_mode_requires_cloud_llm(self):
        engine = CampusInterviewEngine()
        with self.assertRaises(ValueError):
            engine.start(InterviewConfig(
                direction_id="backend", difficulty_id="campus", mode_id="fundamentals",
                interview_mode="deep", provider_config={"llm": {"provider": "mock"}},
            ))

    def test_hybrid_mode_uses_local_path_without_cloud(self):
        engine = CampusInterviewEngine()
        session = engine.start(InterviewConfig(
            direction_id="backend", difficulty_id="campus", mode_id="fundamentals",
            interview_mode="hybrid", provider_config={"llm": {"provider": "mock"}},
        ))["session"]
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter",
                   side_effect=AssertionError("cloud should not be called")):
            payload = engine.answer(session, "这是一个普通的基础回答。")
        self.assertEqual(payload["turn_index"], 1)
        self.assertFalse(session.semantic_state.get("deep_active"))

    def test_hybrid_mode_enters_deep_path_for_project_claim(self):
        engine = CampusInterviewEngine()
        session = engine.start(InterviewConfig(
            direction_id="backend", difficulty_id="campus", mode_id="project_deep_dive",
            interview_mode="hybrid", provider_config={
                "llm": {"provider": "openai_compatible", "api_base": "https://example.test/v1",
                        "model": "test", "api_key": "secret"},
            },
        ))["session"]
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter",
                   return_value=_SemanticProvider()):
            payload = engine.answer(session, "我负责接口设计，上线后通过压测验证了指标。")
        self.assertEqual(payload["turn_index"], 1)
        self.assertIn("semantic_assessment", session.history[-1].question_meta)
        self.assertTrue(session.semantic_state["deep_active"])
