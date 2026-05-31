from __future__ import annotations

from typing import Any


SPONSORED_TAGS = {"广告", "赞助", "sponsored", "ad"}
CONFLICT_TAGS = {"返佣", "affiliate", "commissioned", "利益相关"}


def evaluate_recommendation_safety(
    recommendations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    issues.extend(_sponsorship_issues(recommendations))
    issues.extend(_conflict_issues(recommendations))
    issues.extend(_brand_concentration_issues(recommendations))
    return issues


def _sponsorship_issues(recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues = []
    for item in recommendations:
        tags = {str(tag).lower() for tag in item.get("tags", [])}
        specs = item.get("specs", {}) if isinstance(item.get("specs"), dict) else {}
        sponsored = bool(specs.get("sponsored")) or bool(tags & SPONSORED_TAGS)
        disclosed = bool(specs.get("ad_disclosed")) or "已披露广告" in item.get("tags", [])
        if sponsored and not disclosed:
            issues.append(
                {
                    "product_id": str(item.get("product_id")),
                    "issue": "sponsored_product_requires_disclosure",
                }
            )
    return issues


def _conflict_issues(recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues = []
    for item in recommendations:
        tags = {str(tag).lower() for tag in item.get("tags", [])}
        specs = item.get("specs", {}) if isinstance(item.get("specs"), dict) else {}
        conflict = bool(specs.get("affiliate")) or bool(tags & CONFLICT_TAGS)
        disclosed = bool(specs.get("conflict_disclosed")) or "已披露利益关系" in item.get("tags", [])
        if conflict and not disclosed:
            issues.append(
                {
                    "product_id": str(item.get("product_id")),
                    "issue": "commercial_conflict_requires_disclosure",
                }
            )
    return issues


def _brand_concentration_issues(recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    brands = [str(item.get("brand", "")).strip() for item in recommendations if item.get("brand")]
    if len(brands) < 3:
        return []
    dominant_brand = max(set(brands), key=brands.count)
    if brands.count(dominant_brand) == len(brands):
        return [
            {
                "product_id": "all",
                "issue": f"brand_concentration:{dominant_brand}",
            }
        ]
    return []
