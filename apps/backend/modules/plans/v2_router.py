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
from services.plan_engine.contracts import PlanArtifactKind, PlanDomain, PlanLifecycleStatus, PlanPatch, PlanPatchOperation, PlanRevision
from services.plan_engine.application_service import PlanApplicationService
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
    domain: Literal["NUTRITION", "WORKOUT", "COMBINED_HEALTH"] = "NUTRITION"
    period_start: date
    period_end: date
    timezone: str = Field(min_length=1, max_length=64)
    goal_override: str | None = None
    schedule_constraints: list[str] = Field(default_factory=list, max_length=20)
    temporary_preferences: list[str] = Field(default_factory=list, max_length=20)
    temporary_exclusions: list[str] = Field(default_factory=list, max_length=20)
    profile: dict[str, Any] = Field(default_factory=dict)
    duration_minutes: int | None = Field(default=None, ge=10, le=240)
    number_of_sessions: int | None = Field(default=None, ge=1, le=14)
    training_location: str | None = None
    equipment: list[str] = Field(default_factory=list, max_length=20)


class SaveRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    revision_content_hash: str = Field(min_length=64, max_length=64)
    action_id: str = Field(min_length=1, max_length=200)


class LifecycleRequest(BaseModel):
    expected_revision_number: int = Field(ge=1)
    action_id: str = Field(min_length=1, max_length=200)
    replace_conflicts: bool = False


class RevisionPatchRequest(BaseModel):
    base_revision_id: str = Field(min_length=1)
    expected_revision_number: int = Field(ge=1)
    operation: PlanPatchOperation
    target_item_id: str | None = None
    requested_change: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="USER_REQUEST", max_length=500)
    action_id: str = Field(min_length=1, max_length=200)


