from __future__ import annotations

import json
from copy import deepcopy

import pytest

from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from modules.wger.exercise_prescription_policy import (
    POLICY_FILE,
    POLICY_VERSION,
    ExercisePrescriptionPolicyError,
    build_policy,
    content_sha256,
    estimate_session_energy,
    evaluate_progression,
    load_policy,
    missed_session_action,
    prescription_for,
    safety_gate,
    substitution_decision,
    verify_policy,
)
from services.agent.tools.workout import suggest_workout


def _by_source_id(source_id: int) -> dict:
    return next(
        item
        for item in load_canonical_exercise_catalog()
        if item["source_exercise_id"] == source_id
    )


def test_e3_policy_is_self_hashed_and_reproducible() -> None:
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in policy.items() if key != "manifest_sha256"}
    assert policy["manifest_sha256"] == content_sha256(unsigned)
    assert build_policy(creation_commit=policy["creation_commit"]) == policy
    assert verify_policy()["ok"] is True


def test_policy_covers_every_requested_prescription_dimension() -> None:
    policy = load_policy()
    assert policy["schema_version"] == POLICY_VERSION
    assert set(policy["training_goals"]) == {
        "GENERAL_FITNESS",
        "STRENGTH",
        "HYPERTROPHY",
        "MUSCULAR_ENDURANCE",
        "WEIGHT_MANAGEMENT",
        "MOBILITY",
        "POWER",
    }
    assert policy["supported_population"]
    assert policy["experience_policy"]
    assert policy["goal_profiles"]
    assert policy["weekly_structure"]["major_muscle_exposure"]
    assert policy["weekly_structure"]["movement_pattern_balance"]
    assert policy["exercise_selection_and_substitution"]
    assert policy["effort_policy"]
    assert policy["adaptation_policy"]["progression"]
    assert policy["adaptation_policy"]["regression"]
    assert policy["adaptation_policy"]["missed_session"]
    assert policy["pain_and_safety_boundary"]
    assert policy["aerobic_activity_policy"]
    assert policy["estimated_exercise_energy_expenditure"]


def test_safety_gate_supports_only_ordinary_healthy_adult_scope() -> None:
    assert safety_gate(age=30)["status"] == "SUPPORTED"
    assert safety_gate(age=None)["status"] == "NEEDS_CLARIFICATION"
    assert safety_gate(age=16)["status"] == "REQUIRES_PROFESSIONAL_GUIDANCE"
    assert (
        safety_gate(age=30, health_state="ACUTE_INJURY")["status"]
        == "REQUIRES_PROFESSIONAL_GUIDANCE"
    )
    assert (
        safety_gate(age=30, pregnancy_status="PREGNANT")["status"]
        == "REQUIRES_PROFESSIONAL_GUIDANCE"
    )


@pytest.mark.parametrize(
    "symptom",
    [
        "CHEST_PAIN_OR_PRESSURE",
        "SYNCOPE_OR_FAINTING",
        "SEVERE_OR_UNUSUAL_SHORTNESS_OF_BREATH",
        "LIGHTHEADED_DIZZY_OR_CONFUSED",
        "FAST_OR_UNEVEN_HEARTBEAT",
    ],
)
def test_warning_symptoms_stop_the_ordinary_planner(symptom: str) -> None:
    result = safety_gate(age=30, symptoms=[symptom])
    assert result["status"] == "STOP_AND_SEEK_MEDICAL_EVALUATION"
    assert result["ordinary_planner_allowed"] is False


def test_unknown_experience_keeps_unknown_semantics_with_conservative_profile() -> None:
    result = prescription_for("strength", "unknown")
    assert result["effective_experience"] == "UNKNOWN"
    assert result["experience_assumed"] is False
    assert result["operational_profile"] == "CONSERVATIVE_DEFAULT"
    assert result["eligibility"] == "ELIGIBLE_AFTER_SAFETY_GATE"
    power = prescription_for("POWER", "NOVICE")
    assert power["eligibility"] == "REQUIRES_COACHING_OR_SKILL_ASSESSMENT"


def test_goal_profiles_bind_strength_and_hypertrophy_evidence_without_false_precision() -> None:
    strength = prescription_for("STRENGTH", "EXPERIENCED")["prescription"]
    hypertrophy = prescription_for("HYPERTROPHY", "EXPERIENCED")["prescription"]
    assert strength["load_percent_1rm"]["EXPERIENCED"][0] == 80
    assert strength["sets_per_exercise"]["EXPERIENCED"] == [2, 3]
    assert hypertrophy["weekly_sets_per_target_muscle"] == {
        "NOVICE": [6, 10],
        "EXPERIENCED": [10, 18],
    }
    assert load_policy()["prescription_provenance"]["repetition_ranges"]["provenance"] == "APP_POLICY"


def test_exercise_order_and_weekly_movement_balance_are_explicit() -> None:
    policy = load_policy()
    order = policy["goal_profiles"]["STRENGTH"]["exercise_order"]
    assert order[0] == "TECHNICAL_OR_POWER_MOVEMENTS_IF_ELIGIBLE"
    assert order[1] == "GOAL_PRIORITY_MULTI_JOINT"
    movement = policy["weekly_structure"]["movement_pattern_balance"]
    assert "SQUAT" in movement["primary_weekly_patterns"]
    assert "HINGE" in movement["primary_weekly_patterns"]
    assert "HORIZONTAL_PUSH" in movement["primary_weekly_patterns"]
    assert "HORIZONTAL_PULL" in movement["primary_weekly_patterns"]
    assert "across the week" in movement["rule"]


