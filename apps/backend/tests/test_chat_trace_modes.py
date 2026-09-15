from __future__ import annotations

from config import Settings
from services.agent.debug_trace import (
    DebugTraceBuilder,
    classify_provider_token,
    redact_debug_value,
)
from services.agent.llm_client import ToolCall
from services.agent.orchestrator import AgentOrchestrator
from services.agent.tool_dispatcher import ToolResult
from services.agent.public_reasoning_trace import PublicReasoningTrace, record_tool_result


def test_public_trace_is_allowlisted_and_never_accepts_caller_text() -> None:
    trace = PublicReasoningTrace()

    assert trace.add("TODAY_NUTRITION_CHECKED") is True
    assert trace.add("TOOL_CALL suggest_dish args={secret}") is False
    assert trace.add("TODAY_NUTRITION_CHECKED") is False

    payload = trace.to_dict()
    assert payload["steps"] == [
        {
            "public_event_type": "TODAY_NUTRITION_CHECKED",
            "title": "Đã đối chiếu nhật ký hôm nay",
            "summary": "Mình kiểm tra dữ liệu đã ghi để tránh gợi ý trùng lặp.",
            "timestamp": payload["steps"][0]["timestamp"],
            "order": 1,
        }
    ]
    assert "suggest_dish" not in str(payload)


def test_public_trace_maps_known_tool_outcomes_but_drops_unknown_tool() -> None:
    trace = PublicReasoningTrace()
    record_tool_result(trace, "suggest_dish", ok=True)
    record_tool_result(trace, "unregistered_internal_tool", ok=True)

    assert [step.public_event_type for step in trace.steps] == [
        "FOOD_CATALOG_SEARCHED",
        "RECOMMENDATION_SELECTED",
    ]


def test_public_trace_exposes_catalog_then_approved_recipe_search() -> None:
    trace = PublicReasoningTrace()

    record_tool_result(trace, "search_dish_catalog", ok=True)
    record_tool_result(trace, "search_recipe_web", ok=True)

    assert [step.public_event_type for step in trace.steps] == [
        "FOOD_CATALOG_SEARCHED",
        "EXTERNAL_RECIPE_SEARCHED",
    ]
    assert trace.steps[1].title == "Đã tìm nguồn công thức ngoài"
    assert "nhãn xác minh" in trace.steps[1].summary


def test_public_trace_uses_domain_accurate_copy_for_nutrition_weight_and_lifestyle() -> None:
    trace = PublicReasoningTrace()

    record_tool_result(trace, "search_food_nutrition", ok=True)
    record_tool_result(trace, "get_weight_history", ok=True)
    record_tool_result(trace, "get_lifestyle_logs", ok=True)

    assert [step.public_event_type for step in trace.steps] == [
        "NUTRITION_DATA_SEARCHED",
        "BODY_PROGRESS_CHECKED",
        "LIFESTYLE_LOGS_CHECKED",
    ]
    assert [step.title for step in trace.steps] == [
        "Đã tra thông tin dinh dưỡng",
        "Đã xem dữ liệu cân nặng",
        "Đã xem nhật ký lối sống",
    ]


def test_debug_trace_recursively_redacts_secrets_and_unneeded_pii() -> None:
    builder = DebugTraceBuilder(enabled=True)
    event = builder.record(
        "tool",
        "dispatcher",
        "TOOL_CALL",
        payload={
            "authorization": "Bearer eyJvery.secret.token",
            "nested": [
                {"api_key": "abc-123", "email": "person@example.com"},
                {
                    "phone": "+84999999999",
                    "firebase_service_account": {"private_key": "very-private"},
                    "cookie": "session=secret-cookie",
                    "safe": "dinner",
                },
            ],
            "message": "password=letmein access_token=token-value",
        },
    )

    assert event is not None
    rendered = str(event.to_dict())
    for forbidden in (
        "abc-123", "person@example.com", "+84999999999", "letmein",
        "token-value", "very-private", "secret-cookie",
    ):
        assert forbidden not in rendered
    assert "dinner" in rendered
    assert "[REDACTED]" in rendered


def test_hidden_provider_reasoning_is_classified_internal_only() -> None:
    class Token:
        token_type = "reasoning_content"

        def __str__(self) -> str:
            return "private scratchpad"

    assert classify_provider_token(Token()) == "INTERNAL_REASONING"
    assert redact_debug_value("Authorization: Bearer super-secret") == "Authorization: [REDACTED]"
    assert "person@example.com" not in redact_debug_value("contact person@example.com")
    assert "+84999999999" not in redact_debug_value("phone +84999999999")
    assert "10.776" not in redact_debug_value("latitude=10.776 longitude=106.700")


def test_debug_policy_is_server_side_and_never_enabled_in_production() -> None:
    assert Settings(app_environment="production", chat_trace_mode="debug").debug_trace_allowed_for(
        developer_authenticated=True
    ) is False
    assert Settings(app_environment="development", chat_trace_mode="debug").debug_trace_allowed_for(
        developer_authenticated=False
    ) is True
    assert Settings(app_environment="staging", chat_trace_mode="debug").debug_trace_allowed_for(
        developer_authenticated=False
    ) is False
    assert Settings(app_environment="staging", chat_trace_mode="debug").debug_trace_allowed_for(
        developer_authenticated=True
    ) is True


def test_debug_tool_telemetry_uses_field_names_and_safe_ids_not_profile_records() -> None:
    call = ToolCall(
        id="profile-read",
        name="get_user_profile",
        arguments={"authorization": "Bearer secret", "meal_type": "dinner"},
    )
    result = ToolResult(
        ok=True,
        data={
            "email": "private@example.com",
            "medical_history": "private condition",
            "weight_kg": 72,
            "catalog_dish_id": "dish-7",
        },
    )

    call_payload = AgentOrchestrator._debug_tool_call_payload(call)
    result_payload = AgentOrchestrator._debug_tool_result_payload(call, result)
    rendered = str({"call": call_payload, "result": result_payload})

    assert call_payload["sanitized_arguments"] == {"meal_type": "dinner"}
    assert result_payload["result_keys"] == [
        "catalog_dish_id", "email", "medical_history", "weight_kg"
    ]
    assert result_payload["catalog_dish_id"] == "dish-7"
    for private_value in ("private@example.com", "private condition", "72"):
        assert private_value not in rendered
