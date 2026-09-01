"""Versioned E3 exercise-prescription policy for healthy general adults.

The policy is deliberately separate from the current chatbot and workout
selector. Evidence-supported boundaries and app engineering decisions carry
different provenance so future planners cannot present every default as an
ACSM mandate.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from modules.nutrition.catalog_ingestion import research_identity
from modules.wger.canonical_exercises import MANIFEST_FILE as E2_MANIFEST_FILE
from modules.wger.canonical_exercises import file_sha256
from modules.wger.canonical_exercises import load_canonical_exercise_catalog


BACKEND_DIR = Path(__file__).resolve().parents[2]
# See canonical_exercises: containers mount the backend at ``/app`` and do not
# expose enough parent directories to derive the checkout root by index.
REPO_ROOT = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR
POLICY_FILE = BACKEND_DIR / "data" / "exercise_prescription_policy_v1_1.json"

POLICY_VERSION = "exercise-prescription-policy-v1.1.0"
EVIDENCE_REVIEW_DATE = "2026-08-30"

GOALS = frozenset(
    {
        "GENERAL_FITNESS",
        "STRENGTH",
        "HYPERTROPHY",
        "MUSCULAR_ENDURANCE",
        "WEIGHT_MANAGEMENT",
        "MOBILITY",
        "POWER",
    }
)
EXPERIENCE_LEVELS = frozenset({"NOVICE", "EXPERIENCED", "UNKNOWN"})
EXPERIENCE_HISTORY_SIGNALS = frozenset(
    {"NOVICE", "EXPERIENCED", "INSUFFICIENT", "UNAVAILABLE"}
)

_ACSM_2026 = "ACSM_2026_POSITION_STAND"
_HHS_PAG = "HHS_PHYSICAL_ACTIVITY_GUIDELINES_2E"
_COMPENDIUM_2024 = "ADULT_COMPENDIUM_2024"
_RIR_2024 = "ROBINSON_2024_PROXIMITY_TO_FAILURE"
_REST_2024 = "SINGER_2024_INTERSET_REST"

_EMERGENCY_SYMPTOMS = frozenset(
    {
        "CHEST_PAIN_OR_PRESSURE",
        "SYNCOPE_OR_FAINTING",
        "SEVERE_OR_UNUSUAL_SHORTNESS_OF_BREATH",
        "LIGHTHEADED_DIZZY_OR_CONFUSED",
        "FAST_OR_UNEVEN_HEARTBEAT",
    }
)
_PROFESSIONAL_GUIDANCE_STATES = frozenset(
    {
        "ACUTE_INJURY",
        "RECENT_SURGERY",
        "SEVERE_OR_WORSENING_PAIN",
        "KNOWN_COMPLEX_CHRONIC_CONDITION",
    }
)

_SESSION_MET_CODES: dict[str, dict[str, Any]] = {
    "02040": {
        "activity": "Circuit training, including kettlebells and minimal rest",
        "met": 7.5,
    },
    "02050": {
        "activity": "Resistance training, vigorous effort",
        "met": 6.0,
    },
    "02054": {
        "activity": "Resistance training, multiple exercises, 8-15 repetitions",
        "met": 3.5,
    },
    "02056": {
        "activity": "Body-weight resistance exercise, general",
        "met": 3.0,
    },
    "02057": {
        "activity": "Body-weight resistance exercise, high intensity",
        "met": 6.5,
    },
}

_ACTIVITY_TO_COMPENDIUM: dict[str, dict[str, Any]] = {
    "RESISTANCE_MULTIPLE_EXERCISES_8_15_REPS": {
        "compendium_code": "02054",
        "mapping_status": "DIRECT_SUPPORTED_MAPPING",
        "rationale": "The activity description directly matches Compendium code 02054.",
    },
    "RESISTANCE_VIGOROUS_EFFORT": {
        "compendium_code": "02050",
        "mapping_status": "DIRECT_SUPPORTED_MAPPING",
        "rationale": "The activity description directly matches Compendium code 02050.",
    },
    "BODYWEIGHT_RESISTANCE_GENERAL": {
        "compendium_code": "02056",
        "mapping_status": "DIRECT_SUPPORTED_MAPPING",
        "rationale": "The activity description directly matches Compendium code 02056.",
    },
    "BODYWEIGHT_RESISTANCE_HIGH_INTENSITY": {
        "compendium_code": "02057",
        "mapping_status": "DIRECT_SUPPORTED_MAPPING",
        "rationale": "The activity description directly matches Compendium code 02057.",
    },
    "WGER_RESISTANCE_SESSION_GENERAL": {
        "compendium_code": "02054",
        "mapping_status": "APP_CURATED_MAPPING",
        "rationale": "Wger identifies exercises, not session effort; the app maps a confirmed general multi-exercise session to code 02054.",
    },
    "WGER_RESISTANCE_SESSION_VIGOROUS": {
        "compendium_code": "02050",
        "mapping_status": "APP_CURATED_MAPPING",
        "rationale": "The app maps a separately confirmed vigorous resistance session to code 02050; exercise names alone are insufficient.",
    },
}

_SEMANTIC_CONTENT_KEYS = (
    "supported_population",
    "goal_taxonomy",
    "experience_policy",
    "goal_profiles",
    "prescription_provenance",
    "weekly_structure",
    "exercise_selection_and_substitution",
    "catalog_eligibility",
    "effort_policy",
    "adaptation_policy",
    "pain_and_safety_boundary",
    "aerobic_activity_policy",
    "estimated_exercise_energy_expenditure",
)


class ExercisePrescriptionPolicyError(ValueError):
    """Raised when E3 policy inputs or its frozen identity are invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _source(
    provenance: str,
    *,
    evidence_ids: Iterable[str] = (),
    rationale: str,
) -> dict[str, Any]:
    return {
        "provenance": provenance,
        "evidence_ids": list(evidence_ids),
        "rationale": rationale,
    }


