"""REST endpoints for user-confirmed E4 workout writes.

The generated plan itself is never saved by this router.  Each endpoint is
only called from an explicit client action and the service still enforces the
``WORKOUT_WRITE_MODE=explicit`` gate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.workout_planner.integration import WorkoutIntegrationService, WorkoutRuntimeContext


router = APIRouter(prefix="/workouts", tags=["workouts"])


class SaveWorkoutPlanRequest(BaseModel):
    user_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    activate: bool = False


class WorkoutSetResult(BaseModel):
    set_index: int | None = Field(default=None, ge=1)
    target_reps: int | None = Field(default=None, ge=1)
    actual_reps: int | None = Field(default=None, ge=0)
    load_kg: float | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    rir: float | None = Field(default=None, ge=0, le=10)
    completed: bool | None = None


class WorkoutExerciseResult(BaseModel):
    canonical_exercise_id: str = Field(min_length=1)
    sets: list[WorkoutSetResult] = Field(default_factory=list)
    exercise_completion_status: str | None = None
    technique_stable: bool | None = None
    substituted_from: str | None = None


class LogWorkoutResultRequest(BaseModel):
    user_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    session_completion_status: str
    pain_discomfort_status: str = "UNKNOWN"
    exercise_results: list[WorkoutExerciseResult] = Field(default_factory=list)
    session_rpe: float | None = Field(default=None, ge=1, le=10)
    performed_at: str | None = None
    note: str | None = None
    duration_minutes: float | None = Field(default=None, ge=0)
    reported_device_energy_kcal: float | None = Field(default=None, ge=0)
    user_reported_energy_kcal: float | None = Field(default=None, ge=0)


def _runtime(request: Request, user_id: str) -> WorkoutRuntimeContext:
    return WorkoutRuntimeContext(
        user_id=user_id,
        session_id=None,
        user_context=None,
        db_session=request.app.state.db_session,
    )


@router.post("/plans/{plan_id}/save")
async def save_workout_plan(plan_id: str, body: SaveWorkoutPlanRequest, request: Request) -> dict[str, Any]:
    runtime = _runtime(request, body.user_id)
    return await WorkoutIntegrationService(runtime.db_session).save_plan(
        runtime, plan_id, body.request_id, activate=body.activate
    )


@router.post("/plans/{plan_id}/results")
async def log_workout_result(plan_id: str, body: LogWorkoutResultRequest, request: Request) -> dict[str, Any]:
    runtime = _runtime(request, body.user_id)
    payload = body.model_dump(mode="json")
    payload.pop("user_id", None)
    payload.pop("request_id", None)
    return await WorkoutIntegrationService(runtime.db_session).log_result(
        runtime, plan_id, body.request_id, payload
    )


__all__ = ["router"]
