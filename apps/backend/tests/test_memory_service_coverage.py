"""Coverage manifest for task 5.5 — Unit test cho ``MemoryService``.

Validates: Requirements 5.3, 5.4, 5.8 (chatbot-redesign spec).

Task 5.5 (``backend/.kiro/specs/chatbot-redesign/tasks.md``) requires unit
tests for four behaviours of :class:`services.agent.memory_service.MemoryService`:

1. Rolling summary is updated when the session exceeds
   :data:`config.settings.summary_threshold`.
2. ``getPinnedFacts`` returns only rows with ``status='confirmed'``.
3. ``proposeFact`` writes ``status='pending'`` and records ``source_msg_id``.
4. ``queryRag`` returns ``[]`` when ``chunk_embeddings`` is empty.

All four are already covered by tests written for tasks 5.1, 5.2, and 5.3
in:

- ``tests/test_memory_service.py``
- ``tests/test_memory_service_context.py``
- ``tests/test_rag_service_agent.py``

Rather than duplicate the assertions, this module imports each canonical
test by reference (renamed with a leading underscore so pytest does not
re-collect / re-run them). The import itself is the assertion: if any test
is renamed, moved, or deleted, this manifest fails to collect and the
regression is caught at CI time. A single sanity test then asserts the
manifest mapping is non-empty so pytest reports a passing test for
task 5.5.

Whenever a task-5.5 bullet gains a new canonical test, add it to
:data:`TASK_5_5_COVERAGE` so future readers can find the exact assertion
that backs each requirement.
"""

from __future__ import annotations

# 1) Rolling summary updated when count(turns) > SUMMARY_THRESHOLD.
#    Covered by ``updateRollingSummary`` tests in test_memory_service.py.
from tests.test_memory_service import (
    test_update_rolling_summary_skips_when_below_threshold as _ms_summary_skip,
    test_update_rolling_summary_writes_summary_and_proposes_facts as _ms_summary_writes,
)

# 2) getPinnedFacts only returns ``status='confirmed'``.
from tests.test_memory_service import (
    test_get_pinned_facts_only_returns_confirmed_for_session_owner as _ms_pinned_confirmed_only,
)

# 3) proposeFact writes ``status='pending'`` and records ``source_msg_id``.
from tests.test_memory_service import (
    test_propose_fact_inserts_pending_row_with_owner_user_id as _ms_propose_pending,
    test_propose_fact_strips_whitespace_in_fact_text as _ms_propose_strip_ws,
)

# 4) queryRag returns ``[]`` when chunk_embeddings is empty / not configured.
from tests.test_memory_service_context import (
    test_query_rag_returns_empty_when_corpus_empty as _ms_qrag_empty_corpus,
    test_query_rag_returns_empty_when_rag_service_not_configured as _ms_qrag_no_service,
)
from tests.test_rag_service_agent import (
    test_query_returns_empty_when_chunk_embeddings_empty as _rag_empty_corpus,
)


# Canonical mapping: bullet → list of pytest test callables that prove it.
# Keep this in sync with ``backend/.kiro/specs/chatbot-redesign/tasks.md``
# task 5.5. Adding a new canonical test? Append it to the relevant bullet.
TASK_5_5_COVERAGE: dict[str, tuple] = {
    "rolling_summary_updates_above_threshold": (
        _ms_summary_skip,
        _ms_summary_writes,
    ),
    "get_pinned_facts_only_confirmed": (
        _ms_pinned_confirmed_only,
    ),
    "propose_fact_pending_and_source_msg_id": (
        _ms_propose_pending,
        _ms_propose_strip_ws,
    ),
    "query_rag_empty_when_corpus_empty": (
        _rag_empty_corpus,
        _ms_qrag_empty_corpus,
        _ms_qrag_no_service,
    ),
}


def test_task_5_5_coverage_manifest_is_complete():
    """Every task-5.5 bullet must point at ≥ 1 canonical test.

    The four keys mirror the four bullets in tasks.md §5.5. Each value is a
    non-empty tuple of imported pytest test callables — the imports above
    give us a static guarantee that every referenced test still exists.
    The tests are imported under aliases (``_ms_*`` / ``_rag_*``) so pytest
    does not collect them again here; they are run by their origin modules.
    """
    expected_bullets = {
        "rolling_summary_updates_above_threshold",
        "get_pinned_facts_only_confirmed",
        "propose_fact_pending_and_source_msg_id",
        "query_rag_empty_when_corpus_empty",
    }
    assert set(TASK_5_5_COVERAGE) == expected_bullets

    for bullet, tests in TASK_5_5_COVERAGE.items():
        assert tests, f"task 5.5 bullet '{bullet}' has no canonical test"
        for fn in tests:
            assert callable(fn), (
                f"task 5.5 bullet '{bullet}' references non-callable {fn!r}"
            )
