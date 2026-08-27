from __future__ import annotations

from dataclasses import dataclass

import pytest

from modules.nutrition.catalog import load_dish_catalog
from services.agent.llm_client import ToolCall
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_server_tools
from services.agent.tools.dish import _DISHES, suggest_dish
from services.agent.tools.workout import _EXERCISES, suggest_workout


def test_agent_dish_tool_sees_a_reference_recipe_beyond_old_97_limit() -> None:
    catalog = load_dish_catalog()
    new_dish = next(item for item in catalog if int(item["id"]) > 97)

    result = suggest_dish(
        meal_type=new_dish["meal_types"][0],
        target_kcal=float(new_dish["estimated_calories"]),
        query=new_dish["name"],
    )

    assert len(catalog) == 300
    assert len(_DISHES) == 300
    assert result["id"] == new_dish["id"]
    assert result["name"] == new_dish["name"]
    assert result["catalog_status"] == "normalized_reference_recipe"


def test_missing_wger_equipment_is_not_assumed_to_be_bodyweight() -> None:
    cable_curl = next(item for item in _EXERCISES if item.id == 95)
    leg_press = next(item for item in _EXERCISES if item.id == 146)

    assert cable_curl.equipment == ("cable",)
    assert cable_curl.is_bodyweight is False
    assert "machine" in leg_press.equipment
    assert leg_press.is_bodyweight is False

    bodyweight_plan = suggest_workout("full_body", 40, "none", "advanced")
    selected = {item["wger_id"] for item in bodyweight_plan["exercises"]}
    assert 95 not in selected
    assert 146 not in selected


def test_workout_uses_weight_for_met_calorie_estimate() -> None:
    light = suggest_workout(
        "full_body",
        30,
        "any",
        "intermediate",
        {"weight_kg": 50},
    )
    heavy = suggest_workout(
        "full_body",
        30,
        "any",
        "intermediate",
        {"weight_kg": 100},
    )

    assert [item["wger_id"] for item in light["exercises"]] == [
        item["wger_id"] for item in heavy["exercises"]
    ]
    assert heavy["total_calories_burned"] == pytest.approx(
        light["total_calories_burned"] * 2,
        abs=0.05,
    )
    assert heavy["calorie_estimate"]["weight_kg"] == 100
    assert heavy["calorie_estimate"]["estimated"] is True


def test_workout_goal_changes_resistance_dosage() -> None:
    strength = suggest_workout(
        "chest", 20, "any", "intermediate", goal="strength"
    )
    endurance = suggest_workout(
        "chest", 20, "any", "intermediate", goal="endurance"
    )

    assert all(item["reps"] == "5-8" for item in strength["exercises"])
    assert all(item["rest_seconds"] == 120 for item in strength["exercises"])
    assert all(item["sets"] == 2 for item in strength["exercises"])
    assert all(item["reps"] == "12-15" for item in endurance["exercises"])
    assert all(item["rest_seconds"] == 45 for item in endurance["exercises"])

    beginner_gain = suggest_workout(
        "full_body", 20, "none", "beginner", goal="muscle_gain"
    )
    assert all(item["sets"] == 2 for item in beginner_gain["exercises"])


def test_recovery_workout_uses_low_intensity_mobility_catalog() -> None:
    plan = suggest_workout(
        "mobility",
        20,
        "none",
        "intermediate",
        {"weight_kg": 60},
        goal="recovery",
    )

    assert plan["effective_level"] == "beginner"
    assert plan["goal"] == "recovery"
    assert len(plan["exercises"]) == 4
    assert all(item["met"] <= 3.5 for item in plan["exercises"])


@pytest.mark.parametrize(
    "symptom",
    ["chest_pain", "severe_shortness_of_breath", "dizziness", "fainting"],
)
def test_workout_refuses_warning_symptoms(symptom: str) -> None:
    with pytest.raises(ValueError, match="UNSAFE_TO_RECOMMEND_WORKOUT"):
        suggest_workout(
            "full_body",
            20,
            "none",
            "beginner",
            {"warning_symptoms": [symptom]},
        )


@dataclass
class _Gateway:
    user_context: dict
    user_id: str = "user-1"


@pytest.mark.asyncio
async def test_dispatcher_injects_profile_weight_and_health_goal() -> None:
    registry = ToolRegistry()
    register_server_tools(registry)
    dispatcher = ToolDispatcher(
        registry,
        gateway=_Gateway({"weight": 82, "health_goal": "gain_muscle"}),
    )
    call = ToolCall(
        id="workout-1",
        name="suggest_workout",
        arguments={
            "muscle_group": "full_body",
            "duration_min": 20,
            "equipment": "any",
            "level": "intermediate",
        },
    )

    result = await dispatcher.dispatch("session-1", call, timeout_ms=5_000)

    assert result.ok is True
    assert result.data["goal"] == "muscle_gain"
    assert result.data["calorie_estimate"]["weight_kg"] == 82
    assert call.arguments["user_state"]["weight_kg"] == 82
    assert call.arguments["goal"] == "muscle_gain"


@pytest.mark.asyncio
async def test_dispatcher_preserves_workout_safety_error_code() -> None:
    registry = ToolRegistry()
    register_server_tools(registry)
    dispatcher = ToolDispatcher(registry)
    call = ToolCall(
        id="unsafe-workout-1",
        name="suggest_workout",
        arguments={
            "muscle_group": "full_body",
            "duration_min": 20,
            "equipment": "none",
            "level": "beginner",
            "user_state": {"warning_symptoms": ["chest_pain"]},
        },
    )

    result = await dispatcher.dispatch("session-1", call, timeout_ms=5_000)

    assert result.ok is False
    assert result.error == "UNSAFE_TO_RECOMMEND_WORKOUT"
