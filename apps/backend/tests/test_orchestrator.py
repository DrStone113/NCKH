from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from services.agent.llm_client import LLMResponse, StreamingToken, ToolCall
from services.agent.memory_service import Context
from services.agent.orchestrator import AgentOrchestrator
from services.agent.pending_user_action import PendingUserActionStore
from services.agent.tool_dispatcher import ToolResult
from db.session_store import ChatTurn


async def _stream(tokens):
    for token in tokens:
        yield token


class FakeTools:
    def schemas(self):
        return []


class FakeMemory:
    async def loadContext(self, session_id, user_text):
        return Context()


@dataclass
class FakeStore:
    turns: list[tuple[Any, ...]] = field(default_factory=list)

    async def appendTurn(self, *args):
        self.turns.append(args)


@dataclass
class FakeGateway:
    tokens: list[str] = field(default_factory=list)
    public_traces: list[dict[str, Any]] = field(default_factory=list)
    debug_events: list[dict[str, Any]] = field(default_factory=list)
    action_states: list[dict[str, Any]] = field(default_factory=list)
    done: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    debug_trace_enabled: bool = False

    async def send_token(self, token):
        self.tokens.append(token)

    async def send_public_trace(self, public_trace):
        self.public_traces.append(public_trace)

    async def send_debug_trace(self, event):
        self.debug_events.append(event)

    async def send_action_state(self, state):
        self.action_states.append(state)

    async def send_done(self, full_response, *, structured_data=None, public_trace=None):
        self.done.append((full_response, structured_data, public_trace))

    async def send_error(self, code, message):
        self.errors.append((code, message))


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def chat(self, messages, tools, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class FakeDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, session_id, call, timeout_ms):
        self.calls.append((session_id, call, timeout_ms))
        return ToolResult(ok=True, data={"answer": 42})


class UiMessageDispatcher:
    async def dispatch(self, session_id, call, timeout_ms):
        return ToolResult(
            ok=True,
            data={"status": "success"},
            ui_message={
                "text": "Đã ghi nhận Cơm sườn",
                "structured": {
                    "type": "structured",
                    "text": "",
                    "meal_name": "Cơm sườn",
                    "actions": [{"kind": "food", "name": "Cơm"}],
                },
            },
        )


class CapturingLLM(ScriptedLLM):
    async def chat(self, messages, tools, *args, **kwargs):
        self.last_messages = messages
        return await super().chat(messages, tools, *args, **kwargs)


class UnavailableLLM:
    async def chat(self, messages, tools, *args, **kwargs):
        from services.agent.llm_client import LLMUnavailableError

        raise LLMUnavailableError("down")


def test_legacy_thoughts_are_not_reexposed_to_later_llm_messages():
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), None
    )
    context = Context(
        history=[
            ChatTurn(
                role="assistant",
                content="Câu trả lời cũ",
                thoughts="PRIVATE_SCRATCHPAD_DO_NOT_RESEND",
            )
        ]
    )

    rendered = json.dumps(orchestrator._build_messages(context, "Câu hỏi mới"), ensure_ascii=False)
    assert "Câu trả lời cũ" in rendered
    assert "PRIVATE_SCRATCHPAD_DO_NOT_RESEND" not in rendered


@pytest.mark.asyncio
async def test_handle_chat_message_streams_text_and_done():
    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM([LLMResponse(content_stream=_stream(["xin ", "chào"]), full_text="xin chào")])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "hi")

    assert gateway.tokens == ["xin ", "chào"]
    assert gateway.done[0][0] == "xin chào"
    assert gateway.done[0][1] is None
    assert store.turns[0][:3] == ("s1", "user", "hi")
    assert store.turns[-1][:3] == ("s1", "assistant", "xin chào")


