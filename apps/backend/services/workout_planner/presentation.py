"""Deterministic, schema-safe presentation for E4 workout plans.

The chatbot and Flutter client receive this small projection only.  Every
numeric prescription in it comes directly from ``WorkoutPlan``; prose is
derived from reason codes rather than from an LLM reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.workout_planner.contracts import WorkoutPlan


PRESENTATION_VERSION = "workout-plan-presentation-e4-1-v1.0.0"

_REASON_TEXT: dict[str, str] = {
    "UNDEREXPOSED_MUSCLE_GROUP": "Ưu tiên nhóm cơ có mức tiếp xúc ghi nhận thấp hơn trong cửa sổ hiện có.",
    "RECENT_EXPOSURE": "Có cân nhắc mức tiếp xúc gần đây được ghi nhận.",
    "EQUIPMENT_MATCH": "Bài được chọn phù hợp với thiết bị đã cung cấp.",
    "TIME_BUDGET": "Khối lượng bài được giới hạn theo thời lượng buổi tập đã chọn.",
    "NO_PRIOR_PERFORMANCE": "Chưa có dữ liệu hiệu suất trước đó đủ dùng để điều chỉnh tải.",
    "PROGRESSION_UNAVAILABLE": "Chưa đủ quan sát để đề xuất tăng tải cá nhân hóa.",
    "SAFETY_CONSERVATIVE": "Kế hoạch giữ hướng thận trọng theo thông tin an toàn hiện có.",
}


@dataclass(frozen=True, slots=True)
class WorkoutResponseValidation:
    valid: bool
    violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "violations": list(self.violations)}


class WorkoutPlanPresenter:
    """Project an immutable E4 plan into a client-safe canonical payload."""

    @staticmethod
    def deterministic_text(plan: WorkoutPlan) -> str:
        if plan.readiness != "READY":
            return "Mình cần làm rõ thêm thông tin trước khi tạo buổi tập an toàn và phù hợp."
        duration = (
            f" khoảng {round(plan.estimated_duration)} phút"
            if plan.estimated_duration else ""
        )
        return f"Đây là buổi tập cá nhân hóa của bạn{duration}. Các thông số trong thẻ được tạo trực tiếp từ chính sách tập luyện."

    @classmethod
    def present(cls, plan: WorkoutPlan, *, plan_id: str | None) -> dict[str, Any]:
        exercises: list[dict[str, Any]] = []
        for exercise in plan.exercises:
            prescription = exercise.prescription
            exercises.append(
                {
                    "canonical_exercise_id": exercise.canonical_exercise_id,
                    "source_exercise_id": exercise.source_exercise_id,
                    "display_name": exercise.display_name,
                    "sets": prescription.sets,
                    "rep_range": list(prescription.rep_range) if prescription.rep_range else None,
                    "rest_range_seconds": list(prescription.rest_range_seconds),
                    "effort_target_rir": list(prescription.effort_target_rir) if prescription.effort_target_rir else None,
                    "rpe_semantics": prescription.rpe_semantics,
                    "estimated_minutes": exercise.estimated_minutes,
                    "progression_status": exercise.progression_status.value,
                    "progression_reason_codes": list(exercise.progression_reason_codes),
                    "substitution": exercise.substitution.to_dict(),
                    "selection_reason_codes": list(exercise.selection_reason_codes),
                }
            )
        reason_codes = tuple(
            dict.fromkeys((*plan.selection_reason_codes, *plan.history_reason_codes, *plan.policy_reason_codes))
        )
        explanations = [
            {"reason_code": code, "text": _REASON_TEXT[code]}
            for code in reason_codes
            if code in _REASON_TEXT
        ]
        return {
            "type": "personalized_workout",
            "presentation_version": PRESENTATION_VERSION,
            "plan_id": plan_id,
            "text": cls.deterministic_text(plan),
            "status": plan.readiness,
            "planner_version": plan.planner_version,
            "catalog_version": plan.catalog_version,
            "exercise_policy_version": plan.exercise_policy_version,
            "goal": plan.goal,
            "duration_budget_minutes": plan.duration_budget,
            "estimated_duration_minutes": plan.estimated_duration,
            "time_budget_status": plan.time_budget_status.value,
            "safety_status": plan.safety_status.value,
            "exercises": exercises,
            "selection_reason_codes": list(plan.selection_reason_codes),
            "history_reason_codes": list(plan.history_reason_codes),
            "policy_reason_codes": list(plan.policy_reason_codes),
            "explanations": explanations,
            "energy_estimate": plan.estimated_energy_expenditure.to_dict(),
        }


class WorkoutResponseValidator:
    """Reject any structured chat/card payload that diverges from E4 output."""

    @staticmethod
    def validate(plan: WorkoutPlan, payload: Mapping[str, Any]) -> WorkoutResponseValidation:
        violations: list[str] = []
        if payload.get("type") != "personalized_workout":
            violations.append("TYPE_MISMATCH")
        for key, expected in (
            ("planner_version", plan.planner_version),
            ("catalog_version", plan.catalog_version),
            ("exercise_policy_version", plan.exercise_policy_version),
            ("goal", plan.goal),
            ("duration_budget_minutes", plan.duration_budget),
            ("estimated_duration_minutes", plan.estimated_duration),
            ("time_budget_status", plan.time_budget_status.value),
            ("safety_status", plan.safety_status.value),
            ("energy_estimate", plan.estimated_energy_expenditure.to_dict()),
        ):
            if payload.get(key) != expected:
                violations.append(f"{key.upper()}_MISMATCH")
        actual_exercises = payload.get("exercises")
        if not isinstance(actual_exercises, list) or len(actual_exercises) != len(plan.exercises):
            violations.append("EXERCISE_COUNT_MISMATCH")
        else:
            for index, (actual, expected) in enumerate(zip(actual_exercises, plan.exercises)):
                if not isinstance(actual, Mapping):
                    violations.append(f"EXERCISE_{index}_TYPE_MISMATCH")
                    continue
                prescription = expected.prescription
                expected_values = {
                    "canonical_exercise_id": expected.canonical_exercise_id,
                    "source_exercise_id": expected.source_exercise_id,
                    "display_name": expected.display_name,
                    "sets": prescription.sets,
                    "rep_range": list(prescription.rep_range) if prescription.rep_range else None,
                    "rest_range_seconds": list(prescription.rest_range_seconds),
                    "effort_target_rir": list(prescription.effort_target_rir) if prescription.effort_target_rir else None,
                    "rpe_semantics": prescription.rpe_semantics,
                    "estimated_minutes": expected.estimated_minutes,
                    "progression_status": expected.progression_status.value,
                }
                for key, expected_value in expected_values.items():
                    if actual.get(key) != expected_value:
                        violations.append(f"EXERCISE_{index}_{key.upper()}_MISMATCH")
        return WorkoutResponseValidation(not violations, tuple(violations))


__all__ = [
    "PRESENTATION_VERSION",
    "WorkoutPlanPresenter",
    "WorkoutResponseValidation",
    "WorkoutResponseValidator",
]
