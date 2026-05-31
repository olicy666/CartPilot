from __future__ import annotations

from typing import Any

from backend.models import Product


def rerank_product_candidates(
    products: list[Product],
    query: str,
    vector_scores: dict[str, float] | None = None,
) -> list[Product]:
    """Second-pass product reranker for recalled products."""
    vector_scores = vector_scores or {}
    scored = [
        (
            _product_rerank_score(product, query, vector_scores.get(product.product_id, 0.0)),
            product,
        )
        for product in products
    ]
    scored.sort(key=lambda item: (-item[0], item[1].price))
    return [product for _, product in scored]


def rerank_ranked_candidates(
    ranked_candidates: list[dict[str, Any]],
    query: str,
    constraints: dict[str, Any],
    evidence_by_product: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Second-pass recommendation reranker using query/product/evidence features."""
    reranked: list[dict[str, Any]] = []
    for item in ranked_candidates:
        product: Product = item["product"]
        rerank_score = _final_rerank_score(
            product=product,
            query=query,
            constraints=constraints,
            evidence=evidence_by_product.get(product.product_id, []),
        )
        updated = dict(item)
        breakdown = dict(updated.get("score_breakdown", {}))
        breakdown["rerank"] = round(rerank_score, 3)
        updated["score_breakdown"] = breakdown
        updated["rerank_score"] = round(rerank_score, 3)
        updated["score"] = round(float(updated.get("score", 0.0)) + rerank_score, 3)
        reranked.append(updated)
    reranked.sort(key=lambda item: (-item["score"], item["product"].price))
    return reranked


def rerank_review_evidence(
    evidence: list[dict[str, Any]],
    query: str,
    aspects: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    scored = []
    for item in evidence:
        score = float(item.get("retrieval_score", 0.0))
        score += _aspect_match_score(item.get("matched_aspects", {}), aspects)
        score += _query_overlap_score(query, item.get("content", "")) * 0.05
        if item.get("rating", 5) <= 3:
            score += 0.08
        updated = dict(item)
        updated["rerank_score"] = round(score, 4)
        updated["reranked"] = True
        scored.append((score, updated))
    scored.sort(key=lambda pair: (-pair[0], -int(pair[1].get("rating", 0))))
    return [item for _, item in scored[:top_k]]


def _product_rerank_score(product: Product, query: str, vector_score: float) -> float:
    score = vector_score * 0.45
    score += _query_overlap_score(query, product.searchable_text()) * 0.2
    if product.brand and product.brand.lower() in query.lower():
        score += 0.2
    return score


def _final_rerank_score(
    product: Product,
    query: str,
    constraints: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> float:
    score = _query_overlap_score(query, product.searchable_text()) * 0.08
    mentioned = [item.lower() for item in constraints.get("mentioned_products", [])]
    if any(name and name in product.title.lower() for name in mentioned):
        score += 0.25

    retrieval_scores = [
        float(item.get("rerank_score", item.get("retrieval_score", 0.0)))
        for item in evidence
    ]
    if retrieval_scores:
        score += min(sum(retrieval_scores) / len(retrieval_scores), 1.0) * 0.12

    negative_aspects = sum(
        1
        for item in evidence
        for sentiment in item.get("matched_aspects", {}).values()
        if sentiment == "negative"
    )
    score -= min(negative_aspects * 0.04, 0.16)
    return score


def _aspect_match_score(matched_aspects: dict[str, str], aspects: list[str]) -> float:
    score = 0.0
    for aspect in aspects:
        sentiment = matched_aspects.get(aspect)
        if sentiment == "positive":
            score += 0.12
        elif sentiment == "negative":
            score += 0.1
        elif sentiment:
            score += 0.06
    return score


def _query_overlap_score(query: str, text: str) -> float:
    query_terms = _terms(query)
    text_terms = _terms(text)
    if not query_terms or not text_terms:
        return 0.0
    hits = len(query_terms & text_terms)
    return hits / max(len(query_terms), 1)


def _terms(text: str) -> set[str]:
    normalized = text.lower().replace("，", " ").replace(",", " ")
    terms = {item.strip() for item in normalized.split() if len(item.strip()) >= 2}
    terms.update(char for char in normalized if "\u4e00" <= char <= "\u9fff")
    return terms
