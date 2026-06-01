from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.shopping_copilot import ShoppingCopilot
from backend.agents.workflow import CommerceAgent
from backend.data_loader import load_products


DEFAULT_QUERY = "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"


@st.cache_resource
def get_copilot() -> ShoppingCopilot:
    return ShoppingCopilot(agent=CommerceAgent())


@st.cache_data
def get_products() -> list[dict[str, Any]]:
    return [
        {
            "product_id": product.product_id,
            "title": product.title,
            "category": product.category,
            "brand": product.brand,
            "price": product.price,
            "specs": product.specs,
            "tags": product.tags,
        }
        for product in load_products()
    ]


def emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
    result = copilot.handle_event(
        {
            "session_id": st.session_state.session_id,
            "user_id": st.session_state.user_id,
            "event_type": event_type,
            "payload": payload or {},
        }
    )
    st.session_state.last_result = result


def render_card(card: dict[str, Any]) -> None:
    card_type = card.get("type")
    st.markdown(f"**{card.get('title', '提示')}**")
    if card_type == "purchase_brief":
        st.json(
            {
                "category": card.get("category", {}),
                "budget_max": card.get("budget_max"),
                "scenarios": card.get("scenarios", []),
                "must_dimensions": card.get("must_dimensions", []),
                "exclude_specs": card.get("exclude_specs", {}),
            },
            expanded=False,
        )
    elif card_type == "questions":
        for item in card.get("items", []):
            st.write(f"- {item.get('question')}")
    elif card_type == "current_product":
        product = card.get("product", {})
        st.write(f"{product.get('title')} · {product.get('price')} 元")
        st.caption("、".join(product.get("tags", [])))
    elif card_type == "review_evidence":
        for item in card.get("items", []):
            aspects = item.get("matched_aspects", {})
            st.write(f"- 评分 {item.get('rating')} · {item.get('content')}")
            if aspects:
                st.caption(" / ".join(f"{key}:{value}" for key, value in aspects.items()))
    elif card_type == "constraint_violation":
        for item in card.get("items", []):
            st.error(f"{item.get('title')}：{'；'.join(item.get('reasons', []))}")
    elif card_type == "comparison":
        st.dataframe(card.get("rows", []), use_container_width=True, hide_index=True)
    elif card_type == "checkout_check":
        rejected = card.get("rejected", [])
        if rejected:
            for item in rejected:
                st.error(f"{item.get('title')}：{'；'.join(item.get('reasons', []))}")
        else:
            st.success("购物车商品未违反当前硬约束")
    else:
        st.json(card, expanded=False)


st.set_page_config(page_title="CartPilot Copilot", layout="wide")
copilot = get_copilot()
products = get_products()

if "session_id" not in st.session_state:
    st.session_state.session_id = "demo-shopping-session"
if "user_id" not in st.session_state:
    st.session_state.user_id = "demo-user"
if "last_result" not in st.session_state:
    st.session_state.last_result = None

st.title("CartPilot 购物小助手")

left, right = st.columns([0.62, 0.38], gap="large")

with left:
    st.subheader("购物现场")
    st.text_input("Session", key="session_id")
    st.text_input("User", key="user_id")
    query = st.text_area("搜索需求", value=DEFAULT_QUERY, height=88)
    if st.button("提交搜索事件", type="primary"):
        emit("search_submitted", {"query": query})

    st.divider()
    category = st.selectbox(
        "商品品类",
        sorted({product["category"] for product in products}),
    )
    filtered = [product for product in products if product["category"] == category]
    labels = {
        f"{product['title']} · {product['price']:.0f}元": product["product_id"]
        for product in filtered
    }
    selected_label = st.selectbox("当前商品", list(labels))
    selected_product_id = labels[selected_label]

    action_cols = st.columns(5)
    with action_cols[0]:
        if st.button("查看商品", use_container_width=True):
            emit("product_viewed", {"product_id": selected_product_id})
    with action_cols[1]:
        if st.button("看评论", use_container_width=True):
            emit("review_section_opened", {"product_id": selected_product_id})
    with action_cols[2]:
        if st.button("加入对比", use_container_width=True):
            emit("compare_added", {"product_id": selected_product_id})
    with action_cols[3]:
        if st.button("加入购物车", use_container_width=True):
            emit("cart_added", {"product_id": selected_product_id})
    with action_cols[4]:
        if st.button("结算", use_container_width=True):
            emit("checkout_started", {})

    feedback = st.text_input("补充回答", placeholder="例如：预算2000以内，通勤用，不要入耳式")
    if st.button("回答助手追问"):
        emit("assistant_question_answered", {"feedback": feedback})

with right:
    st.subheader("旁边小助手")
    result = st.session_state.last_result or copilot.get_state(st.session_state.session_id)
    if "assistant_message" in result:
        level = result.get("intervention", {}).get("level", "info")
        if level == "critical":
            st.error(result["assistant_message"])
        elif level == "warn":
            st.warning(result["assistant_message"])
        else:
            st.info(result["assistant_message"])
        for card in result.get("assistant_cards", []):
            with st.container(border=True):
                render_card(card)
    else:
        st.info("先提交搜索事件，小助手会开始维护购物状态。")

    with st.expander("Session State", expanded=False):
        state = result.get("state", result)
        st.json(json.loads(json.dumps(state, ensure_ascii=False)), expanded=False)

    with st.expander("Recent Events", expanded=False):
        st.json(result.get("recent_events", []), expanded=False)
