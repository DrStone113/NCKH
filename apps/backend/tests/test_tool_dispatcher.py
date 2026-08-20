from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from services.agent.llm_client import ToolCall
from services.agent.tool_dispatcher import (
    ToolDispatcher,
    ToolResult,
    _normalise_plan_profile,
)
from services.agent.tool_registry import ToolDescriptor, ToolRegistry
from services.agent.tools.plan_tools import CREATE_LONG_TERM_PLAN_DESCRIPTOR


def test_normalise_plan_profile_uses_flutter_context_and_requested_goal():
    profile = _normalise_plan_profile(
        {
            "user_id": "stale-user",
            "age": 30,
            "gender": "male",
            "height": 172,
            "weight": 68,
            "activity_level": "moderate",
            "health_goal": "maintain",
            "dietary_restrictions": "no_seafood",
            "today_meals": [{"name": "ignored"}],
        },
        user_id="real-user",
        goal="gain_muscle",
    )

    assert profile == {
        "user_id": "real-user",
        "age": 30,
        "gender": "male",
        "height_cm": 172,
        "weight_kg": 68,
        "activity_level": "moderate",
        "health_goal": "gain_muscle",
        "dietary_restrictions": ["no_seafood"],
    }


@dataclass
class _FakeResult:
    rows: list[tuple[Any, ...]] = field(default_factory=list)

    def first(self):
        return self.rows[0] if self.rows else None


@dataclass
class _FakeDbSession:
    invocations: list[dict[str, Any]] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None):
        sql = str(statement)
        if "INSERT INTO tool_invocations" in sql:
            self.invocations.append(
                {
                    "session_id": params["session_id"],
                    "correlation_id": params["correlation_id"],
                    "tool_name": params["tool_name"],
                    "arguments": params["arguments"],
                    "result": None,
                    "ok": None,
                    "error_code": None,
                }
            )
            return _FakeResult()
        if "SELECT result, ok, error_code" in sql:
            request_id = params["request_id"]
            tool_name = params["tool_name"]
            session_id = params["session_id"]
            for item in reversed(self.invocations):
                if (
                    item["session_id"] == session_id
                    and item["tool_name"] == tool_name
                    and f'"request_id": "{request_id}"' in item["arguments"]
                    and item["ok"] is True
                ):
                    return _FakeResult(rows=[(item["result"], item["ok"], item["error_code"])])
            return _FakeResult()
        if "UPDATE tool_invocations" in sql:
            for item in self.invocations:
                if item["correlation_id"] == params["correlation_id"]:
                    item["result"] = params["result"]
                    item["ok"] = params["ok"]
                    item["error_code"] = params["error_code"]
                    break
            return _FakeResult()
        return _FakeResult()


class _FakeGateway:
    def __init__(self):
        self.calls: list[tuple[str, str, dict[str, Any], int]] = []

    async def send_tool_call(self, correlation_id: str, name: str, args: dict[str, Any], timeout_ms: int):
        self.calls.append((correlation_id, name, args, timeout_ms))


def _registry_with(descriptor: ToolDescriptor) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(descriptor)
    return registry


def _client_descriptor(idempotent: bool = True) -> ToolDescriptor:
    return ToolDescriptor(
        name="get_user_profile" if idempotent else "log_meal",
        description="test tool",
        parameters_schema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "value": {"type": "string"},
            },
        },
        side="client",
        idempotent=idempotent,
    )


@pytest.mark.asyncio
async def test_client_dispatch_resolves_from_tool_result():
    gateway = _FakeGateway()
    dispatcher = ToolDispatcher(_registry_with(_client_descriptor()), gateway=gateway)
    call = ToolCall(id="corr-1", name="get_user_profile", arguments={"value": "x"})

    task = asyncio.create_task(dispatcher.dispatch("session-1", call, 100))
    await asyncio.sleep(0)
    ui_message = {
        "text": "Đã ghi nhận món ăn",
        "structured": {"type": "structured", "actions": []},
    }
    dispatcher.on_tool_result(
        "corr-1",
        {
            "ok": True,
            "data": {"user_id": "u1"},
            "ui_message": ui_message,
        },
    )
    result = await task

    assert result == ToolResult(
        ok=True,
        data={"user_id": "u1"},
        ui_message=ui_message,
    )
    assert gateway.calls[0][0] == "corr-1"


