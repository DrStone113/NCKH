from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_client_tools, register_server_tools


def test_tool_catalog_registers_all_22_tools():
    registry = ToolRegistry()
    register_server_tools(registry)
    register_client_tools(registry)

    expected = {
        "get_user_profile",
        "get_today_meals",
        "get_today_exercises",
        "get_meal_log_range",
        "get_exercise_log_range",
        "get_weight_history",
        "get_active_plan",
        "log_meal",
        "log_exercise",
        "log_weight",
        "get_lifestyle_logs",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "mark_plan_item_complete",
        "navigate_to_screen",
        "suggest_dish",
        "suggest_workout",
        "calculate_tdee",
        "search_food_nutrition",
        "create_plan",
        "append_plan_items",
        "query_rag",
    }

    assert set(registry.names()) == expected
    assert len(registry.schemas()) == 22


def test_client_write_tools_require_request_id():
    registry = ToolRegistry()
    register_client_tools(registry)

    write_tools = {
        "log_meal",
        "log_exercise",
        "log_weight",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "mark_plan_item_complete",
        "navigate_to_screen",
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
    assert registry.get("create_plan").idempotent is False
    assert registry.get("append_plan_items").idempotent is False