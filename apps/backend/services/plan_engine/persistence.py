"""PostgreSQL repository for Plan V2 enforced mode.

The P1 memory repository is deliberately useful only for shadow previews.  A
successful enforced write goes through this repository in one transaction and
is reported only after authoritative read-back proves the immutable identity.
No method in this module touches legacy plan or observation tables.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.database import AsyncSessionLocal

from .contracts import (
    PlanDomain,
    PlanItem,
    PlanItemStatus,
    PlanItemType,
    PlanLifecycleStatus,
    PlanRequest,
    PlanRevision,
    PlanValidationIssue,
    PlanValidationResult,
    PlanValidationStatus,
    canonical_json,
)
from .lifecycle import transition_allowed


class PlanPersistenceError(RuntimeError):
    """A fail-closed persistence result with a stable client-safe code."""


class PlanAuthorizationError(PlanPersistenceError):
    pass


def _json(value: Any) -> str:
    return canonical_json(value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    return []


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _day(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class PlanSqlRepository:
    """Owner-scoped immutable revision repository.

    ``session_factory`` is injectable so live PostgreSQL integration tests can
    use an isolated database.  The production default opens a real
    ``AsyncSession``; it intentionally does not accept ``ScopedSession``
    because that facade commits each statement and cannot provide a
    transaction.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession] = AsyncSessionLocal,
    ) -> None:
        self._session_factory = session_factory

    async def put_preview(self, revision: PlanRevision) -> None:
        """Persist an exact non-authoritative draft for restart-safe confirmation."""

        if not revision.owner_user_id or revision.owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO plan_v2_previews (
                            owner_user_id, plan_id, revision_id, content_hash, revision_payload
                        ) VALUES (
                            :owner, CAST(:plan_id AS uuid), CAST(:revision_id AS uuid),
                            :content_hash, CAST(:payload AS jsonb)
                        )
                        ON CONFLICT (owner_user_id, plan_id, revision_id)
                        DO UPDATE SET content_hash = EXCLUDED.content_hash,
                                      revision_payload = EXCLUDED.revision_payload,
                                      created_at = NOW(),
                                      expires_at = NOW() + INTERVAL '30 days'
                        """
                    ),
                    {
                        "owner": revision.owner_user_id,
                        "plan_id": revision.plan_id,
                        "revision_id": revision.revision_id,
                        "content_hash": revision.revision_content_hash,
                        "payload": canonical_json(revision.to_dict()),
                    },
                )

    async def get_preview(
        self, owner_user_id: str, plan_id: str, revision_id: str
    ) -> PlanRevision | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT revision_payload, content_hash
                        FROM plan_v2_previews
                        WHERE owner_user_id = :owner
                          AND plan_id = CAST(:plan_id AS uuid)
                          AND revision_id = CAST(:revision_id AS uuid)
                          AND expires_at > NOW()
                        """
                    ),
                    {"owner": owner_user_id, "plan_id": plan_id, "revision_id": revision_id},
                )
            ).mappings().first()
        if row is None:
            return None
        payload = _as_dict(row["revision_payload"])
        revision = PlanRevision.from_dict(payload)
        if (
            revision.owner_user_id != owner_user_id
            or revision.plan_id != plan_id
            or revision.revision_id != revision_id
            or revision.revision_content_hash != str(row["content_hash"])
        ):
            raise PlanPersistenceError("PLAN_PREVIEW_READBACK_MISMATCH")
        return revision

    async def get(
        self, owner_user_id: str, plan_id: str, revision_id: str | None = None
    ) -> PlanRevision | None:
        async with self._session_factory() as session:
            return await self._get_in_session(session, owner_user_id, plan_id, revision_id)

    async def get_active(
        self, owner_user_id: str, domain: PlanDomain, *, local_date: date | None = None
    ) -> PlanRevision | None:
        async with self._session_factory() as session:
            parameters: dict[str, Any] = {"owner": owner_user_id, "domain": domain.value}
            where_date = ""
            if local_date is not None:
                where_date = " AND period_start <= :local_date AND period_end >= :local_date"
                parameters["local_date"] = local_date
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id::text AS revision_id, plan_id::text AS plan_id
                        FROM plan_v2_revisions
                        WHERE owner_user_id = :owner AND domain = :domain
                          AND lifecycle_status = 'ACTIVE'
                        """ + where_date + " ORDER BY revision_number DESC LIMIT 1"
                    ),
                    parameters,
                )
            ).mappings().first()
            if row is None:
                return None
            return await self._get_in_session(session, owner_user_id, str(row["plan_id"]), str(row["revision_id"]))

    async def list_owned(self, owner_user_id: str) -> tuple[PlanRevision, ...]:
        """Return the newest immutable revision of every plan owned by a principal.

        This is intentionally repository-backed rather than chat-history-backed:
        a chat card is a useful historical presentation, but it cannot decide
        which persisted revision is authoritative for a user.
        """

        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT DISTINCT ON (plan_id) plan_id::text AS plan_id, id::text AS revision_id
                        FROM plan_v2_revisions
                        WHERE owner_user_id = :owner
                        ORDER BY plan_id, revision_number DESC
                        """
                    ),
                    {"owner": owner_user_id},
                )
            ).mappings().all()
            revisions = [
                await self._get_in_session(session, owner_user_id, str(row["plan_id"]), str(row["revision_id"]))
                for row in rows
            ]
        return tuple(
            sorted(
                (revision for revision in revisions if revision is not None),
                key=lambda revision: (revision.created_at, revision.revision_number),
                reverse=True,
            )
        )

    async def save_exact_revision(
        self,
        *,
        owner_user_id: str,
        revision: PlanRevision,
        expected_content_hash: str,
        action_id: str,
        activate: bool,
    ) -> PlanRevision:
        """Persist exactly the preview revision, atomically, then read it back."""

        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        if revision.owner_user_id != owner_user_id:
            raise PlanAuthorizationError("PLAN_OWNER_MISMATCH")
        if revision.revision_content_hash != expected_content_hash:
            raise PlanPersistenceError("PLAN_CONTENT_HASH_MISMATCH")
        if not revision.validation.ready:
            raise PlanPersistenceError("PLAN_NOT_READY")
        if revision.lifecycle_status not in {PlanLifecycleStatus.DRAFT, PlanLifecycleStatus.PENDING_CONFIRMATION}:
            raise PlanPersistenceError("INVALID_PLAN_SAVE_TRANSITION")

        stored_status = PlanLifecycleStatus.ACTIVE if activate else PlanLifecycleStatus.SAVED
        stored = replace(revision, lifecycle_status=stored_status)
        async with self._session_factory() as session:
            try:
                async with session.begin():
                    duplicate = await self._idempotent_revision(
                        session, owner_user_id, "SAVE", action_id, revision
                    )
                    if duplicate is not None:
                        return duplicate
                    await self._assert_parent_is_current(session, stored)
                    await self._insert_plan(session, stored)
                    if activate:
                        await self._supersede_active_overlaps(session, stored)
                    await self._insert_revision(session, stored)
                    await self._insert_items(session, stored)
                    await session.execute(
                        text(
                            """
                            INSERT INTO plan_v2_write_actions (
                                owner_user_id, operation, action_id, plan_id, revision_id,
                                content_hash, result_status
                            ) VALUES (
                                :owner, 'SAVE', :action_id, CAST(:plan_id AS uuid),
                                CAST(:revision_id AS uuid), :content_hash, :status
                            )
                            """
                        ),
                        {
                            "owner": owner_user_id, "action_id": action_id,
                            "plan_id": stored.plan_id, "revision_id": stored.revision_id,
                            "content_hash": stored.revision_content_hash, "status": stored_status.value,
                        },
                    )
                    verified = await self._get_in_session(
                        session, owner_user_id, stored.plan_id, stored.revision_id
                    )
                    self._assert_readback(stored, verified)
            except PlanPersistenceError:
                raise
            except Exception as exc:
                raise PlanPersistenceError("PLAN_PERSISTENCE_TRANSACTION_FAILED") from exc
        read_back = await self.get(owner_user_id, stored.plan_id, stored.revision_id)
        self._assert_readback(stored, read_back)
        return read_back  # type: ignore[return-value]

    async def set_status(
        self,
        *,
        owner_user_id: str,
        plan_id: str,
        revision_id: str,
        expected_revision_number: int,
        status: PlanLifecycleStatus,
        action_id: str,
    ) -> PlanRevision:
        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        async with self._session_factory() as session:
            try:
                async with session.begin():
                    current = await self._get_in_session(session, owner_user_id, plan_id, revision_id, for_update=True)
                    if current is None:
                        raise PlanAuthorizationError("PLAN_NOT_FOUND")
                    duplicate = await self._idempotent_status(
                        session, owner_user_id, "SET_STATUS", action_id, current
                    )
                    if duplicate is not None:
                        return duplicate
                    if current.revision_number != expected_revision_number:
                        raise PlanPersistenceError("PLAN_REVISION_CONFLICT")
                    if not transition_allowed(current.lifecycle_status, status):
                        raise PlanPersistenceError("INVALID_PLAN_LIFECYCLE_TRANSITION")
                    if status is PlanLifecycleStatus.ACTIVE and not current.validation.ready:
                        raise PlanPersistenceError("PLAN_NOT_READY")
                    changed = replace(current, lifecycle_status=status)
                    if status is PlanLifecycleStatus.ACTIVE:
                        await self._supersede_active_overlaps(session, changed)
                    await session.execute(
                        text(
                            """
                            UPDATE plan_v2_revisions
                            SET lifecycle_status = :status
                            WHERE id = CAST(:revision_id AS uuid)
                              AND plan_id = CAST(:plan_id AS uuid)
                              AND owner_user_id = :owner
                            """
                        ),
                        {"status": status.value, "revision_id": revision_id, "plan_id": plan_id, "owner": owner_user_id},
                    )
                    await session.execute(
                        text(
                            """
                            INSERT INTO plan_v2_write_actions (
                                owner_user_id, operation, action_id, plan_id, revision_id,
                                content_hash, result_status
                            ) VALUES (
                                :owner, 'SET_STATUS', :action_id, CAST(:plan_id AS uuid),
                                CAST(:revision_id AS uuid), :content_hash, :status
                            )
                            """
                        ),
                        {
                            "owner": owner_user_id, "action_id": action_id, "plan_id": plan_id,
                            "revision_id": revision_id, "content_hash": changed.revision_content_hash,
                            "status": status.value,
                        },
                    )
                    verified = await self._get_in_session(session, owner_user_id, plan_id, revision_id)
                    self._assert_readback(changed, verified)
            except PlanPersistenceError:
                raise
            except Exception as exc:
                raise PlanPersistenceError("PLAN_PERSISTENCE_TRANSACTION_FAILED") from exc
        read_back = await self.get(owner_user_id, plan_id, revision_id)
        self._assert_readback(changed, read_back)
        return read_back  # type: ignore[return-value]

    async def _idempotent_revision(
        self, session: AsyncSession, owner: str, operation: str, action_id: str, expected: PlanRevision
    ) -> PlanRevision | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT plan_id::text AS plan_id, revision_id::text AS revision_id,
                           content_hash
                    FROM plan_v2_write_actions
                    WHERE owner_user_id = :owner AND operation = :operation AND action_id = :action_id
                    FOR UPDATE
                    """
                ),
                {"owner": owner, "operation": operation, "action_id": action_id},
            )
        ).mappings().first()
        if row is None:
            return None
        if (
            str(row["plan_id"]) != expected.plan_id
            or str(row["revision_id"]) != expected.revision_id
            or str(row["content_hash"]) != expected.revision_content_hash
        ):
            raise PlanPersistenceError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
        return await self._get_in_session(session, owner, expected.plan_id, expected.revision_id)

    async def _idempotent_status(
        self, session: AsyncSession, owner: str, operation: str, action_id: str, expected: PlanRevision
    ) -> PlanRevision | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT plan_id::text AS plan_id, revision_id::text AS revision_id
                    FROM plan_v2_write_actions
                    WHERE owner_user_id = :owner AND operation = :operation AND action_id = :action_id
                    FOR UPDATE
                    """
                ),
                {"owner": owner, "operation": operation, "action_id": action_id},
            )
        ).mappings().first()
        if row is None:
            return None
        if str(row["plan_id"]) != expected.plan_id or str(row["revision_id"]) != expected.revision_id:
            raise PlanPersistenceError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
        return await self._get_in_session(session, owner, expected.plan_id, expected.revision_id)

    async def _assert_parent_is_current(self, session: AsyncSession, revision: PlanRevision) -> None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id::text AS revision_id, revision_number
                    FROM plan_v2_revisions
                    WHERE plan_id = CAST(:plan_id AS uuid) AND owner_user_id = :owner
                    ORDER BY revision_number DESC
                    LIMIT 1 FOR UPDATE
                    """
                ),
                {"plan_id": revision.plan_id, "owner": revision.owner_user_id},
            )
        ).mappings().first()
        if row is None:
            if revision.parent_revision_id is not None or revision.revision_number != 1:
                raise PlanPersistenceError("PLAN_REVISION_CONFLICT")
            return
        if (
            revision.parent_revision_id != str(row["revision_id"])
            or revision.revision_number != int(row["revision_number"]) + 1
        ):
            raise PlanPersistenceError("PLAN_REVISION_CONFLICT")

    async def _insert_plan(self, session: AsyncSession, revision: PlanRevision) -> None:
        await session.execute(
            text(
                """
                INSERT INTO plan_v2_plans (id, owner_user_id, domain, plan_schema_version)
                VALUES (CAST(:plan_id AS uuid), :owner, :domain, :schema)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "plan_id": revision.plan_id, "owner": revision.owner_user_id,
                "domain": revision.domain.value, "schema": revision.plan_schema_version,
            },
        )
        row = (
            await session.execute(
                text("SELECT owner_user_id, domain FROM plan_v2_plans WHERE id = CAST(:plan_id AS uuid) FOR UPDATE"),
                {"plan_id": revision.plan_id},
            )
        ).mappings().first()
        if row is None or str(row["owner_user_id"]) != revision.owner_user_id or str(row["domain"]) != revision.domain.value:
            raise PlanAuthorizationError("PLAN_OWNER_MISMATCH")

    async def _insert_revision(self, session: AsyncSession, revision: PlanRevision) -> None:
        await session.execute(
            text(
                """
                INSERT INTO plan_v2_revisions (
                    id, plan_id, owner_user_id, domain, revision_number, parent_revision_id,
                    lifecycle_status, validation_status, hard_violation_count,
                    period_start, period_end, timezone, request_payload, policy_versions,
                    catalog_versions, goal_snapshot, constraint_snapshot, summary,
                    explanation_metadata, provenance, content_hash, created_at
                ) VALUES (
                    CAST(:revision_id AS uuid), CAST(:plan_id AS uuid), :owner, :domain,
                    :revision_number, CAST(:parent_revision_id AS uuid), :lifecycle_status,
                    :validation_status, :hard_violation_count, :period_start, :period_end,
                    :timezone, CAST(:request_payload AS jsonb), CAST(:policy_versions AS jsonb),
                    CAST(:catalog_versions AS jsonb), CAST(:goal_snapshot AS jsonb),
                    CAST(:constraint_snapshot AS jsonb), CAST(:summary AS jsonb),
                    CAST(:explanation_metadata AS jsonb), CAST(:provenance AS jsonb),
                    :content_hash, :created_at
                )
                """
            ),
            {
                "revision_id": revision.revision_id, "plan_id": revision.plan_id,
                "owner": revision.owner_user_id, "domain": revision.domain.value,
                "revision_number": revision.revision_number, "parent_revision_id": revision.parent_revision_id,
                "lifecycle_status": revision.lifecycle_status.value,
                "validation_status": revision.validation.status.value,
                "hard_violation_count": revision.validation.hard_violation_count,
                "period_start": revision.request.period_start, "period_end": revision.request.period_end,
                "timezone": revision.request.timezone, "request_payload": _json(revision.request.to_dict()),
                "policy_versions": _json(revision.policy_versions), "catalog_versions": _json(revision.catalog_versions),
                "goal_snapshot": _json(revision.goal_snapshot), "constraint_snapshot": _json(revision.constraint_snapshot),
                "summary": _json(revision.summary), "explanation_metadata": _json(revision.explanation_metadata),
                "provenance": _json(revision.provenance), "content_hash": revision.revision_content_hash,
                "created_at": revision.created_at,
            },
        )

    async def _insert_items(self, session: AsyncSession, revision: PlanRevision) -> None:
        for item_order, item in enumerate(revision.items):
            storage_id = str(uuid5(NAMESPACE_URL, f"plan-v2-item-snapshot:{revision.revision_id}:{item.plan_item_id}"))
            await session.execute(
                text(
                    """
                    INSERT INTO plan_v2_items (
                        id, revision_id, plan_item_id, item_order, scheduled_date, schedule_slot, item_type, status,
                        canonical_refs, reason_codes, policy_provenance, planned_content
                    ) VALUES (
                        CAST(:storage_id AS uuid), CAST(:revision_id AS uuid), CAST(:item_id AS uuid), :item_order, :scheduled_date,
                        :schedule_slot, :item_type, :status, CAST(:canonical_refs AS jsonb),
                        CAST(:reason_codes AS jsonb), CAST(:policy_provenance AS jsonb),
                        CAST(:planned_content AS jsonb)
                    )
                    """
                ),
                {
                    "storage_id": storage_id, "item_id": item.plan_item_id, "revision_id": revision.revision_id, "item_order": item_order,
                    "scheduled_date": item.scheduled_date, "schedule_slot": item.schedule_slot,
                    "item_type": item.item_type.value, "status": item.status.value,
                    "canonical_refs": _json(item.canonical_refs), "reason_codes": _json(list(item.reason_codes)),
                    "policy_provenance": _json(list(item.policy_provenance)), "planned_content": _json(item.content),
                },
            )

    async def _supersede_active_overlaps(self, session: AsyncSession, revision: PlanRevision) -> None:
        if revision.domain is PlanDomain.COMBINED_HEALTH:
            return
        await session.execute(
            text(
                """
                UPDATE plan_v2_revisions
                SET lifecycle_status = 'SUPERSEDED'
                WHERE owner_user_id = :owner AND domain = :domain
                  AND lifecycle_status = 'ACTIVE'
                  AND id <> CAST(:revision_id AS uuid)
                  AND period_start <= :period_end AND period_end >= :period_start
                """
            ),
            {
                "owner": revision.owner_user_id, "domain": revision.domain.value,
                "revision_id": revision.revision_id, "period_start": revision.request.period_start,
                "period_end": revision.request.period_end,
            },
        )

    async def _get_in_session(
        self, session: AsyncSession, owner: str, plan_id: str, revision_id: str | None = None, *, for_update: bool = False
    ) -> PlanRevision | None:
        target = "AND r.id = CAST(:revision_id AS uuid)" if revision_id else ""
        locking = " FOR UPDATE" if for_update else ""
        row = (
            await session.execute(
                text(
                    """
                    SELECT r.id::text AS revision_id, r.plan_id::text AS plan_id,
                           r.owner_user_id, r.domain, r.revision_number,
                           r.parent_revision_id::text AS parent_revision_id,
                           r.lifecycle_status, r.validation_status, r.hard_violation_count,
                           r.period_start, r.period_end, r.timezone, r.request_payload,
                           r.policy_versions, r.catalog_versions, r.goal_snapshot,
                           r.constraint_snapshot, r.summary, r.explanation_metadata,
                           r.provenance, r.content_hash, r.created_at
                    FROM plan_v2_revisions r
                    JOIN plan_v2_plans p ON p.id = r.plan_id
                    WHERE r.plan_id = CAST(:plan_id AS uuid)
                      AND r.owner_user_id = :owner AND p.owner_user_id = :owner
                    """ + target + " ORDER BY r.revision_number DESC LIMIT 1" + locking
                ),
                {"owner": owner, "plan_id": plan_id, "revision_id": revision_id},
            )
        ).mappings().first()
        if row is None:
            return None
        item_rows = (
            await session.execute(
                text(
                    """
                    SELECT plan_item_id::text AS plan_item_id, scheduled_date, schedule_slot, item_type,
                           status, canonical_refs, reason_codes, policy_provenance, planned_content
                    FROM plan_v2_items
                    WHERE revision_id = CAST(:revision_id AS uuid)
                    ORDER BY item_order, id
                    """
                ),
                {"revision_id": str(row["revision_id"])},
            )
        ).mappings().all()
        request_payload = _as_dict(row["request_payload"])
        request = PlanRequest(
            domain=PlanDomain(str(request_payload.get("domain") or row["domain"])),
            period_start=_day(request_payload.get("period_start") or row["period_start"]),
            period_end=_day(request_payload.get("period_end") or row["period_end"]),
            timezone=str(request_payload.get("timezone") or row["timezone"]),
            goal_override=request_payload.get("goal_override"),
            schedule_constraints=tuple(_as_list(request_payload.get("schedule_constraints"))),
            temporary_preferences=tuple(_as_list(request_payload.get("temporary_preferences"))),
            temporary_exclusions=tuple(_as_list(request_payload.get("temporary_exclusions"))),
            requested_modifications=tuple(_as_list(request_payload.get("requested_modifications"))),
            request_source=str(request_payload.get("request_source") or "CHAT"),
        )
        issues = tuple(
            PlanValidationIssue(
                code=str(value.get("code") or "PERSISTED_VALIDATION_ISSUE"),
                severity=str(value.get("severity") or "HARD"),
                plan_item_id=value.get("plan_item_id"),
            )
            for value in _as_list(_as_dict(row["provenance"]).get("validation_issues"))
            if isinstance(value, dict)
        )
        validation = PlanValidationResult(PlanValidationStatus(str(row["validation_status"])), issues)
        # The migration stores the hard count as an authoritative check even
        # when old rows predate structured issue persistence.
        if validation.hard_violation_count != int(row["hard_violation_count"]):
            validation = PlanValidationResult(
                PlanValidationStatus(str(row["validation_status"])),
                tuple(
                    [*issues]
                    + [PlanValidationIssue("PERSISTED_HARD_VIOLATION", "HARD")]
                    * max(0, int(row["hard_violation_count"]) - validation.hard_violation_count)
                ),
            )
        items = tuple(
            PlanItem(
                plan_item_id=str(item["plan_item_id"]), scheduled_date=_day(item["scheduled_date"]),
                schedule_slot=str(item["schedule_slot"]), item_type=PlanItemType(str(item["item_type"])),
                canonical_refs=_as_dict(item["canonical_refs"]), status=PlanItemStatus(str(item["status"])),
                reason_codes=tuple(str(value) for value in _as_list(item["reason_codes"])),
                policy_provenance=tuple(str(value) for value in _as_list(item["policy_provenance"])),
                content=_as_dict(item["planned_content"]),
            )
            for item in item_rows
        )
        revision = PlanRevision(
            plan_id=str(row["plan_id"]), domain=PlanDomain(str(row["domain"])),
            revision_id=str(row["revision_id"]), revision_number=int(row["revision_number"]),
            parent_revision_id=row["parent_revision_id"], owner_user_id=str(row["owner_user_id"]),
            request=request, lifecycle_status=PlanLifecycleStatus(str(row["lifecycle_status"])),
            validation=validation, policy_versions=_as_dict(row["policy_versions"]),
            catalog_versions=_as_dict(row["catalog_versions"]), goal_snapshot=_as_dict(row["goal_snapshot"]),
            constraint_snapshot=_as_dict(row["constraint_snapshot"]), items=items,
            summary=_as_dict(row["summary"]), explanation_metadata=_as_dict(row["explanation_metadata"]),
            provenance=_as_dict(row["provenance"]), created_at=_dt(row["created_at"]),
        )
        if revision.revision_content_hash != str(row["content_hash"]):
            raise PlanPersistenceError("PLAN_READBACK_HASH_MISMATCH")
        return revision

    @staticmethod
    def _assert_readback(expected: PlanRevision, actual: PlanRevision | None) -> None:
        if actual is None:
            raise PlanPersistenceError("PLAN_READBACK_FAILED")
        if (
            actual.plan_id != expected.plan_id
            or actual.revision_id != expected.revision_id
            or actual.revision_number != expected.revision_number
            or actual.owner_user_id != expected.owner_user_id
            or actual.revision_content_hash != expected.revision_content_hash
            or actual.lifecycle_status != expected.lifecycle_status
            or actual.policy_versions != expected.policy_versions
            or actual.catalog_versions != expected.catalog_versions
            or actual.items != expected.items
        ):
            raise PlanPersistenceError("PLAN_READBACK_MISMATCH")


__all__ = ["PlanAuthorizationError", "PlanPersistenceError", "PlanSqlRepository"]
