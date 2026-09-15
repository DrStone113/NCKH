"""Safe P1 Plan V2 tool surface.

The LLM supplies only a bounded request.  Authoritative profile context,
nutrition calculations, canonical dishes, and E4 prescriptions are resolved
server-side.  Generated plans remain drafts until a PendingUserAction commits
the exact revision hash.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Iterable, Mapping

from config import settings
from services.agent.tool_registry import ToolDescriptor
from services.plan_engine.contracts import (
    PlanDomain,
    PlanLifecycleStatus,
    PlanPatch,
    PlanPatchOperation,
    PlanRequest,
    PlanRevision,
)
from services.plan_engine.engine import PlanContextResolver, PlanEngine
from services.plan_engine.persistence import PlanPersistenceError, PlanSqlRepository
from services.plan_engine.request_normalization import PlanIntent, normalize_planning_request, normalize_workout_goal
from services.plan_engine.weekly_scheduler import (
    PlanningHorizonState,
    WeeklyScheduleError,
    WeeklyWorkoutRequest,
    WeeklyWorkoutScheduler,
    exposure_from_e4_payload,
    validate_weekly_plan,
)
from services.workout_planner.integration import WorkoutIntegrationService, WorkoutRuntimeContext


PLAN_V2_TOOL_NAMES = frozenset(
    {
        "build_nutrition_plan",
        "build_workout_schedule",
        "get_plan",
        "get_active_plan_v2",
        "revise_plan",
        "save_plan",
        "set_plan_status",
    }
)

_PLAN_STATUSES = [item.value for item in PlanLifecycleStatus]
_PATCH_OPERATIONS = [item.value for item in PlanPatchOperation]
_GOALS = ["lose_weight", "maintain", "gain_muscle"]
_ARRAY_OF_STRINGS = {"type": "array", "items": {"type": "string", "minLength": 1}, "maxItems": 20}


@dataclass(frozen=True, slots=True)
class PlanRuntimeContext:
    """Trusted dispatcher data, intentionally outside the JSON schema."""

    user_id: str | None
    session_id: str | None
    user_context: Mapping[str, Any] | None
    db_session: Any | None
    authenticated_principal: bool = False


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Dispatcher-authenticated identity; never sourced from tool JSON."""

    user_id: str
    authenticated: bool

    @property
    def valid(self) -> bool:
        return self.authenticated and bool(self.user_id) and self.user_id != "anonymous"


def _runtime(value: PlanRuntimeContext | None) -> PlanRuntimeContext:
    return value if isinstance(value, PlanRuntimeContext) else PlanRuntimeContext(None, None, None, None)


def _request(
    *,
    domain: PlanDomain,
    period_start: str,
    period_end: str,
    timezone: str,
    goal_override: str | None = None,
    schedule_constraints: Iterable[str] = (),
    temporary_preferences: Iterable[str] = (),
    temporary_exclusions: Iterable[str] = (),
    requested_modifications: Iterable[str] = (),
    request_source: str = "CHAT",
) -> PlanRequest:
    return PlanRequest(
        domain=domain,
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        timezone=timezone,
        goal_override=goal_override,
        schedule_constraints=tuple(str(item) for item in schedule_constraints),
        temporary_preferences=tuple(str(item) for item in temporary_preferences),
        temporary_exclusions=tuple(str(item) for item in temporary_exclusions),
        requested_modifications=tuple(str(item) for item in requested_modifications),
        request_source=request_source,
    )


def _context(runtime: PlanRuntimeContext):
    raw = dict(runtime.user_context) if isinstance(runtime.user_context, Mapping) else {}
    return PlanContextResolver.resolve(runtime.user_id, raw)


def _principal(runtime: PlanRuntimeContext) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(str(runtime.user_id or ""), bool(runtime.authenticated_principal))


def _enforced_allowed(runtime: PlanRuntimeContext) -> str | None:
    if settings.app_environment.strip().lower() == "production":
        return "PLAN_ENFORCED_MODE_FORBIDDEN_IN_PRODUCTION"
    if not _principal(runtime).valid:
        return "AUTHENTICATED_PRINCIPAL_REQUIRED"
    return None


