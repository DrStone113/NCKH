"""High-level, authoritative E4.1 workout tools.

All profile/history loading and prescription happen server-side.  The private
``_runtime_context`` is injected by the dispatcher after JSON-schema
validation, so it can never be produced by an LLM or included in tool traces.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from services.agent.tool_registry import ToolDescriptor
from services.workout_planner.integration import (
    WorkoutIntegrationService,
    WorkoutRuntimeContext,
)


_GOALS = [
    "GENERAL_FITNESS", "WEIGHT_MANAGEMENT", "HYPERTROPHY", "STRENGTH",
    "MUSCULAR_ENDURANCE", "MOBILITY", "POWER", "AEROBIC_ENDURANCE",
]
_RESULT_STATUS = ["COMPLETED", "PARTIALLY_COMPLETED", "SKIPPED", "CANCELLED"]
_PAIN_STATUS = ["YES", "NO", "UNKNOWN"]


def _runtime(value: WorkoutRuntimeContext | None) -> WorkoutRuntimeContext:
    if isinstance(value, WorkoutRuntimeContext):
        return value
    return WorkoutRuntimeContext(None, None, None, None)


def _service(runtime: WorkoutRuntimeContext) -> WorkoutIntegrationService:
    return WorkoutIntegrationService(runtime.db_session)


async def build_personalized_workout(
    *,
    goal_override: str | None = None,
    duration_minutes: int | None = None,
    training_location: str | None = None,
    equipment: Iterable[str] | None = None,
    temporary_exclusions: Iterable[str] = (),
    temporary_preferences: Iterable[str] = (),
    requested_body_area: str | None = None,
    _runtime_context: WorkoutRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    outcome = await _service(runtime).build(
        runtime,
        goal_override=goal_override,
        requested_duration_minutes=duration_minutes,
        requested_location=training_location,
        available_equipment_override=equipment,
        requested_body_area=requested_body_area,
        exercise_exclude=temporary_exclusions,
        temporary_preferences=temporary_preferences,
    )
    return outcome.to_tool_payload()


async def get_workout_substitutions(
    *,
    plan_id: str,
    canonical_exercise_id: str,
    equipment: Iterable[str] | None = None,
    _runtime_context: WorkoutRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    return await _service(runtime).get_substitutions(
        runtime,
        plan_id=plan_id,
        canonical_exercise_id=canonical_exercise_id,
        equipment_override=equipment,
    )


async def save_workout_plan(
    *,
    plan_id: str,
    request_id: str,
    activate: bool = False,
    _runtime_context: WorkoutRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    return await _service(runtime).save_plan(runtime, plan_id, request_id, activate=activate)


async def log_workout_result(
    *,
    plan_id: str,
    request_id: str,
    session_completion_status: str,
    pain_discomfort_status: str = "UNKNOWN",
    exercise_results: Iterable[Mapping[str, Any]] = (),
    session_rpe: float | None = None,
    performed_at: str | None = None,
    note: str | None = None,
    duration_minutes: float | None = None,
    reported_device_energy_kcal: float | None = None,
    user_reported_energy_kcal: float | None = None,
    _runtime_context: WorkoutRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    payload = {
        "session_completion_status": session_completion_status,
        "pain_discomfort_status": pain_discomfort_status,
        "exercise_results": [dict(item) for item in exercise_results if isinstance(item, Mapping)],
        "session_rpe": session_rpe,
        "performed_at": performed_at,
        "note": note,
        "duration_minutes": duration_minutes,
        "reported_device_energy_kcal": reported_device_energy_kcal,
        "user_reported_energy_kcal": user_reported_energy_kcal,
    }
    return await _service(runtime).log_result(runtime, plan_id, request_id, payload)


_ARRAY_OF_STRINGS = {"type": "array", "items": {"type": "string", "minLength": 1}}
_SET_RESULT = {
    "type": "object",
    "properties": {
        "set_index": {"type": "integer", "minimum": 1},
        "target_reps": {"type": "integer", "minimum": 1},
        "actual_reps": {"type": "integer", "minimum": 0},
        "load_kg": {"type": "number", "minimum": 0},
        "rpe": {"type": "number", "minimum": 1, "maximum": 10},
        "rir": {"type": "number", "minimum": 0, "maximum": 10},
        "completed": {"type": "boolean"},
    },
    "additionalProperties": False,
}
_EXERCISE_RESULT = {
    "type": "object",
    "properties": {
        "canonical_exercise_id": {"type": "string", "minLength": 1},
        "sets": {"type": "array", "items": _SET_RESULT},
        "exercise_completion_status": {"type": "string", "enum": _RESULT_STATUS},
        "technique_stable": {"type": "boolean"},
        "substituted_from": {"type": "string", "minLength": 1},
    },
    "required": ["canonical_exercise_id"],
    "additionalProperties": False,
}

BUILD_PERSONALIZED_WORKOUT_DESCRIPTOR = ToolDescriptor(
    name="build_personalized_workout",
    description="Tạo buổi tập E4 cá nhân hóa. Chỉ dùng khi người dùng muốn gợi ý tập; không tự lưu hoặc tự ghi nhận kết quả.",
    parameters_schema={
        "type": "object",
        "properties": {
            "goal_override": {"type": "string", "enum": _GOALS},
            "duration_minutes": {"type": "integer", "minimum": 10, "maximum": 180},
            "training_location": {"type": "string", "minLength": 1},
            "equipment": _ARRAY_OF_STRINGS,
            "temporary_exclusions": _ARRAY_OF_STRINGS,
            "temporary_preferences": _ARRAY_OF_STRINGS,
            "requested_body_area": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    },
    side="server",
    fn=build_personalized_workout,
    idempotent=True,
)

GET_WORKOUT_SUBSTITUTIONS_DESCRIPTOR = ToolDescriptor(
    name="get_workout_substitutions",
    description="Tìm thay thế E4 an toàn cho một bài trong kế hoạch đã tạo; không tự lưu thay đổi sở thích lâu dài.",
    parameters_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "minLength": 1},
            "canonical_exercise_id": {"type": "string", "minLength": 1},
            "equipment": _ARRAY_OF_STRINGS,
        },
        "required": ["plan_id", "canonical_exercise_id"],
        "additionalProperties": False,
    },
    side="server",
    fn=get_workout_substitutions,
    idempotent=True,
)

SAVE_WORKOUT_PLAN_DESCRIPTOR = ToolDescriptor(
    name="save_workout_plan",
    description="Chỉ lưu kế hoạch E4 khi người dùng yêu cầu rõ ràng lưu hoặc bắt đầu kế hoạch.",
    parameters_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "minLength": 1},
            "request_id": {"type": "string", "minLength": 1},
            "activate": {"type": "boolean"},
        },
        "required": ["plan_id", "request_id"],
        "additionalProperties": False,
    },
    side="server",
    fn=save_workout_plan,
    idempotent=False,
)

LOG_WORKOUT_RESULT_DESCRIPTOR = ToolDescriptor(
    name="log_workout_result",
    description="Chỉ ghi nhận kết quả buổi tập khi người dùng xác nhận rõ. Ghi giá trị thực tế người dùng cung cấp, không sao chép mục tiêu thành kết quả.",
    parameters_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "minLength": 1},
            "request_id": {"type": "string", "minLength": 1},
            "session_completion_status": {"type": "string", "enum": _RESULT_STATUS},
            "pain_discomfort_status": {"type": "string", "enum": _PAIN_STATUS},
            "exercise_results": {"type": "array", "items": _EXERCISE_RESULT},
            "session_rpe": {"type": "number", "minimum": 1, "maximum": 10},
            "performed_at": {"type": "string", "format": "date-time"},
            "note": {"type": "string"},
            "duration_minutes": {"type": "number", "minimum": 0},
            "reported_device_energy_kcal": {"type": "number", "minimum": 0},
            "user_reported_energy_kcal": {"type": "number", "minimum": 0},
        },
        "required": ["plan_id", "request_id", "session_completion_status"],
        "additionalProperties": False,
    },
    side="server",
    fn=log_workout_result,
    idempotent=False,
)


E4_WORKOUT_TOOL_NAMES = frozenset(
    {
        "build_personalized_workout",
        "get_workout_substitutions",
        "save_workout_plan",
        "log_workout_result",
        "suggest_workout",
    }
)

__all__ = [
    "BUILD_PERSONALIZED_WORKOUT_DESCRIPTOR",
    "E4_WORKOUT_TOOL_NAMES",
    "GET_WORKOUT_SUBSTITUTIONS_DESCRIPTOR",
    "LOG_WORKOUT_RESULT_DESCRIPTOR",
    "SAVE_WORKOUT_PLAN_DESCRIPTOR",
    "build_personalized_workout",
    "get_workout_substitutions",
    "log_workout_result",
    "save_workout_plan",
]
