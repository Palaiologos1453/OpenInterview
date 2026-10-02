from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from openinterview_api.interview_engine import CampusInterviewEngine, InterviewConfig
from openinterview_api.services.semantic_interview import SemanticError
from test_api import client
from openinterview_api.main import session_store, storage


CLOUD = {"llm": {"provider": "openai_compatible", "api_base": "https://test.invalid/v1",
                 "model": "test", "api_key": "fake-semantic-secret"}}


class Provider:
    def __init__(self, transform=None):
        self.contexts = []
        self.prompts = []
        self.transform = transform

    def complete(self, messages, **kwargs):
        context = json.loads(messages[1]["content"])
        self.contexts.append(context)
        self.prompts.append(messages[0]["content"])
        sid = context["current_answer_id"]
        evidence = {"source_id": sid, "quote": context["sources"][sid]}
        track = context["track"]
        decision = {"track": track, "action": "probe", "question_kind": "grounded",
            "question": f"请具体说明这次回答中第{len(self.contexts)}处方案的适用边界？" if track == "knowledge" else "你负责的接口如何验证效果？",
            "assessment": "partial", "score": 67, "feedback": "说明了基本思路，仍需澄清边界。",
            "evidence": [evidence], "knowledge_refs": [k["id"] for k in context["knowledge"]],
            "knowledge_findings": [], "project_claims": []}
        finding = {"target": "边界" if track == "knowledge" else "个人贡献", "observation": context["sources"][sid],
            "project": None if track == "knowledge" else "订单系统",
            "status": "needs_clarification" if track == "knowledge" else "candidate_claim", "evidence": [evidence]}
        decision["knowledge_findings" if track == "knowledge" else "project_claims"] = [finding]
        if self.transform:
            self.transform(decision)
        return json.dumps(decision, ensure_ascii=False)


class SemanticTests(unittest.TestCase):
    def start(self, mode="fundamentals"):
        engine = CampusInterviewEngine()
        session = engine.start(InterviewConfig(direction_id="backend", difficulty_id="campus", mode_id=mode,
            interview_strategy="semantic", provider_config=deepcopy(CLOUD), resume_text="项目：订单系统。我负责接口。"))["session"]
        return engine, session

    def test_knowledge_can_probe_multiple_times_without_advancing_stage(self):
        engine, session = self.start()
        provider = Provider()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=provider):
            for _ in range(3):
                engine.answer(session, "索引需要结合查询条件分析。")
        self.assertEqual(session.turn_index, 3)
        self.assertEqual(session.semantic_state["stage_index"], 0)
        self.assertEqual(len(session.semantic_state["knowledge"]), 3)
        self.assertEqual(session.semantic_state["projects"], [])
        self.assertTrue(provider.contexts[0]["knowledge"])
        self.assertIn("八股知识理解", provider.prompts[0])

    def test_project_has_separate_claim_state_and_no_knowledge_substitution(self):
        engine, session = self.start("project_deep_dive")
        provider = Provider()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=provider):
            engine.answer(session, "我只负责接口，没有负责缓存。")
        self.assertEqual(session.semantic_state["projects"][0]["status"], "candidate_claim")
        self.assertEqual(provider.contexts[0]["knowledge"], [])
        self.assertEqual(session.semantic_state["knowledge"], [])
        self.assertIn("没负责的模块", provider.prompts[0])

    def test_invalid_evidence_and_wrong_track_leave_state_unchanged(self):
        transforms = [lambda d: d["evidence"][0].update(quote="不存在的回答"),
                      lambda d: d.update(track="project"),
                      lambda d: d.update(knowledge_refs=["fabricated-source"])]
        for transform in transforms:
            engine, session = self.start()
            before = deepcopy(session)
            with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider(transform)):
                with self.assertRaises(SemanticError):
                    engine.answer(session, "需要考虑索引选择性。")
            self.assertEqual(before, session)

    def test_project_does_not_accept_invented_metric_or_verified_claim(self):
        for transform in [lambda d: d.update(question="你如何证明优化了99%的延迟？"),
                          lambda d: d["project_claims"][0].update(status="supported")]:
            engine, session = self.start("project_deep_dive")
            with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider(transform)):
                with self.assertRaises(SemanticError):
                    engine.answer(session, "我负责接口设计。")
            self.assertEqual(session.turn_index, 0)

    def test_uncertain_report_is_not_scored_by_keyword_rules(self):
        engine, session = self.start()
        provider = Provider(lambda d: d.update(assessment="uncertain", score=None))
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=provider):
            engine.answer(session, "你问的是RR还是RC？")
        with patch.object(engine, "_dimension_scores", side_effect=AssertionError("heuristic score used")):
            report = engine.report(session)
        self.assertIsNone(report["turns"][0]["score"])
        self.assertEqual(report["dimensions"], [])

    def test_topic_budget_advances_independently_of_global_turn_count(self):
        engine, session = self.start()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider()):
            for _ in range(4):
                result = engine.answer(session, "这取决于查询条件。")
        self.assertFalse(result["is_finished"])
        self.assertEqual(session.semantic_state["stage_index"], 1)
        self.assertEqual(session.semantic_state["depth"], 0)

    def test_model_advance_switches_objective(self):
        engine, session = self.start()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider(lambda d: d.update(action="advance"))):
            engine.answer(session, "解释了原理和边界。")
        self.assertEqual(session.semantic_state["stage_index"], 1)