def _revision_payload(revision: PlanRevision, *, mode: str | None = None) -> dict[str, Any]:
    presentation = _present(revision)
    return {
        "status": revision.validation.status.value,
        "plan": revision.to_dict(),
        "plan_id": revision.plan_id,
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "revision_content_hash": revision.revision_content_hash,
        "lifecycle_status": revision.lifecycle_status.value,
        "validation": revision.validation.to_dict(),
        "presentation": presentation,
        "plan_tool_mode": mode or settings.plan_tool_mode,
        "planned_not_actual": True,
    }


async def _persist_authenticated_preview(
    revision: PlanRevision, runtime: PlanRuntimeContext
) -> str:
    if not _principal(runtime).valid:
        return "NOT_AUTHENTICATED"
    # A verified identity alone does not prove that this invocation is attached
    # to the application's persistence runtime.  Unit/development callers use
    # an authenticated synthetic principal with no DB session; attempting the
    # process-global asyncpg pool from their short-lived ``asyncio.run`` loop
    # leaks cancellation tasks when PostgreSQL is unavailable.  The real chat
    # dispatcher always supplies its scoped DB session, while HTTP Plan V2 uses
    # the repository directly in its router.
    if runtime.db_session is None:
        return "UNAVAILABLE"
    try:
        await PlanSqlRepository().put_preview(revision)
        return "PERSISTED"
    except Exception:
        # Draft calculation stays available during a temporary DB outage, but
        # the response explicitly records that restart-safe save is unavailable.
        return "UNAVAILABLE"


def _present(revision: PlanRevision) -> dict[str, Any]:
    """Presentation built exclusively from the persisted revision contract."""

    summary = revision.summary
    daily_summary = summary.get("daily") if isinstance(summary, dict) else {}
    days: dict[str, list[dict[str, Any]]] = {}
    for item in revision.items:
        days.setdefault(item.scheduled_date.isoformat(), []).append(
            {
                "plan_item_id": item.plan_item_id,
                "slot": item.schedule_slot,
                "item_type": item.item_type.value,
                "status": item.status.value,
                "dish_name": item.content.get("dish_name"),
                "canonical_refs": item.canonical_refs,
                # Exact canonical components are presentation data, not an
                # observation. Keeping them here lets every app surface show
                # the same dish detail instead of reconstructing it from text.
                "ingredients": item.content.get("components", []),
                "serving_grams": item.content.get("serving_grams"),
                "planned_duration_minutes": item.content.get("planned_duration_minutes"),
                "nutrition": {
                    key: item.content.get(key)
                    for key in ("total_calories", "total_protein", "total_carbs", "total_fat")
                    if item.content.get(key) is not None
                },
            }
        )
    text = (
        f"Bản kế hoạch {revision.domain.value.lower()} gồm {len(revision.items)} mục, "
        f"từ {revision.request.period_start.isoformat()} đến {revision.request.period_end.isoformat()}. "
        "Đây là kế hoạch dự kiến, chưa phải dữ liệu đã ăn hoặc đã tập."
    )
    return {
        "type": "versioned_plan",
        "text": text,
        "plan_id": revision.plan_id,
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "revision_content_hash": revision.revision_content_hash,
        "domain": revision.domain.value,
        "lifecycle_status": revision.lifecycle_status.value,
        "timezone": revision.request.timezone,
        "period_start": revision.request.period_start.isoformat(),
        "period_end": revision.request.period_end.isoformat(),
        "days": [
            {
                "date": key,
                "items": value,
                "summary": (
                    daily_summary.get(key, {})
                    if isinstance(daily_summary, dict)
                    else {}
                ),
            }
            for key, value in sorted(days.items())
        ],
        "summary": summary,
        "daily_targets": {
            "calories": revision.goal_snapshot.get("canonical_daily_kcal"),
            "protein": revision.goal_snapshot.get("canonical_daily_protein"),
        },
        "reason_codes": revision.explanation_metadata.get("reason_codes", []),
        "planned_not_actual": True,
    }


