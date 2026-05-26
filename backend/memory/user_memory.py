from __future__ import annotations

from typing import Any


class InMemoryUserMemory:
    """Small runtime memory store. Replace with Redis or DB later."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        return self._data

    def get(self, user_id: str) -> dict[str, Any]:
        return self._data.get(user_id, {})
