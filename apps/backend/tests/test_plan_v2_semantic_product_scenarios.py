"""SEMANTIC_REMEDIATION_DEVELOPMENT: practical Plan V2 product flows."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from services.agent.tools.plan_v2 import (
    PlanRuntimeContext,
    build_nutrition_plan,
    build_workout_schedule,
    revise_plan,
    save_plan,
    set_plan_status,
)


def _runtime(*, workout: bool = False) -> PlanRuntimeContext:
    user_id = f"semantic-product-{uuid4()}"
    context = {
        "user_id": user_id,
        "age": 30,
        "equation_sex": "female",
        "height_cm": 164,
        "weight_kg": 58,
        "activity_level": "light",
        "health_goal": "maintain",
    }
    if workout:
        context["workout_profile"] = {
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
        }
    return PlanRuntimeContext(user_id, f"session-{uuid4()}", context, None, True)


def test_natural_three_day_nutrition_and_lifecycle_flow_remains_planned_only() -> None:
    runtime = _runtime()
    draft = asyncio.run(
        build_nutrition_plan(
            period_start="2032-05-03",
            period_end="2032-05-05",
            timezone="Asia/Ho_Chi_Minh",
            temporary_exclusions=("fish",),
            _runtime_context=runtime,
        )
    )
    assert draft["status"] == "READY"
    assert len(draft["plan"]["items"]) == 9
    assert draft["preview_persistence_status"] == "UNAVAILABLE"
    assert all("consumed_at" not in item["content"] for item in draft["plan"]["items"])
    assert "no_fish" in draft["plan"]["constraint_snapshot"]["dietary_restrictions"]

    # A concrete meal-slot change exercises the revision path without trying
    # to turn free prose into a new, uncatalogued dish.
    revised = asyncio.run(
        revise_plan(
            plan_id=draft["plan_id"],
            revision_id=draft["revision_id"],
            expected_revision_number=draft["revision_number"],
            operation="CHANGE_TIME",
            target_item_id=draft["plan"]["items"][0]["plan_item_id"],
            requested_change={"schedule_slot": "snack"},
            reason="đổi khung giờ bữa ăn ngày mai",
            _runtime_context=runtime,
        )
    )
    assert revised["plan_id"] == draft["plan_id"]
    assert revised["revision_id"] != draft["revision_id"]
    assert revised["plan"]["parent_revision_id"] == draft["revision_id"]
    assert revised["plan"]["items"][0]["status"] == "PLANNED"
    assert revised["preview_persistence_status"] == "UNAVAILABLE"

    saved = asyncio.run(
        save_plan(
            plan_id=revised["plan_id"],
            revision_id=revised["revision_id"],
            revision_content_hash=revised["revision_content_hash"],
            request_id=f"save-{uuid4()}",
            _runtime_context=runtime,
        )
    )
    active = asyncio.run(
        set_plan_status(
            plan_id=saved["plan_id"],
            revision_id=saved["revision_id"],
            expected_revision_number=saved["revision_number"],
            status="ACTIVE",
            request_id=f"activate-{uuid4()}",
            _runtime_context=runtime,
        )
    )
    paused = asyncio.run(
        set_plan_status(
            plan_id=active["plan_id"],
            revision_id=active["revision_id"],
            expected_revision_number=active["revision_number"],
            status="PAUSED",
            request_id=f"pause-{uuid4()}",
            _runtime_context=runtime,
        )
    )
    resumed = asyncio.run(
        set_plan_status(
            plan_id=paused["plan_id"],
            revision_id=paused["revision_id"],
            expected_revision_number=paused["revision_number"],
            status="ACTIVE",
            request_id=f"resume-{uuid4()}",
            _runtime_context=runtime,
        )
    )
    assert resumed["lifecycle_status"] == "ACTIVE"
    assert resumed["revision_id"] == revised["revision_id"]


def test_natural_weekly_workout_honors_weekday_count_duration_and_safe_context() -> None:
    runtime = _runtime(workout=True)
    draft = asyncio.run(
        build_workout_schedule(
            period_start="2032-05-03",
            period_end="2032-05-09",
            timezone="Asia/Ho_Chi_Minh",
            goal_override="maintain",
            number_of_sessions=3,
            available_days=("monday", "wednesday", "friday"),
            duration_minutes=45,
            equipment=("bodyweight",),
            _runtime_context=runtime,
        )
    )
    assert draft["status"] == "READY"
    items = draft["plan"]["items"]
    assert len(items) == 3
    assert [item["scheduled_date"] for item in items] == ["2032-05-03", "2032-05-05", "2032-05-07"]
    assert all(item["content"]["e4_presentation"]["exercises"] for item in items)
    assert all(item["content"]["planned_duration_minutes"] <= 45 for item in items)
    assert all("performed_at" not in item["content"] for item in items)
