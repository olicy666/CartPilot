from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.workflow import CommerceAgent


DEFAULT_QUERY = "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY
    response = CommerceAgent().run(query=query, use_llm=True)
    summary = {
        "workflow_status": response.workflow_status,
        "parser_source": response.intent.get("parser_source"),
        "llm_meta": response.llm_meta,
        "intent": {
            "task_type": response.intent.get("task_type"),
            "category": response.intent.get("category"),
            "budget_max": response.intent.get("budget_max"),
            "scenarios": response.intent.get("scenarios"),
            "must_dimensions": response.intent.get("must_dimensions"),
            "exclude_specs": response.intent.get("exclude_specs"),
            "need_clarification": response.intent.get("need_clarification"),
        },
        "top_recommendations": [
            {
                "product_id": item["product_id"],
                "title": item["title"],
                "price": item["price"],
                "score": item["score"],
            }
            for item in response.recommendations[:3]
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
