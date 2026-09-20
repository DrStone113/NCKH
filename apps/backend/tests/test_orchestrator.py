from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from services.agent.llm_client import LLMResponse, StreamingToken, ToolCall
from services.agent.memory_service import Context
from services.agent.orchestrator import (
    AgentOrchestrator,
    _detect_safety_pain_response,
    _ground_suggest_dish_queries,
    _select_relevant_tool_schemas,
)
from services.agent.pending_user_action import PendingUserActionStore
from services.agent.scope_guard import ScopeGuard
from services.agent.tool_dispatcher import ToolResult
from db.session_store import ChatTurn


async def _stream(tokens):
    for token in tokens:
        yield token


class FakeTools:
    def schemas(self):
        return []


class FailingTools:
    def schemas(self):
        raise AssertionError("scope gate should run before tool selection")


class FakeMemory:
    async def loadContext(self, session_id, user_text):
        return Context()


class FailingMemory:
    async def loadContext(self, session_id, user_text):
        raise AssertionError("scope gate should run before memory and RAG")

    async def loadRecentConversationForScope(self, session_id, *, max_turns=12):
        raise AssertionError("clear out-of-scope turns must not read session history")


class ContextualContinuationMemory(FakeMemory):
    def __init__(self, history=None):
        self.scope_history_calls = 0
        self.scope_history = history if history is not None else [
            ChatTurn(role="user", content="Tôi muốn ăn burger phô mai"),
            ChatTurn(
                role="assistant",
                content="Mình có thể gợi ý một phiên bản phù hợp hơn.",
            ),
        ]

    async def loadRecentConversationForScope(self, session_id, *, max_turns=12):
        self.scope_history_calls += 1
        return self.scope_history


@dataclass
class FakeStore:
    turns: list[tuple[Any, ...]] = field(default_factory=list)

    async def appendTurn(self, *args):
        self.turns.append(args)


@dataclass
class FakeGateway:
    tokens: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    public_traces: list[dict[str, Any]] = field(default_factory=list)
    debug_events: list[dict[str, Any]] = field(default_factory=list)
    action_states: list[dict[str, Any]] = field(default_factory=list)
    done: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    debug_trace_enabled: bool = False

    async def send_token(self, token):
        self.tokens.append(token)

    async def send_status(self, status):
        self.statuses.append(status)

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


class QuotaExhaustedLLM:
    async def chat(self, messages, tools, *args, **kwargs):
        from services.agent.llm_client import LLMUnavailableError

        raise LLMUnavailableError(
            "quota exhausted",
            status_code=402,
            reason_code="QUOTA_EXHAUSTED",
        )


def _named_tool_schemas(*names: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": name, "description": name, "parameters": {}},
        }
        for name in names
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["1 + 1 bằng mấy?", "Thời tiết hôm nay thế nào?", "Viết code Python"],
)
async def test_scope_guard_blocks_off_topic_before_memory_tools_and_llm(text: str):
    llm = ScriptedLLM([])
    dispatcher = FakeDispatcher()
    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(
        llm,
        FailingTools(),
        FailingMemory(),
        store,
        dispatcher,
        gateway,
        scope_guard=ScopeGuard(),
    )

    await orchestrator.handleChatMessage("scope-block", text)

    assert llm.calls == 0
    assert dispatcher.calls == []
    assert gateway.statuses == []
    assert len(gateway.done) == 1
    assert "hỗ trợ" in gateway.done[0][0]
    assert [turn[1] for turn in store.turns] == ["user", "assistant"]
    assert [turn[4] for turn in store.turns] == ["scope_guard", "scope_guard"]


@pytest.mark.asyncio
async def test_scope_guard_answers_smalltalk_without_llm():
    llm = ScriptedLLM([])
    gateway = FakeGateway()
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FailingMemory(),
        FakeStore(),
        FakeDispatcher(),
        gateway,
        scope_guard=ScopeGuard(),
    )

    await orchestrator.handleChatMessage("scope-hello", "Chào bạn")

    assert llm.calls == 0
    assert "ăn uống" in gateway.done[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["Tối nay ăn gì?", "Tôi muốn giảm 2 kí treong 2 th tôi"],
)
async def test_scope_guard_forwards_application_question_to_existing_pipeline(text: str):
    llm = ScriptedLLM(
        [LLMResponse(content_stream=_stream(["Mình kiểm tra nhé."]))]
    )
    gateway = FakeGateway()
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        FakeStore(),
        FakeDispatcher(),
        gateway,
        scope_guard=ScopeGuard(),
    )

    await orchestrator.handleChatMessage("scope-pass", text)

    assert llm.calls == 1
    assert gateway.done[0][0] == "Mình kiểm tra nhé."


@pytest.mark.asyncio
async def test_scope_guard_resolves_ambiguous_ellipse_from_safe_session_context():
    llm = ScriptedLLM(
        [LLMResponse(content_stream=_stream(["Bạn có thể chọn burger gà."]))]
    )
    memory = ContextualContinuationMemory()
    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        memory,
        store,
        FakeDispatcher(),
        gateway,
        scope_guard=ScopeGuard(),
    )

    await orchestrator.handleChatMessage("scope-context", "gợi ý đi")

    assert memory.scope_history_calls == 1
    assert llm.calls == 1
    assert gateway.done[0][0] == "Bạn có thể chọn burger gà."
    assert [turn[1] for turn in store.turns] == ["user", "assistant"]
    assert all(turn[4] is None for turn in store.turns)


@pytest.mark.asyncio
async def test_scope_guard_fails_closed_when_ellipse_has_no_safe_session_anchor():
    llm = ScriptedLLM([])
    memory = ContextualContinuationMemory(history=[])
    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        memory,
        store,
        FakeDispatcher(),
        gateway,
        scope_guard=ScopeGuard(),
    )

    await orchestrator.handleChatMessage("scope-no-context", "gợi ý đi")

    assert memory.scope_history_calls == 1
    assert llm.calls == 0
    assert "nói rõ hơn" in gateway.done[0][0]
    assert [turn[4] for turn in store.turns] == ["scope_guard", "scope_guard"]