async def build_nutrition_plan(
    *,
    period_start: str,
    period_end: str,
    timezone: str,
    goal_override: str | None = None,
    schedule_constraints: Iterable[str] = (),
    temporary_preferences: Iterable[str] = (),
    temporary_exclusions: Iterable[str] = (),
    requested_modifications: Iterable[str] = (),
    _runtime_context: PlanRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    normalized = normalize_planning_request(
        intent=PlanIntent.NUTRITION_DRAFT,
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
        goal=goal_override,
        schedule_constraints=schedule_constraints,
        temporary_preferences=temporary_preferences,
        temporary_exclusions=temporary_exclusions,
        context=runtime.user_context,
    )
    request = _request(
        domain=PlanDomain.NUTRITION, period_start=normalized.period_start.isoformat() if normalized.period_start else period_start,
        period_end=normalized.period_end.isoformat() if normalized.period_end else period_end,
        timezone=normalized.timezone or timezone,
        goal_override=normalized.goal if normalized.goal is not None else goal_override,
        schedule_constraints=normalized.nutrition_constraints,
        temporary_preferences=normalized.temporary_preferences, temporary_exclusions=normalized.temporary_exclusions,
        requested_modifications=requested_modifications,
    )
    revision = PlanEngine().build_nutrition_plan(_context(runtime), request)
    payload = _revision_payload(revision)
    payload["preview_persistence_status"] = await _persist_authenticated_preview(revision, runtime)
    return payload


async def build_workout_schedule(
    *,
    period_start: str,
    period_end: str,
    timezone: str,
    goal_override: str | None = None,
    duration_minutes: int | None = None,
    training_location: str | None = None,
    equipment: Iterable[str] | None = None,
    temporary_preferences: Iterable[str] = (),
    temporary_exclusions: Iterable[str] = (),
    requested_body_area: str | None = None,
    number_of_sessions: int | None = None,
    available_days: Iterable[str] = (),
    unavailable_days: Iterable[str] = (),
    preferred_days: Iterable[str] = (),
    duration_by_day: Mapping[str, int] | None = None,
    _runtime_context: PlanRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    normalized = normalize_planning_request(
        intent=PlanIntent.WORKOUT_DRAFT,
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
        goal=goal_override,
        temporary_preferences=temporary_preferences,
        temporary_exclusions=temporary_exclusions,
        session_count=number_of_sessions,
        available_weekdays=available_days,
        unavailable_weekdays=unavailable_days,
        preferred_weekdays=preferred_days,
        duration_minutes=duration_minutes,
        duration_by_day=duration_by_day,
        equipment=equipment,
        context=runtime.user_context,
    )
    request = _request(
        domain=PlanDomain.WORKOUT, period_start=normalized.period_start.isoformat() if normalized.period_start else period_start,
        period_end=normalized.period_end.isoformat() if normalized.period_end else period_end,
        timezone=normalized.timezone or timezone,
        goal_override=normalized.goal if normalized.goal is not None else goal_override,
        temporary_preferences=normalized.temporary_preferences,
        temporary_exclusions=normalized.temporary_exclusions,
    )
    context = _context(runtime)
    safety_clarifications = {
        "WORKOUT_PROFILE_REQUIRED",
        "EXERCISE_SAFETY_CONTEXT_REQUIRED",
    }
    clarification = next((need for need in normalized.clarification_needs if need in safety_clarifications), None)
    if clarification:
        return _revision_payload(PlanEngine()._clarification_revision(context, request, clarification))  # noqa: SLF001
    e4_goal = normalize_workout_goal(goal_override, context=context.raw_context)
    profile = context.raw_context.get("workout_profile") if isinstance(context.raw_context.get("workout_profile"), Mapping) else {}
    configured_days = tuple(str(item) for item in profile.get("preferred_training_days", ()) if isinstance(item, str))
    configured_count = profile.get("available_days_per_week")
    # A bounded one-day request is more specific than a persisted weekly
    # preference.  Passing the old preferred weekdays here could make the
    # requested date appear unavailable and cause an unnecessary clarification.
    resolved_available_days = (
        normalized.available_weekdays
        or (() if request.duration_days == 1 else configured_days)
    )
    resolved_session_count = (
        normalized.session_count
        if normalized.session_count is not None
        else 1 if request.duration_days == 1 else configured_count if isinstance(configured_count, int) else None
    )
    try:
        weekly = WeeklyWorkoutScheduler().schedule(
            WeeklyWorkoutRequest(
                plan_request=request,
                number_of_sessions=resolved_session_count,
                explicit_available_days=resolved_available_days,
                explicit_unavailable_days=normalized.unavailable_weekdays,
                preferred_days=normalized.preferred_weekdays,
                default_duration_minutes=normalized.duration_minutes,
                duration_by_day=dict(normalized.duration_by_day), location=training_location,
                equipment=normalized.equipment if equipment is not None else None,
                temporary_constraints=normalized.temporary_exclusions,
            )
        )
    except WeeklyScheduleError as exc:
        revision = PlanEngine()._clarification_revision(context, request, str(exc))  # noqa: SLF001
        return _revision_payload(revision)
    e4_runtime = WorkoutRuntimeContext(
        user_id=runtime.user_id, session_id=runtime.session_id,
        user_context=runtime.user_context, db_session=runtime.db_session,
    )
    horizon = PlanningHorizonState(context.training_state)
    e4_sessions: list[tuple[date, dict[str, Any], tuple[str, ...]]] = []
    for slot in weekly.slots:
        outcome = await WorkoutIntegrationService(runtime.db_session).build(
            e4_runtime,
            goal_override=e4_goal,
            requested_duration_minutes=slot.duration_minutes,
            requested_location=training_location,
            available_equipment_override=normalized.equipment if equipment is not None else None,
            requested_body_area=requested_body_area,
            exercise_exclude=temporary_exclusions,
            temporary_preferences=temporary_preferences,
        )
        payload = outcome.to_tool_payload()
        if payload.get("status") != "READY":
            revision = PlanEngine()._clarification_revision(context, request, str(payload.get("status") or "E4_PLAN_UNAVAILABLE"))  # noqa: SLF001
            return _revision_payload(revision)
        # Planned exposure is only a soft anti-duplication signal.  If the
        # initial E4 session fully repeats it, ask E4 for an alternative under
        # the same hard constraints; retain the initial session when no valid
        # alternative exists instead of inventing a prescription.
        planned_ids = horizon.planned_exercise_ids
        generated_ids = exposure_from_e4_payload(slot.scheduled_date, payload).exercise_ids
        if planned_ids and generated_ids and set(generated_ids).issubset(set(planned_ids)):
            alternate = await WorkoutIntegrationService(runtime.db_session).build(
                e4_runtime,
                goal_override=e4_goal, requested_duration_minutes=slot.duration_minutes,
                requested_location=training_location,
                available_equipment_override=normalized.equipment if equipment is not None else None,
                requested_body_area=requested_body_area,
                exercise_exclude=tuple(dict.fromkeys((*tuple(temporary_exclusions), *planned_ids))),
                temporary_preferences=temporary_preferences,
            )
            alternate_payload = alternate.to_tool_payload()
            if alternate_payload.get("status") == "READY":
                payload = alternate_payload
        exposure = exposure_from_e4_payload(slot.scheduled_date, payload)
        horizon = horizon.with_planned_session(exposure)
        e4_sessions.append((slot.scheduled_date, payload, slot.provenance))
    weekly_issues = validate_weekly_plan(weekly, horizon=horizon)
    if weekly_issues:
        revision = PlanEngine()._clarification_revision(context, request, weekly_issues[0])  # noqa: SLF001
        return _revision_payload(revision)
    revision = PlanEngine().build_workout_revision(
        context, request, e4_sessions=tuple(e4_sessions)
    )
    revision = replace(
        revision,
        provenance={
            **revision.provenance, "planning_horizon": horizon.projection(),
            "weekly_schedule": {
                "reason_codes": list(weekly.reason_codes),
                "dates": [day.isoformat() for day in weekly.dates],
                "validation_issues": list(weekly_issues),
            },
        },
    )
    PlanEngine().repository.put(revision)
    payload = _revision_payload(revision)
    payload["preview_persistence_status"] = await _persist_authenticated_preview(revision, runtime)
    return payload


def _workout_schedule_dates(raw: Mapping[str, Any], request: PlanRequest) -> tuple[date, ...]:
    """Resolve schedule availability, never fill missing availability with 7 days."""

    profile = raw.get("workout_profile") if isinstance(raw.get("workout_profile"), Mapping) else {}
    configured = profile.get("preferred_training_days")
    names = {str(item).strip().lower()[:3] for item in configured} if isinstance(configured, (list, tuple)) else set()
    weekday_names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    selected = tuple(
        current
        for current in (date.fromordinal(request.period_start.toordinal() + offset) for offset in range(request.duration_days))
        if weekday_names[current.weekday()] in names
    )
    if selected:
        return selected
    available_days = profile.get("available_days_per_week")
    if isinstance(available_days, int) and available_days == 1:
        return (request.period_start,)
    if request.duration_days == 1:
        return (request.period_start,)
    return ()


async def get_plan(
    *, plan_id: str, revision_id: str | None = None, _runtime_context: PlanRuntimeContext | None = None
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    context = _context(runtime)
    if settings.plan_tool_mode == "enforced":
        blocked = _enforced_allowed(runtime)
        if blocked:
            return {"status": blocked}
        revision = await PlanSqlRepository().get(context.owner_user_id, plan_id, revision_id)
    else:
        revision = PlanEngine().repository.get(context.owner_user_id, plan_id, revision_id)
    if revision is None:
        return {"status": "NOT_FOUND", "plan_id": plan_id}
    return _revision_payload(revision)


async def get_active_plan_v2(
    *, domain: str, local_date: str | None = None, _runtime_context: PlanRuntimeContext | None = None
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    context = _context(runtime)
    try:
        parsed_domain = PlanDomain(domain)
        parsed_date = date.fromisoformat(local_date) if local_date else None
    except ValueError:
        return {"status": "INVALID_PLAN_QUERY"}
    if settings.plan_tool_mode == "enforced":
        blocked = _enforced_allowed(runtime)
        if blocked:
            return {"status": blocked}
        revision = await PlanSqlRepository().get_active(context.owner_user_id, parsed_domain, local_date=parsed_date)
    else:
        revision = PlanEngine().repository.get_active(context.owner_user_id, parsed_domain, local_date=parsed_date)
    if revision is None:
        return {"status": "NOT_FOUND", "domain": parsed_domain.value}
    return _revision_payload(revision)


async def revise_plan(
    *,
    plan_id: str,
    revision_id: str,
    expected_revision_number: int,
    operation: str,
    target_item_id: str | None = None,
    requested_change: Mapping[str, Any] | None = None,
    reason: str,
    _runtime_context: PlanRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    normalized = normalize_planning_request(
        intent=PlanIntent.PLAN_REVISION,
        target_plan_id=plan_id,
        target_revision_id=revision_id,
        context=runtime.user_context,
    )
    if normalized.clarification_needs:
        return {"status": normalized.clarification_needs[0], "write_status": "NOT_PERSISTED"}
    try:
        patch = PlanPatch(
            target_plan_id=normalized.target_plan_id or plan_id, target_revision_id=normalized.target_revision_id or revision_id,
            expected_revision_number=expected_revision_number,
            operation=PlanPatchOperation(operation), target_item_id=target_item_id,
            requested_change=dict(requested_change or {}), request_source="CHAT", reason=reason,
        )
        context = _context(runtime)
        if settings.plan_tool_mode == "enforced":
            blocked = _enforced_allowed(runtime)
            if blocked:
                return {"status": blocked}
            persisted = await PlanSqlRepository().get(context.owner_user_id, plan_id, revision_id)
            if persisted is None:
                return {"status": "PLAN_NOT_FOUND"}
            PlanEngine().repository.put(persisted)
        revision = PlanEngine().revise(context, patch)
    except ValueError as exc:
        return {"status": str(exc)}
    payload = _revision_payload(revision)
    payload["preview_persistence_status"] = await _persist_authenticated_preview(revision, runtime)
    return payload


async def save_plan(
    *,
    plan_id: str,
    revision_id: str,
    revision_content_hash: str,
    request_id: str,
    activate: bool = False,
    _runtime_context: PlanRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    if settings.plan_tool_mode == "enforced":
        blocked = _enforced_allowed(runtime)
        if blocked:
            return {"status": blocked, "write_status": "NOT_PERSISTED"}
        context = _context(runtime)
        repository = PlanSqlRepository()
        preview = PlanEngine().repository.get(context.owner_user_id, plan_id, revision_id)
        if preview is None:
            preview = await repository.get_preview(
                context.owner_user_id, plan_id, revision_id
            )
        if preview is None:
            return {"status": "PLAN_PREVIEW_NOT_FOUND", "write_status": "NOT_PERSISTED"}
        try:
            revision = await repository.save_exact_revision(
                owner_user_id=_principal(runtime).user_id, revision=preview,
                expected_content_hash=revision_content_hash, action_id=request_id, activate=activate,
            )
        except PlanPersistenceError as exc:
            return {"status": str(exc), "write_status": "NOT_PERSISTED"}
        payload = _revision_payload(revision)
        payload.update({
            "status": "READY", "write_status": "PERSISTED",
            "read_back_plan_id": revision.plan_id, "read_back_revision_id": revision.revision_id,
            "read_back_revision_content_hash": revision.revision_content_hash,
            "read_back_verified": True,
        })
        return payload
    try:
        revision = PlanEngine().save_exact_revision(
            _context(runtime), plan_id=plan_id, revision_id=revision_id,
            content_hash_value=revision_content_hash, request_id=request_id, activate=activate,
        )
    except ValueError as exc:
        return {"status": str(exc), "write_status": "NOT_PERSISTED"}
    # Shadow storage is intentional: it proves exact revision identity while
    # leaving legacy production plans and observations untouched.
    payload = _revision_payload(revision)
    payload.update(
        {
            "status": "READY",
            "write_status": "SHADOW_SAVED" if settings.plan_tool_mode == "shadow" else "PERSISTED",
            "read_back_plan_id": revision.plan_id,
            "read_back_revision_id": revision.revision_id,
            "read_back_revision_content_hash": revision.revision_content_hash,
        }
    )
    return payload


async def set_plan_status(
    *,
    plan_id: str,
    revision_id: str,
    expected_revision_number: int,
    status: str,
    request_id: str,
    _runtime_context: PlanRuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = _runtime(_runtime_context)
    normalized = normalize_planning_request(
        intent=PlanIntent.PLAN_LIFECYCLE,
        target_plan_id=plan_id,
        target_revision_id=revision_id,
        context=runtime.user_context,
    )
    if normalized.clarification_needs:
        return {"status": normalized.clarification_needs[0], "write_status": "NOT_PERSISTED"}
    plan_id = normalized.target_plan_id or plan_id
    revision_id = normalized.target_revision_id or revision_id
    if settings.plan_tool_mode == "enforced":
        blocked = _enforced_allowed(runtime)
        if blocked:
            return {"status": blocked, "write_status": "NOT_PERSISTED"}
        try:
            revision = await PlanSqlRepository().set_status(
                owner_user_id=_principal(runtime).user_id, plan_id=plan_id, revision_id=revision_id,
                expected_revision_number=expected_revision_number, status=PlanLifecycleStatus(status), action_id=request_id,
            )
        except (ValueError, PlanPersistenceError) as exc:
            return {"status": str(exc), "write_status": "NOT_PERSISTED"}
        payload = _revision_payload(revision)
        payload.update({
            "status": "READY", "write_status": "PERSISTED", "read_back_plan_id": revision.plan_id,
            "read_back_revision_id": revision.revision_id, "read_back_revision_content_hash": revision.revision_content_hash,
            "read_back_verified": True,
        })
        return payload
    try:
        revision = PlanEngine().repository.set_status(
            owner_user_id=_context(runtime).owner_user_id, plan_id=plan_id, revision_id=revision_id,
            expected_revision_number=expected_revision_number, status=PlanLifecycleStatus(status), request_id=request_id,
        )
    except ValueError as exc:
        return {"status": str(exc)}
    return _revision_payload(revision)


_PLAN_REQUEST_PROPERTIES = {
    "period_start": {"type": "string", "format": "date"},
    "period_end": {"type": "string", "format": "date"},
    "timezone": {"type": "string", "minLength": 1, "maxLength": 64},
    "goal_override": {"type": "string", "enum": _GOALS},
    "schedule_constraints": _ARRAY_OF_STRINGS,
    "temporary_preferences": _ARRAY_OF_STRINGS,
    "temporary_exclusions": _ARRAY_OF_STRINGS,
    "requested_modifications": _ARRAY_OF_STRINGS,
}

BUILD_NUTRITION_PLAN_DESCRIPTOR = ToolDescriptor(
    name="build_nutrition_plan",
    description="Tạo bản nháp kế hoạch ăn từ nutrition policy và catalog canonical. Chỉ dùng khi người dùng yêu cầu lập kế hoạch; không tự lưu, không tự coi là đã ăn.",
    parameters_schema={"type": "object", "properties": _PLAN_REQUEST_PROPERTIES, "required": ["period_start", "period_end", "timezone"], "additionalProperties": False},
    side="server", fn=build_nutrition_plan, idempotent=True,
)

BUILD_WORKOUT_SCHEDULE_DESCRIPTOR = ToolDescriptor(
    name="build_workout_schedule",
    description="Tạo bản nháp lịch tập bằng E4. Chỉ dùng khi người dùng yêu cầu lịch tập; không tự lưu, không ghi kết quả tập. Với lịch nhiều buổi mà E4 chưa có weekly scheduler, tool sẽ yêu cầu làm rõ thay vì tự bịa volume/recovery.",
    parameters_schema={
        "type": "object",
        "properties": {
            "period_start": {"type": "string", "format": "date"}, "period_end": {"type": "string", "format": "date"},
            "timezone": {"type": "string", "minLength": 1, "maxLength": 64}, "goal_override": {"type": "string", "enum": _GOALS},
            "duration_minutes": {"type": "integer", "minimum": 10, "maximum": 180}, "training_location": {"type": "string", "minLength": 1, "maxLength": 160},
            "equipment": _ARRAY_OF_STRINGS, "temporary_preferences": _ARRAY_OF_STRINGS,
            "temporary_exclusions": _ARRAY_OF_STRINGS, "requested_body_area": {"type": "string", "minLength": 1, "maxLength": 100},
            "number_of_sessions": {"type": "integer", "minimum": 1, "maximum": 7},
            "available_days": _ARRAY_OF_STRINGS, "unavailable_days": _ARRAY_OF_STRINGS,
            "preferred_days": _ARRAY_OF_STRINGS,
            "duration_by_day": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 10, "maximum": 180}},
        },
        "required": ["period_start", "period_end", "timezone"], "additionalProperties": False,
    },
    side="server", fn=build_workout_schedule, idempotent=True,
)

GET_PLAN_DESCRIPTOR = ToolDescriptor(
    name="get_plan",
    description="Đọc đúng một plan/revision đã biết khi người dùng hỏi nội dung hoặc muốn sửa. Không tạo lại plan và không nhận user_id từ model.",
    parameters_schema={"type": "object", "properties": {"plan_id": {"type": "string", "minLength": 1}, "revision_id": {"type": "string", "minLength": 1}}, "required": ["plan_id"], "additionalProperties": False},
    side="server", fn=get_plan, idempotent=True,
)

GET_ACTIVE_PLAN_V2_DESCRIPTOR = ToolDescriptor(
    name="get_active_plan_v2",
    description="Đọc plan ACTIVE có thẩm quyền cho một domain và ngày địa phương. Dùng cho 'hôm nay trong kế hoạch có gì', tuyệt đối không tạo plan mới.",
    parameters_schema={"type": "object", "properties": {"domain": {"type": "string", "enum": [PlanDomain.NUTRITION.value, PlanDomain.WORKOUT.value]}, "local_date": {"type": "string", "format": "date"}}, "required": ["domain"], "additionalProperties": False},
    side="server", fn=get_active_plan_v2, idempotent=True,
)

REVISE_PLAN_DESCRIPTOR = ToolDescriptor(
    name="revise_plan",
    description="Tạo revision DRAFT mới cho đúng plan item/revision vừa đọc. Không fuzzy-edit từ prose và không tự lưu. Dùng ID trả về từ get_plan/preview.",
    parameters_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "minLength": 1}, "revision_id": {"type": "string", "minLength": 1},
            "expected_revision_number": {"type": "integer", "minimum": 1}, "operation": {"type": "string", "enum": _PATCH_OPERATIONS},
            "target_item_id": {"type": "string", "minLength": 1},
            "requested_change": {"type": "object", "properties": {"schedule_slot": {"type": "string", "minLength": 1}, "scheduled_date": {"type": "string", "format": "date"}, "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 240}}, "additionalProperties": False},
            "reason": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "required": ["plan_id", "revision_id", "expected_revision_number", "operation", "reason"], "additionalProperties": False,
    },
    side="server", fn=revise_plan, idempotent=True,
)

SAVE_PLAN_DESCRIPTOR = ToolDescriptor(
    name="save_plan",
    description="Chỉ lưu chính xác revision người dùng vừa xác nhận. Không dùng khi họ mới yêu cầu tạo/xem plan. plan_id, revision_id và hash phải lấy nguyên vẹn từ preview chờ xác nhận.",
    parameters_schema={
        "type": "object",
            "properties": {"plan_id": {"type": "string", "minLength": 1}, "revision_id": {"type": "string", "minLength": 1}, "revision_content_hash": {"type": "string", "minLength": 64, "maxLength": 64}, "request_id": {"type": "string", "minLength": 1}, "activate": {"type": "boolean", "default": False}},
        "required": ["plan_id", "revision_id", "revision_content_hash", "request_id"], "additionalProperties": False,
    },
    side="server", fn=save_plan, idempotent=False,
)

SET_PLAN_STATUS_DESCRIPTOR = ToolDescriptor(
    name="set_plan_status",
    description="Chỉ đổi lifecycle của đúng revision khi người dùng yêu cầu rõ (pause, resume, complete, cancel). Không dùng để biến DRAFT thành ACTIVE; phải save trước.",
    parameters_schema={"type": "object", "properties": {"plan_id": {"type": "string", "minLength": 1}, "revision_id": {"type": "string", "minLength": 1}, "expected_revision_number": {"type": "integer", "minimum": 1}, "status": {"type": "string", "enum": _PLAN_STATUSES}, "request_id": {"type": "string", "minLength": 1}}, "required": ["plan_id", "revision_id", "expected_revision_number", "status", "request_id"], "additionalProperties": False},
    side="server", fn=set_plan_status, idempotent=False,
)


__all__ = [
    "BUILD_NUTRITION_PLAN_DESCRIPTOR", "BUILD_WORKOUT_SCHEDULE_DESCRIPTOR", "GET_ACTIVE_PLAN_V2_DESCRIPTOR",
    "AuthenticatedPrincipal", "GET_PLAN_DESCRIPTOR", "PLAN_V2_TOOL_NAMES", "PlanRuntimeContext", "REVISE_PLAN_DESCRIPTOR",
    "SAVE_PLAN_DESCRIPTOR", "SET_PLAN_STATUS_DESCRIPTOR", "build_nutrition_plan", "build_workout_schedule",
    "get_active_plan_v2", "get_plan", "revise_plan", "save_plan", "set_plan_status",
]
