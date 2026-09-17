from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from modules.nutrition.catalog_ingestion import research_identity
from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from services.workout_planner.contracts import (
    ApplicabilityStatus,
    ExerciseProfile,
    PainStatus,
    ProgressionStatus,
    StateStatus,
    TimeBudgetStatus,
    TrainingExperience,
    WorkoutRequest,
)
from services.workout_planner.development_scenarios import (
    FIXED_NOW,
    development_scenarios,
    safe_profile,
)
from services.workout_planner.evaluator import evaluate_development_dataset
from services.workout_planner.history import legacy_history_coverage, normalize_training_history
from services.workout_planner.planner import (
    PLANNER_VERSION,
    TIME_ASSUMPTIONS,
    PersonalizedWorkoutPlanner,
    build_session_requirement,
    evaluate_safety,
)
from services.workout_planner.shadow import run_shadow_comparison
from services.workout_planner.validator import WorkoutPlanValidator


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parents[1]


def _state(records=None, status: StateStatus = StateStatus.NOT_LOADED):
    return normalize_training_history(records, computed_at=FIXED_NOW, source_status=status)


def _plan(
    *, profile: ExerciseProfile | None = None, request: WorkoutRequest | None = None,
    records=None, status: StateStatus = StateStatus.NOT_LOADED, energy_weight_kg=None,
):
    profile = profile or safe_profile()
    state = _state(records, status)
    request = request or WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",))
    engine = PersonalizedWorkoutPlanner()
    return engine, state, request, engine.plan(profile, state, request, energy_weight_kg=energy_weight_kg)


def test_runtime_gate_is_current_python_310_patch_and_pytest_is_pinned() -> None:
    assert sys.version_info[:3] == (3, 10, 21)
    assert pytest.__version__ == "8.4.2"
    requirements = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
    development_requirements = (BACKEND_DIR / "requirements-dev.txt").read_text(
        encoding="utf-8"
    )
    assert "-r requirements-dev.txt" in requirements
    assert "pytest==8.4.2" in development_requirements
    assert "hypothesis==6.151.9" in development_requirements
    assert "pytest-asyncio==1.2.0" in development_requirements


def test_profile_and_request_are_immutable_and_keep_unknown_experience() -> None:
    profile = safe_profile(experience=TrainingExperience.UNKNOWN)
    assert profile.training_experience == TrainingExperience.UNKNOWN
    assert profile.local_history_available is False
    with pytest.raises(FrozenInstanceError):
        profile.goal = "STRENGTH"  # type: ignore[misc]
    request = WorkoutRequest(temporary_preferences=("AVOID_LEGS_TODAY",))
    assert request.write_intent is False
    assert profile.disliked_exercises == ()


def test_legacy_history_coverage_is_explicit_and_does_not_manufacture_set_data() -> None:
    coverage = legacy_history_coverage()
    assert coverage["sessions_last_7d"] == "DERIVABLE"
    assert coverage["muscle_exposure_7d"] == "PARTIAL"
    assert coverage["recent_load_kg"] == "MISSING"
    records = ({
        "id": "legacy", "exerciseTemplateId": "wger_713", "date": (FIXED_NOW - timedelta(days=1)).isoformat(),
        "name": "Wall Pushup", "duration": 20, "caloriesBurned": 80, "type": "strength", "isCompleted": True,
    },)
    state = _state(records, StateStatus.KNOWN)
    assert state.sessions_last_7d.value == 1
    assert state.recent_sets.value is None
    assert state.recent_reps.value is None
    assert state.recent_load_kg.value is None
    assert state.recent_rpe.value is None
    assert state.recent_rir.value is None


