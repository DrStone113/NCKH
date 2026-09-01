"""Live PostgreSQL gate for P2; deliberately skips without an explicit URL."""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.plan_engine.contracts import PlanDomain, PlanLifecycleStatus, PlanRequest
from services.plan_engine.engine import MemoryPlanRepository, PlanContextResolver, PlanEngine
from services.plan_engine.persistence import PlanSqlRepository


_LIVE_URL = os.getenv("PLAN_V2_LIVE_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not _LIVE_URL, reason="PLAN_V2_LIVE_POSTGRES_URL is not configured")


@pytest.mark.asyncio
async def test_live_sql_save_readback_idempotency_and_owner_boundary():
    """Requires migrations 010–013 applied to a disposable PostgreSQL DB."""

    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = PlanSqlRepository(session_factory)
    owner = "p2-live-test-owner"
    context = PlanContextResolver.resolve(
        owner,
        {
            "user_id": owner, "age": 31, "equation_sex": "male", "height_cm": 172,
            "weight_kg": 70, "activity_level": "moderate", "health_goal": "maintain",
            "dietary_restrictions": ["no_pork"],
        },
    )
    try:
        preview = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(
            context,
            PlanRequest(PlanDomain.NUTRITION, date(2026, 10, 1), date(2026, 10, 1), "Asia/Ho_Chi_Minh"),
        )
        saved = await repository.save_exact_revision(
            owner_user_id=owner, revision=preview, expected_content_hash=preview.revision_content_hash,
            action_id=f"p2-live-save-{preview.revision_id}", activate=False,
        )
        retry = await repository.save_exact_revision(
            owner_user_id=owner, revision=preview, expected_content_hash=preview.revision_content_hash,
            action_id=f"p2-live-save-{preview.revision_id}", activate=False,
        )
        assert saved.lifecycle_status is PlanLifecycleStatus.SAVED
        assert retry.revision_id == saved.revision_id
        assert saved.revision_content_hash == preview.revision_content_hash
        assert await repository.get("different-owner", saved.plan_id, saved.revision_id) is None
    finally:
        await engine.dispose()
