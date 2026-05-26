from __future__ import annotations

import re
from typing import Any

from backend.models import CategoryProfile


_BUDGET_PATTERNS = [
    re.compile(r"预算\s*([0-9]+(?:\.[0-9]+)?)\s*(万|千|k|K)?"),
    re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(万|千|k|K)?\s*(?:元|块|人民币|rmb|RMB)?\s*(?:以内|以下|内|左右|不超过|别超过)"),
]


def parse_user_intent(
    query: str,
    profile: CategoryProfile | None,
    category_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    budget_max = _extract_budget_max(query)
    scenarios = _extract_scenarios(query, profile)
    must_dimensions = _extract_must_dimensions(query, profile)
    exclude_specs = _extract_exclude_specs(query)
    soft_preferences = _extract_soft_preferences(query)
    mentioned_products = _extract_mentioned_products(query, profile)
    task_type = _detect_task_type(query, mentioned_products)

    return {
        "task_type": task_type,
        "category": profile.category_id if profile else None,
        "category_display_name": profile.display_name if profile else None,
        "category_scores": category_scores or {},
        "budget_max": budget_max,
        "scenarios": scenarios,
        "must_dimensions": must_dimensions,
        "exclude_specs": exclude_specs,
        "soft_preferences": soft_preferences,
        "mentioned_products": mentioned_products,
        "need_clarification": profile is None,
        "parser_source": "rules",
    }


def _extract_budget_max(query: str) -> float | None:
    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(query)
        if match:
            number = float(match.group(1))
            unit = match.group(2)
            return _normalize_amount(number, unit)
    return None


def _normalize_amount(number: float, unit: str | None) -> float:
    if unit == "万":
        return number * 10000
    if unit in {"千", "k", "K"}:
        return number * 1000
    return number


def _extract_scenarios(query: str, profile: CategoryProfile | None) -> list[str]:
    scenario_aliases = {
        "通勤": ["通勤", "地铁", "公交"],
        "办公": ["办公", "办公室", "会议"],
        "游戏": ["游戏", "电竞"],
        "学习": ["学习", "学生", "上课"],
        "记笔记": ["记笔记", "手写", "笔记"],
        "剪视频": ["剪视频", "视频剪辑", "轻度剪视频"],
        "深度学习": ["深度学习", "训练模型", "跑模型"],
        "编程": ["编程", "写代码", "开发"],
        "家庭影院": ["家庭影院", "看电影", "客厅"],
        "小户型": ["小户型", "宿舍", "租房"],
    }
    if profile:
        for scenario in profile.scenario_weights:
            scenario_aliases.setdefault(scenario, [scenario])

    scenarios: list[str] = []
    for scenario, aliases in scenario_aliases.items():
        if any(alias in query for alias in aliases):
            scenarios.append(scenario)
    return scenarios


def _extract_must_dimensions(
    query: str, profile: CategoryProfile | None
) -> list[str]:
    if not profile:
        return []

    dimensions: list[str] = []
    for dimension in profile.decision_dimensions:
        if any(keyword in query for keyword in dimension.keywords):
            dimensions.append(dimension.name)
    return dimensions


def _extract_exclude_specs(query: str) -> dict[str, list[str]]:
    exclude_specs: dict[str, list[str]] = {}
    negative_markers = ["不要", "不想要", "别要", "拒绝", "不考虑", "排除"]

    def has_negative(term: str) -> bool:
        return any(marker + term in query for marker in negative_markers)

    if has_negative("入耳") or has_negative("入耳式"):
        exclude_specs.setdefault("form_factor", []).append("in_ear")
    if has_negative("头戴") or has_negative("头戴式"):
        exclude_specs.setdefault("form_factor", []).append("over_ear")
    if has_negative("太重") or "轻便" in query:
        exclude_specs.setdefault("risk", []).append("heavy")
    if has_negative("曲面屏"):
        exclude_specs.setdefault("panel_shape", []).append("curved")

    return exclude_specs


def _extract_soft_preferences(query: str) -> list[str]:
    preferences: list[str] = []
    keywords = [
        "舒适",
        "续航",
        "降噪",
        "散热",
        "轻便",
        "售后",
        "性价比",
        "屏幕",
        "护眼",
        "安静",
        "颜值",
    ]
    for keyword in keywords:
        if keyword in query:
            preferences.append(keyword)
    return preferences


def _extract_mentioned_products(
    query: str,
    profile: CategoryProfile | None,
) -> list[str]:
    candidates: list[str] = [
        product_name
        for product_name in
        [
            "iPad Air",
            "MatePad Pro",
            "小米 Pad",
            "MacBook Air",
            "ThinkPad",
            "AirPods Pro",
            "WH-1000XM5",
            "QuietComfort",
        ]
    ]

    mentioned = []
    normalized_query = query.lower()
    for candidate in candidates:
        if candidate and candidate.lower() in normalized_query and candidate not in mentioned:
            mentioned.append(candidate)
    return mentioned


def _detect_task_type(query: str, mentioned_products: list[str]) -> str:
    comparison_markers = ["对比", "比较", "哪个更", "哪款更", "选哪个", "怎么选", "还是"]
    if any(marker in query for marker in comparison_markers):
        return "comparison"
    if len(mentioned_products) >= 2:
        return "comparison"
    return "recommendation"
