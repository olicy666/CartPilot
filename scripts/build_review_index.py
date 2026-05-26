from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.data_loader import load_reviews
from backend.retrieval.review_vector_store import ReviewVectorStore


def main() -> None:
    reviews = load_reviews()
    db_path = PROJECT_ROOT / ".cache" / "review_vectors.sqlite"
    store = ReviewVectorStore.from_reviews(reviews, db_path=db_path, rebuild=True)
    print(f"built review vector index: {store.count()} reviews -> {db_path}")


if __name__ == "__main__":
    main()