@pytest.mark.asyncio
async def test_scope_guard_mixed_request_only_forwards_health_fragment():
    llm = CapturingLLM(
        [LLMResponse(content_stream=_stream(["Bạn nên tính protein theo mục tiêu cá nhân."]))]
    )
    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        store,
        FakeDispatcher(),
        gateway,
        scope_guard=ScopeGuard(),
    )

    original = "Hôm nay tôi nên ăn bao nhiêu protein, tiện thể viết code C++ cho tôi"
    await orchestrator.handleChatMessage("scope-mixed", original)

    assert llm.calls == 1
    assert llm.last_messages[-1]["content"] == "Hôm nay tôi nên ăn bao nhiêu protein"
    assert all("C++" not in message.get("content", "") for message in llm.last_messages)
    assert "lập trình" in gateway.done[0][0]
    assert store.turns[0][2] == original
    assert store.turns[0][4] == "scope_guard_mixed"


def test_clear_domain_turns_receive_only_relevant_tool_families():
    schemas = _named_tool_schemas(
        "get_user_profile",
        "suggest_dish",
        "search_dish_catalog",
        "search_recipe_web",
        "suggest_workout",
        "search_exercise_catalog",
        "get_lifestyle_logs",
        "build_nutrition_plan",
        "build_workout_schedule",
    )

    nutrition = _select_relevant_tool_schemas(
        schemas, "Lập thực đơn món Việt trong một tuần"
    )
    nutrition_names = {_tool["function"]["name"] for _tool in nutrition}
    assert nutrition_names == {"get_user_profile", "build_nutrition_plan"}
    assert "suggest_workout" not in nutrition_names
    assert "build_workout_schedule" not in nutrition_names

    fitness = _select_relevant_tool_schemas(schemas, "Gợi ý bài tập tay 30 phút")
    fitness_names = {_tool["function"]["name"] for _tool in fitness}
    assert {"suggest_workout", "search_exercise_catalog"} <= fitness_names
    assert "suggest_dish" not in fitness_names


def test_ambiguous_turn_fails_open_to_full_tool_catalog():
    schemas = _named_tool_schemas("suggest_dish", "suggest_workout")

    selected = _select_relevant_tool_schemas(
        schemas, "Phân tích giúp mình kỹ hơn"
    )

    assert selected == schemas


def test_high_confidence_actions_receive_minimal_tool_sets():
    names = (
        "get_user_profile", "get_today_meals", "get_meal_log_range", "log_meal",
        "update_nutrition_profile", "suggest_dish", "search_dish_catalog",
        "search_recipe_web", "search_food_nutrition", "get_today_exercises",
        "get_exercise_log_range",
        "log_exercise", "log_weight", "get_weight_history", "suggest_workout",
        "search_exercise_catalog", "build_personalized_workout",
        "get_workout_substitutions", "update_workout_profile",
        "get_lifestyle_logs", "log_lifestyle", "set_lifestyle_reminder",
        "navigate_to_screen", "calculate_tdee", "build_nutrition_plan",
        "build_workout_schedule", "get_plan", "get_active_plan_v2", "revise_plan",
        "save_plan", "set_plan_status", "query_rag", "search_medical_knowledge",
    )
    schemas = _named_tool_schemas(*names)

    def selected(text: str) -> set[str]:
        return {
            schema["function"]["name"]
            for schema in _select_relevant_tool_schemas(schemas, text)
        }

    assert selected("mở trang dinh dưỡng") == {"navigate_to_screen"}
    assert selected("nhắc tôi tập lúc 19:00") == {"set_lifestyle_reminder"}
    assert selected("tôi nặng 68kg") == {"log_weight"}
    assert selected("mình vừa uống 500ml") == {"log_lifestyle"}
    assert selected("tôi dị ứng tôm") == {"update_nutrition_profile"}
    assert selected("sáng nay chạy 30 phút") == {
        "log_exercise", "search_exercise_catalog",
    }
    assert selected("lập kế hoạch giảm cân 7 ngày") == {
        "get_user_profile", "build_nutrition_plan",
    }
    assert "search_recipe_web" not in selected("tối nay ăn gì")

    assert selected("Limber 11 thực hiện thế nào?") == {
        "search_food_nutrition", "search_dish_catalog", "search_recipe_web",
        "search_exercise_catalog",
    }


def test_multi_intent_request_keeps_every_required_action_tool():
    schemas = _named_tool_schemas(
        "navigate_to_screen", "set_lifestyle_reminder", "suggest_workout",
        "log_exercise",
    )

    selected = {
        schema["function"]["name"]
        for schema in _select_relevant_tool_schemas(
            schemas, "mở trang tập và nhắc tôi tập lúc 19:00"
        )
    }

    assert selected == {"navigate_to_screen", "set_lifestyle_reminder"}


def test_readback_and_analysis_routes_exclude_writes_and_recommendations():
    names = (
        "get_user_profile", "get_today_meals", "get_meal_log_range", "log_meal",
        "suggest_dish", "search_dish_catalog", "get_today_exercises",
        "get_exercise_log_range", "log_exercise", "log_weight",
        "get_weight_history", "suggest_workout", "get_lifestyle_logs",
        "log_lifestyle", "calculate_tdee", "query_rag", "search_medical_knowledge",
    )
    schemas = _named_tool_schemas(*names)

    meal_readback = {
        schema["function"]["name"]
        for schema in _select_relevant_tool_schemas(
            schemas, "hôm nay tôi đã ăn gì"
        )
    }
    assert meal_readback == {
        "get_user_profile", "get_today_meals", "get_meal_log_range",
    }

    weight_analysis = {
        schema["function"]["name"]
        for schema in _select_relevant_tool_schemas(
            schemas, "phân tích vì sao cân không giảm"
        )
    }
    assert weight_analysis == {
        "get_user_profile", "get_meal_log_range", "get_exercise_log_range",
        "get_weight_history", "get_lifestyle_logs", "calculate_tdee",
    }
    assert not {"log_meal", "log_exercise", "log_weight", "log_lifestyle"} & weight_analysis


