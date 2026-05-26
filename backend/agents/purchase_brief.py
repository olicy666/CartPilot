from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.agents.human_feedback import build_human_questions
from backend.models import CategoryProfile


def build_purchase_brief(
    query: str,
    intent: dict[str, Any],
    profile: CategoryProfile,
    user_memory: dict[str, Any],
    brief_overrides: dict[str, Any] | None = None,
    require_confirmation: bool = False,
    confirmation_questions: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the editable task card used by the human-in-loop step."""
    updated_intent = deepcopy(intent)
    for key, value in (brief_overrides or {}).items():
        if key in updated_intent or key in {
            "banned_product_ids",
            "pinned_product_ids",
            "preference_weights",
            "human_feedback",
        }:
            updated_intent[key] = value

    dimensions = [
        {"name": dimension.name, "label": dimension.label}
        for dimension in profile.decision_dimensions
    ]
    brief = {
        "status": _brief_status(require_confirmation, brief_overrides),
        "query": query,
        "category": {
            "id": profile.category_id,
            "display_name": profile.display_name,
            "matched_aliases": [
                alias for alias in profile.aliases if alias.lower() in query.lower()
            ],
        },
        "budget_max": updated_intent.get("budget_max"),
        "scenarios": updated_intent.get("scenarios", []),
        "must_dimensions": updated_intent.get("must_dimensions", []),
        "exclude_specs": updated_intent.get("exclude_specs", {}),
        "soft_preferences": updated_intent.get("soft_preferences", []),
        "mentioned_products": updated_intent.get("mentioned_products", []),
        "banned_product_ids": updated_intent.get("banned_product_ids", []),
        "pinned_product_ids": updated_intent.get("pinned_product_ids", []),
        "preference_weights": _preference_weights(updated_intent.get("preference_weights", {})),
        "human_feedback": updated_intent.get("human_feedback"),
        "decision_dimensions": dimensions,
        "common_risks": profile.common_risks,
        "required_specs": profile.required_specs,
        "memory_context": user_memory,
        "confirmation_prompts": _confirmation_prompts(updated_intent),
        "confirmation_questions": confirmation_questions or build_human_questions(updated_intent, profile),
    }
    return brief, updated_intent


def _brief_status(
    require_confirmation: bool,
    brief_overrides: dict[str, Any] | None,
) -> str:
    if brief_overrides:
        return "confirmed_with_overrides"
    if require_confirmation:
        return "awaiting_user_confirmation"
    return "auto_confirmed"


def _confirmation_prompts(intent: dict[str, Any]) -> list[str]:
    prompts: list[str] = []
    if intent.get("budget_max") is None:
        prompts.append("是否需要补充预算上限？")
    if not intent.get("scenarios"):
        prompts.append("主要使用场景是什么？")
    if not intent.get("must_dimensions") and not intent.get("soft_preferences"):
        prompts.append("你最看重哪些维度？")
    return prompts


def _preference_weights(raw_weights: dict[str, Any]) -> dict[str, float]:
    weights = {
        "budget": 1.0,
        "scenario": 1.0,
        "dimension": 1.0,
        "evidence": 1.0,
    }
    if not isinstance(raw_weights, dict):
        return weights
    for key in weights:
        value = raw_weights.get(key)
        if isinstance(value, (int, float)):
            weights[key] = float(value)
    return weights
