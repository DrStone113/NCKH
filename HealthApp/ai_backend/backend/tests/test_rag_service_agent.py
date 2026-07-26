"""Unit tests for ``services.agent.rag_service.RAGService``.

Validates Requirements 5.6 and 5.8 from
``backend/.kiro/specs/chatbot-redesign/requirements.md``:

- 5.6: ``query_rag(query, top_k)`` with non-empty ``query`` returns a list of
  length ≤ ``top_k``, every chunk has ``similarity ≥
  RAG_SIMILARITY_THRESHOLD``, ordered by descending similarity.
- 5.8: When ``chunk_embeddings`` has zero rows, ``RAGService.query`` returns
  ``[]``.

Uses a small fake ``AsyncSession`` so we can verify SQL shape and behaviour
without a live Postgres / pgvector setup. The embedding model is stubbed so
tests don't trigger ``sentence-transformers`` downloads.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Allow running ``pytest`` from the ``backend/`` directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: E402
from services.agent.rag_service import (  # noqa: E402
    QUERY_RAG_DESCRIPTOR,
    QUERY_RAG_SCHEMA,
    RAGService,
)
from services.agent.tool_registry import ToolDescriptor  # noqa: E402


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


@dataclass
class _Row:
    """Tiny stand-in for a SQLAlchemy ``Row`` exposing attribute access."""

    id: str
    category: str
    title: str
    content: str
    metadata: dict
    similarity: float


@dataclass
class _FakeResult:
    rows: list[Any] = field(default_factory=list)
    first_row: Any = None

    def first(self):
        return self.first_row

    def fetchall(self):
        return list(self.rows)


@dataclass
class _FakeAsyncSession:
    """Minimal stand-in for ``sqlalchemy.ext.asyncio.AsyncSession``.

    The first ``execute`` call (the empty-check ``SELECT 1 FROM
    chunk_embeddings LIMIT 1``) returns ``empty_check_first``. The next call
    (the cosine-similarity query) returns ``rows``. Every (sql, params) pair
    is recorded so tests can assert on the SQL emitted.
    """

    empty: bool = False  # When True, treat chunk_embeddings as empty
    rows: list[Any] = field(default_factory=list)
    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None):
        sql = str(statement)
        self.executed.append((sql, params))

        if "FROM chunk_embeddings LIMIT 1" in sql:
            return _FakeResult(first_row=None if self.empty else (1,))
        return _FakeResult(rows=self.rows)


def _stub_embedding(svc: RAGService, vec: list[float]) -> None:
    """Replace ``svc.embed`` with a fixed vector so tests don't load a model."""
    svc.embed = lambda _q: vec  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Descriptor metadata
# --------------------------------------------------------------------------- #


