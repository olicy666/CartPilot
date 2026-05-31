from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.models import Review
from backend.retrieval.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    create_embedding_provider,
)


DEFAULT_VECTOR_DIM = 256


class ReviewVectorStore:
    """Small SQLite-backed vector store for review evidence retrieval.

    This is intentionally dependency-light for the demo. It stores normalized
    hashed text vectors and uses cosine similarity at query time. The public
    interface is narrow so it can later be swapped for Chroma, Qdrant, or Milvus.
    """

    def __init__(
        self,
        db_path: Path,
        dim: int = DEFAULT_VECTOR_DIM,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.db_path = db_path
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.dim = dim
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def from_reviews(
        cls,
        reviews: list[Review],
        db_path: Path,
        rebuild: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "ReviewVectorStore":
        store = cls(db_path=db_path, embedding_provider=embedding_provider)
        if rebuild or store._needs_rebuild(len(reviews)):
            store.rebuild(reviews)
        return store

    def rebuild(self, reviews: list[Review]) -> None:
        documents = [_review_document(review) for review in reviews]
        vectors = self.embedding_provider.embed_texts(documents)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM review_vectors")
            conn.executemany(
                """
                INSERT INTO review_vectors
                (review_id, product_id, rating, content, aspects_json, vector_json, provider_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        review.review_id,
                        review.product_id,
                        review.rating,
                        review.content,
                        json.dumps(review.aspects, ensure_ascii=False),
                        json.dumps(vector),
                        self.embedding_provider.name,
                    )
                    for review, vector in zip(reviews, vectors)
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
        query_vector = self.embedding_provider.embed_text(query_text)
        rows = self._load_rows(product_id)
        scored = []
        for row in rows:
            vector = json.loads(row["vector_json"])
            score = cosine_similarity(query_vector, vector)
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
                    "embedding_provider": row["provider_name"],
                }
            )
        return evidence

    def _needs_rebuild(self, expected_count: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT provider_name) FROM review_vectors"
            ).fetchone()
        count = int(row[0] if row else 0)
        provider_count = int(row[1] if row else 0)
        if count != expected_count or provider_count != 1:
            return True
        with closing(sqlite3.connect(self.db_path)) as conn:
            provider_row = conn.execute(
                "SELECT provider_name FROM review_vectors LIMIT 1"
            ).fetchone()
        return bool(provider_row and provider_row[0] != self.embedding_provider.name)

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
                    vector_json TEXT NOT NULL,
                    provider_name TEXT NOT NULL DEFAULT 'hash'
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(review_vectors)").fetchall()
            }
            if "provider_name" not in columns:
                conn.execute(
                    "ALTER TABLE review_vectors ADD COLUMN provider_name TEXT NOT NULL DEFAULT 'hash'"
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


def _aspect_bonus(aspects_dict: dict[str, str], aspects: list[str]) -> float:
    score = 0.0
    for aspect in aspects:
        if aspect in aspects_dict:
            score += 0.18
    return score