class AttachStandaloneRequest(BaseModel):
    base_revision_id: str = Field(min_length=1)
    combined_content_hash: str = Field(min_length=64, max_length=64)
    source_plan_id: str = Field(min_length=1)
    source_revision_id: str = Field(min_length=1)
    source_content_hash: str = Field(min_length=64, max_length=64)
    action_id: str = Field(min_length=1, max_length=200)
    source_surface: Literal["PLAN_UI", "MENU_UI", "WORKOUT_UI"] = "PLAN_UI"


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
async def list_owned_plans(
    artifact_kind: PlanArtifactKind | None = None,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        plans = await PlanSqlRepository().list_owned(principal.user_id, artifact_kind=artifact_kind)
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


@router.post("/previews")
async def create_plan_preview(
    body: DraftRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    """Create an exact preview for MENU, WORKOUT, or COMBINED_PLAN.

    The combined path composes the canonical nutrition and E4 workout
    revisions into one immutable revision; it does not persist child plans.
    """
    profile = {**body.profile, "user_id": principal.user_id}
    runtime = plan_v2.PlanRuntimeContext(
        user_id=principal.user_id,
        session_id=f"plan-api-{uuid4()}",
        user_context=profile,
        db_session=None,
        authenticated_principal=True,
    )
    common = {
        "period_start": body.period_start.isoformat(),
        "period_end": body.period_end.isoformat(),
        "timezone": body.timezone,
        "goal_override": body.goal_override,
        "temporary_preferences": body.temporary_preferences,
        "temporary_exclusions": body.temporary_exclusions,
        "_runtime_context": runtime,
    }
    nutrition_common = {**common, "schedule_constraints": body.schedule_constraints}
    if body.domain == "NUTRITION":
        output = await plan_v2.build_nutrition_plan(**nutrition_common)
        if output.get("status") != "READY":
            return {"status": output.get("status"), "plan": output.get("presentation"), "validation": output.get("validation")}
        revision = PlanRevision.from_dict(output["plan"])
    elif body.domain == "WORKOUT":
        output = await plan_v2.build_workout_schedule(
            **common,
            duration_minutes=body.duration_minutes,
            number_of_sessions=body.number_of_sessions,
            training_location=body.training_location,
            equipment=body.equipment,
        )
        if output.get("status") != "READY":
            return {"status": output.get("status"), "plan": output.get("presentation"), "validation": output.get("validation")}
        revision = PlanRevision.from_dict(output["plan"])
    else:
        nutrition = await plan_v2.build_nutrition_plan(**nutrition_common)
        workout = await plan_v2.build_workout_schedule(
            **common,
            duration_minutes=body.duration_minutes,
            number_of_sessions=body.number_of_sessions,
            training_location=body.training_location,
            equipment=body.equipment,
        )
        if nutrition.get("status") != "READY" or workout.get("status") != "READY":
            return {
                "status": "CLARIFICATION_REQUIRED",
                "components": {"menu": nutrition, "workout": workout},
            }
        context = plan_v2._context(runtime)
        combined_request = plan_v2._request(
            domain=PlanDomain.COMBINED_HEALTH,
            period_start=body.period_start.isoformat(),
            period_end=body.period_end.isoformat(),
            timezone=body.timezone,
            goal_override=body.goal_override,
            schedule_constraints=body.schedule_constraints,
            temporary_preferences=body.temporary_preferences,
            temporary_exclusions=body.temporary_exclusions,
        )
        revision = PlanEngine().build_combined_container(
            context,
            combined_request,
            (PlanRevision.from_dict(nutrition["plan"]), PlanRevision.from_dict(workout["plan"])),
        )
    await PlanApplicationService().preview(revision)
    payload = plan_v2._revision_payload(revision, mode="enforced")
    payload["artifact_kind"] = PlanArtifactKind.for_domain(revision.domain).value
    payload["preview_persistence_status"] = "PERSISTED"
    return payload


@router.post("/actions/save")
@router.post("/plans/save")
async def save_plan(
    body: SaveRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        saved = await PlanApplicationService().save_exact(
            owner_user_id=principal.user_id, plan_id=body.plan_id,
            revision_id=body.revision_id,
            content_hash=body.revision_content_hash, action_id=body.action_id,
            actor_type="USER", source_surface="CHAT",
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plan": _presentation(saved), "read_back_verified": True}


@router.get("/plans/{plan_id}/change-events")
async def get_plan_change_events(
    plan_id: str,
    limit: int = 100,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        events = await PlanApplicationService().list_change_events(
            owner_user_id=principal.user_id, plan_id=plan_id, limit=limit
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"events": events}


@router.get("/plans/{plan_id}/history")
async def get_plan_history(
    plan_id: str,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    try:
        history = await PlanApplicationService().history(
            owner_user_id=principal.user_id, plan_id=plan_id
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    if not history:
        raise _not_found()
    return {"history": [_presentation(revision) for revision in history]}


@router.post("/{plan_id}/revisions")
@router.post("/plans/{plan_id}/revisions")
async def create_plan_revision_preview(
    plan_id: str,
    body: RevisionPatchRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    """Apply a typed patch to the exact base revision and persist its preview."""
    patch = PlanPatch(
        target_plan_id=plan_id,
        target_revision_id=body.base_revision_id,
        operation=body.operation,
        target_item_id=body.target_item_id,
        requested_change=body.requested_change,
        request_source="PLAN_UI",
        reason=body.reason,
        expected_revision_number=body.expected_revision_number,
    )
    try:
        revised = await PlanApplicationService().revise_preview(
            owner_user_id=principal.user_id, patch=patch,
            action_id=body.action_id, source_surface="PLAN_UI", reason=body.reason,
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    except ValueError as exc:
        message = str(exc)
        status = 404 if message in {"PLAN_NOT_FOUND", "PLAN_ITEM_NOT_FOUND"} else 409
        raise HTTPException(status_code=status, detail=message) from exc
    return {
        "status": "PREVIEW_READY",
        "plan": _presentation(revised),
        "revision_content_hash": revised.revision_content_hash,
        "planned_not_actual": True,
    }


@router.post("/plans/{plan_id}/attachments")
async def attach_standalone_plan(
    plan_id: str,
    body: AttachStandaloneRequest,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    """Attach a saved standalone menu/workout to a combined Plan atomically."""
    try:
        attached = await PlanApplicationService().attach_standalone_to_combined(
            owner_user_id=principal.user_id,
            combined_plan_id=plan_id,
            base_revision_id=body.base_revision_id,
            expected_combined_content_hash=body.combined_content_hash,
            source_plan_id=body.source_plan_id,
            source_revision_id=body.source_revision_id,
            expected_source_content_hash=body.source_content_hash,
            action_id=body.action_id,
            source_surface=body.source_surface,
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plan": _presentation(attached), "read_back_verified": True}


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
            replace_conflicts=body.replace_conflicts,
            actor_type="USER",
            source_surface="PLAN_UI",
            reason="EXPLICIT_LIFECYCLE_ACTION",
        )
    except PlanPersistenceError as exc:
        raise _persistence_error(exc) from exc
    return {"plan": _presentation(changed), "read_back_verified": True}


__all__ = ["require_plan_principal", "router"]
