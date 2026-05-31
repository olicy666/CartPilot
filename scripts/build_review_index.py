from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.data_loader import load_products, load_reviews
from backend.retrieval.product_vector_store import ProductVectorStore
from backend.retrieval.review_vector_store import ReviewVectorStore


def main() -> None:
    reviews = load_reviews()
    products = load_products()
    review_db_path = PROJECT_ROOT / ".cache" / "review_vectors.sqlite"
    product_db_path = PROJECT_ROOT / ".cache" / "product_vectors.sqlite"
    review_store = ReviewVectorStore.from_reviews(reviews, db_path=review_db_path, rebuild=True)
    product_store = ProductVectorStore.from_products(products, db_path=product_db_path, rebuild=True)
    print(f"built review vector index: {review_store.count()} reviews -> {review_db_path}")
    print(f"built product vector index: {product_store.count()} products -> {product_db_path}")


if __name__ == "__main__":
    main()
