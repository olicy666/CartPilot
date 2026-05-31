from __future__ import annotations

import unittest

from backend.tools.self_check import self_check_recommendations


class SafetyPolicyTest(unittest.TestCase):
    def test_sponsored_product_requires_disclosure(self) -> None:
        check = self_check_recommendations(
            recommendations=[
                {
                    "product_id": "AD001",
                    "price": 99,
                    "specs": {"sponsored": True},
                    "tags": [],
                    "evidence": [{"review_id": "R1"}],
                }
            ],
            constraints={"budget_max": 100, "exclude_specs": {}},
        )

        self.assertTrue(check["passed"])
        self.assertFalse(check["safety_passed"])
        self.assertEqual(
            check["safety_issues"][0]["issue"],
            "sponsored_product_requires_disclosure",
        )


if __name__ == "__main__":
    unittest.main()