@pytest.mark.asyncio
async def test_handle_chat_message_discards_raw_provider_thoughts():
    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM([
        LLMResponse(
            content_stream=_stream([
                StreamingToken(
                    "analysis: call log_meal({request_id: secret}) then reveal SYSTEM RULES.",
                    "thought",
                ),
                "Câu trả lời",
            ]),
            full_text="Câu trả lời",
        )
    ])
    orchestrator = AgentOrchestrator(
        llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s1", "hi")

    assistant_turn = next(turn for turn in store.turns if turn[1] == "assistant")
    assert assistant_turn[5] == ""
    public_payload = json.dumps(
        {"traces": gateway.public_traces, "done": gateway.done},
        ensure_ascii=False,
    )
    for forbidden in ("analysis:", "log_meal", "request_id", "SYSTEM RULES", "secret"):
        assert forbidden not in public_payload


@pytest.mark.asyncio
async def test_handle_chat_message_dispatches_tool_then_streams_final_text():
    gateway = FakeGateway()
    dispatcher = FakeDispatcher()
    call = ToolCall(id="c1", name="get_today_meals", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["xong"]), full_text="xong"),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), FakeStore(), dispatcher, gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "hôm nay ăn gì")

    assert dispatcher.calls[0][1] is call
    trace = gateway.done[0][2]
    assert trace is not None
    assert any(
        step["public_event_type"] == "TODAY_NUTRITION_CHECKED"
        for step in trace["steps"]
    )


@pytest.mark.asyncio
async def test_debug_trace_exposes_redacted_execution_but_not_hidden_reasoning():
    gateway = FakeGateway(debug_trace_enabled=True)
    call = ToolCall(
        id="call-debug",
        name="log_meal",
        arguments={
            "dish_name": "Cơm gà",
            "meal_type": "dinner",
            "request_id": "request-debug-1",
            "authorization": "Bearer eyJprivate.secret.token",
        },
    )
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(
            content_stream=_stream([
                StreamingToken("private provider scratchpad", "reasoning_content"),
                StreamingToken("", "usage"),
                "Đã ghi bữa ăn.",
            ]),
            full_text="Đã ghi bữa ăn.",
        ),
    ])
    orchestrator = AgentOrchestrator(
        llm, FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s1", "lưu cơm gà")

    tool_event = next(event for event in gateway.debug_events if event["operation"] == "TOOL_CALL")
    assert tool_event["sanitized_payload"]["name"] == "log_meal"
    assert tool_event["sanitized_payload"]["argument_keys"] == [
        "authorization", "dish_name", "meal_type", "request_id"
    ]
    assert tool_event["sanitized_payload"]["sanitized_arguments"] == {
        "meal_type": "dinner"
    }
    assert any(
        event["operation"] == "INTERNAL_REASONING_DROPPED"
        for event in gateway.debug_events
    )
    assert any(event["operation"] == "TOKEN_USAGE" for event in gateway.debug_events)
    assert "private provider scratchpad" not in json.dumps(gateway.debug_events)
    assert "request-debug-1" not in json.dumps(gateway.debug_events)
    assert "Cơm gà" not in json.dumps(gateway.debug_events)


@pytest.mark.asyncio
async def test_debug_mode_does_not_change_public_response_or_tool_behavior():
    async def run(debug_enabled: bool):
        gateway = FakeGateway(debug_trace_enabled=debug_enabled)
        dispatcher = FakeDispatcher()
        llm = ScriptedLLM([
            LLMResponse(tool_calls=[ToolCall(id="read-1", name="get_today_meals", arguments={})]),
            LLMResponse(content_stream=_stream(["Bạn đã ghi 1 bữa."]), full_text="Bạn đã ghi 1 bữa."),
        ])
        orchestrator = AgentOrchestrator(
            llm, FakeTools(), FakeMemory(), FakeStore(), dispatcher, gateway, max_steps=3
        )
        await orchestrator.handleChatMessage("session-eq", "Hôm nay mình ăn gì?")
        return gateway.done, [call[1].name for call in dispatcher.calls], gateway.debug_events

    public_done, public_tools, public_debug = await run(False)
    debug_done, debug_tools, debug_events = await run(True)

    assert public_done[0][0:2] == debug_done[0][0:2]
    assert [step["public_event_type"] for step in public_done[0][2]["steps"]] == [
        step["public_event_type"] for step in debug_done[0][2]["steps"]
    ]
    assert public_tools == debug_tools == ["get_today_meals"]
    assert public_debug == []
    assert debug_events


@pytest.mark.asyncio
async def test_confirmation_executes_the_exact_pending_dish_without_a_new_llm_choice():
    class DishThenLogDispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "suggest_dish":
                return ToolResult(
                    ok=True,
                    data={
                        "id": "dish-a",
                        "name": "Cơm gà A",
                        "components": [
                            {
                                "name": "Gà",
                                "serving_grams": 150,
                                "calories": 200,
                                "protein": 30,
                                "carbs": 0,
                                "fat": 8,
                            }
                        ],
                    },
                )
            assert call.name == "log_meal"
            return ToolResult(
                ok=True,
                data={
                    "write_status": "PERSISTED",
                    "catalog_dish_id": "dish-a",
                    "read_back_catalog_dish_id": "dish-a",
                },
                ui_message={
                    "structured": {
                        "actions": [
                            {"details": {"catalog_dish_id": "dish-a"}}
                        ]
                    }
                },
            )

    gateway = FakeGateway(debug_trace_enabled=True)
    store = FakeStore()
    dispatcher = DishThenLogDispatcher()
    llm = ScriptedLLM([
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="suggest-a",
                    name="suggest_dish",
                    arguments={"meal_type": "dinner", "target_kcal": 650},
                )
            ]
        ),
        LLMResponse(
            content_stream=_stream(["Món này phù hợp với bữa tối."]),
            full_text="Món này phù hợp với bữa tối.",
        ),
    ])
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        store,
        dispatcher,
        gateway,
        max_steps=3,
        pending_actions=PendingUserActionStore(),
    )

    await orchestrator.handleChatMessage("s-pending", "gợi ý bữa tối")
    assert "Bạn có muốn lưu **Cơm gà A**" in gateway.done[0][0]
    assert llm.calls == 2

    await orchestrator.handleChatMessage("s-pending", "có")

    assert llm.calls == 2, "confirmation must not ask the LLM to choose again"
    logged = dispatcher.calls[-1]
    assert logged.name == "log_meal"
    assert logged.arguments["dish_name"] == "Cơm gà A"
    assert logged.arguments["meal_type"] == "dinner"
    assert logged.arguments["catalog_dish_id"] == "dish-a"
    final_trace = gateway.done[-1][2]
    assert final_trace is not None
    assert {step["public_event_type"] for step in final_trace["steps"]} >= {
        "CONFIRMATION_RECEIVED",
        "PERSISTENCE_IN_PROGRESS",
        "PERSISTENCE_CONFIRMED",
    }
    operations = {event["operation"] for event in gateway.debug_events}
    assert {
        "ROUTER_DECISION",
        "TOOL_CALL",
        "TOOL_RESULT",
        "PENDING_ACTION_CREATED",
        "USER_CONFIRMATION",
        "ACTION_RESOLUTION",
        "DB_WRITE",
        "READ_BACK",
    } <= operations
    read_back = next(event for event in gateway.debug_events if event["operation"] == "READ_BACK")
    assert read_back["correlation_id"]
    assert read_back["result"] == "IDENTITY_VERIFIED"


