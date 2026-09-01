"""Immutable, JSON-safe contracts for the E4.0 shadow workout planner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class StateStatus(StrEnum):
    KNOWN = "KNOWN"
    MISSING = "MISSING"
    NOT_LOADED = "NOT_LOADED"
    STALE = "STALE"
    ERROR = "ERROR"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class HistoryCoverage(StrEnum):
    AUTHORITATIVE_AVAILABLE = "AUTHORITATIVE_AVAILABLE"
    DERIVABLE = "DERIVABLE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class TrainingExperience(StrEnum):
    NOVICE = "NOVICE"
    EXPERIENCED = "EXPERIENCED"
    UNKNOWN = "UNKNOWN"


class ExperienceSource(StrEnum):
    EXPLICIT_USER_REPORT = "EXPLICIT_USER_REPORT"
    PROFILE = "PROFILE"
    UNKNOWN = "UNKNOWN"


class PainStatus(StrEnum):
    NONE_REPORTED = "NONE_REPORTED"
    SIGNIFICANT_CURRENT_PAIN = "SIGNIFICANT_CURRENT_PAIN"
    UNKNOWN = "UNKNOWN"


class ApplicabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REQUIRES_PROFESSIONAL_GUIDANCE = "REQUIRES_PROFESSIONAL_GUIDANCE"
    UNSUPPORTED = "UNSUPPORTED"


class TimeBudgetStatus(StrEnum):
    WITHIN_BUDGET = "WITHIN_BUDGET"
    PARTIAL_PLAN = "PARTIAL_PLAN"
    INSUFFICIENT_TIME = "INSUFFICIENT_TIME"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class ProgressionStatus(StrEnum):
    PROGRESSION_AVAILABLE = "PROGRESSION_AVAILABLE"
    MAINTAIN = "MAINTAIN"
    REGRESSION = "REGRESSION"
    PROGRESSION_UNAVAILABLE = "PROGRESSION_UNAVAILABLE"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


class JsonContract:
    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class ExerciseSafetyProfile(JsonContract):
    age: int | None = None
    age_status: StateStatus = StateStatus.UNKNOWN
    health_state: str = "UNKNOWN"
    health_state_status: StateStatus = StateStatus.UNKNOWN
    pregnancy_status: str = "UNKNOWN"
    pregnancy_state_status: StateStatus = StateStatus.UNKNOWN
    warning_symptoms: tuple[str, ...] = ()
    warning_symptoms_status: StateStatus = StateStatus.UNKNOWN
    acute_injury: bool | None = None
    recent_surgery: bool | None = None
    technique_screen_confirmed: bool | None = None
    source: str = "PROFILE"


@dataclass(frozen=True, slots=True)
class ExerciseProfile(JsonContract):
    goal: str | None = None
    goal_status: StateStatus = StateStatus.UNKNOWN
    training_experience: TrainingExperience = TrainingExperience.UNKNOWN
    experience_source: ExperienceSource = ExperienceSource.UNKNOWN
    local_history_available: bool = False
    available_days_per_week: int | None = None
    preferred_training_days: tuple[str, ...] = ()
    default_session_duration_minutes: int | None = None
    training_location: str | None = None
    available_equipment: tuple[str, ...] = ()
    preferred_exercises: tuple[str, ...] = ()
    disliked_exercises: tuple[str, ...] = ()
    exercise_exclusions: tuple[str, ...] = ()
    self_reported_limitations: tuple[str, ...] = ()
    current_pain_status: PainStatus = PainStatus.UNKNOWN
    exercise_safety_profile: ExerciseSafetyProfile = ExerciseSafetyProfile()
    profile_status: StateStatus = StateStatus.UNKNOWN


@dataclass(frozen=True, slots=True)
class StateObservation(JsonContract):
    value: Any
    source: str
    observation_window: str
    computed_at: datetime
    status: StateStatus
    provenance: str
    coverage: HistoryCoverage


@dataclass(frozen=True, slots=True)
class ExercisePerformance(JsonContract):
    canonical_exercise_id: str
    source_exercise_id: int | None
    observed_at: datetime
    completed_sets: int | None = None
    prescribed_sets: int | None = None
    reps: tuple[int, ...] = ()
    load_kg: float | None = None
    rpe: float | None = None
    rir: float | None = None
    completed: bool | None = None
    pain_reported: bool | None = None
    technique_stable: bool | None = None
    consecutive_successes: int = 0
    consecutive_misses: int = 0
    source: str = "EXERCISE_HISTORY"


@dataclass(frozen=True, slots=True)
class TrainingState(JsonContract):
    status: StateStatus
    history_reason_codes: tuple[str, ...]
    sessions_last_7d: StateObservation
    sessions_last_28d: StateObservation
    resistance_sessions_last_7d: StateObservation
    aerobic_minutes_last_7d: StateObservation
    last_session_at: StateObservation
    last_exercise_performed_at: StateObservation
    muscle_exposure_7d: StateObservation
    muscle_exposure_28d: StateObservation
    movement_exposure_7d: StateObservation
    movement_exposure_28d: StateObservation
    exercise_performance_history: StateObservation
    recent_sets: StateObservation
    recent_reps: StateObservation
    recent_load_kg: StateObservation
    recent_rpe: StateObservation
    recent_rir: StateObservation
    completion_rate: StateObservation
    missed_sessions: StateObservation
    reported_pain_events: StateObservation
    recent_substitutions: StateObservation
    active_workout_plan_status: StateObservation


@dataclass(frozen=True, slots=True)
class WorkoutRequest(JsonContract):
    goal_override: str | None = None
    requested_duration_minutes: int | None = None
    requested_location: str | None = None
    available_equipment_override: tuple[str, ...] | None = None
    requested_body_area: str | None = None
    exercise_include: tuple[str, ...] = ()
    exercise_exclude: tuple[str, ...] = ()
    temporary_preferences: tuple[str, ...] = ()
    session_type: str = "RESISTANCE"
    goal_context: str | None = None
    write_intent: bool = False


@dataclass(frozen=True, slots=True)
class SafetyDecision(JsonContract):
    status: ApplicabilityStatus
    reason_codes: tuple[str, ...]
    e3_status: str
    ordinary_planner_allowed: bool
    policy_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionRequirement(JsonContract):
    status: ApplicabilityStatus
    goal: str | None
    goal_domain: str | None
    session_duration_budget: int | None
    required_equipment_constraints: tuple[str, ...]
    allowed_exercise_eligibility: tuple[str, ...]
    target_muscle_priorities: tuple[str, ...]
    target_movement_priorities: tuple[str, ...]
    avoid_reduce_priorities: tuple[str, ...]
    volume_budget: tuple[int, int] | None
    effort_target: tuple[int, int] | None
    rest_ranges: tuple[tuple[str, tuple[int, int]], ...]
    progression_policy: str | None
    safety_restrictions: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    policy_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FilterStage(JsonContract):
    stage: str
    before: int
    removed: int
    after: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class PriorityComponent(JsonContract):
    rule_id: str
    priority: int
    provenance: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class ExercisePrescription(JsonContract):
    sets: int
    rep_range: tuple[int, int] | None
    rest_range_seconds: tuple[int, int]
    effort_target_rir: tuple[int, int] | None
    rpe_semantics: str
    policy_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubstitutionResult(JsonContract):
    status: str
    candidate_exercise_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    policy_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlannedExercise(JsonContract):
    canonical_exercise_id: str
    source_exercise_id: int
    display_name: str
    eligibility_status: tuple[str, ...]
    required_equipment: tuple[str, ...]
    primary_muscles: tuple[str, ...]
    movement_pattern: str
    selection_reason_codes: tuple[str, ...]
    ranking_components: tuple[PriorityComponent, ...]
    prescription: ExercisePrescription
    progression_status: ProgressionStatus
    progression_reason_codes: tuple[str, ...]
    substitution: SubstitutionResult
    estimated_minutes: float
    policy_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnergyEstimate(JsonContract):
    status: str
    estimated_energy_expenditure: float | None
    mapping_status: str
    source: str | None
    activity_code: str | None


@dataclass(frozen=True, slots=True)
class WorkoutPlan(JsonContract):
    planner_version: str
    exercise_policy_version: str
    catalog_version: str
    profile_status: StateStatus
    training_state_status: StateStatus
    safety_status: ApplicabilityStatus
    goal: str | None
    duration_budget: int | None
    estimated_duration: float
    time_budget_status: TimeBudgetStatus
    exercises: tuple[PlannedExercise, ...]
    selection_reason_codes: tuple[str, ...]
    history_reason_codes: tuple[str, ...]
    policy_reason_codes: tuple[str, ...]
    catalog_filtering: tuple[FilterStage, ...]
    estimated_energy_expenditure: EnergyEstimate
    readiness: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class PlanViolation(JsonContract):
    rule_id: str
    severity: str
    code: str
    exercise_id: str | None
    observed: Any
    expected: Any


@dataclass(frozen=True, slots=True)
class ValidationResult(JsonContract):
    ready: bool
    violations: tuple[PlanViolation, ...]
    hard_violation_count: int
    soft_violation_count: int