def test_medical_request_gets_evidence_tools_without_write_tools():
    schemas = _named_tool_schemas(
        "get_user_profile", "query_rag", "search_medical_knowledge",
        "log_meal", "log_exercise", "log_lifestyle",
    )

    selected = {
        schema["function"]["name"]
        for schema in _select_relevant_tool_schemas(
            schemas, "tôi đau ngực và khó thở"
        )
    }

    assert selected == {
        "get_user_profile", "query_rag", "search_medical_knowledge",
    }


@pytest.mark.asyncio
async def test_dispatch_all_parallelizes_reads_but_serializes_writes():
    class TimingDispatcher:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.events: list[str] = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.events.append(f"start:{call.id}")
            await asyncio.sleep(0.01)
            self.events.append(f"end:{call.id}")
            self.active -= 1
            return ToolResult(ok=True, data={"call_id": call.id})

    dispatcher = TimingDispatcher()
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), dispatcher, None
    )
    calls = [
        ToolCall(id="read-a", name="get_today_meals", arguments={}),
        ToolCall(id="read-b", name="get_today_exercises", arguments={}),
        ToolCall(
            id="write-a", name="log_meal", arguments={"request_id": "write-a"}
        ),
        ToolCall(
            id="write-b", name="log_exercise", arguments={"request_id": "write-b"}
        ),
        ToolCall(id="read-c", name="get_lifestyle_logs", arguments={}),
    ]

    results = await orchestrator._dispatch_all("dispatch-order", calls, {})

    assert [call.id for call, _ in results] == [call.id for call in calls]
    assert dispatcher.max_active == 2
    events = dispatcher.events
    assert events.index("start:write-a") > events.index("end:read-a")
    assert events.index("start:write-a") > events.index("end:read-b")
    assert events.index("start:write-b") > events.index("end:write-a")
    assert events.index("start:read-c") > events.index("end:write-b")


@pytest.mark.asyncio
async def test_dispatch_all_coalesces_duplicate_reads_but_not_dish_suggestions():
    class CountingDispatcher:
        def __init__(self):
            self.calls: list[str] = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call.id)
            await asyncio.sleep(0)
            return ToolResult(ok=True, data={"source_call_id": call.id})

    dispatcher = CountingDispatcher()
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), dispatcher, None
    )
    calls = [
        ToolCall(id="meal-a", name="get_today_meals", arguments={}),
        ToolCall(id="meal-b", name="get_today_meals", arguments={}),
        ToolCall(
            id="dish-a", name="suggest_dish", arguments={"meal_type": "dinner"}
        ),
        ToolCall(
            id="dish-b", name="suggest_dish", arguments={"meal_type": "dinner"}
        ),
    ]

    results = await orchestrator._dispatch_all("dispatch-dedup", calls, {})

    assert [call.id for call, _ in results] == [call.id for call in calls]
    assert dispatcher.calls.count("meal-a") == 1
    assert "meal-b" not in dispatcher.calls
    assert {"dish-a", "dish-b"} <= set(dispatcher.calls)


def test_generic_meal_request_removes_model_invented_dish_query():
    call = ToolCall(
        id="dish-generic",
        name="suggest_dish",
        arguments={"meal_type": "lunch", "target_kcal": 800, "query": "gà"},
    )

    changes = _ground_suggest_dish_queries(
        [call],
        user_text="Gợi ý bữa ăn phù hợp với tôi",
        explicit_dish_query=None,
    )

    assert "query" not in call.arguments
    assert changes == [{"action": "REMOVED", "query": "gà"}]


def test_current_user_dish_request_keeps_literal_query():
    call = ToolCall(
        id="dish-current",
        name="suggest_dish",
        arguments={"meal_type": "dinner", "target_kcal": 650, "query": "gà"},
    )

    changes = _ground_suggest_dish_queries(
        [call],
        user_text="Tối nay tôi muốn ăn gà",
        explicit_dish_query="gà",
    )

    assert call.arguments["query"] == "gà"
    assert changes == []


def test_explicit_current_dish_replaces_stale_model_query():
    call = ToolCall(
        id="dish-stale",
        name="suggest_dish",
        arguments={"meal_type": "dinner", "target_kcal": 650, "query": "gà"},
    )

    changes = _ground_suggest_dish_queries(
        [call],
        user_text="Tôi muốn ăn phở bò",
        explicit_dish_query="phở bò",
    )

    assert call.arguments["query"] == "phở bò"
    assert changes == [{"action": "REPLACED", "query": "phở bò"}]


def test_avoidance_language_never_becomes_a_positive_dish_query():
    call = ToolCall(
        id="dish-avoid",
        name="suggest_dish",
        arguments={"meal_type": "lunch", "target_kcal": 700, "query": "gà"},
    )

    _ground_suggest_dish_queries(
        [call],
        user_text="Gợi ý món không có gà",
        explicit_dish_query=None,
    )

    assert "query" not in call.arguments


@pytest.mark.asyncio
async def test_generic_meal_query_guard_runs_before_tool_dispatch():
    dispatcher = FakeDispatcher()
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="dish-guarded",
                        name="suggest_dish",
                        arguments={
                            "meal_type": "lunch",
                            "target_kcal": 800,
                            "query": "gà",
                        },
                    )
                ]
            ),
            LLMResponse(content_stream=_stream(["Đã chọn món phù hợp."])),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        FakeStore(),
        dispatcher,
        FakeGateway(),
        max_steps=3,
    )

    await orchestrator.handleChatMessage(
        "session-query-guard", "Gợi ý bữa ăn phù hợp với tôi"
    )

    dispatched = dispatcher.calls[0][1]
    assert dispatched.name == "suggest_dish"
    assert "query" not in dispatched.arguments


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


