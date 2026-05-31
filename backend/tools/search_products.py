from __future__ import annotations

from typing import TYPE_CHECKING

from backend.models import Product
from backend.tools.rerank import rerank_product_candidates

if TYPE_CHECKING:
    from backend.retrieval.product_vector_store import ProductVectorStore


def search_products(
    products: list[Product],
    query: str,
    category: str | None,
    top_k: int = 20,
    vector_store: ProductVectorStore | None = None,
) -> list[Product]:
    """Retrieve candidate products by category, lexical score, and vector score."""
    candidates = [
        product for product in products if category is None or product.category == category
    ]
    vector_scores: dict[str, float] = {}
    if vector_store is not None:
        vector_hits = vector_store.search(query=query, category=category, top_k=top_k)
        vector_scores = {
            item["product_id"]: float(item.get("vector_score", 0.0))
            for item in vector_hits
        }
        vector_ids = set(vector_scores)
        candidates = [
            product
            for product in candidates
            if product.product_id in vector_ids or _score_product(product, query, category) > 0
        ]

    scored = [
        (_score_product(product, query, category) + vector_scores.get(product.product_id, 0.0), product)
        for product in candidates
    ]
    scored.sort(key=lambda item: (-item[0], item[1].price))
    recalled = [product for score, product in scored[:top_k] if score > 0 or category]
    return rerank_product_candidates(recalled, query=query, vector_scores=vector_scores)


def _score_product(product: Product, query: str, category: str | None) -> float:
    normalized_query = query.lower()
    searchable = product.searchable_text()
    score = 0.0

    if category and product.category == category:
        score += 2.0
    if product.brand and product.brand.lower() in normalized_query:
        score += 2.0
    for tag in product.tags:
        if tag.lower() in normalized_query:
            score += 1.5
    for token in _query_tokens(normalized_query):
        if token in searchable:
            score += 0.4

    return round(score, 3)


def _query_tokens(query: str) -> list[str]:
    tokens = []
    for raw in query.replace("，", " ").replace(",", " ").split():
        token = raw.strip().lower()
        if len(token) >= 2:
            tokens.append(token)
    return tokens
