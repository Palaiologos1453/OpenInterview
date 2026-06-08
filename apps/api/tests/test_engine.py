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
        self.assertIn("后端开发", payload["opening_message"])
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
                direction_id="frontend",
                difficulty_id="internship",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]
        engine.answer(session, "我会从背景、方案、结果三个部分回答，并补充浏览器渲染和网络请求细节。")

        report = engine.report(session)

        self.assertEqual(report["direction"], "前端开发")
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

        self.assertEqual(report["turns"][0]["question_meta"]["id"], "backend-index-btree")
        self.assertTrue(report["turns"][0]["rubric_gaps"])
        self.assertTrue(any("database" in item or "索引" in item for item in report["improvements"]))
        self.assertTrue(report["practice_drills"])
        self.assertTrue(report["answer_guides"])
        self.assertIn("example_answer", report["answer_guides"][0])

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
                resume_text="项目：订单系统，负责缓存、接口和数据库优化。",
                provider_config=MOCK_PROVIDER,
            )
        )
        session = result["session"]

        turn = engine.answer(session, "做了一个项目。")

        self.assertIn("继续补充", turn["next_question"])
        self.assertIn("个人贡献", turn["next_question"])
        self.assertEqual(session.current_question_meta["phase"], "project")


if __name__ == "__main__":
    unittest.main()