def test_query_rag_descriptor_metadata():
    d = QUERY_RAG_DESCRIPTOR
    assert isinstance(d, ToolDescriptor)
    assert d.name == "query_rag"
    assert d.side == "server"
    assert d.idempotent is True
    # Module-level descriptor is unbound — startup wiring (task 12.1) sets fn.
    assert d.fn is None

    schema = d.parameters_schema
    assert schema is QUERY_RAG_SCHEMA
    assert "query" in schema["required"]
    assert schema["properties"]["query"]["minLength"] == 1
    assert schema["properties"]["top_k"]["minimum"] == 1
    # Schema is closed — LLM cannot smuggle arbitrary keys.
    assert schema["additionalProperties"] is False


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_query_rejects_empty_query():
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_QUERY"):
        await svc.query("", top_k=5, db=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_rejects_whitespace_query():
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_QUERY"):
        await svc.query("   ", top_k=5, db=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_rejects_non_string_query():
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_QUERY"):
        await svc.query(123, top_k=5, db=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_rejects_zero_top_k():
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_TOP_K"):
        await svc.query("x", top_k=0, db=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_rejects_negative_top_k():
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_TOP_K"):
        await svc.query("x", top_k=-3, db=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_rejects_bool_top_k():
    """``True`` is an ``int`` in Python; reject explicitly to keep the
    contract unambiguous."""
    svc = RAGService()
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_TOP_K"):
        await svc.query("x", top_k=True, db=session)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Requirement 5.8 - empty corpus
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_query_returns_empty_when_chunk_embeddings_empty():
    """Requirement 5.8: zero rows in ``chunk_embeddings`` → return ``[]``."""
    svc = RAGService()
    # Even if the embed model would fail, an empty corpus must short-circuit.
    _stub_embedding(svc, [0.1, 0.2, 0.3])

    session = _FakeAsyncSession(empty=True)
    result = await svc.query("hello", top_k=5, db=session)  # type: ignore[arg-type]

    assert result == []
    # Only the empty-check SELECT should have run.
    assert len(session.executed) == 1
    assert "FROM chunk_embeddings LIMIT 1" in session.executed[0][0]


# --------------------------------------------------------------------------- #
# Requirement 5.6 - filtering, ordering, truncation
# --------------------------------------------------------------------------- #


def _make_row(rid: str, sim: float) -> _Row:
    return _Row(
        id=rid,
        category="food",
        title=f"title-{rid}",
        content=f"content-{rid}",
        metadata={"src": rid},
        similarity=sim,
    )


@pytest.mark.asyncio
async def test_query_returns_chunks_above_threshold_sorted_descending():
    """Requirement 5.6: every chunk has similarity ≥ threshold and result
    is ordered by descending similarity."""
    svc = RAGService()
    _stub_embedding(svc, [0.1] * 384)

    threshold = settings.rag_similarity_threshold
    # Mix above-threshold rows in non-monotonic order to exercise the sort.
    session = _FakeAsyncSession(
        rows=[
            _make_row("c1", threshold + 0.10),
            _make_row("c2", threshold + 0.30),
            _make_row("c3", threshold + 0.05),
        ]
    )

    result = await svc.query("phở", top_k=5, db=session)  # type: ignore[arg-type]

    assert [c.id for c in result] == ["c2", "c1", "c3"]
    assert all(c.similarity >= threshold for c in result)


@pytest.mark.asyncio
async def test_query_truncates_to_top_k():
    """Requirement 5.6: ``len(result) ≤ top_k``."""
    svc = RAGService()
    _stub_embedding(svc, [0.1] * 384)

    threshold = settings.rag_similarity_threshold
    session = _FakeAsyncSession(
        rows=[_make_row(f"c{i}", threshold + 0.1 + i * 0.01) for i in range(10)]
    )

    result = await svc.query("q", top_k=3, db=session)  # type: ignore[arg-type]

    assert len(result) == 3
    # Top-3 by similarity descending.
    sims = [c.similarity for c in result]
    assert sims == sorted(sims, reverse=True)


@pytest.mark.asyncio
async def test_query_passes_threshold_and_top_k_to_sql():
    """Both the threshold filter and ``top_k`` must reach the database, so
    pgvector does the heavy lifting and we don't transfer entire tables."""
    svc = RAGService()
    _stub_embedding(svc, [0.5, 0.5])

    session = _FakeAsyncSession(rows=[])
    await svc.query("q", top_k=4, db=session)  # type: ignore[arg-type]

    # Two execute() calls: empty-check, then cosine-similarity.
    assert len(session.executed) == 2
    sql, params = session.executed[1]
    assert "<=>" in sql  # pgvector cosine distance operator
    assert "ORDER BY" in sql
    assert "LIMIT :top_k" in sql
    assert params["top_k"] == 4
    assert params["threshold"] == pytest.approx(settings.rag_similarity_threshold)
    # Embedding serialised as ``[v1,v2]`` for pgvector ``vector`` cast.
    assert params["query_vec"].startswith("[") and params["query_vec"].endswith("]")


@pytest.mark.asyncio
async def test_query_handles_null_metadata():
    """Some legacy chunks may have NULL metadata; coerce to ``{}``."""
    svc = RAGService()
    _stub_embedding(svc, [0.1, 0.2])

    threshold = settings.rag_similarity_threshold
    row_with_null_meta = _Row(
        id="c1",
        category="food",
        title="t",
        content="c",
        metadata=None,  # type: ignore[arg-type]
        similarity=threshold + 0.1,
    )
    session = _FakeAsyncSession(rows=[row_with_null_meta])

    result = await svc.query("q", top_k=1, db=session)  # type: ignore[arg-type]
    assert len(result) == 1
    assert result[0].metadata == {}
