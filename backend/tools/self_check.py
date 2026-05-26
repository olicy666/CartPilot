from __future__ import annotations

from typing import Any


def self_check_recommendations(
    recommendations: list[dict[str, Any]],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    budget_max = constraints.get("budget_max")
    exclude_specs = constraints.get("exclude_specs", {})

    for item in recommendations:
        if budget_max is not None and item["price"] > budget_max:
            issues.append(
                {
                    "product_id": item["product_id"],
                    "issue": "recommended_product_over_budget",
                }
            )

        for spec_name, banned_values in exclude_specs.items():
            if spec_name == "risk":
                continue
            if item.get("specs", {}).get(spec_name) in banned_values:
                issues.append(
                    {
                        "product_id": item["product_id"],
                        "issue": f"excluded_spec_{spec_name}",
                    }
                )

        if not item.get("evidence"):
            issues.append(
                {
                    "product_id": item["product_id"],
                    "issue": "missing_review_evidence",
                }
            )

    return {
        "passed": not issues,
        "issues": issues,
        "checked_items": len(recommendations),
    }
