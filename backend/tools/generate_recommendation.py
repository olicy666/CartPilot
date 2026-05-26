from __future__ import annotations

from typing import Any

from backend.models import Product


def generate_recommendation(
    ranked_candidates: list[dict[str, Any]],
    evidence_by_product: dict[str, list[dict[str, Any]]],
    constraints: dict[str, Any],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for item in ranked_candidates[:top_n]:
        product: Product = item["product"]
        evidence = evidence_by_product.get(product.product_id, [])
        recommendations.append(
            {
                "product_id": product.product_id,
                "title": product.title,
                "brand": product.brand,
                "price": product.price,
                "category": product.category,
                "specs": product.specs,
                "tags": product.tags,
                "score": item["score"],
                "score_breakdown": item["score_breakdown"],
                "reasons": _build_reasons(product, constraints, evidence),
                "risks": _build_risks(product, evidence),
                "evidence": evidence,
            }
        )
    return recommendations


def _build_reasons(
    product: Product,
    constraints: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    budget_max = constraints.get("budget_max")
    if budget_max is not None and product.price <= budget_max:
        reasons.append(f"价格 {product.price:.0f} 元，满足预算上限 {budget_max:.0f} 元")

    if product.specs.get("noise_cancellation") is True:
        reasons.append("参数显示支持主动降噪")

    battery_life = product.specs.get("battery_life")
    if battery_life:
        reasons.append(f"续航参数为 {battery_life}")

    scenarios = constraints.get("scenarios", [])
    matched_scenarios = [scenario for scenario in scenarios if scenario in product.tags]
    if matched_scenarios:
        reasons.append("匹配使用场景：" + "、".join(matched_scenarios))

    positive_aspects = []
    for item in evidence:
        for aspect, sentiment in item.get("matched_aspects", {}).items():
            if sentiment == "positive":
                positive_aspects.append(aspect)
    if positive_aspects:
        reasons.append("评论证据支持：" + "、".join(sorted(set(positive_aspects))))

    return reasons or ["综合价格、参数和评论证据排序靠前"]


def _build_risks(product: Product, evidence: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for item in evidence:
        if item.get("rating", 5) <= 3:
            risks.append(item["content"])
        for aspect, sentiment in item.get("matched_aspects", {}).items():
            if sentiment == "negative":
                risks.append(f"{aspect} 相关评论存在负面反馈")
    return list(dict.fromkeys(risks))[:3]
