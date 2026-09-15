"""Unit tests for ``services.agent.tools.food.search_food_nutrition``.

Validates Requirements 4.8 and 7.8 from
``backend/.kiro/specs/chatbot-redesign/requirements.md``:

- 4.8 / 5.6: hybrid retrieval — fuzzy match against ``vietnamese_foods.json``
  plus optional RAG chunks via ``MemoryService.queryRag`` / ``RAGService``.
- 7.8: data files loaded once at module import (verified indirectly via the
  module-level ``_FOODS`` tuple being non-empty).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

# Allow running ``pytest`` from the ``backend/`` directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tool_registry import ToolDescriptor, ToolRegistry  # noqa: E402
from services.agent.tools.food import (  # noqa: E402
    TOOL_DESCRIPTOR,
    _FOODS,
    search_food_nutrition,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRagService:
    """Stand-in for ``RAGService`` (task 4.8) — exposes ``async query``."""

    def __init__(self, chunks=None, raise_exc=None):
        self._chunks = chunks or []
        self._raise = raise_exc
        self.calls: list[tuple[str, int]] = []

    async def query(self, query: str, top_k: int):
        self.calls.append((query, top_k))
        if self._raise is not None:
            raise self._raise
        return list(self._chunks)


class _FakeMemoryService:
    """Stand-in for ``MemoryService`` (task 5.3) — exposes ``async queryRag``."""

    def __init__(self, chunks=None):
        self._chunks = chunks or []
        self.calls: list[tuple[str, int]] = []

    async def queryRag(self, query: str, top_k: int):
        self.calls.append((query, top_k))
        return list(self._chunks)


def _chunk(
    *, id_: str, similarity: float, title: str = "", content: str = ""
) -> dict[str, Any]:
    return {
        "id": id_,
        "category": "nutrition",
        "title": title,
        "content": content,
        "metadata": {},
        "similarity": similarity,
    }


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Foundation
# ---------------------------------------------------------------------------


def test_foods_loaded_at_import_time():
    """Requirement 7.8: data file is loaded eagerly, at least once."""
    assert len(_FOODS) > 0
    # Sanity: the bundled file ships with hundreds of entries.
    assert len(_FOODS) >= 100


def test_descriptor_metadata():
    assert isinstance(TOOL_DESCRIPTOR, ToolDescriptor)
    assert TOOL_DESCRIPTOR.name == "search_food_nutrition"
    assert TOOL_DESCRIPTOR.side == "server"
    assert TOOL_DESCRIPTOR.idempotent is True
    assert TOOL_DESCRIPTOR.fn is search_food_nutrition


def test_descriptor_can_be_registered():
    registry = ToolRegistry()
    registry.register(TOOL_DESCRIPTOR)
    assert "search_food_nutrition" in registry
    schemas = registry.schemas()
    fn_schema = next(
        s for s in schemas if s["function"]["name"] == "search_food_nutrition"
    )
    assert "query" in fn_schema["function"]["parameters"]["properties"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 123, [], {}])
def test_invalid_query_raises(bad):
    with pytest.raises(ValueError, match="INVALID_QUERY"):
        _run(search_food_nutrition(bad))


@pytest.mark.parametrize("bad", [0, -1, 1.5, "5", True, False])
def test_invalid_top_k_raises(bad):
    with pytest.raises(ValueError, match="INVALID_TOP_K"):
        _run(search_food_nutrition("gạo", top_k=bad))


# ---------------------------------------------------------------------------
# Foods-only path (rag_service=None)
# ---------------------------------------------------------------------------


def test_foods_only_returns_matches_for_vietnamese_query():
    result = _run(search_food_nutrition("gạo lứt", top_k=3))
    assert all(entry["source"] == "foods" for entry in result)
    assert len(result) >= 1
    # The exact entry "Gạo lứt" should be present.
    names = [entry["name"] for entry in result]
    assert any(name == "Gạo lứt" for name in names)


def test_foods_only_works_without_diacritics():
    """Accent-stripped queries still match accented entries."""
    result = _run(search_food_nutrition("gao lut", top_k=3))
    names = [entry["name"] for entry in result]
    assert any("lứt" in name.lower() or "lut" in name.lower() for name in names)


def test_foods_only_matches_english_name():
    """``name_en`` is searchable too."""
    result = _run(search_food_nutrition("brown rice", top_k=3))
    assert len(result) >= 1
    assert all(entry["source"] == "foods" for entry in result)


def test_foods_results_sorted_by_score_desc():
    result = _run(search_food_nutrition("gạo", top_k=5))
    scores = [entry["score"] for entry in result]
    assert scores == sorted(scores, reverse=True)


def test_foods_only_no_rag_block_when_service_missing():
    result = _run(search_food_nutrition("cá hồi", top_k=2))
    assert all(entry["source"] == "foods" for entry in result)


def test_foods_block_truncated_to_top_k():
    result = _run(search_food_nutrition("gạo", top_k=2))
    assert sum(1 for entry in result if entry["source"] == "foods") <= 2


def test_idempotent_same_args_same_result():
    """Requirement 2.2 (idempotent reads) — two calls produce identical foods
    blocks. Verified semantically: same names, same scores, same order."""
    a = _run(search_food_nutrition("cá", top_k=4))
    b = _run(search_food_nutrition("cá", top_k=4))
    foods_a = [e for e in a if e["source"] == "foods"]
    foods_b = [e for e in b if e["source"] == "foods"]
    assert foods_a == foods_b


def test_query_with_no_match_returns_empty():
    """A query that matches nothing in the foods table returns an empty list
    when no RAG service is supplied."""
    result = _run(search_food_nutrition("zzzzzzzzzzzzz", top_k=3))
    assert result == []


def test_unrelated_dish_name_does_not_return_weak_ingredient_matches():
    result = _run(search_food_nutrition("pizza", top_k=5))

    assert result == []


# ---------------------------------------------------------------------------
# RAG augmentation
# ---------------------------------------------------------------------------


def test_rag_chunks_appended_after_foods_block():
    rag = _FakeRagService(
        chunks=[
            _chunk(id_="c1", similarity=0.8, title="Salmon nutrition"),
            _chunk(id_="c2", similarity=0.7, title="Omega-3"),
        ]
    )
    result = _run(
        search_food_nutrition("cá hồi", rag_service=rag, top_k=3)
    )
    sources = [entry["source"] for entry in result]
    # Foods entries come first, RAG entries after.
    if "foods" in sources and "rag" in sources:
        first_rag = sources.index("rag")
        last_food = max(i for i, s in enumerate(sources) if s == "foods")
        assert last_food < first_rag

    rag_entries = [e for e in result if e["source"] == "rag"]
    assert [e["id"] for e in rag_entries] == ["c1", "c2"]
    assert rag.calls == [("cá hồi", 3)]


def test_rag_block_sorted_by_score_desc_even_if_upstream_unsorted():
    rag = _FakeRagService(
        chunks=[
            _chunk(id_="low", similarity=0.5),
            _chunk(id_="high", similarity=0.9),
            _chunk(id_="mid", similarity=0.7),
        ]
    )
    result = _run(
        search_food_nutrition("cá", rag_service=rag, top_k=3)
    )
    rag_entries = [e for e in result if e["source"] == "rag"]
    assert [e["id"] for e in rag_entries] == ["high", "mid", "low"]


def test_rag_block_truncated_to_top_k():
    rag = _FakeRagService(
        chunks=[_chunk(id_=f"c{i}", similarity=0.9 - i * 0.05) for i in range(10)]
    )
    result = _run(
        search_food_nutrition("cá", rag_service=rag, top_k=2)
    )
    rag_entries = [e for e in result if e["source"] == "rag"]
    assert len(rag_entries) <= 2


def test_memory_service_querying_supported():
    """``MemoryService.queryRag`` is preferred when present."""
    mem = _FakeMemoryService(
        chunks=[_chunk(id_="m1", similarity=0.8)]
    )
    result = _run(
        search_food_nutrition("gạo", rag_service=mem, top_k=2)
    )
    assert mem.calls == [("gạo", 2)]
    assert any(e["source"] == "rag" and e["id"] == "m1" for e in result)


def test_rag_service_with_no_query_method_silently_degrades():
    class _Useless:
        pass

    result = _run(
        search_food_nutrition("gạo", rag_service=_Useless(), top_k=2)
    )
    assert all(entry["source"] == "foods" for entry in result)


def test_rag_service_exception_silently_degrades():
    rag = _FakeRagService(raise_exc=RuntimeError("vector backend down"))
    result = _run(
        search_food_nutrition("gạo", rag_service=rag, top_k=2)
    )
    assert all(entry["source"] == "foods" for entry in result)


def test_rag_service_returns_empty_keeps_foods_only():
    rag = _FakeRagService(chunks=[])
    result = _run(
        search_food_nutrition("gạo", rag_service=rag, top_k=2)
    )
    assert all(entry["source"] == "foods" for entry in result)


def test_rag_chunk_with_missing_id_skipped():
    rag = _FakeRagService(
        chunks=[
            {"similarity": 0.9, "title": "no id here"},  # missing id → skipped
            _chunk(id_="ok", similarity=0.8),
        ]
    )
    result = _run(
        search_food_nutrition("cá", rag_service=rag, top_k=3)
    )
    rag_entries = [e for e in result if e["source"] == "rag"]
    assert [e["id"] for e in rag_entries] == ["ok"]


def test_rag_pydantic_like_chunk_supported():
    """Object-style chunks (e.g. Pydantic ``KnowledgeChunk``) work too."""

    class _ChunkObj:
        id = "obj1"
        category = "nutrition"
        title = "objA"
        content = "..."
        metadata = {"src": "test"}
        similarity = 0.75

    rag = _FakeRagService(chunks=[_ChunkObj()])
    result = _run(
        search_food_nutrition("cá", rag_service=rag, top_k=2)
    )
    rag_entries = [e for e in result if e["source"] == "rag"]
    assert len(rag_entries) == 1
    assert rag_entries[0]["id"] == "obj1"
    assert rag_entries[0]["metadata"] == {"src": "test"}
    assert rag_entries[0]["score"] == pytest.approx(0.75)
