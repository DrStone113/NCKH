"""Deterministic hard/soft validation for E4.0 WorkoutPlan."""

from __future__ import annotations

from typing import Any

from modules.wger.exercise_prescription_policy import catalog_eligibility, load_policy, substitution_decision
from services.workout_planner.contracts import (
    ApplicabilityStatus,
    ExerciseProfile,
    PlanViolation,
    ProgressionStatus,
    StateStatus,
    TrainingExperience,
    TrainingState,
    ValidationResult,
    WorkoutPlan,
    WorkoutRequest,
)


class WorkoutPlanValidator:
    def __init__(self, catalog: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
        self._catalog = tuple(catalog)
        self._by_id = {item["exercise_id"]: item for item in catalog}
        self._policy = load_policy()

    @staticmethod
    def _violation(rule: str, severity: str, code: str, *, exercise_id: str | None = None, observed: Any = None, expected: Any = None) -> PlanViolation:
        return PlanViolation(rule, severity, code, exercise_id, observed, expected)

    def validate(
        self, plan: WorkoutPlan, profile: ExerciseProfile, state: TrainingState, request: WorkoutRequest,
    ) -> ValidationResult:
        violations: list[PlanViolation] = []
        if plan.safety_status != ApplicabilityStatus.SUPPORTED:
            violations.append(self._violation("E4_SAFETY_GATE", "HARD", "SAFETY_GATE_NOT_SUPPORTED", observed=plan.safety_status.value, expected="SUPPORTED"))
        available = {
            value.strip().casefold()
            for value in (request.available_equipment_override if request.available_equipment_override is not None else profile.available_equipment)
        }
        aliases = {"none": "none (bodyweight exercise)", "bodyweight": "none (bodyweight exercise)", "bodyweight only": "none (bodyweight exercise)", "dumbbells": "dumbbell", "resistance bands": "resistance band"}
        available = {aliases.get(value, value) for value in available}
        excluded = {value.strip().casefold() for value in profile.exercise_exclusions + request.exercise_exclude}
        seen: set[str] = set()
        goal_profile = self._policy["goal_profiles"].get(plan.goal or "")
        operational = profile.training_experience.value if profile.training_experience != TrainingExperience.UNKNOWN else "NOVICE"
        for exercise in plan.exercises:
            item = self._by_id.get(exercise.canonical_exercise_id)
            if item is None:
                violations.append(self._violation("E4_CATALOG_ID", "HARD", "UNKNOWN_CANONICAL_EXERCISE", exercise_id=exercise.canonical_exercise_id))
                continue
            if exercise.canonical_exercise_id in seen:
                violations.append(self._violation("E4_NO_DUPLICATES", "HARD", "DUPLICATE_EXERCISE", exercise_id=exercise.canonical_exercise_id))
            seen.add(exercise.canonical_exercise_id)
            if not catalog_eligibility(item)["structurally_prescription_eligible"]:
                violations.append(self._violation("E4_CATALOG_ELIGIBILITY", "HARD", "CATALOG_HARD_ELIGIBILITY_VIOLATION", exercise_id=exercise.canonical_exercise_id))
            required = {value.casefold() for value in exercise.required_equipment}
            if not required or not required.issubset(available):
                violations.append(self._violation("E4_EQUIPMENT", "HARD", "EQUIPMENT_INCOMPATIBLE", exercise_id=exercise.canonical_exercise_id, observed=sorted(required), expected=sorted(available)))
            names = {str(item.get("name_en") or "").casefold(), str(item.get("name_vi") or "").casefold(), item["exercise_id"].casefold(), str(item["source_exercise_id"])}
            if names & excluded:
                violations.append(self._violation("E4_EXCLUSION", "HARD", "EXCLUDED_EXERCISE_SELECTED", exercise_id=exercise.canonical_exercise_id))
            if (item.get("difficulty") or {}).get("value") == "ADVANCED" and profile.training_experience != TrainingExperience.EXPERIENCED:
                violations.append(self._violation("E4_EXPERIENCE", "HARD", "EXPERIENCE_RESTRICTION_VIOLATION", exercise_id=exercise.canonical_exercise_id))
            if goal_profile:
                sets_rule = goal_profile.get("sets_per_exercise") or {}
                expected_sets = sets_rule.get(operational) if isinstance(sets_rule, dict) else None
                if expected_sets and not expected_sets[0] <= exercise.prescription.sets <= expected_sets[1]:
                    violations.append(self._violation("E3_SETS", "HARD", "SETS_OUTSIDE_POLICY", exercise_id=exercise.canonical_exercise_id, observed=exercise.prescription.sets, expected=expected_sets))
                reps_rule = goal_profile.get("repetition_range")
                expected_reps = reps_rule.get(operational) if isinstance(reps_rule, dict) else reps_rule
                if (tuple(expected_reps) if expected_reps else None) != exercise.prescription.rep_range:
                    violations.append(self._violation("E3_REPS", "HARD", "REPS_OUTSIDE_POLICY", exercise_id=exercise.canonical_exercise_id, observed=exercise.prescription.rep_range, expected=expected_reps))
                valid_rests = [tuple(value) for value in (goal_profile.get("rest_seconds") or {}).values()]
                if exercise.prescription.rest_range_seconds not in valid_rests:
                    violations.append(self._violation("E3_REST", "HARD", "REST_OUTSIDE_POLICY", exercise_id=exercise.canonical_exercise_id, observed=exercise.prescription.rest_range_seconds, expected=valid_rests))
                rir_rule = goal_profile.get("target_rir") or {}
                expected_rir = rir_rule.get(operational) if isinstance(rir_rule, dict) else rir_rule
                if (tuple(expected_rir) if expected_rir else None) != exercise.prescription.effort_target_rir:
                    violations.append(self._violation("E3_RIR", "HARD", "EFFORT_OUTSIDE_POLICY", exercise_id=exercise.canonical_exercise_id, observed=exercise.prescription.effort_target_rir, expected=expected_rir))
            if exercise.progression_status != ProgressionStatus.PROGRESSION_UNAVAILABLE and state.exercise_performance_history.status != StateStatus.KNOWN:
                violations.append(self._violation("E3_1_DOUBLE_PROGRESSION_LOAD", "HARD", "UNSUPPORTED_PROGRESSION", exercise_id=exercise.canonical_exercise_id))
            if exercise.substitution.status == "AVAILABLE":
                source = item
                equipment_ids = {eq["id"] for row in self._catalog for eq in row.get("equipment") or [] if eq["name"].casefold() in available}
                for candidate_id in exercise.substitution.candidate_exercise_ids:
                    candidate = self._by_id.get(candidate_id)
                    decision = substitution_decision(source, candidate or {}, available_equipment_ids=equipment_ids)
                    if decision["decision"] != "ELIGIBLE_AFTER_SAFETY_AND_PREFERENCE_CHECK":
                        violations.append(self._violation("E3_1_SUBSTITUTION_DECISION", "HARD", "INVALID_SUBSTITUTION", exercise_id=candidate_id, observed=decision))
        if plan.duration_budget is not None and plan.estimated_duration > plan.duration_budget:
            violations.append(self._violation("E4_TIME_BUDGET", "HARD", "TIME_BUDGET_EXCEEDED", observed=plan.estimated_duration, expected=plan.duration_budget))
        if plan.estimated_energy_expenditure.estimated_energy_expenditure is not None:
            energy = plan.estimated_energy_expenditure
            if energy.source != "ADULT_COMPENDIUM_2024" or energy.mapping_status not in {"DIRECT_SUPPORTED_MAPPING", "APP_CURATED_MAPPING"}:
                violations.append(self._violation("E4_ENERGY_PROVENANCE", "HARD", "UNSUPPORTED_CALORIE_ESTIMATE", observed=energy.to_dict()))
        movements = {exercise.movement_pattern for exercise in plan.exercises}
        if len(plan.exercises) >= 4 and len(movements) < 2:
            violations.append(self._violation("E4_MOVEMENT_VARIETY", "SOFT", "LOW_MOVEMENT_VARIETY", observed=sorted(movements), expected="PRODUCT_HEURISTIC_NOT_SAFETY_RULE"))
        hard = sum(item.severity == "HARD" for item in violations)
        soft = len(violations) - hard
        ready = hard == 0 and bool(plan.exercises) and plan.time_budget_status.value not in {
            "INSUFFICIENT_TIME", "CLARIFICATION_REQUIRED"
        }
        return ValidationResult(ready, tuple(violations), hard, soft)


__all__ = ["WorkoutPlanValidator"]
