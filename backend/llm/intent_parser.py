from __future__ import annotations

import json
from typing import Any

from backend.llm.client import LLMClient
from backend.models import CategoryProfile


SYSTEM_PROMPT = """你是电商导购 Agent 的意图解析器。
只输出 JSON，不要输出 Markdown。
目标是把用户购物需求解析成可执行约束，未知字段用 null 或空数组。
不要创造不存在的品类 id，只能使用候选品类中的 category_id。
"""


def parse_intent_with_llm(
    query: str,
    profiles: list[CategoryProfile],
    category_scores: dict[str, float],
    fallback_intent: dict[str, Any],
    client: LLMClient,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    prompt = {
        "query": query,
        "candidate_categories": [
            {
                "category_id": profile.category_id,
                "display_name": profile.display_name,
                "aliases": profile.aliases,
                "decision_dimensions": profile.dimension_names,
                "scenario_names": list(profile.scenario_weights.keys()),
            }
            for profile in profiles
        ],
        "category_scores_from_rules": category_scores,
        "fallback_intent_from_rules": fallback_intent,
        "required_output_schema": {
            "task_type": "recommendation | comparison | clarification",
            "category": "string|null",
            "budget_max": "number|null",
            "scenarios": ["string"],
            "must_dimensions": ["string"],
            "exclude_specs": {"spec_name": ["banned_value"]},
            "soft_preferences": ["string"],
            "mentioned_products": ["string"],
            "need_clarification": "boolean",
            "clarification_reason": "string|null"
        },
    }
    parsed, meta = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(prompt, ensure_ascii=False),
        temperature=0.0,
    )
    if parsed is None:
        return None, meta

    normalized = _normalize_llm_intent(parsed, profiles, fallback_intent)
    return normalized, meta


def _normalize_llm_intent(
    parsed: dict[str, Any],
    profiles: list[CategoryProfile],
    fallback_intent: dict[str, Any],
) -> dict[str, Any]:
    allowed_categories = {profile.category_id: profile for profile in profiles}
    category = parsed.get("category")
    if category not in allowed_categories:
        category = fallback_intent.get("category")

    profile = allowed_categories.get(category)
    intent = dict(fallback_intent)
    intent.update(
        {
            "task_type": _pick_task_type(parsed.get("task_type")),
            "category": category,
            "category_display_name": profile.display_name if profile else None,
            "budget_max": _pick_number(parsed.get("budget_max"), fallback_intent.get("budget_max")),
            "scenarios": _pick_string_list(parsed.get("scenarios"), fallback_intent.get("scenarios", [])),
            "must_dimensions": _pick_string_list(parsed.get("must_dimensions"), fallback_intent.get("must_dimensions", [])),
            "exclude_specs": _pick_exclude_specs(parsed.get("exclude_specs"), fallback_intent.get("exclude_specs", {})),
            "soft_preferences": _pick_string_list(parsed.get("soft_preferences"), fallback_intent.get("soft_preferences", [])),
            "mentioned_products": _pick_string_list(parsed.get("mentioned_products"), fallback_intent.get("mentioned_products", [])),
            "need_clarification": bool(parsed.get("need_clarification", fallback_intent.get("need_clarification", False))),
            "clarification_reason": parsed.get("clarification_reason"),
            "parser_source": "llm",
        }
    )
    if intent["category"] is None:
        intent["need_clarification"] = True
    return intent


def _pick_task_type(value: Any) -> str:
    return value if value in {"recommendation", "comparison", "clarification"} else "recommendation"


def _pick_number(value: Any, fallback: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _pick_string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    return [item for item in value if isinstance(item, str)]


def _pick_exclude_specs(value: Any, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return dict(fallback)
    result: dict[str, list[str]] = {}
    for key, items in value.items():
        if isinstance(key, str) and isinstance(items, list):
            result[key] = [item for item in items if isinstance(item, str)]
    return result or dict(fallback)
