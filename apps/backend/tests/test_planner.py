from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from services.agent.planner import PlannerAgent, PlannerError
from services.agent.tool_registry import ToolDescriptor, ToolRegistry


VALID_PROFILE = {
    "user_id": "u1",
    "age": 25,
    "gender": "male",
    "height_cm": 170,
    "weight_kg": 70,
    "activity_level": "moderate",
    "health_goal": "lose_weight",
    "dietary_restrictions": [],
}


@dataclass
class FakeTools:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_on: str | None = None
    dish_id: int = 0

    async def calculate_tdee(self, **kwargs):
        self.calls.append(("calculate_tdee", kwargs))
        return {"bmr": 1500, "tdee": 2000, "daily_kcal": 1800}

    async def create_plan(self, **kwargs):
        self.calls.append(("create_plan", kwargs))
        return "plan-1"

    async def suggest_dish(self, **kwargs):
        self.calls.append(("suggest_dish", kwargs))
        if self.fail_on == "suggest_dish":
            raise Exception("suggest_dish")
        self.dish_id += 1
        return {
            "id": self.dish_id,
            "name": f"Com ga {self.dish_id}",
            "components": [{"name": "ga", "serving_grams": 100, "calories": kwargs["target_kcal"], "protein": 20, "carbs": 0, "fat": 5}],
            "total_calories": kwargs["target_kcal"],
        }

    async def suggest_workout(self, **kwargs):
        self.calls.append(("suggest_workout", kwargs))
        if self.fail_on == "suggest_workout":
            raise Exception("suggest_workout")
        return {
            "workout_title": "Workout",
            "exercises": [{"name": "Push up", "category": "strength", "duration_minutes": 15, "sets": 3, "reps": "10", "calories_burned": 50}],
            "total_duration_minutes": 15,
            "total_calories_burned": 50,
        }

    async def append_plan_items(self, **kwargs):
        self.calls.append(("append_plan_items", kwargs))
        if self.fail_on == "append_plan_items":
            raise Exception("append_plan_items")
        return None


@dataclass
class FakeDb:
    statements: list[str] = field(default_factory=list)

    async def execute(self, statement, params):
        self.statements.append(str(statement))


@dataclass
class _Result:
    row: tuple[int, int, int] | None

    def first(self):
        return self.row


@dataclass
class CoverageDb:
    coverage: tuple[int, int, int]
    statements: list[str] = field(default_factory=list)

    async def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        if "COUNT(DISTINCT day_index)" in sql:
            return _Result(self.coverage)
        return _Result(None)


@pytest.mark.asyncio
async def test_invalid_duration_raises():
    with pytest.raises(PlannerError, match="INVALID_DURATION"):
        await PlannerAgent(FakeTools()).createLongTermPlan("u1", "lose_weight", 2, {"user_id": "u1"}, date(2026, 1, 1))


@pytest.mark.asyncio
async def test_invalid_duration_upper_raises():
    with pytest.raises(PlannerError, match="INVALID_DURATION"):
        await PlannerAgent(FakeTools()).createLongTermPlan("u1", "lose_weight", 121, VALID_PROFILE, date(2026, 1, 1))


@pytest.mark.asyncio
async def test_invalid_profile_raises():
    with pytest.raises(PlannerError, match="INVALID_PROFILE"):
        await PlannerAgent(FakeTools()).createLongTermPlan("u1", "lose_weight", 7, {"user_id": "u1"}, date(2026, 1, 1))


@pytest.mark.asyncio
async def test_profile_age_out_of_range_raises_invalid_profile():
    profile = dict(VALID_PROFILE)
    profile["age"] = 5
    with pytest.raises(PlannerError, match="INVALID_PROFILE"):
        await PlannerAgent(FakeTools()).createLongTermPlan("u1", "lose_weight", 7, profile, date(2026, 1, 1))


@pytest.mark.asyncio
async def test_create_plan_calls_tools_and_passes_duration():
    tools = FakeTools()
    planner = PlannerAgent(tools)
    plan_id = await planner.createLongTermPlan(
        "u1",
        "lose_weight",
        7,
        VALID_PROFILE,
        date(2026, 1, 1),
    )
    assert plan_id == "plan-1"
    assert tools.calls[1][0] == "create_plan"
    assert tools.calls[1][1]["duration_days"] == 7

    append_calls = [
        arguments
        for name, arguments in tools.calls
        if name == "append_plan_items"
    ]
    assert all(
        str(UUID(item["id"])) == item["id"]
        for call in append_calls
        for item in call["items"]
    )


