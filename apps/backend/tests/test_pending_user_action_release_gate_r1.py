from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from services.agent.llm_client import ToolCall
from services.agent.memory_service import Context
from services.agent.orchestrator import AgentOrchestrator
from services.agent.pending_user_action import PendingUserActionStore
from services.agent.tool_dispatcher import ToolResult


def _action(store: PendingUserActionStore, *, session: str = "session-a", owner: str = "user-a", action_type: str = "LOG_RECOMMENDED_DISH"):
    return store.create_action(
        session,
        owner_user_id=owner,
        action_type=action_type,
        tool_name="log_meal",
        tool_arguments={
            "meal_type": "dinner",
            "dish_name": "Cơm gà",
            "catalog_dish_id": "dish-42",
            "request_id": "stable-request",
        },
        target_id="dish-42",
        display_name="Cơm gà",
    )


def test_reconnect_and_owner_conversation_isolation() -> None:
    store = PendingUserActionStore()
    action = _action(store)
    store.put(action)

    # A new gateway after a websocket reconnect can claim the same in-memory
    # action, but another conversation or account cannot.
    assert store.claim_confirmation("session-b", "user-a", "có").status == "NO_MATCH"
    assert store.claim_confirmation("session-a", "user-b", "có").status == "OWNER_MISMATCH"
    claimed = store.claim_confirmation("session-a", "user-a", "có")
    assert claimed.status == "CLAIMED"
    assert claimed.action is action


def test_ambiguous_superseded_and_expired_actions_are_never_claimed() -> None:
    store = PendingUserActionStore()
    old = _action(store)
    latest = _action(store)
    store.put(old)
    store.put(latest)
    assert old.status == "SUPERSEDED"
    assert store.claim_confirmation("session-a", "user-a", "có").action is latest

    ambiguous_store = PendingUserActionStore()
    ambiguous_store.put(_action(ambiguous_store, action_type="LOG_RECOMMENDED_DISH"))
    ambiguous_store.put(_action(ambiguous_store, action_type="SAVE_OTHER_ACTION"))
    assert ambiguous_store.claim_confirmation("session-a", "user-a", "có").status == "AMBIGUOUS"

    expired_store = PendingUserActionStore()
    expired = _action(expired_store)
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired_store.put(expired)
    assert expired_store.claim_confirmation("session-a", "user-a", "có").status == "ACTION_EXPIRED"


class _Tools:
    def schemas(self):
        return []


class _Memory:
    async def loadContext(self, session_id: str, user_text: str) -> Context:
        return Context()


@dataclass
class _SessionStore:
    turns: list[tuple[Any, ...]] = field(default_factory=list)

    async def appendTurn(self, *args: Any) -> None:
        self.turns.append(args)


@dataclass
class _Gateway:
    user_id: str
    done: list[str] = field(default_factory=list)
    action_states: list[dict[str, Any]] = field(default_factory=list)
    debug_trace_enabled: bool = False

    async def send_done(self, text: str, *, structured_data=None, public_trace=None) -> None:
        self.done.append(text)

    async def send_action_state(self, state: dict[str, Any]) -> None:
        self.action_states.append(state)


class _BlockingDispatcher:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def dispatch(self, session_id: str, call: ToolCall, timeout_ms: int) -> ToolResult:
        self.calls.append(call)
        self.started.set()
        await self.release.wait()
        return ToolResult(
            ok=True,
            data={
                "write_status": "PERSISTED",
                "catalog_dish_id": "dish-42",
                "read_back_catalog_dish_id": "dish-42",
            },
            ui_message={
                "structured": {
                    "actions": [
                        {"details": {"catalog_dish_id": "dish-42"}}
                    ]
                }
            },
        )


class _UnusedLlm:
    async def chat(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - assertion guard
        raise AssertionError("A pending confirmation must not invoke the LLM")


@pytest.mark.asyncio
async def test_multidevice_confirmation_performs_one_write_and_returns_idempotent_state() -> None:
    pending = PendingUserActionStore()
    pending.put(_action(pending))
    dispatcher = _BlockingDispatcher()
    first_gateway = _Gateway("user-a")
    second_gateway = _Gateway("user-a")
    first = AgentOrchestrator(
        _UnusedLlm(), _Tools(), _Memory(), _SessionStore(), dispatcher, first_gateway,
        pending_actions=pending,
    )
    second = AgentOrchestrator(
        _UnusedLlm(), _Tools(), _Memory(), _SessionStore(), dispatcher, second_gateway,
        pending_actions=pending,
    )

    first_task = asyncio.create_task(first.handleChatMessage("session-a", "có"))
    await dispatcher.started.wait()
    await second.handleChatMessage("session-a", "có")
    assert len(dispatcher.calls) == 1
    assert second_gateway.action_states[-1]["status"] == "IN_PROGRESS"

    dispatcher.release.set()
    await first_task
    await second.handleChatMessage("session-a", "có")
    assert len(dispatcher.calls) == 1
    assert second_gateway.action_states[-1]["status"] == "ALREADY_EXECUTED"
    assert dispatcher.calls[0].arguments["catalog_dish_id"] == "dish-42"
    assert first_gateway.action_states[-1]["status"] == "PERSISTED"