def test_failure_is_not_required_and_rir_rpe_mapping_is_qualified() -> None:
    effort = load_policy()["effort_policy"]
    assert effort["failure_default"] == "NOT_REQUIRED"
    assert effort["rir_to_rpe_approximation"] == {
        "0": 10,
        "1": 9,
        "2": 8,
        "3": 7,
        "4": 6,
    }
    assert "Approximate only" in effort["mapping_warning"]
    assert "technical_or_power_movements" in effort["failure_prohibited"]


def test_progression_requires_two_successes_good_effort_technique_and_no_pain() -> None:
    result = evaluate_progression(
        completed_all_sets=True,
        reached_top_of_rep_range=True,
        recorded_rir=3,
        technique_stable=True,
        pain_reported=False,
        consecutive_successes=2,
        consecutive_misses=0,
        region="upper_body",
    )
    assert result["decision"] == "PROGRESSION_ELIGIBLE"
    assert result["load_change_percent"] == [2.5, 5.0]

    hold = evaluate_progression(
        completed_all_sets=True,
        reached_top_of_rep_range=True,
        recorded_rir=1,
        technique_stable=True,
        pain_reported=False,
        consecutive_successes=2,
        consecutive_misses=0,
        region="upper_body",
    )
    assert hold["decision"] == "HOLD"


def test_regression_and_pain_are_different_decisions() -> None:
    regression = evaluate_progression(
        completed_all_sets=False,
        reached_top_of_rep_range=False,
        recorded_rir=0,
        technique_stable=True,
        pain_reported=False,
        consecutive_successes=0,
        consecutive_misses=2,
        region="lower_body",
    )
    assert regression["decision"] == "REGRESS_LOAD_OR_VOLUME"
    assert regression["load_change_percent"] == [-5, -10]
    assert regression["volume_change_percent"] == [-20, -30]

    pain = evaluate_progression(
        completed_all_sets=False,
        reached_top_of_rep_range=False,
        recorded_rir=None,
        technique_stable=False,
        pain_reported=True,
        consecutive_successes=0,
        consecutive_misses=1,
        region="lower_body",
    )
    assert pain["decision"] == "SAFETY_STOP"
    assert pain["load_change_percent"] is None


def test_missed_session_never_doubles_or_chases_volume() -> None:
    one = missed_session_action(missed_sessions=1, days_since_last_session=5)
    assert one["decision"] == "RESUME_NEXT_PLANNED_SESSION"
    assert one["make_up_volume"] is False
    extended = missed_session_action(missed_sessions=2, days_since_last_session=9)
    assert extended["decision"] == "REDUCED_RETURN_SESSION"
    assert extended["volume_change_percent"] == [-20, -30]
    injury = missed_session_action(
        missed_sessions=1, days_since_last_session=3, illness_or_injury=True
    )
    assert injury["decision"] == "SAFETY_GATE_REQUIRED"


def test_substitution_requires_matching_catalog_constraints_and_human_review() -> None:
    bench = _by_source_id(73)
    dumbbell_decline = _by_source_id(186)
    review = substitution_decision(
        bench, dumbbell_decline, available_equipment_ids=[3]
    )
    assert review == {
        "decision": "REVIEW_REQUIRED",
        "reason": "E2_CURATED_METADATA_UNREVIEWED",
    }

    reviewed = deepcopy(dumbbell_decline)
    for field in ("movement_pattern", "difficulty", "laterality"):
        reviewed[field]["human_reviewed"] = True
    eligible = substitution_decision(bench, reviewed, available_equipment_ids=[3])
    assert eligible["decision"] == "ELIGIBLE_AFTER_SAFETY_AND_PREFERENCE_CHECK"
    unavailable = substitution_decision(bench, reviewed, available_equipment_ids=[])
    assert unavailable["reason"] == "EQUIPMENT_UNAVAILABLE"


def test_aerobic_policy_keeps_resistance_and_aerobic_targets_separate() -> None:
    aerobic = load_policy()["aerobic_activity_policy"]
    assert aerobic["weekly_moderate_minutes"] == [150, 300]
    assert aerobic["weekly_vigorous_minutes"] == [75, 150]
    assert aerobic["resistance_replacement_allowed"] is False
    assert "duration/frequency before vigorous intensity" in aerobic["inactive_start"]


def test_energy_is_session_level_estimate_with_compendium_age_boundary() -> None:
    estimate = estimate_session_energy(
        activity_code="02054", weight_kg=70, duration_minutes=30, age=30
    )
    assert estimate["status"] == "ESTIMATE_AVAILABLE"
    assert estimate["estimated_energy_expenditure_kcal"] == pytest.approx(128.62, abs=0.01)
    assert estimate["estimated"] is True
    assert estimate["measurement"] is False
    assert estimate["granularity"] == "SESSION_ACTIVITY_LEVEL"

    older = estimate_session_energy(
        activity_code="02054", weight_kg=70, duration_minutes=30, age=65
    )
    assert older["status"] == "AGE_APPROPRIATE_TABLE_REQUIRED"
    assert older["estimated_energy_expenditure_kcal"] is None
    with pytest.raises(
        ExercisePrescriptionPolicyError,
        match="UNSUPPORTED_COMPENDIUM_ACTIVITY_CODE",
    ):
        estimate_session_energy(
            activity_code="INVENTED", weight_kg=70, duration_minutes=30, age=30
        )


def test_e3_remains_isolated_from_current_chatbot_runtime() -> None:
    policy = load_policy()
    assert policy["phase_boundary"]["runtime_chatbot_behavior_changed"] is False
    assert policy["e2_baseline"]["production_recommendation_enabled"] is False
    legacy = suggest_workout(
        "chest", 20, "any", "intermediate", goal="strength"
    )
    assert all(item["reps"] == "5-8" for item in legacy["exercises"])
    assert all(item["sets"] == 2 for item in legacy["exercises"])
