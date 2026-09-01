"""Deterministic P2 weekly workout scheduling around E4 sessions.

This module intentionally allocates calendar slots only.  It has no sets,
reps, rest, effort, recovery, or volume prescription constants.  E4 remains
the sole authority for each generated session.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping

from .contracts import ContextValue, PlanRequest


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_VI_WEEKDAYS = {
    "thứ 2": "mon", "thu 2": "mon", "t2": "mon", "monday": "mon",
    "thứ 3": "tue", "thu 3": "tue", "t3": "tue", "tuesday": "tue",
    "thứ 4": "wed", "thu 4": "wed", "t4": "wed", "wednesday": "wed",
    "thứ 5": "thu", "thu 5": "thu", "t5": "thu", "thursday": "thu",
    "thứ 6": "fri", "thu 6": "fri", "t6": "fri", "friday": "fri",
    "thứ 7": "sat", "thu 7": "sat", "t7": "sat", "saturday": "sat",
    "chủ nhật": "sun", "chu nhat": "sun", "cn": "sun", "sunday": "sun",
}


class WeeklyScheduleError(ValueError):
    """Stable clarification/fail-closed scheduler reason code."""


@dataclass(frozen=True, slots=True)
class WeeklyWorkoutRequest:
    """Only scheduling facts plus opaque E4 request inputs.

    Dates may be ISO dates or weekday labels (Vietnamese/English).  A supplied
    date is exact; a supplied weekday is a recurring availability constraint
    within the PlanRequest horizon.
    """

    plan_request: PlanRequest
    number_of_sessions: int | None = None
    explicit_available_days: tuple[str, ...] = ()
    explicit_unavailable_days: tuple[str, ...] = ()
    preferred_days: tuple[str, ...] = ()
    default_duration_minutes: int | None = None
    duration_by_day: Mapping[str, int] = field(default_factory=dict)
    location: str | None = None
    equipment: tuple[str, ...] | None = None
    temporary_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.number_of_sessions is not None and not 1 <= self.number_of_sessions <= 7:
            raise WeeklyScheduleError("INVALID_WEEKLY_SESSION_COUNT")
        if self.default_duration_minutes is not None and not 10 <= self.default_duration_minutes <= 180:
            raise WeeklyScheduleError("INVALID_SESSION_DURATION")
        for value in self.duration_by_day.values():
            if not isinstance(value, int) or not 10 <= value <= 180:
                raise WeeklyScheduleError("INVALID_SESSION_DURATION")


@dataclass(frozen=True, slots=True)
class PlannedSessionExposure:
    """Facts implied by a generated plan, never an observation of a workout."""

    scheduled_date: date
    exercise_ids: tuple[str, ...]
    muscle_exposure: tuple[str, ...] = ()
    movement_exposure: tuple[str, ...] = ()
    planned_duration_minutes: int | None = None
    source: str = "PLANNED_E4_SESSION"


@dataclass(frozen=True, slots=True)
class PlanningHorizonState:
    """Separate actual training state plus projected, non-observational facts."""

    actual_training_state: ContextValue
    planned_sessions: tuple[PlannedSessionExposure, ...] = ()

    def with_planned_session(self, exposure: PlannedSessionExposure) -> "PlanningHorizonState":
        return PlanningHorizonState(self.actual_training_state, (*self.planned_sessions, exposure))

    @property
    def planned_exercise_ids(self) -> tuple[str, ...]:
        return tuple(identifier for session in self.planned_sessions for identifier in session.exercise_ids)

    def projection(self) -> dict[str, Any]:
        """Safe planned-only projector used for balance and debug trace."""

        return {
            "planned_session_count": len(self.planned_sessions),
            "planned_exercise_ids": list(self.planned_exercise_ids),
            "planned_muscle_exposure": sorted({item for session in self.planned_sessions for item in session.muscle_exposure}),
            "planned_movement_exposure": sorted({item for session in self.planned_sessions for item in session.movement_exposure}),
            "planned_duration_minutes": sum(
                session.planned_duration_minutes or 0 for session in self.planned_sessions
            ),
            "actual_training_state_source": self.actual_training_state.source,
            "planned_is_not_actual": True,
        }


@dataclass(frozen=True, slots=True)
class ScheduledWorkoutSlot:
    scheduled_date: date
    duration_minutes: int | None
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeeklyWorkoutPlan:
    slots: tuple[ScheduledWorkoutSlot, ...]
    status: str = "READY"
    reason_codes: tuple[str, ...] = ()

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(item.scheduled_date for item in self.slots)


class ScheduleRequirementResolver:
    """Resolve user availability without inventing missing availability."""

    @staticmethod
    def resolve(raw: WeeklyWorkoutRequest) -> tuple[tuple[date, ...], tuple[date, ...], tuple[date, ...]]:
        horizon = tuple(
            date.fromordinal(raw.plan_request.period_start.toordinal() + offset)
            for offset in range(raw.plan_request.duration_days)
        )
        available = _resolve_day_tokens(raw.explicit_available_days, horizon)
        unavailable = _resolve_day_tokens(raw.explicit_unavailable_days, horizon)
        preferred = _resolve_day_tokens(raw.preferred_days, horizon)
        if raw.explicit_available_days and not available:
            raise WeeklyScheduleError("SCHEDULE_AVAILABLE_DAYS_OUTSIDE_PERIOD")
        candidates = tuple(day for day in (available or horizon) if day not in set(unavailable))
        if not candidates:
            raise WeeklyScheduleError("SCHEDULE_NO_AVAILABLE_DAYS")
        return candidates, preferred, available


class WeeklyWorkoutScheduler:
    """Calendar allocator with documented deterministic product heuristic."""

    def schedule(self, request: WeeklyWorkoutRequest) -> WeeklyWorkoutPlan:
        candidates, preferred, explicitly_selected = ScheduleRequirementResolver.resolve(request)
        requested = request.number_of_sessions
        if requested is None:
            # An exact user day list means schedule those days.  Without a
            # number or exact day constraint, a schedule would be invented.
            if explicitly_selected:
                requested = len(explicitly_selected)
            elif request.plan_request.duration_days == 1:
                requested = 1
            else:
                raise WeeklyScheduleError("WEEKLY_SESSION_COUNT_REQUIRED")
        if requested > len(candidates):
            raise WeeklyScheduleError("SCHEDULE_INSUFFICIENT_AVAILABLE_DAYS")
        selected = _spread_evenly(candidates, requested, set(preferred))
        provenance = (
            "USER_REQUESTED_SCHEDULE" if request.explicit_available_days else "PRODUCT_SCHEDULING_HEURISTIC",
            "SOFT_PLANNING_TARGET",
            "E4_PER_SESSION_DELEGATION_REQUIRED",
        )
        return WeeklyWorkoutPlan(
            slots=tuple(
                ScheduledWorkoutSlot(
                    scheduled_date=day,
                    duration_minutes=_duration_for(day, request),
                    provenance=provenance,
                )
                for day in selected
            ),
            reason_codes=provenance,
        )


def exposure_from_e4_payload(scheduled_date: date, payload: Mapping[str, Any]) -> PlannedSessionExposure:
    """Extract only future planned facts from a structured E4 payload."""

    presentation = payload.get("presentation") if isinstance(payload, Mapping) else None
    exercises = presentation.get("exercises") if isinstance(presentation, Mapping) else None
    exercise_ids: list[str] = []
    muscles: list[str] = []
    movements: list[str] = []
    if isinstance(exercises, list):
        for exercise in exercises:
            if not isinstance(exercise, Mapping):
                continue
            identifier = exercise.get("canonical_exercise_id")
            if isinstance(identifier, str) and identifier:
                exercise_ids.append(identifier)
            for key, target in (("target_muscles", muscles), ("movement_patterns", movements)):
                values = exercise.get(key)
                if isinstance(values, list):
                    target.extend(str(value) for value in values if isinstance(value, str) and value)
    duration = presentation.get("estimated_duration_minutes") if isinstance(presentation, Mapping) else None
    return PlannedSessionExposure(
        scheduled_date=scheduled_date,
        exercise_ids=tuple(dict.fromkeys(exercise_ids)),
        muscle_exposure=tuple(sorted(set(muscles))),
        movement_exposure=tuple(sorted(set(movements))),
        planned_duration_minutes=int(duration) if isinstance(duration, (int, float)) else None,
    )


def validate_weekly_plan(plan: WeeklyWorkoutPlan, *, horizon: PlanningHorizonState | None = None) -> tuple[str, ...]:
    """Hard weekly invariants; balance remains a soft provenance-only target."""

    issues: list[str] = []
    seen: set[date] = set()
    for slot in plan.slots:
        if slot.scheduled_date in seen:
            issues.append("DUPLICATE_WEEKLY_SESSION_DATE")
        seen.add(slot.scheduled_date)
        if slot.duration_minutes is not None and not 10 <= slot.duration_minutes <= 180:
            issues.append("WEEKLY_DURATION_CONSTRAINT_VIOLATION")
        if "E4_PER_SESSION_DELEGATION_REQUIRED" not in slot.provenance:
            issues.append("WEEKLY_E4_DELEGATION_MISSING")
    if horizon is not None:
        projection = horizon.projection()
        forbidden = {"actual_completion", "actual_recovery", "actual_rpe", "actual_load", "recovered", "fatigued"}
        if forbidden.intersection(projection):
            issues.append("WEEKLY_FABRICATED_ACTUAL_STATE")
    return tuple(dict.fromkeys(issues))


def _normalise_day_token(value: str) -> str:
    token = " ".join(value.strip().casefold().replace("thứ", "thu").split())
    if token in _VI_WEEKDAYS:
        return _VI_WEEKDAYS[token]
    return token[:3] if token[:3] in _WEEKDAYS else token


def _resolve_day_tokens(tokens: Iterable[str], horizon: tuple[date, ...]) -> tuple[date, ...]:
    selected: set[date] = set()
    for raw in tokens:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            exact = date.fromisoformat(raw.strip())
        except ValueError:
            weekday = _normalise_day_token(raw)
            if weekday in _WEEKDAYS:
                selected.update(day for day in horizon if _WEEKDAYS[day.weekday()] == weekday)
            continue
        if exact in horizon:
            selected.add(exact)
    return tuple(sorted(selected))


def _spread_evenly(candidates: tuple[date, ...], count: int, preferred: set[date]) -> tuple[date, ...]:
    """Maximise spacing, then preferred days, then earliest date deterministically."""

    if count == len(candidates):
        return candidates
    chosen: list[date] = []
    remaining = list(candidates)
    while len(chosen) < count:
        def key(day: date) -> tuple[int, int, int]:
            distance = min((abs(day.toordinal() - other.toordinal()) for other in chosen), default=10_000)
            # min() later selects smallest, so negate higher-is-better values.
            return (-distance, -(1 if day in preferred else 0), day.toordinal())
        candidate = min(remaining, key=key)
        chosen.append(candidate)
        remaining.remove(candidate)
    return tuple(sorted(chosen))


def _duration_for(day: date, request: WeeklyWorkoutRequest) -> int | None:
    exact = request.duration_by_day.get(day.isoformat())
    if isinstance(exact, int):
        return exact
    weekday = request.duration_by_day.get(_WEEKDAYS[day.weekday()])
    if isinstance(weekday, int):
        return weekday
    return request.default_duration_minutes


__all__ = [
    "PlannedSessionExposure", "PlanningHorizonState", "ScheduleRequirementResolver",
    "ScheduledWorkoutSlot", "WeeklyScheduleError", "WeeklyWorkoutPlan", "WeeklyWorkoutRequest",
    "WeeklyWorkoutScheduler", "exposure_from_e4_payload", "validate_weekly_plan",
]
