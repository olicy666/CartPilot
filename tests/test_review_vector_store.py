from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.data_loader import load_reviews
from backend.retrieval.review_vector_store import ReviewVectorStore
from backend.tools.retrieve_reviews import retrieve_product_reviews


class ReviewVectorStoreTest(unittest.TestCase):
    def test_retrieve_reviews_from_sqlite_vector_store(self) -> None:
        reviews = load_reviews()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = ReviewVectorStore.from_reviews(
                reviews,
                db_path=Path(tmp_dir) / "reviews.sqlite",
                rebuild=True,
            )
            evidence = retrieve_product_reviews(
                reviews=reviews,
                product_id="H004",
                aspects=["noise_cancellation", "comfort"],
                query="通勤 降噪 戴久舒服",
                vector_store=store,
            )

        self.assertTrue(evidence)
        self.assertEqual(evidence[0]["retrieval_source"], "sqlite_vector_store")
        self.assertIn(evidence[0]["review_id"], {"RH007", "RH008"})


if __name__ == "__main__":
    unittest.main()
