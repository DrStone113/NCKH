"""Canonical nutrition calculation exposed as the ``calculate_tdee`` tool.

The historical tool name is retained for API compatibility. All production
nutrition values are delegated to ``nutrition-policy-v1.0.1``; research adapters
use their separately frozen legacy implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from models.schemas import UserProfile
from services.agent.tool_registry import ToolDescriptor
from services.nutrition.calculator import (
    CanonicalNutritionInput,
    CanonicalValue,
    InputStatus,
    calculate_canonical_nutrition,
)
from services.nutrition.registry import POLICY


ACTIVITY_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {key: float(value) for key, value in POLICY["activity"]["factors"].items()}
)
HEALTH_GOALS = frozenset({"lose_weight", "maintain", "gain_muscle"})


_USER_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 10, "maximum": 120},
        "gender": {"type": ["string", "null"]},
        "equation_sex": {
            "type": ["string", "null"],
            "enum": ["male", "female", None],
            "description": "Explicit Mifflin input; never inferred from gender.",
        },
        "nutrition_safety_profile": {
            "type": "object",
            "properties": {
                field: {
                    "type": "string",
                    "enum": ["YES", "NO", "UNKNOWN", "NOT_PROVIDED"],
                }
                for field in (
                    "pregnancy",
                    "lactation",
                    "eating_disorder_risk_or_history",
                    "serious_renal_condition",
                    "fluid_restricted_cardiac_condition",
                    "clinically_complex_metabolic_condition",
                )
            },
            "additionalProperties": False,
        },
        "height_cm": {"type": "number", "minimum": 100, "maximum": 250},
        "weight_kg": {"type": "number", "minimum": 30, "maximum": 300},
        "activity_level": {
            "type": "string",
            "enum": list(ACTIVITY_MULTIPLIERS.keys()),
        },
        "health_goal": {"type": "string", "enum": sorted(HEALTH_GOALS)},
        "dietary_restrictions": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "required": [
        "user_id",
        "age",
        "height_cm",
        "weight_kg",
        "activity_level",
        "health_goal",
    ],
    "additionalProperties": False,
}


def _coerce_to_profile(profile: UserProfile | Mapping[str, Any]) -> UserProfile:
    if isinstance(profile, UserProfile):
        return profile
    if not isinstance(profile, Mapping):
        raise ValueError("INVALID_PROFILE")
    try:
        return UserProfile.model_validate(profile)
    except ValidationError as exc:
        raise ValueError("INVALID_PROFILE") from exc


def calculate_tdee(profile: UserProfile | Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical nutrition state plus legacy response aliases.

    ``bmr``, ``tdee`` and ``daily_kcal`` remain as aliases for existing API
    consumers. They are outputs of the canonical calculator, never parallel
    formula implementations. Unsupported or safety-gated targets are ``None``.
    """
    validated = _coerce_to_profile(profile)
    if validated.activity_level not in ACTIVITY_MULTIPLIERS:
        raise ValueError("INVALID_PROFILE")
    if validated.health_goal not in HEALTH_GOALS:
        raise ValueError("INVALID_PROFILE")

    state = calculate_canonical_nutrition(
        CanonicalNutritionInput(
            age=CanonicalValue.known(validated.age, source="user_profile"),
            equation_sex=(
                CanonicalValue.known(
                    validated.equation_sex,
                    source="user_profile.equation_sex",
                )
                if validated.equation_sex is not None
                else CanonicalValue.unavailable(
                    InputStatus.MISSING,
                    source="user_profile.equation_sex",
                )
            ),
            height_cm=CanonicalValue.known(
                validated.height_cm, source="user_profile"
            ),
            weight_kg=CanonicalValue.known(
                validated.weight_kg, source="user_profile"
            ),
            activity_level=CanonicalValue.known(
                validated.activity_level, source="user_profile"
            ),
            health_goal=CanonicalValue.known(
                validated.health_goal, source="user_profile"
            ),
            safety_profile=validated.nutrition_safety_profile.to_canonical(),
        )
    )
    result = state.to_dict()
    result.update(
        {
            "bmr": result["estimated_rmr_kcal_per_day"],
            "tdee": result["estimated_tdee_kcal_per_day"],
            "daily_kcal": result["calorie_target_kcal_per_day"],
            "daily_protein": (
                result["protein"]["planning_g_per_day"]
                if isinstance(result.get("protein"), dict)
                else None
            ),
        }
    )
    return result


TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="calculate_tdee",
    description=(
        "Tính trạng thái dinh dưỡng chuẩn theo nutrition-policy-v1.0.1, gồm BMI, "
        "RMR ước tính, TDEE ước tính, mục tiêu năng lượng và dải đa lượng."
    ),
    parameters_schema=_USER_PROFILE_SCHEMA,
    side="server",
    fn=calculate_tdee,
    idempotent=True,
)


__all__ = [
    "ACTIVITY_MULTIPLIERS",
    "HEALTH_GOALS",
    "TOOL_DESCRIPTOR",
    "calculate_tdee",
]