@pytest.mark.asyncio
async def test_long_term_plan_dispatch_injects_profile_before_validation():
    captured: dict[str, Any] = {}

    async def create_complete_plan(**kwargs):
        captured.update(kwargs)
        return {"days_generated": kwargs["duration_days"]}

    descriptor = ToolDescriptor(
        name=CREATE_LONG_TERM_PLAN_DESCRIPTOR.name,
        description=CREATE_LONG_TERM_PLAN_DESCRIPTOR.description,
        parameters_schema=CREATE_LONG_TERM_PLAN_DESCRIPTOR.parameters_schema,
        side="server",
        fn=create_complete_plan,
        idempotent=False,
    )
    gateway = _FakeGateway()
    gateway.user_id = "user-1"
    gateway.user_context = {
        "age": 30,
        "gender": "male",
        "height": 172,
        "weight": 68,
        "activity_level": "moderate",
        "health_goal": "maintain",
    }
    dispatcher = ToolDispatcher(_registry_with(descriptor), gateway=gateway)
    call = ToolCall(
        id="plan-call",
        name="create_long_term_plan",
        arguments={
            "user_id": "stale-user",
            "goal": "gain_muscle",
            "duration_days": 7,
            "start_date": "2026-08-14",
            "profile": {"dietary_restrictions": ["vegetarian"]},
            "request_id": "plan-request-1",
        },
    )

    result = await dispatcher.dispatch("session-1", call, 1000)

    assert result.ok is True
    assert captured["user_id"] == "user-1"
    assert captured["profile"]["height_cm"] == 172
    assert captured["profile"]["health_goal"] == "gain_muscle"
    assert captured["profile"]["dietary_restrictions"] == ["vegetarian"]


@pytest.mark.asyncio
async def test_cleanup_session_rejects_pending_client_calls():
    gateway = _FakeGateway()
    dispatcher = ToolDispatcher(_registry_with(_client_descriptor()), gateway=gateway)
    call = ToolCall(id="corr-2", name="get_user_profile", arguments={"value": "x"})

    task = asyncio.create_task(dispatcher.dispatch("session-1", call, 1000))
    await asyncio.sleep(0)
    dispatcher.cleanup_session("session-1")
    result = await task

    assert result == ToolResult(ok=False, error="DISCONNECTED")


@pytest.mark.asyncio
async def test_non_idempotent_tool_requires_request_id():
    descriptor = _client_descriptor(idempotent=False)
    dispatcher = ToolDispatcher(_registry_with(descriptor), gateway=_FakeGateway())
    call = ToolCall(id="corr-3", name="log_meal", arguments={"value": "x"})

    result = await dispatcher.dispatch("session-1", call, 100)

    assert result == ToolResult(ok=False, error="INVALID_ARGS")


@pytest.mark.asyncio
async def test_non_idempotent_tool_reuses_cached_result_for_same_request_id():
    descriptor = ToolDescriptor(
        name="save_profile",
        description="write tool",
        parameters_schema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["request_id", "value"],
        },
        side="server",
        idempotent=False,
        fn=lambda request_id, value: {"saved": value},
    )
    db = _FakeDbSession()
    dispatcher = ToolDispatcher(_registry_with(descriptor), db_session=db)
    call = ToolCall(id="corr-4", name="save_profile", arguments={"request_id": "r1", "value": "a"})

    first = await dispatcher.dispatch("session-1", call, 100)
    second = await dispatcher.dispatch("session-1", ToolCall(id="corr-5", name="save_profile", arguments={"request_id": "r1", "value": "a"}), 100)

    assert first == ToolResult(ok=True, data={"saved": "a"})
    assert second == ToolResult(ok=True, data={"saved": "a"})


# ---------------------------------------------------------------------------
# Per-session diversification of suggest_dish
#
# ``suggest_dish`` ranks candidates by ``(|total_calories - target_kcal|, id)``.
# Every dish is scaled to hit the target, so that distance is ~0 for all of
# them and the id tiebreak would return the same dish on every turn. The
# dispatcher feeds back the ids already returned in this session so plain chat
# gets the variety that only the planner used to have.
# ---------------------------------------------------------------------------


def _dish_registry() -> ToolRegistry:
    from services.agent.tools.dish import TOOL_DESCRIPTOR

    return _registry_with(TOOL_DESCRIPTOR)