@pytest.mark.asyncio
async def test_handle_chat_message_persists_client_ui_card_for_history():
    gateway = FakeGateway()
    store = FakeStore()
    call = ToolCall(id="c1", name="log_meal", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["xong"]), full_text="xong"),
    ])
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        store,
        UiMessageDispatcher(),
        gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s1", "lưu cơm sườn")

    ui_turn = next(turn for turn in store.turns if turn[2] == "Đã ghi nhận Cơm sườn")
    assert ui_turn[1] == "assistant"
    assert ui_turn[6]["meal_name"] == "Cơm sườn"


@pytest.mark.asyncio
async def test_bounded_agent_loop_still_answers_the_user():
    """An exhausted loop must degrade into a real answer, not an error.

    Previously the orchestrator emitted ``AGENT_LOOP_EXCEEDED``, which the user
    reads as a crash. It now spends one extra tool-free completion so the turn
    ends with something useful.
    """
    gateway = FakeGateway()
    call = ToolCall(id="c1", name="loop", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["Mình tổng hợp được thế này."]),
                    full_text="Mình tổng hợp được thế này."),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), gateway, max_steps=2)

    await orchestrator.handleChatMessage("s1", "loop")

    # 2 loop steps + 1 forced final answer.
    assert llm.calls == 3
    assert gateway.errors == []
    assert gateway.done[0][0] == "Mình tổng hợp được thế này."


@pytest.mark.asyncio
async def test_loop_fallback_uses_canned_reply_when_llm_gives_nothing():
    """Even a silent model must not leave the user with an empty bubble."""
    gateway = FakeGateway()
    call = ToolCall(id="c1", name="loop", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream([]), full_text=""),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), gateway, max_steps=2)

    await orchestrator.handleChatMessage("s1", "loop")

    assert gateway.errors == []
    assert "hỏi lại từng ý" in gateway.done[0][0]