def test_historical_tool_payloads_are_not_replayed_as_orphan_messages():
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), None
    )
    context = Context(
        history=[
            ChatTurn(role="assistant", content="Mình đã kiểm tra."),
            ChatTurn(
                role="tool",
                content='{"private_raw_payload": true}',
                tool_call_id="old-call",
                tool_name="get_user_profile",
            ),
            ChatTurn(role="user", content="Cảm ơn"),
        ]
    )

    messages = orchestrator._build_messages(context, "Tiếp tục")

    assert [message["role"] for message in messages] == [
        "system",
        "assistant",
        "user",
        "user",
    ]
    assert "private_raw_payload" not in json.dumps(messages)


def test_history_limit_counts_only_model_visible_conversation_turns():
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), None
    )
    context = Context(
        history=[
            ChatTurn(role="user", content="Tôi muốn ăn burger"),
            ChatTurn(role="assistant", content="Mình sẽ tìm burger phù hợp."),
            ChatTurn(role="tool", content='{"results": [1]}', tool_name="search_dish_catalog"),
            ChatTurn(role="tool", content='{"results": [2]}', tool_name="search_recipe_web"),
            ChatTurn(role="assistant", content="Bạn có thể chọn burger gà."),
        ]
    )

    messages = orchestrator._build_messages(
        context,
        "Cái nào cũng được",
        history_turn_limit=2,
    )

    assert messages[-3:] == [
        {"role": "assistant", "content": "Mình sẽ tìm burger phù hợp."},
        {"role": "assistant", "content": "Bạn có thể chọn burger gà."},
        {"role": "user", "content": "Cái nào cũng được"},
    ]


def test_zero_history_limit_replays_no_prior_turns():
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]), FakeTools(), FakeMemory(), FakeStore(), FakeDispatcher(), None
    )
    context = Context(history=[ChatTurn(role="user", content="Tin nhắn cũ")])

    messages = orchestrator._build_messages(
        context,
        "Tin nhắn mới",
        history_turn_limit=0,
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[-1]["content"] == "Tin nhắn mới"


def test_scope_guard_history_is_not_replayed_to_the_llm():
    orchestrator = AgentOrchestrator(
        ScriptedLLM([]),
        FakeTools(),
        FakeMemory(),
        FakeStore(),
        FakeDispatcher(),
        None,
        scope_guard=ScopeGuard(),
    )
    context = Context(
        history=[
            ChatTurn(
                role="user",
                content="Viết code Python",
                tool_name="scope_guard",
            ),
            ChatTurn(
                role="assistant",
                content="Mình chỉ hỗ trợ sức khỏe.",
                tool_name="scope_guard",
            ),
            ChatTurn(role="user", content="Tối nay ăn gì?"),
        ]
    )

    messages = orchestrator._build_messages(context, "Gợi ý món khác")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "Viết code Python" not in rendered
    assert "Mình chỉ hỗ trợ sức khỏe" not in rendered
    assert "Tối nay ăn gì?" in rendered


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
async def test_structured_plan_result_skips_the_second_llm_completion():
    class StructuredPlanDispatcher:
        async def dispatch(self, session_id, call, timeout_ms):
            return ToolResult(
                ok=True,
                data={
                    "presentation": {
                        "type": "versioned_plan",
                        "text": "Đây là bản nháp kế hoạch 7 ngày.",
                    }
                },
            )

    gateway = FakeGateway()
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="plan-1",
                        name="build_nutrition_plan",
                        arguments={},
                    )
                ]
            )
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        FakeStore(),
        StructuredPlanDispatcher(),
        gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("cost-plan", "Lập thực đơn 7 ngày")

    assert llm.calls == 1
    assert gateway.done[-1][0] == "Đây là bản nháp kế hoạch 7 ngày."
    assert gateway.done[-1][1]["type"] == "versioned_plan"


@pytest.mark.asyncio
async def test_tool_call_preamble_is_not_streamed_or_saved_as_a_chat_bubble():
    gateway = FakeGateway()
    store = FakeStore()
    call = ToolCall(id="c-preamble", name="get_today_meals", arguments={})
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[call],
                content_stream=_stream(["Để mình kiểm tra nhé..."]),
                full_text="Để mình kiểm tra nhé...",
            ),
            LLMResponse(
                content_stream=_stream(["Hôm nay bạn chưa ghi bữa ăn nào."]),
                full_text="Hôm nay bạn chưa ghi bữa ăn nào.",
            ),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        store,
        FakeDispatcher(),
        gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s-natural", "Hôm nay tôi đã ăn gì?")

    assert gateway.tokens == ["Hôm nay bạn chưa ghi bữa ăn nào."]
    assistant_turns = [turn[2] for turn in store.turns if turn[1] == "assistant"]
    assert assistant_turns == ["Hôm nay bạn chưa ghi bữa ăn nào."]


def test_successful_tool_result_includes_natural_answer_contract():
    serialized = AgentOrchestrator._serialize_result(
        ToolCall(id="dish-search", name="search_dish_catalog", arguments={}),
        ToolResult(ok=True, data={"scanned_count": 300, "matched_count": 1}),
    )

    payload = json.loads(serialized)
    guidance = payload["huong_dan_tra_loi"]
    assert "tiếng Việt tự nhiên" in guidance
    assert "không nhắc tên tool" in guidance
    assert "toàn bộ dữ liệu món ăn" in guidance
    assert "không dùng từ 'catalog'" in guidance
    assert "Tôn trọng lựa chọn của người dùng" in guidance
    assert "không phán xét" in guidance