def _goal_profiles() -> dict[str, Any]:
    shared_order = [
        "TECHNICAL_OR_POWER_MOVEMENTS_IF_ELIGIBLE",
        "GOAL_PRIORITY_MULTI_JOINT",
        "OTHER_MULTI_JOINT",
        "SINGLE_JOINT_OR_ACCESSORY",
        "CORE_CARRY_OR_COOLDOWN",
    ]
    return {
        "GENERAL_FITNESS": {
            "frequency_days_per_week": {"NOVICE": [2, 3], "EXPERIENCED": [2, 4]},
            "load_percent_1rm": [50, 75],
            "repetition_range": [8, 15],
            "sets_per_exercise": {"NOVICE": [2, 2], "EXPERIENCED": [2, 3]},
            "weekly_sets_per_major_muscle": {"NOVICE": [4, 8], "EXPERIENCED": [6, 12]},
            "rest_seconds": {"multi_joint": [90, 180], "accessory": [60, 120]},
            "target_rir": {"NOVICE": [3, 4], "EXPERIENCED": [2, 4]},
            "session_duration_minutes": [30, 60],
            "exercise_order": shared_order,
            "selection": "FULL_BODY_OR_BALANCED_SPLIT_USING_MAJOR_MOVEMENT_PATTERNS",
        },
        "STRENGTH": {
            "frequency_days_per_week": {"NOVICE": [2, 3], "EXPERIENCED": [2, 4]},
            "load_percent_1rm": {"NOVICE": [60, 80], "EXPERIENCED": [80, 90]},
            "repetition_range": {"NOVICE": [5, 10], "EXPERIENCED": [3, 6]},
            "sets_per_exercise": {"NOVICE": [2, 3], "EXPERIENCED": [2, 3]},
            "weekly_sets_per_priority_muscle": {"NOVICE": [4, 8], "EXPERIENCED": [6, 12]},
            "rest_seconds": {"priority_lift": [120, 300], "accessory": [60, 180]},
            "target_rir": {"NOVICE": [3, 4], "EXPERIENCED": [2, 3]},
            "session_duration_minutes": [35, 75],
            "exercise_order": shared_order,
            "selection": "GOAL_PRIORITY_LIFTS_FIRST_WITH_BALANCED_ASSISTANCE",
        },
        "HYPERTROPHY": {
            "frequency_days_per_week": {"NOVICE": [2, 3], "EXPERIENCED": [3, 5]},
            "load_percent_1rm": [60, 80],
            "repetition_range": [6, 15],
            "sets_per_exercise": {"NOVICE": [2, 3], "EXPERIENCED": [2, 4]},
            "weekly_sets_per_target_muscle": {"NOVICE": [6, 10], "EXPERIENCED": [10, 18]},
            "rest_seconds": {"multi_joint": [90, 180], "accessory": [60, 120]},
            "target_rir": {"NOVICE": [2, 4], "EXPERIENCED": [1, 3]},
            "session_duration_minutes": [35, 75],
            "exercise_order": shared_order,
            "selection": "MULTI_JOINT_PLUS_TARGETED_ACCESSORIES_WITHOUT_DUPLICATE_JUNK_VOLUME",
        },
        "MUSCULAR_ENDURANCE": {
            "frequency_days_per_week": {"NOVICE": [2, 3], "EXPERIENCED": [2, 4]},
            "load_percent_1rm": [30, 60],
            "repetition_range": [12, 20],
            "sets_per_exercise": {"NOVICE": [2, 2], "EXPERIENCED": [2, 3]},
            "weekly_sets_per_major_muscle": {"NOVICE": [4, 8], "EXPERIENCED": [6, 12]},
            "rest_seconds": {"multi_joint": [60, 120], "accessory": [45, 90]},
            "target_rir": {"NOVICE": [3, 4], "EXPERIENCED": [2, 3]},
            "session_duration_minutes": [25, 60],
            "exercise_order": shared_order,
            "selection": "LOWER_SKILL_MOVEMENTS_THAT_PRESERVE_TECHNIQUE_UNDER_FATIGUE",
        },
        "WEIGHT_MANAGEMENT": {
            "frequency_days_per_week": {"NOVICE": [2, 3], "EXPERIENCED": [2, 4]},
            "load_percent_1rm": [50, 75],
            "repetition_range": [8, 15],
            "sets_per_exercise": {"NOVICE": [2, 2], "EXPERIENCED": [2, 3]},
            "weekly_sets_per_major_muscle": {"NOVICE": [4, 8], "EXPERIENCED": [6, 12]},
            "rest_seconds": {"multi_joint": [90, 180], "accessory": [60, 120]},
            "target_rir": {"NOVICE": [3, 4], "EXPERIENCED": [2, 4]},
            "session_duration_minutes": [30, 60],
            "exercise_order": shared_order,
            "selection": "SUSTAINABLE_FULL_BODY_RESISTANCE_PLUS_SEPARATE_AEROBIC_TARGET",
            "semantic_guardrails": [
                "HIGHER_REPETITIONS_DO_NOT_IMPLY_GREATER_FAT_LOSS",
                "SHORTER_REST_DOES_NOT_IMPLY_BETTER_WEIGHT_LOSS",
                "RESISTANCE_TRAINING_DOES_NOT_REPLACE_AEROBIC_OR_NUTRITION_CONTEXT",
            ],
            "field_provenance": {
                "frequency_days_per_week": "EVIDENCE_BASED_POLICY",
                "load_percent_1rm": "PRODUCT_HEURISTIC",
                "repetition_range": "PRODUCT_HEURISTIC",
                "sets_per_exercise": "PRODUCT_HEURISTIC",
                "weekly_sets_per_major_muscle": "PRODUCT_HEURISTIC",
                "rest_seconds": "PRODUCT_HEURISTIC",
                "target_rir": "PRODUCT_HEURISTIC",
                "session_duration_minutes": "PRODUCT_HEURISTIC",
                "exercise_order": "PRODUCT_HEURISTIC",
                "selection": "PRODUCT_HEURISTIC",
                "semantic_guardrails": "EVIDENCE_BASED_POLICY",
            },
        },
        "MOBILITY": {
            "frequency_days_per_week": {"NOVICE": [2, 7], "EXPERIENCED": [2, 7]},
            "load_percent_1rm": None,
            "repetition_range": None,
            "sets_per_exercise": {"NOVICE": [1, 3], "EXPERIENCED": [1, 3]},
            "weekly_sets_per_major_muscle": None,
            "rest_seconds": {"as_needed": [15, 60]},
            "target_rir": None,
            "session_duration_minutes": [10, 30],
            "exercise_order": ["LOW_INTENSITY_WARMUP", "CONTROLLED_MOBILITY", "COOLDOWN"],
            "selection": "PAIN_FREE_CONTROLLED_RANGE_OF_MOTION_ONLY",
            "field_provenance": {
                "frequency_days_per_week": "PRODUCT_HEURISTIC",
                "load_percent_1rm": "REQUIRES_DECISION",
                "repetition_range": "REQUIRES_DECISION",
                "sets_per_exercise": "PRODUCT_HEURISTIC",
                "weekly_sets_per_major_muscle": "REQUIRES_DECISION",
                "rest_seconds": "PRODUCT_HEURISTIC",
                "target_rir": "REQUIRES_DECISION",
                "session_duration_minutes": "PRODUCT_HEURISTIC",
                "exercise_order": "PRODUCT_HEURISTIC",
                "selection": "PRODUCT_HEURISTIC",
            },
            "evidence_scope": "PAIN_FREE_GENERAL_MOBILITY_ONLY_NO_ACSM_RESISTANCE_INHERITANCE",
        },
        "POWER": {
            "frequency_days_per_week": {"NOVICE": None, "EXPERIENCED": [2, 3]},
            "load_percent_1rm": {"EXPERIENCED": [30, 70]},
            "repetition_range": {"EXPERIENCED": [3, 6]},
            "sets_per_exercise": {"NOVICE": None, "EXPERIENCED": [2, 4]},
            "weekly_repetitions_times_sets_cap": 24,
            "rest_seconds": {"power_lift": [120, 300]},
            "target_rir": {"EXPERIENCED": [3, 5]},
            "session_duration_minutes": [30, 60],
            "exercise_order": shared_order,
            "selection": "HIGH_SKILL_POWER_WORK_REQUIRES_EXPERIENCE_AND_TECHNIQUE_SCREEN",
            "eligibility": {
                "NOVICE": "REQUIRES_COACHING_OR_SKILL_ASSESSMENT",
                "EXPERIENCED": "ELIGIBLE_AFTER_SAFETY_AND_TECHNIQUE_SCREEN",
                "UNKNOWN": "REQUIRES_EXPERIENCE_CONFIRMATION",
            },
        },
    }