@pytest.mark.asyncio
async def test_llm_unavailable_sends_error_and_does_not_append_assistant_turn():
    from services.agent.llm_client import LLMUnavailableError

    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(UnavailableLLM(), FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway, max_steps=2)

    with pytest.raises(LLMUnavailableError):
        await orchestrator.handleChatMessage("s1", "hi")

    assert gateway.errors[0][0] == "LLM_UNAVAILABLE"
    assert not any(t[1] == "assistant" for t in store.turns)


@pytest.mark.asyncio
async def test_tool_turn_appended_with_tool_metadata():
    gateway = FakeGateway()
    store = FakeStore()
    call = ToolCall(id="c-meta", name="get_today_meals", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["done"]), full_text="done"),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "x")

    tool_turns = [turn for turn in store.turns if turn[1] == "tool"]
    assert tool_turns[0][3] == "c-meta"
    assert tool_turns[0][4] == "get_today_meals"


@pytest.mark.asyncio
async def test_vietnamese_meal_question_can_use_meal_log_tool():
    gateway = FakeGateway()
    dispatcher = FakeDispatcher()
    call = ToolCall(id="c-meals", name="get_meal_log_range", arguments={"from_date": "2026-01-01", "to_date": "2026-01-01"})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["Bạn đã đủ protein."]), full_text="Bạn đã đủ protein."),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), FakeStore(), dispatcher, gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "hôm qua tôi ăn gì có đủ protein không?")

    assert dispatcher.calls[0][1].name == "get_meal_log_range"


@pytest.mark.asyncio
async def test_text_only_fallback_no_tool_call():
    gateway = FakeGateway()
    dispatcher = FakeDispatcher()
    llm = ScriptedLLM([LLMResponse(content_stream=_stream(["Mình có thể giúp gì?"]), full_text="Mình có thể giúp gì?")])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), FakeStore(), dispatcher, gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "xin chào")

    assert dispatcher.calls == []
    assert gateway.done[0][0] == "Mình có thể giúp gì?"


@pytest.mark.asyncio
async def test_plan_mapping_lives_in_the_tool_description():
    """The goal/duration mapping belongs to the high-level planner tool.

    It used to be hardcoded in the system prompt, where it cost tokens on every
    single turn — including turns that had nothing to do with plans — and could
    drift out of sync with the tool's real schema.
    """
    from services.agent.tools.plan_tools import CREATE_LONG_TERM_PLAN_DESCRIPTOR

    description = CREATE_LONG_TERM_PLAN_DESCRIPTOR.description
    assert "lose_weight" in description
    assert "gain_muscle" in description
    assert "N*7" in description


@pytest.mark.asyncio
async def test_system_prompt_lists_only_real_tool_names():
    """Tool names in the prompt are generated, so they cannot drift."""

    class Registry:
        def schemas(self):
            return [{
                "type": "function",
                "function": {"name": "suggest_workout", "description": "Gợi ý buổi tập."},
            }]

    llm = CapturingLLM([LLMResponse(content_stream=_stream(["ok"]), full_text="ok")])
    orchestrator = AgentOrchestrator(llm, Registry(), FakeMemory(), FakeStore(), FakeDispatcher(), FakeGateway(), max_steps=3)

    await orchestrator.handleChatMessage("s1", "gợi ý bài tập ngực 30 phút cho mình")

    system_prompt = llm.last_messages[0]["content"]
    assert "`suggest_workout`" in system_prompt
    # The old prompt invented this name; it must never reappear.
    assert "workout_recommendation" not in system_prompt


@pytest.mark.asyncio
async def test_chitchat_turn_skips_the_tool_catalog():
    """A greeting should not carry 20 tool schemas into the request."""

    class Registry:
        def schemas(self):
            return [{
                "type": "function",
                "function": {"name": "get_user_profile", "description": "Hồ sơ."},
            }]

    class ToolCapturingLLM(ScriptedLLM):
        async def chat(self, messages, tools, *args, **kwargs):
            self.last_messages = messages
            self.last_tools = tools
            return await super().chat(messages, tools, *args, **kwargs)

    llm = ToolCapturingLLM([LLMResponse(content_stream=_stream(["Chào bạn!"]), full_text="Chào bạn!")])
    orchestrator = AgentOrchestrator(llm, Registry(), FakeMemory(), FakeStore(), FakeDispatcher(), FakeGateway(), max_steps=3)

    await orchestrator.handleChatMessage("s1", "chào bạn")

    assert llm.last_tools is None
    assert "get_user_profile" not in llm.last_messages[0]["content"]