def test_unavailable_history_is_not_zero_volume_fresh_or_novice() -> None:
    state = _state()
    assert state.status == StateStatus.NOT_LOADED
    assert state.sessions_last_7d.value is None
    assert state.muscle_exposure_7d.value is None
    assert "HISTORY_UNAVAILABLE" in state.history_reason_codes
    _, _, _, plan = _plan()
    assert all(item.progression_status == ProgressionStatus.PROGRESSION_UNAVAILABLE for item in plan.exercises)
    assert "HISTORY_UNAVAILABLE" in plan.history_reason_codes


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (replace(safe_profile(), current_pain_status=PainStatus.SIGNIFICANT_CURRENT_PAIN), ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE),
        (replace(safe_profile(), exercise_safety_profile=replace(safe_profile().exercise_safety_profile, acute_injury=True)), ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE),
        (replace(safe_profile(), exercise_safety_profile=replace(safe_profile().exercise_safety_profile, recent_surgery=True)), ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE),
        (replace(safe_profile(), exercise_safety_profile=replace(safe_profile().exercise_safety_profile, warning_symptoms=("CHEST_PAIN_OR_PRESSURE",))), ApplicabilityStatus.UNSUPPORTED),
        (replace(safe_profile(), current_pain_status=PainStatus.UNKNOWN), ApplicabilityStatus.NEEDS_CLARIFICATION),
    ],
)
def test_non_overridable_safety_gate(profile: ExerciseProfile, expected: ApplicabilityStatus) -> None:
    decision = evaluate_safety(profile)
    assert decision.status == expected
    _, _, _, plan = _plan(profile=profile)
    assert plan.exercises == ()
    assert plan.readiness == "NOT_READY"


@pytest.mark.parametrize("term", ["sức bền", "endurance", "tăng endurance"])
def test_ambiguous_endurance_requires_clarification(term: str) -> None:
    profile = safe_profile()
    request = WorkoutRequest(goal_override=term, requested_duration_minutes=30, available_equipment_override=("none",))
    _, _, _, plan = _plan(profile=profile, request=request)
    assert plan.goal is None
    assert plan.time_budget_status == TimeBudgetStatus.CLARIFICATION_REQUIRED
    assert plan.exercises == ()


def test_aerobic_endurance_is_handed_off_not_silently_mapped_to_resistance() -> None:
    request = WorkoutRequest(goal_override="AEROBIC_ENDURANCE", goal_context="AEROBIC", session_type="AEROBIC", requested_duration_minutes=30, available_equipment_override=("none",))
    profile = safe_profile()
    state = _state()
    safety = evaluate_safety(profile)
    requirement = build_session_requirement(profile, state, request, safety)
    assert requirement.goal_domain == "AEROBIC"
    assert requirement.status == ApplicabilityStatus.UNSUPPORTED
    assert "AEROBIC_DOMAIN_HANDOFF" in requirement.selection_reason_codes


def test_power_requires_experience_and_technique_confirmation() -> None:
    novice = safe_profile(goal="POWER", experience=TrainingExperience.NOVICE)
    _, _, _, blocked = _plan(profile=novice)
    assert blocked.exercises == ()
    experienced = safe_profile(goal="POWER", experience=TrainingExperience.EXPERIENCED, technique_screen=True)
    _, _, _, allowed = _plan(profile=experienced)
    assert allowed.safety_status == ApplicabilityStatus.SUPPORTED
    assert all(item.movement_pattern in {"SQUAT", "HINGE"} for item in allowed.exercises)


def test_catalog_filter_reports_exact_arithmetic_at_every_hard_stage() -> None:
    _, _, _, plan = _plan()
    assert plan.catalog_filtering[0].before == 885
    expected_stages = {
        "SAFETY", "EXERCISE_EXCLUSIONS", "EXERCISE_INCLUDES", "AVAILABLE_EQUIPMENT", "LOCATION",
        "CATALOG_ELIGIBILITY", "REQUIRED_INSTRUCTIONS", "GOAL_DOMAIN", "EXPERIENCE_TECHNICAL_GATE", "EXPLICIT_LIMITATIONS",
    }
    assert {item.stage for item in plan.catalog_filtering} == expected_stages
    for previous, current in zip(plan.catalog_filtering, plan.catalog_filtering[1:]):
        assert previous.after == current.before
    assert all(item.before - item.removed == item.after for item in plan.catalog_filtering)


def test_hard_filters_cannot_be_resurrected_by_ranking() -> None:
    request = WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_exclude=("713",))
    _, _, _, plan = _plan(request=request)
    assert 713 not in {item.source_exercise_id for item in plan.exercises}
    assert all(item.required_equipment == ("none (bodyweight exercise)",) for item in plan.exercises)


def test_contextual_experience_status_does_not_block_all_unspecified_exercises() -> None:
    _, _, _, plan = _plan(profile=safe_profile(experience=TrainingExperience.UNKNOWN))
    assert plan.exercises
    assert any("REQUIRES_EXPERIENCE_CONFIRMATION" in item.eligibility_status for item in plan.exercises)
    assert all(item.movement_pattern not in {"CARDIO_OTHER", "LOCOMOTION", "MOBILITY"} for item in plan.exercises)