def build_policy(*, creation_commit: str | None = None) -> dict[str, Any]:
    try:
        e2 = json.loads(E2_MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExercisePrescriptionPolicyError("INVALID_E2_MANIFEST") from exc
    policy = {
        "schema_version": POLICY_VERSION,
        "creation_commit": creation_commit or _current_git_commit(),
        "supersedes": {
            "policy_version": "exercise-prescription-policy-v1.0.0",
            "artifact": "apps/backend/data/exercise_prescription_policy_v1.json",
            "reason": "Material semantic corrections for experience, taxonomy, provenance, catalog eligibility, progression and MET mapping.",
        },
        "scope": "E3_1_PRESCRIPTION_POLICY_SEMANTIC_AND_REPRODUCIBILITY_GATE_ONLY",
        "reviewed_at": EVIDENCE_REVIEW_DATE,
        "supported_population": {
            "status": "SUPPORTED",
            "criteria": [
                "adult_age_18_or_older",
                "healthy_general_or_recreational_fitness",
                "no_current_warning_symptoms",
                "no_acute_injury_recent_surgery_or_severe_worsening_pain",
                "no_unresolved_condition_requiring_clinical_prescription",
            ],
            "excluded_from_ordinary_planner": [
                "under_18",
                "pregnancy_or_postpartum",
                "clinical_rehabilitation",
                "known_complex_chronic_condition_without_professional_plan",
                "acute_injury_or_recent_surgery",
                "warning_symptoms_or_severe_worsening_pain",
            ],
            "source": _source(
                "SAFETY_SCOPE",
                evidence_ids=[_ACSM_2026, _HHS_PAG],
                rationale="The resistance evidence applies to healthy adults; symptomatic or condition-specific exercise requires a different pathway.",
            ),
        },
        "training_goals": sorted(GOALS),
        "goal_taxonomy": {
            "resistance_domain": sorted(GOALS),
            "aerobic_domain": ["AEROBIC_ENDURANCE"],
            "ambiguous_terms": ["sức bền", "tăng endurance", "endurance"],
            "ambiguous_without_context": "CLARIFICATION_REQUIRED",
            "endurance_alias_prohibited": True,
        },
        "experience_policy": {
            "NOVICE": "User-reported less than six months of consistent resistance training or an explicitly reported long layoff.",
            "EXPERIENCED": "At least six months of consistent resistance training with stable technique and usable logs.",
            "UNKNOWN": "The user has not explicitly reported experience; this value remains UNKNOWN regardless of local history availability.",
            "UNKNOWN_OPERATIONAL_PROFILE": "CONSERVATIVE_DEFAULT",
            "history_availability_is_experience": False,
            "explicit_report_and_history_signal_are_separate": True,
            "conflicting_signals": "EXPOSE_CONFLICT_DO_NOT_SILENTLY_RECLASSIFY",
            "power_eligibility": {
                "NOVICE": "REQUIRES_COACHING_OR_SKILL_ASSESSMENT",
                "EXPERIENCED": "ELIGIBLE_AFTER_SAFETY_AND_TECHNIQUE_SCREEN",
                "UNKNOWN": "REQUIRES_EXPERIENCE_CONFIRMATION",
            },
            "source": _source(
                "APP_POLICY",
                evidence_ids=[_ACSM_2026],
                rationale="Experience routing is a conservative product boundary; missing local history is not evidence that a user is a novice.",
            ),
        },
        "goal_profiles": _goal_profiles(),
        "prescription_provenance": {
            "frequency": _source(
                "EVIDENCE_BOUND_PLUS_APP_RANGE",
                evidence_ids=[_ACSM_2026, _HHS_PAG],
                rationale="At least two weekly resistance exposures are evidence-bound; wider goal-specific ranges are app defaults.",
            ),
            "load_sets_weekly_volume": _source(
                "EVIDENCE_BOUND_PLUS_APP_RANGE",
                evidence_ids=[_ACSM_2026],
                rationale="Strength benefits from heavier loads and 2-3 sets; hypertrophy benefits from about 10 or more weekly sets, with diminishing returns around 18-20.",
            ),
            "repetition_ranges": _source(
                "APP_POLICY",
                evidence_ids=[_ACSM_2026],
                rationale="Rep ranges operationalize load and goal but are not presented as uniquely optimal ACSM mandates.",
            ),
            "rest_intervals": _source(
                "APP_POLICY",
                evidence_ids=[_ACSM_2026, _REST_2024],
                rationale="Defaults preserve set performance; evidence does not establish one universally optimal interval.",
            ),
            "rir_rpe": _source(
                "APP_AUTOREGULATION_POLICY",
                evidence_ids=[_ACSM_2026, _RIR_2024],
                rationale="Failure is not required by default; RIR estimates are useful but imprecise and goal dependent.",
            ),
            "exercise_order": _source(
                "EVIDENCE_BOUND_PLUS_APP_ORDER",
                evidence_ids=[_ACSM_2026],
                rationale="Priority strength movements benefit from early placement; remaining order is a deterministic app convention.",
            ),
            "session_duration": _source(
                "APP_POLICY",
                rationale="Duration bands are feasibility budgets, not physiological dose thresholds.",
            ),
        },
        "weekly_structure": {
            "major_muscle_exposure": {
                "target_days_per_week": [2, 3],
                "minimum_for_general_health": 2,
                "volume_distribution": "Prefer spreading target-muscle sets across at least two days when schedule allows.",
                "constraint_class": "SOFT_PLANNING_TARGET",
                "source": _source(
                    "EVIDENCE_BOUND",
                    evidence_ids=[_ACSM_2026, _HHS_PAG],
                    rationale="Healthy adults should train all major muscle groups at least twice weekly.",
                ),
            },
            "movement_pattern_balance": {
                "primary_weekly_patterns": [
                    "SQUAT",
                    "HINGE",
                    "HORIZONTAL_PUSH",
                    "HORIZONTAL_PULL",
                    "VERTICAL_PUSH",
                    "VERTICAL_PULL",
                    "CORE_ANTI_EXTENSION_OR_ANTI_ROTATION",
                ],
                "conditional_patterns": ["LOCOMOTION", "CARRY", "UNILATERAL_LOWER_BODY"],
                "rule": "Balance is evaluated across the week, not forced into every session.",
                "constraint_class": "PRODUCT_HEURISTIC",
                "not_a_universal_medical_requirement": True,
                "source": _source(
                    "APP_POLICY",
                    rationale="Movement balance is an explainable planner constraint; ACSM specifies major muscles, not this exact taxonomy.",
                ),
            },
            "hard_constraints": [
                {
                    "rule_id": "BALANCE_SAFETY_GATE_FIRST",
                    "constraint_class": "HARD_CONSTRAINT",
                    "rule": "No weekly-balance target may override safety or available-equipment constraints.",
                }
            ],
        },
        "exercise_selection_and_substitution": {
            "selection_order": [
                "PASS_SAFETY_GATE",
                "MATCH_AVAILABLE_EQUIPMENT",
                "MATCH_GOAL_AND_EXPERIENCE",
                "COVER_WEEKLY_MUSCLE_AND_MOVEMENT_GAPS",
                "HONOR_PREFERENCES_AND_DISLIKES",
                "FIT_SESSION_TIME",
            ],
            "session_exercise_count": {"resistance": [4, 8], "mobility": [2, 8]},
            "substitution_required_match": [
                "same_movement_pattern",
                "overlapping_primary_muscle",
                "available_equipment",
                "appropriate_reviewed_difficulty",
                "no_limitation_or_safety_conflict",
            ],
            "unreviewed_e2_metadata": "REVIEW_REQUIRED_NOT_AUTO_SUBSTITUTABLE",
            "source": _source(
                "APP_CATALOG_POLICY",
                rationale="Substitutions are faithful only when the source and candidate constraints actually match.",
            ),
        },
        "catalog_eligibility": {
            "policy_version": POLICY_VERSION,
            "statuses": [
                "PRESCRIPTION_ELIGIBLE",
                "SEARCH_ONLY",
                "INSTRUCTION_INCOMPLETE",
                "MUSCLE_UNKNOWN",
                "MOVEMENT_UNKNOWN",
                "SUBSTITUTION_UNAVAILABLE",
                "REQUIRES_EXPERIENCE_CONFIRMATION",
            ],
            "missing_metadata_is_filled": False,
            "classification_summary": _catalog_eligibility_summary(),
            "source": _source(
                "E2_STRUCTURAL_ELIGIBILITY_POLICY",
                rationale="Eligibility is derived only from frozen E2 fields; structural eligibility does not bypass safety, experience or human review.",
            ),
        },
        "effort_policy": {
            "rir_to_rpe_approximation": {"0": 10, "1": 9, "2": 8, "3": 7, "4": 6},
            "mapping_warning": "Approximate only; user-reported RIR/RPE is not a direct physiological measurement.",
            "failure_default": "NOT_REQUIRED",
            "failure_exception": "Experienced users may optionally use 0-1 RIR on a final set of a stable low-risk isolation movement; never required.",
            "failure_prohibited": [
                "novice_default",
                "technical_or_power_movements",
                "free_weight_compounds_without_safeties",
                "pain_fatigue_or_form_breakdown",
            ],
        },
        "adaptation_policy": {
            "progression": {
                "rule_id": "E3_1_DOUBLE_PROGRESSION_LOAD",
                "policy_version": POLICY_VERSION,
                "method": "DOUBLE_PROGRESSION",
                "evidence_status": "PRODUCT_HEURISTIC",
                "uniquely_optimal_claim": False,
                "required_observations": [
                    "prior_prescription_and_result_available",
                    "all_prescribed_sets_completed_at_top_of_rep_range",
                    "target_rir_met",
                    "stable_technique",
                    "no_pain_or_warning_symptoms",
                    "two_consecutive_successful_exposures",
                ],
                "no_prior_history": "PROGRESSION_UNAVAILABLE",
                "failure_behavior": "HOLD_CURRENT_PRESCRIPTION_UNLESS_REGRESSION_OR_SAFETY_RULE_APPLIES",
                "load_increase_percent": {"upper_body": [2.5, 5.0], "lower_body": [2.5, 7.5]},
                "source": _source(
                    "APP_POLICY",
                    evidence_ids=[_ACSM_2026],
                    rationale="Progressive overload is evidence-informed; double progression and exact increments are app operational choices, not uniquely optimal.",
                ),
            },
            "regression": {
                "triggers": [
                    "two_consecutive_exposures_below_minimum_reps",
                    "repeated_zero_rir_or_technique_breakdown",
                    "completion_rate_below_80_percent",
                    "return_after_extended_layoff",
                ],
                "load_reduction_percent": [5, 10],
                "volume_reduction_percent": [20, 30],
                "pain_action": "SAFETY_GATE_NOT_AUTOMATIC_REGRESSION",
            },
            "missed_session": {
                "one_session": "Resume the next planned session; do not double sessions or chase missed volume.",
                "two_or_more_or_seven_days": "Resume with 20-30% less volume and optionally 5-10% less load, then reassess.",
                "illness_injury_or_warning_symptoms": "Do not auto-reschedule; route through safety gate.",
                "source": _source(
                    "APP_POLICY",
                    rationale="Missed-session rules prioritize adherence and avoid unsafe compensatory volume.",
                ),
            },
        },
        "pain_and_safety_boundary": {
            "states": [
                "SUPPORTED",
                "NEEDS_CLARIFICATION",
                "REQUIRES_PROFESSIONAL_GUIDANCE",
                "STOP_AND_SEEK_MEDICAL_EVALUATION",
            ],
            "warning_symptoms": sorted(_EMERGENCY_SYMPTOMS),
            "pain_rule": "New sharp, severe, worsening, gait-altering or persistent pain is not handled by swapping exercises or lowering load.",
            "llm_override_allowed": False,
            "source": _source(
                "SAFETY_BOUNDARY",
                evidence_ids=[_HHS_PAG],
                rationale="Symptoms and condition-specific plans require clinical evaluation or professional guidance outside an ordinary fitness planner.",
            ),
        },
        "aerobic_activity_policy": {
            "weekly_moderate_minutes": [150, 300],
            "weekly_vigorous_minutes": [75, 150],
            "combination_allowed": True,
            "equivalence_rule": "One vigorous minute counts approximately as two moderate minutes for guideline accounting.",
            "inactive_start": "Start with small tolerable amounts and progress duration/frequency before vigorous intensity.",
            "resistance_replacement_allowed": False,
            "weight_management_note": "Weight-management goals do not authorize extreme aerobic volume or punitive exercise.",
            "source": _source(
                "EVIDENCE_BOUND",
                evidence_ids=[_HHS_PAG],
                rationale="Federal adult guidelines specify aerobic minutes plus at least two muscle-strengthening days.",
            ),
        },
        "estimated_exercise_energy_expenditure": {
            "method": "SESSION_ACTIVITY_LEVEL_MET_ESTIMATE",
            "formula": "MET * 3.5 * weight_kg / 200 * duration_minutes",
            "adult_compendium_age_range": [19, 59],
            "activity_codes": deepcopy(_SESSION_MET_CODES),
            "activity_to_compendium_mapping": deepcopy(_ACTIVITY_TO_COMPENDIUM),
            "mapping_statuses": [
                "DIRECT_SUPPORTED_MAPPING",
                "APP_CURATED_MAPPING",
                "UNMAPPED_ACTIVITY",
            ],
            "wger_mapping_boundary": "Wger exercise metadata never supplies MET; session context must be mapped explicitly.",
            "no_compendium_code": "NO_CALORIE_ESTIMATE",
            "forbidden": [
                "per_set_calorie_claim",
                "exact_calories_burned_label",
                "invented_exercise_specific_met",
                "use_outside_source_age_range_without_age_appropriate_table",
            ],
            "output_label": "estimated_energy_expenditure_kcal",
            "source": _source(
                "EVIDENCE_SOURCE_PLUS_ESTIMATION_FORMULA",
                evidence_ids=[_COMPENDIUM_2024],
                rationale="Compendium MET values standardize population estimates and are not individual measurements.",
            ),
        },
        "evidence_registry": {
            _ACSM_2026: {
                "title": "ACSM Position Stand: Resistance Training Prescription for Muscle Function, Hypertrophy, and Physical Performance in Healthy Adults",
                "year": 2026,
                "url": "https://pubmed.ncbi.nlm.nih.gov/41843416/",
                "doi": "10.1249/MSS.0000000000003897",
                "population": "healthy adults age 18 or older",
            },
            _HHS_PAG: {
                "title": "Physical Activity Guidelines for Americans, Second Edition",
                "year": 2018,
                "url": "https://odphp.health.gov/sites/default/files/2019-09/Physical_Activity_Guidelines_2nd_edition.pdf",
                "publisher": "U.S. Department of Health and Human Services",
            },
            _COMPENDIUM_2024: {
                "title": "2024 Adult Compendium of Physical Activities",
                "year": 2024,
                "url": "https://pacompendium.com/adult-compendium/",
                "doi": "10.1016/j.jshs.2023.10.010",
                "population": "adults age 19-59",
            },
            _RIR_2024: {
                "title": "Dose-response relationship between estimated proximity to failure, strength gain, and hypertrophy",
                "year": 2024,
                "url": "https://pubmed.ncbi.nlm.nih.gov/38970765/",
                "doi": "10.1007/s40279-024-02069-2",
            },
            _REST_2024: {
                "title": "Give it a rest: inter-set rest duration and muscle hypertrophy",
                "year": 2024,
                "url": "https://pubmed.ncbi.nlm.nih.gov/39205815/",
                "doi": "10.3389/fspor.2024.1429789",
            },
        },
        "source_registry": {
            "schema_version": "exercise-policy-source-registry-v1.0.0",
            "evidence_source_ids": [
                _ACSM_2026,
                _HHS_PAG,
                _COMPENDIUM_2024,
                _RIR_2024,
                _REST_2024,
            ],
            "catalog_source": {
                "source_id": "E2_CANONICAL_EXERCISE_CATALOG",
                "manifest_path": "apps/backend/data/canonical_exercise_catalog_manifest_v1.json",
                "manifest_sha256": file_sha256(E2_MANIFEST_FILE),
                "catalog_content_sha256": e2.get("catalog", {}).get("content_sha256"),
            },
            "nutrition_policy_used": False,
            "research_conditions_modified": False,
        },
        "e2_baseline": {
            "schema_version": e2.get("schema_version"),
            "manifest_hash": e2.get("manifest_hash"),
            "file_sha256": file_sha256(E2_MANIFEST_FILE),
            "catalog_sha256": e2.get("catalog", {}).get("content_sha256"),
            "production_recommendation_enabled": e2.get("catalog", {}).get(
                "production_recommendation_enabled"
            ),
        },
        "research_identity": research_identity(),
        "phase_boundary": {
            "current": "E3_1_PRESCRIPTION_POLICY_SEMANTIC_AND_REPRODUCIBILITY_GATE",
            "runtime_chatbot_behavior_changed": False,
            "not_implemented": [
                "personalized training-state planner",
                "workout log schema migration",
                "progression persistence",
                "context planner and chatbot integration",
            ],
            "next": "E4_PERSONALIZED_WORKOUT_PLANNER",
        },
    }
    semantic_content = {key: policy[key] for key in _SEMANTIC_CONTENT_KEYS}
    policy["content_sha256"] = content_sha256(semantic_content)
    policy["manifest_sha256"] = content_sha256(policy)
    return policy


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ExercisePrescriptionPolicyError("GIT_COMMIT_UNAVAILABLE") from exc


def load_policy() -> dict[str, Any]:
    try:
        payload = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExercisePrescriptionPolicyError("INVALID_E3_POLICY") from exc
    return payload


def verify_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = policy or load_policy()
    actual = build_policy(creation_commit=expected["creation_commit"])
    if actual != expected:
        differing = sorted(
            key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)
        )
        raise ExercisePrescriptionPolicyError(
            f"E3_POLICY_MISMATCH:{','.join(differing)}"
        )
    return {
        "ok": True,
        "policy_version": expected["schema_version"],
        "goals": len(expected["training_goals"]),
        "evidence_sources": len(expected["evidence_registry"]),
        "content_sha256": expected["content_sha256"],
        "manifest_sha256": expected["manifest_sha256"],
        "research_corpus": expected["research_identity"]["corpus_version"],
    }


