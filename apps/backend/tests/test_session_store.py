from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from db.session_store import DbSessionStore, SessionStore


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


@pytest.mark.asyncio
async def test_db_session_store_append_turn_inserts_only():
    db = FakeDb()
    store = DbSessionStore(db)
    msg_id = await store.appendTurn(
        "s1", "assistant", "answer", None, None, "reasoning"
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
            "thoughts": "reasoning",
            "structured_data": None,
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
