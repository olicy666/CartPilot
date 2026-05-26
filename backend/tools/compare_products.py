from __future__ import annotations

from typing import Any

from backend.models import Product


def compare_products(
    products: list[Product],
    dimensions: list[str],
) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    for product in products:
        row = {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "price": product.price,
        }
        for dimension in dimensions:
            row[dimension] = product.specs.get(dimension, "未知")
        table.append(row)
    return table
