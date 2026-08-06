"""Unit tests for ``services.agent.memory_service.MemoryService``.

Validates Requirements 5.2, 5.3, 5.4, 7.5 from the chatbot-redesign spec.

Like ``tests/test_plan_tools.py``, these tests use a lightweight fake
``AsyncSession`` so they verify the SQL shape and parameters without
spinning up Postgres. Behaviour exercised:

- ``getRollingSummary`` returns the stored summary or ``""`` when missing.
- ``saveRollingSummary`` emits an upsert against ``chat_session_memory``.
- ``getPinnedFacts`` joins ``chat_sessions`` and filters ``status='confirmed'``.
- ``proposeFact`` resolves the owning ``user_id`` then inserts with
  ``status='pending'``.
- ``confirmFact`` / ``rejectFact`` flip ``status`` and surface
  ``FACT_NOT_FOUND`` when the row does not exist.
- ``updateRollingSummary`` re-summarises old turns once the session exceeds
  ``SUMMARY_THRESHOLD`` and proposes only previously-unseen pinned facts.
- Input validation rejects empty ids, bad categories, and unknown sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from config import settings
from services.agent.memory_service import (
    MemoryService,
    buildFactExtractionPrompt,
    buildSummaryPrompt,
)


# --------------------------------------------------------------------------- #
# Fake AsyncSession + queryable in-memory tables
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResult:
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    rowcount: int = -1

    def first(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


@dataclass
class _FakeAsyncSession:
    """Minimal ``AsyncSession`` substitute backed by in-memory dicts.

    Every ``execute`` call is logged into ``executed`` so tests can assert on
    the SQL that would be sent to Postgres. The simulated tables:

    - ``chat_sessions``: ``{session_id: user_id}``
    - ``chat_session_memory``: ``{session_id: rolling_summary}``
    - ``user_facts``: list of dicts (one per row)
    - ``chat_messages``: list of dicts (one per row)
    """

    chat_sessions: dict[str, str] = field(default_factory=dict)
    chat_session_memory: dict[str, str] = field(default_factory=dict)
    user_facts: list[dict[str, Any]] = field(default_factory=list)
    chat_messages: list[dict[str, Any]] = field(default_factory=list)
    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        sql = str(statement)
        self.executed.append((sql, params))

        # SELECT COUNT(*) FROM chat_messages WHERE session_id = :sid
        if "SELECT COUNT(*) FROM chat_messages" in sql:
            sid = params["sid"]
            n = sum(1 for m in self.chat_messages if m["session_id"] == sid)
            return _FakeResult(rows=[(n,)])

        # SELECT id, session_id, role, content, ... FROM chat_messages
        if "FROM chat_messages" in sql:
            sid = params["sid"]
            limit = int(params.get("lim", 0)) if params else 0
            matched = [m for m in self.chat_messages if m["session_id"] == sid]
            # Choose ASC or DESC ordering based on the SQL shape.
            if "ORDER BY created_at ASC" in sql:
                matched.sort(key=lambda m: (m["created_at"], m["id"]))
            else:
                matched.sort(
                    key=lambda m: (m["created_at"], m["id"]), reverse=True
                )
            if limit > 0:
                matched = matched[:limit]
            rows = [
                (
                    m["id"],
                    m["session_id"],
                    m["role"],
                    m["content"],
                    m.get("tool_call_id"),
                    m.get("tool_name"),
                    m["created_at"],
                )
                for m in matched
            ]
            return _FakeResult(rows=rows)

        # SELECT rolling_summary FROM chat_session_memory WHERE session_id = :sid
        if "FROM chat_session_memory" in sql:
            sid = params["sid"]
            if sid in self.chat_session_memory:
                return _FakeResult(rows=[(self.chat_session_memory[sid],)])
            return _FakeResult(rows=[])

        # INSERT INTO chat_session_memory ... ON CONFLICT ... DO UPDATE
        if "INSERT INTO chat_session_memory" in sql:
            self.chat_session_memory[params["sid"]] = params["summary"]
            return _FakeResult(rowcount=1)

        # SELECT user_id FROM chat_sessions WHERE id = :sid
        if "FROM chat_sessions WHERE id" in sql:
            sid = params["sid"]
            if sid in self.chat_sessions:
                return _FakeResult(rows=[(self.chat_sessions[sid],)])
            return _FakeResult(rows=[])

        # SELECT f.fact FROM user_facts AS f JOIN chat_sessions ...
        # (no f.status filter — used by _load_existing_fact_texts)
        if (
            "FROM user_facts" in sql
            and "JOIN chat_sessions" in sql
            and "f.status = 'confirmed'" not in sql
            and "SELECT" in sql
            and "f.fact" in sql
            and "f.id" not in sql
        ):
            sid = params["sid"]
            user_id = self.chat_sessions.get(sid)
            if user_id is None:
                return _FakeResult(rows=[])
            matched = [
                (f["fact"],)
                for f in self.user_facts
                if f["user_id"] == user_id
            ]
            return _FakeResult(rows=matched)

        # SELECT ... FROM user_facts JOIN chat_sessions ... WHERE s.id = :sid
        if "FROM user_facts" in sql and "JOIN chat_sessions" in sql:
            sid = params["sid"]
            user_id = self.chat_sessions.get(sid)
            if user_id is None:
                return _FakeResult(rows=[])
            matched = [
                (
                    f["id"],
                    f["user_id"],
                    f["category"],
                    f["fact"],
                    f["status"],
                    f.get("source_msg_id"),
                    f.get("created_at"),
                )
                for f in self.user_facts
                if f["user_id"] == user_id and f["status"] == "confirmed"
            ]
            return _FakeResult(rows=matched)

        # INSERT INTO user_facts (...)
        if "INSERT INTO user_facts" in sql:
            self.user_facts.append(
                {
                    "id": params["id"],
                    "user_id": params["user_id"],
                    "category": params["category"],
                    "fact": params["fact"],
                    "status": params.get("status", "pending"),
                    "source_msg_id": params.get("source"),
                    "created_at": datetime.now(timezone.utc),
                }
            )
            return _FakeResult(rowcount=1)

        # UPDATE user_facts SET status = :status WHERE id = :id
        if "UPDATE user_facts" in sql:
            target_id = params["id"]
            for row in self.user_facts:
                if row["id"] == target_id:
                    row["status"] = params["status"]
                    return _FakeResult(rowcount=1)
            return _FakeResult(rowcount=0)

        return _FakeResult()


# --------------------------------------------------------------------------- #
# getRollingSummary / saveRollingSummary
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_rolling_summary_returns_empty_when_missing():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]
    result = await svc.getRollingSummary("session-1")
    assert result == ""


@pytest.mark.asyncio
async def test_get_rolling_summary_returns_stored_value():
    session = _FakeAsyncSession(
        chat_session_memory={"session-1": "user thích phở bò"},
    )
    svc = MemoryService(session)  # type: ignore[arg-type]
    result = await svc.getRollingSummary("session-1")
    assert result == "user thích phở bò"


@pytest.mark.asyncio
async def test_save_rolling_summary_upserts():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]

    await svc.saveRollingSummary("session-1", "summary v1")
    assert session.chat_session_memory["session-1"] == "summary v1"

    # Second call updates the same row.
    await svc.saveRollingSummary("session-1", "summary v2")
    assert session.chat_session_memory["session-1"] == "summary v2"

    # Both writes used the upsert SQL shape.
    insert_calls = [
        sql for sql, _ in session.executed if "INSERT INTO chat_session_memory" in sql
    ]
    assert len(insert_calls) == 2
    for sql in insert_calls:
        assert "ON CONFLICT" in sql
        assert "DO UPDATE" in sql


@pytest.mark.asyncio
async def test_save_rolling_summary_rejects_empty_session_id():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_SESSION_ID"):
        await svc.saveRollingSummary("", "summary")


@pytest.mark.asyncio
async def test_save_rolling_summary_rejects_non_string_summary():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_SUMMARY"):
        await svc.saveRollingSummary("s", 123)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# getPinnedFacts — Requirement 5.4
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_pinned_facts_only_returns_confirmed_for_session_owner():
    session = _FakeAsyncSession(
        chat_sessions={"sess-A": "user-1", "sess-B": "user-2"},
        user_facts=[
            {
                "id": str(uuid4()),
                "user_id": "user-1",
                "category": "allergy",
                "fact": "dị ứng hải sản",
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": datetime(2025, 1, 1, 10, 0, 0),
            },
            {
                "id": str(uuid4()),
                "user_id": "user-1",
                "category": "preference",
                "fact": "thích ăn cay",
                "status": "pending",  # must be filtered out
                "source_msg_id": None,
                "created_at": datetime(2025, 1, 2, 10, 0, 0),
            },
            {
                "id": str(uuid4()),
                "user_id": "user-1",
                "category": "goal",
                "fact": "muốn giảm 5kg",
                "status": "rejected",  # must be filtered out
                "source_msg_id": None,
                "created_at": datetime(2025, 1, 3, 10, 0, 0),
            },
            {
                "id": str(uuid4()),
                "user_id": "user-2",  # belongs to a different session/user
                "category": "allergy",
                "fact": "dị ứng đậu phộng",
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": datetime(2025, 1, 1, 11, 0, 0),
            },
        ],
    )
    svc = MemoryService(session)  # type: ignore[arg-type]

    facts = await svc.getPinnedFacts("sess-A")
    assert len(facts) == 1
    assert facts[0].user_id == "user-1"
    assert facts[0].category == "allergy"
    assert facts[0].fact == "dị ứng hải sản"
    assert facts[0].status == "confirmed"


@pytest.mark.asyncio
async def test_get_pinned_facts_returns_empty_for_unknown_session():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]
    assert await svc.getPinnedFacts("does-not-exist") == []


# --------------------------------------------------------------------------- #
# proposeFact — Requirement 5.3
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_propose_fact_inserts_pending_row_with_owner_user_id():
    session = _FakeAsyncSession(chat_sessions={"sess-1": "user-1"})
    svc = MemoryService(session)  # type: ignore[arg-type]

    fact_id = await svc.proposeFact(
        session_id="sess-1",
        fact_text="dị ứng tôm",
        category="allergy",
        source_msg_id="msg-42",
    )

    # Returned id is a UUID string and matches the stored row.
    assert isinstance(fact_id, str)
    assert len(session.user_facts) == 1
    row = session.user_facts[0]
    assert row["id"] == fact_id
    assert row["user_id"] == "user-1"  # resolved from chat_sessions
    assert row["category"] == "allergy"
    assert row["fact"] == "dị ứng tôm"
    assert row["status"] == "pending"
    assert row["source_msg_id"] == "msg-42"


@pytest.mark.asyncio
async def test_propose_fact_strips_whitespace_in_fact_text():
    session = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(session)  # type: ignore[arg-type]

    await svc.proposeFact(
        session_id="s",
        fact_text="   ăn chay   ",
        category="preference",
        source_msg_id=None,
    )
    assert session.user_facts[0]["fact"] == "ăn chay"
    assert session.user_facts[0]["source_msg_id"] is None


@pytest.mark.asyncio
async def test_propose_fact_rejects_unknown_session():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="SESSION_NOT_FOUND"):
        await svc.proposeFact(
            session_id="missing",
            fact_text="ăn chay",
            category="preference",
            source_msg_id=None,
        )
    # No insert was attempted.
    assert session.user_facts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category",
    ["", "random", "PREFERENCE", "habit"],
)
async def test_propose_fact_rejects_unknown_category(category):
    session = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_CATEGORY"):
        await svc.proposeFact(
            session_id="s",
            fact_text="ăn chay",
            category=category,
            source_msg_id=None,
        )
    assert session.user_facts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_text", ["", "   ", "\t\n"])
async def test_propose_fact_rejects_blank_text(bad_text):
    session = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_FACT_TEXT"):
        await svc.proposeFact(
            session_id="s",
            fact_text=bad_text,
            category="preference",
            source_msg_id=None,
        )


# --------------------------------------------------------------------------- #
# confirmFact / rejectFact
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_confirm_fact_flips_status_to_confirmed():
    fact_id = str(uuid4())
    session = _FakeAsyncSession(
        user_facts=[
            {
                "id": fact_id,
                "user_id": "u",
                "category": "allergy",
                "fact": "f",
                "status": "pending",
                "source_msg_id": None,
                "created_at": datetime.now(timezone.utc),
            }
        ],
    )
    svc = MemoryService(session)  # type: ignore[arg-type]

    await svc.confirmFact(fact_id)
    assert session.user_facts[0]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_reject_fact_flips_status_to_rejected():
    fact_id = str(uuid4())
    session = _FakeAsyncSession(
        user_facts=[
            {
                "id": fact_id,
                "user_id": "u",
                "category": "preference",
                "fact": "f",
                "status": "pending",
                "source_msg_id": None,
                "created_at": datetime.now(timezone.utc),
            }
        ],
    )
    svc = MemoryService(session)  # type: ignore[arg-type]

    await svc.rejectFact(fact_id)
    assert session.user_facts[0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_confirm_fact_raises_when_fact_missing():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="FACT_NOT_FOUND"):
        await svc.confirmFact(str(uuid4()))


@pytest.mark.asyncio
async def test_reject_fact_raises_when_fact_missing():
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="FACT_NOT_FOUND"):
        await svc.rejectFact(str(uuid4()))


@pytest.mark.asyncio
async def test_confirm_fact_rejects_blank_id():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_FACT_ID"):
        await svc.confirmFact("")


# --------------------------------------------------------------------------- #
# updateRollingSummary — Requirement 5.2 / 5.3
# --------------------------------------------------------------------------- #


@dataclass
class _FakeLLMResponse:
    """Stand-in for ``services.agent.llm_client.LLMResponse``."""

    full_text: str = ""
    tool_calls: list = field(default_factory=list)
    content_stream: Any = None


class _ScriptedLLM:
    """Tiny LLM double that returns scripted ``full_text`` per call.

    ``responses`` is consumed in order: the first call returns
    ``responses[0]``, the second ``responses[1]``, and so on. ``side_effect``
    (if set on a slot) is raised instead of returning. Records every call so
    tests can assert on the prompts that were sent.
    """

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> _FakeLLMResponse:
        self.calls.append(
            {"messages": messages, "tools": tools, "stream": stream}
        )
        if not self._responses:
            raise AssertionError("scripted LLM ran out of responses")
        next_response = self._responses.pop(0)
        if isinstance(next_response, BaseException):
            raise next_response
        return next_response


def _make_chat_messages(session_id: str, n: int) -> list[dict[str, Any]]:
    """Build ``n`` alternating user/assistant rows for ``session_id``."""
    base = datetime(2025, 1, 1, 9, 0, 0)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"{'câu hỏi' if role == 'user' else 'trả lời'} #{i + 1}"
        rows.append(
            {
                "id": str(uuid4()),
                "session_id": session_id,
                "role": role,
                "content": content,
                "tool_call_id": None,
                "tool_name": None,
                "created_at": base + timedelta(minutes=i),
            }
        )
    return rows


@pytest.mark.asyncio
async def test_update_rolling_summary_skips_when_below_threshold():
    sid = str(uuid4())
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, settings.summary_threshold),
    )
    llm = _ScriptedLLM(responses=[])  # any call would raise

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # No summary write happened, no LLM call was made.
    assert llm.calls == []
    assert db.chat_session_memory == {}


@pytest.mark.asyncio
async def test_update_rolling_summary_writes_summary_and_proposes_facts():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5  # enough to trigger summary
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="Tóm tắt mới về user."),
            _FakeLLMResponse(
                full_text=(
                    '[{"category": "allergy", "fact": "dị ứng tôm"}, '
                    '{"category": "preference", "fact": "thích ăn cay"}]'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # Summary was saved.
    assert db.chat_session_memory[sid] == "Tóm tắt mới về user."
    # Both facts were proposed with status='pending' for the owning user.
    assert len(db.user_facts) == 2
    assert {f["fact"] for f in db.user_facts} == {
        "dị ứng tôm",
        "thích ăn cay",
    }
    for fact in db.user_facts:
        assert fact["user_id"] == "user-1"
        assert fact["status"] == "pending"
        assert fact["source_msg_id"] is None

    # LLM was called twice: once for summary, once for fact extraction.
    assert len(llm.calls) == 2
    # Summary call had no tools and stream=False.
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["stream"] is False


@pytest.mark.asyncio
async def test_update_rolling_summary_skips_existing_facts_case_insensitive():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
        user_facts=[
            {
                "id": str(uuid4()),
                "user_id": "user-1",
                "category": "allergy",
                "fact": "Dị ứng tôm",  # mixed case to test casefold dedupe
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": datetime(2024, 12, 1),
            }
        ],
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="summary"),
            _FakeLLMResponse(
                full_text=(
                    '[{"category": "allergy", "fact": "dị ứng tôm"}, '
                    '{"category": "preference", "fact": "thích phở bò"}]'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # The duplicate "dị ứng tôm" was skipped; only the new fact was inserted.
    facts_with_status_pending = [
        f for f in db.user_facts if f["status"] == "pending"
    ]
    assert len(facts_with_status_pending) == 1
    assert facts_with_status_pending[0]["fact"] == "thích phở bò"


@pytest.mark.asyncio
async def test_update_rolling_summary_performs_fact_updates():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
        user_facts=[
            {
                "id": "fact-1",
                "user_id": "user-1",
                "category": "allergy",
                "fact": "Dị ứng lạc",
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": datetime(2024, 12, 1),
            }
        ],
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="summary"),
            _FakeLLMResponse(
                full_text=(
                    '[{"action": "update", "category": "allergy", "fact": "Dị ứng hạt điều", '
                    '"target_fact": "Dị ứng lạc", "confidence": "high"}]'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # The old fact is now rejected
    old_fact = next(f for f in db.user_facts if f["id"] == "fact-1")
    assert old_fact["status"] == "rejected"

    # The new fact is proposed and confirmed (high confidence allergy)
    new_fact = next(f for f in db.user_facts if f["id"] != "fact-1")
    assert new_fact["fact"] == "Dị ứng hạt điều"
    assert new_fact["status"] == "confirmed"


@pytest.mark.asyncio
async def test_update_rolling_summary_performs_fact_removals():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
        user_facts=[
            {
                "id": "fact-2",
                "user_id": "user-1",
                "category": "goal",
                "fact": "Mục tiêu giảm 5kg",
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": datetime(2024, 12, 1),
            }
        ],
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="summary"),
            _FakeLLMResponse(
                full_text=(
                    '[{"action": "remove", "category": "goal", '
                    '"target_fact": "Mục tiêu giảm 5kg", "confidence": "high"}]'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # The fact is now rejected
    fact = next(f for f in db.user_facts if f["id"] == "fact-2")
    assert fact["status"] == "rejected"
    # No new facts were added
    assert len(db.user_facts) == 1


@pytest.mark.asyncio
async def test_update_rolling_summary_handles_markdown_fenced_json():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="summary"),
            _FakeLLMResponse(
                full_text=(
                    'Đây là kết quả:\n'
                    '```json\n'
                    '[{"category": "goal", "fact": "muốn giảm 5kg"}]\n'
                    '```'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    pending = [f for f in db.user_facts if f["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["fact"] == "muốn giảm 5kg"
    assert pending[0]["category"] == "goal"


@pytest.mark.asyncio
async def test_update_rolling_summary_buckets_unknown_category_as_other():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="summary"),
            _FakeLLMResponse(
                full_text=(
                    '[{"category": "weird-bucket", "fact": "đi bộ buổi sáng"}]'
                )
            ),
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    pending = [f for f in db.user_facts if f["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["category"] == "other"


@pytest.mark.asyncio
async def test_update_rolling_summary_swallows_llm_failure():
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
    )
    # First LLM call (summary) blows up; second call is never made.
    llm = _ScriptedLLM(responses=[RuntimeError("ollama down"), RuntimeError("x")])

    svc = MemoryService(db)  # type: ignore[arg-type]
    # Best-effort contract: errors must NOT propagate.
    await svc.updateRollingSummary(sid, llm)

    # No summary written, but the call returned cleanly.
    assert sid not in db.chat_session_memory


@pytest.mark.asyncio
async def test_update_rolling_summary_invalid_session_id_raises():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    llm = _ScriptedLLM(responses=[])
    with pytest.raises(ValueError, match="INVALID_SESSION_ID"):
        await svc.updateRollingSummary("", llm)


@pytest.mark.asyncio
async def test_update_rolling_summary_skips_when_no_summary_text_returned():
    """If the LLM emits whitespace-only text, the prior summary is preserved."""
    sid = str(uuid4())
    n_turns = settings.summary_threshold + 5
    db = _FakeAsyncSession(
        chat_sessions={sid: "user-1"},
        chat_messages=_make_chat_messages(sid, n_turns),
        chat_session_memory={sid: "previous summary"},
    )
    llm = _ScriptedLLM(
        responses=[
            _FakeLLMResponse(full_text="   \n  "),  # blank summary
            _FakeLLMResponse(full_text="[]"),  # no facts
        ]
    )

    svc = MemoryService(db)  # type: ignore[arg-type]
    await svc.updateRollingSummary(sid, llm)

    # Previous summary was preserved, no facts inserted.
    assert db.chat_session_memory[sid] == "previous summary"
    assert db.user_facts == []


# --------------------------------------------------------------------------- #
# Module-level prompt builders
# --------------------------------------------------------------------------- #


def test_build_summary_prompt_includes_prior_summary_when_present():
    msgs = buildSummaryPrompt(
        turns_text="user: hello\nassistant: hi",
        prior_summary="user thích ăn chay",
    )
    assert isinstance(msgs, list)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    # User content references both the prior summary and the new turns.
    assert "user thích ăn chay" in msgs[1]["content"]
    assert "user: hello" in msgs[1]["content"]


def test_build_summary_prompt_omits_empty_prior_summary():
    msgs = buildSummaryPrompt(
        turns_text="user: a\nassistant: b",
        prior_summary="",
    )
    assert "Tóm tắt trước đây" not in msgs[1]["content"]
    assert "user: a" in msgs[1]["content"]


def test_build_fact_extraction_prompt_returns_messages_format():
    msgs = buildFactExtractionPrompt(turns_text="user: tôi dị ứng tôm")
    assert isinstance(msgs, list)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    # The system prompt advertises the schema and the allowed categories.
    assert "category" in msgs[0]["content"]
    assert "preference" in msgs[0]["content"]
    assert "allergy" in msgs[0]["content"]
    assert "tôi dị ứng tôm" in msgs[1]["content"]
