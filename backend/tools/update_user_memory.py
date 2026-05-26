from __future__ import annotations

from typing import Any


def update_user_memory(
    memory: dict[str, Any],
    user_id: str,
    intent: dict[str, Any],
) -> dict[str, Any]:
    user_memory = memory.setdefault(user_id, {})

    if intent.get("budget_max") is not None:
        user_memory["last_budget_max"] = intent["budget_max"]
    if intent.get("category"):
        user_memory["last_category"] = intent["category"]
    if intent.get("scenarios"):
        user_memory["recent_scenarios"] = _merge_unique(
            user_memory.get("recent_scenarios", []),
            intent["scenarios"],
        )
    if intent.get("soft_preferences"):
        user_memory["soft_preferences"] = _merge_unique(
            user_memory.get("soft_preferences", []),
            intent["soft_preferences"],
        )

    return user_memory


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    return merged[-10:]
