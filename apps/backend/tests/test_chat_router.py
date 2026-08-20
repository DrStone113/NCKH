from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from modules.chat.router import get_session_messages, list_chat_sessions


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


@dataclass
class _FakeDb:
    rows: list[Any]
    sql: str = ""
    params: dict[str, Any] | None = None

    async def execute(self, statement: Any, params: dict[str, Any]) -> _FakeResult:
        self.sql = str(statement)
        self.params = params
        return _FakeResult(self.rows)


@pytest.mark.asyncio
async def test_session_history_returns_persisted_thoughts() -> None:
    created_at = datetime(2026, 8, 14, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id="message-id",
        session_id="session-id",
        role="assistant",
        content="Câu trả lời",
        thoughts="Đối chiếu dữ liệu.",
        structured_data={
            "type": "structured",
            "text": "",
            "meal_name": "Cơm sườn",
            "actions": [],
        },
        created_at=created_at,
    )
    db = _FakeDb([row])

    messages = await get_session_messages("session-id", db=db)  # type: ignore[arg-type]

    assert "thoughts" in db.sql
    assert db.params == {"sid": "session-id"}
    assert messages == [
        {
            "id": "message-id",
            "session_id": "session-id",
            "role": "assistant",
            "content": "Câu trả lời",
            "thoughts": "Đối chiếu dữ liệu.",
            "structured": {
                "type": "structured",
                "text": "",
                "meal_name": "Cơm sườn",
                "actions": [],
            },
            "created_at": created_at.isoformat(),
        }
    ]


@pytest.mark.asyncio
async def test_session_list_is_scoped_to_the_requested_user() -> None:
    db = _FakeDb([])

    sessions = await list_chat_sessions(
        user_id="user-1",
        limit=20,
        db=db,  # type: ignore[arg-type]
    )

    assert sessions == []
    assert db.params == {"user_id": "user-1", "limit": 20}
    assert "s.user_id = :user_id" in db.sql
    assert "OR s.user_id = 'anonymous'" not in db.sql
