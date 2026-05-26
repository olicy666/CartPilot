from __future__ import annotations

import re
from typing import Any

from backend.models import CategoryProfile, Product


def rank_candidates(
    products: list[Product],
    constraints: dict[str, Any],
    evidence_by_product: dict[str, list[dict[str, Any]]],
    profile: CategoryProfile | None,
) -> list[dict[str, Any]]:
    ranked = []
    for product in products:
        score, breakdown = _score_candidate(
            product=product,
            constraints=constraints,
            evidence=evidence_by_product.get(product.product_id, []),
            profile=profile,
        )
        ranked.append(
            {
                "product": product,
                "score": round(score, 3),
                "score_breakdown": breakdown,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["product"].price))
    return ranked


def _score_candidate(
    product: Product,
    constraints: dict[str, Any],
    evidence: list[dict[str, Any]],
    profile: CategoryProfile | None,
) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}
    weights = _score_weights(constraints.get("preference_weights", {}))

    budget_score = _budget_score(product.price, constraints.get("budget_max"))
    breakdown["budget"] = budget_score * weights["budget"]

    scenario_score = _scenario_score(product, constraints.get("scenarios", []))
    breakdown["scenario"] = scenario_score * weights["scenario"]

    dimension_score = _dimension_score(
        product=product,
        dimensions=constraints.get("must_dimensions", []),
        profile=profile,
    )
    breakdown["dimension"] = dimension_score * weights["dimension"]

    evidence_score = _evidence_score(evidence)
    breakdown["evidence"] = evidence_score * weights["evidence"]

    score = sum(breakdown.values())
    return score, breakdown


def _score_weights(raw_weights: dict[str, Any]) -> dict[str, float]:
    defaults = {
        "budget": 1.0,
        "scenario": 1.0,
        "dimension": 1.0,
        "evidence": 1.0,
    }
    if not isinstance(raw_weights, dict):
        return defaults
    for key in defaults:
        value = raw_weights.get(key)
        if isinstance(value, (int, float)):
            defaults[key] = max(0.0, min(float(value), 3.0))
    return defaults


def _budget_score(price: float, budget_max: float | None) -> float:
    if budget_max is None:
        return 0.1
    if price > budget_max:
        return -1.0
    return 0.15 + min((budget_max - price) / max(budget_max, 1), 0.25)


def _scenario_score(product: Product, scenarios: list[str]) -> float:
    if not scenarios:
        return 0.1
    hits = sum(1 for scenario in scenarios if scenario in product.tags)
    return hits * 0.2


def _dimension_score(
    product: Product,
    dimensions: list[str],
    profile: CategoryProfile | None,
) -> float:
    if not dimensions and profile:
        dimensions = profile.dimension_names[:3]
    score = 0.0
    for dimension in dimensions:
        score += _score_dimension(product, dimension)
    return min(score, 0.8)


def _score_dimension(product: Product, dimension: str) -> float:
    specs = product.specs
    tags = set(product.tags)

    if dimension == "noise_cancellation":
        return 0.2 if specs.get("noise_cancellation") else 0.0
    if dimension == "battery_life":
        hours = _extract_number(specs.get("battery_life"))
        return 0.2 if hours and hours >= 20 else 0.08 if hours else 0.0
    if dimension == "comfort":
        return 0.15 if "舒适" in tags or "轻便" in tags else 0.05
    if dimension == "gpu":
        gpu = str(specs.get("gpu", "")).lower()
        return 0.22 if any(token in gpu for token in ["rtx", "m", "radeon"]) else 0.05
    if dimension == "ram":
        ram = specs.get("ram_gb")
        return 0.18 if isinstance(ram, (int, float)) and ram >= 16 else 0.05
    if dimension in specs and specs.get(dimension) not in {None, "", False}:
        return 0.12
    return 0.0


def _evidence_score(evidence: list[dict[str, Any]]) -> float:
    score = 0.0
    for item in evidence:
        sentiments = item.get("matched_aspects", {}).values()
        score += 0.08
        score += sum(0.08 for sentiment in sentiments if sentiment == "positive")
        score -= sum(0.08 for sentiment in sentiments if sentiment == "negative")
    return max(min(score, 0.5), -0.3)


def _extract_number(value: Any) -> float | None:
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", str(value))
    return float(match.group(0)) if match else None