def resolve_experience(
    *,
    explicit_experience: str | None,
    local_history_available: bool,
    history_signal: str = "UNAVAILABLE",
) -> dict[str, Any]:
    if not isinstance(local_history_available, bool):
        raise ExercisePrescriptionPolicyError("INVALID_HISTORY_AVAILABILITY")
    normalized_experience = (
        "UNKNOWN"
        if explicit_experience is None
        else str(explicit_experience).strip().upper()
    )
    normalized_history = str(history_signal).strip().upper()
    if normalized_experience not in EXPERIENCE_LEVELS:
        raise ExercisePrescriptionPolicyError("INVALID_EXPERIENCE_LEVEL")
    if normalized_history not in EXPERIENCE_HISTORY_SIGNALS:
        raise ExercisePrescriptionPolicyError("INVALID_HISTORY_SIGNAL")
    if not local_history_available and normalized_history not in {
        "UNAVAILABLE",
        "INSUFFICIENT",
    }:
        raise ExercisePrescriptionPolicyError("HISTORY_SIGNAL_WITHOUT_LOCAL_HISTORY")
    conflict = (
        normalized_experience in {"NOVICE", "EXPERIENCED"}
        and normalized_history in {"NOVICE", "EXPERIENCED"}
        and normalized_experience != normalized_history
    )
    return {
        "experience": normalized_experience,
        "experience_provenance": (
            "USER_REPORTED"
            if explicit_experience is not None
            and normalized_experience in {"NOVICE", "EXPERIENCED"}
            else "UNKNOWN_NOT_INFERRED"
        ),
        "operational_profile": (
            normalized_experience
            if normalized_experience in {"NOVICE", "EXPERIENCED"}
            else "CONSERVATIVE_DEFAULT"
        ),
        "local_history_available": local_history_available,
        "history_signal": normalized_history,
        "history_signal_provenance": "LOCAL_TRAINING_HISTORY",
        "signals_conflict": conflict,
        "semantic_status": "CONFLICTING_SIGNALS" if conflict else "RESOLVED",
    }


