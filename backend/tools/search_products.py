from __future__ import annotations

from backend.models import Product


def search_products(
    products: list[Product],
    query: str,
    category: str | None,
    top_k: int = 20,
) -> list[Product]:
    """Retrieve candidate products by category and lightweight lexical scoring."""
    candidates = [
        product for product in products if category is None or product.category == category
    ]
    scored = [
        (_score_product(product, query, category), product)
        for product in candidates
    ]
    scored.sort(key=lambda item: (-item[0], item[1].price))
    return [product for score, product in scored[:top_k] if score > 0 or category]


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