class SemanticApiTests(unittest.TestCase):
    def create(self):
        response = client.post("/v1/interviews", json={"interview_strategy": "semantic",
            "mode_id": "fundamentals", "provider_config": CLOUD})
        self.assertEqual(response.status_code, 200)
        return response.json()["session_id"]

    def test_missing_cloud_configuration_rejected(self):
        response = client.post("/v1/interviews", json={"interview_strategy": "semantic"})
        self.assertEqual(response.status_code, 400)

    def test_preview_does_not_make_paid_calls(self):
        sid = self.create()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter") as provider:
            response = client.post(f"/v1/interviews/{sid}/preview", json={"answer": "临时转录", "expected_turn_index": 0})
        self.assertEqual(response.status_code, 409)
        provider.assert_not_called()

    def test_restore_and_idempotency_preserve_semantic_state_without_keys(self):
        sid = self.create()
        provider = Provider()
        body = {"answer": "需要结合查询条件解释。", "request_id": "semantic-final-1"}
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=provider):
            first = client.post(f"/v1/interviews/{sid}/turn", json=body)
            repeated = client.post(f"/v1/interviews/{sid}/turn", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), repeated.json())
        self.assertEqual(len(provider.contexts), 1)
        state = deepcopy(session_store.get(sid).semantic_state)
        question = session_store.get(sid).current_question
        session_store.delete(sid)
        restored = session_store.get(sid)
        self.assertEqual(restored.current_question, question)
        self.assertEqual(restored.semantic_state, state)
        self.assertNotIn("fake-semantic-secret", json.dumps(storage.export_interviews()))
        self.assertEqual(client.post(f"/v1/interviews/{sid}/turn", json={"answer": "继续解释"}).status_code, 400)
        configured = client.post(f"/v1/interviews/{sid}/llm", json=CLOUD["llm"])
        self.assertEqual(configured.status_code, 200)
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider()):
            self.assertEqual(client.get(f"/v1/interviews/{sid}/report").status_code, 200)

    def test_provider_failure_does_not_consume_turn_or_expose_error_body(self):
        sid = self.create()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", side_effect=RuntimeError("SECRET provider body")):
            response = client.post(f"/v1/interviews/{sid}/turn", json={"answer": "解释索引机制。"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("SECRET", response.text)
        self.assertEqual(session_store.get(sid).turn_index, 0)
        self.assertEqual(storage.get_interview_turns(sid), [])

    def test_storage_failure_does_not_mutate_hot_session(self):
        sid = self.create()
        with patch("openinterview_api.services.semantic_interview.build_llm_adapter", return_value=Provider()), \
             patch.object(storage, "save_turn", side_effect=RuntimeError("database failed")):
            with self.assertRaises(RuntimeError):
                client.post(f"/v1/interviews/{sid}/turn", json={"answer": "解释索引机制。"})
        self.assertEqual(session_store.get(sid).turn_index, 0)
