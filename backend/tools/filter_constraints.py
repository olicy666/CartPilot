from __future__ import annotations

from typing import Any

from backend.models import Product


def filter_by_constraints(
    products: list[Product],
    constraints: dict[str, Any],
) -> tuple[list[Product], list[dict[str, Any]]]:
    kept: list[Product] = []
    rejected: list[dict[str, Any]] = []

    for product in products:
        reasons = _violation_reasons(product, constraints)
        if reasons:
            rejected.append(
                {
                    "product_id": product.product_id,
                    "title": product.title,
                    "reasons": reasons,
                }
            )
        else:
            kept.append(product)

    return kept, rejected


def _violation_reasons(product: Product, constraints: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    budget_max = constraints.get("budget_max")
    if budget_max is not None and product.price > budget_max:
        reasons.append(f"价格 {product.price:.0f} 超过预算 {budget_max:.0f}")

    exclude_specs = constraints.get("exclude_specs", {})
    for spec_name, banned_values in exclude_specs.items():
        if spec_name == "risk":
            if "heavy" in banned_values and _is_heavy(product):
                reasons.append("重量或定位不符合轻便偏好")
            continue

        value = product.specs.get(spec_name)
        if value in banned_values:
            reasons.append(f"{spec_name}={value} 命中排除条件")

    must_dimensions = constraints.get("must_dimensions", [])
    if "noise_cancellation" in must_dimensions:
        if product.specs.get("noise_cancellation") is not True:
            reasons.append("缺少主动降噪")

    return reasons


def _is_heavy(product: Product) -> bool:
    weight_g = product.specs.get("weight_g")
    weight_kg = product.specs.get("weight_kg")
    if isinstance(weight_g, (int, float)):
        return weight_g > 300
    if isinstance(weight_kg, (int, float)):
        return weight_kg > 1.8
    return False
