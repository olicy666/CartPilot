from __future__ import annotations

from typing import Any, TypedDict

from backend.models import CategoryProfile, Product, TraceStep


class CommerceAgentState(TypedDict, total=False):
    query: str
    user_id: str
    require_confirmation: bool
    use_llm: bool
    brief_overrides: dict[str, Any] | None
    human_feedback: str | None
    workflow_status: str

    profile: CategoryProfile | None
    category_scores: dict[str, float]
    intent: dict[str, Any]
    purchase_brief: dict[str, Any]
    llm_meta: dict[str, Any]
    agent_plan: dict[str, Any]
    agent_answer_summary: str | None

    candidates: list[Product]
    filtered_products: list[Product]
    rejected_products: list[dict[str, Any]]
    review_aspects: list[str]
    evidence_by_product: dict[str, list[dict[str, Any]]]
    ranked_candidates: list[dict[str, Any]]
    comparison_table: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]

    answer: str
    self_check: dict[str, Any]
    memory_update: dict[str, Any]
    trace: list[TraceStep]
