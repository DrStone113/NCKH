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
            "Củng cố & deload",
            "Giảm nhẹ khối lượng tập để hấp thu tiến bộ và hạn chế tích mỡ không cần thiết.",
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

_WEEKLY_WORKOUTS: dict[str, dict[int, str | None]] = {
    # weekday(): Monday=0 ... Sunday=6. Every goal keeps Sunday as a full
    # rest day, with one or two midweek active-recovery slots.
    "lose_weight": {
        0: "full_body",
        1: "cardio",
        2: "legs",
        3: None,
        4: "full_body",
        5: "cardio",
        6: None,
    },
    "gain_muscle": {
        0: "chest",
        1: "back",
        2: "legs",
        3: None,
        4: "shoulders",
        5: "arms",
        6: None,
    },
    "maintain": {
        0: "full_body",
        1: "cardio",
        2: None,
        3: "legs",
        4: None,
        5: "full_body",
        6: None,
    },
}


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
                workout_focus = self._workout_focus(plan_date, goal)
                day_kind = self._day_kind(plan_date, workout_focus)
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
                    "weekday": plan_date.weekday() + 1,
                    "weekday_name": _WEEKDAY_NAMES[plan_date.weekday()],
                    "day_kind": day_kind,
                    "workout_focus": workout_focus,
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
                            "duration_min": self._workout_duration(
                                goal, phase_index
                            ),
                            "equipment": "any",
                            "level": self._workout_level(
                                validated.activity_level, phase_index
                            ),
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
    def _workout_focus(plan_date: date, goal: str) -> str | None:
        return _WEEKLY_WORKOUTS[goal][plan_date.weekday()]

    @staticmethod
    def _day_kind(plan_date: date, workout_focus: str | None) -> str:
        if workout_focus is not None:
            return "workout"
        return "rest" if plan_date.weekday() == 6 else "active_recovery"

    @staticmethod
    def _workout_duration(goal: str, phase_index: int) -> int:
        base = {"lose_weight": 35, "gain_muscle": 45, "maintain": 30}[goal]
        adjustment = (-5, 0, 5, -5)[phase_index - 1]
        return max(20, base + adjustment)

    @staticmethod
    def _workout_level(activity_level: str, phase_index: int) -> str:
        if phase_index == 1 or activity_level in {"sedentary", "light"}:
            return "beginner"
        if phase_index == 3 and activity_level == "very_active":
            return "advanced"
        return "intermediate"


__all__ = ["PlannerAgent", "PlannerError"]
