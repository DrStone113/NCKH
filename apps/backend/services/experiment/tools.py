"""Explicit deterministic tool allowlists for versioned research protocols."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from services.agent.tool_registry import ToolDescriptor, ToolRegistry
from services.agent.tools.tdee import calculate_tdee as calculate_canonical_tdee
from services.experiment.config import (
    NUTRITION_ABLATION_PROTOCOL_ID,
    ExperimentConfig,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.legacy_nutrition import (
    calculate_tdee_research_legacy_v1,
)


CALCULATE_TDEE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "age": {"type": "integer", "minimum": 18, "maximum": 120},
        "sex": {"type": "string", "enum": ["male", "female"]},
        "height_cm": {"type": "number", "minimum": 100, "maximum": 250},
        "weight_kg": {"type": "number", "minimum": 30, "maximum": 300},
        "activity_level": {
            "type": "string",
            "enum": ["sedentary", "light", "moderate", "active", "very_active"],
        },
        "goal": {
            "type": "string",
            "enum": ["lose_weight", "maintain", "gain_muscle"],
        },
    },
    "required": [
        "age",
        "sex",
        "height_cm",
        "weight_kg",
        "activity_level",
        "goal",
    ],
    "additionalProperties": False,
}


def _calculate_tdee_for_research(
    *,
    age: int,
    sex: str,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> dict[str, float]:
    """Execute the immutable pre-D2.1 research nutrition policy."""

    return calculate_tdee_research_legacy_v1(
        age=age,
        sex=sex,
        height_cm=height_cm,
        weight_kg=weight_kg,
        activity_level=activity_level,
        goal=goal,
    )


def _calculate_canonical_tdee_for_ablation(
    *,
    age: int,
    sex: str,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> dict[str, Any]:
    """Adapt the stable research schema to canonical nutrition-policy-v1.0.1."""

    return calculate_canonical_tdee(
        {
            "user_id": "nutrition-ablation-fixture",
            "age": age,
            "gender": sex,
            "equation_sex": sex,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "activity_level": activity_level,
            "health_goal": goal,
            "dietary_restrictions": [],
        }
    )


LEGACY_CALCULATE_TDEE_DESCRIPTOR = ToolDescriptor(
    name="calculate_tdee",
    description=(
        "Deterministically calculate the frozen legacy Mifflin-St Jeor BMR, "
        "activity-adjusted TDEE, and goal-adjusted daily calorie value."
    ),
    parameters_schema=CALCULATE_TDEE_SCHEMA,
    side="server",
    fn=_calculate_tdee_for_research,
    idempotent=True,
)

CANONICAL_CALCULATE_TDEE_DESCRIPTOR = ToolDescriptor(
    name="calculate_tdee",
    description=(
        "Deterministically calculate canonical nutrition-policy-v1.0.1 state, "
        "including BMI, estimated RMR/TDEE, safety status, calorie target, "
        "protein planning, and fluid guidance from explicit inputs."
    ),
    parameters_schema=CALCULATE_TDEE_SCHEMA,
    side="server",
    fn=_calculate_canonical_tdee_for_ablation,
    idempotent=True,
)

# Backwards-compatible export for historical callers. New S0-S3 arms select
# the canonical descriptor inside ``build_research_tool_registry``.
CALCULATE_TDEE_DESCRIPTOR = LEGACY_CALCULATE_TDEE_DESCRIPTOR


def build_research_tool_registry(config: ExperimentConfig) -> ToolRegistry:
    """Build a fresh registry containing only tools authorized by condition."""

    registry = ToolRegistry()
    if config.nutrition_tools_enabled:
        descriptor = (
            CANONICAL_CALCULATE_TDEE_DESCRIPTOR
            if config.protocol_id == NUTRITION_ABLATION_PROTOCOL_ID
            else LEGACY_CALCULATE_TDEE_DESCRIPTOR
        )
        registry.register(descriptor)
    return registry


async def execute_research_tool(
    registry: ToolRegistry, name: str, arguments: dict[str, Any]
) -> Any:
    """Validate and run one allowlisted pure server tool."""

    descriptor = registry.get(name)
    if descriptor is None:
        raise ExperimentError("EXPERIMENT_TOOL_NOT_ALLOWED", name)
    valid, error = registry.validate(name, arguments)
    if not valid:
        raise ExperimentError(error or "INVALID_ARGS", name)
    if descriptor.side != "server" or descriptor.fn is None or not descriptor.idempotent:
        raise ExperimentError("EXPERIMENT_TOOL_NOT_DETERMINISTIC", name)

    try:
        if inspect.iscoroutinefunction(descriptor.fn):
            return await descriptor.fn(**arguments)
        return await asyncio.to_thread(descriptor.fn, **arguments)
    except ExperimentError:
        raise
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_TOOL_FAILED", f"{name}: {safe_error_detail(exc)}"
        ) from exc


__all__ = [
    "CANONICAL_CALCULATE_TDEE_DESCRIPTOR",
    "CALCULATE_TDEE_DESCRIPTOR",
    "CALCULATE_TDEE_SCHEMA",
    "LEGACY_CALCULATE_TDEE_DESCRIPTOR",
    "build_research_tool_registry",
    "execute_research_tool",
]
