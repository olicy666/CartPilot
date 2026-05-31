from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from backend.agents.human_feedback import build_human_questions, parse_human_feedback
from backend.llm.client import LLMClient
from backend.models import CategoryProfile
from backend.prompts.registry import get_prompt


SYSTEM_PROMPT_TEMPLATE = get_prompt("agentic_planner_system")
SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.text


def build_agentic_questions(
    query: str,
    intent: dict[str, Any],
    profile: CategoryProfile,
    user_memory: dict[str, Any],
    client: LLMClient,
    enabled: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fallback = build_human_questions(intent, profile)
    if not enabled:
        return fallback, _prompt_meta({"used": False, "reason": "agentic_questions_disabled"})

    payload = {
        "task": "generate_dynamic_human_in_loop_questions",
        "query": query,
        "current_intent": intent,
        "category_profile": _profile_payload(profile),
        "user_memory": user_memory,
        "fallback_questions": fallback,
        "required_output_schema": {
            "questions": [
                {
                    "id": "short_stable_id",
                    "title": "short_title",
                    "question": "user_facing_question",
                    "input_type": "single_choice|multi_choice",
                    "options": ["2-8 concise options"],
                    "allow_custom": True,
                }
            ]
        },
        "rules": [
            "最多 4 个问题",
            "不要重复询问用户已经明确说过的信息",
            "选项必须贴合品类和当前需求",
            "优先追问会影响推荐结果的问题",
        ],
    }
    parsed, meta = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        temperature=0.2,
    )
    if parsed is None:
        return fallback, _prompt_meta({**meta, "used": False})

    questions = _normalize_questions(parsed.get("questions"), fallback)
    if not questions:
        return fallback, _prompt_meta({**meta, "used": False, "reason": "agentic_questions_empty"})
    return questions, _prompt_meta({**meta, "used": True})


def normalize_human_feedback_with_agent(
    feedback: str,
    current_intent: dict[str, Any],
    profile: CategoryProfile,
    client: LLMClient,
    enabled: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not feedback.strip():
        return {}, _prompt_meta({"used": False, "reason": "human_feedback_empty"})

    rule_overrides = parse_human_feedback(feedback, current_intent, profile)
    if not enabled:
        return rule_overrides, _prompt_meta({"used": False, "reason": "agentic_normalizer_disabled"})

    payload = {
        "task": "normalize_human_feedback",
        "feedback": feedback,
        "current_intent": current_intent,
        "category_profile": _profile_payload(profile),
        "rule_based_overrides": rule_overrides,
        "required_output_schema": {
            "intent_overrides": {
                "budget_max": "number|null",
                "scenarios": ["string"],
                "must_dimensions": ["dimension_name"],
                "exclude_specs": {"spec_name": ["banned_value"]},
                "soft_preferences": ["string"],
                "mentioned_products": ["string"],
                "preference_weights": {
                    "budget": "0-3 number",
                    "scenario": "0-3 number",
                    "dimension": "0-3 number",
                    "evidence": "0-3 number",
                },
            }
        },
        "rules": [
            "只归一化用户反馈，不要创造商品事实",
            "用户明确说不要的内容必须进入 exclude_specs",
            "用户更看重口碑/评价/踩坑时提高 evidence 权重",
            "用户更看重参数/体验维度时提高 dimension 权重",
        ],
    }
    parsed, meta = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        temperature=0.0,
    )
    if parsed is None:
        return rule_overrides, _prompt_meta({**meta, "used": False})

    agent_overrides = _normalize_intent_overrides(
        parsed.get("intent_overrides", parsed),
        current_intent,
        profile,
    )
    merged = _merge_feedback_overrides(
        current_intent=current_intent,
        rule_overrides=rule_overrides,
        agent_overrides=agent_overrides,
        feedback=feedback,
    )
    return merged, _prompt_meta({**meta, "used": True})


