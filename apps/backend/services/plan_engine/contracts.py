"""Immutable contracts for the versioned Plan Engine (P1).

These contracts deliberately model *planned* state only.  They are separate
from meal/exercise observations and keep enough provenance to reproduce a
draft, validate a revision, and audit a confirmed save without asking an LLM
to reconstruct nutrition or workout calculations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Final
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class PlanDomain(StrEnum):
    NUTRITION = "NUTRITION"
    WORKOUT = "WORKOUT"
    COMBINED_HEALTH = "COMBINED_HEALTH"


class PlanArtifactKind(StrEnum):
    """User-facing planned artifact semantics.

    ``PlanDomain`` remains wire-compatible with existing rows.  This enum is
    the public contract used by chat and Flutter so a single nutrition day is
    never confused with a multi-day menu or a combined Plan.
    """

    MENU = "MENU"
    WORKOUT = "WORKOUT"
    COMBINED_PLAN = "COMBINED_PLAN"

    @classmethod
    def for_domain(cls, domain: "PlanDomain") -> "PlanArtifactKind":
        return {
            PlanDomain.NUTRITION: cls.MENU,
            PlanDomain.WORKOUT: cls.WORKOUT,
            PlanDomain.COMBINED_HEALTH: cls.COMBINED_PLAN,
        }[domain]


class PlanLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    SAVED = "SAVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class PlanValidationStatus(StrEnum):
    READY = "READY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    REQUIRES_SPECIALIST_GUIDANCE = "REQUIRES_SPECIALIST_GUIDANCE"
    INVALID = "INVALID"


class PlanItemType(StrEnum):
    MEAL = "MEAL"
    WORKOUT_SESSION = "WORKOUT_SESSION"


class PlanItemStatus(StrEnum):
    PLANNED = "PLANNED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class PlanPatchOperation(StrEnum):
    ADD_ITEM = "ADD_ITEM"
    REMOVE_ITEM = "REMOVE_ITEM"
    REPLACE_ITEM = "REPLACE_ITEM"
    MOVE_ITEM = "MOVE_ITEM"
    CHANGE_TIME = "CHANGE_TIME"
    CHANGE_DURATION = "CHANGE_DURATION"
    CHANGE_GOAL = "CHANGE_GOAL"
    CHANGE_CONSTRAINT = "CHANGE_CONSTRAINT"


class ContextState(StrEnum):
    KNOWN = "KNOWN"
    MISSING = "MISSING"
    NOT_LOADED = "NOT_LOADED"
    STALE = "STALE"
    ERROR = "ERROR"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


PLAN_SCHEMA_VERSION: Final[str] = "plan-v2.0"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextValue:
    """Authoritative value plus its availability state; never default to zero."""

    value: Any
    state: ContextState
    source: str

    @classmethod
    def known(cls, value: Any, *, source: str) -> "ContextValue":
        return cls(value=value, state=ContextState.KNOWN, source=source)

    @classmethod
    def unavailable(cls, state: ContextState, *, source: str) -> "ContextValue":
        if state is ContextState.KNOWN:
            raise ValueError("KNOWN_CONTEXT_REQUIRES_VALUE")
        return cls(value=None, state=state, source=source)


@dataclass(frozen=True, slots=True)
class PlanRequest:
    domain: PlanDomain
    period_start: date
    period_end: date
    timezone: str
    goal_override: str | None = None
    schedule_constraints: tuple[str, ...] = ()
    temporary_preferences: tuple[str, ...] = ()
    temporary_exclusions: tuple[str, ...] = ()
    requested_modifications: tuple[str, ...] = ()
    request_source: str = "CHAT"

    def __post_init__(self) -> None:
        if self.period_end < self.period_start:
            raise ValueError("INVALID_PLAN_PERIOD")
        if (self.period_end - self.period_start).days > 119:
            raise ValueError("PLAN_PERIOD_EXCEEDS_120_DAYS")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("INVALID_PLAN_TIMEZONE") from exc
        if self.domain is PlanDomain.COMBINED_HEALTH and self.goal_override is None:
            # A combined container has no formula of its own; the optional
            # goal label remains only explanatory metadata.
            return

    @property
    def duration_days(self) -> int:
        return (self.period_end - self.period_start).days + 1

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class PlanItem:
    plan_item_id: str
    scheduled_date: date
    schedule_slot: str
    item_type: PlanItemType
    canonical_refs: dict[str, Any]
    status: PlanItemStatus = PlanItemStatus.PLANNED
    reason_codes: tuple[str, ...] = ()
    policy_provenance: tuple[str, ...] = ()
    content: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class PlanValidationIssue:
    code: str
    severity: str
    plan_item_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlanValidationResult:
    status: PlanValidationStatus
    issues: tuple[PlanValidationIssue, ...] = ()

    @property
    def hard_violation_count(self) -> int:
        return sum(issue.severity == "HARD" for issue in self.issues)

    @property
    def ready(self) -> bool:
        return self.status is PlanValidationStatus.READY and not self.hard_violation_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "hard_violation_count": self.hard_violation_count,
            "issues": [_json_value(asdict(issue)) for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class PlanRevision:
    plan_id: str
    domain: PlanDomain
    revision_id: str
    revision_number: int
    parent_revision_id: str | None
    owner_user_id: str
    request: PlanRequest
    lifecycle_status: PlanLifecycleStatus
    validation: PlanValidationResult
    policy_versions: dict[str, str]
    catalog_versions: dict[str, str]
    goal_snapshot: dict[str, Any]
    constraint_snapshot: dict[str, Any]
    items: tuple[PlanItem, ...]
    summary: dict[str, Any]
    explanation_metadata: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    plan_schema_version: str = PLAN_SCHEMA_VERSION

    @property
    def revision_content_hash(self) -> str:
        return content_hash(self.content_identity())

    @property
    def artifact_kind(self) -> PlanArtifactKind:
        return PlanArtifactKind.for_domain(self.domain)

    def content_identity(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "domain": self.domain.value,
            "revision_id": self.revision_id,
            "revision_number": self.revision_number,
            "parent_revision_id": self.parent_revision_id,
            "owner_user_id": self.owner_user_id,
            "request": self.request.to_dict(),
            "policy_versions": self.policy_versions,
            "catalog_versions": self.catalog_versions,
            "goal_snapshot": self.goal_snapshot,
            "constraint_snapshot": self.constraint_snapshot,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "explanation_metadata": self.explanation_metadata,
            "provenance": self.provenance,
            "plan_schema_version": self.plan_schema_version,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = _json_value(asdict(self))
        payload["revision_content_hash"] = self.revision_content_hash
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlanRevision":
        """Restore an exact server-created preview without involving an LLM."""

        request_raw = dict(raw["request"])
        request = PlanRequest(
            domain=PlanDomain(request_raw["domain"]),
            period_start=date.fromisoformat(str(request_raw["period_start"])),
            period_end=date.fromisoformat(str(request_raw["period_end"])),
            timezone=str(request_raw["timezone"]),
            goal_override=request_raw.get("goal_override"),
            schedule_constraints=tuple(request_raw.get("schedule_constraints") or ()),
            temporary_preferences=tuple(request_raw.get("temporary_preferences") or ()),
            temporary_exclusions=tuple(request_raw.get("temporary_exclusions") or ()),
            requested_modifications=tuple(request_raw.get("requested_modifications") or ()),
            request_source=str(request_raw.get("request_source") or "CHAT"),
        )
        validation_raw = dict(raw["validation"])
        validation = PlanValidationResult(
            status=PlanValidationStatus(validation_raw["status"]),
            issues=tuple(
                PlanValidationIssue(
                    code=str(issue["code"]),
                    severity=str(issue["severity"]),
                    plan_item_id=issue.get("plan_item_id"),
                )
                for issue in validation_raw.get("issues") or ()
            ),
        )
        items = tuple(
            PlanItem(
                plan_item_id=str(item["plan_item_id"]),
                scheduled_date=date.fromisoformat(str(item["scheduled_date"])),
                schedule_slot=str(item["schedule_slot"]),
                item_type=PlanItemType(item["item_type"]),
                canonical_refs=dict(item.get("canonical_refs") or {}),
                status=PlanItemStatus(item.get("status") or PlanItemStatus.PLANNED.value),
                reason_codes=tuple(item.get("reason_codes") or ()),
                policy_provenance=tuple(item.get("policy_provenance") or ()),
                content=dict(item.get("content") or {}),
            )
            for item in raw.get("items") or ()
        )
        created_at = datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00"))
        revision = cls(
            plan_id=str(raw["plan_id"]),
            domain=PlanDomain(raw["domain"]),
            revision_id=str(raw["revision_id"]),
            revision_number=int(raw["revision_number"]),
            parent_revision_id=raw.get("parent_revision_id"),
            owner_user_id=str(raw["owner_user_id"]),
            request=request,
            lifecycle_status=PlanLifecycleStatus(raw["lifecycle_status"]),
            validation=validation,
            policy_versions=dict(raw.get("policy_versions") or {}),
            catalog_versions=dict(raw.get("catalog_versions") or {}),
            goal_snapshot=dict(raw.get("goal_snapshot") or {}),
            constraint_snapshot=dict(raw.get("constraint_snapshot") or {}),
            items=items,
            summary=dict(raw.get("summary") or {}),
            explanation_metadata=dict(raw.get("explanation_metadata") or {}),
            provenance=dict(raw.get("provenance") or {}),
            created_at=created_at,
            plan_schema_version=str(raw.get("plan_schema_version") or PLAN_SCHEMA_VERSION),
        )
        expected_hash = raw.get("revision_content_hash")
        if expected_hash and revision.revision_content_hash != expected_hash:
            raise ValueError("PLAN_PREVIEW_HASH_MISMATCH")
        return revision


@dataclass(frozen=True, slots=True)
class PlanPatch:
    target_plan_id: str
    target_revision_id: str
    operation: PlanPatchOperation
    target_item_id: str | None
    requested_change: dict[str, Any]
    request_source: str
    reason: str
    expected_revision_number: int

    def __post_init__(self) -> None:
        if not self.target_plan_id or not self.target_revision_id:
            raise ValueError("PLAN_REVISION_IDENTITY_REQUIRED")
        if self.operation in {
            PlanPatchOperation.REMOVE_ITEM,
            PlanPatchOperation.REPLACE_ITEM,
            PlanPatchOperation.MOVE_ITEM,
            PlanPatchOperation.CHANGE_TIME,
            PlanPatchOperation.CHANGE_DURATION,
        } and not self.target_item_id:
            raise ValueError("PLAN_ITEM_ID_REQUIRED")


def new_plan_id() -> str:
    return str(uuid4())


def new_revision_id() -> str:
    return str(uuid4())


__all__ = [
    "ContextState", "ContextValue", "PLAN_SCHEMA_VERSION", "PlanDomain", "PlanArtifactKind",
    "PlanItem", "PlanItemStatus", "PlanItemType", "PlanLifecycleStatus",
    "PlanPatch", "PlanPatchOperation", "PlanRequest", "PlanRevision",
    "PlanValidationIssue", "PlanValidationResult", "PlanValidationStatus",
    "canonical_json", "content_hash", "new_plan_id", "new_revision_id",
]
