"""Authenticated authoritative HTTP surface for persisted Plan V2 revisions.

The legacy ``/plans`` routes continue to serve legacy plan records.  This
router deliberately does not blend the two stores: every read and lifecycle
write below goes through :class:`PlanSqlRepository` and uses the bearer
principal as the only owner identity.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.agent.tools import plan_v2
from services.auth import AuthenticatedPrincipal, require_authenticated_principal
from services.plan_engine.contracts import PlanDomain, PlanLifecycleStatus, PlanRevision
from services.plan_engine.engine import PlanEngine
from services.plan_engine.lifecycle import valid_targets
from services.plan_engine.persistence import PlanAuthorizationError, PlanPersistenceError, PlanSqlRepository


router = APIRouter(prefix="/api/plan-v2", tags=["plan-v2"])


PlanApiPrincipal = AuthenticatedPrincipal


async def require_plan_principal(
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> PlanApiPrincipal:
    return principal


class DraftRequest(BaseModel):
    domain: Literal["NUTRITION"] = "NUTRITION"
    period_start: date
    period_end: date
    timezone: str = Field(min_length=1, max_length=64)
    goal_override: str | None = None
    schedule_constraints: list[str] = Field(default_factory=list, max_length=20)
    temporary_preferences: list[str] = Field(default_factory=list, max_length=20)
    temporary_exclusions: list[str] = Field(default_factory=list, max_length=20)
    profile: dict[str, Any] = Field(default_factory=dict)


class SaveRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    revision_content_hash: str = Field(min_length=64, max_length=64)
    action_id: str = Field(min_length=1, max_length=200)


class LifecycleRequest(BaseModel):
    expected_revision_number: int = Field(ge=1)
    action_id: str = Field(min_length=1, max_length=200)


def _presentation(revision: PlanRevision) -> dict[str, Any]:
    """Return an exact UI payload generated from the authoritative revision."""

    payload = plan_v2._revision_payload(revision, mode="enforced")
    presentation = dict(payload["presentation"])
    presentation.update(
        {
            "validation": payload["validation"],
            "policy_versions": revision.policy_versions,
            "catalog_versions": revision.catalog_versions,
            "parent_revision_id": revision.parent_revision_id,
            "created_at": revision.created_at.isoformat(),
            "valid_lifecycle_targets": [status.value for status in valid_targets(revision.lifecycle_status)],
            "planned_not_actual": True,
        }
    )
    return presentation


def _not_found() -> HTTPException:
    # 404 for both missing and foreign owned identities avoids disclosing that
    # another user's revision exists.
    return HTTPException(status_code=404, detail="PLAN_NOT_FOUND")


def _persistence_error(exc: Exception) -> HTTPException:
    message = str(exc)
    if isinstance(exc, PlanAuthorizationError) and message == "PLAN_NOT_FOUND":
        return _not_found()
    if message in {
        "PLAN_READBACK_FAILED",
        "PLAN_READBACK_MISMATCH",
        "PLAN_PERSISTENCE_TRANSACTION_FAILED",
        "PLAN_PREVIEW_PERSISTENCE_FAILED",
    }:
        return HTTPException(status_code=503, detail=message)
    return HTTPException(status_code=409, detail=message)


@router.get("/plans")
async def list_owned_plans(principal: PlanApiPrincipal = Depends(require_plan_principal)) -> dict[str, Any]:
    try:
        plans = await PlanSqlRepository().list_owned(principal.user_id)
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plans": [_presentation(plan) for plan in plans]}


@router.get("/plans/active/{domain}")
async def get_active_plan(
    domain: PlanDomain,
    local_date: date | None = None,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        revision = await PlanSqlRepository().get_active(principal.user_id, domain, local_date=local_date)
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    if revision is None:
        raise _not_found()
    return {"plan": _presentation(revision)}


@router.get("/plans/{plan_id}")
async def get_exact_plan(
    plan_id: str,
    revision_id: str | None = None,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        revision = await PlanSqlRepository().get(principal.user_id, plan_id, revision_id)
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    if revision is None:
        raise _not_found()
    return {"plan": _presentation(revision)}


@router.post("/drafts/nutrition")
async def create_nutrition_draft(
    body: DraftRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    # This uses the public Plan V2 construction entry point and leaves the
    # result in DRAFT.  No legacy plan or observation is written by preview.
    profile = {**body.profile, "user_id": principal.user_id}
    output = await plan_v2.build_nutrition_plan(
        period_start=body.period_start.isoformat(),
        period_end=body.period_end.isoformat(),
        timezone=body.timezone,
        goal_override=body.goal_override,
        schedule_constraints=body.schedule_constraints,
        temporary_preferences=body.temporary_preferences,
        temporary_exclusions=body.temporary_exclusions,
        _runtime_context=plan_v2.PlanRuntimeContext(
            user_id=principal.user_id,
            session_id=f"plan-api-{uuid4()}",
            user_context=profile,
            db_session=None,
            authenticated_principal=True,
        ),
    )
    if output.get("status") != "READY":
        return {"status": output.get("status"), "plan": output.get("presentation"), "validation": output.get("validation")}
    try:
        await PlanSqlRepository().put_preview(PlanRevision.from_dict(output["plan"]))
    except Exception as exc:
        raise _persistence_error(PlanPersistenceError("PLAN_PREVIEW_PERSISTENCE_FAILED")) from exc
    return {"status": "READY", "plan": output["presentation"]}


@router.post("/plans/save")
async def save_plan(
    body: SaveRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    # Prefer the hot cache, then restore the exact server-created durable draft.
    repository = PlanSqlRepository()
    preview = PlanEngine().repository.get(principal.user_id, body.plan_id, body.revision_id)
    if preview is None:
        try:
            preview = await repository.get_preview(
                principal.user_id, body.plan_id, body.revision_id
            )
        except Exception as exc:
            raise _persistence_error(PlanPersistenceError("PLAN_PREVIEW_PERSISTENCE_FAILED")) from exc
    if preview is None:
        raise HTTPException(status_code=409, detail="PLAN_PREVIEW_NOT_FOUND")
    try:
        saved = await repository.save_exact_revision(
            owner_user_id=principal.user_id,
            revision=preview,
            expected_content_hash=body.revision_content_hash,
            action_id=body.action_id,
            activate=False,
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plan": _presentation(saved), "read_back_verified": True}


@router.post("/plans/{plan_id}/revisions/{revision_id}/{operation}")
async def change_lifecycle(
    plan_id: str,
    revision_id: str,
    operation: Literal["activate", "pause", "resume", "cancel"],
    body: LifecycleRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    target = {
        "activate": PlanLifecycleStatus.ACTIVE,
        "resume": PlanLifecycleStatus.ACTIVE,
        "pause": PlanLifecycleStatus.PAUSED,
        "cancel": PlanLifecycleStatus.CANCELLED,
    }[operation]
    try:
        changed = await PlanSqlRepository().set_status(
            owner_user_id=principal.user_id,
            plan_id=plan_id,
            revision_id=revision_id,
            expected_revision_number=body.expected_revision_number,
            status=target,
            action_id=body.action_id,
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plan": _presentation(changed), "read_back_verified": True}


__all__ = ["require_plan_principal", "router"]