def plan_agent_workflow(
    query: str,
    intent: dict[str, Any],
    profile: CategoryProfile,
    client: LLMClient,
    enabled: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback = _fallback_tool_plan(query, intent, profile)
    if not enabled:
        return fallback, _prompt_meta({"used": False, "reason": "agentic_planner_disabled"})

    payload = {
        "task": "plan_agent_tool_workflow",
        "query": query,
        "intent": intent,
        "category_profile": _profile_payload(profile),
        "available_tools": [
            "product_search",
            "constraint_filter",
            "review_vector_retrieval",
            "rank_candidates",
            "compare_products",
            "recommendation_explainer",
            "self_check",
        ],
        "required_output_schema": {
            "tool_sequence": ["tool_name"],
            "search_top_k": "integer 5-30",
            "need_comparison": "boolean",
            "review_plan": {
                "aspects": ["dimension_name"],
                "queries": ["short evidence query"],
                "top_k": "integer 1-5",
            },
            "ranking_focus": ["budget|scenario|dimension|evidence"],
            "recommendation_style": "short style instruction",
        },
        "rules": [
            "明确多商品对比或用户问哪个更适合时 need_comparison=true",
            "用户强调踩坑/真实评价时，review_plan queries 要覆盖负面证据",
            "不要跳过 constraint_filter 和 self_check",
            "search_top_k 不超过 30",
        ],
    }
    parsed, meta = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        temperature=0.1,
    )
    if parsed is None:
        return fallback, _prompt_meta({**meta, "used": False})

    plan = _normalize_tool_plan(parsed, fallback, profile)
    return plan, _prompt_meta({**meta, "used": True})


def explain_recommendations_with_agent(
    recommendations: list[dict[str, Any]],
    intent: dict[str, Any],
    purchase_brief: dict[str, Any],
    agent_plan: dict[str, Any],
    client: LLMClient,
    enabled: bool,
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    if not recommendations:
        return recommendations, None, _prompt_meta({"used": False, "reason": "no_recommendations"})
    if not enabled:
        return recommendations, None, _prompt_meta({"used": False, "reason": "agentic_explainer_disabled"})

    payload = {
        "task": "explain_recommendations",
        "intent": intent,
        "purchase_brief": _compact_brief(purchase_brief),
        "agent_plan": agent_plan,
        "recommendations": [_compact_recommendation(item) for item in recommendations],
        "required_output_schema": {
            "answer_summary": "one short user-facing paragraph",
            "items": [
                {
                    "product_id": "string",
                    "reasons": ["specific reason grounded in specs or evidence"],
                    "risks": ["specific risk grounded in evidence"],
                }
            ],
        },
        "rules": [
            "每条理由必须基于商品参数、价格、场景标签或评论证据",
            "不要编造没有出现在输入里的商品事实",
            "风险为空时返回空数组，不要硬编风险",
            "语言像真实导购，简洁具体",
        ],
    }
    parsed, meta = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        temperature=0.2,
    )
    if parsed is None:
        return recommendations, None, _prompt_meta({**meta, "used": False})

    explained = _apply_explanations(recommendations, parsed.get("items", []))
    summary = parsed.get("answer_summary") if isinstance(parsed.get("answer_summary"), str) else None
    return explained, summary, _prompt_meta({**meta, "used": True})


def _profile_payload(profile: CategoryProfile) -> dict[str, Any]:
    return {
        "category_id": profile.category_id,
        "display_name": profile.display_name,
        "aliases": profile.aliases,
        "decision_dimensions": [
            {
                "name": dimension.name,
                "label": dimension.label,
                "keywords": dimension.keywords,
            }
            for dimension in profile.decision_dimensions
        ],
        "required_specs": profile.required_specs,
        "scenario_names": list(profile.scenario_weights.keys()),
        "common_risks": profile.common_risks,
    }


def _prompt_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        **meta,
        "prompt_key": SYSTEM_PROMPT_TEMPLATE.key,
        "prompt_version": SYSTEM_PROMPT_TEMPLATE.version,
    }


def _normalize_questions(
    raw_questions: Any,
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_questions, list):
        return fallback

    normalized: list[dict[str, Any]] = []
    for index, question in enumerate(raw_questions[:4], start=1):
        if not isinstance(question, dict):
            continue
        title = _clean_text(question.get("title"), default=f"需求确认 {index}")
        text = _clean_text(question.get("question"), default="")
        if not text:
            continue
        options = _clean_list(question.get("options"))[:8]
        input_type = question.get("input_type")
        if input_type not in {"single_choice", "multi_choice"}:
            input_type = "multi_choice" if options else "text"
        normalized.append(
            {
                "id": _clean_id(question.get("id"), f"agent_q{index}"),
                "title": title,
                "question": text,
                "input_type": input_type,
                "options": options,
                "allow_custom": bool(question.get("allow_custom", True)),
                "source": "agent",
            }
        )
    return normalized or fallback


