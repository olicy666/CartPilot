from __future__ import annotations

import unittest

from backend.data_loader import load_products
from backend.tools.filter_constraints import filter_by_constraints


class FilterConstraintsTest(unittest.TestCase):
    def test_filter_budget_and_excluded_form_factor(self) -> None:
        products = [item for item in load_products() if item.category == "headphones"]
        constraints = {
            "budget_max": 2000,
            "exclude_specs": {"form_factor": ["in_ear"]},
            "must_dimensions": ["noise_cancellation"],
        }

        kept, rejected = filter_by_constraints(products, constraints)

        self.assertTrue(kept)
        self.assertTrue(all(item.price <= 2000 for item in kept))
        self.assertTrue(all(item.specs["form_factor"] != "in_ear" for item in kept))
        self.assertTrue(any(item["product_id"] == "H003" for item in rejected))


if __name__ == "__main__":
    unittest.main()
