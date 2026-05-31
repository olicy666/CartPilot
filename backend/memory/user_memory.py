from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class InMemoryUserMemory:
    """Small runtime memory store. Replace with Redis or DB later."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        return self._data

    def get(self, user_id: str) -> dict[str, Any]:
        return self._data.get(user_id, {})

    def set(self, user_id: str, value: dict[str, Any]) -> None:
        self._data[user_id] = value


class SQLiteUserMemory:
    """Small SQLite-backed preference memory for local production-like demos."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def snapshot(self) -> dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute("SELECT user_id, memory_json FROM user_memory").fetchall()
        memory: dict[str, Any] = {}
        for user_id, raw in rows:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = {}
            memory[user_id] = value if isinstance(value, dict) else {}
        return memory

    def get(self, user_id: str) -> dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT memory_json FROM user_memory WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def set(self, user_id: str, value: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO user_memory (user_id, memory_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    memory_json = excluded.memory_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, json.dumps(value, ensure_ascii=False)),
            )
            conn.commit()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id TEXT PRIMARY KEY,
                    memory_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
