"""SEMANTIC_REMEDIATION_DEVELOPMENT: generalized Plan V2 request tests."""

from __future__ import annotations

import asyncio

from services.agent.tools.plan_v2 import PlanRuntimeContext, build_workout_schedule
from services.plan_engine.request_normalization import (
    PlanIntent,
    normalize_planning_request,
    partition_nutrition_exclusions,
)


def test_food_exclusions_use_policy_aliases_only_when_the_contract_defines_them() -> None:
    dietary, ingredients = partition_nutrition_exclusions(("fish", "nấm hương", "no_egg"))

    assert dietary == ("no_fish", "no_egg")
    assert ingredients == ("nấm hương",)


def test_vietnamese_weekdays_and_equipment_normalize_without_inventing_facts() -> None:
    normalized = normalize_planning_request(
        intent=PlanIntent.WORKOUT_DRAFT,
        period_start="2032-04-05",
        period_end="2032-04-11",
        timezone="Asia/Ho_Chi_Minh",
        goal="giảm cân",
        session_count=3,
        available_weekdays=("Thứ 2", "thứ 4", "thứ 6"),
        duration_by_day={"Thứ 2": 25, "thứ 4": 35, "thứ 6": 30},
        equipment=("dây kháng lực",),
        context={"workout_profile": {"exercise_safety_profile": {}}},
    )

    assert normalized.goal == "lose_weight"
    assert normalized.goal_source == "EXPLICIT_REQUEST"
    assert normalized.available_weekdays == ("monday", "wednesday", "friday")
    assert dict(normalized.duration_by_day) == {"monday": 25, "wednesday": 35, "friday": 30}
    assert normalized.equipment == ("resistance band",)
    assert not normalized.clarification_needs


def test_missing_workout_safety_and_frequency_stay_explicit() -> None:
    normalized = normalize_planning_request(
        intent=PlanIntent.WORKOUT_DRAFT,
        period_start="2032-04-05",
        period_end="2032-04-11",
        timezone="Asia/Ho_Chi_Minh",
        context={"workout_profile": {}},
    )

    assert "EXERCISE_SAFETY_CONTEXT_REQUIRED" in normalized.clarification_needs
    assert "WORKOUT_FREQUENCY_REQUIRED" in normalized.clarification_needs
    assert normalized.session_count is None


def test_invalid_date_and_weekday_are_not_replaced_with_defaults() -> None:
    normalized = normalize_planning_request(
        intent=PlanIntent.WORKOUT_DRAFT,
        period_start="tomorrow",
        period_end="",
        timezone="Not/AZone",
        available_weekdays=("whenever",),
    )

    assert normalized.period_start is None
    assert normalized.period_end is None
    assert normalized.timezone is None
    assert {"EXACT_DATE_RANGE_REQUIRED", "TIMEZONE_REQUIRED", "INVALID_WEEKDAY_CONSTRAINT"}.issubset(normalized.clarification_needs)


def test_lifecycle_targets_are_trimmed_but_never_invented() -> None:
    normalized = normalize_planning_request(
        intent=PlanIntent.PLAN_LIFECYCLE,
        target_plan_id="  plan-1  ",
        target_revision_id=None,
    )

    assert normalized.operation == "LIFECYCLE"
    assert normalized.target_plan_id == "plan-1"
    assert normalized.target_revision_id is None
    assert normalized.clarification_needs == ("TARGET_REVISION_ID_REQUIRED",)


def test_workout_tool_returns_specific_safe_clarification_without_profile() -> None:
    output = asyncio.run(
        build_workout_schedule(
            period_start="2032-04-05",
            period_end="2032-04-05",
            timezone="Asia/Ho_Chi_Minh",
            duration_minutes=30,
            equipment=("dây kháng lực",),
            _runtime_context=PlanRuntimeContext(
                user_id="semantic-remediation-user",
                session_id="semantic-remediation-session",
                user_context={"user_id": "semantic-remediation-user"},
                db_session=None,
            ),
        )
    )

    assert output["status"] == "CLARIFICATION_REQUIRED"
    assert output["validation"]["issues"][0]["code"] == "WORKOUT_PROFILE_REQUIRED"
    assert output["planned_not_actual"] is True


def test_one_day_request_overrides_stale_weekly_preferences_and_maps_maintain_goal() -> None:
    profile = {
        "user_id": "semantic-remediation-user",
        "age": 30,
        "health_goal": "maintain",
        "workout_profile": {
            "training_experience": "NOVICE",
            "current_pain_status": "NO",
            "available_days_per_week": 3,
            "preferred_training_days": ["monday", "wednesday", "friday"],
            "default_session_duration_minutes": 45,
            "training_location": "home",
            "available_equipment": ["none"],
            "preferred_exercises": [],
            "disliked_exercises": [],
            "exercise_exclusions": [],
            "self_reported_limitations": [],
            "exercise_safety_profile": {
                "health_state": "HEALTHY_GENERAL",
                "pregnancy_status": "NOT_APPLICABLE",
                "warning_symptoms": [],
                "acute_injury": False,
                "recent_surgery": False,
                "technique_screen_confirmed": False,
            },
        },
    }
    output = asyncio.run(
        build_workout_schedule(
            period_start="2032-04-05",
            period_end="2032-04-05",
            timezone="Asia/Ho_Chi_Minh",
            goal_override="maintain",
            duration_minutes=45,
            equipment=("bodyweight",),
            _runtime_context=PlanRuntimeContext(
                user_id="semantic-remediation-user",
                session_id="semantic-remediation-single-day",
                user_context=profile,
                db_session=None,
                authenticated_principal=True,
            ),
        )
    )

    assert output["status"] == "READY"
    assert len(output["plan"]["items"]) == 1
    assert output["plan"]["request"]["goal_override"] == "maintain"
    assert output["planned_not_actual"] is True