@pytest.mark.asyncio
async def test_planner_resolves_functions_from_the_production_registry():
    tools = FakeTools()
    registry = ToolRegistry()

    async def calculate_tdee(profile):
        tools.calls.append(("calculate_tdee", profile))
        return {"bmr": 1500, "tdee": 2000, "daily_kcal": 1800}

    functions = {
        "calculate_tdee": calculate_tdee,
        "create_plan": tools.create_plan,
        "suggest_dish": tools.suggest_dish,
        "suggest_workout": tools.suggest_workout,
        "append_plan_items": tools.append_plan_items,
    }
    for name, fn in functions.items():
        registry.register(
            ToolDescriptor(
                name=name,
                description=name,
                parameters_schema={"type": "object"},
                side="server",
                fn=fn,
            )
        )

    plan_id = await PlannerAgent(registry).createLongTermPlan(
        "u1", "lose_weight", 3, VALID_PROFILE, date(2026, 1, 1)
    )

    assert plan_id == "plan-1"
    assert [
        arguments["day_index"]
        for name, arguments in tools.calls
        if name == "append_plan_items"
    ] == [1, 2, 3]


@pytest.mark.asyncio
async def test_recent_dish_ids_are_bounded():
    tools = FakeTools()
    planner = PlannerAgent(tools)
    await planner.createLongTermPlan(
        "u1",
        "lose_weight",
        7,
        VALID_PROFILE,
        date(2026, 1, 1),
    )
    recent_args = [args for name, args in tools.calls if name == "suggest_dish"]
    assert max(len(args["recent_dish_ids"]) for args in recent_args) <= 12


@pytest.mark.asyncio
async def test_plan_day_coverage_append_called_for_every_day():
    tools = FakeTools()
    await PlannerAgent(tools).createLongTermPlan("u1", "lose_weight", 7, VALID_PROFILE, date(2026, 1, 1))
    append_days = [args["day_index"] for name, args in tools.calls if name == "append_plan_items"]
    assert set(append_days) == set(range(1, 8))


@pytest.mark.asyncio
async def test_plan_kcal_consistency_per_day():
    tools = FakeTools()
    await PlannerAgent(tools).createLongTermPlan("u1", "lose_weight", 7, VALID_PROFILE, date(2026, 1, 1))
    append_calls = [args for name, args in tools.calls if name == "append_plan_items"]
    for call in append_calls:
        meals = [
            item for item in call["items"] if item["item_type"] == "meal"
        ]
        meal_kcal = sum(item["target_kcal"] for item in meals)
        daily_target = meals[0]["payload"]["schedule"]["daily_kcal_target"]
        assert meal_kcal == pytest.approx(daily_target)


def test_sixty_day_phase_mapping_uses_eight_full_weeks_and_four_days():
    total_weeks = 9
    phases = [
        PlannerAgent.phaseIndexForWeek(week, total_weeks)
        for week in range(1, total_weeks + 1)
    ]
    assert phases == [1, 1, 2, 2, 3, 3, 4, 4, 4]


@pytest.mark.asyncio
async def test_sixty_day_plan_follows_weekly_work_rest_rhythm():
    tools = FakeTools()
    await PlannerAgent(tools).createLongTermPlan(
        "u1",
        "lose_weight",
        60,
        VALID_PROFILE,
        date(2026, 1, 5),  # Monday
    )
    calls = {
        args["day_index"]: args
        for name, args in tools.calls
        if name == "append_plan_items"
    }

    assert len(calls) == 60
    last_schedule = calls[60]["items"][0]["payload"]["schedule"]
    assert last_schedule["week_index"] == 9
    assert last_schedule["week_day"] == 4
    assert last_schedule["is_partial_week"] is True

    for week in range(1, 9):
        week_calls = [calls[day] for day in range((week - 1) * 7 + 1, week * 7 + 1)]
        workout_days = sum(
            any(item["item_type"] == "exercise" for item in call["items"])
            for call in week_calls
        )
        assert workout_days == 5
        sunday = week_calls[6]
        assert all(item["item_type"] != "exercise" for item in sunday["items"])
        assert sunday["items"][0]["payload"]["schedule"]["day_kind"] == "rest"


@pytest.mark.asyncio
async def test_rollback_on_tool_failure():
    tools = FakeTools(fail_on="suggest_workout")
    db = FakeDb()
    with pytest.raises(PlannerError, match="suggest_workout"):
        await PlannerAgent(tools, db_session=db).createLongTermPlan("u1", "lose_weight", 3, VALID_PROFILE, date(2026, 1, 1))
    assert any("DELETE FROM plan_items" in sql for sql in db.statements)
    assert any("DELETE FROM plans" in sql for sql in db.statements)


@pytest.mark.asyncio
async def test_incomplete_database_coverage_is_rolled_back():
    tools = FakeTools()
    db = CoverageDb(coverage=(0, 0, 0))

    with pytest.raises(PlannerError, match="PLAN_INCOMPLETE"):
        await PlannerAgent(tools, db_session=db).createLongTermPlan(
            "u1",
            "lose_weight",
            3,
            VALID_PROFILE,
            date(2026, 1, 1),
        )

    assert any("COUNT(DISTINCT day_index)" in sql for sql in db.statements)
    assert any("DELETE FROM plans" in sql for sql in db.statements)
    assert not any("UPDATE plans" in sql for sql in db.statements)
