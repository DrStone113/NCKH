"""P1 development scenario inventory (non-research engineering fixtures).

These are testable classifications, not a clinical dataset and not a research
outcome.  The matrix intentionally separates expected READY, clarification,
and conflict outcomes so shadow comparison can detect a safety regression.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanDevelopmentScenario:
    scenario_id: str
    area: str
    expected_outcome: str


_AREAS: dict[str, tuple[str, ...]] = {
    "nutrition_single_day": ("normal", "allergy", "dietary_restriction", "food_exclusion", "missing_profile", "specialist_gate"),
    "nutrition_week": ("normal", "variety", "timezone_boundary", "food_exclusion", "missing_input", "policy_provenance"),
    "workout_single": ("home", "gym", "equipment_limit", "unknown_experience", "pain_gate", "safety_gate"),
    "workout_week": ("one_day_available", "three_day_available", "missing_availability", "timezone_boundary", "e4_gate", "history_context"),
    "combined_reference": ("nutrition_and_workout", "child_missing", "no_energy_compensation", "independent_validation", "timezone", "read_only"),
    "revision_patch": ("change_meal", "change_workout", "move_schedule", "cancel_item", "change_time", "change_duration"),
    "lifecycle": ("draft", "pending_confirmation", "save", "activate", "pause", "resume", "complete", "cancel"),
    "write_integrity": ("duplicate_confirmation", "network_retry", "two_devices", "stale_revision", "cross_user", "hash_mismatch"),
    "actual_separation": ("planned_meal_not_consumed", "planned_workout_not_completed", "no_actual_reps", "no_consumed_at", "no_daily_total_mutation", "no_training_history_mutation"),
    "legacy_migration": ("readable", "migratable", "unversioned", "invalid", "no_recalculation", "explicit_edit_only"),
    "trace_presentation": ("public_read", "public_revision", "debug_ids", "day_cards", "text_fallback", "redaction"),
    "policy_invariance": ("nutrition_v101", "exercise_v110", "e2_catalog", "food_catalog", "research_a", "research_b", "research_c"),
    "context_states": ("known", "missing", "not_loaded", "stale", "error", "conflict", "unknown"),
    "date_semantics": ("asia_ho_chi_minh", "utc_boundary", "monday_local", "period_start", "period_end", "invalid_timezone"),
    "validator": ("canonical_dish", "canonical_exercise", "out_of_period", "duplicate_item", "hard_block", "soft_variety"),
    "tool_surface": ("no_low_level_create", "no_append_items", "bounded_request", "no_raw_totals", "no_formula_input", "owner_bound"),
    "active_semantics": ("nutrition_overlap", "workout_overlap", "different_domain", "supersede_old", "active_read", "no_silent_merge"),
}


def development_scenarios() -> tuple[PlanDevelopmentScenario, ...]:
    scenarios: list[PlanDevelopmentScenario] = []
    for area, cases in _AREAS.items():
        for case in cases:
            outcome = "CLARIFICATION_OR_BLOCK" if any(
                marker in case
                for marker in ("missing", "gate", "stale", "cross_user", "mismatch", "invalid", "not_loaded", "error", "conflict")
            ) else "READY_OR_INVARIANT"
            scenarios.append(PlanDevelopmentScenario(f"P1-{area}-{case}", area, outcome))
    return tuple(scenarios)


__all__ = ["PlanDevelopmentScenario", "development_scenarios"]