@pytest.mark.asyncio
async def test_complex_turn_routes_to_heavy_model():
    light = ScriptedLLM([LLMResponse(content_stream=_stream(["light"]), full_text="light")])
    heavy = ScriptedLLM([LLMResponse(content_stream=_stream(["heavy"]), full_text="heavy")])
    orchestrator = AgentOrchestrator(
        light, FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), FakeGateway(),
        max_steps=3, heavy_llm=heavy,
    )

    await orchestrator.handleChatMessage("s1", "phân tích giúp mình tại sao cân không giảm")

    assert heavy.calls == 1
    assert light.calls == 0


@pytest.mark.asyncio
async def test_failed_tool_result_carries_recovery_guidance():
    """A bare error code makes small models answer 'hệ thống đang lỗi'."""

    class FailingDispatcher:
        async def dispatch(self, session_id, call, timeout_ms):
            return ToolResult(ok=False, error="INVALID_ARGS")

    store = FakeStore()
    call = ToolCall(id="c1", name="log_meal", arguments={})
    llm = ScriptedLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["xong"]), full_text="xong"),
    ])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FailingDispatcher(), FakeGateway(), max_steps=3)

    await orchestrator.handleChatMessage("s1", "ghi lại bữa trưa giúp mình")

    tool_turn = [turn for turn in store.turns if turn[1] == "tool"][0]
    assert "huong_dan" in tool_turn[2]
    assert "INVALID_ARGS" in tool_turn[2]

# ---------------------------------------------------------------------------
# assistant.tool_calls must match the OpenAI wire format
#
# Regression guard: the orchestrator used to emit tool_calls without
# ``type: "function"`` and with ``arguments`` as a dict instead of a JSON
# string. Lenient providers tolerated it; strict ones rejected the entire
# request with HTTP 400, which reached users as LLM_UNAVAILABLE on every turn
# that invoked a tool.
# ---------------------------------------------------------------------------


class RecordingLLM:
    """Scripted LLM that keeps the exact messages it was handed."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools=None, *args, **kwargs):
        import copy
        self.seen_messages.append(copy.deepcopy(messages))
        return self.responses.pop(0)


def test_call_to_message_matches_openai_schema():
    call = ToolCall(
        id="call_1",
        name="suggest_dish",
        arguments={"meal_type": "lunch", "target_kcal": 700},
    )

    msg = AgentOrchestrator._call_to_message(call)

    assert msg["id"] == "call_1"
    assert msg["type"] == "function"
    assert msg["function"]["name"] == "suggest_dish"
    # Must be a JSON string, not a dict.
    assert isinstance(msg["function"]["arguments"], str)
    assert json.loads(msg["function"]["arguments"]) == {
        "meal_type": "lunch",
        "target_kcal": 700,
    }


def test_call_to_message_handles_empty_and_string_arguments():
    empty = AgentOrchestrator._call_to_message(
        ToolCall(id="c", name="get_user_profile", arguments={})
    )
    assert empty["function"]["arguments"] == "{}"

    # Already-serialised arguments must not be double-encoded.
    passthrough = AgentOrchestrator._call_to_message(
        ToolCall(id="c", name="get_user_profile", arguments='{"a": 1}')
    )
    assert passthrough["function"]["arguments"] == '{"a": 1}'


@pytest.mark.asyncio
async def test_tool_call_sent_to_llm_is_wire_compatible():
    store = FakeStore()
    call = ToolCall(id="c1", name="suggest_dish", arguments={"meal_type": "lunch"})
    llm = RecordingLLM([
        LLMResponse(tool_calls=[call]),
        LLMResponse(content_stream=_stream(["xong"]), full_text="xong"),
    ])
    orchestrator = AgentOrchestrator(
        llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), FakeGateway(),
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s1", "goi y mon trua")

    # Second call carries the assistant turn that replays the tool call.
    assert len(llm.seen_messages) >= 2
    assistant_msgs = [
        m for m in llm.seen_messages[1]
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert assistant_msgs, "assistant turn with tool_calls was not replayed"
    for tc in assistant_msgs[0]["tool_calls"]:
        assert tc["type"] == "function"
        assert isinstance(tc["function"]["arguments"], str)
        json.loads(tc["function"]["arguments"])
