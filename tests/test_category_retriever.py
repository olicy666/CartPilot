from __future__ import annotations

import unittest

from backend.data_loader import load_category_profiles
from backend.retrieval.category_retriever import CategoryRetriever


class CategoryRetrieverTest(unittest.TestCase):
    def test_detect_laptop_from_deep_learning_query(self) -> None:
        retriever = CategoryRetriever(load_category_profiles())
        profile, scores = retriever.detect("预算8000，想买一台适合跑深度学习和写代码的笔记本")

        self.assertIsNotNone(profile)
        self.assertEqual(profile.category_id, "laptop")
        self.assertGreater(scores["laptop"], 0)


if __name__ == "__main__":
    unittest.main()
