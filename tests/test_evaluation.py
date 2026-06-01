from __future__ import annotations

import unittest

from backend.evaluation.eval_agent import evaluate


class EvaluationTest(unittest.TestCase):
    def test_small_eval_runs(self) -> None:
        report = evaluate()

        self.assertGreaterEqual(report["total"], 5)
        self.assertGreaterEqual(report["metrics"]["category_correct"], 0.7)
        self.assertGreaterEqual(report["metrics"]["trace_contains_expected"], 0.7)
        self.assertGreaterEqual(report["metrics"]["constraint_adherence"], 0.9)
        self.assertGreaterEqual(report["metrics"]["hitl_clarification"], 0.9)
        self.assertGreaterEqual(report["metrics"]["rag_evidence_coverage"], 0.7)
        self.assertGreaterEqual(report["metrics"]["recommendation_traceable"], 0.9)
        self.assertGreaterEqual(report["metrics"]["self_check_passed"], 0.7)
        self.assertIn("task_success", report["metrics"])


if __name__ == "__main__":
    unittest.main()
