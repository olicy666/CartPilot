from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.agents.graph import _comparison_dimensions, _review_aspects
from backend.agents.workflow import CommerceAgent
from backend.models import Product, to_plain_dict
from backend.tools.compare_products import compare_products
from backend.tools.filter_constraints import filter_by_constraints
from backend.tools.retrieve_reviews import retrieve_product_reviews


EVENT_STAGE_MAP = {
    "search_submitted": "exploring",
    "filter_changed": "shortlisting",
    "product_viewed": "product_viewing",
    "review_section_opened": "product_viewing",
    "compare_added": "comparing",
    "cart_added": "cart_checking",
    "cart_removed": "cart_checking",
    "checkout_started": "checkout",
    "assistant_question_answered": "shortlisting",
}


class SQLiteShoppingSessionStore:
    """Persist shopping events and derived copilot state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def load_state(self, session_id: str) -> dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT state_json FROM shopping_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return _initial_state(session_id)
        try:
            state = json.loads(row[0])
        except json.JSONDecodeError:
            return _initial_state(session_id)
        return state if isinstance(state, dict) else _initial_state(session_id)

    def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO shopping_sessions (session_id, state_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, json.dumps(state, ensure_ascii=False)),
            )
            conn.commit()

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO shopping_events (session_id, event_json, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (session_id, json.dumps(event, ensure_ascii=False)),
            )
            conn.commit()

    def recent_events(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT event_json FROM shopping_events
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        events = []
        for row in rows:
            try:
                events.append(json.loads(row[0]))
            except json.JSONDecodeError:
                continue
        return list(reversed(events))

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shopping_sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shopping_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shopping_events_session ON shopping_events(session_id, id)"
            )
            conn.commit()


class ShoppingCopilot:
    """Event-driven side assistant for the shopping journey."""

    def __init__(
        self,
        agent: CommerceAgent | None = None,
        cache_dir: Path | None = None,
    ):
        self.agent = agent or CommerceAgent()
        base_cache = cache_dir or Path(__file__).resolve().parents[2] / ".cache"
        self.store = SQLiteShoppingSessionStore(base_cache / "shopping_copilot.sqlite")

    def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_event(event)
        session_id = normalized["session_id"]
        state = self.store.load_state(session_id)
        self.store.append_event(session_id, normalized)

        event_type = normalized["event_type"]
        payload = normalized["payload"]
        state["user_id"] = normalized["user_id"]
        state["stage"] = EVENT_STAGE_MAP.get(event_type, state.get("stage", "exploring"))
        state["last_event_type"] = event_type

        if event_type == "search_submitted":
            response = self._handle_search(state, payload)
        elif event_type == "assistant_question_answered":
            response = self._handle_feedback(state, payload)
        elif event_type == "product_viewed":
            response = self._handle_product_viewed(state, payload)
        elif event_type == "review_section_opened":
            response = self._handle_review_opened(state, payload)
        elif event_type == "compare_added":
            response = self._handle_compare_added(state, payload)
        elif event_type == "cart_added":
            response = self._handle_cart_added(state, payload)
        elif event_type == "cart_removed":
            response = self._handle_cart_removed(state, payload)
        elif event_type == "checkout_started":
            response = self._handle_checkout(state)
        else:
            response = self._passive_update(state, payload)

        state["last_assistant_message"] = response["assistant_message"]
        state["assistant_cards"] = response.get("assistant_cards", [])
        self.store.save_state(session_id, state)
        response["state"] = state
        response["recent_events"] = self.store.recent_events(session_id, limit=8)
        return response

    def get_state(self, session_id: str) -> dict[str, Any]:
        state = self.store.load_state(session_id)
        state["recent_events"] = self.store.recent_events(session_id, limit=20)
        return state

    def _handle_search(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        state["query"] = query
        if not query:
            return _response(
                state,
                "我还没有拿到搜索词。先告诉我你想买什么，我会整理需求卡。",
                intervention_level="info",
            )

        result = self.agent.run(
            query=query,
            user_id=state["user_id"],
            session_id=state["session_id"],
            require_confirmation=True,
            use_llm=bool(payload.get("use_llm", False)),
        )
        state["intent"] = result.intent
        state["purchase_brief"] = result.purchase_brief
        state["recommendations"] = result.recommendations
        cards = [_brief_card(result.purchase_brief)]
        questions = result.purchase_brief.get("confirmation_questions", [])
        if questions:
            cards.append({"type": "questions", "title": "我建议先确认", "items": questions})
        return _response(
            state,
            "我已经把你的搜索整理成购买需求卡。先确认预算、场景和不能接受项，后面我会根据你的浏览行为实时提醒。",
            cards,
            intervention_level="ask",
            reason="search_started_with_purchase_brief",
        )

    def _handle_feedback(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        feedback = str(payload.get("feedback") or "").strip()
        query = state.get("query") or feedback
        if not feedback:
            return _response(state, "还没有收到你的补充说明。", intervention_level="info")
        result = self.agent.run(
            query=query,
            user_id=state["user_id"],
            session_id=state["session_id"],
            require_confirmation=True,
            human_feedback=feedback,
            brief_overrides=payload.get("brief_overrides"),
            use_llm=bool(payload.get("use_llm", False)),
        )
        state["query"] = result.query
        state["intent"] = result.intent
        state["purchase_brief"] = result.purchase_brief
        state["recommendations"] = result.recommendations
        return _response(
            state,
            "已把你的补充信息写回需求卡。接下来你点开具体商品时，我会按这些约束做实时检查。",
            [_brief_card(result.purchase_brief)],
            intervention_level="info",
            reason="feedback_normalized",
        )

    def _handle_product_viewed(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        product = self._product(payload.get("product_id"))
        if product is None:
            return _response(state, "这个商品 ID 不在当前虚拟商品库里。", intervention_level="warn")
        _append_unique(state, "viewed_products", product.product_id)
        state["current_product_id"] = product.product_id
        return self._product_guidance_response(state, product, reason="product_viewed")

    def _handle_review_opened(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        product = self._product(payload.get("product_id") or state.get("current_product_id"))
        if product is None:
            return _response(state, "先点进一个商品，我再帮你总结评论风险。", intervention_level="info")
        state["current_product_id"] = product.product_id
        evidence = self._evidence(product, state)
        return _response(
            state,
            "你正在看评论区。我把和当前需求最相关的评论证据提出来了，重点看正负面 aspect。",
            [_product_card(product), _evidence_card(evidence)],
            intervention_level="info",
            reason="review_evidence_opened",
        )

    def _handle_compare_added(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        product = self._product(payload.get("product_id"))
        if product is None:
            return _response(state, "这个商品暂时无法加入对比。", intervention_level="warn")
        _append_unique(state, "compared_products", product.product_id)
        products = [self._product(product_id) for product_id in state.get("compared_products", [])]
        products = [item for item in products if item is not None]
        if len(products) < 2:
            return _response(
                state,
                f"已把 {product.title} 放入对比。再看一款商品后，我可以帮你生成对比表。",
                [_product_card(product)],
                intervention_level="info",
                reason="compare_started",
            )
        profile = self._profile(state)
        dimensions = _comparison_dimensions(state.get("intent", {}), profile) if profile else []
        table = compare_products(products[:5], dimensions[:6])
        return _response(
            state,
            "你已经进入对比阶段。我先按你的需求维度生成一个结构化对比表。",
            [{"type": "comparison", "title": "候选商品对比", "rows": table}],
            intervention_level="suggest",
            reason="comparison_ready",
        )

    def _handle_cart_added(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        product = self._product(payload.get("product_id"))
        if product is None:
            return _response(state, "这个商品暂时无法加入购物车检查。", intervention_level="warn")
        _append_unique(state, "cart_products", product.product_id)
        state["current_product_id"] = product.product_id
        return self._product_guidance_response(state, product, reason="cart_added", checkout_mode=True)

    def _handle_cart_removed(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        product_id = str(payload.get("product_id") or "")
        state["cart_products"] = [
            item for item in state.get("cart_products", []) if item != product_id
        ]
        return _response(
            state,
            "我已同步购物车变化。你继续看商品时，我会按当前需求帮你检查。",
            intervention_level="info",
            reason="cart_updated",
        )

    def _handle_checkout(self, state: dict[str, Any]) -> dict[str, Any]:
        products = [self._product(product_id) for product_id in state.get("cart_products", [])]
        products = [item for item in products if item is not None]
        if not products:
            return _response(
                state,
                "你已经到结算阶段，但购物车里还没有我能检查的商品。",
                intervention_level="warn",
                reason="checkout_without_cart",
            )
        kept, rejected = filter_by_constraints(products, state.get("intent", {}))
        cards = [
            {
                "type": "checkout_check",
                "title": "下单前检查",
                "kept": [_product_summary(product) for product in kept],
                "rejected": rejected,
            }
        ]
        if rejected:
            message = "下单前我发现购物车里有商品违反了你的硬约束，建议先处理这些风险。"
            level = "critical"
        else:
            message = "下单前检查通过：购物车商品没有违反预算和明确排除项。建议再确认评论风险是否可接受。"
            level = "suggest"
        return _response(state, message, cards, intervention_level=level, reason="checkout_self_check")

    def _passive_update(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("signals", {}).update(payload.get("signals", {}))
        return _response(
            state,
            "我已记录你的浏览状态。等你点进商品、打开评论或加入购物车时，我会主动做检查。",
            intervention_level="silent",
            reason="passive_event_recorded",
        )

    def _product_guidance_response(
        self,
        state: dict[str, Any],
        product: Product,
        reason: str,
        checkout_mode: bool = False,
    ) -> dict[str, Any]:
        kept, rejected = filter_by_constraints([product], state.get("intent", {}))
        evidence = self._evidence(product, state)
        cards = [_product_card(product), _evidence_card(evidence)]
        if rejected:
            cards.append({"type": "constraint_violation", "title": "硬约束风险", "items": rejected})
            return _response(
                state,
                f"{product.title} 命中了你的硬约束，不建议继续作为首选。主要原因：{'; '.join(rejected[0]['reasons'])}",
                cards,
                intervention_level="critical",
                reason=f"{reason}_constraint_violation",
            )
        if checkout_mode:
            message = f"{product.title} 已加入购物车。它没有违反当前硬约束，我会建议你下单前再确认评论风险。"
            level = "suggest"
        else:
            message = f"你正在看 {product.title}。它没有违反当前硬约束，我已提取相关评论证据供你判断。"
            level = "info"
        return _response(state, message, cards, intervention_level=level, reason=reason)

    def _evidence(self, product: Product, state: dict[str, Any]) -> list[dict[str, Any]]:
        profile = self._profile(state)
        fallback_dimensions = profile.dimension_names if profile else []
        aspects = _review_aspects(state.get("intent", {}), fallback_dimensions)
        return retrieve_product_reviews(
            reviews=self.agent.graph.reviews,
            product_id=product.product_id,
            aspects=aspects,
            top_k=3,
            query=state.get("query") or product.title,
            vector_store=self.agent.graph.review_vector_store,
        )

    def _profile(self, state: dict[str, Any]):
        category = state.get("intent", {}).get("category")
        for profile in self.agent.graph.profiles:
            if profile.category_id == category:
                return profile
        return None

    def _product(self, product_id: Any) -> Product | None:
        if not product_id:
            return None
        product_id = str(product_id)
        for product in self.agent.graph.products:
            if product.product_id == product_id:
                return product
        return None


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload", {})
    return {
        "session_id": str(event.get("session_id") or "demo-session"),
        "user_id": str(event.get("user_id") or "demo-user"),
        "event_type": str(event.get("event_type") or "unknown"),
        "payload": payload if isinstance(payload, dict) else {},
    }


def _initial_state(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "user_id": "demo-user",
        "stage": "idle",
        "query": "",
        "intent": {},
        "purchase_brief": {},
        "current_product_id": None,
        "viewed_products": [],
        "compared_products": [],
        "cart_products": [],
        "recommendations": [],
        "signals": {},
        "assistant_cards": [],
        "last_assistant_message": "",
    }


def _response(
    state: dict[str, Any],
    message: str,
    cards: list[dict[str, Any]] | None = None,
    intervention_level: str = "info",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "session_id": state["session_id"],
        "stage": state.get("stage", "idle"),
        "assistant_message": message,
        "assistant_cards": cards or [],
        "intervention": {
            "level": intervention_level,
            "reason": reason,
        },
    }


def _brief_card(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "purchase_brief",
        "title": "购买需求卡",
        "category": brief.get("category", {}),
        "budget_max": brief.get("budget_max"),
        "scenarios": brief.get("scenarios", []),
        "must_dimensions": brief.get("must_dimensions", []),
        "exclude_specs": brief.get("exclude_specs", {}),
        "soft_preferences": brief.get("soft_preferences", []),
    }


def _product_card(product: Product) -> dict[str, Any]:
    return {
        "type": "current_product",
        "title": "当前商品",
        "product": _product_summary(product),
    }


def _evidence_card(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "review_evidence",
        "title": "相关评论证据",
        "items": evidence,
    }


def _product_summary(product: Product) -> dict[str, Any]:
    return to_plain_dict(
        {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "price": product.price,
            "specs": product.specs,
            "tags": product.tags,
        }
    )


def _append_unique(state: dict[str, Any], key: str, value: str) -> None:
    values = list(state.get(key, []))
    if value not in values:
        values.append(value)
    state[key] = values[-20:]
