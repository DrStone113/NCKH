"""Unit tests for ``MemoryService.queryRag`` and ``MemoryService.loadContext``.

Validates Requirements 5.5, 5.6, 5.8 from the chatbot-redesign spec
(``backend/.kiro/specs/chatbot-redesign/requirements.md``):

- 5.5: ``loadContext`` returns the four pieces (history, rolling_summary,
  pinned_facts, rag_chunks) the orchestrator needs to build the system
  prompt.
- 5.6: ``queryRag`` delegates to a wired-in :class:`RAGService` and forwards
  the AsyncSession.
- 5.8: When no ``RAGService`` is configured (or when it itself returns
  ``[]``), ``queryRag`` and ``loadContext`` produce empty ``rag_chunks``.

Pattern follows ``tests/test_memory_service.py``: a lightweight in-memory
fake ``AsyncSession`` so we exercise the SQL shape and behaviour without a
running Postgres. The RAG side is covered by stub implementations that
record the call arguments instead of running ``sentence-transformers``.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

# Make ``backend/`` importable when running ``pytest`` from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: E402
from models.schemas import KnowledgeChunk  # noqa: E402
from services.agent.memory_service import Context, MemoryService  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake AsyncSession (mirrors ``tests/test_memory_service.py``)
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
    """Async session backed by tiny in-memory tables.

    Only the queries used by ``MemoryService.loadContext`` /
    ``MemoryService.queryRag`` paths are routed:

    - ``chat_messages`` (history load)
    - ``chat_session_memory`` (rolling summary read)
    - ``user_facts`` JOIN ``chat_sessions`` (pinned facts)
    """

    chat_sessions: dict[str, str] = field(default_factory=dict)
    chat_session_memory: dict[str, str] = field(default_factory=dict)
    user_facts: list[dict[str, Any]] = field(default_factory=list)
    chat_messages: list[dict[str, Any]] = field(default_factory=list)
    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        sql = str(statement)
        self.executed.append((sql, params))

        # SELECT ... FROM chat_messages WHERE session_id = :sid ORDER BY ... LIMIT :lim
        if "FROM chat_messages" in sql:
            sid = params["sid"]
            limit = params["lim"]
            matched_all = [
                m for m in self.chat_messages if m["session_id"] == sid
            ]
            # Ensure they are in chronological order for index-based neighboring retrieval
            matched_all.sort(key=lambda m: (m["created_at"], m["id"]))

            if "query" in params:
                q = params["query"].lower()
                matched_indices = [
                    i for i, m in enumerate(matched_all) if q in m["content"].lower()
                ]
                neighbor_indices = set()
                for idx in matched_indices:
                    for offset in range(-2, 3):
                        n_idx = idx + offset
                        if 0 <= n_idx < len(matched_all):
                            neighbor_indices.add(n_idx)
                matched = [matched_all[idx] for idx in sorted(neighbor_indices)]
                matched = matched[:limit]
            else:
                # Normal history load: latest DESC limit
                matched_all.reverse()
                matched = matched_all[:limit]

            return _FakeResult(
                rows=[
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
            )

        # SELECT rolling_summary FROM chat_session_memory WHERE session_id = :sid
        if "FROM chat_session_memory" in sql:
            sid = params["sid"]
            if sid in self.chat_session_memory:
                return _FakeResult(rows=[(self.chat_session_memory[sid],)])
            return _FakeResult(rows=[])

        # SELECT user_id FROM chat_sessions WHERE id = :sid
        if "FROM chat_sessions WHERE id" in sql:
            sid = params["sid"]
            if sid in self.chat_sessions:
                return _FakeResult(rows=[(self.chat_sessions[sid],)])
            return _FakeResult(rows=[])

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

        return _FakeResult()


class _ConcurrentFakeAsyncSession(_FakeAsyncSession):
    supports_concurrent_statements = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active = 0
        self.max_active = 0

    async def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return await super().execute(statement, params)
        finally:
            self.active -= 1


# --------------------------------------------------------------------------- #
# Stub RAGService — records calls without doing real embedding work
# --------------------------------------------------------------------------- #


@dataclass
class _StubRAGService:
    """Minimal stand-in mimicking :class:`RAGService.query`.

    Stores the last ``(query, top_k, db)`` tuple passed to ``query`` so tests
    can assert on the delegation. The ``return_chunks`` field configures what
    the stub returns; the default is the empty list to mirror Requirement
    5.8 behaviour when ``chunk_embeddings`` is empty.
    """

    return_chunks: list[KnowledgeChunk] = field(default_factory=list)
    raise_error: ValueError | None = None
    calls: list[tuple[str, int, Any]] = field(default_factory=list)

    async def query(
        self,
        query: str,
        top_k: int,
        *,
        db: Any,
    ) -> list[KnowledgeChunk]:
        self.calls.append((query, top_k, db))
        if self.raise_error is not None:
            raise self.raise_error
        return list(self.return_chunks)


def _make_chunk(
    similarity: float, *, title: str = "demo"
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=str(uuid4()),
        category="food",
        title=title,
        content=f"content for {title}",
        metadata={},
        similarity=similarity,
    )


def _make_message(
    *,
    session_id: str,
    role: str,
    content: str,
    created_at: datetime,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": created_at,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
    }


# --------------------------------------------------------------------------- #
# queryRag — Requirement 5.6 / 5.8
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_query_rag_returns_empty_when_rag_service_not_configured():
    """5.8: with no RAGService wired in, ``queryRag`` must return ``[]``."""
    session = _FakeAsyncSession()
    svc = MemoryService(session)  # type: ignore[arg-type]

    result = await svc.queryRag("phở bò", top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_query_rag_delegates_to_rag_service_with_db_session():
    """5.6: queryRag forwards (query, top_k, db) to RAGService.query."""
    session = _FakeAsyncSession()
    chunk = _make_chunk(0.83, title="phở")
    rag = _StubRAGService(return_chunks=[chunk])
    svc = MemoryService(session, rag_service=rag)  # type: ignore[arg-type]

    result = await svc.queryRag("phở bò", top_k=3)

    assert result == [chunk]
    assert len(rag.calls) == 1
    query_arg, top_k_arg, db_arg = rag.calls[0]
    assert query_arg == "phở bò"
    assert top_k_arg == 3
    assert db_arg is session  # delegation passes the AsyncSession through


@pytest.mark.asyncio
async def test_query_rag_returns_empty_when_corpus_empty():
    """5.8: RAGService returns [] when chunk_embeddings is empty — passthrough."""
    session = _FakeAsyncSession()
    rag = _StubRAGService(return_chunks=[])
    svc = MemoryService(session, rag_service=rag)  # type: ignore[arg-type]

    result = await svc.queryRag("anything", top_k=5)
    assert result == []
    assert rag.calls == [("anything", 5, session)]


@pytest.mark.asyncio
async def test_cost_optimized_context_can_skip_rag_and_contextual_history():
    session_id = str(uuid4())
    now = datetime.now()
    session = _FakeAsyncSession(
        chat_sessions={session_id: "user-1"},
        chat_messages=[
            _make_message(
                session_id=session_id,
                role="user",
                content="100g ức gà bao nhiêu protein?",
                created_at=now,
            )
        ],
    )
    rag = _StubRAGService(return_chunks=[_make_chunk(0.9)])
    svc = MemoryService(session, rag_service=rag)  # type: ignore[arg-type]

    context = await svc.loadContextCostOptimized(
        session_id,
        "100g ức gà bao nhiêu protein?",
        include_rag=False,
        include_relevant_history=False,
    )

    assert context.rag_chunks == []
    assert context.relevant_history == []
    assert context.rag_requested is False
    assert context.rag_result_status == "NOT_REQUESTED"
    assert rag.calls == []
    assert not any(params and "query" in params for _, params in session.executed)


# --------------------------------------------------------------------------- #
# loadContext — Requirement 5.5
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_load_context_returns_all_four_pieces():
    """5.5: loadContext bundles history + summary + facts + rag_chunks."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    session_id = "sess-1"
    user_id = "user-1"

    chunk = _make_chunk(0.71, title="chunk-A")
    rag = _StubRAGService(return_chunks=[chunk])

    db = _FakeAsyncSession(
        chat_sessions={session_id: user_id},
        chat_session_memory={session_id: "user thích phở bò"},
        chat_messages=[
            _make_message(
                session_id=session_id,
                role="user",
                content="hôm nay tôi nên ăn gì?",
                created_at=base,
            ),
            _make_message(
                session_id=session_id,
                role="assistant",
                content="Bạn nên ăn phở bò",
                created_at=base + timedelta(seconds=5),
            ),
            # Different session — must be ignored.
            _make_message(
                session_id="sess-other",
                role="user",
                content="noise",
                created_at=base + timedelta(seconds=10),
            ),
        ],
        user_facts=[
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "category": "allergy",
                "fact": "dị ứng hải sản",
                "status": "confirmed",
                "source_msg_id": None,
                "created_at": base - timedelta(days=1),
            },
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "category": "preference",
                "fact": "thích cay",
                "status": "pending",  # filtered out
                "source_msg_id": None,
                "created_at": base - timedelta(days=2),
            },
        ],
    )
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    ctx = await svc.loadContext(session_id, "tôi muốn ăn gì giàu protein?")

    assert isinstance(ctx, Context)
    # History: chronological (oldest first), only this session's rows.
    assert len(ctx.history) == 2
    assert ctx.history[0].content == "hôm nay tôi nên ăn gì?"
    assert ctx.history[0].role == "user"
    assert ctx.history[1].content == "Bạn nên ăn phở bò"
    assert ctx.history[1].role == "assistant"
    # Rolling summary loaded as-is.
    assert ctx.rolling_summary == "user thích phở bò"
    # Only the confirmed fact survives.
    assert len(ctx.pinned_facts) == 1
    assert ctx.pinned_facts[0].fact == "dị ứng hải sản"
    assert ctx.pinned_facts[0].status == "confirmed"
    # RAG chunks come from the wired-in stub.
    assert ctx.rag_chunks == [chunk]
    # And were called with (user_text, settings.rag_top_k, db).
    assert rag.calls == [
        ("tôi muốn ăn gì giàu protein?", settings.rag_top_k, db)
    ]