def resolve_goal_domain(term: str, *, context: str | None = None) -> dict[str, Any]:
    normalized = " ".join(str(term).strip().casefold().split())
    normalized_context = None if context is None else str(context).strip().upper()
    if normalized_context not in {None, "RESISTANCE", "AEROBIC"}:
        raise ExercisePrescriptionPolicyError("INVALID_GOAL_CONTEXT")
    muscular_explicit = {
        "muscular_endurance",
        "muscular endurance",
        "sức bền cơ",
        "sức bền cơ bắp",
    }
    aerobic_explicit = {
        "aerobic_endurance",
        "aerobic endurance",
        "sức bền tim mạch",
        "cardiorespiratory endurance",
    }
    ambiguous = {"sức bền", "tăng endurance", "endurance"}
    if normalized in muscular_explicit:
        return {"status": "RESOLVED", "goal": "MUSCULAR_ENDURANCE", "domain": "RESISTANCE"}
    if normalized in aerobic_explicit:
        return {"status": "RESOLVED", "goal": "AEROBIC_ENDURANCE", "domain": "AEROBIC"}
    if normalized in ambiguous:
        if normalized_context == "RESISTANCE":
            return {"status": "RESOLVED", "goal": "MUSCULAR_ENDURANCE", "domain": "RESISTANCE"}
        if normalized_context == "AEROBIC":
            return {"status": "RESOLVED", "goal": "AEROBIC_ENDURANCE", "domain": "AEROBIC"}
        return {
            "status": "CLARIFICATION_REQUIRED",
            "goal": None,
            "domain": None,
            "question": "Bạn muốn tăng sức bền cơ khi tập kháng lực hay sức bền tim mạch/aerobic?",
        }
    upper = str(term).strip().upper()
    if upper in GOALS:
        return {"status": "RESOLVED", "goal": upper, "domain": "RESISTANCE"}
    if upper == "AEROBIC_ENDURANCE":
        return {"status": "RESOLVED", "goal": upper, "domain": "AEROBIC"}
    raise ExercisePrescriptionPolicyError("INVALID_TRAINING_GOAL")


