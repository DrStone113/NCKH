"""Regression coverage for persisted workout-intake memory and confirmation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from services.agent.system_prompt import buildSystemPrompt
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_client_tools
from services.agent.tools.workout import suggest_workout_facade
from services.workout_planner.contracts import PainStatus
from services.workout_planner.integration import (
    ExerciseProfileAdapter,
    WorkoutIntegrationService,
    WorkoutRuntimeContext,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _current_confirmed_context() -> dict[str, object]:
    return {
        "user_id": "workout-profile-memory-user",
        "age": 30,
        "health_goal": "gain_muscle",
        "weight": 70.0,
        "exercise_history": [],
        "exercise_history_status": "KNOWN",
        "exercise_history_loaded": True,
        "workout_profile": {
            "training_experience": "NOVICE",
            "available_days_per_week": 3,
            "default_session_duration_minutes": 30,
            "training_location": "home",
            "available_equipment": ["none"],
            "current_pain_status": "NO",
            "safety_checked_at": datetime.now(timezone.utc).isoformat(),
            "intake_confirmation_status": "CONFIRMED",
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


def test_pending_workout_profile_requires_recap_before_building_plan() -> None:
    context = _current_confirmed_context()
    profile = context["workout_profile"]
    assert isinstance(profile, dict)
    profile["intake_confirmation_status"] = "PENDING_CONFIRMATION"

    outcome = _run(
        WorkoutIntegrationService().build(
            WorkoutRuntimeContext("workout-profile-memory-user", "session", context, None)
        )
    )

    assert outcome.status == "PROFILE_CONFIRMATION_REQUIRED"
    assert outcome.error_code == "WORKOUT_PROFILE_RECAP_REQUIRED"
    assert outcome.plan is None
    assert outcome.presentation is None


def test_pending_profile_cannot_bypass_recap_through_legacy_facade() -> None:
    context = _current_confirmed_context()
    profile = context["workout_profile"]
    assert isinstance(profile, dict)
    profile["intake_confirmation_status"] = "PENDING_CONFIRMATION"

    result = _run(
        suggest_workout_facade(
            "abs",
            30,
            "none",
            "beginner",
            _runtime_context=WorkoutRuntimeContext(
                "workout-profile-memory-user", "session", context, None
            ),
        )
    )

    assert result == {
        "status": "PROFILE_CONFIRMATION_REQUIRED",
        "error_code": "WORKOUT_PROFILE_RECAP_REQUIRED",
    }


def test_current_confirmed_workout_profile_can_build_ready_plan() -> None:
    context = _current_confirmed_context()

    outcome = _run(
        WorkoutIntegrationService().build(
            WorkoutRuntimeContext("workout-profile-memory-user", "session", context, None)
        )
    )

    assert outcome.status == "READY"
    assert outcome.plan is not None
    assert outcome.presentation is not None


def test_stale_safety_check_is_not_reused_as_current_pain_clearance() -> None:
    context = _current_confirmed_context()
    profile = context["workout_profile"]
    assert isinstance(profile, dict)
    profile["safety_checked_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()

    adapted = ExerciseProfileAdapter().adapt(context)

    assert adapted.profile.current_pain_status == PainStatus.UNKNOWN
    assert adapted.field_statuses["current_pain_status"] == "STALE"


def test_chat_profile_without_safety_timestamp_is_not_a_current_clearance() -> None:
    context = _current_confirmed_context()
    profile = context["workout_profile"]
    assert isinstance(profile, dict)
    profile.pop("safety_checked_at")

    adapted = ExerciseProfileAdapter().adapt(context)

    assert adapted.profile.current_pain_status == PainStatus.UNKNOWN
    assert adapted.field_statuses["current_pain_status"] == "STALE"


def test_pending_profile_prompt_requires_recap_and_confirmation() -> None:
    context = _current_confirmed_context()
    profile = context["workout_profile"]
    assert isinstance(profile, dict)
    profile["intake_confirmation_status"] = "PENDING_CONFIRMATION"

    prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        user_profile=context,
    )
    # The explicit profile section gives the LLM the stored facts to recap,
    # while the E4 rules make confirmation mandatory before planning.
    assert "BẮT BUỘC XÁC NHẬN" in prompt
    assert "chatbot đang nhớ có đúng không" in prompt
    assert "Mình đang nhớ …; đúng chứ?" in prompt


def test_client_catalog_registers_and_validates_workout_profile_memory_tool() -> None:
    registry = ToolRegistry()
    register_client_tools(registry)

    descriptor = registry.get("update_workout_profile")
    assert descriptor is not None
    assert descriptor.side == "client"
    assert not descriptor.idempotent

    capture_valid, capture_error = registry.validate(
        "update_workout_profile",
        {
            "mode": "CAPTURE",
            "patch": {
                "training_experience": "NOVICE",
                "available_days_per_week": 3,
                "current_pain_status": "NO",
            },
            "request_id": "capture-profile-memory-1",
        },
    )
    confirm_valid, confirm_error = registry.validate(
        "update_workout_profile",
        {
            "mode": "CONFIRM",
            "patch": {},
            "request_id": "confirm-profile-memory-1",
        },
    )

    assert (capture_valid, capture_error) == (True, None)
    assert (confirm_valid, confirm_error) == (True, None)
