from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.agents.agentic_planner import (
    build_agentic_questions,
    explain_recommendations_with_agent,
    normalize_human_feedback_with_agent,
    plan_agent_workflow,
)
from backend.agents.human_feedback import merge_overrides
from backend.agents.intent_parser import parse_user_intent
from backend.agents.langgraph_adapter import END, START, StateGraph
from backend.agents.purchase_brief import build_purchase_brief
from backend.agents.state import CommerceAgentState
from backend.data_loader import (
    DEFAULT_DATA_DIR,
    load_category_profiles,
    load_products,
    load_reviews,
)
from backend.llm.client import LLMClient
from backend.llm.intent_parser import parse_intent_with_llm
from backend.memory.user_memory import InMemoryUserMemory
from backend.models import CategoryProfile, Product, TraceStep
from backend.retrieval.category_retriever import CategoryRetriever
from backend.retrieval.review_vector_store import ReviewVectorStore
from backend.tools.compare_products import compare_products
from backend.tools.filter_constraints import filter_by_constraints
from backend.tools.generate_recommendation import generate_recommendation
from backend.tools.rank_candidates import rank_candidates
from backend.tools.retrieve_reviews import retrieve_product_reviews
from backend.tools.search_products import search_products
from backend.tools.self_check import self_check_recommendations
from backend.tools.update_user_memory import update_user_memory


