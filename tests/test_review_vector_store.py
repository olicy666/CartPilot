from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.data_loader import load_reviews
from backend.data_loader import load_products
from backend.retrieval.product_vector_store import ProductVectorStore
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

    def test_product_vector_store_retrieves_by_category(self) -> None:
        products = load_products()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = ProductVectorStore.from_products(
                products,
                db_path=Path(tmp_dir) / "products.sqlite",
                rebuild=True,
            )
            hits = store.search(
                query="通勤 降噪 舒适 耳机",
                category="headphones",
                top_k=3,
            )

        self.assertTrue(hits)
        self.assertTrue(all(item["category"] == "headphones" for item in hits))
        self.assertEqual(hits[0]["retrieval_source"], "product_vector_store")


if __name__ == "__main__":
    unittest.main()
