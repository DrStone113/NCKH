"""``search_food_nutrition`` server-side tool.

Looks up Vietnamese food nutrition data, returning a hybrid list that fuses
fuzzy matches from ``data/vietnamese_foods.json`` with top-k semantically
similar chunks pulled from the RAG knowledge base.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §9.6 (``MemoryService.queryRag`` postconditions).
- Requirements 4.8, 7.8 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract
--------
``async search_food_nutrition(query, *, rag_service=None, top_k=5) -> list[dict]``

Returns up to ``2 * top_k`` dict entries, each shaped::

    # source == "foods" — entry pulled from vietnamese_foods.json
    {
        "source": "foods",
        "score": float,                 # fuzzy-match ratio in [0.0, 1.0]
        "name": str,                    # tên tiếng Việt
        "name_en": str | None,
        "ma_so": int | None,
        "energy_kcal": float | None,    # per 100g
        "protein": float | None,        # per 100g
        "fat": float | None,
        "carbohydrates": float | None,
        "fiber": float | None,
    }

    # source == "rag" — entry pulled from MemoryService.queryRag / RAGService
    {
        "source": "rag",
        "score": float,                 # cosine similarity
        "id": str,
        "category": str,
        "title": str,
        "content": str,
        "metadata": dict,
    }

The list is sorted ``foods`` block first (descending fuzzy ratio) followed by
the RAG block (descending similarity). Each block is independently truncated
to ``top_k`` entries so a strong fuzzy match never starves the RAG block.

When ``rag_service`` is ``None`` — or its ``query`` / ``queryRag`` raises any
exception, or returns an empty list — the function silently degrades to the
foods-only result. A failed RAG lookup must never break a chat turn.

Raises ``ValueError`` with one of:

- ``"INVALID_QUERY"``       — ``query`` is not a non-empty string.
- ``"INVALID_TOP_K"``       — ``top_k`` is not a positive integer.

The tool is idempotent: same arguments deterministically produce the same
foods-only result. The RAG block is only as deterministic as the underlying
``rag_service`` (typically deterministic for a given embedding model and DB
state).

Note
----
This module only *defines* :data:`TOOL_DESCRIPTOR`. Registration into the
shared :class:`ToolRegistry` happens centrally in task 12.1
(``register_server_tools``), where the runtime ``rag_service`` instance is
bound via ``functools.partial``. The data file is loaded exactly once at
module import time per Requirement 7.8.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.agent.tool_registry import ToolDescriptor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum fuzzy ratio for a foods-table entry to be considered a match.
#: Below this we drop the entry entirely; this prevents nonsense queries from
#: returning every food in the catalog ranked by trivial substring overlap.
_MIN_FUZZY_SCORE: float = 0.30

#: Default ``top_k`` when the caller leaves it unspecified. Matches
#: ``settings.rag_top_k`` (5).
_DEFAULT_TOP_K: int = 5

#: Hard cap on ``top_k`` — both for foods and RAG — so a runaway LLM call
#: cannot ask for thousands of entries.
_MAX_TOP_K: int = 50


# ---------------------------------------------------------------------------
# JSON Schema — passed to the LLM via ToolRegistry.schemas()
# ---------------------------------------------------------------------------

# Only ``query`` and ``top_k`` are exposed to the LLM. ``rag_service`` is an
# internal injection bound at registration time.
_SEARCH_FOOD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Tên món / nguyên liệu cần tra cứu, ví dụ 'cá hồi', "
                "'gạo lứt', 'salmon'. Hỗ trợ cả tiếng Việt và tiếng Anh."
            ),
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": _MAX_TOP_K,
            "default": _DEFAULT_TOP_K,
            "description": (
                "Số kết quả tối đa cho mỗi nguồn (foods table và RAG). "
                "Tổng kết quả trả về có thể lên tới 2 * top_k."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Data loading (once at import time per Requirement 7.8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _FoodRecord:
    """A pre-resolved entry from ``vietnamese_foods.json`` ready for matching."""

    name: str
    name_en: str | None
    ma_so: int | None
    energy_kcal: float | None
    protein: float | None
    fat: float | None
    carbohydrates: float | None
    fiber: float | None
    # Pre-normalised lowercase / accent-stripped strings for fast matching.
    name_norm: str
    name_en_norm: str


# Computed at module import; treated as immutable thereafter.
_FOODS: tuple[_FoodRecord, ...] = ()


def _data_dir() -> Path:
    # backend/services/agent/tools/food.py → backend/data
    return Path(__file__).resolve().parent.parent.parent.parent / "data"


def _strip_accents(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics for accent-insensitive matching.

    ``"Gạo lứt"`` → ``"gao lut"``. This means a query of ``"gao lut"`` (no
    diacritics — common when typed quickly) still matches ``"Gạo lứt"``.
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_food_record(entry: Mapping[str, Any]) -> _FoodRecord | None:
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name_en = entry.get("name_en")
    if not isinstance(name_en, str) or not name_en.strip():
        name_en = None
    return _FoodRecord(
        name=name.strip(),
        name_en=name_en,
        ma_so=_safe_optional_int(entry.get("ma_so")),
        energy_kcal=_safe_optional_float(entry.get("energy_kcal")),
        protein=_safe_optional_float(entry.get("protein")),
        fat=_safe_optional_float(entry.get("fat")),
        carbohydrates=_safe_optional_float(entry.get("carbohydrates")),
        fiber=_safe_optional_float(entry.get("fiber")),
        name_norm=_strip_accents(name),
        name_en_norm=_strip_accents(name_en) if name_en else "",
    )


def _load_foods() -> tuple[_FoodRecord, ...]:
    path = _data_dir() / "vietnamese_foods.json"
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        logger.error("vietnamese_foods.json not found at %s", path)
        return ()
    except json.JSONDecodeError as exc:
        logger.error("vietnamese_foods.json is not valid JSON: %s", exc)
        return ()

    if not isinstance(raw, list):
        logger.error("vietnamese_foods.json is not a list")
        return ()

    records: list[_FoodRecord] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        rec = _build_food_record(entry)
        if rec is not None:
            records.append(rec)

    logger.info(
        "search_food_nutrition: loaded %d foods from %s", len(records), path.name
    )
    return tuple(records)


# Eagerly load at import time. ``_FOODS`` is treated as immutable.
_FOODS = _load_foods()


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def _fuzzy_score(query_norm: str, candidate_norm: str) -> float:
    """Return a [0.0, 1.0] match score for ``candidate_norm`` against ``query_norm``.

    Uses ``SequenceMatcher.ratio()`` as the base, then boosts substring hits:
    a query that is a contained substring of the candidate (e.g. ``"ga"`` in
    ``"gao lut"``) gets a floor of ``0.6`` so the LLM still sees obvious
    matches even when the strings differ in length.
    """
    if not query_norm or not candidate_norm:
        return 0.0
    base = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    if query_norm in candidate_norm or candidate_norm in query_norm:
        base = max(base, 0.6)
    return base


def _match_food(query_norm: str, record: _FoodRecord) -> float:
    """Score a single :class:`_FoodRecord` against a normalised query.

    Considers the Vietnamese ``name`` and English ``name_en``; returns the
    higher of the two ratios.
    """
    score_vn = _fuzzy_score(query_norm, record.name_norm)
    score_en = (
        _fuzzy_score(query_norm, record.name_en_norm)
        if record.name_en_norm
        else 0.0
    )
    return max(score_vn, score_en)


def _foods_payload(record: _FoodRecord, score: float) -> dict[str, Any]:
    return {
        "source": "foods",
        "score": round(score, 4),
        "name": record.name,
        "name_en": record.name_en,
        "ma_so": record.ma_so,
        "energy_kcal": record.energy_kcal,
        "protein": record.protein,
        "fat": record.fat,
        "carbohydrates": record.carbohydrates,
        "fiber": record.fiber,
    }


def _search_foods(query: str, top_k: int) -> list[dict[str, Any]]:
    """Return up to ``top_k`` foods matches for ``query``, ranked by score."""
    query_norm = _strip_accents(query)
    if not query_norm:
        return []

    scored: list[tuple[float, int, _FoodRecord]] = []
    for idx, rec in enumerate(_FOODS):
        score = _match_food(query_norm, rec)
        if score >= _MIN_FUZZY_SCORE:
            # Stable tiebreak: original catalog order (idx ascending).
            scored.append((score, idx, rec))

    # Sort by score DESC, idx ASC → deterministic ordering.
    scored.sort(key=lambda triple: (-triple[0], triple[1]))
    return [_foods_payload(rec, score) for score, _, rec in scored[:top_k]]


# ---------------------------------------------------------------------------
# RAG augmentation
# ---------------------------------------------------------------------------


async def _query_rag(
    rag_service: Any, query: str, top_k: int, db: Any = None
) -> list[Any]:
    """Invoke the duck-typed ``rag_service``.

    Supports both:

    - :class:`services.agent.rag_service.RAGService` (task 4.8) — exposes
      ``async query(query, top_k)``.
    - :class:`services.agent.memory_service.MemoryService` (task 5.3) —
      exposes ``async queryRag(query, top_k)``.

    Any exception is logged and converted to an empty list so a flaky vector
    backend never breaks the chat turn.
    """
    method = None
    matched_attr = None
    for attr in ("queryRag", "query"):
        candidate = getattr(rag_service, attr, None)
        if callable(candidate):
            method = candidate
            matched_attr = attr
            break
    if method is None:
        logger.warning(
            "search_food_nutrition: rag_service has no queryRag/query method"
        )
        return []

    try:
        if matched_attr == "query" and db is not None:
            result = await method(query, top_k, db=db)
        else:
            result = await method(query, top_k)
    except Exception as exc:  # pragma: no cover - exercised in tests
        logger.warning("search_food_nutrition: RAG lookup failed: %s", exc)
        return []

    if not result:
        return []
    if not isinstance(result, Sequence):
        logger.warning(
            "search_food_nutrition: RAG returned non-sequence %r", type(result)
        )
        return []
    return list(result)


def _chunk_payload(chunk: Any) -> dict[str, Any] | None:
    """Coerce a ``KnowledgeChunk``-like object (Pydantic model OR dict) into
    a uniform dict payload, or return ``None`` on shape mismatch."""

    def _read(name: str) -> Any:
        if isinstance(chunk, Mapping):
            return chunk.get(name)
        return getattr(chunk, name, None)

    similarity = _read("similarity")
    try:
        similarity_f = float(similarity) if similarity is not None else 0.0
    except (TypeError, ValueError):
        similarity_f = 0.0

    chunk_id = _read("id")
    if chunk_id is None:
        return None

    return {
        "source": "rag",
        "score": round(similarity_f, 4),
        "id": str(chunk_id),
        "category": str(_read("category") or ""),
        "title": str(_read("title") or ""),
        "content": str(_read("content") or ""),
        "metadata": dict(_read("metadata") or {}),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search_food_nutrition(
    query: str,
    *,
    rag_service: Any = None,
    top_k: int = _DEFAULT_TOP_K,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Search Vietnamese foods + RAG knowledge for ``query``.

    Parameters
    ----------
    query:
        Free-text food / ingredient query. Must be a non-empty string.
    rag_service:
        Optional duck-typed RAG service. Must expose either
        ``async queryRag(query, top_k)`` or ``async query(query, top_k)``
        returning ``KnowledgeChunk``-like objects (Pydantic models or dicts
        with at least ``id``, ``similarity``). When ``None`` or unusable,
        the result contains foods entries only.
    top_k:
        Per-source cap. The returned list contains ``≤ top_k`` foods entries
        followed by ``≤ top_k`` RAG entries.
    db:
        Optional database session context passed to the RAG query.

    Returns
    -------
    list[dict]
        See module docstring for the entry shape. May be empty when no
        foods match and RAG is unavailable / returns nothing.

    Raises
    ------
    ValueError
        ``"INVALID_QUERY"`` or ``"INVALID_TOP_K"``.
    """
    # ---- input validation --------------------------------------------------
    if not isinstance(query, str) or not query.strip():
        raise ValueError("INVALID_QUERY")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("INVALID_TOP_K")
    top_k = min(top_k, _MAX_TOP_K)

    foods_block = _search_foods(query, top_k)

    rag_block: list[dict[str, Any]] = []
    if rag_service is not None:
        chunks = await _query_rag(rag_service, query, top_k, db=db)
        for chunk in chunks:
            payload = _chunk_payload(chunk)
            if payload is not None:
                rag_block.append(payload)
        # Defensive: ensure the RAG block is sorted by score DESC even if
        # the upstream service forgot to. design.md §9.6 promises descending
        # similarity, but we don't want a single misbehaving service to
        # break the public contract of this tool.
        rag_block.sort(key=lambda entry: -entry["score"])
        rag_block = rag_block[:top_k]

    return foods_block + rag_block


# ---------------------------------------------------------------------------
# Descriptor — consumed by ``register_server_tools`` (task 12.1)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="search_food_nutrition",
    description=(
        "Tra cứu dinh dưỡng món Việt: ghép kết quả fuzzy match từ "
        "vietnamese_foods.json với top-k chunk RAG có similarity ≥ "
        "RAG_SIMILARITY_THRESHOLD. Trả về danh sách entries với field "
        "`source` ∈ {'foods', 'rag'}."
    ),
    parameters_schema=_SEARCH_FOOD_SCHEMA,
    side="server",
    fn=search_food_nutrition,
    idempotent=True,
)


__all__ = [
    "TOOL_DESCRIPTOR",
    "search_food_nutrition",
]
