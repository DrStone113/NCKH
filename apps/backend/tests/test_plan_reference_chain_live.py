"""Live PostgreSQL proof for Plan V2 preview/pending/persistence identity."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.acceptance.p2_2.reference_chain import exercise_reference_chain
from services.plan_engine.persistence import PlanSqlRepository


_LIVE_URL = os.getenv("PLAN_V2_LIVE_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not _LIVE_URL, reason="PLAN_V2_LIVE_POSTGRES_URL is not configured")


@pytest.mark.asyncio
async def test_preview_pending_persisted_readback_reference_identity_is_exact():
    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    try:
        evidence = await exercise_reference_chain(
            PlanSqlRepository(async_sessionmaker(engine, expire_on_commit=False)),
            owner_user_id=f"p2-2-reference-{uuid4()}",
        )
    finally:
        await engine.dispose()
    assert evidence["identity_match"] is True
    assert evidence["pending_status"] == "PENDING_CONFIRMATION"
    assert evidence["persisted_status"] == "SAVED"
    assert evidence["read_back_status"] == "SAVED"
