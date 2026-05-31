from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.models import Product
from backend.retrieval.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    create_embedding_provider,
)


class ProductVectorStore:
    """SQLite-backed product vector index.

    The default embedding provider is deterministic and local. Set
    EMBEDDING_PROVIDER=openai to use a real OpenAI-compatible embedding model.
    """

    def __init__(
        self,
        db_path: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.db_path = db_path
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def from_products(
        cls,
        products: list[Product],
        db_path: Path,
        rebuild: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "ProductVectorStore":
        store = cls(db_path=db_path, embedding_provider=embedding_provider)
        if rebuild or store._needs_rebuild(len(products)):
            store.rebuild(products)
        return store

    def rebuild(self, products: list[Product]) -> None:
        documents = [_product_document(product) for product in products]
        vectors = self.embedding_provider.embed_texts(documents)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM product_vectors")
            conn.executemany(
                """
                INSERT INTO product_vectors
                (product_id, category, title, document, vector_json, provider_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        product.product_id,
                        product.category,
                        product.title,
                        document,
                        json.dumps(vector),
                        self.embedding_provider.name,
                    )
                    for product, document, vector in zip(products, documents, vectors)
                ],
            )
            conn.commit()

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        query_vector = self.embedding_provider.embed_text(query)
        rows = self._load_rows(category)
        scored = []
        for row in rows:
            vector = json.loads(row["vector_json"])
            score = cosine_similarity(query_vector, vector)
            scored.append(
                {
                    "product_id": row["product_id"],
                    "title": row["title"],
                    "category": row["category"],
                    "vector_score": round(score, 4),
                    "retrieval_source": "product_vector_store",
                    "embedding_provider": row["provider_name"],
                }
            )
        scored.sort(key=lambda item: -item["vector_score"])
        return scored[:top_k]

    def count(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM product_vectors").fetchone()
        return int(row[0] if row else 0)

    def _needs_rebuild(self, expected_count: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT provider_name) FROM product_vectors"
            ).fetchone()
        count = int(row[0] if row else 0)
        provider_count = int(row[1] if row else 0)
        if count != expected_count or provider_count != 1:
            return True
        with closing(sqlite3.connect(self.db_path)) as conn:
            provider_row = conn.execute(
                "SELECT provider_name FROM product_vectors LIMIT 1"
            ).fetchone()
        return bool(provider_row and provider_row[0] != self.embedding_provider.name)

    def _load_rows(self, category: str | None) -> list[sqlite3.Row]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if category:
                rows = conn.execute(
                    "SELECT * FROM product_vectors WHERE category = ?",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM product_vectors").fetchall()
        return list(rows)

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_vectors (
                    product_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    document TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    provider_name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_vectors_category ON product_vectors(category)"
            )
            conn.commit()


def _product_document(product: Product) -> str:
    specs = " ".join(f"{key}:{value}" for key, value in product.specs.items())
    tags = " ".join(product.tags)
    return " ".join(
        [
            product.title,
            product.brand,
            product.category,
            product.description,
            specs,
            tags,
        ]
    )
