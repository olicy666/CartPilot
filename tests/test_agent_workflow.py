from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.agents.workflow import CommerceAgent


class AgentWorkflowTest(unittest.TestCase):
    def test_headphone_agent_trace_and_self_check(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"
        )

        step_names = [step.name for step in result.trace]

        self.assertIn("Intent Parser", step_names)
        self.assertIn("Purchase Brief", step_names)
        self.assertIn("Product Search", step_names)
        self.assertIn("Constraint Filter", step_names)
        self.assertIn("Review Evidence Retrieval", step_names)
        self.assertIn("Self Check", step_names)
        self.assertEqual(result.workflow_status, "completed")
        self.assertEqual(result.purchase_brief["category"]["id"], "headphones")
        self.assertTrue(result.recommendations)
        self.assertTrue(result.self_check["passed"])
        self.assertTrue(
            all(item["specs"].get("form_factor") != "in_ear" for item in result.recommendations)
        )

    def test_unknown_category_asks_clarification(self) -> None:
        agent = CommerceAgent()
        result = agent.run("我想买个送朋友的东西，预算500")

        self.assertFalse(result.recommendations)
        self.assertIn("品类", result.answer)
        self.assertFalse(result.self_check["passed"])
        self.assertEqual(result.workflow_status, "needs_clarification")

    def test_purchase_brief_can_pause_for_human_confirmation(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "预算8000，想买一台适合跑深度学习和写代码的笔记本",
            require_confirmation=True,
        )

        step_names = [step.name for step in result.trace]

        self.assertIn("Human-in-loop Checkpoint", step_names)
        self.assertEqual(result.workflow_status, "awaiting_user_confirmation")
        self.assertEqual(result.purchase_brief["status"], "awaiting_user_confirmation")
        self.assertIn("你更注重哪方面", result.answer)
        priority_question = next(
            item
            for item in result.purchase_brief["confirmation_questions"]
            if item["id"] == "priority"
        )
        self.assertEqual(priority_question["input_type"], "multi_choice")
        self.assertTrue(priority_question["options"])
        self.assertFalse(result.recommendations)

    def test_purchase_brief_overrides_continue_workflow(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "预算8000，想买一台适合跑深度学习和写代码的笔记本",
            require_confirmation=True,
            brief_overrides={"budget_max": 9000},
        )

        self.assertEqual(result.workflow_status, "completed")
        self.assertEqual(result.intent["budget_max"], 9000)
        self.assertTrue(result.recommendations)

    def test_human_feedback_answers_drive_recommendation(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "我想买降噪耳机",
            require_confirmation=True,
            human_feedback="预算2000元以内；使用场景：通勤、办公；更看重：舒适度、真实口碑；不能接受：不要入耳式",
        )

        self.assertEqual(result.workflow_status, "completed")
        self.assertEqual(result.intent["budget_max"], 2000)
        self.assertIn("通勤", result.intent["scenarios"])
        self.assertIn("in_ear", result.intent["exclude_specs"]["form_factor"])
        self.assertEqual(
            result.purchase_brief["human_feedback"],
            "预算2000元以内；使用场景：通勤、办公；更看重：舒适度、真实口碑；不能接受：不要入耳式",
        )
        self.assertGreaterEqual(result.purchase_brief["preference_weights"]["dimension"], 1.5)
        self.assertGreaterEqual(result.purchase_brief["preference_weights"]["evidence"], 1.8)
        self.assertTrue(
            all(item["specs"].get("form_factor") != "in_ear" for item in result.recommendations)
        )

    def test_preference_weights_are_applied(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "预算2000以内，买通勤降噪耳机，不要入耳式",
            brief_overrides={
                "preference_weights": {
                    "budget": 0.5,
                    "scenario": 1.0,
                    "dimension": 1.0,
                    "evidence": 2.0,
                }
            },
        )

        self.assertEqual(result.purchase_brief["preference_weights"]["evidence"], 2.0)
        self.assertGreater(
            result.recommendations[0]["score_breakdown"]["evidence"],
            0.4,
        )

    def test_comparison_task_builds_table(self) -> None:
        agent = CommerceAgent()
        result = agent.run("iPad Air、华为 MatePad Pro 和小米 Pad 这几个，哪个更适合记笔记和轻度剪视频？")

        self.assertEqual(result.intent["task_type"], "comparison")
        self.assertTrue(result.comparison_table)
        self.assertIn("Comparison", [step.name for step in result.trace])

    def test_llm_parser_falls_back_without_api_key(self) -> None:
        with patch(
            "backend.agents.graph.parse_intent_with_llm",
            return_value=(None, {"ok": False, "reason": "llm_api_key_missing"}),
        ):
            agent = CommerceAgent()
            result = agent.run("预算2000以内，买通勤降噪耳机", use_llm=True)

        self.assertEqual(result.intent["parser_source"], "rules")
        self.assertFalse(result.llm_meta["used"])
        self.assertEqual(result.llm_meta["reason"], "llm_api_key_missing")

    def test_session_checkpoint_can_resume_human_feedback(self) -> None:
        agent = CommerceAgent()
        session_id = "test-session-resume"
        first = agent.run(
            "我想买降噪耳机",
            require_confirmation=True,
            session_id=session_id,
        )
        self.assertEqual(first.workflow_status, "awaiting_user_confirmation")
        self.assertTrue(agent.checkpoints.load_pending(session_id))

        resumed = agent.run(
            "继续",
            session_id=session_id,
            human_feedback="预算2000以内，通勤用，不要入耳式",
        )
        self.assertEqual(resumed.workflow_status, "completed")
        self.assertIsNone(agent.checkpoints.load_pending(session_id))
        self.assertEqual(resumed.query, "我想买降噪耳机")

    def test_session_followup_answers_from_previous_result(self) -> None:
        agent = CommerceAgent()
        session_id = "test-session-followup"
        agent.run(
            "预算2000以内，买通勤降噪耳机，不要入耳式",
            session_id=session_id,
        )

        followup = agent.run(
            "为什么不推荐 Apple AirPods Pro 2 入耳式降噪耳机？",
            session_id=session_id,
        )

        self.assertEqual(followup.workflow_status, "followup_answered")
        self.assertIn("主要原因", followup.answer)
        self.assertIn("Conversation Follow-up", [step.name for step in followup.trace])

    def test_monitoring_metrics_are_recorded(self) -> None:
        agent = CommerceAgent()
        result = agent.run(
            "预算2000以内，买通勤降噪耳机",
            session_id="test-session-monitoring",
        )

        self.assertGreaterEqual(result.monitoring["total_runs"], 1)
        self.assertIn("completed", result.monitoring["workflow_status_counts"])


if __name__ == "__main__":
    unittest.main()