def _normalize_intent_overrides(
    raw: Any,
    current_intent: dict[str, Any],
    profile: CategoryProfile,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    allowed_dimensions = set(profile.dimension_names)
    overrides: dict[str, Any] = {}

    budget = raw.get("budget_max")
    if isinstance(budget, (int, float)):
        overrides["budget_max"] = float(budget)

    for key in ["scenarios", "soft_preferences", "mentioned_products"]:
        values = _clean_list(raw.get(key))
        if values:
            overrides[key] = values

    dimensions = [
        item for item in _clean_list(raw.get("must_dimensions"))
        if item in allowed_dimensions
    ]
    if dimensions:
        overrides["must_dimensions"] = dimensions

    exclude_specs = _clean_exclude_specs(raw.get("exclude_specs"))
    if exclude_specs:
        overrides["exclude_specs"] = exclude_specs

    weights = _clean_weights(raw.get("preference_weights"))
    if weights:
        overrides["preference_weights"] = weights

    overrides["category"] = current_intent.get("category")
    overrides["category_display_name"] = current_intent.get("category_display_name")
    return overrides


def _merge_feedback_overrides(
    current_intent: dict[str, Any],
    rule_overrides: dict[str, Any],
    agent_overrides: dict[str, Any],
    feedback: str,
) -> dict[str, Any]:
    merged = deepcopy(current_intent)

    budget_candidates = [
        rule_overrides.get("budget_max"),
        agent_overrides.get("budget_max"),
        current_intent.get("budget_max"),
    ]
    merged["budget_max"] = next(
        (value for value in budget_candidates if isinstance(value, (int, float))),
        current_intent.get("budget_max"),
    )

    for key in ["scenarios", "must_dimensions", "soft_preferences", "mentioned_products"]:
        merged[key] = _merge_unique(
            current_intent.get(key, []),
            agent_overrides.get(key, []),
            rule_overrides.get(key, []),
        )

    merged["exclude_specs"] = _merge_exclude_specs(
        current_intent.get("exclude_specs", {}),
        agent_overrides.get("exclude_specs", {}),
        rule_overrides.get("exclude_specs", {}),
    )
    merged["preference_weights"] = _merge_weights(
        current_intent.get("preference_weights", {}),
        agent_overrides.get("preference_weights", {}),
        rule_overrides.get("preference_weights", {}),
    )
    merged["human_feedback"] = feedback.strip()
    merged["need_clarification"] = False
    return merged


def _fallback_tool_plan(
    query: str,
    intent: dict[str, Any],
    profile: CategoryProfile,
) -> dict[str, Any]:
    aspects = list(intent.get("must_dimensions", [])) or profile.dimension_names[:4]
    query_parts = [
        query,
        *intent.get("scenarios", []),
        *intent.get("soft_preferences", []),
        *aspects,
    ]
    needs_comparison = (
        intent.get("task_type") == "comparison"
        or len(intent.get("mentioned_products", [])) >= 2
    )
    return {
        "tool_sequence": [
            "product_search",
            "constraint_filter",
            "review_vector_retrieval",
            "rank_candidates",
            "compare_products" if needs_comparison else "recommendation_explainer",
            "self_check",
        ],
        "search_top_k": 20,
        "need_comparison": needs_comparison,
        "review_plan": {
            "aspects": aspects[:6],
            "queries": [" ".join(str(item) for item in query_parts if item)],
            "top_k": 3,
        },
        "ranking_focus": ["budget", "scenario", "dimension", "evidence"],
        "recommendation_style": "简洁、可解释、引用评论证据",
        "source": "fallback",
    }


def _normalize_tool_plan(
    raw: dict[str, Any],
    fallback: dict[str, Any],
    profile: CategoryProfile,
) -> dict[str, Any]:
    allowed_tools = {
        "product_search",
        "constraint_filter",
        "review_vector_retrieval",
        "rank_candidates",
        "compare_products",
        "recommendation_explainer",
        "self_check",
    }
    plan = deepcopy(fallback)
    tools = [item for item in _clean_list(raw.get("tool_sequence")) if item in allowed_tools]
    if tools:
        for required in ["constraint_filter", "self_check"]:
            if required not in tools:
                tools.append(required)
        plan["tool_sequence"] = tools

    search_top_k = raw.get("search_top_k")
    if isinstance(search_top_k, int):
        plan["search_top_k"] = max(5, min(search_top_k, 30))

    if isinstance(raw.get("need_comparison"), bool):
        plan["need_comparison"] = raw["need_comparison"]

    review_plan = raw.get("review_plan")
    if isinstance(review_plan, dict):
        allowed_dimensions = set(profile.dimension_names)
        aspects = [item for item in _clean_list(review_plan.get("aspects")) if item in allowed_dimensions]
        queries = _clean_list(review_plan.get("queries"))[:5]
        top_k = review_plan.get("top_k")
        plan["review_plan"] = {
            "aspects": aspects or plan["review_plan"]["aspects"],
            "queries": queries or plan["review_plan"]["queries"],
            "top_k": max(1, min(top_k, 5)) if isinstance(top_k, int) else plan["review_plan"]["top_k"],
        }

    ranking_focus = [
        item
        for item in _clean_list(raw.get("ranking_focus"))
        if item in {"budget", "scenario", "dimension", "evidence"}
    ]
    if ranking_focus:
        plan["ranking_focus"] = ranking_focus

    style = _clean_text(raw.get("recommendation_style"), default="")
    if style:
        plan["recommendation_style"] = style
    plan["source"] = "agent"
    return plan


def _compact_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": brief.get("category"),
        "budget_max": brief.get("budget_max"),
        "scenarios": brief.get("scenarios", []),
        "must_dimensions": brief.get("must_dimensions", []),
        "soft_preferences": brief.get("soft_preferences", []),
        "human_feedback": brief.get("human_feedback"),
    }