def catalog_eligibility(record: dict[str, Any]) -> dict[str, Any]:
    statuses: list[str] = []
    instructions_complete = bool((record.get("instructions") or {}).get("text"))
    muscles_known = bool(record.get("primary_muscles"))
    movement = (record.get("movement_pattern") or {}).get("value")
    movement_known = bool(movement and movement != "UNKNOWN")
    substitution_available = bool(
        (record.get("substitution_group") or {}).get("value")
    )
    difficulty = (record.get("difficulty") or {}).get("value")
    if not instructions_complete:
        statuses.append("INSTRUCTION_INCOMPLETE")
    if not muscles_known:
        statuses.append("MUSCLE_UNKNOWN")
    if not movement_known:
        statuses.append("MOVEMENT_UNKNOWN")
    if not substitution_available:
        statuses.append("SUBSTITUTION_UNAVAILABLE")
    if difficulty in {"ADVANCED", "UNSPECIFIED", None}:
        statuses.append("REQUIRES_EXPERIENCE_CONFIRMATION")
    structural_blockers = {
        "INSTRUCTION_INCOMPLETE",
        "MUSCLE_UNKNOWN",
        "MOVEMENT_UNKNOWN",
    }
    if structural_blockers.intersection(statuses):
        statuses.insert(0, "SEARCH_ONLY")
    else:
        statuses.insert(0, "PRESCRIPTION_ELIGIBLE")
    return {
        "exercise_id": record.get("exercise_id"),
        "statuses": statuses,
        "missing_metadata_filled": False,
        "structurally_prescription_eligible": statuses[0] == "PRESCRIPTION_ELIGIBLE",
        "catalog_review_status": record.get("review_status"),
        "policy_version": POLICY_VERSION,
    }


def _catalog_eligibility_summary() -> dict[str, Any]:
    counts = {
        status: 0
        for status in (
            "PRESCRIPTION_ELIGIBLE",
            "SEARCH_ONLY",
            "INSTRUCTION_INCOMPLETE",
            "MUSCLE_UNKNOWN",
            "MOVEMENT_UNKNOWN",
            "SUBSTITUTION_UNAVAILABLE",
            "REQUIRES_EXPERIENCE_CONFIRMATION",
        )
    }
    catalog = load_canonical_exercise_catalog()
    for record in catalog:
        for status in catalog_eligibility(record)["statuses"]:
            counts[status] += 1
    return {"record_count": len(catalog), "status_counts": counts}


