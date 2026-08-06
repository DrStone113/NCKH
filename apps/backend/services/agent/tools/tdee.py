"""``calculate_tdee`` server-side tool.

Computes BMR (Mifflin-St Jeor), TDEE (BMR × activity factor) and a goal-adjusted
``daily_kcal`` for a :class:`UserProfile`.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §6.1 (UserProfile constraints).
- Requirements 4.7, 3.12 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract
--------
``calculate_tdee(profile)`` accepts either an already-validated
:class:`UserProfile` instance or a plain mapping (the LLM dispatches tool
arguments as JSON objects, which arrive here as ``dict``). Anything that does
not conform to §6.1 — missing required fields, values out of range, or an
unsupported enum literal for ``gender`` / ``activity_level`` / ``health_goal``
— results in ``ValueError("INVALID_PROFILE")``.

The tool is idempotent: same profile → same result. It is registered with
``side="server"`` and ``idempotent=True``.

Note
----
This module only *defines* :data:`TOOL_DESCRIPTOR`. Registration into the
shared :class:`ToolRegistry` happens centrally in task 12.1
(``register_server_tools``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from models.schemas import UserProfile
from services.agent.tool_registry import ToolDescriptor


# ---------------------------------------------------------------------------
# Constants — design.md §4.6 / requirement 4.7
# ---------------------------------------------------------------------------

#: Activity-level multipliers applied to BMR to produce TDEE.
ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

#: Health-goal adjustments applied to TDEE to produce ``daily_kcal``.
GOAL_ADJUSTMENTS: dict[str, float] = {
    "lose_weight": -500.0,
    "maintain": 0.0,
    "gain_muscle": 300.0,
}


# ---------------------------------------------------------------------------
# JSON Schema — must mirror UserProfile (design.md §6.1)
# ---------------------------------------------------------------------------

# Hand-written JSON Schema (rather than ``UserProfile.model_json_schema()``)
# so the wire format stays stable and small for the LLM. The constraints here
# MUST stay in sync with ``UserProfile``.
_USER_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 10, "maximum": 120},
        "gender": {"type": "string", "enum": ["male", "female"]},
        "height_cm": {"type": "number", "minimum": 100, "maximum": 250},
        "weight_kg": {"type": "number", "minimum": 30, "maximum": 300},
        "activity_level": {
            "type": "string",
            "enum": list(ACTIVITY_MULTIPLIERS.keys()),
        },
        "health_goal": {
            "type": "string",
            "enum": list(GOAL_ADJUSTMENTS.keys()),
        },
        "dietary_restrictions": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "required": [
        "user_id",
        "age",
        "gender",
        "height_cm",
        "weight_kg",
        "activity_level",
        "health_goal",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


def _mifflin_st_jeor_bmr(profile: UserProfile) -> float:
    """Return BMR in kcal/day per the Mifflin-St Jeor equation.

    Male:   ``10*kg + 6.25*cm − 5*age + 5``
    Female: ``10*kg + 6.25*cm − 5*age − 161``
    """
    base = 10.0 * profile.weight_kg + 6.25 * profile.height_cm - 5.0 * profile.age
    if profile.gender == "male":
        return base + 5.0
    # ``UserProfile.gender`` is constrained to {"male", "female"} by the
    # Pydantic Literal, so the only remaining branch is "female".
    return base - 161.0


def _coerce_to_profile(profile: UserProfile | Mapping[str, Any]) -> UserProfile:
    """Normalize ``profile`` to a validated :class:`UserProfile`.

    Anything that fails Pydantic validation (missing required field, out of
    range, wrong type, unknown enum literal) is converted into
    ``ValueError("INVALID_PROFILE")`` so callers see a single, stable error
    code regardless of the underlying validator detail.
    """
    if isinstance(profile, UserProfile):
        return profile
    if not isinstance(profile, Mapping):
        raise ValueError("INVALID_PROFILE")
    try:
        return UserProfile.model_validate(profile)
    except ValidationError as exc:  # pragma: no cover - exercised in tests
        raise ValueError("INVALID_PROFILE") from exc


def calculate_tdee(profile: UserProfile | Mapping[str, Any]) -> dict[str, float]:
    """Compute ``{bmr, tdee, daily_kcal}`` for ``profile``.

    Parameters
    ----------
    profile:
        Either a validated :class:`UserProfile` or a raw mapping that can be
        validated as one (the dispatcher passes ``call.arguments`` as a
        ``dict``).

    Returns
    -------
    dict
        ``{"bmr": float, "tdee": float, "daily_kcal": float}``.

    Raises
    ------
    ValueError
        With message ``"INVALID_PROFILE"`` whenever any §6.1 constraint is
        violated.
    """
    validated = _coerce_to_profile(profile)

    # The Pydantic ``Literal`` types already constrain these enums, but we
    # double-check here so the contract ("INVALID_PROFILE" on any out-of-range
    # input") is enforced even if a future schema change relaxes them.
    if validated.activity_level not in ACTIVITY_MULTIPLIERS:
        raise ValueError("INVALID_PROFILE")
    if validated.health_goal not in GOAL_ADJUSTMENTS:
        raise ValueError("INVALID_PROFILE")

    bmr = _mifflin_st_jeor_bmr(validated)
    tdee = bmr * ACTIVITY_MULTIPLIERS[validated.activity_level]
    daily_kcal = tdee + GOAL_ADJUSTMENTS[validated.health_goal]

    return {"bmr": bmr, "tdee": tdee, "daily_kcal": daily_kcal}


# ---------------------------------------------------------------------------
# Descriptor — consumed by ``register_server_tools`` (task 12.1)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="calculate_tdee",
    description=(
        "Tính BMR (Mifflin-St Jeor), TDEE (BMR × activity factor) và "
        "daily_kcal đã điều chỉnh theo health_goal cho một UserProfile."
    ),
    parameters_schema=_USER_PROFILE_SCHEMA,
    side="server",
    fn=calculate_tdee,
    idempotent=True,
)


__all__ = [
    "ACTIVITY_MULTIPLIERS",
    "GOAL_ADJUSTMENTS",
    "TOOL_DESCRIPTOR",
    "calculate_tdee",
]
