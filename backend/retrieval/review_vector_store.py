from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.models import Review


DEFAULT_VECTOR_DIM = 256


class ReviewVectorStore:
    """Small SQLite-backed vector store for review evidence retrieval.

    This is intentionally dependency-light for the demo. It stores normalized
    hashed text vectors and uses cosine similarity at query time. The public
    interface is narrow so it can later be swapped for Chroma, Qdrant, or Milvus.
    """

    def __init__(self, db_path: Path, dim: int = DEFAULT_VECTOR_DIM):
        self.db_path = db_path
        self.dim = dim
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def from_reviews(
        cls,
        reviews: list[Review],
        db_path: Path,
        rebuild: bool = False,
    ) -> "ReviewVectorStore":
        store = cls(db_path=db_path)
        if rebuild or store.count() != len(reviews):
            store.rebuild(reviews)
        return store

    def rebuild(self, reviews: list[Review]) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM review_vectors")
            conn.executemany(
                """
                INSERT INTO review_vectors
                (review_id, product_id, rating, content, aspects_json, vector_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        review.review_id,
                        review.product_id,
                        review.rating,
                        review.content,
                        json.dumps(review.aspects, ensure_ascii=False),
                        json.dumps(_embed(_review_document(review), self.dim)),
                    )
                    for review in reviews
                ],
            )
            conn.commit()

    def count(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM review_vectors").fetchone()
        return int(row[0] if row else 0)

    def search(
        self,
        query: str,
        product_id: str | None = None,
        aspects: list[str] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        query_text = " ".join([query, *(aspects or [])])
        query_vector = _embed(query_text, self.dim)
        rows = self._load_rows(product_id)
        scored = []
        for row in rows:
            vector = json.loads(row["vector_json"])
            score = _cosine(query_vector, vector)
            aspects_dict = json.loads(row["aspects_json"])
            if aspects:
                score += _aspect_bonus(aspects_dict, aspects)
            scored.append((score, row, aspects_dict))

        scored.sort(key=lambda item: (-item[0], -item[1]["rating"]))
        evidence = []
        for score, row, aspects_dict in scored[:top_k]:
            evidence.append(
                {
                    "review_id": row["review_id"],
                    "rating": row["rating"],
                    "content": row["content"],
                    "matched_aspects": {
                        aspect: sentiment
                        for aspect, sentiment in aspects_dict.items()
                        if not aspects or aspect in aspects
                    },
                    "retrieval_score": round(score, 4),
                    "retrieval_source": "sqlite_vector_store",
                }
            )
        return evidence

    def _load_rows(self, product_id: str | None) -> list[sqlite3.Row]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if product_id:
                rows = conn.execute(
                    "SELECT * FROM review_vectors WHERE product_id = ?",
                    (product_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM review_vectors").fetchall()
        return list(rows)

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_vectors (
                    review_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    aspects_json TEXT NOT NULL,
                    vector_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_review_vectors_product_id ON review_vectors(product_id)"
            )
            conn.commit()


def _review_document(review: Review) -> str:
    aspect_terms = " ".join(
        f"{aspect} {sentiment}" for aspect, sentiment in review.aspects.items()
    )
    return f"{review.content} {aspect_terms}"


def _embed(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token in _tokens(text):
        index = _stable_hash(token) % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


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


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _aspect_bonus(aspects_dict: dict[str, str], aspects: list[str]) -> float:
    score = 0.0
    for aspect in aspects:
        if aspect in aspects_dict:
            score += 0.18
    return score
