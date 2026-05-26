from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LLMConfig":
        _load_dotenv_if_available()
        file_config = _load_local_config()
        return cls(
            base_url=(
                os.getenv("LLM_BASE_URL")
                or file_config.get("base_url")
                or "https://api.openai.com/v1"
            ).rstrip("/"),
            api_key=(
                os.getenv("LLM_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or file_config.get("api_key")
            ),
            model=os.getenv("LLM_MODEL") or file_config.get("model") or "gpt-4o-mini",
            timeout_seconds=float(
                os.getenv("LLM_TIMEOUT_SECONDS")
                or file_config.get("timeout_seconds")
                or 30
            ),
        )


class LLMClient:
    """Minimal OpenAI-compatible chat completions client.

    The client is intentionally small and dependency-free. It never logs secrets,
    and callers can safely skip LLM usage when `is_configured` is false.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if not self.is_configured:
            return None, {"ok": False, "reason": "llm_api_key_missing"}

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            url=f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(  # noqa: S310 - user-configured HTTPS endpoint.
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")[:500]
            return None, {
                "ok": False,
                "reason": "llm_http_error",
                "status": error.code,
                "error_body": error_body,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            return None, {
                "ok": False,
                "reason": "llm_request_failed",
                "error_type": type(error).__name__,
            }

        content = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _parse_json_content(content)
        if parsed is None:
            return None, {"ok": False, "reason": "llm_json_parse_failed"}

        return parsed, {
            "ok": True,
            "model": body.get("model", self.config.model),
            "usage": body.get("usage", {}),
        }


def _parse_json_content(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None

    return value if isinstance(value, dict) else None


def _load_local_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "llm.local.json"
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return value if isinstance(value, dict) else {}
