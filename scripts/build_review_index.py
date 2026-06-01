from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.data_loader import load_products, load_reviews
from backend.retrieval.vector_store_factory import (
    build_product_vector_store,
    build_review_vector_store,
)


def main() -> None:
    reviews = load_reviews()
    products = load_products()
    cache_dir = PROJECT_ROOT / ".cache"
    review_store = build_review_vector_store(reviews, cache_dir=cache_dir, rebuild=True)
    product_store = build_product_vector_store(products, cache_dir=cache_dir, rebuild=True)
    print(
        f"built review vector index: {review_store.count()} reviews "
        f"with {type(review_store).__name__}"
    )
    print(
        f"built product vector index: {product_store.count()} products "
        f"with {type(product_store).__name__}"
    )


if __name__ == "__main__":
    main()
