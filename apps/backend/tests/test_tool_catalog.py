from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_client_tools, register_server_tools


def test_tool_catalog_registers_all_tools():
    registry = ToolRegistry()
    register_server_tools(registry)
    register_client_tools(registry)

    expected = {
        "get_user_profile",
        "get_today_meals",
        "get_today_exercises",
        "get_meal_log_range",
        "get_exercise_log_range",
        "update_workout_profile",
        "update_nutrition_profile",
        "get_weight_history",
        "log_meal",
        "log_exercise",
        "log_weight",
        "get_lifestyle_logs",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "navigate_to_screen",
        "suggest_dish",
        "search_dish_catalog",
        "suggest_workout",
        "search_exercise_catalog",
        "build_personalized_workout",
        "get_workout_substitutions",
        "save_workout_plan",
        "log_workout_result",
        "calculate_tdee",
            "search_food_nutrition",
            "build_combined_plan",
            "build_nutrition_plan",
        "build_workout_schedule",
        "get_plan",
        "get_active_plan_v2",
        "revise_plan",
        "save_plan",
        "set_plan_status",
        "query_rag",
        "search_medical_knowledge",
    }

    assert set(registry.names()) == expected
    assert len(registry.schemas()) == 35
    assert not {"create_long_term_plan", "create_plan", "append_plan_items", "get_active_plan", "mark_plan_item_complete"}.intersection(registry.names())


def test_client_write_tools_require_request_id():
    registry = ToolRegistry()
    register_client_tools(registry)

    write_tools = {
        "log_meal",
        "log_exercise",
        "log_weight",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "navigate_to_screen",
        "update_workout_profile",
    }
    for name in write_tools:
        descriptor = registry.get(name)
        assert descriptor is not None
        assert descriptor.idempotent is False
        assert "request_id" in descriptor.parameters_schema["required"]


def test_server_tool_sides_and_idempotency():
    registry = ToolRegistry()
    register_server_tools(registry)

    assert registry.get("suggest_dish").side == "server"
    assert registry.get("suggest_dish").idempotent is True
    assert registry.get("search_dish_catalog").idempotent is True
    assert registry.get("search_exercise_catalog").idempotent is True
    assert registry.get("build_nutrition_plan").idempotent is True
    assert registry.get("save_plan").idempotent is False
    assert registry.get("set_plan_status").idempotent is False