def prescription_for(
    goal: str,
    experience: str,
    *,
    local_history_available: bool = False,
    history_signal: str = "UNAVAILABLE",
) -> dict[str, Any]:
    normalized_goal = str(goal).strip().upper()
    if normalized_goal not in GOALS:
        raise ExercisePrescriptionPolicyError("INVALID_TRAINING_GOAL")
    experience_resolution = resolve_experience(
        explicit_experience=experience,
        local_history_available=local_history_available,
        history_signal=history_signal,
    )
    normalized_experience = experience_resolution["experience"]
    profile = deepcopy(load_policy()["goal_profiles"][normalized_goal])
    if normalized_goal == "POWER":
        eligibility = profile["eligibility"][normalized_experience]
    else:
        eligibility = "ELIGIBLE_AFTER_SAFETY_GATE"
    return {
        "policy_version": POLICY_VERSION,
        "goal": normalized_goal,
        "requested_experience": normalized_experience,
        "effective_experience": normalized_experience,
        "experience_assumed": False,
        "operational_profile": experience_resolution["operational_profile"],
        "experience_resolution": experience_resolution,
        "eligibility": eligibility,
        "prescription": profile,
    }


def safety_gate(
    *,
    age: int | None,
    symptoms: Iterable[str] = (),
    health_state: str = "HEALTHY_GENERAL",
    pregnancy_status: str = "NOT_APPLICABLE",
) -> dict[str, Any]:
    symptom_set = {str(item).strip().upper() for item in symptoms}
    unknown_symptoms = symptom_set - _EMERGENCY_SYMPTOMS
    if unknown_symptoms:
        raise ExercisePrescriptionPolicyError("INVALID_WARNING_SYMPTOM")
    if symptom_set:
        return {
            "status": "STOP_AND_SEEK_MEDICAL_EVALUATION",
            "reason_codes": sorted(symptom_set),
            "ordinary_planner_allowed": False,
        }
    if age is None or health_state == "UNKNOWN" or pregnancy_status == "UNKNOWN":
        return {
            "status": "NEEDS_CLARIFICATION",
            "reason_codes": ["MISSING_SAFETY_CONTEXT"],
            "ordinary_planner_allowed": False,
        }
    if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
        raise ExercisePrescriptionPolicyError("INVALID_AGE")
    normalized_health = health_state.strip().upper()
    normalized_pregnancy = pregnancy_status.strip().upper()
    reasons: list[str] = []
    if age < 18:
        reasons.append("UNDER_18_OUTSIDE_POLICY")
    if normalized_health in _PROFESSIONAL_GUIDANCE_STATES:
        reasons.append(normalized_health)
    elif normalized_health != "HEALTHY_GENERAL":
        raise ExercisePrescriptionPolicyError("INVALID_HEALTH_STATE")
    if normalized_pregnancy in {"PREGNANT", "POSTPARTUM"}:
        reasons.append(f"{normalized_pregnancy}_OUTSIDE_POLICY")
    elif normalized_pregnancy != "NOT_APPLICABLE":
        raise ExercisePrescriptionPolicyError("INVALID_PREGNANCY_STATUS")
    if reasons:
        return {
            "status": "REQUIRES_PROFESSIONAL_GUIDANCE",
            "reason_codes": reasons,
            "ordinary_planner_allowed": False,
        }
    return {
        "status": "SUPPORTED",
        "reason_codes": [],
        "ordinary_planner_allowed": True,
    }


def evaluate_progression(
    *,
    completed_all_sets: bool,
    reached_top_of_rep_range: bool,
    recorded_rir: float | None,
    technique_stable: bool,
    pain_reported: bool,
    consecutive_successes: int,
    consecutive_misses: int,
    region: str,
    prior_history_available: bool = True,
) -> dict[str, Any]:
    if not isinstance(prior_history_available, bool):
        raise ExercisePrescriptionPolicyError("INVALID_HISTORY_AVAILABILITY")
    rule_metadata = {
        "rule_id": "E3_1_DOUBLE_PROGRESSION_LOAD",
        "policy_version": POLICY_VERSION,
        "evidence_status": "PRODUCT_HEURISTIC",
        "required_observations": [
            "prior_prescription_and_result_available",
            "set_completion",
            "rep_range_position",
            "recorded_rir",
            "technique_stability",
            "pain_status",
            "consecutive_exposure_count",
        ],
        "failure_behavior": "HOLD_UNLESS_REGRESSION_OR_SAFETY_RULE_APPLIES",
    }
    normalized_region = region.strip().lower()
    if normalized_region not in {"upper_body", "lower_body"}:
        raise ExercisePrescriptionPolicyError("INVALID_PROGRESSION_REGION")
    if consecutive_successes < 0 or consecutive_misses < 0:
        raise ExercisePrescriptionPolicyError("INVALID_EXPOSURE_COUNT")
    if recorded_rir is not None and (
        isinstance(recorded_rir, bool)
        or not isinstance(recorded_rir, (int, float))
        or not math.isfinite(recorded_rir)
        or recorded_rir < 0
        or recorded_rir > 10
    ):
        raise ExercisePrescriptionPolicyError("INVALID_RIR")
    if pain_reported:
        return {
            **rule_metadata,
            "decision": "SAFETY_STOP",
            "load_change_percent": None,
            "previous_load_kg": None,
            "reason": "Pain is evaluated by the safety gate, not automatic load regression.",
        }
    if not prior_history_available:
        return {
            **rule_metadata,
            "decision": "PROGRESSION_UNAVAILABLE",
            "load_change_percent": None,
            "previous_load_kg": None,
            "reason": "No prior prescription/result exists; previous load is not inferred.",
        }
    if not technique_stable:
        return {
            **rule_metadata,
            "decision": "HOLD_OR_REDUCE_FOR_TECHNIQUE",
            "load_change_percent": [0, -10],
            "previous_load_kg": None,
            "reason": "Technique stability is required before progression.",
        }
    if consecutive_misses >= 2 and (not completed_all_sets or not reached_top_of_rep_range):
        return {
            **rule_metadata,
            "decision": "REGRESS_LOAD_OR_VOLUME",
            "load_change_percent": [-5, -10],
            "volume_change_percent": [-20, -30],
            "previous_load_kg": None,
            "reason": "Two consecutive misses trigger a conservative regression.",
        }
    eligible = (
        completed_all_sets
        and reached_top_of_rep_range
        and recorded_rir is not None
        and recorded_rir >= 2
        and consecutive_successes >= 2
    )
    if eligible:
        increase = [2.5, 5.0] if normalized_region == "upper_body" else [2.5, 7.5]
        return {
            **rule_metadata,
            "decision": "PROGRESSION_ELIGIBLE",
            "load_change_percent": increase,
            "previous_load_kg": None,
            "reason": "Double-progression criteria were met twice without pain or technique loss.",
        }
    return {
        **rule_metadata,
        "decision": "HOLD",
        "load_change_percent": [0, 0],
        "previous_load_kg": None,
        "reason": "Progression criteria are incomplete; repeat the prescription.",
    }


