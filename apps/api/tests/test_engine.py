import unittest

from openinterview_api.interview_engine import CampusInterviewEngine, InterviewConfig


MOCK_PROVIDER = {
    "llm": {"provider": "mock"},
    "asr": {"provider": "browser"},
    "tts": {"provider": "browser"},
}


class CampusInterviewEngineTest(unittest.TestCase):
    def test_start_and_answer_flow(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="comprehensive",
                candidate_name="候选人",
                resume_text="做过一个 Redis 缓存和 MySQL 查询优化项目。",
                provider_config=MOCK_PROVIDER,
            )
        )

        session = result["session"]
        payload = result["payload"]

        self.assertEqual(payload["session_id"], session.session_id)
        self.assertIn("Java 后端", payload["opening_message"])
        self.assertTrue(payload["next_question"])

        turn = engine.answer(
            session,
            "首先我会介绍背景，然后说明方案和结果。这个项目主要优化数据库索引和缓存一致性，最后降低了接口延迟。",
        )

        self.assertEqual(turn["turn_index"], 1)
        self.assertTrue(turn["next_question"])
        self.assertGreater(session.history[0].score, 50)

    def test_report_contains_dimensions(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="internship",
                interviewer_style_id="fundamental_chain",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]
        engine.answer(session, "我会从背景、方案、结果三个部分回答，并补充 Java、数据库和缓存细节。")

        report = engine.report(session)

        self.assertEqual(report["direction"], "Java 后端")
        self.assertEqual(report["interviewer_style"], "八股连环追问型")
        self.assertEqual(len(report["dimensions"]), 4)
        self.assertTrue(report["review_plan"])

    def test_question_bank_metadata_drives_report_gaps(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="fundamentals",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        engine.answer(
            session,
            "首先 B+ 树适合范围查询，叶子节点有序链表，索引能减少扫描行数，也要关注回表和覆盖索引。",
        )
        report = engine.report(session)

        self.assertTrue(report["turns"][0]["question_meta"]["id"])
        self.assertTrue(report["turns"][0]["question_meta"]["rubric"])
        self.assertTrue(report["turns"][0]["rubric_gaps"])
        self.assertTrue(report["improvements"])
        self.assertTrue(report["practice_drills"])
        self.assertTrue(report["answer_guides"])
        self.assertIn("example_answer", report["answer_guides"][0])
        self.assertTrue(report["study_guides"])
        self.assertIn("reference_answer", report["study_guides"][0])
        self.assertIn("common_mistakes", report["study_guides"][0])
        self.assertIn("interviewer_followups", report["study_guides"][0])
        self.assertIn("low_score_answer", report["study_guides"][0])
        self.assertIn("high_score_answer", report["study_guides"][0])
        self.assertIn("related_knowledge", report["study_guides"][0])

    def test_low_score_answer_gets_followup(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="fundamentals",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        turn = engine.answer(session, "不太清楚。")

        self.assertIn("继续补充", turn["next_question"])
        self.assertEqual(session.current_question_meta["type"], "followup")

    def test_project_deep_dive_followup_is_project_specific(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="project_deep_dive",
                interviewer_style_id="resume_truth_probe",
                resume_text=(
                    "项目：订单系统，负责缓存、接口和数据库优化。"
                    "使用 Java、Spring Boot、MySQL、Redis，接口延迟降低 30%，线上压测发现过缓存击穿问题。"
                ),
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        turn = engine.answer(session, "做了一个项目。")

        self.assertIn("继续补充", turn["next_question"])
        self.assertTrue(
            any(keyword in turn["next_question"] for keyword in ["本人做的吗", "指标从哪里来", "统计口径", "故障"])
        )
        self.assertEqual(session.current_question_meta["phase"], "project")

    def test_interviewer_styles_change_followup_pressure(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="fundamentals",
                interviewer_style_id="fundamental_chain",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        turn = engine.answer(session, "HashMap 是一个 Map。")

        self.assertIn("底层原理", turn["next_question"])
        self.assertIn("八股连环追问", turn["interviewer_message"])

    def test_system_design_style_prioritizes_design_topics(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="backend",
                difficulty_id="campus",
                mode_id="system_design_intro",
                interviewer_style_id="system_design",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        engine.answer(
            session,
            (
                "项目业务背景是订单链路延迟高，目标是降低核心接口 P99。"
                "我的个人贡献是设计缓存和索引优化方案，负责编码、联调、上线和监控。"
                "核心技术方案包含 Redis 缓存、MySQL 索引、接口限流和灰度发布。"
                "指标结果是 P99 延迟下降 30%，验证方式来自压测报告和线上监控。"
                "技术选型对比过本地缓存和分布式缓存，也说明了数据一致性风险和兜底。"
            ),
        )

        self.assertIn(
            session.current_question_meta["topic"],
            {"system-design", "distributed-system", "high-availability", "high-performance", "message-queue"},
        )
        self.assertIn("系统设计型", result["payload"]["opening_message"])

    def test_ai_application_direction_uses_ai_question_bank(self):
        engine = CampusInterviewEngine()
        result = engine.start(
            InterviewConfig(
                direction_id="ai_application",
                difficulty_id="campus",
                mode_id="fundamentals",
                interviewer_style_id="fundamental_chain",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        self.assertIn("AI 应用开发", result["payload"]["opening_message"])
        self.assertIn(
            session.current_question_meta["topic"],
            {"llm-basics", "llm-api", "prompt-engineering", "structured-output", "rag", "agent"},
        )

        engine.answer(session, "Token、上下文窗口、采样参数会影响成本、延迟和稳定性，需要用评测集和线上指标验证。")
        report = engine.report(session)

        self.assertEqual(report["direction"], "AI 应用开发")
        self.assertIn("AI 应用工程场景", report["study_guides"][0]["reference_answer"])


if __name__ == "__main__":
    unittest.main()