class CommerceAgentGraph:
    """LangGraph-based orchestration for the shopping decision workflow."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.profiles = load_category_profiles(self.data_dir)
        self.products = load_products(self.data_dir)
        self.reviews = load_reviews(self.data_dir)
        self.category_retriever = CategoryRetriever(self.profiles)
        self.review_vector_store = ReviewVectorStore.from_reviews(
            self.reviews,
            db_path=Path(__file__).resolve().parents[2] / ".cache" / "review_vectors.sqlite",
        )
        self.llm_client = LLMClient()
        self.memory = InMemoryUserMemory()
        self.graph = self._build_graph()

    def invoke(self, state: CommerceAgentState) -> CommerceAgentState:
        return self.graph.invoke(state)

    def list_categories(self) -> list[dict[str, str]]:
        return self.category_retriever.list_categories()

    def _build_graph(self):
        graph = StateGraph(CommerceAgentState)
        graph.add_node("intent_parser", self._intent_parser)
        graph.add_node("clarification", self._clarification)
        graph.add_node("purchase_brief", self._purchase_brief)
        graph.add_node("await_user_confirmation", self._await_user_confirmation)
        graph.add_node("product_search", self._product_search)
        graph.add_node("constraint_filter", self._constraint_filter)
        graph.add_node("review_evidence", self._review_evidence)
        graph.add_node("rank_candidates", self._rank_candidates)
        graph.add_node("comparison", self._comparison)
        graph.add_node("recommendation", self._recommendation)
        graph.add_node("self_check", self._self_check)
        graph.add_node("memory_update", self._memory_update)
        graph.add_node("finalize", self._finalize)

        graph.add_edge(START, "intent_parser")
        graph.add_conditional_edges(
            "intent_parser",
            self._route_after_intent,
            {"clarify": "clarification", "continue": "purchase_brief"},
        )
        graph.add_edge("clarification", END)
        graph.add_conditional_edges(
            "purchase_brief",
            self._route_after_purchase_brief,
            {
                "await_confirmation": "await_user_confirmation",
                "continue": "product_search",
            },
        )
        graph.add_edge("await_user_confirmation", END)
        graph.add_edge("product_search", "constraint_filter")
        graph.add_edge("constraint_filter", "review_evidence")
        graph.add_edge("review_evidence", "rank_candidates")
        graph.add_conditional_edges(
            "rank_candidates",
            self._route_after_ranking,
            {"compare": "comparison", "recommend": "recommendation"},
        )
        graph.add_edge("comparison", "recommendation")
        graph.add_edge("recommendation", "self_check")
        graph.add_edge("self_check", "memory_update")
        graph.add_edge("memory_update", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _intent_parser(self, state: CommerceAgentState) -> CommerceAgentState:
        query = state["query"]
        profile, category_scores = self.category_retriever.detect(query)
        intent = parse_user_intent(query, profile, category_scores)
        llm_meta = {"enabled": bool(state.get("use_llm", False)), "used": False}
        if state.get("use_llm", False):
            llm_intent, llm_call_meta = parse_intent_with_llm(
                query=query,
                profiles=self.profiles,
                category_scores=category_scores,
                fallback_intent=intent,
                client=self.llm_client,
            )
            llm_meta.update(llm_call_meta)
            if llm_intent is not None:
                intent = llm_intent
                llm_meta["used"] = True
                profile = _find_profile(self.profiles, intent.get("category"))

        return _with_trace(
            state,
            {
                "profile": profile,
                "category_scores": category_scores,
                "intent": intent,
                "llm_meta": llm_meta,
                "workflow_status": "intent_parsed",
            },
            name="Intent Parser",
            reason="识别品类、预算、场景、硬约束和软偏好",
            inputs={"query": query, "use_llm": state.get("use_llm", False)},
            outputs={"intent": intent, "llm_meta": llm_meta},
        )

    def _route_after_intent(self, state: CommerceAgentState) -> str:
        if state["intent"].get("need_clarification"):
            return "clarify"
        return "continue"

    def _clarification(self, state: CommerceAgentState) -> CommerceAgentState:
        categories = "、".join(
            item["display_name"] for item in self.category_retriever.list_categories()
        )
        answer = f"我还不能确定你想买的品类。可以先告诉我是以下哪类吗：{categories}？"
        return _with_trace(
            state,
            {
                "answer": answer,
                "recommendations": [],
                "self_check": {"passed": False, "issues": ["category_unclear"]},
                "memory_update": {},
                "workflow_status": "needs_clarification",
            },
            name="Clarification",
            reason="无法稳定识别商品品类，需要先追问",
            inputs={"query": state["query"]},
            outputs={"question": answer},
        )

    def _purchase_brief(self, state: CommerceAgentState) -> CommerceAgentState:
        profile = _require_profile(state)
        user_memory = self.memory.get(state.get("user_id", "demo-user"))
        agentic_enabled = _agentic_llm_enabled(state)
        feedback_overrides, feedback_meta = normalize_human_feedback_with_agent(
            feedback=state.get("human_feedback") or "",
            current_intent=state["intent"],
            profile=profile,
            client=self.llm_client,
            enabled=agentic_enabled,
        )
        merged_overrides = merge_overrides(
            state.get("brief_overrides"),
            feedback_overrides,
        )
        draft_brief, updated_intent = build_purchase_brief(
            query=state["query"],
            intent=state["intent"],
            profile=profile,
            user_memory=user_memory,
            brief_overrides=merged_overrides,
            require_confirmation=state.get("require_confirmation", False),
        )
        questions, question_meta = build_agentic_questions(
            query=state["query"],
            intent=updated_intent,
            profile=profile,
            user_memory=user_memory,
            client=self.llm_client,
            enabled=agentic_enabled,
        )
        brief, updated_intent = build_purchase_brief(
            query=state["query"],
            intent=state["intent"],
            profile=profile,
            user_memory=user_memory,
            brief_overrides=merged_overrides,
            require_confirmation=state.get("require_confirmation", False),
            confirmation_questions=questions,
        )
        agent_plan, plan_meta = plan_agent_workflow(
            query=state["query"],
            intent=updated_intent,
            profile=profile,
            client=self.llm_client,
            enabled=agentic_enabled,
        )
        brief["agent_plan"] = agent_plan
        llm_meta = _merge_agentic_meta(
            state.get("llm_meta", {}),
            {
                "feedback_normalization": feedback_meta,
                "question_generation": question_meta,
                "tool_planning": plan_meta,
            },
        )
        return _with_trace(
            state,
            {
                "purchase_brief": brief,
                "intent": updated_intent,
                "agent_plan": agent_plan,
                "llm_meta": llm_meta,
                "workflow_status": brief["status"],
            },
            name="Purchase Brief",
            reason="让 Agent 归一化反馈、生成追问并规划后续工具路径",
            inputs={
                "intent": state["intent"],
                "require_confirmation": state.get("require_confirmation", False),
                "brief_overrides": merged_overrides,
                "human_feedback": state.get("human_feedback"),
                "agentic_enabled": agentic_enabled,
            },
            outputs={
                "purchase_brief": draft_brief | {"confirmation_questions": questions},
                "agent_plan": agent_plan,
            },
        )

    def _route_after_purchase_brief(self, state: CommerceAgentState) -> str:
        if state["purchase_brief"]["status"] == "awaiting_user_confirmation":
            return "await_confirmation"
        return "continue"

    def _await_user_confirmation(self, state: CommerceAgentState) -> CommerceAgentState:
        brief = state["purchase_brief"]
        questions = [
            item.get("question", "")
            for item in brief.get("confirmation_questions", [])
            if item.get("question")
        ]
        prompts = (
            questions
            or brief.get("confirmation_prompts")
            or ["请补充你的使用场景、优先级或不能接受的商品特点。"]
        )
        answer = "我先整理了一张购物任务卡，请确认后再继续推荐：\n" + "\n".join(
            f"- {prompt}" for prompt in prompts
        )
        return _with_trace(
            state,
            {
                "answer": answer,
                "recommendations": [],
                "self_check": {"passed": False, "issues": ["awaiting_user_confirmation"]},
                "memory_update": {},
                "workflow_status": "awaiting_user_confirmation",
            },
            name="Human-in-loop Checkpoint",
            reason="在真正检索和排序前暂停，让用户确认或修正购物任务卡",
            inputs={"purchase_brief": brief},
            outputs={"answer": answer},
        )

    def _product_search(self, state: CommerceAgentState) -> CommerceAgentState:
        intent = state["intent"]
        search_top_k = _search_top_k(state.get("agent_plan", {}))
        candidates = search_products(
            products=self.products,
            query=state["query"],
            category=intent["category"],
            top_k=search_top_k,
        )
        banned_product_ids = set(intent.get("banned_product_ids", []))
        if banned_product_ids:
            candidates = [
                product for product in candidates if product.product_id not in banned_product_ids
            ]
        return _with_trace(
            state,
            {"candidates": candidates, "workflow_status": "products_retrieved"},
            name="Product Search",
            reason="根据识别出的品类和 query 召回候选商品",
            inputs={"category": intent["category"], "top_k": search_top_k},
            outputs={"candidate_products": _summarize_products(candidates)},
        )

    def _constraint_filter(self, state: CommerceAgentState) -> CommerceAgentState:
        filtered, rejected = filter_by_constraints(
            state.get("candidates", []),
            state["intent"],
        )
        return _with_trace(
            state,
            {
                "filtered_products": filtered,
                "rejected_products": rejected,
                "workflow_status": "constraints_filtered",
            },
            name="Constraint Filter",
            reason="用确定性代码处理预算、排除项和必要参数",
            inputs={"constraints": state["intent"]},
            outputs={"kept": _summarize_products(filtered), "rejected": rejected},
        )

    def _review_evidence(self, state: CommerceAgentState) -> CommerceAgentState:
        profile = _require_profile(state)
        review_plan = state.get("agent_plan", {}).get("review_plan", {})
        aspects = _review_aspects(
            state["intent"],
            profile.dimension_names,
            review_plan.get("aspects", []),
        )
        review_query = _review_query(state["query"], review_plan)
        review_top_k = _review_top_k(review_plan)
        evidence_by_product = {
            product.product_id: retrieve_product_reviews(
                reviews=self.reviews,
                product_id=product.product_id,
                aspects=aspects,
                top_k=review_top_k,
                query=review_query,
                vector_store=self.review_vector_store,
            )
            for product in state.get("filtered_products", [])
        }
        return _with_trace(
            state,
            {
                "review_aspects": aspects,
                "evidence_by_product": evidence_by_product,
                "workflow_status": "evidence_retrieved",
            },
            name="Review Evidence Retrieval",
            reason="围绕用户关注维度检索评论证据",
            inputs={
                "aspects": aspects,
                "queries": review_plan.get("queries", []),
                "query": review_query,
                "retrieval_source": "sqlite_vector_store",
            },
            outputs={"evidence_by_product": evidence_by_product},
        )

    def _rank_candidates(self, state: CommerceAgentState) -> CommerceAgentState:
        ranked = rank_candidates(
            products=state.get("filtered_products", []),
            constraints=state["intent"],
            evidence_by_product=state.get("evidence_by_product", {}),
            profile=state.get("profile"),
        )
        ranked = _apply_pinned_products(
            ranked,
            state["intent"].get("pinned_product_ids", []),
        )
        ranked_summary = [
            {
                "product_id": item["product"].product_id,
                "title": item["product"].title,
                "score": item["score"],
                "score_breakdown": item["score_breakdown"],
            }
            for item in ranked
        ]
        return _with_trace(
            state,
            {
                "ranked_candidates": ranked,
                "workflow_status": "candidates_ranked",
            },
            name="Rank Candidates",
            reason="结合约束满足度、场景匹配、参数和评论证据排序",
            inputs={"candidate_count": len(state.get("filtered_products", []))},
            outputs={"ranked": ranked_summary},
        )

    def _route_after_ranking(self, state: CommerceAgentState) -> str:
        agent_plan = state.get("agent_plan", {})
        if agent_plan.get("need_comparison") or state["intent"].get("task_type") == "comparison":
            return "compare"
        return "recommend"

    def _comparison(self, state: CommerceAgentState) -> CommerceAgentState:
        profile = _require_profile(state)
        dimensions = _comparison_dimensions(state["intent"], profile)
        ranked_products = [
            item["product"] for item in state.get("ranked_candidates", [])
        ]
        table = compare_products(ranked_products[:5], dimensions)
        return _with_trace(
            state,
            {
                "comparison_table": table,
                "workflow_status": "comparison_ready",
            },
            name="Comparison",
            reason="针对多商品选择任务生成结构化对比表",
            inputs={"dimensions": dimensions},
            outputs={"comparison_table": table},
        )

    def _recommendation(self, state: CommerceAgentState) -> CommerceAgentState:
        recommendations = generate_recommendation(
            ranked_candidates=state.get("ranked_candidates", []),
            evidence_by_product=state.get("evidence_by_product", {}),
            constraints=state["intent"],
            top_n=3,
        )
        recommendations, answer_summary, explanation_meta = explain_recommendations_with_agent(
            recommendations=recommendations,
            intent=state["intent"],
            purchase_brief=state.get("purchase_brief", {}),
            agent_plan=state.get("agent_plan", {}),
            client=self.llm_client,
            enabled=_agentic_llm_enabled(state),
        )
        llm_meta = _merge_agentic_meta(
            state.get("llm_meta", {}),
            {"recommendation_explanation": explanation_meta},
        )
        return _with_trace(
            state,
            {
                "recommendations": recommendations,
                "agent_answer_summary": answer_summary,
                "llm_meta": llm_meta,
                "workflow_status": "recommendations_generated",
            },
            name="Recommendation",
            reason="用排序结果和评论证据生成可解释推荐，必要时由 Agent 组织导购话术",
            inputs={"top_n": 3, "agent_plan": state.get("agent_plan", {})},
            outputs={"recommendations": recommendations, "answer_summary": answer_summary},
        )

    def _self_check(self, state: CommerceAgentState) -> CommerceAgentState:
        self_check = self_check_recommendations(
            state.get("recommendations", []),
            state["intent"],
        )
        return _with_trace(
            state,
            {
                "self_check": self_check,
                "workflow_status": "self_checked",
            },
            name="Self Check",
            reason="检查推荐是否违反硬约束，以及是否包含评论证据",
            inputs={"constraints": state["intent"]},
            outputs=self_check,
        )

    def _memory_update(self, state: CommerceAgentState) -> CommerceAgentState:
        user_id = state.get("user_id", "demo-user")
        memory_update = update_user_memory(
            memory=self.memory.snapshot(),
            user_id=user_id,
            intent=state["intent"],
        )
        return _with_trace(
            state,
            {
                "memory_update": memory_update,
                "workflow_status": "memory_updated",
            },
            name="Memory Update",
            reason="记录用户最近关注的品类、预算、场景和偏好",
            inputs={"user_id": user_id},
            outputs={"memory": memory_update},
        )

    def _finalize(self, state: CommerceAgentState) -> CommerceAgentState:
        answer = _format_answer(
            state.get("recommendations", []),
            state.get("self_check", {}),
            state.get("comparison_table", []),
            state.get("agent_answer_summary"),
        )
        return {
            "answer": answer,
            "workflow_status": "completed",
        }


def _with_trace(
    state: CommerceAgentState,
    updates: CommerceAgentState,
    name: str,
    reason: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> CommerceAgentState:
    trace = list(state.get("trace", []))
    trace.append(
        TraceStep(
            name=name,
            reason=reason,
            inputs=inputs,
            outputs=outputs,
        )
    )
    result = dict(updates)
    result["trace"] = trace
    return result


def _require_profile(state: CommerceAgentState) -> CategoryProfile:
    profile = state.get("profile")
    if profile is None:
        raise ValueError("Category profile is required after intent parsing.")
    return profile


def _find_profile(
    profiles: list[CategoryProfile],
    category_id: str | None,
) -> CategoryProfile | None:
    for profile in profiles:
        if profile.category_id == category_id:
            return profile
    return None


def _agentic_llm_enabled(state: CommerceAgentState) -> bool:
    llm_meta = state.get("llm_meta", {})
    return bool(state.get("use_llm", False) and llm_meta.get("used", False))


def _merge_agentic_meta(
    llm_meta: dict[str, Any],
    updates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    merged = dict(llm_meta or {})
    agentic = dict(merged.get("agentic", {}))
    agentic.update(updates)
    merged["agentic"] = agentic
    return merged


def _search_top_k(agent_plan: dict[str, Any]) -> int:
    value = agent_plan.get("search_top_k")
    return max(5, min(value, 30)) if isinstance(value, int) else 20


def _review_aspects(
    intent: dict[str, Any],
    fallback_dimensions: list[str],
    planned_aspects: list[str] | None = None,
) -> list[str]:
    aspects = [
        aspect
        for aspect in (planned_aspects or [])
        if aspect in fallback_dimensions
    ]
    if not aspects:
        aspects = list(intent.get("must_dimensions", []))
    if not aspects:
        aspects = list(fallback_dimensions[:4])
    return aspects


def _review_query(default_query: str, review_plan: dict[str, Any]) -> str:
    queries = [
        item
        for item in review_plan.get("queries", [])
        if isinstance(item, str) and item.strip()
    ]
    return " ".join(queries) if queries else default_query


def _review_top_k(review_plan: dict[str, Any]) -> int:
    value = review_plan.get("top_k")
    return max(1, min(value, 5)) if isinstance(value, int) else 3


def _comparison_dimensions(
    intent: dict[str, Any],
    profile: CategoryProfile,
) -> list[str]:
    dimensions = list(intent.get("must_dimensions", []))
    for name in profile.dimension_names:
        if name not in dimensions:
            dimensions.append(name)
    return dimensions[:6]


def _apply_pinned_products(
    ranked: list[dict[str, Any]],
    pinned_product_ids: list[str],
) -> list[dict[str, Any]]:
    if not pinned_product_ids:
        return ranked
    pinned = set(pinned_product_ids)
    return sorted(
        ranked,
        key=lambda item: (
            0 if item["product"].product_id in pinned else 1,
            -item["score"],
            item["product"].price,
        ),
    )


def _summarize_products(products: list[Product]) -> list[dict[str, Any]]:
    return [
        {
            "product_id": product.product_id,
            "title": product.title,
            "price": product.price,
            "brand": product.brand,
        }
        for product in products
    ]


def _format_answer(
    recommendations: list[dict[str, Any]],
    self_check: dict[str, Any],
    comparison_table: list[dict[str, Any]] | None = None,
    agent_answer_summary: str | None = None,
) -> str:
    if not recommendations:
        return "没有找到满足硬约束的商品，建议放宽预算或减少排除条件。"

    lines = []
    if agent_answer_summary:
        lines.append(agent_answer_summary)
    if comparison_table:
        lines.append("我先按你的使用目标整理了对比表，再给出推荐排序。")
    if not agent_answer_summary:
        lines.append("基于你的约束，我建议优先看：")
    for index, item in enumerate(recommendations, start=1):
        reason = item["reasons"][0] if item.get("reasons") else "综合排序靠前"
        lines.append(
            f"{index}. {item['title']}（{item['price']:.0f} 元）：{reason}"
        )
        if item.get("risks"):
            lines.append(f"   风险提示：{item['risks'][0]}")

    if not self_check.get("passed"):
        lines.append("注意：自检发现部分推荐可能缺少证据或违反约束，请查看 trace。")
    return "\n".join(lines)