@pytest.mark.asyncio
async def test_progress_statuses_are_short_and_user_facing():
    gateway = FakeGateway()
    llm = ScriptedLLM(
        [LLMResponse(content_stream=_stream(["Mình đây."]), full_text="Mình đây.")]
    )
    orchestrator = AgentOrchestrator(
        llm,
        FakeTools(),
        FakeMemory(),
        FakeStore(),
        FakeDispatcher(),
        gateway,
    )

    await orchestrator.handleChatMessage("status-natural", "Bạn còn ở đó không?")

    assert gateway.statuses == [
        "Đang xem thông tin liên quan…",
        "Đang chuẩn bị câu trả lời…",
    ]
    rendered = " ".join(gateway.statuses).casefold()
    for internal_word in ("ngữ cảnh", "lập kế hoạch", "bước 2", "công cụ", "tool"):
        assert internal_word not in rendered


@pytest.mark.parametrize(
    ("tool_name", "expected_guidance"),
    [
        ("suggest_dish", "không âm thầm đổi món"),
        ("suggest_workout", "không mô tả buổi tập như hình phạt"),
        ("get_lifestyle_logs", "không chẩn đoán hoặc phán xét"),
        ("log_meal", "không đề nghị tập để bù calo"),
        ("log_weight", "không phán xét con số cân nặng"),
        ("get_active_plan_v2", "không phải bằng chứng người dùng đã ăn hoặc đã tập"),
        ("build_workout_schedule", "chưa phải buổi tập đã thực hiện"),
    ],
)
def test_tool_result_guidance_preserves_agency_and_state_boundaries(
    tool_name: str, expected_guidance: str
):
    serialized = AgentOrchestrator._serialize_result(
        ToolCall(id=f"call-{tool_name}", name=tool_name, arguments={}),
        ToolResult(ok=True, data={}),
    )

    guidance = json.loads(serialized)["huong_dan_tra_loi"]
    assert expected_guidance.casefold() in guidance.casefold()
    assert "gợi ý, dự kiến, đã thực hiện và đã lưu" in guidance


@pytest.mark.parametrize("error_code", ["TIMEOUT", "WRITE_REJECTED", "PERSISTENCE_ERROR"])
def test_tool_error_guidance_is_user_friendly_and_state_honest(error_code: str):
    serialized = AgentOrchestrator._serialize_result(
        ToolCall(id="failed-call", name="log_lifestyle", arguments={}),
        ToolResult(ok=False, error=error_code, data={}),
    )

    guidance = json.loads(serialized)["huong_dan"]
    assert "nói đúng phần chưa làm được" in guidance
    assert "dữ liệu cũ chưa bị thay đổi" in guidance
    assert "Không đổ lỗi cho người dùng" in guidance
    assert "không nhắc tên tool" in guidance


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
    assert "Bạn có xác nhận đã ăn **Cơm gà A**" in gateway.done[0][0]
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
    reads as a crash. It now returns a deterministic message without exceeding
    the paid-call budget.
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

    # The paid-call budget is a hard ceiling; no hidden third completion.
    assert llm.calls == 2
    assert gateway.errors == []
    assert "chưa lấy đủ thông tin" in gateway.done[0][0]


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
    assert gateway.done[0][0] == (
        "Mình chưa lấy đủ thông tin để trả lời chính xác. "
        "Bạn gửi lại yêu cầu này giúp mình nhé."
    )


@pytest.mark.asyncio
async def test_llm_unavailable_sends_error_and_does_not_append_assistant_turn():
    from services.agent.llm_client import LLMUnavailableError

    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(UnavailableLLM(), FakeTools(), FakeMemory(), store, FakeDispatcher(), gateway, max_steps=2)

    with pytest.raises(LLMUnavailableError):
        await orchestrator.handleChatMessage("s1", "hi")

    assert gateway.errors[0][0] == "LLM_UNAVAILABLE"
    assert "máy chủ AI" not in gateway.errors[0][1]
    assert not any(t[1] == "assistant" for t in store.turns)


@pytest.mark.asyncio
async def test_llm_quota_exhausted_sends_actionable_error_code():
    from services.agent.llm_client import LLMUnavailableError

    gateway = FakeGateway()
    store = FakeStore()
    orchestrator = AgentOrchestrator(
        QuotaExhaustedLLM(),
        FakeTools(),
        FakeMemory(),
        store,
        FakeDispatcher(),
        gateway,
        max_steps=2,
    )

    with pytest.raises(LLMUnavailableError):
        await orchestrator.handleChatMessage("s1", "hi")

    assert gateway.errors[0][0] == "LLM_QUOTA_EXHAUSTED"
    assert "quota" not in gateway.errors[0][1].casefold()
    assert "API key" not in gateway.errors[0][1]
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


