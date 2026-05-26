from __future__ import annotations

from backend.models import CategoryProfile


class CategoryRetriever:
    """Retrieve the most likely category profile from a user query."""

    def __init__(self, profiles: list[CategoryProfile]):
        self.profiles = profiles

    def detect(self, query: str) -> tuple[CategoryProfile | None, dict[str, float]]:
        normalized = query.lower()
        scores: dict[str, float] = {}

        for profile in self.profiles:
            score = 0.0
            if profile.display_name and profile.display_name in query:
                score += 4.0

            for alias in profile.aliases:
                if alias.lower() in normalized:
                    score += 3.0

            for dimension in profile.decision_dimensions:
                for keyword in dimension.keywords:
                    if keyword.lower() in normalized:
                        score += 0.8

            for scenario in profile.scenario_weights:
                if scenario.lower() in normalized:
                    score += 1.0

            for risk in profile.common_risks:
                if risk.lower() in normalized:
                    score += 0.5

            scores[profile.category_id] = round(score, 3)

        best_category = max(scores, key=scores.get) if scores else None
        if best_category is None or scores[best_category] <= 0:
            return None, scores

        profile = next(item for item in self.profiles if item.category_id == best_category)
        return profile, scores

    def list_categories(self) -> list[dict[str, str]]:
        return [
            {"category_id": profile.category_id, "display_name": profile.display_name}
            for profile in self.profiles
        ]
