"""Frozen nutrition calculations used only by historical research conditions.

This module intentionally preserves the pre-D2.1 production behaviour offered
to research condition D.  It must not import the production nutrition
calculator: future production policy versions must not change historical A/B/C
or condition-D observations.
"""

from __future__ import annotations

from types import MappingProxyType


RESEARCH_NUTRITION_POLICY_VERSION = "research-legacy-v1"

LEGACY_ACTIVITY_MULTIPLIERS = MappingProxyType(
    {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
)

LEGACY_GOAL_ADJUSTMENTS = MappingProxyType(
    {
        "lose_weight": -500.0,
        "maintain": 0.0,
        "gain_muscle": 300.0,
    }
)


def calculate_tdee_research_legacy_v1(
    *,
    age: int,
    sex: str,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> dict[str, float]:
    """Return the exact deterministic result used before production D2.1."""

    if sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    elif sex == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        raise ValueError("INVALID_RESEARCH_PROFILE")

    try:
        activity_factor = LEGACY_ACTIVITY_MULTIPLIERS[activity_level]
        goal_adjustment = LEGACY_GOAL_ADJUSTMENTS[goal]
    except KeyError as exc:
        raise ValueError("INVALID_RESEARCH_PROFILE") from exc

    tdee = bmr * activity_factor
    return {
        "bmr": bmr,
        "tdee": tdee,
        "daily_kcal": tdee + goal_adjustment,
    }


__all__ = [
    "LEGACY_ACTIVITY_MULTIPLIERS",
    "LEGACY_GOAL_ADJUSTMENTS",
    "RESEARCH_NUTRITION_POLICY_VERSION",
    "calculate_tdee_research_legacy_v1",
]