def _compact_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": item.get("product_id"),
        "title": item.get("title"),
        "brand": item.get("brand"),
        "price": item.get("price"),
        "specs": item.get("specs", {}),
        "tags": item.get("tags", []),
        "score_breakdown": item.get("score_breakdown", {}),
        "rule_reasons": item.get("reasons", []),
        "rule_risks": item.get("risks", []),
        "evidence": [
            {
                "rating": evidence.get("rating"),
                "content": evidence.get("content"),
                "matched_aspects": evidence.get("matched_aspects", {}),
            }
            for evidence in item.get("evidence", [])[:3]
        ],
    }


def _apply_explanations(
    recommendations: list[dict[str, Any]],
    raw_items: Any,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return recommendations
    by_id = {
        item.get("product_id"): item
        for item in raw_items
        if isinstance(item, dict) and isinstance(item.get("product_id"), str)
    }
    explained: list[dict[str, Any]] = []
    for item in recommendations:
        updated = dict(item)
        raw = by_id.get(item.get("product_id"), {})
        reasons = _clean_list(raw.get("reasons"))
        risks = _clean_list(raw.get("risks"))
        if reasons:
            updated["reasons"] = reasons[:5]
            updated["explanation_source"] = "agent"
        if risks:
            updated["risks"] = risks[:3]
        explained.append(updated)
    return explained


def _clean_text(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    text = value.strip()
    return text or default


def _clean_id(value: Any, default: str) -> str:
    text = _clean_text(value, default)
    return "".join(char for char in text if char.isalnum() or char in {"_", "-"})[:32] or default


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text and text not in cleaned:
                cleaned.append(text)
    return cleaned


def _clean_exclude_specs(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, items in value.items():
        if isinstance(key, str):
            values = _clean_list(items)
            if values:
                cleaned[key] = values
    return cleaned


def _clean_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, float] = {}
    for key in ["budget", "scenario", "dimension", "evidence"]:
        raw = value.get(key)
        if isinstance(raw, (int, float)):
            cleaned[key] = max(0.0, min(float(raw), 3.0))
    return cleaned


def _merge_unique(*lists: list[str]) -> list[str]:
    merged: list[str] = []
    for values in lists:
        for item in values or []:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
    return merged


def _merge_exclude_specs(*specs: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for spec in specs:
        for key, values in (spec or {}).items():
            merged[key] = _merge_unique(merged.get(key, []), values)
    return merged


def _merge_weights(*weights_list: dict[str, Any]) -> dict[str, float]:
    merged = {
        "budget": 1.0,
        "scenario": 1.0,
        "dimension": 1.0,
        "evidence": 1.0,
    }
    for weights in weights_list:
        for key in merged:
            value = (weights or {}).get(key)
            if isinstance(value, (int, float)):
                merged[key] = max(merged[key], max(0.0, min(float(value), 3.0)))
    return merged
