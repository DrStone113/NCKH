"""Live PostgreSQL gate for P2; deliberately skips without an explicit URL."""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.plan_engine.contracts import (
    PlanDomain,
    PlanLifecycleStatus,
    PlanPatch,
    PlanPatchOperation,
    PlanRequest,
)
from services.plan_engine.engine import MemoryPlanRepository, PlanContextResolver, PlanEngine
from services.plan_engine.persistence import PlanAuthorizationError, PlanPersistenceError, PlanSqlRepository


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


@pytest.mark.asyncio
async def test_live_sql_revision_lifecycle_idempotency_and_cross_owner_denial():
    """Exercise the production repository against PostgreSQL, not a mock."""

    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = PlanSqlRepository(session_factory)
    owner = f"p2-live-matrix-{uuid4()}"
    context = PlanContextResolver.resolve(
        owner,
        {
            "user_id": owner, "age": 31, "equation_sex": "male", "height_cm": 172,
            "weight_kg": 70, "activity_level": "moderate", "health_goal": "maintain",
            "dietary_restrictions": ["no_pork"],
        },
    )
    request = PlanRequest(PlanDomain.NUTRITION, date(2026, 10, 3), date(2026, 10, 3), "Asia/Ho_Chi_Minh")
    planner = PlanEngine(MemoryPlanRepository())
    try:
        original = planner.build_nutrition_plan(context, request)
        saved = await repository.save_exact_revision(
            owner_user_id=owner, revision=original, expected_content_hash=original.revision_content_hash,
            action_id=f"save-{original.revision_id}", activate=False,
        )
        assert saved.lifecycle_status is PlanLifecycleStatus.SAVED
        assert saved.revision_content_hash == original.revision_content_hash

        active = await repository.set_status(
            owner_user_id=owner, plan_id=saved.plan_id, revision_id=saved.revision_id,
            expected_revision_number=1, status=PlanLifecycleStatus.ACTIVE, action_id=f"activate-{saved.revision_id}",
        )
        paused = await repository.set_status(
            owner_user_id=owner, plan_id=saved.plan_id, revision_id=saved.revision_id,
            expected_revision_number=1, status=PlanLifecycleStatus.PAUSED, action_id=f"pause-{saved.revision_id}",
        )
        resumed = await repository.set_status(
            owner_user_id=owner, plan_id=saved.plan_id, revision_id=saved.revision_id,
            expected_revision_number=1, status=PlanLifecycleStatus.ACTIVE, action_id=f"resume-{saved.revision_id}",
        )
        retried_resume = await repository.set_status(
            owner_user_id=owner, plan_id=saved.plan_id, revision_id=saved.revision_id,
            expected_revision_number=1, status=PlanLifecycleStatus.ACTIVE, action_id=f"resume-{saved.revision_id}",
        )
        cancelled = await repository.set_status(
            owner_user_id=owner, plan_id=saved.plan_id, revision_id=saved.revision_id,
            expected_revision_number=1, status=PlanLifecycleStatus.CANCELLED, action_id=f"cancel-{saved.revision_id}",
        )
        assert (active.lifecycle_status, paused.lifecycle_status, resumed.lifecycle_status, cancelled.lifecycle_status) == (
            PlanLifecycleStatus.ACTIVE, PlanLifecycleStatus.PAUSED, PlanLifecycleStatus.ACTIVE, PlanLifecycleStatus.CANCELLED,
        )
        assert retried_resume == resumed

        revised = planner.revise(
            context,
            PlanPatch(
                target_plan_id=original.plan_id, target_revision_id=original.revision_id,
                expected_revision_number=1, operation=PlanPatchOperation.CHANGE_TIME,
                target_item_id=original.items[0].plan_item_id, requested_change={"schedule_slot": "snack"},
                request_source="P2_1_LIVE", reason="live revision matrix",
            ),
        )
        persisted_revision = await repository.save_exact_revision(
            owner_user_id=owner, revision=revised, expected_content_hash=revised.revision_content_hash,
            action_id=f"save-{revised.revision_id}", activate=False,
        )
        assert persisted_revision.revision_number == 2
        assert persisted_revision.parent_revision_id == original.revision_id
        assert persisted_revision.revision_content_hash == revised.revision_content_hash
        assert await repository.get("other-owner", original.plan_id, original.revision_id) is None

        with pytest.raises(PlanPersistenceError, match="PLAN_REVISION_CONFLICT"):
            await repository.set_status(
                owner_user_id=owner, plan_id=original.plan_id, revision_id=revised.revision_id,
                expected_revision_number=1, status=PlanLifecycleStatus.ACTIVE, action_id=f"stale-{revised.revision_id}",
            )
        with pytest.raises(PlanAuthorizationError, match="PLAN_NOT_FOUND"):
            await repository.set_status(
                owner_user_id="other-owner", plan_id=original.plan_id, revision_id=revised.revision_id,
                expected_revision_number=2, status=PlanLifecycleStatus.ACTIVE, action_id=f"foreign-{revised.revision_id}",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_sql_attach_transfer_preserves_logical_items_and_is_idempotent():
    """A standalone menu becomes direct combined content in one SQL transaction."""

    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = PlanSqlRepository(session_factory)
    owner = f"p2-live-attach-{uuid4()}"
    context = PlanContextResolver.resolve(
        owner,
        {
            "user_id": owner, "age": 31, "equation_sex": "male", "height_cm": 172,
            "weight_kg": 70, "activity_level": "moderate", "health_goal": "maintain",
        },
    )
    request = PlanRequest(PlanDomain.NUTRITION, date(2026, 11, 3), date(2026, 11, 3), "Asia/Ho_Chi_Minh")
    source_request = PlanRequest(PlanDomain.NUTRITION, date(2026, 11, 4), date(2026, 11, 4), "Asia/Ho_Chi_Minh")
    planner = PlanEngine(MemoryPlanRepository())
    try:
        standalone = planner.build_nutrition_plan(context, source_request)
        standalone_saved = await repository.save_exact_revision(
            owner_user_id=owner, revision=standalone,
            expected_content_hash=standalone.revision_content_hash,
            action_id=f"save-source-{standalone.revision_id}", activate=False,
        )
        combined_component = planner.build_nutrition_plan(context, request)
        combined = planner.build_combined_container(
            context,
            PlanRequest(PlanDomain.COMBINED_HEALTH, date(2026, 11, 3), date(2026, 11, 4), "Asia/Ho_Chi_Minh"),
            (combined_component,),
        )
        combined_saved = await repository.save_exact_revision(
            owner_user_id=owner, revision=combined,
            expected_content_hash=combined.revision_content_hash,
            action_id=f"save-combined-{combined.revision_id}", activate=False,
        )
        action_id = f"attach-{uuid4()}"
        attached = await repository.attach_standalone_to_combined(
            owner_user_id=owner,
            combined_plan_id=combined_saved.plan_id,
            base_revision_id=combined_saved.revision_id,
            expected_combined_content_hash=combined_saved.revision_content_hash,
            source_plan_id=standalone_saved.plan_id,
            source_revision_id=standalone_saved.revision_id,
            expected_source_content_hash=standalone_saved.revision_content_hash,
            action_id=action_id,
            source_surface="MENU_UI",
        )
        retried = await repository.attach_standalone_to_combined(
            owner_user_id=owner,
            combined_plan_id=combined_saved.plan_id,
            base_revision_id=combined_saved.revision_id,
            expected_combined_content_hash=combined_saved.revision_content_hash,
            source_plan_id=standalone_saved.plan_id,
            source_revision_id=standalone_saved.revision_id,
            expected_source_content_hash=standalone_saved.revision_content_hash,
            action_id=action_id,
            source_surface="MENU_UI",
        )
        assert attached.revision_number == 2
        assert retried.revision_id == attached.revision_id
        assert {item.plan_item_id for item in standalone_saved.items}.issubset(
            {item.plan_item_id for item in attached.items}
        )
        source_after = await repository.get(owner, standalone_saved.plan_id, standalone_saved.revision_id)
        assert source_after is not None
        assert source_after.lifecycle_status is PlanLifecycleStatus.SUPERSEDED
    finally:
        await engine.dispose()
