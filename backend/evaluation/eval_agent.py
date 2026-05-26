from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.workflow import CommerceAgent


CASES_PATH = Path(__file__).resolve().parent / "test_cases.json"


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def evaluate() -> dict[str, Any]:
    agent = CommerceAgent()
    cases = load_cases()
    results = []
    counters = {
        "category_correct": 0,
        "clarification_correct": 0,
        "task_type_correct": 0,
        "trace_contains_expected": 0,
        "top_product_correct": 0,
    }

    for case in cases:
        response = agent.run(
            query=case["query"],
            brief_overrides=case.get("brief_overrides"),
        )
        trace_steps = [step.name for step in response.trace]
        category_ok = response.intent.get("category") == case.get("expected_category")
        clarification_ok = (
            response.intent.get("need_clarification") == case.get("need_clarification")
        )
        task_type_ok = (
            "expected_task_type" not in case
            or response.intent.get("task_type") == case["expected_task_type"]
        )
        trace_ok = all(
            step in trace_steps for step in case.get("expected_trace_steps", [])
        )
        top_product_ok = (
            "expected_top_product_id" not in case
            or (
                bool(response.recommendations)
                and response.recommendations[0]["product_id"] == case["expected_top_product_id"]
            )
        )

        counters["category_correct"] += int(category_ok)
        counters["clarification_correct"] += int(clarification_ok)
        counters["task_type_correct"] += int(task_type_ok)
        counters["trace_contains_expected"] += int(trace_ok)
        counters["top_product_correct"] += int(top_product_ok)
        results.append(
            {
                "id": case["id"],
                "category_ok": category_ok,
                "clarification_ok": clarification_ok,
                "task_type_ok": task_type_ok,
                "trace_ok": trace_ok,
                "top_product_ok": top_product_ok,
                "workflow_status": response.workflow_status,
            }
        )

    total = len(cases)
    return {
        "total": total,
        "metrics": {
            name: round(value / total, 3)
            for name, value in counters.items()
        },
        "cases": results,
    }


def main() -> None:
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
