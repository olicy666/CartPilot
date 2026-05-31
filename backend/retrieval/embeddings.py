from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


DEFAULT_HASH_DIM = 256


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_text(self, text: str) -> list[float]:
        ...


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "OpenAIEmbeddingConfig | None":
        api_key = (
            os.getenv("EMBEDDING_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
        )
        if not api_key:
            return None
        return cls(
            base_url=(
                os.getenv("EMBEDDING_BASE_URL")
                or os.getenv("LLM_BASE_URL")
                or "https://api.openai.com/v1"
            ).rstrip("/"),
            api_key=api_key,
            model=os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small",
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS") or 30),
        )


class HashEmbeddingProvider:
    """Deterministic local fallback embedding provider for offline demos."""

    name = "hash"

    def __init__(self, dim: int = DEFAULT_HASH_DIM):
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_embed_hash(text, self.dim) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embedding provider.

    This is opt-in via EMBEDDING_PROVIDER=openai so tests and local demos do not
    accidentally depend on network access or API credentials.
    """

    def __init__(self, config: OpenAIEmbeddingConfig):
        self.config = config
        self.name = f"openai:{config.model}"
        self.dim = int(os.getenv("EMBEDDING_DIM") or 1536)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self.config.model,
            "input": texts,
        }
        request = urllib.request.Request(
            url=f"{self.config.base_url}/embeddings",
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
            error_body = error.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"embedding_http_error:{error.code}:{error_body}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(f"embedding_request_failed:{type(error).__name__}") from error

        rows = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [_normalize_vector(row.get("embedding", [])) for row in rows]
        if len(vectors) != len(texts):
            raise RuntimeError("embedding_response_count_mismatch")
        if vectors:
            self.dim = len(vectors[0])
        return vectors

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def create_embedding_provider() -> EmbeddingProvider:
    provider_name = (os.getenv("EMBEDDING_PROVIDER") or "hash").lower()
    if provider_name == "openai":
        config = OpenAIEmbeddingConfig.from_env()
        if config is not None:
            return OpenAIEmbeddingProvider(config)
    return HashEmbeddingProvider()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _embed_hash(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token in _tokens(text):
        index = _stable_hash(token) % dim
        vector[index] += 1.0
    return _normalize_vector(vector)


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return list(vector)
    return [float(value) / norm for value in vector]


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    tokens.extend(cjk_chars)
    tokens.extend(
        "".join(cjk_chars[index : index + 2])
        for index in range(max(len(cjk_chars) - 1, 0))
    )
    return [token for token in tokens if token.strip()]


def _stable_hash(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)
