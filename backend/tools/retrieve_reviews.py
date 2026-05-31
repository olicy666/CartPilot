from __future__ import annotations

from typing import Any

from backend.models import Review
from backend.retrieval.review_vector_store import ReviewVectorStore
from backend.tools.rerank import rerank_review_evidence


def retrieve_product_reviews(
    reviews: list[Review],
    product_id: str,
    aspects: list[str],
    top_k: int = 3,
    query: str | None = None,
    vector_store: ReviewVectorStore | None = None,
) -> list[dict[str, Any]]:
    if vector_store is not None:
        evidence = vector_store.search(
            query=query or " ".join(aspects),
            product_id=product_id,
            aspects=aspects,
            top_k=top_k,
        )
        return rerank_review_evidence(
            evidence=evidence,
            query=query or " ".join(aspects),
            aspects=aspects,
            top_k=top_k,
        )

    product_reviews = [review for review in reviews if review.product_id == product_id]
    scored = [
        (_score_review(review, aspects), review)
        for review in product_reviews
    ]
    scored.sort(key=lambda item: (-item[0], -item[1].rating))

    evidence: list[dict[str, Any]] = []
    for score, review in scored[:top_k]:
        if score <= 0 and aspects:
            continue
        evidence.append(
            {
                "review_id": review.review_id,
                "rating": review.rating,
                "content": review.content,
                "matched_aspects": {
                    aspect: sentiment
                    for aspect, sentiment in review.aspects.items()
                    if not aspects or aspect in aspects
                },
            }
        )
    return rerank_review_evidence(
        evidence=evidence,
        query=query or " ".join(aspects),
        aspects=aspects,
        top_k=top_k,
    )


def _score_review(review: Review, aspects: list[str]) -> float:
    if not aspects:
        return float(review.rating)

    score = 0.0
    for aspect in aspects:
        if aspect in review.aspects:
            score += 2.0
        if aspect.replace("_", " ") in review.content.lower():
            score += 0.5
    return score + review.rating * 0.1
