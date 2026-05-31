from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class SQLiteCheckpointStore:
    """Persist pending human-in-the-loop checkpoints by session."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save_pending(self, session_id: str, payload: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO hitl_checkpoints (session_id, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()

    def load_pending(self, session_id: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT payload_json FROM hitl_checkpoints WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def clear(self, session_id: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "DELETE FROM hitl_checkpoints WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hitl_checkpoints (
                    session_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
