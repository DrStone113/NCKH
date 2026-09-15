from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from services.agent.answer_validators import validate_answer
from services.agent.context_planner import ContextPlanner
from services.agent.cost_governor import limits_for_turn
from services.agent.inference_policy_v2 import (
    DiagonalLinUCBShadow,
    InferenceRoute,
    POLICY_VERSION,
    decide_inference,
)
from services.agent.llm_client import ToolCall
from services.agent.tool_dispatcher import ToolResult
from services.agent.turn_router import classify_turn
from services.backend_optimization import (
    AdaptiveAdmissionController,
    BackendCostMetrics,
    OwnerScopedSnapshotCache,
    PublicSingleFlightCache,
)


def _decision(query: str):
    classification, context_plan = ContextPlanner().create_plan(query)
    turn_plan = classify_turn(query)
    return decide_inference(
        classification,
        context_plan,
        turn_plan,
        limits_for_turn(turn_plan),
    )


def test_inference_policy_is_versioned_and_never_prefetches_writes() -> None:
    decision = _decision("Ghi bữa ăn này vào nhật ký")
    assert decision.policy_version == POLICY_VERSION
    assert all(not name.startswith(("log_", "save_", "create_")) for name in decision.prefetch_tools)
    assert "PERSISTENCE_CONFIRMATION" in decision.validators


def test_shadow_bandit_records_propensity_without_mutating_on_recommend() -> None:
    bandit = DiagonalLinUCBShadow()
    before = {arm: list(values) for arm, values in bandit._b.items()}
    recommendation = bandit.recommend(
        [1.0] * 8,
        allowed_arms=[InferenceRoute.DETERMINISTIC, InferenceRoute.LIGHT_LLM],
    )
    assert sum(recommendation.propensities.values()) == pytest.approx(1.0)
    assert bandit._b == before


def test_validators_block_unsupported_persistence_and_numeric_claims() -> None:
    read = ToolCall("r", "get_today_meals", {})
    outcome = validate_answer(
        "Đã lưu. Tổng hôm nay là 900 kcal.",
        validators=["PERSISTENCE_CONFIRMATION", "NUMERIC_CONSISTENCY"],
        tool_results=[(read, ToolResult(ok=True, data={"total_kcal": 700}))],
    )
    assert outcome.passed is False
    assert set(outcome.failure_codes) == {
        "PERSISTENCE_NOT_CONFIRMED",
        "UNSUPPORTED_NUMERIC_CLAIM",
    }
    assert outcome.correction


@pytest.mark.asyncio
async def test_public_cache_coalesces_concurrent_loads() -> None:
    cache = PublicSingleFlightCache(max_entries=4, ttl_seconds=60)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"public": True}

    results = await asyncio.gather(
        *(cache.get_or_load("wger:categories", loader) for _ in range(8))
    )
    assert calls == 1
    assert results == [{"public": True}] * 8


@pytest.mark.asyncio
async def test_private_snapshot_requires_version_and_invalidates_only_owner_session() -> None:
    cache = OwnerScopedSnapshotCache(ttl_seconds=60)
    assert await cache.set(
        owner="u1", session_id="s1", source="profile", params={}, value={"age": 20}
    ) is False
    for owner, session in (("u1", "s1"), ("u2", "s2")):
        assert await cache.set(
            owner=owner,
            session_id=session,
            source="profile",
            params={},
            value={"updated_at": "2026-09-14T00:00:00Z", "age": 20},
        )
    await cache.invalidate(owner="u1", session_id="s1")
    assert await cache.get(owner="u1", session_id="s1", source="profile", params={}) is None
    assert await cache.get(owner="u2", session_id="s2", source="profile", params={}) is not None


@pytest.mark.asyncio
async def test_admission_reserves_one_slot_for_urgent_safety() -> None:
    controller = AdaptiveAdmissionController(
        minimum=2,
        initial=2,
        maximum=4,
        timeout_seconds=0.1,
        enforce=True,
    )
    q1 = await controller.acquire(priority=2)
    q2 = await controller.acquire(priority=2)
    urgent = await controller.acquire(priority=0, urgent=True)
    assert urgent >= 0
    assert controller.active == 3
    await controller.release(queue_ms=urgent)
    await controller.release(queue_ms=q2)
    await controller.release(queue_ms=q1)


def test_metrics_are_aggregate_and_reject_dynamic_private_labels() -> None:
    metrics = BackendCostMetrics()
    metrics.increment("llm.calls.light_llm")
    metrics.observe("chat.queue_ms", 12.0)
    with pytest.raises(ValueError, match="INVALID_METRIC_KEY"):
        metrics.increment("user:private-id")
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["llm.calls.light_llm"] == 1
    assert snapshot["samples"]["chat.queue_ms"]["p95"] == 12.0