def missed_session_action(
    *, missed_sessions: int, days_since_last_session: int, illness_or_injury: bool = False
) -> dict[str, Any]:
    if missed_sessions < 0 or days_since_last_session < 0:
        raise ExercisePrescriptionPolicyError("INVALID_MISSED_SESSION_STATE")
    if illness_or_injury:
        return {
            "decision": "SAFETY_GATE_REQUIRED",
            "make_up_volume": False,
            "load_change_percent": None,
            "volume_change_percent": None,
        }
    if missed_sessions == 0:
        return {
            "decision": "CONTINUE_PLAN",
            "make_up_volume": False,
            "load_change_percent": [0, 0],
            "volume_change_percent": [0, 0],
        }
    if missed_sessions == 1 and days_since_last_session < 7:
        return {
            "decision": "RESUME_NEXT_PLANNED_SESSION",
            "make_up_volume": False,
            "load_change_percent": [0, 0],
            "volume_change_percent": [0, 0],
        }
    return {
        "decision": "REDUCED_RETURN_SESSION",
        "make_up_volume": False,
        "load_change_percent": [-5, -10],
        "volume_change_percent": [-20, -30],
    }


def substitution_decision(
    source: dict[str, Any],
    candidate: dict[str, Any],
    *,
    available_equipment_ids: Iterable[int],
) -> dict[str, Any]:
    if source.get("exercise_id") == candidate.get("exercise_id"):
        return {"decision": "NOT_A_SUBSTITUTION", "reason": "SAME_EXERCISE"}
    source_pattern = (source.get("movement_pattern") or {}).get("value")
    candidate_pattern = (candidate.get("movement_pattern") or {}).get("value")
    if not source_pattern or source_pattern == "UNKNOWN" or source_pattern != candidate_pattern:
        return {"decision": "INCOMPATIBLE", "reason": "MOVEMENT_PATTERN_MISMATCH"}
    source_muscles = {int(item["id"]) for item in source.get("primary_muscles") or []}
    candidate_muscles = {int(item["id"]) for item in candidate.get("primary_muscles") or []}
    if not source_muscles.intersection(candidate_muscles):
        return {"decision": "INCOMPATIBLE", "reason": "PRIMARY_MUSCLE_MISMATCH"}
    available = {int(item) for item in available_equipment_ids}
    required = {int(item["id"]) for item in candidate.get("equipment") or []}
    if not required.issubset(available):
        return {"decision": "INCOMPATIBLE", "reason": "EQUIPMENT_UNAVAILABLE"}
    curated = [
        candidate.get("movement_pattern") or {},
        candidate.get("difficulty") or {},
        candidate.get("laterality") or {},
    ]
    if any(item.get("human_reviewed") is not True for item in curated):
        return {
            "decision": "REVIEW_REQUIRED",
            "reason": "E2_CURATED_METADATA_UNREVIEWED",
        }
    return {
        "decision": "ELIGIBLE_AFTER_SAFETY_AND_PREFERENCE_CHECK",
        "reason": "CATALOG_CONSTRAINTS_MATCH",
    }


def map_activity_to_compendium(activity_key: str) -> dict[str, Any]:
    normalized = str(activity_key).strip().upper()
    mapping = _ACTIVITY_TO_COMPENDIUM.get(normalized)
    if mapping is None:
        return {
            "activity_key": normalized,
            "mapping_status": "UNMAPPED_ACTIVITY",
            "compendium_code": None,
            "rationale": "No reviewed direct or app-curated mapping exists.",
            "policy_version": POLICY_VERSION,
        }
    return {
        "activity_key": normalized,
        **deepcopy(mapping),
        "policy_version": POLICY_VERSION,
    }


def estimate_session_energy(
    *, activity_code: str, weight_kg: float, duration_minutes: float, age: int
) -> dict[str, Any]:
    if activity_code not in _SESSION_MET_CODES:
        raise ExercisePrescriptionPolicyError("UNSUPPORTED_COMPENDIUM_ACTIVITY_CODE")
    for value, error in (
        (weight_kg, "INVALID_WEIGHT"),
        (duration_minutes, "INVALID_DURATION"),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ExercisePrescriptionPolicyError(error)
    if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
        raise ExercisePrescriptionPolicyError("INVALID_AGE")
    record = _SESSION_MET_CODES[activity_code]
    if age < 19 or age > 59:
        return {
            "status": "AGE_APPROPRIATE_TABLE_REQUIRED",
            "estimated_energy_expenditure_kcal": None,
            "activity_code": activity_code,
            "source": _COMPENDIUM_2024,
            "mapping_status": "DIRECT_SUPPORTED_MAPPING",
            "reason": "The 2024 Adult Compendium table used here covers ages 19-59.",
        }
    kcal = float(record["met"]) * 3.5 * float(weight_kg) / 200 * float(duration_minutes)
    return {
        "status": "ESTIMATE_AVAILABLE",
        "estimated_energy_expenditure_kcal": round(kcal, 2),
        "activity_code": activity_code,
        "activity": record["activity"],
        "met": record["met"],
        "duration_minutes": float(duration_minutes),
        "weight_kg": float(weight_kg),
        "source": _COMPENDIUM_2024,
        "mapping_status": "DIRECT_SUPPORTED_MAPPING",
        "estimated": True,
        "measurement": False,
        "granularity": "SESSION_ACTIVITY_LEVEL",
    }


def estimate_mapped_session_energy(
    *, activity_key: str, weight_kg: float, duration_minutes: float, age: int
) -> dict[str, Any]:
    mapping = map_activity_to_compendium(activity_key)
    code = mapping["compendium_code"]
    if code is None:
        return {
            "status": "NO_CALORIE_ESTIMATE",
            "estimated_energy_expenditure_kcal": None,
            "mapping": mapping,
            "estimated": False,
        }
    estimate = estimate_session_energy(
        activity_code=code,
        weight_kg=weight_kg,
        duration_minutes=duration_minutes,
        age=age,
    )
    estimate["mapping_status"] = mapping["mapping_status"]
    estimate["mapping"] = mapping
    return estimate


__all__ = [
    "EVIDENCE_REVIEW_DATE",
    "EXPERIENCE_LEVELS",
    "GOALS",
    "POLICY_FILE",
    "POLICY_VERSION",
    "ExercisePrescriptionPolicyError",
    "build_policy",
    "catalog_eligibility",
    "canonical_json_bytes",
    "content_sha256",
    "estimate_mapped_session_energy",
    "estimate_session_energy",
    "evaluate_progression",
    "load_policy",
    "map_activity_to_compendium",
    "missed_session_action",
    "prescription_for",
    "resolve_experience",
    "resolve_goal_domain",
    "safety_gate",
    "substitution_decision",
    "verify_policy",
]
