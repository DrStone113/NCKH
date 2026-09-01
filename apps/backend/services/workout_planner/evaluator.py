"""Engineering-only E4.0 invariant, sensitivity, and latency metrics."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any

from services.workout_planner.contracts import ApplicabilityStatus, ProgressionStatus, StateStatus
from services.workout_planner.development_scenarios import (
    FIXED_NOW,
    DevelopmentScenario,
    development_scenarios,
    irrelevant_input_pairs,
    personalization_pairs,
)
from services.workout_planner.history import normalize_training_history
from services.workout_planner.planner import PersonalizedWorkoutPlanner, build_session_requirement, evaluate_safety
from services.workout_planner.validator import WorkoutPlanValidator
from services.agent.tools.workout import suggest_workout
from modules.wger.exercise_prescription_policy import catalog_eligibility, load_policy


EVALUATION_VERSION = "workout-planner-evaluation-v1.0.0"


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: DevelopmentScenario
    state: Any
    plan: Any
    requirement: Any
    validation: Any
    latency_ms: float
    oracle_failures: tuple[str, ...]


def _run(engine: PersonalizedWorkoutPlanner, scenario: DevelopmentScenario) -> ScenarioResult:
    missed = 1 if "MISSED_SESSION" in scenario.request.temporary_preferences else None
    state = normalize_training_history(
        scenario.history_records,
        computed_at=FIXED_NOW,
        source_status=scenario.history_source_status,
        missed_sessions=missed,
    )
    safety = evaluate_safety(scenario.profile)
    requirement = build_session_requirement(scenario.profile, state, scenario.request, safety)
    started = time.perf_counter()
    plan = engine.plan(scenario.profile, state, scenario.request)
    latency = (time.perf_counter() - started) * 1000
    validator = WorkoutPlanValidator(engine._catalog)  # noqa: SLF001 - evaluator owns the same frozen catalog
    validation = validator.validate(plan, scenario.profile, state, scenario.request)
    failures: list[str] = []
    oracle = scenario.oracle
    if safety.status != oracle.safety_status:
        failures.append("SAFETY_STATUS")
    if requirement.status != oracle.planning_status:
        failures.append("PLANNING_STATUS")
    if plan.goal != oracle.goal:
        failures.append("GOAL")
    if plan.time_budget_status.value not in oracle.allowed_time_statuses:
        failures.append("TIME_STATUS")
    selected_names = {
        str(item.canonical_exercise_id).casefold() for item in plan.exercises
    } | {str(item.source_exercise_id) for item in plan.exercises}
    if any(value.casefold() in selected_names for value in oracle.hard_exclusions):
        failures.append("HARD_EXCLUSION")
    history_observed = "HISTORY_AVAILABLE" if state.status == StateStatus.KNOWN else "HISTORY_UNAVAILABLE"
    if history_observed != oracle.history_behavior:
        failures.append("HISTORY_BEHAVIOR")
    progression_values = {item.progression_status.value for item in plan.exercises}
    if oracle.progression == "PROGRESSION_AVAILABLE" and "PROGRESSION_AVAILABLE" not in progression_values:
        failures.append("PROGRESSION")
    elif oracle.progression == "REGRESSION" and "REGRESSION" not in progression_values:
        failures.append("PROGRESSION")
    elif oracle.progression == "PROGRESSION_UNAVAILABLE" and any(
        value != "PROGRESSION_UNAVAILABLE" for value in progression_values
    ):
        failures.append("PROGRESSION")
    if oracle.planning_status == ApplicabilityStatus.SUPPORTED and validation.hard_violation_count:
        failures.append("HARD_POLICY_INVARIANT")
    if oracle.safety_status != ApplicabilityStatus.SUPPORTED and plan.exercises:
        failures.append("UNSAFE_EXERCISES_EMITTED")
    return ScenarioResult(scenario, state, plan, requirement, validation, latency, tuple(failures))


def _fingerprint(plan: Any, kind: str) -> Any:
    exercises = tuple(item.canonical_exercise_id for item in plan.exercises)
    prescriptions = tuple(
        (item.prescription.sets, item.prescription.rep_range, item.prescription.rest_range_seconds, item.prescription.effort_target_rir)
        for item in plan.exercises
    )
    if kind == "EXERCISES":
        return exercises
    if kind == "PRESCRIPTION":
        return plan.goal, prescriptions
    if kind == "HISTORY_OR_EXERCISES":
        return plan.history_reason_codes, exercises
    if kind == "DURATION_OR_COUNT":
        return plan.duration_budget, plan.estimated_duration, len(exercises)
    if kind == "SAFETY":
        return plan.safety_status, exercises
    return plan.to_dict()


def evaluate_development_dataset() -> dict[str, Any]:
    engine = PersonalizedWorkoutPlanner()
    scenarios = development_scenarios()
    results = [_run(engine, scenario) for scenario in scenarios]
    deterministic = 0
    for result in results:
        repeated = engine.plan(result.scenario.profile, result.state, result.scenario.request)
        if repeated.to_dict() == result.plan.to_dict():
            deterministic += 1
    sensitivity_success = 0
    sensitivity_details = []
    for pair in personalization_pairs():
        left = _run(engine, pair.left).plan
        right = _run(engine, pair.right).plan
        changed = _fingerprint(left, pair.expected_change) != _fingerprint(right, pair.expected_change)
        sensitivity_success += int(changed)
        sensitivity_details.append({"pair_id": pair.pair_id, "passed": changed, "expected_change": pair.expected_change})
    stability_success = 0
    stability_details = []
    for pair in irrelevant_input_pairs():
        left = _run(engine, pair.left).plan
        right = _run(engine, pair.right).plan
        stable = (
            tuple(item.canonical_exercise_id for item in left.exercises), left.goal, left.estimated_duration
        ) == (
            tuple(item.canonical_exercise_id for item in right.exercises), right.goal, right.estimated_duration
        )
        stability_success += int(stable)
        stability_details.append({"pair_id": pair.pair_id, "passed": stable})
    all_violations = [violation for result in results for violation in result.validation.violations]
    safety_violations = sum(
        result.scenario.oracle.safety_status != ApplicabilityStatus.SUPPORTED and bool(result.plan.exercises)
        for result in results
    )
    equipment_violations = sum(item.code == "EQUIPMENT_INCOMPATIBLE" for item in all_violations)
    catalog_violations = sum(item.code == "CATALOG_HARD_ELIGIBILITY_VIOLATION" for item in all_violations)
    progression_violations = sum(item.code == "UNSUPPORTED_PROGRESSION" for item in all_violations)
    energy_violations = sum(item.code == "UNSUPPORTED_CALORIE_ESTIMATE" for item in all_violations)
    time_violations = sum(item.code == "TIME_BUDGET_EXCEEDED" for item in all_violations)
    policy_hard_violations = sum(
        item.severity == "HARD" and item.code not in {"SAFETY_GATE_NOT_SUPPORTED"}
        for item in all_violations
    )
    history_correct = sum("HISTORY_BEHAVIOR" not in result.oracle_failures for result in results)
    progression_correct = sum("PROGRESSION" not in result.oracle_failures for result in results)
    substitution_violations = sum(item.code == "INVALID_SUBSTITUTION" for item in all_violations)
    fabricated_history_values = 0
    advanced_keys = {"completed_sets", "prescribed_sets", "sets", "reps", "load_kg", "rpe", "rir"}
    for result in results:
        rows = result.scenario.history_records
        has_advanced = bool(rows and any(advanced_keys.intersection(row) for row in rows))
        if not has_advanced:
            for field in ("recent_sets", "recent_reps", "recent_load_kg", "recent_rpe", "recent_rir"):
                observation = getattr(result.state, field)
                fabricated_history_values += int(observation.value is not None)

    legacy_goal = {
        "GENERAL_FITNESS": "general_fitness", "STRENGTH": "strength", "HYPERTROPHY": "muscle_gain",
        "MUSCULAR_ENDURANCE": "endurance", "WEIGHT_MANAGEMENT": "weight_loss", "MOBILITY": "recovery",
    }
    legacy_policy_violations = 0
    legacy_catalog_violations = 0
    legacy_comparison_cases = 0
    policy = load_policy()
    catalog_by_source = {item["source_exercise_id"]: item for item in engine._catalog}  # noqa: SLF001
    for result in results[:40]:
        scenario = result.scenario
        goal = scenario.oracle.goal
        if scenario.oracle.planning_status != ApplicabilityStatus.SUPPORTED or goal not in legacy_goal:
            continue
        equipment = scenario.request.available_equipment_override or scenario.profile.available_equipment
        if len(equipment) != 1:
            continue
        legacy_equipment = {"bodyweight": "none", "bodyweight only": "none"}.get(equipment[0], equipment[0])
        level = "beginner" if scenario.profile.training_experience.value == "NOVICE" else "advanced" if scenario.profile.training_experience.value == "EXPERIENCED" else "intermediate"
        try:
            payload = suggest_workout(
                "mobility" if goal == "MOBILITY" else "full_body",
                max(10, int(scenario.request.requested_duration_minutes or 30)), legacy_equipment, level,
                goal=legacy_goal[goal],
            )
        except ValueError:
            continue
        legacy_comparison_cases += 1
        goal_profile = policy["goal_profiles"][goal]
        operational = scenario.profile.training_experience.value if scenario.profile.training_experience.value != "UNKNOWN" else "NOVICE"
        sets_rule = (goal_profile.get("sets_per_exercise") or {}).get(operational)
        reps_rule = goal_profile.get("repetition_range")
        expected_reps = reps_rule.get(operational) if isinstance(reps_rule, dict) else reps_rule
        rest_ranges = [tuple(value) for value in (goal_profile.get("rest_seconds") or {}).values()]
        for item in payload.get("exercises") or []:
            if sets_rule and not sets_rule[0] <= item.get("sets", -1) <= sets_rule[1]:
                legacy_policy_violations += 1
            normalized_reps = str(item.get("reps") or "").replace(" ", "")
            if expected_reps and normalized_reps != f"{expected_reps[0]}-{expected_reps[1]}":
                legacy_policy_violations += 1
            rest = item.get("rest_seconds")
            if rest_ranges and not any(low <= rest <= high for low, high in rest_ranges):
                legacy_policy_violations += 1
            source_id = item.get("wger_id") or item.get("id")
            canonical = catalog_by_source.get(source_id)
            if canonical is None or not catalog_eligibility(canonical)["structurally_prescription_eligible"]:
                legacy_catalog_violations += 1
    latencies = sorted(result.latency_ms for result in results)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    failed = [
        {"scenario_id": result.scenario.scenario_id, "failures": list(result.oracle_failures)}
        for result in results if result.oracle_failures
    ]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "scenario_count": len(results),
        "safety_invariant_violations": safety_violations,
        "hard_equipment_violations": equipment_violations,
        "equipment_compatibility_rate": round(1 - equipment_violations / max(1, sum(len(result.plan.exercises) for result in results)), 4),
        "catalog_hard_eligibility_violations": catalog_violations,
        "catalog_eligibility_violation_rate": round(catalog_violations / max(1, sum(len(result.plan.exercises) for result in results)), 4),
        "policy_hard_rule_compliance_rate": round(1 - policy_hard_violations / max(1, sum(len(result.plan.exercises) for result in results)), 4),
        "time_budget_compliance_rate": round(1 - time_violations / len(results), 4),
        "time_budget_hard_violations": time_violations,
        "required_history_behavior_accuracy": round(history_correct / len(results), 4),
        "progression_correctness": round(progression_correct / len(results), 4),
        "unsupported_progression": progression_violations,
        "fabricated_history_values": fabricated_history_values,
        "substitution_validity": round(1 - substitution_violations / max(1, sum(len(result.plan.exercises) for result in results)), 4),
        "unsupported_calorie_estimates": energy_violations,
        "personalization_sensitivity": round(sensitivity_success / len(personalization_pairs()), 4),
        "personalization_pairs": sensitivity_details,
        "irrelevant_input_stability": round(stability_success / len(irrelevant_input_pairs()), 4),
        "stability_pairs": stability_details,
        "determinism": round(deterministic / len(results), 4),
        "planner_latency_ms": {
            "median": round(statistics.median(latencies), 3),
            "p95": round(latencies[p95_index], 3),
            "max": round(max(latencies), 3),
        },
        "legacy_vs_e4_policy_violation_comparison": {
            "comparison_cases": legacy_comparison_cases,
            "legacy_policy_violations": legacy_policy_violations,
            "legacy_catalog_eligibility_violations": legacy_catalog_violations,
            "e4_policy_hard_violations": policy_hard_violations,
            "e4_catalog_hard_eligibility_violations": catalog_violations,
            "exact_exercise_overlap_target": None,
        },
        "failed_scenarios": failed,
    }


__all__ = ["EVALUATION_VERSION", "ScenarioResult", "evaluate_development_dataset"]
