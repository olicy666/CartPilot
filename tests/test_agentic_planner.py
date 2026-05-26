from __future__ import annotations

import unittest
from typing import Any

from backend.agents.agentic_planner import (
    build_agentic_questions,
    explain_recommendations_with_agent,
    normalize_human_feedback_with_agent,
    plan_agent_workflow,
)
from backend.data_loader import DEFAULT_DATA_DIR, load_category_profiles


class FakeLLMClient:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.payload, {"ok": True, "model": "fake-agent"}


class AgenticPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        profiles = load_category_profiles(DEFAULT_DATA_DIR)
        self.profile = next(profile for profile in profiles if profile.category_id == "headphones")
        self.intent = {
            "task_type": "recommendation",
            "category": "headphones",
            "category_display_name": "耳机",
            "budget_max": None,
            "scenarios": [],
            "must_dimensions": [],
            "exclude_specs": {},
            "soft_preferences": [],
            "mentioned_products": [],
            "need_clarification": False,
        }

    def test_agent_can_generate_dynamic_choice_questions(self) -> None:
        questions, meta = build_agentic_questions(
            query="我想买耳机，戴久别累",
            intent=self.intent,
            profile=self.profile,
            user_memory={},
            client=FakeLLMClient(
                {
                    "questions": [
                        {
                            "id": "comfort_risk",
                            "title": "佩戴顾虑",
                            "question": "你更担心哪类佩戴问题？",
                            "input_type": "multi_choice",
                            "options": ["夹头", "闷热", "太重"],
                            "allow_custom": True,
                        }
                    ]
                }
            ),
            enabled=True,
        )

        self.assertTrue(meta["used"])
        self.assertEqual(questions[0]["source"], "agent")
        self.assertEqual(questions[0]["options"], ["夹头", "闷热", "太重"])

    def test_agent_can_normalize_feedback_to_structured_constraints(self) -> None:
        overrides, meta = normalize_human_feedback_with_agent(
            feedback="通勤办公室用，预算2000以内，更看重舒适和真实口碑，不要入耳式",
            current_intent=self.intent,
            profile=self.profile,
            client=FakeLLMClient(
                {
                    "intent_overrides": {
                        "budget_max": 2000,
                        "scenarios": ["通勤", "办公"],
                        "must_dimensions": ["comfort"],
                        "exclude_specs": {"form_factor": ["in_ear"]},
                        "soft_preferences": ["真实口碑"],
                        "preference_weights": {"dimension": 1.7, "evidence": 2.0},
                    }
                }
            ),
            enabled=True,
        )

        self.assertTrue(meta["used"])
        self.assertEqual(overrides["budget_max"], 2000)
        self.assertIn("通勤", overrides["scenarios"])
        self.assertIn("comfort", overrides["must_dimensions"])
        self.assertIn("in_ear", overrides["exclude_specs"]["form_factor"])
        self.assertGreaterEqual(overrides["preference_weights"]["evidence"], 2.0)

    def test_agent_can_plan_tools_and_review_queries(self) -> None:
        intent = dict(self.intent)
        intent.update({"must_dimensions": ["comfort"], "soft_preferences": ["真实口碑"]})
        plan, meta = plan_agent_workflow(
            query="买通勤降噪耳机，别踩坑",
            intent=intent,
            profile=self.profile,
            client=FakeLLMClient(
                {
                    "tool_sequence": [
                        "product_search",
                        "constraint_filter",
                        "review_vector_retrieval",
                        "rank_candidates",
                        "recommendation_explainer",
                        "self_check",
                    ],
                    "search_top_k": 12,
                    "need_comparison": False,
                    "review_plan": {
                        "aspects": ["comfort", "noise_cancellation"],
                        "queries": ["夹头 闷热 负面评价", "地铁通勤 降噪 风噪"],
                        "top_k": 4,
                    },
                    "ranking_focus": ["evidence", "dimension"],
                    "recommendation_style": "先讲避坑，再讲推荐",
                }
            ),
            enabled=True,
        )

        self.assertTrue(meta["used"])
        self.assertEqual(plan["search_top_k"], 12)
        self.assertEqual(plan["review_plan"]["top_k"], 4)
        self.assertIn("夹头 闷热 负面评价", plan["review_plan"]["queries"])
        self.assertEqual(plan["source"], "agent")

    def test_agent_can_rewrite_recommendation_explanations(self) -> None:
        recommendations = [
            {
                "product_id": "H001",
                "title": "测试耳机",
                "price": 999,
                "reasons": ["规则理由"],
                "risks": [],
                "evidence": [{"rating": 5, "content": "戴久不夹头", "matched_aspects": {"comfort": "positive"}}],
            }
        ]
        explained, summary, meta = explain_recommendations_with_agent(
            recommendations=recommendations,
            intent=self.intent,
            purchase_brief={},
            agent_plan={},
            client=FakeLLMClient(
                {
                    "answer_summary": "我会优先避开佩戴风险，再看降噪。",
                    "items": [
                        {
                            "product_id": "H001",
                            "reasons": ["评论里明确提到戴久不夹头，适合长时间佩戴。"],
                            "risks": [],
                        }
                    ],
                }
            ),
            enabled=True,
        )

        self.assertTrue(meta["used"])
        self.assertEqual(summary, "我会优先避开佩戴风险，再看降噪。")
        self.assertEqual(explained[0]["explanation_source"], "agent")
        self.assertIn("戴久不夹头", explained[0]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
