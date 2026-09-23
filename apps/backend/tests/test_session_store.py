from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from db.session_store import DbSessionStore, SessionStore, session_store


@dataclass
class FakeDb:
    rows: list[dict[str, Any]] = field(default_factory=list)

    async def execute(self, statement, params):
        self.rows.append(params)


def test_session_store_append_turn_keeps_tool_metadata():
    store = SessionStore()
    store.appendTurn("s1", "tool", "{}", "c1", "get_today_meals")
    turn = store.get_history("s1")[0]
    assert turn.tool_call_id == "c1"
    assert turn.tool_name == "get_today_meals"


def test_session_store_discards_legacy_raw_thoughts() -> None:
    store = SessionStore()
    store.appendTurn("s1", "assistant", "answer", thoughts="private scratchpad")

    assert store.get_history("s1")[0].thoughts == ""


@pytest.mark.asyncio
async def test_db_session_store_append_turn_inserts_only():
    db = FakeDb()
    store = DbSessionStore(db)
    public_trace = {
        "trace_id": "trace-1",
        "status": "COMPLETED",
        "steps": [{"public_event_type": "PROFILE_CONTEXT_USED"}],
    }
    msg_id = await store.appendTurn(
        "s1", "assistant", "answer", None, None, "private scratchpad", None, public_trace
    )
    assert msg_id
    assert db.rows == [
        {
            "id": msg_id,
            "session_id": "s1",
            "role": "assistant",
            "content": "answer",
            "tool_call_id": None,
            "tool_name": None,
            "thoughts": "",
            "structured_data": None,
            "public_trace": json.dumps(public_trace, ensure_ascii=False),
        }
    ]


@pytest.mark.asyncio
async def test_db_session_store_persists_structured_card_payload():
    db = FakeDb()
    store = DbSessionStore(db)
    structured = {
        "type": "structured",
        "text": "",
        "meal_name": "Cơm sườn",
        "actions": [{"kind": "food", "name": "Cơm"}],
    }

    await store.appendTurn(
        "s1",
        "assistant",
        "Đã ghi nhận Cơm sườn",
        structured_data=structured,
    )

    assert json.loads(db.rows[0]["structured_data"]) == structured
    assert store.db_session is db


@pytest.mark.asyncio
async def test_db_insert_failure_cannot_report_a_saved_chat_turn():
    class FailingDb:
        async def execute(self, statement, params):
            raise RuntimeError("database rejected insert")

    with pytest.raises(RuntimeError, match="database rejected insert"):
        await DbSessionStore(FailingDb()).appendTurn("unsaved-chat", "assistant", "answer")
    assert session_store.get_history("unsaved-chat") == []
