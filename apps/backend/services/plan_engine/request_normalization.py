"""Canonical, side-effect-free normalization for structured Plan V2 requests.

The chat model may choose a bounded Plan V2 tool, but it is not allowed to
invent facts.  This module canonicalizes equivalent *representations* supplied
to that tool while preserving unknowns as explicit clarification requirements.
It does not parse a free-text conversation, query storage, or mutate a plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Iterable, Mapping
from unicodedata import normalize as unicode_normalize
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.plan_engine.contracts import PlanDomain


class PlanIntent(str, Enum):
    NUTRITION_DRAFT = "NUTRITION_DRAFT"
    WORKOUT_DRAFT = "WORKOUT_DRAFT"
    PLAN_READ = "PLAN_READ"
    PLAN_REVISION = "PLAN_REVISION"
    PLAN_LIFECYCLE = "PLAN_LIFECYCLE"


def _key(value: str) -> str:
    """Accent-insensitive comparison key; punctuation and separators are cosmetic."""

    return " ".join(
        "".join(
            char if char.isascii() and char.isalnum() else " "
            for char in unicode_normalize("NFD", value).casefold()
        ).split()
    )


def _aliases(values: Mapping[str, str]) -> dict[str, str]:
    return {_key(alias): target for alias, target in values.items()}


_GOAL_ALIASES = _aliases({
    "lose_weight": "lose_weight",
    "weight_loss": "lose_weight",
    "giam can": "lose_weight",
    "giảm cân": "lose_weight",
    "maintain": "maintain",
    "maintenance": "maintain",
    "duy tri": "maintain",
    "duy trì": "maintain",
    "gain_muscle": "gain_muscle",
    "muscle_gain": "gain_muscle",
    "tang co": "gain_muscle",
    "tăng cơ": "gain_muscle",
})
_WEEKDAY_ALIASES = _aliases({
    "monday": "monday", "mon": "monday", "thu 2": "monday", "t2": "monday",
    "tuesday": "tuesday", "tue": "tuesday", "thu 3": "tuesday", "t3": "tuesday",
    "wednesday": "wednesday", "wed": "wednesday", "thu 4": "wednesday", "t4": "wednesday",
    "thursday": "thursday", "thu": "thursday", "thu 5": "thursday", "t5": "thursday",
    "friday": "friday", "fri": "friday", "thu 6": "friday", "t6": "friday",
    "saturday": "saturday", "sat": "saturday", "thu 7": "saturday", "t7": "saturday",
    "sunday": "sunday", "sun": "sunday", "chu nhat": "sunday", "cn": "sunday",
})
_EQUIPMENT_ALIASES = _aliases({
    "day khang luc": "resistance band",
    "dây kháng lực": "resistance band",
    "resistance bands": "resistance band",
    "resistance band": "resistance band",
    "khong dung cu": "none",
    "không dụng cụ": "none",
    "bodyweight": "none",
    "bodyweight only": "none",
    "ta don": "barbell",
    "tạ đòn": "barbell",
    "ta doi": "dumbbell",
    "tạ đôi": "dumbbell",
})
_WORKOUT_GOALS = {
    "lose_weight": "WEIGHT_MANAGEMENT",
    "maintain": "GENERAL_FITNESS",
    "gain_muscle": "HYPERTROPHY",
}
_E4_GOALS = _aliases({
    "general fitness": "GENERAL_FITNESS",
    "general_fitness": "GENERAL_FITNESS",
    "weight management": "WEIGHT_MANAGEMENT",
    "weight_management": "WEIGHT_MANAGEMENT",
    "hypertrophy": "HYPERTROPHY",
    "strength": "STRENGTH",
    "mobility": "MOBILITY",
    "power": "POWER",
})
_NUTRITION_RESTRICTION_ALIASES = _aliases({
    "vegetarian": "vegetarian", "an chay": "vegetarian", "ăn chay": "vegetarian",
    "vegan": "vegan", "thuan chay": "vegan", "thuần chay": "vegan",
    "low_carb": "low_carb", "high_protein": "high_protein",
    "no_seafood": "no_seafood", "hai san": "no_seafood", "hải sản": "no_seafood",
    "no_pork": "no_pork", "pork": "no_pork", "thit heo": "no_pork", "thịt heo": "no_pork",
    "no_beef": "no_beef", "beef": "no_beef", "thit bo": "no_beef", "thịt bò": "no_beef",
    "no_fish": "no_fish", "fish": "no_fish", "ca": "no_fish", "cá": "no_fish",
    "no_egg": "no_egg", "egg": "no_egg", "trung": "no_egg", "trứng": "no_egg",
    "no_milk": "no_milk", "milk": "no_milk", "sua": "no_milk", "sữa": "no_milk",
    "no_peanut": "no_peanut", "peanut": "no_peanut",
    "no_tree_nut": "no_tree_nut", "no_soy": "no_soy", "no_wheat_gluten": "no_wheat_gluten",
    "no_sesame": "no_sesame", "no_crustacean": "no_crustacean", "no_mollusc": "no_mollusc",
})


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    compact = " ".join(value.split())
    return compact or None


def _unique_text(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text is not None and text not in result:
            result.append(text)
    return tuple(result)


def _weekday(value: Any) -> str | None:
    text = _text(value)
    return _WEEKDAY_ALIASES.get(_key(text)) if text is not None else None


def _equipment(value: Any) -> str | None:
    text = _text(value)
    return _EQUIPMENT_ALIASES.get(_key(text), text.casefold() if text is not None else None)


def _goal(value: Any) -> str | None:
    text = _text(value)
    return _GOAL_ALIASES.get(_key(text)) if text is not None else None


def normalize_workout_goal(value: Any, *, context: Mapping[str, Any] | None = None) -> str | None:
    """Translate the Plan goal vocabulary to E4's distinct goal vocabulary.

    An unknown explicit value is preserved for E4 to classify as a typed
    clarification; it is never silently replaced by a profile default.
    """

    supplied = _text(value)
    if supplied is None and isinstance(context, Mapping):
        supplied = _text(context.get("health_goal"))
    if supplied is None:
        return None
    key = _key(supplied)
    plan_goal = _GOAL_ALIASES.get(key)
    if plan_goal is not None:
        return _WORKOUT_GOALS[plan_goal]
    return _E4_GOALS.get(key, supplied)


def partition_nutrition_exclusions(values: Iterable[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split policy-defined dietary constraints from literal ingredient exclusions.

    This prevents a food preference from being silently coerced into an
    unrelated policy enum while still allowing the planner to filter it.
    """

    dietary: list[str] = []
    ingredients: list[str] = []
    for value in values:
        text = _text(value)
        if text is None:
            continue
        restriction = _NUTRITION_RESTRICTION_ALIASES.get(_key(text))
        target = dietary if restriction is not None else ingredients
        normalized = restriction or text
        if normalized not in target:
            target.append(normalized)
    return tuple(dietary), tuple(ingredients)


