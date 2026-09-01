"""Deterministic E4.0 personalized workout planner.

This module is deliberately not registered as a chatbot tool.  It consumes the
frozen E2 catalog and E3.1 policy and has no write path.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from modules.wger.canonical_exercises import CATALOG_VERSION, load_canonical_exercise_catalog
from modules.wger.exercise_prescription_policy import (
    POLICY_VERSION,
    catalog_eligibility,
    estimate_mapped_session_energy,
    evaluate_progression,
    load_policy,
    prescription_for,
    resolve_goal_domain,
    safety_gate,
    substitution_decision,
)
from services.workout_planner.contracts import (
    ApplicabilityStatus,
    EnergyEstimate,
    ExercisePrescription,
    ExerciseProfile,
    FilterStage,
    PainStatus,
    PlannedExercise,
    PriorityComponent,
    ProgressionStatus,
    SafetyDecision,
    SessionRequirement,
    StateStatus,
    SubstitutionResult,
    TimeBudgetStatus,
    TrainingExperience,
    TrainingState,
    WorkoutPlan,
    WorkoutRequest,
)


PLANNER_VERSION = "deterministic-workout-planner-v1.0.0-shadow"
TIME_MODEL_VERSION = "workout-time-model-v1.0.0"
TIME_ASSUMPTIONS = {
    "session_overhead_seconds": 300,
    "execution_seconds_per_set": 45,
    "transition_seconds_per_exercise": 60,
    "equipment_setup_seconds": 30,
}

_MULTI_JOINT = {
    "SQUAT", "HINGE", "HORIZONTAL_PUSH", "HORIZONTAL_PULL", "VERTICAL_PUSH", "VERTICAL_PULL",
}
_GOAL_ALIASES = {
    "GENERAL": "GENERAL_FITNESS",
    "GENERAL_FITNESS": "GENERAL_FITNESS",
    "STRENGTH": "STRENGTH",
    "MUSCLE_GAIN": "HYPERTROPHY",
    "GAIN_MUSCLE": "HYPERTROPHY",
    "HYPERTROPHY": "HYPERTROPHY",
    "MUSCULAR_ENDURANCE": "MUSCULAR_ENDURANCE",
    "WEIGHT_LOSS": "WEIGHT_MANAGEMENT",
    "LOSE_WEIGHT": "WEIGHT_MANAGEMENT",
    "WEIGHT_MANAGEMENT": "WEIGHT_MANAGEMENT",
    "RECOVERY": "MOBILITY",
    "MOBILITY": "MOBILITY",
    "POWER": "POWER",
}
_EQUIPMENT_ALIASES = {
    "none": "none (bodyweight exercise)",
    "bodyweight": "none (bodyweight exercise)",
    "bodyweight only": "none (bodyweight exercise)",
    "dumbbells": "dumbbell",
    "resistance bands": "resistance band",
    "pullup bar": "pull-up bar",
    "pull up bar": "pull-up bar",
    "ez bar": "sz-bar",
}
_BODY_AREA = {
    "chest": ({"Chest"}, {"HORIZONTAL_PUSH"}),
    "nguc": ({"Chest"}, {"HORIZONTAL_PUSH"}),
    "back": ({"Back"}, {"HORIZONTAL_PULL", "VERTICAL_PULL"}),
    "lung": ({"Back"}, {"HORIZONTAL_PULL", "VERTICAL_PULL"}),
    "legs": ({"Legs", "Calves"}, {"SQUAT", "HINGE", "CALF_RAISE"}),
    "chan": ({"Legs", "Calves"}, {"SQUAT", "HINGE", "CALF_RAISE"}),
    "arms": ({"Arms"}, {"ELBOW_FLEXION", "ELBOW_EXTENSION"}),
    "tay": ({"Arms"}, {"ELBOW_FLEXION", "ELBOW_EXTENSION"}),
    "shoulders": ({"Shoulders"}, {"VERTICAL_PUSH", "SHOULDER_ISOLATION"}),
    "vai": ({"Shoulders"}, {"VERTICAL_PUSH", "SHOULDER_ISOLATION"}),
    "core": ({"Abs"}, {"CORE_FLEXION", "CORE_ANTI_EXTENSION", "CORE_ANTI_ROTATION"}),
    "abs": ({"Abs"}, {"CORE_FLEXION", "CORE_ANTI_EXTENSION", "CORE_ANTI_ROTATION"}),
    "full_body": (set(), set()),
    "full body": (set(), set()),
}


def _norm(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _equipment(values: Iterable[str]) -> tuple[str, ...]:
    normalized = {_EQUIPMENT_ALIASES.get(_norm(item), _norm(item)) for item in values if str(item).strip()}
    return tuple(sorted(normalized))


def _names(record: dict[str, Any]) -> set[str]:
    return {
        _norm(value)
        for value in (record.get("exercise_id"), record.get("name_en"), record.get("name_vi"), str(record.get("source_exercise_id")))
        if value
    }


def _goal(profile: ExerciseProfile, request: WorkoutRequest) -> dict[str, Any]:
    raw = request.goal_override
    if raw is None and profile.goal_status == StateStatus.KNOWN:
        raw = profile.goal
    if raw is None:
        return {"status": "CLARIFICATION_REQUIRED", "goal": None, "domain": None}
    alias = _GOAL_ALIASES.get(str(raw).strip().upper())
    if alias:
        return {"status": "RESOLVED", "goal": alias, "domain": "RESISTANCE"}
    return resolve_goal_domain(str(raw), context=request.goal_context)


def evaluate_safety(profile: ExerciseProfile) -> SafetyDecision:
    safety = profile.exercise_safety_profile
    if profile.current_pain_status == PainStatus.UNKNOWN:
        return SafetyDecision(
            ApplicabilityStatus.NEEDS_CLARIFICATION,
            ("CURRENT_PAIN_STATUS_UNKNOWN",),
            "NEEDS_CLARIFICATION",
            False,
            ("E3_1_SAFETY_GATE",),
        )
    if safety.warning_symptoms_status in {StateStatus.NOT_LOADED, StateStatus.MISSING, StateStatus.ERROR, StateStatus.STALE, StateStatus.UNKNOWN}:
        return SafetyDecision(
            ApplicabilityStatus.NEEDS_CLARIFICATION,
            ("SAFETY_INFORMATION_UNKNOWN",),
            "NEEDS_CLARIFICATION",
            False,
            ("E3_1_SAFETY_GATE",),
        )
    if safety.warning_symptoms:
        e3 = safety_gate(
            age=safety.age,
            symptoms=safety.warning_symptoms,
            health_state="HEALTHY_GENERAL",
            pregnancy_status="NOT_APPLICABLE",
        )
        return SafetyDecision(
            ApplicabilityStatus.UNSUPPORTED,
            tuple(e3["reason_codes"]),
            e3["status"],
            False,
            ("E3_1_SAFETY_GATE", "WARNING_SYMPTOMS_NON_OVERRIDABLE"),
        )
    health_state = safety.health_state
    if safety.acute_injury is True:
        health_state = "ACUTE_INJURY"
    elif safety.recent_surgery is True:
        health_state = "RECENT_SURGERY"
    elif profile.current_pain_status == PainStatus.SIGNIFICANT_CURRENT_PAIN:
        health_state = "SEVERE_OR_WORSENING_PAIN"
    elif safety.health_state_status != StateStatus.KNOWN:
        health_state = "UNKNOWN"
    age = safety.age if safety.age_status == StateStatus.KNOWN else None
    pregnancy = safety.pregnancy_status if safety.pregnancy_state_status == StateStatus.KNOWN else "UNKNOWN"
    e3 = safety_gate(age=age, symptoms=(), health_state=health_state, pregnancy_status=pregnancy)
    mapping = {
        "SUPPORTED": ApplicabilityStatus.SUPPORTED,
        "NEEDS_CLARIFICATION": ApplicabilityStatus.NEEDS_CLARIFICATION,
        "REQUIRES_PROFESSIONAL_GUIDANCE": ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE,
        "STOP_AND_SEEK_MEDICAL_EVALUATION": ApplicabilityStatus.UNSUPPORTED,
    }
    return SafetyDecision(
        mapping[e3["status"]], tuple(e3["reason_codes"]), e3["status"], bool(e3["ordinary_planner_allowed"]),
        ("E3_1_SAFETY_GATE",),
    )


def build_session_requirement(
    profile: ExerciseProfile,
    state: TrainingState,
    request: WorkoutRequest,
    safety: SafetyDecision,
) -> SessionRequirement:
    goal = _goal(profile, request)
    duration = request.requested_duration_minutes or profile.default_session_duration_minutes
    equipment = _equipment(request.available_equipment_override if request.available_equipment_override is not None else profile.available_equipment)
    reasons: list[str] = []
    if safety.status != ApplicabilityStatus.SUPPORTED:
        status = safety.status
    elif request.write_intent:
        status = ApplicabilityStatus.UNSUPPORTED
        reasons.append("WRITE_INTENT_FORBIDDEN_IN_E4_0")
    elif goal["status"] == "CLARIFICATION_REQUIRED":
        status = ApplicabilityStatus.NEEDS_CLARIFICATION
        reasons.append("AMBIGUOUS_OR_MISSING_GOAL")
    elif goal["domain"] == "AEROBIC":
        status = ApplicabilityStatus.UNSUPPORTED
        reasons.append("AEROBIC_DOMAIN_HANDOFF")
    elif duration is None or duration <= 0:
        status = ApplicabilityStatus.NEEDS_CLARIFICATION
        reasons.append("SESSION_DURATION_MISSING")
    elif not equipment:
        status = ApplicabilityStatus.NEEDS_CLARIFICATION
        reasons.append("AVAILABLE_EQUIPMENT_UNKNOWN")
    else:
        status = ApplicabilityStatus.SUPPORTED
    if goal.get("goal") == "POWER" and status == ApplicabilityStatus.SUPPORTED:
        if profile.training_experience != TrainingExperience.EXPERIENCED:
            status = ApplicabilityStatus.NEEDS_CLARIFICATION
            reasons.append("POWER_REQUIRES_CONFIRMED_EXPERIENCE")
        elif profile.exercise_safety_profile.technique_screen_confirmed is not True:
            status = ApplicabilityStatus.NEEDS_CLARIFICATION
            reasons.append("POWER_REQUIRES_TECHNIQUE_SCREEN")
    target_muscles: set[str] = set()
    target_movements: set[str] = set()
    if request.requested_body_area:
        target_muscles, target_movements = _BODY_AREA.get(_norm(request.requested_body_area), (set(), set()))
    policy_rule_ids: tuple[str, ...] = ()
    volume: tuple[int, int] | None = None
    effort: tuple[int, int] | None = None
    rests: tuple[tuple[str, tuple[int, int]], ...] = ()
    if goal.get("goal") and goal.get("domain") == "RESISTANCE":
        result = prescription_for(
            goal["goal"], profile.training_experience.value,
            local_history_available=profile.local_history_available,
            history_signal="UNAVAILABLE" if not profile.local_history_available else "INSUFFICIENT",
        )
        prescription = result["prescription"]
        operational = profile.training_experience.value if profile.training_experience != TrainingExperience.UNKNOWN else "NOVICE"
        sets_value = prescription.get("sets_per_exercise") or {}
        if isinstance(sets_value, dict):
            selected_sets = sets_value.get(operational)
            volume = tuple(selected_sets) if selected_sets else None
        rir_value = prescription.get("target_rir") or {}
        if isinstance(rir_value, dict):
            selected_rir = rir_value.get(operational)
            effort = tuple(selected_rir) if selected_rir else None
        rests = tuple((key, tuple(value)) for key, value in (prescription.get("rest_seconds") or {}).items())
        policy_rule_ids = (f"E3_GOAL_PROFILE_{goal['goal']}", "E3_1_EXPERIENCE_SEMANTICS")
    if state.status != StateStatus.KNOWN:
        reasons.append("HISTORY_UNAVAILABLE")
    reasons.extend(safety.reason_codes)
    return SessionRequirement(
        status=status,
        goal=goal.get("goal"),
        goal_domain=goal.get("domain"),
        session_duration_budget=duration,
        required_equipment_constraints=equipment,
        allowed_exercise_eligibility=("PRESCRIPTION_ELIGIBLE",),
        target_muscle_priorities=tuple(sorted(target_muscles)),
        target_movement_priorities=tuple(sorted(target_movements)),
        avoid_reduce_priorities=tuple(sorted(request.temporary_preferences)),
        volume_budget=volume,
        effort_target=effort,
        rest_ranges=rests,
        progression_policy="E3_1_DOUBLE_PROGRESSION_LOAD" if goal.get("domain") == "RESISTANCE" else None,
        safety_restrictions=safety.reason_codes,
        selection_reason_codes=tuple(dict.fromkeys(reasons)),
        policy_rule_ids=policy_rule_ids,
    )


class PersonalizedWorkoutPlanner:
    """Pure deterministic planner over immutable input contracts."""

    def __init__(self, catalog: list[dict[str, Any]] | None = None) -> None:
        self._catalog = tuple(catalog or load_canonical_exercise_catalog())
        self._policy = load_policy()

    @staticmethod
    def _stage(candidates: list[dict[str, Any]], predicate: Any, stage: str, reason: str) -> tuple[list[dict[str, Any]], FilterStage]:
        before = len(candidates)
        kept = [item for item in candidates if predicate(item)]
        return kept, FilterStage(stage, before, before - len(kept), len(kept), reason)

    def _hard_filter(
        self, profile: ExerciseProfile, request: WorkoutRequest, requirement: SessionRequirement, safety: SafetyDecision,
    ) -> tuple[list[dict[str, Any]], tuple[FilterStage, ...]]:
        candidates = list(self._catalog)
        stages: list[FilterStage] = []
        candidates, stage = self._stage(candidates, lambda _: safety.status == ApplicabilityStatus.SUPPORTED, "SAFETY", "SAFETY_GATE")
        stages.append(stage)
        exclusions = {_norm(item) for item in profile.exercise_exclusions + request.exercise_exclude}
        candidates, stage = self._stage(candidates, lambda item: not (_names(item) & exclusions), "EXERCISE_EXCLUSIONS", "EXPLICIT_EXCLUSION")
        stages.append(stage)
        includes = {_norm(item) for item in request.exercise_include}
        candidates, stage = self._stage(candidates, lambda item: not includes or bool(_names(item) & includes), "EXERCISE_INCLUDES", "EXPLICIT_INCLUDE")
        stages.append(stage)
        available = set(requirement.required_equipment_constraints)

        def equipment_ok(item: dict[str, Any]) -> bool:
            required = {_norm(eq["name"]) for eq in item.get("equipment") or []}
            return bool(required) and required.issubset(available)

        candidates, stage = self._stage(candidates, equipment_ok, "AVAILABLE_EQUIPMENT", "EQUIPMENT_HARD_CONSTRAINT")
        stages.append(stage)
        location = _norm(request.requested_location or profile.training_location or "unknown")
        candidates, stage = self._stage(
            candidates,
            lambda item: location not in {"outdoors", "outdoor"} or {_norm(eq["name"]) for eq in item.get("equipment") or []} == {"none (bodyweight exercise)"},
            "LOCATION", "LOCATION_HARD_CONSTRAINT",
        )
        stages.append(stage)
        candidates, stage = self._stage(candidates, lambda item: catalog_eligibility(item)["structurally_prescription_eligible"], "CATALOG_ELIGIBILITY", "E3_1_PRESCRIPTION_ELIGIBLE")
        stages.append(stage)
        candidates, stage = self._stage(candidates, lambda item: bool((item.get("instructions") or {}).get("text")), "REQUIRED_INSTRUCTIONS", "INSTRUCTIONS_REQUIRED")
        stages.append(stage)

        def goal_domain_ok(item: dict[str, Any]) -> bool:
            movement = (item.get("movement_pattern") or {}).get("value")
            if requirement.goal == "MOBILITY":
                return movement == "MOBILITY"
            if requirement.goal == "POWER":
                return movement in {"SQUAT", "HINGE"}
            return movement not in {"CARDIO_OTHER", "LOCOMOTION", "MOBILITY"}

        candidates, stage = self._stage(candidates, goal_domain_ok, "GOAL_DOMAIN", "RESISTANCE_AEROBIC_SEPARATION")
        stages.append(stage)

        def experience_ok(item: dict[str, Any]) -> bool:
            difficulty = (item.get("difficulty") or {}).get("value")
            if requirement.goal == "POWER":
                return profile.training_experience == TrainingExperience.EXPERIENCED and profile.exercise_safety_profile.technique_screen_confirmed is True
            if difficulty == "ADVANCED":
                return profile.training_experience == TrainingExperience.EXPERIENCED
            return True  # UNSPECIFIED does not globally block ordinary E3.1 use.

        candidates, stage = self._stage(candidates, experience_ok, "EXPERIENCE_TECHNICAL_GATE", "CONTEXTUAL_EXPERIENCE_RULE")
        stages.append(stage)
        limitations = {_norm(item) for item in profile.self_reported_limitations}
        candidates, stage = self._stage(candidates, lambda item: not (_names(item) & limitations), "EXPLICIT_LIMITATIONS", "NO_DIAGNOSIS_EXPLICIT_NAME_ONLY")
        stages.append(stage)
        return candidates, tuple(stages)

    @staticmethod
    def _exposure(state: TrainingState, field: str) -> dict[str, int]:
        observation = getattr(state, field)
        if observation.status != StateStatus.KNOWN or observation.value is None:
            return {}
        return {str(key): int(value) for key, value in observation.value}

    def _rank(
        self, candidates: list[dict[str, Any]], profile: ExerciseProfile, state: TrainingState, request: WorkoutRequest, requirement: SessionRequirement,
    ) -> list[tuple[dict[str, Any], tuple[PriorityComponent, ...], int]]:
        muscle_exposure = self._exposure(state, "muscle_exposure_7d")
        movement_exposure = self._exposure(state, "movement_exposure_7d")
        last_dates = dict(state.last_exercise_performed_at.value or ()) if state.last_exercise_performed_at.status == StateStatus.KNOWN else {}
        preferred = {_norm(item) for item in profile.preferred_exercises}
        disliked = {_norm(item) for item in profile.disliked_exercises}
        included = {_norm(item) for item in request.exercise_include}
        ranked = []
        for item in candidates:
            components: list[PriorityComponent] = [PriorityComponent("E4_GOAL_COMPATIBILITY", 20, "E3_GOAL_PROFILE_PLUS_APP_RULE", "GOAL_MATCH")]
            movement = (item.get("movement_pattern") or {}).get("value") or "UNKNOWN"
            muscles = {muscle.get("name_en") or muscle.get("name") for muscle in item.get("primary_muscles") or []}
            category = (item.get("category") or {}).get("name")
            names = _names(item)
            if requirement.goal in {"STRENGTH", "HYPERTROPHY"} and movement in _MULTI_JOINT:
                components.append(PriorityComponent("E4_MULTI_JOINT_GOAL_PRIORITY", 16, "E3_EXERCISE_ORDER_PLUS_APP_RULE", "GOAL_PRIORITY_MULTI_JOINT"))
            if requirement.goal == "POWER" and movement in {"SQUAT", "HINGE"}:
                components.append(PriorityComponent("E4_POWER_MOVEMENT_ELIGIBILITY", 20, "E3_POWER_POLICY_PLUS_E2_MOVEMENT", "POWER_MOVEMENT_MATCH"))
            if requirement.goal == "MOBILITY" and movement == "MOBILITY":
                components.append(PriorityComponent("E4_MOBILITY_MOVEMENT_ELIGIBILITY", 20, "E3_MOBILITY_POLICY_PLUS_E2_MOVEMENT", "MOBILITY_MATCH"))
            if requirement.target_movement_priorities and movement in requirement.target_movement_priorities:
                components.append(PriorityComponent("E4_REQUESTED_MOVEMENT", 50, "CURRENT_TURN_REQUEST", "REQUESTED_BODY_AREA_MATCH"))
            if requirement.target_muscle_priorities and category in requirement.target_muscle_priorities:
                components.append(PriorityComponent("E4_REQUESTED_MUSCLE", 50, "CURRENT_TURN_REQUEST", "REQUESTED_BODY_AREA_MATCH"))
            if movement_exposure.get(movement, 0) == 0:
                components.append(PriorityComponent("E4_WEEKLY_MOVEMENT_VARIETY", 12, "PRODUCT_HEURISTIC", "MOVEMENT_VARIETY_TARGET"))
            elif movement_exposure.get(movement, 0) >= 2:
                components.append(PriorityComponent("E4_RECENT_MOVEMENT_EXPOSURE", -12, "AUTHORITATIVE_HISTORY", "RECENTLY_TRAINED"))
            if muscles and all(muscle_exposure.get(muscle, 0) == 0 for muscle in muscles):
                components.append(PriorityComponent("E4_UNDEREXPOSED_MUSCLE", 15, "SOFT_PLANNING_TARGET", "UNDEREXPOSED_MUSCLE_GROUP"))
            last = last_dates.get(item["exercise_id"])
            if isinstance(last, datetime) and state.sessions_last_7d.computed_at - last <= timedelta(days=3):
                components.append(PriorityComponent("E4_RECENT_EXACT_EXERCISE", -20, "AUTHORITATIVE_HISTORY", "RECENT_EXERCISE_REPETITION"))
            if names & preferred:
                components.append(PriorityComponent("E4_PERSISTENT_PREFERENCE", 18, "PROFILE", "USER_PREFERENCE"))
            if names & disliked:
                components.append(PriorityComponent("E4_PERSISTENT_DISLIKE", -25, "PROFILE", "USER_DISLIKE"))
            if names & included:
                components.append(PriorityComponent("E4_CURRENT_TURN_INCLUDE", 80, "CURRENT_TURN_REQUEST", "EXPLICIT_INCLUDE"))
            equipment_count = len(item.get("equipment") or [])
            components.append(PriorityComponent("E4_TIME_EFFICIENCY", 8 if equipment_count == 1 else 2, "TIME_MODEL_PRODUCT_HEURISTIC", "TIME_EFFICIENT_SETUP"))
            ranked.append((item, tuple(components), sum(component.priority for component in components)))
        return sorted(ranked, key=lambda row: (-row[2], row[0]["exercise_id"]))

    def _prescription(self, goal: str, experience: TrainingExperience, movement: str) -> ExercisePrescription:
        profile = self._policy["goal_profiles"][goal]
        operational = experience.value if experience != TrainingExperience.UNKNOWN else "NOVICE"
        sets_rule = profile.get("sets_per_exercise") or {}
        sets_range = sets_rule.get(operational) if isinstance(sets_rule, dict) else None
        sets = int(sets_range[0]) if sets_range else 1
        reps_rule = profile.get("repetition_range")
        if isinstance(reps_rule, dict):
            rep_value = reps_rule.get(operational)
        else:
            rep_value = reps_rule
        rep_range = tuple(rep_value) if rep_value else None
        rest_rule = profile.get("rest_seconds") or {}
        if "as_needed" in rest_rule:
            rest = tuple(rest_rule["as_needed"])
        elif movement in _MULTI_JOINT:
            rest = tuple(rest_rule.get("multi_joint") or rest_rule.get("priority_lift") or rest_rule.get("power_lift"))
        else:
            rest = tuple(rest_rule.get("accessory") or next(iter(rest_rule.values())))
        rir_rule = profile.get("target_rir") or {}
        rir_value = rir_rule.get(operational) if isinstance(rir_rule, dict) else rir_rule
        return ExercisePrescription(
            sets=sets,
            rep_range=rep_range,
            rest_range_seconds=rest,
            effort_target_rir=tuple(rir_value) if rir_value else None,
            rpe_semantics="RIR_IS_SELF_REPORTED_APPROXIMATION_NOT_PHYSIOLOGICAL_MEASUREMENT" if rir_value else "NOT_APPLICABLE",
            policy_rule_ids=(f"E3_GOAL_PROFILE_{goal}_SETS", f"E3_GOAL_PROFILE_{goal}_REPS", f"E3_GOAL_PROFILE_{goal}_REST", f"E3_GOAL_PROFILE_{goal}_RIR"),
        )

    @staticmethod
    def _exercise_minutes(prescription: ExercisePrescription, equipment_count: int) -> float:
        seconds = prescription.sets * TIME_ASSUMPTIONS["execution_seconds_per_set"]
        seconds += max(0, prescription.sets - 1) * prescription.rest_range_seconds[0]
        seconds += TIME_ASSUMPTIONS["transition_seconds_per_exercise"]
        if equipment_count:
            seconds += TIME_ASSUMPTIONS["equipment_setup_seconds"]
        return round(seconds / 60, 2)

    @staticmethod
    def _progression(item: dict[str, Any], prescription: ExercisePrescription, state: TrainingState) -> tuple[ProgressionStatus, tuple[str, ...]]:
        if state.exercise_performance_history.status != StateStatus.KNOWN:
            return ProgressionStatus.PROGRESSION_UNAVAILABLE, ("HISTORY_UNAVAILABLE", "NO_PRIOR_RELEVANT_PERFORMANCE")
        histories = [value for value in state.exercise_performance_history.value if value.canonical_exercise_id == item["exercise_id"]]
        if not histories:
            return ProgressionStatus.PROGRESSION_UNAVAILABLE, ("NO_PRIOR_RELEVANT_PERFORMANCE",)
        prior = histories[-1]
        required = (
            prior.completed_sets is not None, prior.prescribed_sets is not None, bool(prior.reps), prior.rir is not None,
            prior.technique_stable is not None, prior.pain_reported is not None,
        )
        if not all(required) or prescription.rep_range is None:
            return ProgressionStatus.PROGRESSION_UNAVAILABLE, ("REQUIRED_OBSERVATIONS_MISSING",)
        decision = evaluate_progression(
            completed_all_sets=prior.completed_sets == prior.prescribed_sets,
            reached_top_of_rep_range=bool(prior.reps) and min(prior.reps) >= prescription.rep_range[1],
            recorded_rir=prior.rir,
            technique_stable=bool(prior.technique_stable),
            pain_reported=bool(prior.pain_reported),
            consecutive_successes=prior.consecutive_successes,
            consecutive_misses=prior.consecutive_misses,
            region="lower_body" if (item.get("category") or {}).get("name") in {"Legs", "Calves"} else "upper_body",
            prior_history_available=True,
        )
        mapped = {
            "PROGRESSION_ELIGIBLE": ProgressionStatus.PROGRESSION_AVAILABLE,
            "HOLD": ProgressionStatus.MAINTAIN,
            "HOLD_OR_REDUCE_FOR_TECHNIQUE": ProgressionStatus.REGRESSION,
            "REGRESS_LOAD_OR_VOLUME": ProgressionStatus.REGRESSION,
            "PROGRESSION_UNAVAILABLE": ProgressionStatus.PROGRESSION_UNAVAILABLE,
            "SAFETY_STOP": ProgressionStatus.PROGRESSION_UNAVAILABLE,
        }
        return mapped[decision["decision"]], (decision["rule_id"], decision["decision"])

    def _substitutions(
        self, item: dict[str, Any], candidates: list[dict[str, Any]], available_equipment: tuple[str, ...], experience: TrainingExperience,
    ) -> SubstitutionResult:
        group = (item.get("substitution_group") or {}).get("value")
        if not group:
            return SubstitutionResult("SUBSTITUTION_UNAVAILABLE", (), ("CATALOG_SUBSTITUTION_GROUP_MISSING",), ("E3_1_SUBSTITUTION_DECISION",))
        equipment_ids = {
            eq["id"] for candidate in self._catalog for eq in candidate.get("equipment") or [] if _norm(eq["name"]) in set(available_equipment)
        }
        eligible: list[str] = []
        reasons: set[str] = set()
        for candidate in candidates:
            if candidate["exercise_id"] == item["exercise_id"]:
                continue
            if (candidate.get("substitution_group") or {}).get("value") != group:
                continue
            if not catalog_eligibility(candidate)["structurally_prescription_eligible"]:
                reasons.add("CATALOG_INELIGIBLE")
                continue
            difficulty = (candidate.get("difficulty") or {}).get("value")
            if difficulty == "ADVANCED" and experience != TrainingExperience.EXPERIENCED:
                reasons.add("EXPERIENCE_INCOMPATIBLE")
                continue
            decision = substitution_decision(item, candidate, available_equipment_ids=equipment_ids)
            if decision["decision"] == "ELIGIBLE_AFTER_SAFETY_AND_PREFERENCE_CHECK":
                eligible.append(candidate["exercise_id"])
            else:
                reasons.add(decision["reason"])
        return SubstitutionResult(
            "AVAILABLE" if eligible else "SUBSTITUTION_UNAVAILABLE",
            tuple(sorted(eligible)),
            tuple(sorted(reasons or {"NO_REVIEWED_COMPATIBLE_SUBSTITUTE"})),
            ("E3_1_SUBSTITUTION_DECISION",),
        )

    def plan(
        self,
        profile: ExerciseProfile,
        state: TrainingState,
        request: WorkoutRequest,
        *,
        energy_weight_kg: float | None = None,
    ) -> WorkoutPlan:
        safety = evaluate_safety(profile)
        requirement = build_session_requirement(profile, state, request, safety)
        candidates, stages = self._hard_filter(profile, request, requirement, safety)
        generated_at = state.sessions_last_7d.computed_at
        empty_status = TimeBudgetStatus.CLARIFICATION_REQUIRED if requirement.status in {ApplicabilityStatus.NEEDS_CLARIFICATION, ApplicabilityStatus.UNSUPPORTED, ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE} else TimeBudgetStatus.INSUFFICIENT_TIME
        if requirement.status != ApplicabilityStatus.SUPPORTED:
            return WorkoutPlan(
                PLANNER_VERSION, POLICY_VERSION, CATALOG_VERSION, profile.profile_status, state.status, safety.status,
                requirement.goal, requirement.session_duration_budget, 0.0, empty_status, (), requirement.selection_reason_codes,
                state.history_reason_codes, requirement.policy_rule_ids, stages,
                EnergyEstimate("NO_CALORIE_ESTIMATE", None, "UNMAPPED_ACTIVITY", None, None), "NOT_READY", generated_at,
            )
        ranked = self._rank(candidates, profile, state, request, requirement)
        budget = int(requirement.session_duration_budget or 0)
        total = TIME_ASSUMPTIONS["session_overhead_seconds"] / 60
        target_count = 2 if budget <= 20 else 4 if budget <= 35 else 5 if budget <= 50 else 6
        selected: list[tuple[dict[str, Any], tuple[PriorityComponent, ...], ExercisePrescription, float]] = []
        seen_movements: set[str] = set()
        passes = (True, False)
        for diverse_only in passes:
            for item, components, _ in ranked:
                if any(existing[0]["exercise_id"] == item["exercise_id"] for existing in selected):
                    continue
                movement = (item.get("movement_pattern") or {}).get("value") or "UNKNOWN"
                if diverse_only and movement in seen_movements:
                    continue
                prescription = self._prescription(requirement.goal or "GENERAL_FITNESS", profile.training_experience, movement)
                minutes = self._exercise_minutes(prescription, len(item.get("equipment") or []))
                if total + minutes > budget:
                    continue
                selected.append((item, components, prescription, minutes))
                seen_movements.add(movement)
                total += minutes
                if len(selected) >= target_count:
                    break
            if len(selected) >= target_count:
                break
        planned: list[PlannedExercise] = []
        for item, components, prescription, minutes in selected:
            progression, progression_reasons = self._progression(item, prescription, state)
            substitution = self._substitutions(item, list(self._catalog), requirement.required_equipment_constraints, profile.training_experience)
            eligibility = tuple(catalog_eligibility(item)["statuses"])
            reasons = tuple(
                dict.fromkeys(
                    [component.reason_code for component in components]
                    + ["WITHIN_TIME_BUDGET"]
                )
            )
            planned.append(PlannedExercise(
                canonical_exercise_id=item["exercise_id"], source_exercise_id=item["source_exercise_id"],
                display_name=item["name_en"], eligibility_status=eligibility,
                required_equipment=tuple(sorted(_norm(eq["name"]) for eq in item.get("equipment") or [])),
                primary_muscles=tuple(sorted((muscle.get("name_en") or muscle.get("name") or str(muscle.get("id"))) for muscle in item.get("primary_muscles") or [])),
                movement_pattern=(item.get("movement_pattern") or {}).get("value") or "UNKNOWN",
                selection_reason_codes=reasons, ranking_components=components, prescription=prescription,
                progression_status=progression, progression_reason_codes=progression_reasons, substitution=substitution,
                estimated_minutes=minutes,
                policy_rule_ids=tuple(dict.fromkeys(prescription.policy_rule_ids + substitution.policy_rule_ids + (TIME_MODEL_VERSION,))),
            ))
        if not planned:
            time_status = TimeBudgetStatus.INSUFFICIENT_TIME
            estimated = 0.0
        else:
            estimated = round(total, 2)
            time_status = TimeBudgetStatus.WITHIN_BUDGET if len(planned) >= target_count else TimeBudgetStatus.PARTIAL_PLAN
        energy = EnergyEstimate("NO_CALORIE_ESTIMATE", None, "UNMAPPED_ACTIVITY", None, None)
        age = profile.exercise_safety_profile.age
        if energy_weight_kg is not None and age is not None and planned:
            all_bodyweight = all(ex.required_equipment == ("none (bodyweight exercise)",) for ex in planned)
            mapped = estimate_mapped_session_energy(
                activity_key="BODYWEIGHT_RESISTANCE_GENERAL" if all_bodyweight else "WGER_RESISTANCE_SESSION_GENERAL",
                weight_kg=energy_weight_kg, duration_minutes=estimated, age=age,
            )
            mapping = mapped.get("mapping") or {}
            energy = EnergyEstimate(
                mapped["status"], mapped.get("estimated_energy_expenditure_kcal"), mapped.get("mapping_status", mapping.get("mapping_status", "UNMAPPED_ACTIVITY")),
                mapped.get("source"), mapped.get("activity_code"),
            )
        draft = WorkoutPlan(
            PLANNER_VERSION, POLICY_VERSION, CATALOG_VERSION, profile.profile_status, state.status, safety.status,
            requirement.goal, budget, estimated, time_status, tuple(planned),
            tuple(dict.fromkeys(requirement.selection_reason_codes + (("HISTORY_UNAVAILABLE",) if state.status != StateStatus.KNOWN else ()))),
            state.history_reason_codes,
            tuple(dict.fromkeys(requirement.policy_rule_ids + (TIME_MODEL_VERSION,))),
            stages, energy, "DRAFT", generated_at,
        )
        from services.workout_planner.validator import WorkoutPlanValidator
        validation = WorkoutPlanValidator(self._catalog).validate(draft, profile, state, request)
        return replace(draft, readiness="READY" if validation.ready else "NOT_READY")


__all__ = [
    "PLANNER_VERSION", "TIME_ASSUMPTIONS", "TIME_MODEL_VERSION", "PersonalizedWorkoutPlanner",
    "build_session_requirement", "evaluate_safety",
]
