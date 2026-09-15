"""Integration-level safety tests for the E4.1 adapter/presentation boundary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from config import settings
from services.agent.tools.workout import suggest_workout_facade
from services.workout_planner.contracts import StateStatus, TrainingExperience
from services.workout_planner.integration import (
    ExerciseProfileAdapter,
    TrainingStateAdapter,
    WorkoutIntegrationService,
    WorkoutPlanCache,
    WorkoutRuntimeContext,
)
from services.workout_planner.presentation import WorkoutResponseValidator


def _safe_context() -> dict[str, object]:
    return {
        "user_id": "e4-integration-user",
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


def _run(awaitable):
    return asyncio.run(awaitable)


def test_profile_adapter_keeps_unknown_experience_unknown() -> None:
    result = ExerciseProfileAdapter().adapt({"workout_profile": {}})
    assert result.profile.training_experience == TrainingExperience.UNKNOWN
    assert result.field_statuses["training_experience"] == "MISSING"


def test_history_error_is_never_converted_to_empty_known_history() -> None:
    state = TrainingStateAdapter().adapt(
        None,
        legacy_status=StateStatus.ERROR,
        modern_results=(),
        modern_available=False,
        active_plan_status=None,
        computed_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert state.sessions_last_7d.status == StateStatus.ERROR
    assert state.sessions_last_7d.value is None


def test_ready_plan_is_deterministic_and_presentation_matches() -> None:
    runtime = WorkoutRuntimeContext("e4-integration-user", "session", _safe_context(), None)
    first = _run(WorkoutIntegrationService().build(runtime))
    second = _run(WorkoutIntegrationService().build(runtime))
    assert first.status == "READY"
    assert first.plan is not None and first.presentation is not None
    assert second.plan is not None
    first_plan = first.plan.to_dict()
    second_plan = second.plan.to_dict()
    first_plan.pop("generated_at")
    second_plan.pop("generated_at")
    assert first_plan == second_plan
    assert WorkoutResponseValidator.validate(first.plan, first.presentation).valid
    assert first.validation["hard_violation_count"] == 0


def test_presentation_validator_rejects_dosage_tampering() -> None:
    runtime = WorkoutRuntimeContext("e4-integration-user", "session", _safe_context(), None)
    outcome = _run(WorkoutIntegrationService().build(runtime))
    assert outcome.plan is not None and outcome.presentation is not None
    tampered = {**outcome.presentation, "exercises": [dict(item) for item in outcome.presentation["exercises"]]}
    tampered["exercises"][0]["sets"] += 1
    validation = WorkoutResponseValidator.validate(outcome.plan, tampered)
    assert not validation.valid
    assert any("SETS_MISMATCH" in item for item in validation.violations)


def test_recommendation_does_not_persist_and_writes_stay_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "workout_write_mode", "off")
    runtime = WorkoutRuntimeContext("e4-integration-user", "session", _safe_context(), None)
    service = WorkoutIntegrationService()
    outcome = _run(service.build(runtime))
    assert outcome.status == "READY" and outcome.plan_id
    result = _run(service.save_plan(runtime, outcome.plan_id, "explicit-save"))
    assert result == {"status": "WORKOUT_WRITE_DISABLED", "write_status": "REJECTED"}


def test_explicit_save_restores_owner_scoped_preview_after_cache_restart(monkeypatch) -> None:
    monkeypatch.setattr(settings, "workout_write_mode", "explicit")
    runtime = WorkoutRuntimeContext("e4-integration-user", "session", _safe_context(), None)
    built = _run(WorkoutIntegrationService(cache=WorkoutPlanCache()).build(runtime))
    assert built.plan_id and built.presentation

    class PreviewRepository:
        async def load_preview(self, user_id, plan_id):
            assert user_id == "e4-integration-user"
            assert plan_id == built.plan_id
            return built.presentation

        async def save_presentation(self, user_id, plan_id, presentation, request_id, *, activate):
            assert presentation == built.presentation
            return {
                "id": plan_id,
                "status": "SAVED",
                "planner_version": presentation["planner_version"],
            }

    restarted = WorkoutIntegrationService(cache=WorkoutPlanCache())
    restarted._repository = PreviewRepository()  # noqa: SLF001 - restart boundary fixture
    result = _run(restarted.save_plan(runtime, built.plan_id, "restart-save"))

    assert result["write_status"] == "PERSISTED"
    assert result["workout_plan_id"] == built.plan_id


def test_enforced_legacy_facade_never_falls_back_to_generic_algorithm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "workout_planner_mode", "enforced")
    result = _run(
        suggest_workout_facade(
            "arms", 30, "none", "beginner", goal="general_fitness",
            _runtime_context=WorkoutRuntimeContext("e4-integration-user", "session", _safe_context(), None),
        )
    )
    assert result["status"] == "READY"
    assert "presentation" in result
    assert "workout_title" not in result
