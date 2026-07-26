"""
Property-based tests for **Property 6: Idempotent reads**.

Task 4.9 — **Validates: Requirements 2.2**

Requirement 2.2 (``backend/.kiro/specs/chatbot-redesign/requirements.md``):

    WHERE tool có ``idempotent = true``, WHEN tool đó được gọi hai lần liên
    tiếp với cùng ``arguments`` trong cùng ``session_id`` mà không có write
    tool xen giữa, THE Tool_Dispatcher SHALL trả về kết quả ngữ nghĩa giống
    nhau ở cả hai lần gọi.

The five tools registered with ``idempotent=True`` (see design.md §5) are:

    - ``calculate_tdee``           — pure function over a ``UserProfile``.
    - ``suggest_dish``             — deterministic pick from a frozen catalog.
    - ``suggest_workout``          — deterministic pick from a frozen catalog.
    - ``search_food_nutrition``    — fuzzy match (foods) + RAG augmentation.
    - ``query_rag`` (RAGService)   — pgvector cosine search.

Strategy
--------
For each tool we draw random arguments inside its declared input space using
``hypothesis``, call the tool twice in a row, and assert that the two results
are *semantically* identical:

- For tools where every output field is derived deterministically from the
  inputs and from frozen module-level data (``_DISHES``, ``_EXERCISES``,
  ``_FOODS``), the two payloads are byte-for-byte equal — no ``id`` field is
  randomised.
- ``query_rag`` depends on the Postgres + pgvector backend; we mock the
  ``RAGService`` with a stub session that returns the same rows on every
  ``execute()`` call and a stub embedder that always returns the same
  vector. This isolates the property under test (idempotency of the public
  contract) from the live database.

Mocking choice
--------------
``query_rag`` requires a live Postgres + pgvector backend that's not
available in CI; we mock ``RAGService`` with the same fake-session pattern
used by ``tests/test_rag_service_agent.py``. This keeps the property test
hermetic while still exercising the real ``RAGService.query`` contract
(input validation, threshold filtering, ordering, truncation).

A second variant of ``search_food_nutrition`` is exercised both with
``rag_service=None`` (foods-only, fully in-memory) and with a deterministic
fake ``rag_service`` to cover the hybrid path.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Allow ``import services.agent.*`` when pytest is run from the
# ``backend/`` directory (matches the convention used in sibling tests).
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings as app_settings  # noqa: E402
from services.agent.rag_service import RAGService  # noqa: E402
from services.agent.tools.dish import suggest_dish  # noqa: E402
from services.agent.tools.food import search_food_nutrition  # noqa: E402
from services.agent.tools.tdee import (  # noqa: E402
    ACTIVITY_MULTIPLIERS,
    GOAL_ADJUSTMENTS,
    calculate_tdee,
)
from services.agent.tools.workout import (  # noqa: E402
    _VALID_EQUIPMENT,
    _VALID_LEVELS,
    _VALID_MUSCLE_GROUPS,
    suggest_workout,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies — constrained to each tool's declared input domain
# ---------------------------------------------------------------------------

# UserProfile (design.md §6.1) — bounds match models.schemas.UserProfile.
_user_profile_strategy = st.fixed_dictionaries(
    {
        "user_id": st.text(min_size=1, max_size=20),
        "age": st.integers(min_value=10, max_value=120),
        "gender": st.sampled_from(["male", "female"]),
        "height_cm": st.floats(
            min_value=100.0,
            max_value=250.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        "weight_kg": st.floats(
            min_value=30.0,
            max_value=300.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        "activity_level": st.sampled_from(sorted(ACTIVITY_MULTIPLIERS.keys())),
        "health_goal": st.sampled_from(sorted(GOAL_ADJUSTMENTS.keys())),
    }
)

# suggest_dish strategies — same shape as test_suggest_dish_pbt.py.
_MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
_RESTRICTIONS = (
    "vegetarian",
    "vegan",
    "low_carb",
    "high_protein",
    "no_seafood",
)
_meal_type_strategy = st.sampled_from(_MEAL_TYPES)
_target_kcal_strategy = st.floats(
    min_value=50.0,
    max_value=5000.0,
    allow_nan=False,
    allow_infinity=False,
)
_restrictions_strategy = st.lists(
    st.sampled_from(_RESTRICTIONS),
    unique=True,
    min_size=0,
    max_size=len(_RESTRICTIONS),
)
_recent_ids_strategy = st.lists(
    st.integers(min_value=1, max_value=500),
    unique=True,
    min_size=0,
    max_size=6,
)

# suggest_workout strategies — same shape as test_suggest_workout_pbt.py.
_muscle_group_strategy = st.sampled_from(sorted(_VALID_MUSCLE_GROUPS))
_equipment_strategy = st.sampled_from(sorted(_VALID_EQUIPMENT))
_level_strategy = st.sampled_from(sorted(_VALID_LEVELS))
_duration_strategy = st.integers(min_value=10, max_value=120)
_fatigue_strategy = st.one_of(
    st.none(),
    st.sampled_from(["low", "moderate", "high", "very_high"]),
)

# search_food_nutrition / query_rag — non-empty queries, sane top_k.
_query_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"),  # exclude surrogates / control chars
    ),
    min_size=1,
    max_size=30,
).map(str.strip).filter(lambda s: len(s) >= 1)
_top_k_strategy = st.integers(min_value=1, max_value=10)


def _run(coro):
    """Execute an async coroutine in a fresh event loop (consistent with the
    sibling tests in ``test_search_food_nutrition.py``)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Property 6.a — calculate_tdee is idempotent