def _dish_call(index: int, **overrides: Any) -> ToolCall:
    args: dict[str, Any] = {"meal_type": "lunch", "target_kcal": 850}
    args.update(overrides)
    return ToolCall(id=f"dish-{index}", name="suggest_dish", arguments=args)


@pytest.mark.asyncio
async def test_suggest_dish_does_not_repeat_within_a_session():
    dispatcher = ToolDispatcher(_dish_registry())

    names: list[str] = []
    for i in range(10):
        result = await dispatcher.dispatch("session-1", _dish_call(i), 5000)
        assert result.ok, result.error
        names.append(result.data["name"])

    # Without the diversity window this would be the same dish 10 times.
    assert len(set(names)) == len(names), f"repeated suggestions: {names}"


@pytest.mark.asyncio
async def test_suggest_dish_diversity_is_scoped_per_session():
    dispatcher = ToolDispatcher(_dish_registry())

    first_a = await dispatcher.dispatch("session-a", _dish_call(0), 5000)
    second_a = await dispatcher.dispatch("session-a", _dish_call(1), 5000)
    first_b = await dispatcher.dispatch("session-b", _dish_call(2), 5000)

    assert first_a.data["id"] != second_a.data["id"]
    # A fresh conversation must not inherit another session's history.
    assert first_b.data["id"] == first_a.data["id"]


@pytest.mark.asyncio
async def test_suggest_dish_honours_caller_supplied_recent_ids():
    dispatcher = ToolDispatcher(_dish_registry())

    baseline = await dispatcher.dispatch("session-1", _dish_call(0), 5000)
    excluded = baseline.data["id"]

    result = await dispatcher.dispatch(
        "session-2", _dish_call(1, recent_dish_ids=[excluded]), 5000
    )

    assert result.ok, result.error
    assert result.data["id"] != excluded


@pytest.mark.asyncio
async def test_suggest_dish_merges_caller_ids_with_session_history():
    """An incomplete caller list must not undo the session's own record.

    The LLM rebuilds ``recent_dish_ids`` from conversation history, so it drops
    entries whenever history is trimmed or a DB write fails. Replacing our
    record with that stale list would hand the user a dish they just saw.
    """
    dispatcher = ToolDispatcher(_dish_registry())

    first = await dispatcher.dispatch("session-1", _dish_call(0), 5000)
    second = await dispatcher.dispatch("session-1", _dish_call(1), 5000)

    # Caller only remembers the first dish; the dispatcher knows about both.
    third = await dispatcher.dispatch(
        "session-1", _dish_call(2, recent_dish_ids=[first.data["id"]]), 5000
    )

    assert third.ok, third.error
    assert third.data["id"] not in {first.data["id"], second.data["id"]}


@pytest.mark.asyncio
async def test_suggest_dish_falls_back_instead_of_failing_when_exhausted():
    """A saturated window must never turn into a spurious NO_DISH_FOUND."""
    dispatcher = ToolDispatcher(_dish_registry())

    # "snack" is the smallest bucket in the catalog, so this loop exhausts
    # every candidate several times over.
    for i in range(40):
        result = await dispatcher.dispatch(
            "session-1", _dish_call(i, meal_type="snack", target_kcal=200), 5000
        )
        assert result.ok, f"call {i} failed with {result.error}"


@pytest.mark.asyncio
async def test_cleanup_session_clears_diversity_window():
    dispatcher = ToolDispatcher(_dish_registry())

    first = await dispatcher.dispatch("session-1", _dish_call(0), 5000)
    assert dispatcher._recent_ids

    dispatcher.cleanup_session("session-1")
    assert dispatcher._recent_ids == {}

    # History is gone, so the ranking restarts from the best-fitting dish.
    after_cleanup = await dispatcher.dispatch("session-1", _dish_call(1), 5000)
    assert after_cleanup.data["id"] == first.data["id"]


@pytest.mark.asyncio
async def test_diversity_window_does_not_grow_unbounded():
    from services.agent.tool_dispatcher import _RECENT_IDS_MAX_SESSIONS

    dispatcher = ToolDispatcher(_dish_registry())

    for i in range(_RECENT_IDS_MAX_SESSIONS + 25):
        await dispatcher.dispatch(f"session-{i}", _dish_call(i), 5000)

    assert len(dispatcher._recent_ids) <= _RECENT_IDS_MAX_SESSIONS
