"""Planner agent for creating long-term plans."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from models.schemas import ExercisePlanPayload, MealPlanPayload, PlanItem, UserProfile


@dataclass(slots=True)
class PlannerError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


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
            daily_kcal = float(metrics["daily_kcal"])
            daily_protein = self._protein_target(validated.weight_kg, goal)
            plan_id = await self._call_tool(
                "create_plan",
                {
                    "user_id": user_id,
                    "goal": goal,
                    "duration_days": duration_days,
                    "start_date": start_date.isoformat(),
                    "daily_kcal_target": daily_kcal,
                    "daily_protein_target": daily_protein,
                    "request_id": f"plan-{user_id}-{start_date.isoformat()}-{duration_days}",
                },
            )

            recent_dish_ids: deque[int] = deque(maxlen=6)
            for day_index in range(1, duration_days + 1):
                items: list[dict[str, Any]] = []
                plan_date = start_date + timedelta(days=day_index - 1)

                for meal_type, ratio in (("breakfast", 0.30), ("lunch", 0.40), ("dinner", 0.30)):
                    dish = await self._call_tool(
                        "suggest_dish",
                        {
                            "meal_type": meal_type,
                            "target_kcal": daily_kcal * ratio,
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
                    items.append(
                        PlanItem(
                            id=f"{plan_id}-{day_index}-{meal_type}",
                            plan_id=plan_id,
                            day_index=day_index,
                            plan_date=plan_date,
                            item_type="meal",
                            title=dish["name"],
                            payload=payload.model_dump(mode="json"),
                            target_kcal=float(dish["total_calories"]),
                            target_protein=sum(float(c["protein"]) for c in dish["components"]),
                            completed=False,
                        ).model_dump(mode="json")
                    )

                if not self._is_rest_day(day_index, goal):
                    workout = await self._call_tool(
                        "suggest_workout",
                        {
                            "muscle_group": self._pick_focus(day_index, goal),
                            "duration_min": self._pick_duration(goal),
                            "equipment": "any",
                            "level": "beginner",
                        },
                    )
                    ex_payload = ExercisePlanPayload.model_validate(workout)
                    items.append(
                        PlanItem(
                            id=f"{plan_id}-{day_index}-exercise",
                            plan_id=plan_id,
                            day_index=day_index,
                            plan_date=plan_date,
                            item_type="exercise",
                            title=workout["workout_title"],
                            payload=ex_payload.model_dump(mode="json"),
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

            return str(plan_id)
        except PlannerError:
            raise
        except Exception as exc:
            if plan_id and self.db_session is not None:
                await self._rollback_plan(plan_id)
            code = getattr(exc, "code", None) or str(exc) or "PLANNER_ERROR"
            raise PlannerError(code) from exc

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        fn = getattr(self.tools, name, None)
        if fn is None:
            raise PlannerError(f"MISSING_TOOL_{name.upper()}")
        result = fn(**arguments)
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def _rollback_plan(self, plan_id: str) -> None:
        if self.db_session is None:
            return
        from sqlalchemy import text

        await self.db_session.execute(text("DELETE FROM plan_items WHERE plan_id = :plan_id"), {"plan_id": plan_id})
        await self.db_session.execute(text("DELETE FROM plans WHERE id = :plan_id"), {"plan_id": plan_id})

    @staticmethod
    def _protein_target(weight_kg: float, goal: str) -> float:
        multiplier = 2.0 if goal == "gain_muscle" else 1.6 if goal == "lose_weight" else 1.4
        return round(weight_kg * multiplier, 2)

    @staticmethod
    def _is_rest_day(day_index: int, goal: str) -> bool:
        return goal != "gain_muscle" and day_index % 7 == 0

    @staticmethod
    def _pick_focus(day_index: int, goal: str) -> str:
        rotation = ["full_body", "legs", "back", "chest", "shoulders", "arms", "cardio"]
        if goal == "lose_weight":
            rotation = ["cardio", "full_body", "legs", "back", "cardio", "arms", "full_body"]
        return rotation[(day_index - 1) % len(rotation)]

    @staticmethod
    def _pick_duration(goal: str) -> int:
        return 45 if goal == "gain_muscle" else 30


__all__ = ["PlannerAgent", "PlannerError"]