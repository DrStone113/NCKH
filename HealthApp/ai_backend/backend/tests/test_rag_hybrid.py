"""Tests for hybrid retrieval fusion in :class:`RAGService`.

These cover the pure fusion logic (no DB required). The DB-backed query paths
are exercised by ``test_rag_service_agent.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.agent.rag_service import (
    KEYWORD_WEIGHT,
    RRF_K,
    VECTOR_WEIGHT,
    RAGService,
)


@dataclass
class Row:
    """Minimal stand-in for a SQLAlchemy result row."""

    id: str
    category: str = "food"
    title: str = "t"
    content: str = "c"
    metadata: dict[str, Any] | None = None
    similarity: float = 0.8


def _rows(*ids: str) -> list[Row]:
    return [Row(id=i) for i in ids]


def test_chunk_found_by_both_retrievers_wins():
    """Agreement between retrievers is the strongest signal there is.

    ``b`` is only 2nd in each list but appears in both, so it must outrank
    ``a`` and ``x``, each of which topped exactly one list.
    """
    svc = RAGService()
    dense = _rows("a", "b", "c")
    sparse = _rows("x", "b", "y")

    result = svc._fuse(dense, sparse, top_k=3)

    assert result[0].id == "b"


def test_fusion_respects_top_k():
    svc = RAGService()
    result = svc._fuse(_rows("a", "b", "c", "d"), _rows("e", "f"), top_k=2)
    assert len(result) == 2


def test_keyword_only_hit_still_surfaces():
    """A dish name the embedding smeared away must still be retrievable."""
    svc = RAGService()
    result = svc._fuse(_rows("a"), _rows("bun-bo-hue"), top_k=5)
    assert "bun-bo-hue" in {c.id for c in result}


def test_vector_outranks_keyword_at_equal_rank():
    """With the configured weights, dense wins a head-to-head tie."""
    assert VECTOR_WEIGHT > KEYWORD_WEIGHT
    svc = RAGService()
    result = svc._fuse(_rows("dense-top"), _rows("sparse-top"), top_k=2)
    assert result[0].id == "dense-top"


def test_dense_similarity_is_preserved_for_dense_hits():
    svc = RAGService()
    dense = [Row(id="a", similarity=0.91)]
    result = svc._fuse(dense, _rows("z"), top_k=2)
    by_id = {c.id: c for c in result}
    assert by_id["a"].similarity == pytest.approx(0.91)


def test_rrf_k_matches_published_default():
    """Guard against someone tuning this to a value that flattens ranking."""
    assert RRF_K == 60


@pytest.mark.asyncio
async def test_keyword_probe_is_cached():
    """The information_schema probe must not run on every single query."""
    svc = RAGService()
    calls = 0

    class FakeResult:
        def first(self):
            return (1,)

    class FakeDB:
        async def execute(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResult()

    db = FakeDB()
    assert await svc._has_keyword_index(db) is True
    assert await svc._has_keyword_index(db) is True
    assert calls == 1


@pytest.mark.asyncio
async def test_missing_search_vector_column_degrades_quietly():
    """Before migration 002 runs, hybrid search must fall back, not crash."""
    svc = RAGService()

    class FakeResult:
        def first(self):
            return None

    class FakeDB:
        async def execute(self, *args, **kwargs):
            return FakeResult()

    assert await svc._has_keyword_index(FakeDB()) is False