@pytest.mark.asyncio
async def test_explicit_named_dish_enforces_catalog_then_web_when_model_skips_tools():
    class ToolsWithRecipeFallback(FakeTools):
        def schemas(self):
            return _named_tool_schemas(
                "search_dish_catalog",
                "search_recipe_web",
                "get_today_meals",
            )

        def get(self, name):
            return (
                object()
                if name in {"search_dish_catalog", "search_recipe_web"}
                else None
            )

    class Dispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "search_dish_catalog":
                return ToolResult(
                    ok=True,
                    data={"scanned_count": 300, "matched_count": 0, "results": []},
                )
            assert call.name == "search_recipe_web"
            return ToolResult(
                ok=True,
                data={
                    "status": "REFERENCE_ONLY_RESULTS",
                    "recipes": [
                        {
                            "title": "Cassava pizza",
                            "source": "THEMEALDB_OFFICIAL_API",
                            "source_url": "https://www.themealdb.com/api/json/v1/1/lookup.php?i=53044",
                            "verification_status": "REFERENCE_ONLY",
                            "ingredients": [
                                {"source_text": "1 cassava pizza base"},
                                {"source_text": "tomato sauce"},
                            ],
                        }
                    ],
                    "requested_query": "pizza",
                    "purpose": "catalog_miss",
                    "canonical_write_authorized": False,
                    "meal_logging_authorized": False,
                },
            )

    gateway = FakeGateway()
    dispatcher = Dispatcher()
    llm = RecordingLLM(
        [
            LLMResponse(
                content_stream=_stream(["Catalog không có pizza."]),
                full_text="Catalog không có pizza.",
            ),
            LLMResponse(
                content_stream=_stream(["Mình tìm được một công thức tham khảo."]),
                full_text="Mình tìm được một công thức tham khảo.",
            ),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        ToolsWithRecipeFallback(),
        FakeMemory(),
        FakeStore(),
        dispatcher,
        gateway,
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s-pizza", "Tôi muốn ăn pizza")

    assert [call.name for call in dispatcher.calls] == [
        "search_dish_catalog",
        "search_recipe_web",
    ]
    assert dispatcher.calls[0].arguments["query"] == "pizza"
    assert dispatcher.calls[1].arguments == {"query": "pizza"}
    reply = gateway.done[-1][0]
    assert gateway.tokens == [reply]
    assert "Cassava pizza" in reply
    assert "TheMealDB (www.themealdb.com)" in reply
    assert "độ phù hợp với dị ứng hoặc chế độ ăn" in reply
    assert "- 1 đế pizza cassava" in reply
    assert "- sốt cà chua" in reply
    assert "Catalog" not in reply
    assert "canonical" not in reply
    assert "](" not in reply
    assert "150 kcal" not in reply
    assert len(llm.seen_messages) == 1
    assert [
        step["public_event_type"]
        for step in gateway.done[-1][2]["steps"]
    ] == ["FOOD_CATALOG_SEARCHED", "EXTERNAL_RECIPE_SEARCHED"]


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


@pytest.mark.asyncio
async def test_local_dish_miss_dispatches_web_recipe_fallback_without_model_choice():
    class ToolsWithRecipeFallback(FakeTools):
        def get(self, name):
            return (
                object()
                if name in {"search_dish_catalog", "search_recipe_web"}
                else None
            )

    class LocalMissDispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "suggest_dish":
                return ToolResult(ok=False, error="NO_DISH_FOUND")
            if call.name == "search_dish_catalog":
                return ToolResult(
                    ok=True,
                    data={
                        "scanned_count": 300,
                        "matched_count": 0,
                        "results": [],
                    },
                )
            assert call.name == "search_recipe_web"
            return ToolResult(
                ok=True,
                data={
                    "status": "REFERENCE_ONLY_RESULTS",
                    "recipes": [{"title": "Steak Diane"}],
                    "meal_logging_authorized": False,
                },
            )

    dispatcher = LocalMissDispatcher()
    llm = RecordingLLM([
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="dish-miss",
                    name="suggest_dish",
                    arguments={
                        "query": "beefsteak",
                        "meal_type": "dinner",
                        "target_kcal": 650,
                    },
                )
            ]
        ),
        LLMResponse(
            content_stream=_stream(["Mình đã tìm được công thức." ]),
            full_text="Mình đã tìm được công thức.",
        ),
    ])
    orchestrator = AgentOrchestrator(
        llm,
        ToolsWithRecipeFallback(),
        FakeMemory(),
        FakeStore(),
        dispatcher,
        FakeGateway(),
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s-beefsteak", "Tìm món beefsteak")

    assert [call.name for call in dispatcher.calls] == [
        "suggest_dish",
        "search_dish_catalog",
        "search_recipe_web",
    ]
    assert dispatcher.calls[1].arguments == {
        "query": "beefsteak",
        "page": 1,
        "page_size": 5,
        "include_details": True,
    }
    assert dispatcher.calls[2].arguments == {
        "query": "beefsteak",
        "meal_type": "dinner",
        "target_kcal": 650,
    }
    replay = llm.seen_messages[1]
    assistant_calls = next(
        message["tool_calls"]
        for message in replay
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert [item["function"]["name"] for item in assistant_calls] == [
        "suggest_dish",
        "search_dish_catalog",
        "search_recipe_web",
    ]
    tool_call_ids = [
        message["tool_call_id"] for message in replay if message.get("role") == "tool"
    ]
    assert tool_call_ids == [
        "dish-miss",
        "dish-miss-dish-catalog-fallback",
        "dish-miss-recipe-web-fallback",
    ]


@pytest.mark.asyncio
async def test_local_catalog_match_prevents_unnecessary_recipe_web_fallback():
    class ToolsWithRecipeFallback(FakeTools):
        def get(self, name):
            return (
                object()
                if name in {"search_dish_catalog", "search_recipe_web"}
                else None
            )

    class ExistingDishDispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "suggest_dish":
                return ToolResult(ok=False, error="NO_DISH_FOUND")
            assert call.name == "search_dish_catalog"
            return ToolResult(
                ok=True,
                data={
                    "scanned_count": 300,
                    "matched_count": 1,
                    "results": [{"dish_id": 42, "name": "Beefsteak"}],
                },
            )

    dispatcher = ExistingDishDispatcher()
    llm = RecordingLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="dish-filtered",
                        name="suggest_dish",
                        arguments={
                            "query": "beefsteak",
                            "meal_type": "dinner",
                            "target_kcal": 200,
                        },
                    )
                ]
            ),
            LLMResponse(
                content_stream=_stream(["Món có trong dữ liệu nhưng không khớp bộ lọc."]),
                full_text="Món có trong dữ liệu nhưng không khớp bộ lọc.",
            ),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        ToolsWithRecipeFallback(),
        FakeMemory(),
        FakeStore(),
        dispatcher,
        FakeGateway(),
        max_steps=3,
    )

    await orchestrator.handleChatMessage("s-filtered", "Tìm món beefsteak")

    assert [call.name for call in dispatcher.calls] == [
        "suggest_dish",
        "search_dish_catalog",
    ]


