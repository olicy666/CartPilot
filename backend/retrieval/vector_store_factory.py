from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.models import Product, Review
from backend.retrieval.chroma_vector_store import (
    ChromaProductVectorStore,
    ChromaReviewVectorStore,
    ChromaUnavailableError,
)
from backend.retrieval.product_vector_store import ProductVectorStore
from backend.retrieval.review_vector_store import ReviewVectorStore


def build_product_vector_store(
    products: list[Product],
    cache_dir: Path,
    rebuild: bool = False,
) -> Any:
    provider = _vector_store_provider()
    if provider == "chroma":
        try:
            return ChromaProductVectorStore.from_products(
                products,
                persist_dir=cache_dir / "chroma",
                rebuild=rebuild,
            )
        except ChromaUnavailableError:
            if _strict_chroma():
                raise
    return ProductVectorStore.from_products(
        products,
        db_path=cache_dir / "product_vectors.sqlite",
        rebuild=rebuild,
    )


def build_review_vector_store(
    reviews: list[Review],
    cache_dir: Path,
    rebuild: bool = False,
) -> Any:
    provider = _vector_store_provider()
    if provider == "chroma":
        try:
            return ChromaReviewVectorStore.from_reviews(
                reviews,
                persist_dir=cache_dir / "chroma",
                rebuild=rebuild,
            )
        except ChromaUnavailableError:
            if _strict_chroma():
                raise
    return ReviewVectorStore.from_reviews(
        reviews,
        db_path=cache_dir / "review_vectors.sqlite",
        rebuild=rebuild,
    )


def _vector_store_provider() -> str:
    return (os.getenv("VECTOR_STORE_PROVIDER") or "chroma").lower()


def _strict_chroma() -> bool:
    return os.getenv("VECTOR_STORE_STRICT", "").lower() in {"1", "true", "yes"}
