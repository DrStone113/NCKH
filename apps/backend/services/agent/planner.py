"""Planner agent for creating long-term plans."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
import inspect
import math
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from models.schemas import ExercisePlanPayload, MealPlanPayload, PlanItem, UserProfile
from services.nutrition.registry import POLICY, POLICY_VERSION


@dataclass(slots=True)
class PlannerError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


_WEEKDAY_NAMES = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)

_PHASE_DETAILS: dict[str, dict[int, tuple[str, str, str]]] = {
    "lose_weight": {
        1: (
            "adaptation",
            "Thích nghi & tạo nhịp sinh hoạt",
            "Ổn định giờ ăn, ưu tiên kỹ thuật tập và hình thành nhịp vận động tuần.",
        ),
        2: (
            "build",
            "Tăng tốc giảm mỡ",
            "Giữ thâm hụt đều, tăng protein và duy trì cả cardio lẫn kháng lực.",
        ),
        3: (
            "progression",
            "Tăng tải & chống chững",
            "Tăng nhẹ thời lượng tập và dùng một ngày nạp lại có kiểm soát mỗi tuần.",
        ),
        4: (
            "consolidation",
            "Củng cố & chuyển sang duy trì",
            "Giảm áp lực thâm hụt, giữ thói quen và chuẩn bị mức năng lượng bền vững.",
        ),
    },
    "gain_muscle": {
        1: (
            "adaptation",
            "Làm quen kỹ thuật & lịch phục hồi",
            "Ưu tiên form chuẩn, ngủ đủ và tạo nhịp tập–nghỉ cố định trong tuần.",
        ),
        2: (
            "build",
            "Xây nền cơ bắp",
            "Tăng tải có kiểm soát, giữ thặng dư năng lượng và protein ổn định.",
        ),
        3: (
            "progression",
            "Đẩy mạnh sức mạnh & khối cơ",
            "Tăng thời lượng hoặc tải tập nhưng vẫn giữ hai khoảng phục hồi mỗi tuần.",
        ),
        4: (
            "consolidation",
            "Củng cố & deload cuối lộ trình",
            (
                "Củng cố kỹ thuật và thói quen; chỉ giảm nhẹ khối lượng ở "
                "tuần cuối để phục hồi."
            ),
        ),
    },
    "maintain": {
        1: (
            "adaptation",
            "Thiết lập nhịp sống cân bằng",
            "Ổn định giờ ăn, vận động vừa sức và bảo đảm ngày nghỉ thực sự.",
        ),
        2: (
            "build",
            "Tăng tính đều đặn",
            "Duy trì lịch tập đa dạng, năng lượng cân bằng và giấc ngủ ổn định.",
        ),
        3: (
            "progression",
            "Nâng thể lực toàn diện",
            "Tăng nhẹ thử thách trong các buổi chính, không hy sinh phục hồi.",
        ),
        4: (
            "consolidation",
            "Củng cố thói quen lâu dài",
            "Giữ lịch có thể lặp lại sau khi lộ trình kết thúc và tránh quá tải.",
        ),
    },
}

@dataclass(frozen=True, slots=True)
class _WorkoutSlot:
    focus: str | None
    session_type: str


_REST = _WorkoutSlot(None, "rest")
_RECOVERY = _WorkoutSlot("mobility", "recovery")
_FULL_BODY = _WorkoutSlot("full_body", "resistance")
_CARDIO = _WorkoutSlot("cardio", "aerobic")
_LEGS = _WorkoutSlot("legs", "resistance")


_ADULT_WEEKLY_WORKOUTS: dict[str, tuple[_WorkoutSlot, ...]] = {
    # Major muscle groups are trained on nonconsecutive days. General fitness
    # and weight-loss plans use two full-body days; muscle-gain uses three.
    "lose_weight": (
        _FULL_BODY, _CARDIO, _RECOVERY, _FULL_BODY, _CARDIO, _CARDIO, _REST
    ),
    "gain_muscle": (
        _FULL_BODY, _CARDIO, _FULL_BODY, _RECOVERY, _FULL_BODY, _CARDIO, _REST
    ),
    "maintain": (
        _FULL_BODY, _CARDIO, _RECOVERY, _FULL_BODY, _CARDIO, _CARDIO, _REST
    ),
}

# Youth guidelines call for daily activity and muscle-/bone-strengthening on at
# least three days. Structured sessions cover only part of the daily 60-minute
# target; school, play, sport, and walking can supply the remainder.
_YOUTH_WEEKLY_WORKOUTS: tuple[_WorkoutSlot, ...] = (
    _FULL_BODY,
    _CARDIO,
    _LEGS,
    _RECOVERY,
    _FULL_BODY,
    _CARDIO,
    _RECOVERY,
)


class PlannerAgent:
    def __init__(self, tools: Any, db_session: Any | None = None) -> None:
        self.tools = tools
        self.db_session = db_session

    async def createLongTermPlan(
        self,
        user_id: str,
        goal: str,
        duration_days: int,
        profile: UserProfile | dict[str, Any],
        start_date: date,
    ) -> str:
        if isinstance(duration_days, bool) or not isinstance(duration_days, int) or not (3 <= duration_days <= 120):
            raise PlannerError("INVALID_DURATION")
        if goal not in {"lose_weight", "maintain", "gain_muscle"}:
            raise PlannerError("INVALID_GOAL")
        try:
            validated = UserProfile.model_validate(profile)
        except Exception as exc:
            raise PlannerError("INVALID_PROFILE") from exc

        plan_id: str | None = None
        try:
            metrics = await self._call_tool(
                "calculate_tdee",
                dict(validated.model_dump()),
            )
            if metrics.get("calorie_target_status") != "AVAILABLE":
                raise PlannerError(
                    str(metrics.get("status") or "CALORIE_TARGET_UNAVAILABLE")
                )
            daily_kcal = float(metrics["daily_kcal"])
            tdee = float(metrics.get("tdee", daily_kcal))
            daily_protein = float(metrics["daily_protein"])
            formula_ids = list(metrics.get("formula_ids") or [])
            plan_id = await self._call_tool(
                "create_plan",
                {
                    "user_id": user_id,
                    "goal": goal,
                    "duration_days": duration_days,
                    "start_date": start_date.isoformat(),
                    "daily_kcal_target": daily_kcal,
                    "daily_protein_target": daily_protein,
                    "nutrition_policy_version": POLICY_VERSION,
                    "nutrition_formula_ids": formula_ids,
                    "request_id": f"plan-{user_id}-{start_date.isoformat()}-{duration_days}",
                },
            )

            total_weeks = math.ceil(duration_days / 7)
            recent_dish_ids: deque[int] = deque(maxlen=12)
            for day_index in range(1, duration_days + 1):
                items: list[dict[str, Any]] = []
                plan_date = start_date + timedelta(days=day_index - 1)
                week_index = ((day_index - 1) // 7) + 1
                week_day = ((day_index - 1) % 7) + 1
                phase_index = self.phaseIndexForWeek(week_index, total_weeks)
                is_deload_week = total_weeks >= 4 and week_index == total_weeks
                phase_key, phase_title, weekly_focus = _PHASE_DETAILS[goal][
                    phase_index
                ]
                # Nutrition baselines do not vary by planner phase. The old
                # unregistered phase deficits/surpluses and protein escalation
                # were hidden policy and are deliberately removed for new plans.
                weekly_kcal = daily_kcal
                is_refeed_day = False
                day_kcal = daily_kcal
                week_protein = daily_protein
                workout_slot = self._workout_slot(
                    plan_date,
                    goal,
                    age=validated.age,
                    phase_index=phase_index,
                    activity_level=validated.activity_level,
                )
                workout_focus = workout_slot.focus
                day_kind = self._day_kind(workout_slot)
                planned_duration = self._workout_duration(
                    goal,
                    phase_index,
                    session_type=workout_slot.session_type,
                    activity_level=validated.activity_level,
                    is_deload_week=is_deload_week,
                    age=validated.age,
                )
                training_summary = self._weekly_training_summary(
                    goal,
                    age=validated.age,
                    phase_index=phase_index,
                    activity_level=validated.activity_level,
                )
                schedule = {
                    "week_index": week_index,
                    "week_day": week_day,
                    "total_weeks": total_weeks,
                    "is_partial_week": (
                        week_index == total_weeks and duration_days % 7 != 0
                    ),
                    "phase_index": phase_index,
                    "phase_key": phase_key,
                    "phase_title": phase_title,
                    "weekly_focus": weekly_focus,
                    "is_deload_week": is_deload_week,
                    "weekday": plan_date.weekday() + 1,
                    "weekday_name": _WEEKDAY_NAMES[plan_date.weekday()],
                    "day_kind": day_kind,
                    "workout_focus": workout_focus,
                    "session_type": workout_slot.session_type,
                    "session_intensity": self._session_intensity(
                        workout_slot.session_type,
                        phase_index=phase_index,
                        activity_level=validated.activity_level,
                        is_deload_week=is_deload_week,
                    ),
                    "planned_duration_minutes": planned_duration,
                    "age_band": self._age_band(validated.age),
                    "weekly_activity_target": self._weekly_activity_target(
                        validated.age
                    ),
                    "weekly_training_summary": training_summary,
                    "progression_rule": (
                        "Tăng thời lượng/tần suất trước cường độ; "
                        "chỉ tăng một biến khi đã phục hồi tốt."
                    ),
                    "intensity_cue": self._intensity_cue(
                        workout_slot.session_type
                    ),
                    "weekly_daily_kcal_target": round(weekly_kcal, 2),
                    "daily_kcal_target": round(day_kcal, 2),
                    "daily_protein_target": round(week_protein, 2),
                    "is_refeed_day": is_refeed_day,
                }

                meal_split = POLICY["meal_split"]
                for meal_type in ("breakfast", "lunch", "dinner"):
                    ratio = float(meal_split[meal_type])
                    dish = await self._call_tool(
                        "suggest_dish",
                        {
                            "meal_type": meal_type,
                            "target_kcal": day_kcal * ratio,
                            "dietary_restrictions": validated.dietary_restrictions,
                            "recent_dish_ids": list(recent_dish_ids),
                        },
                    )
                    if "id" in dish:
                        recent_dish_ids.append(int(dish["id"]))
                    payload = MealPlanPayload(
                        meal_type=meal_type,
                        dish_name=dish["name"],
                        components=dish["components"],
                        total_calories=dish["total_calories"],
                        nutrition_method=dish.get("nutrition_method"),
                        allergen_ids=dish.get("allergen_ids") or [],
                        dietary_tags=dish.get("dietary_tags") or {},
                        quality=dish.get("quality") or {},
                        serving=dish.get("serving") or {},
                        provenance=dish.get("provenance") or {},
                        region_metadata=dish.get("region_metadata") or {},
                    )
                    meal_payload = payload.model_dump(mode="json")
                    meal_payload["schedule"] = schedule
                    items.append(
                        PlanItem(
                            id=str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"plan-item:{plan_id}:{day_index}:{meal_type}",
                                )
                            ),
                            plan_id=plan_id,
                            day_index=day_index,
                            plan_date=plan_date,
                            item_type="meal",
                            title=dish["name"],
                            payload=meal_payload,
                            target_kcal=float(dish["total_calories"]),
                            target_protein=sum(float(c["protein"]) for c in dish["components"]),
                            completed=False,
                        ).model_dump(mode="json")
                    )

                if workout_focus is not None:
                    workout = await self._call_tool(
                        "suggest_workout",
                        {
                            "muscle_group": workout_focus,
                            "duration_min": planned_duration,
                            "equipment": (
                                "none"
                                if workout_slot.session_type == "recovery"
                                else "any"
                            ),
                            "level": (
                                "beginner"
                                if workout_slot.session_type == "recovery"
                                else self._workout_level(
                                    validated.activity_level,
                                    phase_index,
                                    is_deload_week=is_deload_week,
                                )
                            ),
                            "goal": self._tool_workout_goal(
                                goal,
                                workout_slot.session_type,
                            ),
                            "user_state": {"weight_kg": validated.weight_kg},
                        },
                    )
                    ex_payload = ExercisePlanPayload.model_validate(workout)
                    exercise_payload = ex_payload.model_dump(mode="json")
                    exercise_payload["schedule"] = schedule
                    items.append(
                        PlanItem(
                            id=str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"plan-item:{plan_id}:{day_index}:exercise",
                                )
                            ),
                            plan_id=plan_id,
                            day_index=day_index,
                            plan_date=plan_date,
                            item_type="exercise",
                            title=workout["workout_title"],
                            payload=exercise_payload,
                            target_kcal=None,
                            target_protein=None,
                            completed=False,
                        ).model_dump(mode="json")
                    )

                await self._call_tool(
                    "append_plan_items",
                    {
                        "plan_id": plan_id,
                        "day_index": day_index,
                        "items": items,
                        "request_id": f"append-{plan_id}-{day_index}",
                    },
                )

            if self.db_session is not None:
                await self._verify_plan_coverage(str(plan_id), duration_days)
                await self._deactivate_other_plans(user_id, str(plan_id))
            return str(plan_id)
        except PlannerError:
            if plan_id and self.db_session is not None:
                await self._rollback_plan(plan_id)
            raise
        except Exception as exc:
            if plan_id and self.db_session is not None:
                await self._rollback_plan(plan_id)
            code = getattr(exc, "code", None) or str(exc) or "PLANNER_ERROR"
            raise PlannerError(code) from exc

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        fn = getattr(self.tools, name, None)
        if fn is None and hasattr(self.tools, "get"):
            descriptor = self.tools.get(name)
            fn = getattr(descriptor, "fn", None)
        if fn is None:
            raise PlannerError(f"MISSING_TOOL_{name.upper()}")

        # ToolRegistry stores implementations inside descriptors. Mirror the
        # dispatcher's calling convention so single-profile tools such as
        # calculate_tdee receive one dict, while ordinary tools receive kwargs.
        try:
            signature = inspect.signature(fn)
            has_var_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            regular_parameters = [
                parameter
                for parameter in signature.parameters.values()
                if parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            ]
            use_positional_dict = (
                not has_var_kwargs
                and len(regular_parameters) == 1
                and regular_parameters[0].name not in arguments
            )
        except (TypeError, ValueError):
            use_positional_dict = False

        result = fn(arguments) if use_positional_dict else fn(**arguments)
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def _rollback_plan(self, plan_id: str) -> None:
        if self.db_session is None:
            return
        from sqlalchemy import text

        await self.db_session.execute(text("DELETE FROM plan_items WHERE plan_id = :plan_id"), {"plan_id": plan_id})
        await self.db_session.execute(text("DELETE FROM plans WHERE id = :plan_id"), {"plan_id": plan_id})

    async def _deactivate_other_plans(self, user_id: str, plan_id: str) -> None:
        from sqlalchemy import text

        await self.db_session.execute(
            text(
                """
                UPDATE plans
                SET status = 'cancelled'
                WHERE user_id = :user_id
                  AND status = 'active'
                  AND id <> :plan_id
                """
            ),
            {"user_id": user_id, "plan_id": plan_id},
        )

    async def _verify_plan_coverage(
        self, plan_id: str, duration_days: int
    ) -> None:
        """Refuse success unless all days and three daily meals reached Postgres."""
        from sqlalchemy import text

        row = (
            await self.db_session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS item_count,
                        COUNT(DISTINCT day_index)
                            FILTER (WHERE item_type = 'meal') AS covered_days,
                        COUNT(*) FILTER (WHERE item_type = 'meal') AS meal_count
                    FROM plan_items
                    WHERE plan_id = :plan_id
                    """
                ),
                {"plan_id": plan_id},
            )
        ).first()
        if row is None:
            raise PlannerError("PLAN_INCOMPLETE")

        item_count, covered_days, meal_count = (int(value or 0) for value in row)
        if (
            item_count < duration_days * 3
            or covered_days != duration_days
            or meal_count != duration_days * 3
        ):
            raise PlannerError("PLAN_INCOMPLETE")

    @staticmethod
    def phaseIndexForWeek(week_index: int, total_weeks: int) -> int:
        """Map a roadmap week onto 1 of 4 phases, including short plans."""
        if total_weeks <= 1:
            return 1
        if not 1 <= week_index <= total_weeks:
            raise ValueError("INVALID_WEEK_INDEX")
        if total_weeks == 2:
            return 1 if week_index == 1 else 4
        if total_weeks == 3:
            return (1, 2, 4)[week_index - 1]
        return min(4, math.ceil(week_index * 4 / total_weeks))

    @staticmethod
    def _protein_target(
        weight_kg: float, goal: str, *, phase_index: int
    ) -> float:
        raise RuntimeError("USE_CANONICAL_PROTEIN_TARGET")

    @staticmethod
    def _weekly_kcal_target(
        daily_kcal: float, goal: str, phase_index: int, *, tdee: float
    ) -> float:
        return daily_kcal

    @staticmethod
    def _day_kcal_target(
        weekly_kcal: float, *, tdee: float, is_refeed_day: bool
    ) -> float:
        return weekly_kcal

    @staticmethod
    def _age_band(age: int) -> str:
        if age < 18:
            return "youth_10_17"
        if age >= 65:
            return "older_adult_65_plus"
        return "adult_18_64"

    @classmethod
    def _workout_slot(
        cls,
        plan_date: date,
        goal: str,
        *,
        age: int,
        phase_index: int,
        activity_level: str,
    ) -> _WorkoutSlot:
        weekday = plan_date.weekday()
        if age < 18:
            return _YOUTH_WEEKLY_WORKOUTS[weekday]

        slot = _ADULT_WEEKLY_WORKOUTS[goal][weekday]
        # Inactive adults start with one fewer structured session. The extra
        # day is introduced after adaptation, increasing frequency before
        # intensity as recommended by the Physical Activity Guidelines.
        if phase_index == 1 and activity_level in {"sedentary", "light"}:
            if (goal == "gain_muscle" and weekday == 4) or (
                goal != "gain_muscle" and weekday == 5
            ):
                return _REST
        return slot

    @staticmethod
    def _day_kind(slot: _WorkoutSlot) -> str:
        if slot.session_type == "recovery":
            return "active_recovery"
        if slot.session_type == "rest":
            return "rest"
        return "workout"

    @staticmethod
    def _weekly_activity_target(age: int) -> dict[str, Any]:
        if age < 18:
            return {
                "moderate_to_vigorous_minutes_per_day": 60,
                "vigorous_days_per_week": 3,
                "muscle_strengthening_days_per_week": 3,
                "bone_strengthening_days_per_week": 3,
                "note": (
                    "Buổi trong app chỉ là một phần; vui chơi, thể thao, "
                    "đi bộ và hoạt động ở trường đều được tính."
                ),
                "source": (
                    "https://www.cdc.gov/physical-activity-education/"
                    "guidelines/index.html"
                ),
            }

        target: dict[str, Any] = {
            "moderate_aerobic_minutes_per_week": {"minimum": 150, "maximum": 300},
            "vigorous_aerobic_minutes_per_week": {"minimum": 75, "maximum": 150},
            "muscle_strengthening_days_per_week": 2,
            "note": (
                "Các phút vận động ngoài buổi tập như đi bộ nhanh vẫn được "
                "cộng vào mục tiêu aerobic tuần."
            ),
            "source": (
                "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html"
            ),
        }
        if age >= 65:
            target["balance_activity"] = True
            target["balance_note"] = (
                "Kết hợp aerobic, tăng cơ và hoạt động cân bằng phù hợp "
                "khả năng."
            )
        return target

    @classmethod
    def _weekly_training_summary(
        cls,
        goal: str,
        *,
        age: int,
        phase_index: int,
        activity_level: str,
    ) -> str:
        monday = date(2026, 1, 5)
        slots = [
            cls._workout_slot(
                monday + timedelta(days=offset),
                goal,
                age=age,
                phase_index=phase_index,
                activity_level=activity_level,
            )
            for offset in range(7)
        ]
        counts = {
            kind: sum(slot.session_type == kind for slot in slots)
            for kind in ("resistance", "aerobic", "recovery", "rest")
        }
        suffix = (
            "; hoạt động hằng ngày tiếp tục cộng vào mục tiêu 60 phút/ngày"
            if age < 18
            else "; cộng thêm vận động hằng ngày để tiến tới 150 phút aerobic/tuần"
        )
        if age >= 65:
            suffix += "; nên bổ sung hoạt động cân bằng phù hợp"
        return (
            f"{counts['resistance']} buổi kháng lực • "
            f"{counts['aerobic']} buổi aerobic • "
            f"{counts['recovery']} buổi phục hồi • "
            f"{counts['rest']} ngày nghỉ{suffix}"
        )

    @staticmethod
    def _workout_duration(
        goal: str,
        phase_index: int,
        *,
        session_type: str,
        activity_level: str,
        is_deload_week: bool,
        age: int,
    ) -> int:
        if session_type == "rest":
            return 0
        if session_type == "recovery":
            return 25 if age < 18 else 20

        if session_type == "aerobic":
            base = {"lose_weight": 45, "gain_muscle": 30, "maintain": 45}[goal]
        else:
            base = {"lose_weight": 35, "gain_muscle": 45, "maintain": 35}[goal]

        adjustment = (-5, 0, 5, 0)[phase_index - 1]
        if phase_index == 1 and activity_level in {"sedentary", "light"}:
            adjustment -= 5
        if is_deload_week:
            adjustment -= 5
        if age < 18:
            base = min(base, 40)
        # suggest_workout currently emits at most eight five-minute exercise
        # blocks. Keep the promised duration aligned with the returned routine;
        # extra daily movement is described separately in the weekly target.
        return min(40, max(20, base + adjustment))

    @staticmethod
    def _workout_level(
        activity_level: str,
        phase_index: int,
        *,
        is_deload_week: bool,
    ) -> str:
        if is_deload_week or phase_index == 1:
            return "beginner"
        # When frequency is introduced in phase 2, keep the load easy for
        # inactive users. Phase 3 then advances one variable: difficulty.
        if phase_index == 2 and activity_level in {"sedentary", "light"}:
            return "beginner"
        if phase_index == 3 and activity_level == "very_active":
            return "advanced"
        return "intermediate"

    @staticmethod
    def _tool_workout_goal(goal: str, session_type: str) -> str:
        if session_type == "recovery":
            return "recovery"
        if session_type == "aerobic":
            return "weight_loss" if goal == "lose_weight" else "endurance"
        return {
            "lose_weight": "weight_loss",
            "gain_muscle": "muscle_gain",
            "maintain": "general_fitness",
        }[goal]

    @staticmethod
    def _session_intensity(
        session_type: str,
        *,
        phase_index: int,
        activity_level: str,
        is_deload_week: bool,
    ) -> str:
        if session_type == "rest":
            return "rest"
        if session_type == "recovery":
            return "light"
        if is_deload_week or (
            phase_index == 1 and activity_level in {"sedentary", "light"}
        ):
            return "light_to_moderate"
        if phase_index == 3 and activity_level == "very_active":
            return "moderate_to_vigorous"
        return "moderate"

    @staticmethod
    def _intensity_cue(session_type: str) -> str:
        if session_type == "aerobic":
            return "Cường độ vừa: nói chuyện được nhưng không hát được."
        if session_type == "resistance":
            return "Các lần cuối nên thử thách nhưng vẫn giữ đúng kỹ thuật."
        if session_type == "recovery":
            return "Giữ nhẹ, thở đều, không cố vượt qua đau."
        return "Nghỉ hoàn toàn hoặc chỉ sinh hoạt nhẹ theo khả năng."


__all__ = ["PlannerAgent", "PlannerError"]
