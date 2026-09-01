"""Development-only E4.0 scenarios with human-authored invariant oracles.

The cases are synthetic engineering fixtures and share no IDs or text with the
frozen research pilot/final datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from services.workout_planner.contracts import (
    ApplicabilityStatus,
    ExerciseProfile,
    ExerciseSafetyProfile,
    ExperienceSource,
    PainStatus,
    StateStatus,
    TrainingExperience,
    WorkoutRequest,
)


DEVELOPMENT_DATASET_VERSION = "workout-planner-development-v1"
FIXED_NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class ScenarioOracle:
    safety_status: ApplicabilityStatus
    goal: str | None
    planning_status: ApplicabilityStatus
    hard_exclusions: tuple[str, ...]
    required_equipment: tuple[str, ...]
    history_behavior: str
    progression: str
    allowed_time_statuses: tuple[str, ...]
    minimum_invariants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DevelopmentScenario:
    scenario_id: str
    profile: ExerciseProfile
    history_records: tuple[dict[str, Any], ...] | None
    history_source_status: StateStatus
    request: WorkoutRequest
    oracle: ScenarioOracle


@dataclass(frozen=True, slots=True)
class SensitivityPair:
    pair_id: str
    left: DevelopmentScenario
    right: DevelopmentScenario
    expected_change: str


def safe_profile(
    *,
    goal: str = "GENERAL_FITNESS",
    experience: TrainingExperience = TrainingExperience.UNKNOWN,
    equipment: tuple[str, ...] = ("none",),
    duration: int = 30,
    location: str = "home",
    technique_screen: bool | None = None,
    exclusions: tuple[str, ...] = (),
    dislikes: tuple[str, ...] = (),
) -> ExerciseProfile:
    return ExerciseProfile(
        goal=goal,
        goal_status=StateStatus.KNOWN,
        training_experience=experience,
        experience_source=ExperienceSource.EXPLICIT_USER_REPORT if experience != TrainingExperience.UNKNOWN else ExperienceSource.UNKNOWN,
        local_history_available=False,
        available_days_per_week=3,
        preferred_training_days=("MONDAY", "WEDNESDAY", "FRIDAY"),
        default_session_duration_minutes=duration,
        training_location=location,
        available_equipment=equipment,
        disliked_exercises=dislikes,
        exercise_exclusions=exclusions,
        current_pain_status=PainStatus.NONE_REPORTED,
        exercise_safety_profile=ExerciseSafetyProfile(
            age=30,
            age_status=StateStatus.KNOWN,
            health_state="HEALTHY_GENERAL",
            health_state_status=StateStatus.KNOWN,
            pregnancy_status="NOT_APPLICABLE",
            pregnancy_state_status=StateStatus.KNOWN,
            warning_symptoms=(),
            warning_symptoms_status=StateStatus.KNOWN,
            acute_injury=False,
            recent_surgery=False,
            technique_screen_confirmed=technique_screen,
            source="SYNTHETIC_DEVELOPMENT_PROFILE",
        ),
        profile_status=StateStatus.KNOWN,
    )


def _oracle(
    goal: str | None,
    equipment: tuple[str, ...],
    *,
    safety: ApplicabilityStatus = ApplicabilityStatus.SUPPORTED,
    planning: ApplicabilityStatus = ApplicabilityStatus.SUPPORTED,
    history: str = "HISTORY_UNAVAILABLE",
    progression: str = "PROGRESSION_UNAVAILABLE",
    exclusions: tuple[str, ...] = (),
) -> ScenarioOracle:
    return ScenarioOracle(
        safety,
        goal,
        planning,
        exclusions,
        equipment,
        history,
        progression,
        ("WITHIN_BUDGET", "PARTIAL_PLAN", "INSUFFICIENT_TIME") if planning == ApplicabilityStatus.SUPPORTED else ("CLARIFICATION_REQUIRED",),
        (
            "NO_HARD_SAFETY_VIOLATION",
            "EQUIPMENT_COMPATIBLE",
            "CATALOG_PRESCRIPTION_ELIGIBLE",
            "POLICY_VALUES_FROM_E3_1",
            "NO_FABRICATED_HISTORY",
            "NO_UNSUPPORTED_ENERGY_ESTIMATE",
        ),
    )


def development_scenarios() -> tuple[DevelopmentScenario, ...]:
    scenarios: list[DevelopmentScenario] = []
    goals = (
        "GENERAL_FITNESS", "STRENGTH", "HYPERTROPHY", "MUSCULAR_ENDURANCE",
        "WEIGHT_MANAGEMENT", "MOBILITY", "POWER",
    )
    experiences = (TrainingExperience.NOVICE, TrainingExperience.EXPERIENCED, TrainingExperience.UNKNOWN)
    durations = (15, 30, 45, 60)
    equipment_options = (("none",), ("dumbbell",), ("dumbbell", "bench"), ("resistance band",))
    index = 0
    for goal in goals:
        for experience in experiences:
            for duration in durations:
                equipment = equipment_options[index % len(equipment_options)]
                location = "home" if index % 2 == 0 else "gym"
                profile = safe_profile(
                    goal=goal, experience=experience, equipment=equipment, duration=duration,
                    location=location, technique_screen=True if goal == "POWER" and experience == TrainingExperience.EXPERIENCED else None,
                )
                planning = ApplicabilityStatus.SUPPORTED
                if goal == "POWER" and experience != TrainingExperience.EXPERIENCED:
                    planning = ApplicabilityStatus.NEEDS_CLARIFICATION
                scenarios.append(DevelopmentScenario(
                    f"matrix-{index:03d}", profile, None, StateStatus.NOT_LOADED,
                    WorkoutRequest(requested_duration_minutes=duration, requested_location=location, available_equipment_override=equipment, session_type="RESISTANCE"),
                    _oracle(goal, equipment, planning=planning),
                ))
                index += 1

    recent = ({
        "id": "dev-log-1", "exerciseTemplateId": "wger_713", "date": (FIXED_NOW - timedelta(days=2)).isoformat(),
        "name": "Wall Pushup", "duration": 20, "caloriesBurned": 100, "type": "strength", "isCompleted": True,
    },)
    success = ({
        **recent[0], "id": "dev-log-success", "completed_sets": 2, "prescribed_sets": 2,
        "reps": [15, 15], "load_kg": 20.0, "rir": 3.0, "technique_stable": True,
        "pain_reported": False, "consecutive_successes": 2, "consecutive_misses": 0,
    },)
    failure = ({
        **recent[0], "id": "dev-log-failure", "completed_sets": 1, "prescribed_sets": 2,
        "reps": [5], "load_kg": 20.0, "rir": 0.0, "technique_stable": True,
        "pain_reported": False, "consecutive_successes": 0, "consecutive_misses": 2,
    },)
    base = safe_profile()
    specials = [
        ("recent-history", base, recent, StateStatus.KNOWN, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE")),
        ("successful-progression", replace(base, local_history_available=True), success, StateStatus.KNOWN, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_include=("713",)), _oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE", progression="PROGRESSION_AVAILABLE")),
        ("failed-progression", replace(base, local_history_available=True), failure, StateStatus.KNOWN, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_include=("713",)), _oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE", progression="REGRESSION")),
        ("missed-workout", replace(base, local_history_available=True), recent, StateStatus.KNOWN, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), temporary_preferences=("MISSED_SESSION",)), _oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE")),
        ("explicit-dislike", replace(base, disliked_exercises=("Wall Pushup",)), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",))),
        ("temporary-no-legs", base, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), temporary_preferences=("AVOID_LEGS_TODAY",)), _oracle("GENERAL_FITNESS", ("none",))),
        ("explicit-exclusion", replace(base, exercise_exclusions=("713",)), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), exclusions=("713",))),
        ("ambiguous-endurance-vi", base, None, StateStatus.NOT_LOADED, WorkoutRequest(goal_override="sức bền", requested_duration_minutes=30, available_equipment_override=("none",)), _oracle(None, ("none",), planning=ApplicabilityStatus.NEEDS_CLARIFICATION)),
        ("ambiguous-endurance-en", base, None, StateStatus.NOT_LOADED, WorkoutRequest(goal_override="endurance", requested_duration_minutes=30, available_equipment_override=("none",)), _oracle(None, ("none",), planning=ApplicabilityStatus.NEEDS_CLARIFICATION)),
        ("aerobic-handoff", base, None, StateStatus.NOT_LOADED, WorkoutRequest(goal_override="AEROBIC_ENDURANCE", requested_duration_minutes=30, available_equipment_override=("none",), session_type="AEROBIC"), _oracle("AEROBIC_ENDURANCE", ("none",), planning=ApplicabilityStatus.UNSUPPORTED)),
        ("unavailable-substitution", base, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), exercise_include=("713",)), _oracle("GENERAL_FITNESS", ("none",))),
        ("limited-kettlebell", replace(base, available_equipment=("kettlebell",)), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("kettlebell",)), _oracle("GENERAL_FITNESS", ("kettlebell",))),
    ]
    pain_profile = replace(base, current_pain_status=PainStatus.SIGNIFICANT_CURRENT_PAIN)
    warning_profile = replace(base, exercise_safety_profile=replace(base.exercise_safety_profile, warning_symptoms=("CHEST_PAIN_OR_PRESSURE",)))
    injury_profile = replace(base, exercise_safety_profile=replace(base.exercise_safety_profile, acute_injury=True))
    surgery_profile = replace(base, exercise_safety_profile=replace(base.exercise_safety_profile, recent_surgery=True))
    unknown_profile = replace(base, current_pain_status=PainStatus.UNKNOWN)
    specials.extend([
        ("significant-pain", pain_profile, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE, planning=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE)),
        ("warning-symptom", warning_profile, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.UNSUPPORTED, planning=ApplicabilityStatus.UNSUPPORTED)),
        ("acute-injury", injury_profile, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE, planning=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE)),
        ("recent-surgery", surgery_profile, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE, planning=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE)),
        ("missing-safety", unknown_profile, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.NEEDS_CLARIFICATION, planning=ApplicabilityStatus.NEEDS_CLARIFICATION)),
        ("missing-equipment", replace(base, available_equipment=()), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30), _oracle("GENERAL_FITNESS", (), planning=ApplicabilityStatus.NEEDS_CLARIFICATION)),
        ("missing-duration", replace(base, default_session_duration_minutes=None), None, StateStatus.NOT_LOADED, WorkoutRequest(available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",), planning=ApplicabilityStatus.NEEDS_CLARIFICATION)),
        ("write-intent-forbidden", base, None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",), write_intent=True), _oracle("GENERAL_FITNESS", ("none",), planning=ApplicabilityStatus.UNSUPPORTED)),
    ])
    for sid, profile, history, history_status, request, oracle in specials:
        scenarios.append(DevelopmentScenario(f"special-{sid}", profile, history, history_status, request, oracle))
    return tuple(scenarios)


def personalization_pairs() -> tuple[SensitivityPair, ...]:
    base = DevelopmentScenario("pair-base", safe_profile(), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",)))
    recent = ({"id": "pair-log", "exerciseTemplateId": "wger_713", "date": (FIXED_NOW - timedelta(days=1)).isoformat(), "name": "Wall Pushup", "duration": 20, "caloriesBurned": 100, "type": "strength", "isCompleted": True},)
    return (
        SensitivityPair("equipment", base, replace(base, scenario_id="pair-equipment", profile=replace(base.profile, available_equipment=("dumbbell",)), request=replace(base.request, available_equipment_override=("dumbbell",)), oracle=_oracle("GENERAL_FITNESS", ("dumbbell",))), "EXERCISES"),
        SensitivityPair("goal", base, replace(base, scenario_id="pair-goal", profile=replace(base.profile, goal="STRENGTH"), oracle=_oracle("STRENGTH", ("none",))), "PRESCRIPTION"),
        SensitivityPair("history", base, replace(base, scenario_id="pair-history", profile=replace(base.profile, local_history_available=True), history_records=recent, history_source_status=StateStatus.KNOWN, oracle=_oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE")), "HISTORY_OR_EXERCISES"),
        SensitivityPair("duration", replace(base, scenario_id="pair-duration-25", request=replace(base.request, requested_duration_minutes=25)), replace(base, scenario_id="pair-duration-60", request=replace(base.request, requested_duration_minutes=60)), "DURATION_OR_COUNT"),
        SensitivityPair("pain", base, replace(base, scenario_id="pair-pain", profile=replace(base.profile, current_pain_status=PainStatus.SIGNIFICANT_CURRENT_PAIN), oracle=_oracle("GENERAL_FITNESS", ("none",), safety=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE, planning=ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE)), "SAFETY"),
        SensitivityPair("experience", replace(base, scenario_id="pair-novice", profile=replace(base.profile, goal="STRENGTH", training_experience=TrainingExperience.NOVICE)), replace(base, scenario_id="pair-experienced", profile=replace(base.profile, goal="STRENGTH", training_experience=TrainingExperience.EXPERIENCED)), "PRESCRIPTION"),
        SensitivityPair("completed-workout", base, replace(base, scenario_id="pair-completed", profile=replace(base.profile, local_history_available=True), history_records=recent, history_source_status=StateStatus.KNOWN, oracle=_oracle("GENERAL_FITNESS", ("none",), history="HISTORY_AVAILABLE")), "HISTORY_OR_EXERCISES"),
    )


def irrelevant_input_pairs() -> tuple[SensitivityPair, ...]:
    base = DevelopmentScenario("stable-base", safe_profile(), None, StateStatus.NOT_LOADED, WorkoutRequest(requested_duration_minutes=30, available_equipment_override=("none",)), _oracle("GENERAL_FITNESS", ("none",)))
    return (
        SensitivityPair("preferred-days", base, replace(base, scenario_id="stable-days", profile=replace(base.profile, preferred_training_days=("TUESDAY", "THURSDAY"))), "NO_CHANGE"),
        SensitivityPair("available-days", base, replace(base, scenario_id="stable-frequency", profile=replace(base.profile, available_days_per_week=4)), "NO_CHANGE"),
    )


__all__ = [
    "DEVELOPMENT_DATASET_VERSION", "FIXED_NOW", "DevelopmentScenario", "ScenarioOracle", "SensitivityPair",
    "development_scenarios", "irrelevant_input_pairs", "personalization_pairs", "safe_profile",
]