@dataclass(frozen=True, slots=True)
class NormalizedPlanRequest:
    """Single authoritative projection passed from structured input to planners."""

    intent: PlanIntent
    domain: PlanDomain | None
    operation: str
    period_start: date | None
    period_end: date | None
    timezone: str | None
    goal: str | None
    goal_source: str | None
    meal_scope: tuple[str, ...]
    meal_count: int | None
    nutrition_constraints: tuple[str, ...]
    temporary_preferences: tuple[str, ...]
    temporary_exclusions: tuple[str, ...]
    session_count: int | None
    available_weekdays: tuple[str, ...]
    unavailable_weekdays: tuple[str, ...]
    preferred_weekdays: tuple[str, ...]
    duration_minutes: int | None
    duration_by_day: Mapping[str, int]
    equipment: tuple[str, ...]
    target_plan_id: str | None
    target_revision_id: str | None
    clarification_needs: tuple[str, ...]

    @property
    def is_valid_date_range(self) -> bool:
        return self.period_start is not None and self.period_end is not None and self.period_start <= self.period_end


def normalize_planning_request(
    *,
    intent: PlanIntent,
    period_start: Any = None,
    period_end: Any = None,
    timezone: Any = None,
    goal: Any = None,
    schedule_constraints: Iterable[Any] = (),
    temporary_preferences: Iterable[Any] = (),
    temporary_exclusions: Iterable[Any] = (),
    meal_scope: Iterable[Any] = (),
    meal_count: Any = None,
    session_count: Any = None,
    available_weekdays: Iterable[Any] = (),
    unavailable_weekdays: Iterable[Any] = (),
    preferred_weekdays: Iterable[Any] = (),
    duration_minutes: Any = None,
    duration_by_day: Mapping[Any, Any] | None = None,
    equipment: Iterable[Any] | None = None,
    target_plan_id: Any = None,
    target_revision_id: Any = None,
    context: Mapping[str, Any] | None = None,
) -> NormalizedPlanRequest:
    """Normalize a structured call without creating implicit dates or facts."""

    start_text, end_text, zone = _text(period_start), _text(period_end), _text(timezone)
    try:
        start = date.fromisoformat(start_text) if start_text else None
        end = date.fromisoformat(end_text) if end_text else None
    except ValueError:
        start = end = None
    if zone:
        try:
            ZoneInfo(zone)
        except ZoneInfoNotFoundError:
            zone = None

    domain = PlanDomain.NUTRITION if intent is PlanIntent.NUTRITION_DRAFT else PlanDomain.WORKOUT if intent is PlanIntent.WORKOUT_DRAFT else None
    needs: list[str] = []
    if intent in {PlanIntent.NUTRITION_DRAFT, PlanIntent.WORKOUT_DRAFT}:
        if start is None or end is None:
            needs.append("EXACT_DATE_RANGE_REQUIRED")
        elif end < start:
            needs.append("INVALID_DATE_RANGE")
        if zone is None:
            needs.append("TIMEZONE_REQUIRED")
    normalized_goal = _goal(goal)
    supplied_goal = _text(goal)
    if supplied_goal is not None and normalized_goal is None:
        needs.append("GOAL_CLARIFICATION_REQUIRED")

    raw_available = tuple(available_weekdays)
    raw_unavailable = tuple(unavailable_weekdays)
    raw_preferred = tuple(preferred_weekdays)
    if any(_text(item) is not None and _weekday(item) is None for item in (*raw_available, *raw_unavailable, *raw_preferred)):
        needs.append("INVALID_WEEKDAY_CONSTRAINT")
    available = tuple(day for item in raw_available if (day := _weekday(item)) is not None)
    unavailable = tuple(day for item in raw_unavailable if (day := _weekday(item)) is not None)
    preferred = tuple(day for item in raw_preferred if (day := _weekday(item)) is not None)
    available, unavailable, preferred = _unique_text(available), _unique_text(unavailable), _unique_text(preferred)
    normalized_equipment = _unique_text(item for raw in (equipment or ()) if (item := _equipment(raw)) is not None)
    durations: dict[str, int] = {}
    for raw_day, raw_duration in (duration_by_day or {}).items():
        key = _text(raw_day)
        canonical_day = _weekday(raw_day)
        if key and isinstance(raw_duration, int) and 10 <= raw_duration <= 180:
            durations[canonical_day or key] = raw_duration

    parsed_session_count = session_count if isinstance(session_count, int) and 1 <= session_count <= 7 else None
    parsed_duration = duration_minutes if isinstance(duration_minutes, int) and 10 <= duration_minutes <= 180 else None
    if intent is PlanIntent.WORKOUT_DRAFT:
        profile = context.get("workout_profile") if isinstance(context, Mapping) else None
        if not isinstance(profile, Mapping):
            needs.append("WORKOUT_PROFILE_REQUIRED")
        elif not isinstance(profile.get("exercise_safety_profile"), Mapping):
            needs.append("EXERCISE_SAFETY_CONTEXT_REQUIRED")
        if start is not None and end is not None and start != end and parsed_session_count is None and not available:
            needs.append("WORKOUT_FREQUENCY_REQUIRED")
    if intent in {PlanIntent.PLAN_REVISION, PlanIntent.PLAN_LIFECYCLE}:
        if _text(target_plan_id) is None:
            needs.append("TARGET_PLAN_ID_REQUIRED")
        if _text(target_revision_id) is None:
            needs.append("TARGET_REVISION_ID_REQUIRED")

    return NormalizedPlanRequest(
        intent=intent,
        domain=domain,
        operation="CREATE_DRAFT" if domain is not None else "REVISE" if intent is PlanIntent.PLAN_REVISION else "LIFECYCLE" if intent is PlanIntent.PLAN_LIFECYCLE else intent.value,
        period_start=start,
        period_end=end,
        timezone=zone,
        goal=normalized_goal,
        goal_source="EXPLICIT_REQUEST" if supplied_goal is not None and normalized_goal is not None else None,
        meal_scope=_unique_text(meal_scope),
        meal_count=meal_count if isinstance(meal_count, int) and meal_count > 0 else None,
        nutrition_constraints=_unique_text(schedule_constraints),
        temporary_preferences=_unique_text(temporary_preferences),
        temporary_exclusions=_unique_text(temporary_exclusions),
        session_count=parsed_session_count,
        available_weekdays=available,
        unavailable_weekdays=unavailable,
        preferred_weekdays=preferred,
        duration_minutes=parsed_duration,
        duration_by_day=durations,
        equipment=normalized_equipment,
        target_plan_id=_text(target_plan_id),
        target_revision_id=_text(target_revision_id),
        clarification_needs=tuple(dict.fromkeys(needs)),
    )


__all__ = ["NormalizedPlanRequest", "PlanIntent", "normalize_planning_request", "normalize_workout_goal", "partition_nutrition_exclusions"]