def test_time_solver_builds_inside_budget_instead_of_truncating() -> None:
    short = WorkoutRequest(requested_duration_minutes=15, available_equipment_override=("none",))
    _, _, _, short_plan = _plan(request=short)
    long = WorkoutRequest(requested_duration_minutes=60, available_equipment_override=("none",))
    _, _, _, long_plan = _plan(request=long)
    assert short_plan.estimated_duration <= 15
    assert long_plan.estimated_duration <= 60
    assert len(short_plan.exercises) < len(long_plan.exercises)
    assert TIME_ASSUMPTIONS["session_overhead_seconds"] == 300
    assert all(item.prescription.rest_range_seconds[0] >= 45 for item in short_plan.exercises)


@pytest.mark.parametrize("goal", ["GENERAL_FITNESS", "STRENGTH", "HYPERTROPHY", "MUSCULAR_ENDURANCE", "WEIGHT_MANAGEMENT", "MOBILITY"])
def test_prescriptions_are_consumed_from_e3_1(goal: str) -> None:
    profile = safe_profile(goal=goal, experience=TrainingExperience.NOVICE)
    _, state, request, plan = _plan(profile=profile)
    validation = WorkoutPlanValidator(load_canonical_exercise_catalog()).validate(plan, profile, state, request)
    assert not [item for item in validation.violations if item.severity == "HARD"]
    assert all(any(rule.startswith(f"E3_GOAL_PROFILE_{goal}") for rule in item.policy_rule_ids) for item in plan.exercises)


def test_weight_management_does_not_optimize_for_fabricated_calorie_burn() -> None:
    general = _plan(profile=safe_profile(goal="GENERAL_FITNESS"))[3]
    weight = _plan(profile=safe_profile(goal="WEIGHT_MANAGEMENT"))[3]
    dosage = lambda plan: [  # noqa: E731 - compact comparison intentionally ignores goal-specific audit IDs
        (item.prescription.sets, item.prescription.rep_range, item.prescription.rest_range_seconds, item.prescription.effort_target_rir)
        for item in plan.exercises
    ]
    assert dosage(general) == dosage(weight)
    assert weight.estimated_energy_expenditure.estimated_energy_expenditure is None


def test_progression_requires_complete_relevant_performance() -> None:
    complete = ({
        "id": "complete", "exerciseTemplateId": "wger_713", "date": (FIXED_NOW - timedelta(days=2)).isoformat(),
        "name": "Wall Pushup", "duration": 20, "caloriesBurned": 80, "type": "strength", "isCompleted": True,
        "completed_sets": 2, "prescribed_sets": 2, "reps": [15, 15], "load_kg": 10.0, "rir": 3.0,
        "technique_stable": True, "pain_reported": False, "consecutive_successes": 2, "consecutive_misses": 0,
    },)
    request = WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_include=("713",))
    profile = replace(safe_profile(), local_history_available=True)
    _, _, _, plan = _plan(profile=profile, request=request, records=complete, status=StateStatus.KNOWN)
    assert plan.exercises[0].progression_status == ProgressionStatus.PROGRESSION_AVAILABLE
    incomplete = ({key: value for key, value in complete[0].items() if key not in {"rir", "load_kg"}},)
    _, _, _, blocked = _plan(profile=profile, request=request, records=incomplete, status=StateStatus.KNOWN)
    assert blocked.exercises[0].progression_status == ProgressionStatus.PROGRESSION_UNAVAILABLE


def test_substitution_uses_structural_e3_rule_and_stays_explicit_when_unreviewed() -> None:
    request = WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_include=("713",))
    _, _, _, plan = _plan(request=request)
    assert plan.exercises[0].substitution.status == "SUBSTITUTION_UNAVAILABLE"
    assert plan.exercises[0].substitution.reason_codes
    assert plan.exercises[0].substitution.candidate_exercise_ids == ()


def test_energy_is_optional_session_level_compendium_estimate() -> None:
    _, _, _, unavailable = _plan()
    assert unavailable.estimated_energy_expenditure.status == "NO_CALORIE_ESTIMATE"
    _, _, _, available = _plan(energy_weight_kg=70)
    energy = available.estimated_energy_expenditure
    assert energy.estimated_energy_expenditure is not None
    assert energy.source == "ADULT_COMPENDIUM_2024"
    assert energy.mapping_status in {"DIRECT_SUPPORTED_MAPPING", "APP_CURATED_MAPPING"}


