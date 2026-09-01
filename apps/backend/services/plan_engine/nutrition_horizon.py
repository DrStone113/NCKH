"""P2 multi-day nutrition planning state and deterministic variety scoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import ContextValue, PlanItem


@dataclass(frozen=True, slots=True)
class NutritionPlanningHorizonState:
    """Planned totals are explicitly separate from consumed nutrition state."""

    actual_consumed_nutrition: ContextValue
    planned_day_totals: Mapping[str, Mapping[str, float]]

    @classmethod
    def empty(cls, actual_consumed_nutrition: ContextValue) -> "NutritionPlanningHorizonState":
        return cls(actual_consumed_nutrition=actual_consumed_nutrition, planned_day_totals={})

    def add_planned_meal(self, item: PlanItem) -> "NutritionPlanningHorizonState":
        day = item.scheduled_date.isoformat()
        current = dict(self.planned_day_totals.get(day, {}))
        for source, target in (("total_calories", "calories"), ("total_protein", "protein"), ("total_carbs", "carbs"), ("total_fat", "fat")):
            value = item.content.get(source)
            if isinstance(value, (int, float)):
                current[target] = round(float(current.get(target, 0.0)) + float(value), 2)
        return NutritionPlanningHorizonState(
            actual_consumed_nutrition=self.actual_consumed_nutrition,
            planned_day_totals={**self.planned_day_totals, day: current},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "planned_day_totals": {day: dict(values) for day, values in sorted(self.planned_day_totals.items())},
            "actual_consumed_nutrition_source": self.actual_consumed_nutrition.source,
            "planned_is_not_consumed": True,
        }


def variety_score(items: Iterable[PlanItem]) -> dict[str, Any]:
    """Return transparent soft-target counts; it never creates substitutions."""

    meals = tuple(item for item in items if item.item_type.value == "MEAL")
    dish_ids = [str(item.canonical_refs.get("dish_id")) for item in meals if item.canonical_refs.get("dish_id")]
    proteins: list[str] = []
    patterns: list[str] = []
    for item in meals:
        content = item.content
        primary = content.get("primary_protein")
        if isinstance(primary, str) and primary:
            proteins.append(primary)
        tags = content.get("dietary_tags")
        objective = tags.get("objective") if isinstance(tags, Mapping) else None
        if isinstance(objective, list):
            patterns.append("|".join(sorted(str(value) for value in objective)))
    def repeats(values: list[str]) -> int:
        return sum(max(0, count - 1) for count in Counter(values).values())
    repetition = repeats(dish_ids) + repeats(proteins) + repeats(patterns)
    return {
        "classification": "SOFT_PLANNING_TARGET",
        "dish_repetitions": repeats(dish_ids),
        "primary_protein_repetitions": repeats(proteins),
        "major_dish_pattern_repetitions": repeats(patterns),
        "score": max(0, len(meals) * 3 - repetition),
        "user_preference_may_override": True,
        "no_substitution_invented": True,
    }


__all__ = ["NutritionPlanningHorizonState", "variety_score"]
