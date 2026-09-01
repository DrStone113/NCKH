from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from modules.nutrition.catalog_ingestion import research_identity
from modules.wger.exercise_prescription_policy import (
    POLICY_FILE,
    POLICY_VERSION,
    ExercisePrescriptionPolicyError,
    build_policy,
    catalog_eligibility,
    content_sha256,
    estimate_mapped_session_energy,
    evaluate_progression,
    load_policy,
    map_activity_to_compendium,
    prescription_for,
    resolve_experience,
    resolve_goal_domain,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
LEGACY_E3_FILE = BACKEND_DIR / "data" / "exercise_prescription_policy_v1.json"
E2_MANIFEST_FILE = BACKEND_DIR / "data" / "canonical_exercise_catalog_manifest_v1.json"
RESEARCH_MANIFEST_FILE = BACKEND_DIR / "data" / "research_corpus_manifest.json"
NUTRITION_POLICY_FILE = (
    BACKEND_DIR / "services" / "nutrition" / "nutrition_policy_v1_0_1.json"
)


def _by_source_id(source_id: int) -> dict:
    return next(
        item
        for item in load_canonical_exercise_catalog()
        if item["source_exercise_id"] == source_id
    )


def test_experience_semantics_keep_report_and_history_separate() -> None:
    novice = resolve_experience(
        explicit_experience="NOVICE",
        local_history_available=False,
    )
    assert novice["experience"] == "NOVICE"
    assert novice["experience_provenance"] == "USER_REPORTED"
    assert novice["history_signal"] == "UNAVAILABLE"

    experienced_without_history = resolve_experience(
        explicit_experience="EXPERIENCED",
        local_history_available=False,
    )
    assert experienced_without_history["experience"] == "EXPERIENCED"
    assert experienced_without_history["operational_profile"] == "EXPERIENCED"
    assert experienced_without_history["local_history_available"] is False

    unknown = resolve_experience(
        explicit_experience=None,
        local_history_available=False,
    )
    assert unknown["experience"] == "UNKNOWN"
    assert unknown["experience_provenance"] == "UNKNOWN_NOT_INFERRED"
    assert unknown["operational_profile"] == "CONSERVATIVE_DEFAULT"

    conflict = resolve_experience(
        explicit_experience="EXPERIENCED",
        local_history_available=True,
        history_signal="NOVICE",
    )
    assert conflict["experience"] == "EXPERIENCED"
    assert conflict["history_signal"] == "NOVICE"
    assert conflict["signals_conflict"] is True
    assert conflict["semantic_status"] == "CONFLICTING_SIGNALS"


def test_prescription_does_not_turn_missing_history_into_novice() -> None:
    experienced = prescription_for(
        "STRENGTH",
        "EXPERIENCED",
        local_history_available=False,
    )
    assert experienced["effective_experience"] == "EXPERIENCED"
    assert experienced["experience_resolution"]["history_signal"] == "UNAVAILABLE"

    unknown = prescription_for(
        "STRENGTH",
        "UNKNOWN",
        local_history_available=False,
    )
    assert unknown["effective_experience"] == "UNKNOWN"
    assert unknown["operational_profile"] == "CONSERVATIVE_DEFAULT"
    with pytest.raises(
        ExercisePrescriptionPolicyError,
        match="HISTORY_SIGNAL_WITHOUT_LOCAL_HISTORY",
    ):
        prescription_for(
            "STRENGTH",
            "EXPERIENCED",
            local_history_available=False,
            history_signal="EXPERIENCED",
        )


@pytest.mark.parametrize("term", ["sức bền", "tăng endurance", "endurance"])
def test_ambiguous_endurance_requires_domain_clarification(term: str) -> None:
    ambiguous = resolve_goal_domain(term)
    assert ambiguous["status"] == "CLARIFICATION_REQUIRED"
    assert ambiguous["goal"] is None
    assert resolve_goal_domain(term, context="RESISTANCE")["goal"] == "MUSCULAR_ENDURANCE"
    assert resolve_goal_domain(term, context="AEROBIC")["goal"] == "AEROBIC_ENDURANCE"


def test_muscular_and_aerobic_endurance_are_separate_taxonomy_domains() -> None:
    policy = load_policy()
    taxonomy = policy["goal_taxonomy"]
    assert "MUSCULAR_ENDURANCE" in taxonomy["resistance_domain"]
    assert "AEROBIC_ENDURANCE" not in taxonomy["resistance_domain"]
    assert taxonomy["aerobic_domain"] == ["AEROBIC_ENDURANCE"]
    assert "ENDURANCE" not in taxonomy["resistance_domain"]
    assert resolve_goal_domain("sức bền cơ")["goal"] == "MUSCULAR_ENDURANCE"
    assert resolve_goal_domain("sức bền tim mạch")["goal"] == "AEROBIC_ENDURANCE"


def test_weight_management_has_no_rep_or_rest_fat_loss_claim() -> None:
    policy = load_policy()
    weight = policy["goal_profiles"]["WEIGHT_MANAGEMENT"]
    general = policy["goal_profiles"]["GENERAL_FITNESS"]
    assert weight["repetition_range"] == general["repetition_range"]
    assert weight["rest_seconds"] == general["rest_seconds"]
    assert "HIGHER_REPETITIONS_DO_NOT_IMPLY_GREATER_FAT_LOSS" in weight["semantic_guardrails"]
    assert "SHORTER_REST_DOES_NOT_IMPLY_BETTER_WEIGHT_LOSS" in weight["semantic_guardrails"]
    assert weight["field_provenance"]["repetition_range"] == "PRODUCT_HEURISTIC"
    assert weight["field_provenance"]["rest_seconds"] == "PRODUCT_HEURISTIC"


def test_every_mobility_rule_has_allowed_provenance_without_acsm_inheritance() -> None:
    mobility = load_policy()["goal_profiles"]["MOBILITY"]
    allowed = {"EVIDENCE_BASED_POLICY", "PRODUCT_HEURISTIC", "REQUIRES_DECISION"}
    rule_fields = {
        key
        for key in mobility
        if key not in {"field_provenance", "evidence_scope"}
    }
    assert set(mobility["field_provenance"]) == rule_fields
    assert set(mobility["field_provenance"].values()).issubset(allowed)
    assert mobility["evidence_scope"].endswith("NO_ACSM_RESISTANCE_INHERITANCE")
    assert "source" not in mobility


def test_power_eligibility_is_explicit_for_all_experience_states() -> None:
    eligibility = load_policy()["goal_profiles"]["POWER"]["eligibility"]
    assert eligibility == {
        "NOVICE": "REQUIRES_COACHING_OR_SKILL_ASSESSMENT",
        "EXPERIENCED": "ELIGIBLE_AFTER_SAFETY_AND_TECHNIQUE_SCREEN",
        "UNKNOWN": "REQUIRES_EXPERIENCE_CONFIRMATION",
    }
    unknown = prescription_for("POWER", "UNKNOWN")
    assert unknown["effective_experience"] == "UNKNOWN"
    assert unknown["eligibility"] == "REQUIRES_EXPERIENCE_CONFIRMATION"


def test_catalog_eligibility_exposes_missing_e2_metadata_without_filling_it() -> None:
    eligible = catalog_eligibility(_by_source_id(12))
    incomplete = catalog_eligibility(_by_source_id(56))
    muscle_unknown = catalog_eligibility(_by_source_id(9))
    movement_unknown = catalog_eligibility(_by_source_id(31))

    assert eligible["statuses"][0] == "PRESCRIPTION_ELIGIBLE"
    assert eligible["catalog_review_status"] == "SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED"
    assert incomplete["statuses"][0] == "SEARCH_ONLY"
    assert "INSTRUCTION_INCOMPLETE" in incomplete["statuses"]
    assert "MUSCLE_UNKNOWN" in muscle_unknown["statuses"]
    assert "MOVEMENT_UNKNOWN" in movement_unknown["statuses"]
    assert "SUBSTITUTION_UNAVAILABLE" in muscle_unknown["statuses"]
    assert all(
        result["missing_metadata_filled"] is False
        for result in (eligible, incomplete, muscle_unknown, movement_unknown)
    )


def test_catalog_eligibility_summary_is_frozen_for_all_e2_records() -> None:
    summary = load_policy()["catalog_eligibility"]["classification_summary"]
    assert summary == {
        "record_count": 885,
        "status_counts": {
            "PRESCRIPTION_ELIGIBLE": 430,
            "SEARCH_ONLY": 455,
            "INSTRUCTION_INCOMPLETE": 29,
            "MUSCLE_UNKNOWN": 194,
            "MOVEMENT_UNKNOWN": 320,
            "SUBSTITUTION_UNAVAILABLE": 438,
            "REQUIRES_EXPERIENCE_CONFIRMATION": 878,
        },
    }


def test_balance_rules_disclose_constraint_strength() -> None:
    weekly = load_policy()["weekly_structure"]
    assert weekly["major_muscle_exposure"]["constraint_class"] == "SOFT_PLANNING_TARGET"
    movement = weekly["movement_pattern_balance"]
    assert movement["constraint_class"] == "PRODUCT_HEURISTIC"
    assert movement["not_a_universal_medical_requirement"] is True
    assert all(
        item["constraint_class"] == "HARD_CONSTRAINT"
        for item in weekly["hard_constraints"]
    )


def test_progression_rule_has_complete_semantics_and_no_history_behavior() -> None:
    rule = load_policy()["adaptation_policy"]["progression"]
    assert rule["rule_id"] == "E3_1_DOUBLE_PROGRESSION_LOAD"
    assert rule["policy_version"] == POLICY_VERSION
    assert rule["evidence_status"] == "PRODUCT_HEURISTIC"
    assert rule["uniquely_optimal_claim"] is False
    assert rule["required_observations"]
    assert rule["failure_behavior"]

    unavailable = evaluate_progression(
        completed_all_sets=False,
        reached_top_of_rep_range=False,
        recorded_rir=None,
        technique_stable=True,
        pain_reported=False,
        consecutive_successes=0,
        consecutive_misses=0,
        region="upper_body",
        prior_history_available=False,
    )
    assert unavailable["decision"] == "PROGRESSION_UNAVAILABLE"
    assert unavailable["previous_load_kg"] is None
    for field in (
        "rule_id",
        "policy_version",
        "evidence_status",
        "required_observations",
        "failure_behavior",
    ):
        assert field in unavailable


def test_met_mapping_provenance_and_unmapped_no_estimate() -> None:
    direct = map_activity_to_compendium("RESISTANCE_MULTIPLE_EXERCISES_8_15_REPS")
    curated = map_activity_to_compendium("WGER_RESISTANCE_SESSION_GENERAL")
    unmapped = map_activity_to_compendium("WGER_AXE_HOLD")
    assert direct["mapping_status"] == "DIRECT_SUPPORTED_MAPPING"
    assert direct["compendium_code"] == "02054"
    assert curated["mapping_status"] == "APP_CURATED_MAPPING"
    assert curated["compendium_code"] == "02054"
    assert unmapped["mapping_status"] == "UNMAPPED_ACTIVITY"
    assert unmapped["compendium_code"] is None

    unavailable = estimate_mapped_session_energy(
        activity_key="WGER_AXE_HOLD",
        weight_kg=70,
        duration_minutes=30,
        age=30,
    )
    assert unavailable["status"] == "NO_CALORIE_ESTIMATE"
    assert unavailable["estimated_energy_expenditure_kcal"] is None
    assert unavailable["estimated"] is False


def test_material_semantics_are_versioned_without_overwriting_e3_v1() -> None:
    policy = load_policy()
    assert POLICY_FILE.name == "exercise_prescription_policy_v1_1.json"
    assert policy["schema_version"] == "exercise-prescription-policy-v1.1.0"
    assert policy["supersedes"]["policy_version"] == "exercise-prescription-policy-v1.0.0"
    assert LEGACY_E3_FILE.exists()
    assert hashlib.sha256(LEGACY_E3_FILE.read_bytes()).hexdigest() == (
        "38ac8adf02ecc454c1f5dfe8489249529a4c08ebbbbb4ce4a9eb330a24fb4754"
    )

    unsigned = {key: value for key, value in policy.items() if key != "manifest_sha256"}
    assert policy["manifest_sha256"] == content_sha256(unsigned)
    assert len(policy["content_sha256"]) == 64
    assert len(policy["manifest_sha256"]) == 64
    assert policy["creation_commit"]
    assert policy["source_registry"]["catalog_source"]["catalog_content_sha256"]
    assert build_policy(creation_commit=policy["creation_commit"]) == policy


def test_e3_1_phase_boundary_still_prohibits_e4_runtime_integration() -> None:
    boundary = load_policy()["phase_boundary"]
    assert boundary["current"] == "E3_1_PRESCRIPTION_POLICY_SEMANTIC_AND_REPRODUCIBILITY_GATE"
    assert boundary["runtime_chatbot_behavior_changed"] is False
    assert "personalized training-state planner" in boundary["not_implemented"]


def test_protected_e2_nutrition_and_research_artifacts_are_unchanged() -> None:
    assert hashlib.sha256(E2_MANIFEST_FILE.read_bytes()).hexdigest() == (
        "52cf7808ea817107132d3dfe20e673aa2124babf509dc9045d7a92b9d8c21d4f"
    )
    assert hashlib.sha256(NUTRITION_POLICY_FILE.read_bytes()).hexdigest() == (
        "e521a889afffcb535254c38c959aada5e64398ddd9f9f0613ac82be119f72127"
    )
    assert hashlib.sha256(RESEARCH_MANIFEST_FILE.read_bytes()).hexdigest() == (
        "703005bc1574162cf418cc4f5eff00029e7ab3b8c66eabdb5b4bb844a28cb633"
    )
    identity = research_identity()
    assert identity["corpus_version"] == "offline-v1-636"
    assert identity["experiment_condition_hashes"] == {
        "A": "d86e653a0737492efddaccfec0efd20e4cc972375d0811a5f03d989f08638710",
        "B": "5e19f545276858b65e1f9fd1c7464111b83fb7e35bf8d57870ed0bd25a950585",
        "C": "6c59f13b05c4f7e552f4a4a6371314e492e8ed8705e7a3439e323f145a265df7",
    }
    assert all(item["unchanged"] for item in identity["source_artifacts"])