def test_plan_uses_canonical_english_names_without_fabricated_vietnamese_names() -> None:
    catalog = {item["exercise_id"]: item for item in load_canonical_exercise_catalog()}
    _, _, _, plan = _plan()
    assert all(item.display_name == catalog[item.canonical_exercise_id]["name_en"] for item in plan.exercises)


def test_validator_detects_tampered_equipment_and_time() -> None:
    engine, state, request, plan = _plan()
    tampered_exercise = replace(plan.exercises[0], required_equipment=("barbell",))
    tampered = replace(plan, exercises=(tampered_exercise,) + plan.exercises[1:], estimated_duration=31)
    result = WorkoutPlanValidator(engine._catalog).validate(tampered, safe_profile(), state, request)  # noqa: SLF001
    assert result.ready is False
    assert {item.code for item in result.violations} >= {"EQUIPMENT_INCOMPATIBLE", "TIME_BUDGET_EXCEEDED"}


def test_development_dataset_and_acceptance_metrics() -> None:
    assert len(development_scenarios()) >= 100
    metrics = evaluate_development_dataset()
    assert metrics["scenario_count"] >= 100
    assert metrics["safety_invariant_violations"] == 0
    assert metrics["hard_equipment_violations"] == 0
    assert metrics["catalog_hard_eligibility_violations"] == 0
    assert metrics["unsupported_progression"] == 0
    assert metrics["fabricated_history_values"] == 0
    assert metrics["unsupported_calorie_estimates"] == 0
    assert metrics["policy_hard_rule_compliance_rate"] == 1.0
    assert metrics["time_budget_hard_violations"] == 0
    assert metrics["determinism"] == 1.0
    assert metrics["personalization_sensitivity"] >= 0.95
    assert metrics["irrelevant_input_stability"] == 1.0
    assert metrics["failed_scenarios"] == []


def test_shadow_mode_is_off_by_default_and_never_changes_production_output(monkeypatch) -> None:
    from config import settings

    profile = safe_profile()
    state = _state()
    request = WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",))
    monkeypatch.setattr(settings, "workout_planner_mode", "off")
    assert run_shadow_comparison(profile, state, request, legacy_arguments={"muscle_group": "full_body", "duration_min": 30, "equipment": "none", "level": "intermediate"}) is None
    monkeypatch.setattr(settings, "workout_planner_mode", "shadow")
    comparison = run_shadow_comparison(profile, state, request, legacy_arguments={"muscle_group": "full_body", "duration_min": 30, "equipment": "none", "level": "intermediate"})
    assert comparison is not None
    assert comparison.production_output_changed is False


def test_e4_core_planner_is_not_reimplemented_in_chatbot_integration() -> None:
    # E4.1 intentionally wires the planner through an adapter/facade.  The
    # chatbot must not copy its frozen planner version or prescription logic.
    for relative in ("services/agent/orchestrator.py", "services/agent/tool_dispatcher.py", "services/agent/tools/workout.py"):
        text = (BACKEND_DIR / relative).read_text(encoding="utf-8")
        assert PLANNER_VERSION not in text
    integration = (BACKEND_DIR / "services/workout_planner/integration.py").read_text(encoding="utf-8")
    assert "planner.plan(profile, state, request" in integration


def test_frozen_research_e2_e3_and_nutrition_artifacts_are_unchanged() -> None:
    expected = {
        "data/canonical_exercise_catalog_manifest_v1.json": "52cf7808ea817107132d3dfe20e673aa2124babf509dc9045d7a92b9d8c21d4f",
        "data/exercise_prescription_policy_v1_1.json": "ac1b1b17b57516ca7a9fb657867dcd1d030c27fdb894252e5884bd4e93e7f2af",
        "data/research_corpus_manifest.json": "703005bc1574162cf418cc4f5eff00029e7ab3b8c66eabdb5b4bb844a28cb633",
        "services/nutrition/nutrition_policy_v1_0_1.json": "e521a889afffcb535254c38c959aada5e64398ddd9f9f0613ac82be119f72127",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((BACKEND_DIR / relative).read_bytes()).hexdigest() == digest
    identity = research_identity()
    assert identity["corpus_version"] == "offline-v1-636"
    assert identity["experiment_condition_hashes"] == {
        "A": "d86e653a0737492efddaccfec0efd20e4cc972375d0811a5f03d989f08638710",
        "B": "5e19f545276858b65e1f9fd1c7464111b83fb7e35bf8d57870ed0bd25a950585",
        "C": "6c59f13b05c4f7e552f4a4a6371314e492e8ed8705e7a3439e323f145a265df7",
    }
