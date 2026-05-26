from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.agents.intent_parser import parse_user_intent
from backend.models import CategoryProfile


def build_human_questions(
    intent: dict[str, Any],
    profile: CategoryProfile,
) -> list[dict[str, Any]]:
    """Build concise guide questions for the user before recommendation."""
    questions: list[dict[str, Any]] = []

    if intent.get("budget_max") is None:
        questions.append(
            {
                "id": "budget",
                "title": "预算边界",
                "question": "这次购买有没有明确预算上限，或者可接受的价格区间？",
                "input_type": "single_choice",
                "options": _budget_options(),
                "allow_custom": True,
            }
        )

    if not intent.get("scenarios"):
        questions.append(
            {
                "id": "scenario",
                "title": "使用场景",
                "question": "主要会在什么场景使用？可以描述通勤、办公、学习、游戏、家庭等具体情况。",
                "input_type": "multi_choice",
                "options": _scenario_options(profile),
                "allow_custom": True,
            }
        )

    questions.append(
        {
            "id": "priority",
            "title": "优先级",
            "question": _priority_question(profile),
            "input_type": "multi_choice",
            "options": _priority_options(profile),
            "allow_custom": True,
        }
    )
    questions.append(
        {
            "id": "avoid",
            "title": "不能接受",
            "question": "有没有明确不想要的类型、品牌、形态或风险点？",
            "input_type": "multi_choice",
            "options": _avoid_options(profile),
            "allow_custom": True,
        }
    )

    return questions[:4]


def parse_human_feedback(
    feedback: str,
    current_intent: dict[str, Any],
    profile: CategoryProfile,
) -> dict[str, Any]:
    """Convert a free-form user clarification into brief overrides."""
    if not feedback.strip():
        return {}

    parsed = parse_user_intent(feedback, profile, current_intent.get("category_scores"))
    overrides = deepcopy(current_intent)

    if parsed.get("budget_max") is not None:
        overrides["budget_max"] = parsed["budget_max"]

    overrides["scenarios"] = _merge_unique(
        current_intent.get("scenarios", []),
        parsed.get("scenarios", []),
    )
    overrides["must_dimensions"] = _merge_unique(
        current_intent.get("must_dimensions", []),
        parsed.get("must_dimensions", []),
    )
    overrides["soft_preferences"] = _merge_unique(
        current_intent.get("soft_preferences", []),
        parsed.get("soft_preferences", []),
    )
    overrides["exclude_specs"] = _merge_exclude_specs(
        current_intent.get("exclude_specs", {}),
        parsed.get("exclude_specs", {}),
    )
    overrides["preference_weights"] = _infer_preference_weights(
        feedback,
        profile,
        current_intent.get("preference_weights", {}),
    )
    overrides["human_feedback"] = feedback.strip()
    overrides["need_clarification"] = False
    return overrides


def merge_overrides(
    base: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any] | None:
    if not base and not incoming:
        return None
    merged = dict(incoming)
    for key, value in (base or {}).items():
        if key == "exclude_specs":
            merged[key] = _merge_exclude_specs(
                merged.get("exclude_specs", {}),
                value,
            )
        elif key == "preference_weights":
            weights = dict(merged.get("preference_weights", {}))
            weights.update(value or {})
            merged[key] = weights
        elif key in {"scenarios", "must_dimensions", "soft_preferences"}:
            merged[key] = _merge_unique(merged.get(key, []), value or [])
        else:
            merged[key] = value
    return merged


def _priority_question(profile: CategoryProfile) -> str:
    labels = [dimension.label for dimension in profile.decision_dimensions[:5]]
    joined = "、".join(labels)
    return f"你更注重哪方面？比如 {joined}、价格、真实口碑或售后风险。"


def _budget_options() -> list[str]:
    return ["500元以内", "1000元以内", "2000元以内", "5000元以内", "10000元以内"]


def _scenario_options(profile: CategoryProfile) -> list[str]:
    common = [
        "通勤",
        "办公",
        "学习",
        "游戏",
        "家庭",
        "深度学习",
        "编程",
        "记笔记",
        "剪视频",
        "小户型",
    ]
    return _unique_strings([*profile.scenario_weights.keys(), *common])[:6]


def _priority_options(profile: CategoryProfile) -> list[str]:
    dimensions = [dimension.label for dimension in profile.decision_dimensions[:5]]
    return _unique_strings([*dimensions, "价格/性价比", "真实口碑", "售后风险"])[:8]


def _avoid_options(profile: CategoryProfile) -> list[str]:
    category_options = {
        "headphones": ["不要入耳式", "不要头戴式", "不要太重", "不要夹头"],
        "laptop": ["不要太重", "不要噪音大", "不要散热差", "不要售后风险"],
        "tablet": ["不要配件太贵", "不要软件适配差", "不要太重"],
        "phone": ["不要发热", "不要信号弱", "不要续航差"],
        "monitor": ["不要曲面屏", "不要拖影", "不要漏光", "不要支架不稳"],
        "projector": ["不要白天不够亮", "不要风扇噪音", "不要系统广告"],
        "coffee_machine": ["不要清洁麻烦", "不要耗材贵", "不要噪音大"],
        "air_fryer": ["不要清洁麻烦", "不要涂层磨损", "不要占地大"],
    }
    defaults = [f"不要{risk}" for risk in profile.common_risks[:4]]
    return _unique_strings([*category_options.get(profile.category_id, []), *defaults, "不要太贵"])[:6]


def _infer_preference_weights(
    feedback: str,
    profile: CategoryProfile,
    current_weights: dict[str, Any],
) -> dict[str, float]:
    weights = {
        "budget": 1.0,
        "scenario": 1.0,
        "dimension": 1.0,
        "evidence": 1.0,
    }
    for key, value in (current_weights or {}).items():
        if key in weights and isinstance(value, (int, float)):
            weights[key] = float(value)

    text = feedback.lower()
    if any(term in text for term in ["价格", "预算", "便宜", "性价比", "不要太贵"]):
        weights["budget"] = max(weights["budget"], 1.7)
    if any(term in text for term in ["价格无所谓", "预算无所谓", "不太在意价格"]):
        weights["budget"] = min(weights["budget"], 0.6)
    if any(term in text for term in ["场景", "通勤", "办公", "游戏", "学习", "家用", "深度学习"]):
        weights["scenario"] = max(weights["scenario"], 1.4)
    if any(term in text for term in ["口碑", "评价", "评论", "真实反馈", "差评", "风险", "售后"]):
        weights["evidence"] = max(weights["evidence"], 1.8)
    if any(term in text for term in ["参数", "性能", "续航", "降噪", "舒适", "屏幕", "显卡", "内存"]):
        weights["dimension"] = max(weights["dimension"], 1.5)

    for dimension in profile.decision_dimensions:
        if any(keyword.lower() in text for keyword in dimension.keywords):
            weights["dimension"] = max(weights["dimension"], 1.5)
            if dimension.name in {"comfort", "cooling", "screen", "battery_life"}:
                weights["evidence"] = max(weights["evidence"], 1.4)

    return weights


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing or [])
    for item in incoming or []:
        if item not in merged:
            merged.append(item)
    return merged


def _unique_strings(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique


def _merge_exclude_specs(
    existing: dict[str, list[str]],
    incoming: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged = {key: list(value) for key, value in (existing or {}).items()}
    for key, values in (incoming or {}).items():
        merged[key] = _merge_unique(merged.get(key, []), values)
    return merged
