from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


FOLLOWUP_MARKERS = ["为什么", "为啥", "怎么没", "不推荐", "没有推荐", "不选", "继续", "上一轮"]


class SQLiteConversationStore:
    """Persist recent session turns for follow-up questions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def append_turn(
        self,
        session_id: str,
        query: str,
        response: dict[str, Any],
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO conversation_turns (session_id, query, response_json, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (session_id, query, json.dumps(response, ensure_ascii=False)),
            )
            conn.commit()

    def last_response(self, session_id: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT response_json FROM conversation_turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_turns_session ON conversation_turns(session_id, id)"
            )
            conn.commit()


def is_followup_query(query: str) -> bool:
    normalized = query.strip().lower()
    return any(marker in normalized for marker in FOLLOWUP_MARKERS)


def answer_followup_from_last_response(
    query: str,
    last_response: dict[str, Any],
) -> str | None:
    product_name = _extract_product_hint(query, last_response)
    rejected = _find_rejected_product(product_name, last_response) if product_name else None
    if rejected:
        reasons = "；".join(rejected.get("reasons", [])) or "不满足上一轮硬约束"
        return f"上一轮没有推荐 {rejected.get('title', product_name)}，主要原因是：{reasons}。"

    recommendations = last_response.get("recommendations", [])
    if product_name and recommendations:
        titles = [item.get("title", "") for item in recommendations]
        if not any(product_name.lower() in title.lower() for title in titles):
            top = recommendations[0]
            return (
                f"上一轮优先推荐 {top.get('title')}，因为它的综合分更高。"
                f"{product_name} 没进入前三，通常是预算、场景匹配、参数或评论证据得分不如当前推荐。"
            )

    if recommendations:
        names = "、".join(item.get("title", "") for item in recommendations[:3])
        return f"上一轮推荐前三是：{names}。你可以追问某一款为什么没被推荐，我会按过滤原因和排序证据解释。"
    return None


def _extract_product_hint(query: str, last_response: dict[str, Any]) -> str | None:
    candidates: list[str] = []
    for item in last_response.get("recommendations", []):
        candidates.extend([item.get("title", ""), item.get("brand", ""), item.get("product_id", "")])
    for step in last_response.get("trace", []):
        outputs = step.get("outputs", {}) if isinstance(step, dict) else {}
        for product in outputs.get("candidate_products", []):
            candidates.extend([product.get("title", ""), product.get("product_id", "")])
        for product in outputs.get("rejected", []):
            candidates.extend([product.get("title", ""), product.get("product_id", "")])

    normalized = query.lower()
    for candidate in sorted(set(candidates), key=len, reverse=True):
        if candidate and candidate.lower() in normalized:
            return candidate
    return None


def _find_rejected_product(
    product_hint: str,
    last_response: dict[str, Any],
) -> dict[str, Any] | None:
    hint = product_hint.lower()
    for step in last_response.get("trace", []):
        outputs = step.get("outputs", {}) if isinstance(step, dict) else {}
        for product in outputs.get("rejected", []):
            if hint in product.get("title", "").lower() or hint == product.get("product_id", "").lower():
                return product
    return None
