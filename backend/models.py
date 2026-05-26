from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


def to_plain_dict(value: Any) -> Any:
    """Convert dataclasses and nested containers into JSON-friendly values."""
    if is_dataclass(value):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class CategoryDimension:
    name: str
    label: str
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryDimension":
        return cls(
            name=data["name"],
            label=data.get("label", data["name"]),
            keywords=list(data.get("keywords", [])),
        )


@dataclass(frozen=True)
class CategoryProfile:
    category_id: str
    display_name: str
    aliases: list[str]
    decision_dimensions: list[CategoryDimension]
    required_specs: list[str]
    scenario_weights: dict[str, dict[str, float]]
    common_risks: list[str]

    @property
    def dimension_names(self) -> list[str]:
        return [dimension.name for dimension in self.decision_dimensions]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryProfile":
        return cls(
            category_id=data["category_id"],
            display_name=data["display_name"],
            aliases=list(data.get("aliases", [])),
            decision_dimensions=[
                CategoryDimension.from_dict(item)
                for item in data.get("decision_dimensions", [])
            ],
            required_specs=list(data.get("required_specs", [])),
            scenario_weights=dict(data.get("scenario_weights", {})),
            common_risks=list(data.get("common_risks", [])),
        )


@dataclass(frozen=True)
class Product:
    product_id: str
    title: str
    category: str
    brand: str
    price: float
    specs: dict[str, Any]
    description: str
    tags: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Product":
        return cls(
            product_id=data["product_id"],
            title=data["title"],
            category=data["category"],
            brand=data.get("brand", ""),
            price=float(data.get("price", 0)),
            specs=dict(data.get("specs", {})),
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
        )

    def searchable_text(self) -> str:
        parts = [self.title, self.brand, self.description, *self.tags]
        parts.extend(str(value) for value in self.specs.values())
        return " ".join(parts).lower()


@dataclass(frozen=True)
class Review:
    review_id: str
    product_id: str
    rating: int
    content: str
    aspects: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Review":
        return cls(
            review_id=data["review_id"],
            product_id=data["product_id"],
            rating=int(data.get("rating", 0)),
            content=data.get("content", ""),
            aspects=dict(data.get("aspects", {})),
        )


@dataclass
class TraceStep:
    name: str
    reason: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]


@dataclass
class AgentResponse:
    query: str
    answer: str
    intent: dict[str, Any]
    purchase_brief: dict[str, Any]
    comparison_table: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    trace: list[TraceStep]
    self_check: dict[str, Any]
    memory_update: dict[str, Any]
    llm_meta: dict[str, Any]
    workflow_status: str

    def to_dict(self) -> dict[str, Any]:
        return to_plain_dict(self)
