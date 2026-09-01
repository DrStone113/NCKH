"""Standalone legacy/E4 comparison; intentionally absent from chatbot wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import settings
from modules.wger.exercise_prescription_policy import catalog_eligibility
from services.agent.tools.workout import suggest_workout
from services.workout_planner.contracts import ExerciseProfile, TrainingState, WorkoutRequest
from services.workout_planner.planner import PersonalizedWorkoutPlanner
from services.workout_planner.validator import WorkoutPlanValidator


SHADOW_COMPARISON_VERSION = "workout-shadow-comparison-v1.0.0"


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    version: str
    mode: str
    production_output_changed: bool
    legacy_error: str | None
    exercise_overlap_count: int
    exercise_overlap_rate: float
    legacy_equipment_violations: int
    e4_equipment_violations: int
    legacy_safety_violations: int
    e4_safety_violations: int
    history_responsiveness: dict[str, Any]
    goal_compatibility: dict[str, Any]
    estimated_duration: dict[str, Any]
    policy_compliance: dict[str, Any]
    catalog_eligibility: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__) if hasattr(self, "__dict__") else {
            field: getattr(self, field) for field in self.__dataclass_fields__
        }


def _legacy_ids(payload: dict[str, Any] | None) -> set[int]:
    if not payload:
        return set()
    result: set[int] = set()
    for item in payload.get("exercises") or []:
        value = item.get("wger_id") or item.get("id")
        if isinstance(value, int) and not isinstance(value, bool):
            result.add(value)
    return result


def run_shadow_comparison(
    profile: ExerciseProfile,
    state: TrainingState,
    request: WorkoutRequest,
    *,
    legacy_arguments: dict[str, Any],
    planner: PersonalizedWorkoutPlanner | None = None,
) -> ShadowComparison | None:
    """Run only when explicitly enabled; return no production response payload."""

    if not settings.workout_planner_shadow_enabled:
        return None
    engine = planner or PersonalizedWorkoutPlanner()
    plan = engine.plan(profile, state, request)
    legacy: dict[str, Any] | None = None
    legacy_error: str | None = None
    try:
        legacy = suggest_workout(**legacy_arguments)
    except ValueError as exc:
        legacy_error = str(exc)
    legacy_ids = _legacy_ids(legacy)
    e4_ids = {item.source_exercise_id for item in plan.exercises}
    overlap = legacy_ids & e4_ids
    available = {
        value.casefold()
        for value in (request.available_equipment_override if request.available_equipment_override is not None else profile.available_equipment)
    }
    aliases = {"none": "none (bodyweight exercise)", "bodyweight": "none (bodyweight exercise)", "dumbbells": "dumbbell"}
    available = {aliases.get(value, value) for value in available}
    legacy_equipment_violations = 0
    if legacy:
        for item in legacy.get("exercises") or []:
            required = {str(value).casefold() for value in item.get("equipment") or []}
            if required and not required.issubset(available) and legacy_arguments.get("equipment") != "any":
                legacy_equipment_violations += 1
    validation = WorkoutPlanValidator(engine._catalog).validate(plan, profile, state, request)  # noqa: SLF001 - audit path
    e4_equipment = sum(item.code == "EQUIPMENT_INCOMPATIBLE" for item in validation.violations)
    e4_safety = sum(item.code == "SAFETY_GATE_NOT_SUPPORTED" for item in validation.violations)
    catalog_by_source = {item["source_exercise_id"]: item for item in engine._catalog}  # noqa: SLF001
    legacy_catalog_violations = sum(
        source_id not in catalog_by_source
        or not catalog_eligibility(catalog_by_source[source_id])["structurally_prescription_eligible"]
        for source_id in legacy_ids
    )
    return ShadowComparison(
        SHADOW_COMPARISON_VERSION, "shadow", False, legacy_error, len(overlap),
        round(len(overlap) / max(1, len(legacy_ids | e4_ids)), 4),
        legacy_equipment_violations, e4_equipment,
        1 if legacy_error != "UNSAFE_TO_RECOMMEND_WORKOUT" and plan.safety_status.value != "SUPPORTED" and legacy is not None else 0,
        e4_safety,
        {"legacy_consumes_history": False, "e4_history_status": state.status.value, "e4_reason_codes": list(plan.history_reason_codes)},
        {"legacy_goal": legacy.get("goal") if legacy else None, "e4_goal": plan.goal},
        {"legacy_minutes": legacy.get("total_duration_minutes") if legacy else None, "e4_minutes": plan.estimated_duration, "budget": plan.duration_budget},
        {"legacy_validator_available": False, "e4_hard_violations": validation.hard_violation_count},
        {"legacy_hard_violations": legacy_catalog_violations, "e4_hard_violations": sum(item.code == "CATALOG_HARD_ELIGIBILITY_VIOLATION" for item in validation.violations)},
    )


__all__ = ["SHADOW_COMPARISON_VERSION", "ShadowComparison", "run_shadow_comparison"]
