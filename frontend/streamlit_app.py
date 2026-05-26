from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.workflow import CommerceAgent


DEFAULT_QUERY = "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"


@st.cache_resource
def get_agent() -> CommerceAgent:
    return CommerceAgent()


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _chips(items: list[str], class_name: str = "chip") -> str:
    if not items:
        return '<span class="muted">暂无</span>'
    return "".join(f'<span class="{class_name}">{_escape(item)}</span>' for item in items)


def _money(value: Any) -> str:
    if value is None:
        return "未设置"
    return f"{float(value):.0f} 元"


def _status_text(status: str) -> str:
    mapping = {
        "auto_confirmed": "已自动确认",
        "awaiting_user_confirmation": "等待确认",
        "confirmed_with_overrides": "已人工调整",
    }
    return mapping.get(status, status or "未知")


def _candidate_options(result: Any) -> dict[str, str]:
    if not result:
        return {}
    for step in result.trace:
        if step.name == "Product Search":
            products = step.outputs.get("candidate_products", [])
            return {
                f"{item['title']} · {item['price']:.0f}元": item["product_id"]
                for item in products
            }
    return {}


def _render_brief(brief: dict[str, Any]) -> None:
    category = brief.get("category", {})
    st.markdown(
        f"""
        <div class="surface">
          <div class="section-kicker">PURCHASE BRIEF</div>
          <div class="brief-title">{_escape(category.get("display_name", "未识别品类"))}</div>
          <div class="status-row">
            <span class="status-dot"></span>
            <span>{_escape(_status_text(brief.get("status", "")))}</span>
          </div>
          <div class="brief-grid">
            <div><span class="field-label">预算</span><strong>{_escape(_money(brief.get("budget_max")))}</strong></div>
            <div><span class="field-label">场景</span>{_chips(brief.get("scenarios", []))}</div>
            <div><span class="field-label">硬约束</span>{_chips(brief.get("must_dimensions", []))}</div>
            <div><span class="field-label">偏好</span>{_chips(brief.get("soft_preferences", []))}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    risks = brief.get("common_risks", [])
    if risks:
        st.markdown("**常见风险点**")
        st.markdown(_chips(risks, "risk-chip"), unsafe_allow_html=True)

    dimensions = brief.get("decision_dimensions", [])
    if dimensions:
        st.markdown("**当前品类决策维度**")
        labels = [item.get("label", item.get("name", "")) for item in dimensions]
        st.markdown(_chips(labels), unsafe_allow_html=True)


def _render_questions(brief: dict[str, Any]) -> None:
    questions = brief.get("confirmation_questions", [])
    if not questions:
        st.caption("当前需求已经比较完整，可以直接继续推荐。")
        return

    for item in questions:
        st.markdown(
            f"""
            <div class="question-card">
              <div class="question-title">{_escape(item.get("title", "需求确认"))}</div>
              <div class="question-text">{_escape(item.get("question", ""))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_question_inputs(brief: dict[str, Any]) -> str:
    questions = brief.get("confirmation_questions", [])
    answers: list[str] = []
    if not questions:
        st.caption("当前需求已经比较完整，可以直接继续推荐。")
    for question in questions:
        _render_question_card(question)
        options = list(question.get("options", []))
        input_type = question.get("input_type", "multi_choice")
        if input_type == "single_choice":
            choices = ["暂不选择", *options]
            selected = st.radio(
                question.get("title", "需求确认"),
                choices,
                key=_question_key(question, "single"),
                label_visibility="collapsed",
            )
            if selected and selected != "暂不选择":
                answers.append(_format_question_answer(question, [selected]))
        elif options:
            selected_items = st.multiselect(
                question.get("title", "需求确认"),
                options=options,
                key=_question_key(question, "multi"),
                label_visibility="collapsed",
                placeholder="选一个或多个",
            )
            if selected_items:
                answers.append(_format_question_answer(question, selected_items))
        else:
            text = st.text_input(
                question.get("title", "需求确认"),
                key=_question_key(question, "text"),
                label_visibility="collapsed",
            )
            if text.strip():
                answers.append(text.strip())

    custom_answer = st.text_area(
        "补充说明",
        key="human_feedback_text",
        height=92,
        placeholder="选项不够准确时，可以在这里补充一句。",
    )
    if custom_answer.strip():
        answers.append(custom_answer.strip())
    return "；".join(answers)


def _render_question_card(question: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="question-card">
          <div class="question-title">{_escape(question.get("title", "需求确认"))}</div>
          <div class="question-text">{_escape(question.get("question", ""))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _question_key(question: dict[str, Any], suffix: str) -> str:
    question_id = question.get("id", "question")
    return f"question_{question_id}_{suffix}"


def _format_question_answer(question: dict[str, Any], selected: list[str]) -> str:
    joined = "、".join(selected)
    question_id = question.get("id")
    if question_id == "budget":
        return f"预算{selected[0]}"
    if question_id == "scenario":
        return f"使用场景：{joined}"
    if question_id == "priority":
        return f"更看重：{joined}"
    if question_id == "avoid":
        return f"不能接受：{joined}"
    return f"{question.get('title', '需求')}：{joined}"


def _render_recommendation_card(item: dict[str, Any], index: int) -> None:
    score = float(item.get("score", 0))
    score_width = max(8, min(score / 1.5 * 100, 100))
    title = _escape(item["title"])
    price = _escape(f"{item['price']:.0f} 元")
    brand = _escape(item.get("brand", ""))
    tags = _chips(item.get("tags", [])[:5])

    st.markdown(
        f"""
        <div class="product-card">
          <div class="product-topline">
            <div class="rank-badge">Top {index}</div>
            <div class="score-label">匹配分 {score:.2f}</div>
          </div>
          <div class="product-title">{title}</div>
          <div class="product-meta">{brand} · {price}</div>
          <div class="score-track"><div class="score-fill" style="width:{score_width:.0f}%"></div></div>
          <div class="chip-row">{tags}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    reason_cols = st.columns([0.62, 0.38])
    with reason_cols[0]:
        st.markdown("**推荐依据**")
        for reason in item.get("reasons", []):
            st.markdown(f"- {reason}")
    with reason_cols[1]:
        st.markdown("**风险提示**")
        risks = item.get("risks") or ["暂无明显风险"]
        for risk in risks:
            st.markdown(f"- {risk}")

    breakdown = item.get("score_breakdown", {})
    if breakdown:
        readable = {
            "价格": breakdown.get("budget", 0),
            "场景": breakdown.get("scenario", 0),
            "参数": breakdown.get("dimension", 0),
            "证据": breakdown.get("evidence", 0),
        }
        st.caption(
            " · ".join(f"{name} {value:.2f}" for name, value in readable.items())
        )

    with st.expander("查看评论证据", expanded=False):
        for evidence in item.get("evidence", []):
            aspects = evidence.get("matched_aspects", {})
            aspect_text = "、".join(
                f"{key}:{value}" for key, value in aspects.items()
            ) or "综合评价"
            st.markdown(
                f"""
                <div class="evidence">
                  <div class="evidence-meta">评分 {evidence.get("rating", "-")} · {aspect_text}</div>
                  <div>{_escape(evidence.get("content", ""))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_trace(result: Any) -> None:
    st.markdown("**工作流进度**")
    for index, step in enumerate(result.trace, start=1):
        st.markdown(
            f"""
            <div class="timeline-item">
              <div class="timeline-index">{index}</div>
              <div>
                <div class="timeline-title">{_escape(step.name)}</div>
                <div class="timeline-reason">{_escape(step.reason)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_self_check(result: Any) -> None:
    check = result.self_check or {}
    passed = check.get("passed", False)
    label = "通过" if passed else "需检查"
    css_class = "check-ok" if passed else "check-warn"
    st.markdown(
        f'<div class="{css_class}">Self-check：{label} · 已检查 {check.get("checked_items", 0)} 个推荐</div>',
        unsafe_allow_html=True,
    )
    issues = check.get("issues", [])
    if issues:
        for issue in issues:
            st.markdown(f"- `{issue}`")


def _weight_value(brief: dict[str, Any], key: str) -> float:
    weights = brief.get("preference_weights", {})
    value = weights.get(key, 1.0) if isinstance(weights, dict) else 1.0
    return float(value if isinstance(value, (int, float)) else 1.0)


def _render_css() -> None:
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2rem;
            max-width: 1480px;
          }
          .stApp {
            background: #f6f7f9;
            color: #172033;
          }
          h1, h2, h3 {
            letter-spacing: 0;
          }
          .app-header {
            background: linear-gradient(135deg, #ffffff 0%, #eef5ff 100%);
            border: 1px solid #e5e9f0;
            border-radius: 14px;
            padding: 20px 22px;
            margin-bottom: 18px;
          }
          .app-title {
            font-size: 28px;
            font-weight: 760;
            margin-bottom: 6px;
          }
          .app-subtitle {
            color: #667085;
            font-size: 15px;
          }
          .surface, .product-card, .side-panel {
            background: #ffffff;
            border: 1px solid #e5e9f0;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 8px 26px rgba(22, 34, 51, 0.04);
            margin-bottom: 14px;
          }
          .section-kicker {
            color: #667085;
            font-size: 12px;
            font-weight: 720;
            text-transform: uppercase;
            margin-bottom: 8px;
          }
          .brief-title {
            font-size: 22px;
            font-weight: 760;
            margin-bottom: 8px;
          }
          .status-row {
            display: flex;
            gap: 8px;
            align-items: center;
            color: #3d4a5c;
            margin-bottom: 12px;
          }
          .status-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: #16a34a;
            display: inline-block;
          }
          .brief-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
          }
          .field-label {
            display: block;
            color: #667085;
            font-size: 12px;
            margin-bottom: 5px;
          }
          .chip-row {
            margin-top: 12px;
          }
          .chip, .risk-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 9px;
            margin: 3px 4px 3px 0;
            font-size: 12px;
            background: #eef4ff;
            color: #27548a;
            border: 1px solid #d8e6ff;
          }
          .risk-chip {
            background: #fff7ed;
            color: #9a3412;
            border-color: #fed7aa;
          }
          .muted {
            color: #8a94a6;
            font-size: 13px;
          }
          .product-card {
            padding: 18px;
            margin-top: 10px;
          }
          .product-topline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
          }
          .rank-badge {
            background: #172033;
            color: #ffffff;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 720;
          }
          .score-label {
            color: #667085;
            font-size: 13px;
          }
          .product-title {
            font-size: 20px;
            font-weight: 760;
            margin-bottom: 4px;
          }
          .product-meta {
            color: #667085;
            font-size: 14px;
          }
          .score-track {
            height: 7px;
            background: #edf0f5;
            border-radius: 999px;
            margin-top: 14px;
            overflow: hidden;
          }
          .score-fill {
            height: 100%;
            background: linear-gradient(90deg, #2563eb, #16a34a);
            border-radius: 999px;
          }
          .evidence {
            border-left: 3px solid #8bb8ff;
            background: #f8fbff;
            padding: 10px 12px;
            border-radius: 8px;
            margin-bottom: 10px;
          }
          .evidence-meta {
            color: #667085;
            font-size: 12px;
            margin-bottom: 5px;
          }
          .question-card {
            background: #ffffff;
            border: 1px solid #e5e9f0;
            border-left: 4px solid #2563eb;
            border-radius: 10px;
            padding: 12px 13px;
            margin-bottom: 10px;
          }
          .question-title {
            color: #344054;
            font-size: 13px;
            font-weight: 760;
            margin-bottom: 5px;
          }
          .question-text {
            color: #172033;
            font-size: 14px;
            line-height: 1.55;
          }
          .timeline-item {
            display: grid;
            grid-template-columns: 28px 1fr;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px solid #edf0f5;
          }
          .timeline-index {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #eef4ff;
            color: #2563eb;
            font-size: 12px;
            font-weight: 760;
          }
          .timeline-title {
            font-weight: 720;
            font-size: 14px;
          }
          .timeline-reason {
            color: #667085;
            font-size: 12px;
            margin-top: 2px;
          }
          .check-ok, .check-warn {
            border-radius: 10px;
            padding: 10px 12px;
            font-weight: 680;
            margin: 8px 0 12px;
          }
          .check-ok {
            background: #ecfdf3;
            color: #027a48;
            border: 1px solid #abefc6;
          }
          .check-warn {
            background: #fffaeb;
            color: #b54708;
            border: 1px solid #fedf89;
          }
          div[data-testid="stJson"] {
            background: #f8fafc;
            border-radius: 10px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="CommerceMind-Agent", layout="wide")
_render_css()

agent = get_agent()

if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "draft_brief" not in st.session_state:
    st.session_state.draft_brief = None
if "query_text" not in st.session_state:
    st.session_state.query_text = DEFAULT_QUERY
if "human_feedback_text" not in st.session_state:
    st.session_state.human_feedback_text = ""

st.markdown(
    """
    <div class="app-header">
      <div class="app-title">CommerceMind-Agent</div>
      <div class="app-subtitle">把购物需求整理成任务卡，再通过商品工具、评论证据和自检生成可解释推荐。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

top_left, top_right = st.columns([0.72, 0.28])
with top_left:
    query = st.text_area(
        "购物需求",
        key="query_text",
        height=86,
        label_visibility="collapsed",
        placeholder="例如：预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累",
    )
with top_right:
    use_llm = st.toggle("使用 LLM 解析", value=False, help="未配置 API Key 时会自动使用规则解析。")
    button_a, button_b = st.columns(2)
    with button_a:
        build_brief = st.button("整理任务卡", use_container_width=True)
    with button_b:
        direct_run = st.button("直接推荐", type="primary", use_container_width=True)

if build_brief and query.strip():
    result = agent.run(query=query, require_confirmation=True, use_llm=use_llm)
    st.session_state.draft_brief = result.purchase_brief
    st.session_state.last_result = result
    st.session_state.human_feedback_text = ""

if direct_run and query.strip():
    result = agent.run(query=query, use_llm=use_llm)
    st.session_state.last_result = result
    st.session_state.draft_brief = result.purchase_brief

result = st.session_state.last_result
brief = st.session_state.draft_brief

left, center, right = st.columns([0.26, 0.46, 0.28], gap="large")

with left:
    st.markdown("### 任务卡")
    if brief:
        _render_brief(brief)
    else:
        st.info("先整理任务卡，系统会识别品类、预算、场景和硬约束。")

with center:
    st.markdown("### 推荐结果")
    if not result:
        st.info("输入购物需求后，可以先整理任务卡，也可以直接生成推荐。")
    elif not result.recommendations:
        if result.workflow_status == "awaiting_user_confirmation":
            st.info("右侧补充需求后，系统会继续检索商品、引用评论证据并生成推荐。")
        else:
            st.warning(result.answer)
    else:
        if result.comparison_table:
            st.markdown("**对比表**")
            st.dataframe(result.comparison_table, use_container_width=True, hide_index=True)

        for index, item in enumerate(result.recommendations, start=1):
            _render_recommendation_card(item, index)

with right:
    st.markdown("### 需求确认")
    if not brief:
        st.info("整理任务卡后，系统会在这里追问关键需求。")
    else:
        human_feedback = _render_question_inputs(brief)

        st.markdown("### 人工校准")
        budget_value = brief.get("budget_max")
        budget_max = st.number_input(
            "预算上限",
            min_value=0.0,
            value=float(budget_value or 0),
            step=100.0,
            help="设置为 0 表示不限制预算。",
        )

        options = _candidate_options(result)
        selected_banned: list[str] = []
        selected_pinned: list[str] = []
        with st.expander("指定商品", expanded=False):
            if options:
                selected_banned = st.multiselect(
                    "排除商品",
                    options=list(options.keys()),
                    help="用于模拟用户不喜欢某些候选商品。",
                )
                selected_pinned = st.multiselect(
                    "优先考虑",
                    options=list(options.keys()),
                    help="用于模拟用户希望优先看某些候选商品。",
                )
            else:
                st.caption("生成候选商品后可在这里点选，也可以先直接输入商品 ID。")
            banned_ids_text = st.text_input("排除 ID", value="")
            pinned_ids_text = st.text_input("优先 ID", value="")

        with st.expander("高级排序设置", expanded=False):
            budget_weight = st.slider(
                "价格敏感",
                min_value=0.0,
                max_value=3.0,
                value=_weight_value(brief, "budget"),
                step=0.1,
            )
            scenario_weight = st.slider(
                "场景匹配",
                min_value=0.0,
                max_value=3.0,
                value=_weight_value(brief, "scenario"),
                step=0.1,
            )
            dimension_weight = st.slider(
                "参数重要性",
                min_value=0.0,
                max_value=3.0,
                value=_weight_value(brief, "dimension"),
                step=0.1,
            )
            evidence_weight = st.slider(
                "评论证据",
                min_value=0.0,
                max_value=3.0,
                value=_weight_value(brief, "evidence"),
                step=0.1,
            )

        if st.button("回答并继续推荐", type="primary", use_container_width=True):
            banned_ids = [options[label] for label in selected_banned]
            pinned_ids = [options[label] for label in selected_pinned]
            banned_ids.extend(_split_ids(banned_ids_text))
            pinned_ids.extend(_split_ids(pinned_ids_text))
            overrides: dict[str, Any] = {
                "budget_max": budget_max if budget_max > 0 else None,
                "banned_product_ids": list(dict.fromkeys(banned_ids)),
                "pinned_product_ids": list(dict.fromkeys(pinned_ids)),
                "preference_weights": {
                    "budget": budget_weight,
                    "scenario": scenario_weight,
                    "dimension": dimension_weight,
                    "evidence": evidence_weight,
                },
            }
            result = agent.run(
                query=query,
                require_confirmation=True,
                use_llm=use_llm,
                human_feedback=human_feedback,
                brief_overrides=overrides,
            )
            st.session_state.last_result = result
            st.session_state.draft_brief = result.purchase_brief
            st.rerun()

    if result:
        with st.expander("开发调试", expanded=False):
            _render_self_check(result)
            _render_trace(result)
            llm_meta = result.llm_meta or {}
            parser = result.intent.get("parser_source", "rules")
            st.caption(
                f"解析来源：{parser} · LLM 开启：{llm_meta.get('enabled', False)} · "
                f"实际调用：{llm_meta.get('used', False)}"
            )
            st.markdown("**Trace JSON**")
            st.json(json.loads(json.dumps(result.to_dict()["trace"], ensure_ascii=False)))
            st.markdown("**Purchase Brief JSON**")
            st.json(result.purchase_brief)
