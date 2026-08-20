from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from services.agent.llm_client import LLMResponse, StreamingToken, ToolCall
from services.agent.memory_service import Context
from services.agent.orchestrator import AgentOrchestrator
from services.agent.tool_dispatcher import ToolResult


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
    thoughts: list[str] = field(default_factory=list)
    done: list[tuple[str, list[dict[str, Any]]]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    async def send_token(self, token):
        self.tokens.append(token)

    async def send_thought(self, token):
        self.thoughts.append(token)

    async def send_done(self, full_response, performed_actions):
        self.done.append((full_response, performed_actions))

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


@pytest.mark.asyncio
async def test_handle_chat_message_streams_text_and_done():
    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM([LLMResponse(content_stream=_stream(["xin ", "chào"]), full_text="xin chào")])
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway, max_steps=3)

    await orchestrator.handleChatMessage("s1", "hi")

    assert gateway.tokens == ["xin ", "chào"]
    assert gateway.done == [("xin chào", [])]
    assert store.turns[0][:3] == ("s1", "user", "hi")
    assert store.turns[-1][:3] == ("s1", "assistant", "xin chào")


@pytest.mark.asyncio
async def test_handle_chat_message_persists_streamed_thoughts_for_history():
    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM([
        LLMResponse(
            content_stream=_stream([
                StreamingToken("Phân tích yêu cầu. ", "thought"),
                StreamingToken("Đối chiếu dữ liệu.", "thought"),
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

    assert gateway.thoughts == ["Phân tích yêu cầu. ", "Đối chiếu dữ liệu."]
    assistant_turn = next(turn for turn in store.turns if turn[1] == "assistant")
    assert assistant_turn[5] == "Phân tích yêu cầu. Đối chiếu dữ liệu."


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
    assert gateway.done[0][1][0]["tool"] == "get_today_meals"


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