@pytest.mark.asyncio
async def test_load_context_parallelizes_independent_reads_on_scoped_session():
    db = _ConcurrentFakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(db)  # type: ignore[arg-type]

    await svc.loadContext("s", "Cảm ơn bạn nhiều nhé")

    assert db.max_active >= 3
    assert len(db.executed) == 3


@pytest.mark.asyncio
async def test_load_context_history_respects_max_history_turns():
    """history is capped at ``settings.max_history_turns`` and ordered chronologically."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    session_id = "sess-many"
    db = _FakeAsyncSession(
        chat_sessions={session_id: "u"},
        chat_messages=[
            _make_message(
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"turn-{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(settings.max_history_turns + 5)
        ],
    )
    svc = MemoryService(db)  # type: ignore[arg-type]

    ctx = await svc.loadContext(session_id, "next?")

    assert len(ctx.history) == settings.max_history_turns
    # The most recent turn is the last one in the chronological list.
    assert ctx.history[-1].content == (
        f"turn-{settings.max_history_turns + 5 - 1}"
    )
    # Strictly increasing created_at (chronological order).
    timestamps = [t.created_at for t in ctx.history]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_load_context_excludes_scope_guard_turns_from_model_history():
    base = datetime(2025, 1, 1, 12, 0, 0)
    db = _FakeAsyncSession(
        chat_sessions={"s": "u"},
        chat_messages=[
            _make_message(
                session_id="s",
                role="user",
                content="1 + 1 bằng mấy?",
                tool_name="scope_guard",
                created_at=base,
            ),
            _make_message(
                session_id="s",
                role="assistant",
                content="Mình chỉ hỗ trợ sức khỏe.",
                tool_name="scope_guard",
                created_at=base + timedelta(seconds=1),
            ),
            _make_message(
                session_id="s",
                role="user",
                content="Tối nay ăn gì?",
                created_at=base + timedelta(seconds=2),
            ),
        ],
    )
    svc = MemoryService(db)  # type: ignore[arg-type]

    ctx = await svc.loadContext("s", "Gợi ý món khác")

    assert [turn.content for turn in ctx.history] == ["Tối nay ăn gì?"]


@pytest.mark.asyncio
async def test_load_context_returns_empty_pieces_for_unknown_session():
    """A fresh session id with no rows yields empty history/facts/summary."""
    db = _FakeAsyncSession()
    svc = MemoryService(db)  # type: ignore[arg-type]

    ctx = await svc.loadContext("brand-new-session", "câu hỏi đầu tiên")
    assert ctx.history == []
    assert ctx.rolling_summary == ""
    assert ctx.pinned_facts == []
    assert ctx.rag_chunks == []


@pytest.mark.asyncio
async def test_load_context_skips_rag_when_user_text_is_blank():
    """Blank user_text must not trigger a RAGService call (would 400 anyway)."""
    rag = _StubRAGService(return_chunks=[_make_chunk(0.9)])
    db = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    ctx = await svc.loadContext("s", "   ")
    assert ctx.rag_chunks == []
    assert rag.calls == []


@pytest.mark.asyncio
async def test_load_context_keeps_semantic_retrieval_for_punctuation_reference():
    """A bare question mark can refer to prior context and is not chitchat."""
    rag = _StubRAGService(return_chunks=[])
    db = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    await svc.loadContext("s", "?")

    assert rag.calls == [("?", settings.rag_top_k, db)]


@pytest.mark.asyncio
async def test_load_context_skips_rag_on_conversational_keywords():
    """Conversational short responses like 'có', 'không', 'ok' must not trigger RAG."""
    rag = _StubRAGService(return_chunks=[_make_chunk(0.9)])
    db = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    for word in ["có", "không", "ok", "dạ", "ừ", "hủy", "thôi"]:
        ctx = await svc.loadContext("s", word)
        assert ctx.rag_chunks == []
        assert rag.calls == []


@pytest.mark.asyncio
async def test_load_context_skips_rag_when_no_rag_service():
    """5.8: missing RAGService → rag_chunks == []. Other pieces still load."""
    db = _FakeAsyncSession(
        chat_sessions={"s": "u"},
        chat_session_memory={"s": "summary"},
    )
    svc = MemoryService(db)  # type: ignore[arg-type]

    ctx = await svc.loadContext("s", "có RAG không?")
    assert ctx.rag_chunks == []
    assert ctx.rolling_summary == "summary"


@pytest.mark.asyncio
async def test_load_context_swallows_rag_value_errors():
    """A RAGService that rejects the query must not break loadContext."""
    rag = _StubRAGService(raise_error=ValueError("INVALID_QUERY"))
    db = _FakeAsyncSession(chat_sessions={"s": "u"})
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    ctx = await svc.loadContext("s", "bad query")
    # rag_chunks degrades gracefully to [] — the rest of the context still
    # loads so the orchestrator can build the prompt.
    assert ctx.rag_chunks == []


@pytest.mark.asyncio
async def test_load_context_rejects_blank_session_id():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_SESSION_ID"):
        await svc.loadContext("", "hi")


@pytest.mark.asyncio
async def test_load_context_rejects_non_string_user_text():
    svc = MemoryService(_FakeAsyncSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_USER_TEXT"):
        await svc.loadContext("s", 123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_load_context_retrieves_contextual_history():
    """loadContext retrieves contextual history matching the user query (outside the sliding history window)."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    session_id = "sess-long"
    user_id = "user-1"

    # Create 30 messages, so the first 6 are outside the history window of 24
    chat_messages = []
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"tin-nhan-cũ-{i}" if i < 6 else f"tin-nhan-moi-{i}"
        chat_messages.append(
            _make_message(
                session_id=session_id,
                role=role,
                content=content,
                created_at=base + timedelta(seconds=i),
            )
        )

    db = _FakeAsyncSession(
        chat_sessions={session_id: user_id},
        chat_messages=chat_messages,
    )
    rag = _StubRAGService(return_chunks=[])
    svc = MemoryService(db, rag_service=rag)  # type: ignore[arg-type]

    # Query for one of the old messages (e.g. "tin-nhan-cũ-0")
    ctx = await svc.loadContext(session_id, "tin-nhan-cũ-0")

    # History contains the last 24 messages
    assert len(ctx.history) == 24
    assert all("tin-nhan-moi" in m.content for m in ctx.history)

    # Contextual search (relevant_history) contains the messages outside the sliding window
    assert len(ctx.relevant_history) > 0
    # They should be from the first 6 old messages
    assert any("tin-nhan-cũ" in m.content for m in ctx.relevant_history)