@pytest.mark.asyncio
async def test_early_recipe_web_call_is_replaced_by_catalog_first_lookup():
    class ToolsWithRecipeFallback(FakeTools):
        def get(self, name):
            return (
                object()
                if name in {"search_dish_catalog", "search_recipe_web"}
                else None
            )

    class Dispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "search_dish_catalog":
                return ToolResult(
                    ok=True,
                    data={"scanned_count": 300, "matched_count": 0, "results": []},
                )
            assert call.name == "search_recipe_web"
            return ToolResult(
                ok=True,
                data={
                    "status": "REFERENCE_ONLY_RESULTS",
                    "requested_query": "cassava pizza",
                    "recipes": [
                        {
                            "title": "Cassava pizza",
                            "source": "THEMEALDB_OFFICIAL_API",
                            "source_url": "https://www.themealdb.com/meal/1",
                            "verification_status": "REFERENCE_ONLY",
                            "ingredients": [{"source_text": "cassava base"}],
                        }
                    ],
                    "canonical_write_authorized": False,
                    "meal_logging_authorized": False,
                },
            )

    dispatcher = Dispatcher()
    llm = RecordingLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="web-too-early",
                        name="search_recipe_web",
                        arguments={"query": "cassava pizza"},
                    )
                ]
            )
        ]
    )
    orchestrator = AgentOrchestrator(
        llm,
        ToolsWithRecipeFallback(),
        FakeMemory(),
        FakeStore(),
        dispatcher,
        FakeGateway(),
        max_steps=3,
    )

    await orchestrator.handleChatMessage(
        "s-web-order", "Cassava pizza có trong ứng dụng không?"
    )

    assert [call.name for call in dispatcher.calls] == [
        "search_dish_catalog",
        "search_recipe_web",
    ]
    assert dispatcher.calls[0].arguments["query"] == "cassava pizza"


@pytest.mark.asyncio
async def test_direct_catalog_miss_dispatches_recipe_web_fallback():
    class ToolsWithRecipeFallback(FakeTools):
        def get(self, name):
            return object() if name == "search_recipe_web" else None

    class Dispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "search_dish_catalog":
                return ToolResult(
                    ok=True,
                    data={"scanned_count": 300, "matched_count": 0, "results": []},
                )
            assert call.name == "search_recipe_web"
            return ToolResult(
                ok=True,
                data={"status": "REFERENCE_ONLY_RESULTS", "recipes": []},
            )

    dispatcher = Dispatcher()
    llm = RecordingLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="catalog-pizza",
                        name="search_dish_catalog",
                        arguments={"query": "pizza", "include_details": True},
                    )
                ]
            ),
            LLMResponse(content_stream=_stream(["Không có trong catalog."])),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm, ToolsWithRecipeFallback(), FakeMemory(), FakeStore(), dispatcher,
        FakeGateway(), max_steps=3,
    )

    await orchestrator.handleChatMessage(
        "s-pizza-catalog", "Pizza có trong ứng dụng không? Cho tôi cách làm."
    )

    assert [call.name for call in dispatcher.calls] == [
        "search_dish_catalog",
        "search_recipe_web",
    ]
    assert dispatcher.calls[1].arguments == {"query": "pizza"}


@pytest.mark.asyncio
async def test_local_dish_without_steps_fetches_reference_instructions_only():
    class ToolsWithRecipeFallback(FakeTools):
        def get(self, name):
            return object() if name == "search_recipe_web" else None

    class Dispatcher:
        def __init__(self):
            self.calls = []

        async def dispatch(self, session_id, call, timeout_ms):
            self.calls.append(call)
            if call.name == "search_dish_catalog":
                return ToolResult(
                    ok=True,
                    data={
                        "scanned_count": 300,
                        "matched_count": 1,
                        "results": [
                            {
                                "dish_id": 7,
                                "name": "Phở bò",
                                "instructions": [],
                                "instruction_status": "UNAVAILABLE_IN_CANONICAL_CATALOG",
                            }
                        ],
                    },
                )
            assert call.name == "search_recipe_web"
            return ToolResult(
                ok=True,
                data={
                    "status": "REFERENCE_ONLY_RESULTS",
                    "purpose": "instructions_only",
                    "recipes": [{"title": "Beef pho", "instructions": ["step"]}],
                },
            )

    dispatcher = Dispatcher()
    llm = RecordingLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="catalog-pho",
                        name="search_dish_catalog",
                        arguments={"query": "phở bò", "include_details": True},
                    )
                ]
            ),
            LLMResponse(content_stream=_stream(["Đây là cách làm tham khảo."])),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm, ToolsWithRecipeFallback(), FakeMemory(), FakeStore(), dispatcher,
        FakeGateway(), max_steps=3,
    )

    await orchestrator.handleChatMessage(
        "s-pho-instructions", "Cho tôi nguyên liệu và cách làm phở bò."
    )

    assert [call.name for call in dispatcher.calls] == [
        "search_dish_catalog",
        "search_recipe_web",
    ]
    assert dispatcher.calls[1].arguments == {
        "query": "phở bò",
        "purpose": "instructions_only",
    }


