from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.agents.workflow import CommerceAgent


GOLDEN_PATH = Path(__file__).resolve().parents[1] / "backend" / "evaluation" / "golden_cases.json"


class GoldenWorkflowTest(unittest.TestCase):
    def test_golden_cases_remain_stable(self) -> None:
        cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        agent = CommerceAgent()

        for case in cases:
            with self.subTest(case=case["id"]):
                result = agent.run(case["query"], session_id=f"golden-{case['id']}")
                trace_names = [step.name for step in result.trace]

                self.assertEqual(result.intent.get("category"), case["expected_category"])
                self.assertEqual(result.workflow_status, case["expected_status"])
                self.assertEqual(
                    trace_names[: len(case["expected_trace_prefix"])],
                    case["expected_trace_prefix"],
                )

                banned_spec = case.get("must_not_recommend_spec")
                if banned_spec:
                    for spec_name, spec_value in banned_spec.items():
                        self.assertTrue(
                            all(
                                item.get("specs", {}).get(spec_name) != spec_value
                                for item in result.recommendations
                            )
                        )


if __name__ == "__main__":
    unittest.main()
