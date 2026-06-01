from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.agents.shopping_copilot import ShoppingCopilot
from backend.agents.workflow import CommerceAgent


class ShoppingCopilotTest(unittest.TestCase):
    def test_search_event_builds_purchase_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            copilot = ShoppingCopilot(agent=CommerceAgent(), cache_dir=Path(tmp_dir))
            result = copilot.handle_event(
                {
                    "session_id": "copilot-search",
                    "user_id": "demo-user",
                    "event_type": "search_submitted",
                    "payload": {
                        "query": "预算2000以内，通勤用，想买降噪耳机，不要入耳式"
                    },
                }
            )

        self.assertEqual(result["stage"], "exploring")
        self.assertEqual(result["state"]["intent"]["category"], "headphones")
        self.assertIn("purchase_brief", {card["type"] for card in result["assistant_cards"]})

    def test_product_view_event_detects_constraint_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            copilot = ShoppingCopilot(agent=CommerceAgent(), cache_dir=Path(tmp_dir))
            copilot.handle_event(
                {
                    "session_id": "copilot-product",
                    "user_id": "demo-user",
                    "event_type": "search_submitted",
                    "payload": {
                        "query": "预算2000以内，通勤用，想买降噪耳机，不要入耳式"
                    },
                }
            )
            result = copilot.handle_event(
                {
                    "session_id": "copilot-product",
                    "user_id": "demo-user",
                    "event_type": "product_viewed",
                    "payload": {"product_id": "H003"},
                }
            )

        self.assertEqual(result["stage"], "product_viewing")
        self.assertEqual(result["intervention"]["level"], "critical")
        self.assertIn("硬约束", result["assistant_message"])

    def test_compare_and_checkout_events_return_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            copilot = ShoppingCopilot(agent=CommerceAgent(), cache_dir=Path(tmp_dir))
            compare_result = {}
            for event in [
                {
                    "event_type": "search_submitted",
                    "payload": {"query": "预算2000以内，通勤用，想买降噪耳机"},
                },
                {"event_type": "compare_added", "payload": {"product_id": "H004"}},
                {"event_type": "compare_added", "payload": {"product_id": "H005"}},
            ]:
                compare_result = copilot.handle_event(
                    {
                        "session_id": "copilot-journey",
                        "user_id": "demo-user",
                        **event,
                    }
                )
            copilot.handle_event(
                {
                    "session_id": "copilot-journey",
                    "user_id": "demo-user",
                    "event_type": "cart_added",
                    "payload": {"product_id": "H004"},
                }
            )
            checkout = copilot.handle_event(
                {
                    "session_id": "copilot-journey",
                    "user_id": "demo-user",
                    "event_type": "checkout_started",
                    "payload": {},
                }
            )

        self.assertIn("comparison", {card["type"] for card in compare_result["assistant_cards"]})
        self.assertIn("checkout_check", {card["type"] for card in checkout["assistant_cards"]})


if __name__ == "__main__":
    unittest.main()