@pytest.mark.asyncio
async def test_direct_exercise_catalog_lookup_returns_exact_source_without_second_llm_pass():
    class Dispatcher:
        async def dispatch(self, session_id, call, timeout_ms):
            return ToolResult(
                ok=True,
                data={
                    "scanned_count": 885,
                    "matched_count": 1,
                    "results": [
                        {
                            "name": "Limber 11",
                            "source": "WGER",
                            "review_status": "SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED",
                            "quality_flags": ["DIFFICULTY_REVIEW_REQUIRED"],
                            "instructions": {
                                "text": "1. Foam Roll IT Band - 10-15 passes"
                            },
                        }
                    ],
                },
            )

    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="exercise-lookup",
                        name="search_exercise_catalog",
                        arguments={"query": "Limber 11", "include_details": True},
                    )
                ]
            )
        ]
    )
    orchestrator = AgentOrchestrator(
        llm, FakeTools(), FakeMemory(), store, Dispatcher(), gateway, max_steps=3
    )

    await orchestrator.handleChatMessage(
        "s-exact-exercise", "Limber 11 thực hiện thế nào?"
    )

    assert llm.calls == 1
    reply = gateway.done[-1][0]
    assert "1. Foam Roll IT Band - 10-15 passes" in reply
    assert "chưa được duyệt đầy đủ" in reply
    assert "lưu" not in reply.casefold()
    assert "phù hợp" in reply.casefold()  # appears only in the explicit disclaimer


@pytest.mark.asyncio
async def test_plan_collision_and_clarification_preserves_valid_plan_and_llm_answer():
    """When a turn invokes both nutrition and workout planning, and workout requires clarification,
    the valid nutrition plan is preserved, early exit is NOT triggered, and the LLM response is retained.
    """
    class MultiPlanDispatcher:
        async def dispatch(self, session_id, call, timeout_ms):
            if call.name == "build_nutrition_plan":
                return ToolResult(
                    ok=True,
                    data={
                        "status": "READY",
                        "plan": {"plan_id": "nut-1", "domain": "NUTRITION"},
                        "presentation": {
                            "type": "versioned_plan",
                            "domain": "NUTRITION",
                            "text": "Bản kế hoạch nutrition gồm 3 mục.",
                            "days": [
                                {
                                    "date": "2026-09-21",
                                    "items": [{"name": "Burger bò áp chảo"}],
                                }
                            ],
                        },
                    },
                )
            if call.name == "build_workout_schedule":
                return ToolResult(
                    ok=True,
                    data={
                        "status": "CLARIFICATION_REQUIRED",
                        "reason_codes": ["CLARIFICATION_REQUIRED"],
                        "plan": {"plan_id": "work-1", "domain": "WORKOUT"},
                        "presentation": {
                            "type": "versioned_plan",
                            "domain": "WORKOUT",
                            "text": "Bản kế hoạch workout gồm 0 mục.",
                            "days": [],
                        },
                    },
                )
            return ToolResult(ok=False, error="UNKNOWN_TOOL")

    gateway = FakeGateway()
    store = FakeStore()
    llm = ScriptedLLM(
        [
            # Step 1: LLM calls both planning tools
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call-nut",
                        name="build_nutrition_plan",
                        arguments={"period_start": "2026-09-21", "period_end": "2026-09-21", "timezone": "Asia/Ho_Chi_Minh"},
                    ),
                    ToolCall(
                        id="call-work",
                        name="build_workout_schedule",
                        arguments={"period_start": "2026-09-21", "period_end": "2026-09-21", "timezone": "Asia/Ho_Chi_Minh"},
                    ),
                ]
            ),
            # Step 2: LLM answers the user directly about the burger and asks for workout clarification
            LLMResponse(
                content_stream=_stream([
                    "Bạn hoàn toàn có thể ăn một chiếc burger vào ngày mai nếu cân đối lượng calo trong ngày. ",
                    "Mình đã lên kế hoạch ăn uống với món burger bò. ",
                    "Về phần tập luyện, bạn có thể cho mình biết bạn có đang gặp chấn thương nào không?",
                ]),
                full_text=(
                    "Bạn hoàn toàn có thể ăn một chiếc burger vào ngày mai nếu cân đối lượng calo trong ngày. "
                    "Mình đã lên kế hoạch ăn uống với món burger bò. "
                    "Về phần tập luyện, bạn có thể cho mình biết bạn có đang gặp chấn thương nào không?"
                ),
            ),
        ]
    )
    orchestrator = AgentOrchestrator(
        llm, FakeTools(), FakeMemory(), store, MultiPlanDispatcher(), gateway, max_steps=4
    )

    await orchestrator.handleChatMessage(
        "s-burger-plan",
        "Liệu ngày mai tôi có thể ăn burger không? Lên kế hoạch ăn và tập cho ngày mai để mọi thứ oke",
    )

    # 1. The LLM must be called a second time to synthesize the answer
    assert llm.calls == 2

    # 2. The reply must directly answer the burger question
    reply = gateway.done[-1][0]
    assert "ăn một chiếc burger" in reply
    assert "chấn thương" in reply

    # 3. The structured data MUST be the valid nutrition plan with 1 day/items, NOT the 0-item workout plan
    structured = gateway.done[-1][1]
    assert structured is not None
    assert structured.get("type") == "versioned_plan"
    assert structured.get("domain") == "NUTRITION"
    assert len(structured.get("days", [])) == 1
    assert structured["days"][0]["items"][0]["name"] == "Burger bò áp chảo"


def test_detect_safety_pain_response_clears_on_affirmation():
    history = [
        ChatTurn(
            role="assistant",
            content="Tôi cần xác nhận một điều an toàn trước khi tạo buổi tập chân cho bạn: hôm nay bạn có bị đau hoặc khó chịu ở đầu gối, háng hay đùi không?",
        )
    ]
    assert _detect_safety_pain_response("oke", history) == "NO"
    assert _detect_safety_pain_response("không", history) == "NO"
    assert _detect_safety_pain_response("bình thường", history) == "NO"
    assert _detect_safety_pain_response("không đau gì cả", history) == "NO"
    assert _detect_safety_pain_response("có, bị đau gối", history) == "YES"
    assert _detect_safety_pain_response("hôm nay ăn gì", history) is None


