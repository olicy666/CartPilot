from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    version: str
    text: str


PROMPTS = {
    "agentic_planner_system": PromptTemplate(
        key="agentic_planner_system",
        version="agentic-planner-v1",
        text="""你是一个有边界的电商导购 Agent。
你可以决定追问什么、如何归一化用户反馈、下一步调用哪些工具、检索哪些评论证据、如何解释推荐。
必须只输出 JSON，不要输出 Markdown。
硬约束不得放松：预算上限、用户明确排除项、商品事实和自检仍由代码校验。
""",
    ),
    "intent_parser_system": PromptTemplate(
        key="intent_parser_system",
        version="intent-parser-v1",
        text="""你是电商导购 Agent 的意图解析器。
只输出 JSON，不要输出 Markdown。
目标是把用户购物需求解析成可执行约束，未知字段用 null 或空数组。
不要创造不存在的品类 id，只能使用候选品类中的 category_id。
""",
    ),
}


def get_prompt(key: str) -> PromptTemplate:
    try:
        return PROMPTS[key]
    except KeyError as error:
        raise ValueError(f"unknown_prompt:{key}") from error
