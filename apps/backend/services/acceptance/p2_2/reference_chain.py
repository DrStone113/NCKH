"""Observed preview-to-readback identity evidence for P2.2 development tests."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from services.agent.pending_user_action import PendingUserActionStore
from services.agent.tools import plan_v2
from services.plan_engine.contracts import PlanDomain, PlanRequest
from services.plan_engine.engine import PlanContextResolver, PlanEngine
from services.plan_engine.persistence import PlanSqlRepository


async def exercise_reference_chain(
    repository: PlanSqlRepository,
    *,
    owner_user_id: str,
) -> dict[str, Any]:
    """Execute the real Plan V2 preview/pending/save/read-back chain.

    The returned observations are not a comparator shortcut: every identity
    originates in the product contracts and every persisted value is read back
    from PostgreSQL through the owner-scoped repository.
    """

    context = PlanContextResolver.resolve(
        owner_user_id,
        {
            "user_id": owner_user_id,
            "age": 31,
            "equation_sex": "female",
            "height_cm": 164,
            "weight_kg": 60,
            "activity_level": "moderate",
            "health_goal": "maintain",
            "dietary_restrictions": ["no_pork"],
        },
    )
    preview = PlanEngine().build_nutrition_plan(
        context,
        PlanRequest(
            PlanDomain.NUTRITION,
            date(2026, 11, 3),
            date(2026, 11, 3),
            "Asia/Ho_Chi_Minh",
            request_source="P2_2_REFERENCE_CHAIN",
        ),
    )
    preview_payload = plan_v2._revision_payload(preview)
    pending_store = PendingUserActionStore()
    action = pending_store.create_plan_save_action(
        f"p2-2-reference-session-{uuid4()}",
        owner_user_id=owner_user_id,
        plan_payload=preview_payload,
    )
    if action is None:
        raise AssertionError("PENDING_ACTION_CREATION_FAILED")
    pending_store.put(action)
    claim = pending_store.claim_confirmation(action.session_id, owner_user_id, "yes")
    if claim.status != "CLAIMED" or claim.action is None:
        raise AssertionError(f"PENDING_ACTION_CLAIM_FAILED:{claim.status}")

    pending = PlanEngine().repository.get(owner_user_id, preview.plan_id, preview.revision_id)
    if pending is None:
        raise AssertionError("PENDING_REVISION_NOT_FOUND")
    persisted = await repository.save_exact_revision(
        owner_user_id=owner_user_id,
        revision=pending,
        expected_content_hash=str(action.target_identity["revision_content_hash"]),
        action_id=str(action.tool_arguments["request_id"]),
        activate=False,
    )
    pending_store.complete(claim.action, persisted_reference_id=persisted.revision_id)
    read_back = await repository.get(owner_user_id, persisted.plan_id, persisted.revision_id)
    if read_back is None:
        raise AssertionError("AUTHORITATIVE_READBACK_MISSING")

    identities = {
        "preview": {
            "plan_id": preview.plan_id,
            "revision_id": preview.revision_id,
            "content_hash": preview.revision_content_hash,
        },
        "pending_action": {
            "plan_id": str(action.target_identity["plan_id"]),
            "revision_id": str(action.target_identity["revision_id"]),
            "content_hash": str(action.target_identity["revision_content_hash"]),
        },
        "pending_revision": {
            "plan_id": pending.plan_id,
            "revision_id": pending.revision_id,
            "content_hash": pending.revision_content_hash,
        },
        "persisted": {
            "plan_id": persisted.plan_id,
            "revision_id": persisted.revision_id,
            "content_hash": persisted.revision_content_hash,
        },
        "read_back": {
            "plan_id": read_back.plan_id,
            "revision_id": read_back.revision_id,
            "content_hash": read_back.revision_content_hash,
        },
    }
    plan_ids = {entry["plan_id"] for entry in identities.values()}
    revision_ids = {entry["revision_id"] for entry in identities.values()}
    hashes = {entry["content_hash"] for entry in identities.values()}
    if len(plan_ids) != 1 or len(revision_ids) != 1 or len(hashes) != 1:
        raise AssertionError("REFERENCE_CHAIN_IDENTITY_MISMATCH")
    return {
        "identities": identities,
        "pending_status": pending.lifecycle_status.value,
        "persisted_status": persisted.lifecycle_status.value,
        "read_back_status": read_back.lifecycle_status.value,
        "identity_match": True,
    }


__all__ = ["exercise_reference_chain"]
