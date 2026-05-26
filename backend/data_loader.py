from __future__ import annotations

import json
from pathlib import Path

from backend.models import CategoryProfile, Product, Review


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def load_json(filename: str, data_dir: Path | None = None) -> list[dict]:
    base_dir = data_dir or DEFAULT_DATA_DIR
    path = base_dir / filename
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_category_profiles(data_dir: Path | None = None) -> list[CategoryProfile]:
    base_dir = data_dir or DEFAULT_DATA_DIR
    profiles_by_id = {
        item["category_id"]: item
        for item in load_json("category_profiles.json", base_dir)
    }

    skill_dir = base_dir / "category_skills"
    if skill_dir.exists():
        for path in sorted(skill_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as file:
                item = json.load(file)
            profiles_by_id[item["category_id"]] = item

    return [
        CategoryProfile.from_dict(item)
        for item in profiles_by_id.values()
    ]


def load_products(data_dir: Path | None = None) -> list[Product]:
    return [Product.from_dict(item) for item in load_json("products.json", data_dir)]


def load_reviews(data_dir: Path | None = None) -> list[Review]:
    return [Review.from_dict(item) for item in load_json("reviews.json", data_dir)]
