from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class SQLiteRunMonitor:
    """Persist traces and aggregate lightweight operational metrics."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def record(self, response: dict[str, Any]) -> None:
        run_id = str(response.get("run_id") or "")
        session_id = str(response.get("session_id") or "")
        workflow_status = str(response.get("workflow_status") or "unknown")
        llm_meta = response.get("llm_meta", {}) if isinstance(response.get("llm_meta"), dict) else {}
        self_check = response.get("self_check", {}) if isinstance(response.get("self_check"), dict) else {}
        llm_fallback = bool(llm_meta.get("enabled") and not llm_meta.get("used"))
        self_check_failed = bool(self_check and not self_check.get("passed", False))
        errored = workflow_status in {"error", "failed"} or workflow_status.endswith("_error")

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_traces
                (run_id, session_id, workflow_status, llm_fallback, self_check_failed, errored, response_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    run_id,
                    session_id,
                    workflow_status,
                    int(llm_fallback),
                    int(self_check_failed),
                    int(errored),
                    json.dumps(response, ensure_ascii=False),
                ),
            )
            conn.commit()

    def metrics(self) -> dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(llm_fallback) AS llm_fallback_runs,
                    SUM(self_check_failed) AS self_check_failed_runs,
                    SUM(errored) AS errored_runs
                FROM run_traces
                """
            ).fetchone()
            statuses = conn.execute(
                """
                SELECT workflow_status, COUNT(*)
                FROM run_traces
                GROUP BY workflow_status
                ORDER BY COUNT(*) DESC
                """
            ).fetchall()
        total = int(row[0] if row else 0)
        llm_fallback = int(row[1] or 0) if row else 0
        self_check_failed = int(row[2] or 0) if row else 0
        errored = int(row[3] or 0) if row else 0
        return {
            "total_runs": total,
            "llm_fallback_runs": llm_fallback,
            "llm_fallback_rate": _rate(llm_fallback, total),
            "self_check_failed_runs": self_check_failed,
            "self_check_failed_rate": _rate(self_check_failed, total),
            "errored_runs": errored,
            "error_rate": _rate(errored, total),
            "workflow_status_counts": {status: count for status, count in statuses},
        }

    def recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT response_json FROM run_traces
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        traces = []
        for row in rows:
            try:
                traces.append(json.loads(row[0]))
            except json.JSONDecodeError:
                continue
        return traces

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_traces (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workflow_status TEXT NOT NULL,
                    llm_fallback INTEGER NOT NULL DEFAULT 0,
                    self_check_failed INTEGER NOT NULL DEFAULT 0,
                    errored INTEGER NOT NULL DEFAULT 0,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_traces_session ON run_traces(session_id, created_at)"
            )
            conn.commit()


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