# ---------------------------------------------------------------------------


@given(profile=_user_profile_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_calculate_tdee_idempotent(profile: dict) -> None:
    """``calculate_tdee`` returns identical ``{bmr, tdee, daily_kcal}`` for
    two consecutive calls with the same profile.

    Validates Requirements 2.2 for the ``calculate_tdee`` server tool.
    """
    a = calculate_tdee(profile)
    b = calculate_tdee(profile)
    assert a == b
    # Sanity: the keys promised by the contract are present.
    assert set(a.keys()) == {"bmr", "tdee", "daily_kcal"}


# ---------------------------------------------------------------------------
# Property 6.b — suggest_dish is idempotent
# ---------------------------------------------------------------------------


def _normalise_dish(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a dish payload for semantic comparison.

    The catalog ``id`` happens to be deterministic in the current
    implementation, so we keep it in the comparison; this also catches a
    regression where the picked dish drifts between calls. The surrounding
    fields (``components`` ordering, ``meal_types`` ordering) are already
    deterministic in the producer, so direct equality is the right test.
    """
    return payload


@given(
    meal_type=_meal_type_strategy,
    target_kcal=_target_kcal_strategy,
    dietary_restrictions=_restrictions_strategy,
    recent_dish_ids=_recent_ids_strategy,
)
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_suggest_dish_idempotent(
    meal_type: str,
    target_kcal: float,
    dietary_restrictions: list[str],
    recent_dish_ids: list[int],
) -> None:
    """Two consecutive calls with the same args return the same dish payload.

    Validates Requirements 2.2 for ``suggest_dish``. Some restriction
    combinations admit no dish (``NO_DISH_FOUND``); we ``assume(False)`` in
    that case so Hypothesis treats it as a filter, not a failure.
    """
    try:
        first = suggest_dish(
            meal_type=meal_type,
            target_kcal=target_kcal,
            dietary_restrictions=dietary_restrictions,
            recent_dish_ids=recent_dish_ids,
        )
    except ValueError as exc:
        if str(exc) == "NO_DISH_FOUND":
            assume(False)
        raise

    second = suggest_dish(
        meal_type=meal_type,
        target_kcal=target_kcal,
        dietary_restrictions=dietary_restrictions,
        recent_dish_ids=recent_dish_ids,
    )

    assert _normalise_dish(first) == _normalise_dish(second)


# ---------------------------------------------------------------------------
# Property 6.c — suggest_workout is idempotent
# ---------------------------------------------------------------------------


@given(
    muscle_group=_muscle_group_strategy,
    duration_min=_duration_strategy,
    equipment=_equipment_strategy,
    level=_level_strategy,
    fatigue=_fatigue_strategy,
)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_suggest_workout_idempotent(
    muscle_group: str,
    duration_min: int,
    equipment: str,
    level: str,
    fatigue: str | None,
) -> None:
    """Two consecutive calls with the same args return the same workout plan.

    Validates Requirements 2.2 for ``suggest_workout``. Some
    ``muscle_group × equipment × level`` combinations have fewer than two
    candidate exercises in the dataset; the tool raises
    ``NO_EXERCISES_FOUND`` and we filter those examples out.
    """
    user_state = None if fatigue is None else {"fatigue_level": fatigue}

    def _call() -> dict[str, Any]:
        return suggest_workout(
            muscle_group=muscle_group,
            duration_min=duration_min,
            equipment=equipment,
            level=level,
            user_state=user_state,
        )

    try:
        first = _call()
    except ValueError as exc:
        if str(exc) == "NO_EXERCISES_FOUND":
            assume(False)
        raise

    second = _call()
    assert first == second


# ---------------------------------------------------------------------------
# Property 6.d — search_food_nutrition (foods-only) is idempotent
# ---------------------------------------------------------------------------


@given(query=_query_strategy, top_k=_top_k_strategy)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_search_food_nutrition_foods_only_idempotent(
    query: str, top_k: int
) -> None:
    """Without a RAG service, two calls return identical foods blocks.

    Validates Requirements 2.2 for ``search_food_nutrition`` on the
    deterministic in-memory path.
    """
    a = _run(search_food_nutrition(query, top_k=top_k))
    b = _run(search_food_nutrition(query, top_k=top_k))
    assert a == b


# ---------------------------------------------------------------------------
# Property 6.e — search_food_nutrition (with deterministic RAG) is idempotent
# ---------------------------------------------------------------------------


class _DeterministicRagService:
    """Stand-in RAG service that always returns the same chunks.

    Mirrors the public surface of :class:`RAGService` (``async query``) so
    the tool's RAG branch is exercised, but the result is fully deterministic
    so we can assert byte-for-byte equality across two calls.
    """

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        # Deep-copied per call so the consumer cannot accidentally mutate
        # the shared list and inadvertently cause a "false idempotency" pass.
        self._chunks = chunks

    async def query(self, query: str, top_k: int) -> list[dict[str, Any]]:
        # Return a fresh copy on every call so accidental mutation by the
        # consumer doesn't make the second call see different data.
        return [dict(c) for c in self._chunks]


@given(query=_query_strategy, top_k=_top_k_strategy)
@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
def test_search_food_nutrition_with_rag_idempotent(
    query: str, top_k: int
) -> None:
    """With a deterministic RAG service, two calls return identical hybrid
    payloads (foods block + RAG block).

    Validates Requirements 2.2 for ``search_food_nutrition`` on the hybrid
    path; pins down that the per-call RAG augmentation is repeatable.
    """
    chunks = [
        {
            "id": "k1",
            "category": "nutrition",
            "title": "Salmon basics",
            "content": "Salmon is rich in omega-3.",
            "metadata": {"src": "test"},
            "similarity": 0.85,
        },
        {
            "id": "k2",
            "category": "nutrition",
            "title": "Rice basics",
            "content": "Brown rice has more fiber than white.",
            "metadata": {},
            "similarity": 0.72,
        },
    ]
    rag = _DeterministicRagService(chunks)

    a = _run(search_food_nutrition(query, rag_service=rag, top_k=top_k))
    b = _run(search_food_nutrition(query, rag_service=rag, top_k=top_k))
    assert a == b


# ---------------------------------------------------------------------------
# Property 6.f — query_rag is idempotent (RAGService.query, mocked DB)
# ---------------------------------------------------------------------------
#
# Documentation: ``query_rag`` ultimately depends on Postgres + pgvector,
# which is not available in this test environment. We mock the AsyncSession
# (returning the same rows on every call) and stub the embedding function so
# the property under test is the public contract of ``RAGService.query``:
# given identical inputs and identical underlying state, two consecutive
# calls return identical results.


@dataclass
class _Row:
    """Minimal stand-in for a SQLAlchemy ``Row`` exposing attribute access."""

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
    """Stub session returning a fixed set of rows for the cosine-similarity
    query and a non-null first row for the empty-check.

    This is structurally identical to the helper in
    ``tests/test_rag_service_agent.py`` and the mock-choice trade-off is
    documented at the top of this file.
    """

    rows: list[_Row] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None):
        sql = str(statement)
        if "FROM chunk_embeddings LIMIT 1" in sql:
            # Treat the corpus as non-empty so we exercise the full code path.
            return _FakeResult(first_row=(1,))
        return _FakeResult(rows=list(self.rows))


def _make_row(rid: str, sim: float) -> _Row:
    return _Row(
        id=rid,
        category="food",
        title=f"title-{rid}",
        content=f"content-{rid}",
        metadata={"src": rid},
        similarity=sim,
    )


def _stub_embedding(svc: RAGService, vec: list[float]) -> None:
    svc.embed = lambda _q: vec  # type: ignore[assignment]


@given(query=_query_strategy, top_k=_top_k_strategy)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_query_rag_idempotent_with_mocked_db(query: str, top_k: int) -> None:
    """Two consecutive calls to ``RAGService.query`` with the same args and
    the same underlying state return identical chunk lists.

    Validates Requirements 2.2 for ``query_rag``. The DB layer is mocked
    (``_FakeAsyncSession``) and the embedding function is stubbed; this
    documents what idempotency means at the public-contract level when the
    DB state and embedding model are held constant between calls.
    """
    threshold = app_settings.rag_similarity_threshold
    rows = [
        _make_row("c1", threshold + 0.30),
        _make_row("c2", threshold + 0.10),
        _make_row("c3", threshold + 0.05),
    ]

    svc = RAGService()
    _stub_embedding(svc, [0.1, 0.2, 0.3])

    session_a = _FakeAsyncSession(rows=list(rows))
    session_b = _FakeAsyncSession(rows=list(rows))

    a = _run(svc.query(query, top_k=top_k, db=session_a))  # type: ignore[arg-type]
    b = _run(svc.query(query, top_k=top_k, db=session_b))  # type: ignore[arg-type]

    # Compare semantically: ``KnowledgeChunk`` is a Pydantic model, so equal
    # field values imply equal models.
    assert a == b

    # Sanity: ``len(result) ≤ top_k`` and the threshold filter held.
    assert len(a) <= top_k
    for chunk in a:
        assert chunk.similarity >= threshold


# ---------------------------------------------------------------------------
# Concrete examples (regression anchors)
# ---------------------------------------------------------------------------
#
# Hypothesis is good at finding minimal counter-examples, but a few
# deterministic example-based assertions document the property in plain
# English and keep the suite useful even when shrinking shrinks an example
# down to nothing.


def test_calculate_tdee_idempotent_concrete_example() -> None:
    profile = {
        "user_id": "u1",
        "age": 30,
        "gender": "male",
        "height_cm": 175.0,
        "weight_kg": 70.0,
        "activity_level": "moderate",
        "health_goal": "maintain",
    }
    assert calculate_tdee(profile) == calculate_tdee(profile)


def test_suggest_dish_idempotent_concrete_example() -> None:
    args = dict(
        meal_type="lunch",
        target_kcal=600.0,
        dietary_restrictions=[],
        recent_dish_ids=[],
    )
    assert suggest_dish(**args) == suggest_dish(**args)


def test_suggest_workout_idempotent_concrete_example() -> None:
    args = dict(
        muscle_group="chest",
        duration_min=30,
        equipment="any",
        level="intermediate",
        user_state=None,
    )
    assert suggest_workout(**args) == suggest_workout(**args)


def test_search_food_nutrition_idempotent_concrete_example() -> None:
    a = _run(search_food_nutrition("gạo lứt", top_k=3))
    b = _run(search_food_nutrition("gạo lứt", top_k=3))
    assert a == b
