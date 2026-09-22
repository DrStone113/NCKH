"""PostgreSQL repository for Plan V2 enforced mode.

The P1 memory repository is deliberately useful only for shadow previews.  A
successful enforced write goes through this repository in one transaction and
is reported only after authoritative read-back proves the immutable identity.
No method in this module touches legacy plan or observation tables.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
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
    new_revision_id,
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
                await self._put_preview_in_session(session, revision)

    async def put_patch_preview(
        self, *, owner_user_id: str, before: PlanRevision, after: PlanRevision,
        action_id: str, actor_type: str, source_surface: str, operation: str,
        reason: str | None = None,
    ) -> PlanRevision:
        """Persist one typed patch preview and its audit event atomically."""
        if not action_id:
            raise PlanPersistenceError("PLAN_ACTION_ID_REQUIRED")
        async with self._session_factory() as session:
            async with session.begin():
                existing = (
                    await session.execute(
                        text(
                            """
                            SELECT plan_id::text, base_revision_id::text, preview_revision_id::text
                            FROM plan_v2_preview_actions
                            WHERE owner_user_id = :owner AND action_id = :action_id
                            FOR UPDATE
                            """
                        ),
                        {"owner": owner_user_id, "action_id": action_id},
                    )
                ).mappings().first()
                if existing is not None:
                    if str(existing["plan_id"]) != before.plan_id or str(existing["base_revision_id"]) != before.revision_id:
                        raise PlanPersistenceError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
                    row = (
                        await session.execute(
                            text(
                                """
                                SELECT revision_payload FROM plan_v2_previews
                                WHERE owner_user_id = :owner AND plan_id = CAST(:plan_id AS uuid)
                                  AND revision_id = CAST(:revision_id AS uuid) AND expires_at > NOW()
                                """
                            ),
                            {"owner": owner_user_id, "plan_id": before.plan_id, "revision_id": str(existing["preview_revision_id"])},
                        )
                    ).mappings().first()
                    if row is None:
                        raise PlanPersistenceError("PLAN_PREVIEW_NOT_FOUND")
                    return PlanRevision.from_dict(_as_dict(row["revision_payload"]))
                await self._put_preview_in_session(session, after)
                await self._insert_change_event(
                    session, owner_user_id=owner_user_id, plan_id=after.plan_id,
                    from_revision_id=before.revision_id, to_revision_id=None,
                    actor_type=actor_type, source_surface=source_surface,
                    operation=operation, before_payload=before.to_dict(),
                    after_payload=after.to_dict(), reason=reason,
                    correlation_id=action_id,
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO plan_v2_preview_actions (
                            owner_user_id, action_id, plan_id, base_revision_id,
                            preview_revision_id, preview_content_hash
                        ) VALUES (
                            :owner, :action_id, CAST(:plan_id AS uuid), CAST(:base_revision_id AS uuid),
                            CAST(:preview_revision_id AS uuid), :content_hash
                        )
                        """
                    ),
                    {
                        "owner": owner_user_id, "action_id": action_id, "plan_id": after.plan_id,
                        "base_revision_id": before.revision_id, "preview_revision_id": after.revision_id,
                        "content_hash": after.revision_content_hash,
                    },
                )
        return after

    async def _put_preview_in_session(self, session: AsyncSession, revision: PlanRevision) -> None:
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
                "owner": revision.owner_user_id, "plan_id": revision.plan_id,
                "revision_id": revision.revision_id, "content_hash": revision.revision_content_hash,
                "payload": canonical_json(revision.to_dict()),
            },
        )

    async def record_preview_change_event(
        self, *, owner_user_id: str, before: PlanRevision, after: PlanRevision,
        actor_type: str = "USER", source_surface: str = "PLAN_UI",
        operation: str = "PATCH_PREVIEW", reason: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Record a preview mutation without promoting it to authoritative state."""
        async with self._session_factory() as session:
            async with session.begin():
                await self._insert_change_event(
                    session, owner_user_id=owner_user_id, plan_id=after.plan_id,
                    # Preview IDs only exist in plan_v2_previews until an
                    # explicit exact save promotes them.  The FK-backed audit
                    # event therefore links to its authoritative base and
                    # carries the prospective revision in after_payload.
                    from_revision_id=before.revision_id, to_revision_id=None,
                    actor_type=actor_type, source_surface=source_surface,
                    operation=operation, before_payload=before.to_dict(),
                    after_payload=after.to_dict(), reason=reason,
                    correlation_id=correlation_id,
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
            if domain is PlanDomain.COMBINED_HEALTH:
                query = """
                    SELECT id::text AS revision_id, plan_id::text AS plan_id
                    FROM plan_v2_revisions
                    WHERE owner_user_id = :owner AND domain = :domain
                      AND lifecycle_status = 'ACTIVE'
                """ + where_date + " ORDER BY revision_number DESC LIMIT 1"
            else:
                parameters["content_domain"] = domain.value
                query = """
                    SELECT c.revision_id::text AS revision_id, c.plan_id::text AS plan_id
                    FROM plan_v2_active_claims c
                    JOIN plan_v2_revisions r ON r.id = c.revision_id
                    WHERE c.owner_user_id = :owner AND c.content_domain = :content_domain
                      AND r.lifecycle_status = 'ACTIVE'
                """ + (
                    " AND c.effective_period @> :local_date"
                    if local_date is not None else ""
                ) + " ORDER BY r.revision_number DESC LIMIT 1"
            row = (await session.execute(text(query), parameters)).mappings().first()
            if row is None:
                return None
            return await self._get_in_session(session, owner_user_id, str(row["plan_id"]), str(row["revision_id"]))

    async def list_owned(
        self, owner_user_id: str, *, artifact_kind: PlanArtifactKind | None = None
    ) -> tuple[PlanRevision, ...]:
        """Return the newest immutable revision of every plan owned by a principal.

        This is intentionally repository-backed rather than chat-history-backed:
        a chat card is a useful historical presentation, but it cannot decide
        which persisted revision is authoritative for a user.
        """

        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        async with self._session_factory() as session:
            query = """
                SELECT DISTINCT ON (r.plan_id) r.plan_id::text AS plan_id, r.id::text AS revision_id
                FROM plan_v2_revisions r
                JOIN plan_v2_plans p ON p.id = r.plan_id
                WHERE r.owner_user_id = :owner
            """
            parameters: dict[str, Any] = {"owner": owner_user_id}
            if artifact_kind is not None:
                # Do not bind an untyped NULL into ``:kind IS NULL`` with
                # asyncpg: PostgreSQL cannot infer that parameter's type.
                query += " AND p.artifact_kind = :artifact_kind"
                parameters["artifact_kind"] = artifact_kind.value
            query += " ORDER BY r.plan_id, r.revision_number DESC"
            rows = (
                await session.execute(
                    text(query),
                    parameters,
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

    async def list_history(self, owner_user_id: str, plan_id: str) -> tuple[PlanRevision, ...]:
        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id::text AS revision_id
                        FROM plan_v2_revisions
                        WHERE owner_user_id = :owner AND plan_id = CAST(:plan_id AS uuid)
                        ORDER BY revision_number DESC
                        """
                    ),
                    {"owner": owner_user_id, "plan_id": plan_id},
                )
            ).mappings().all()
            revisions = [
                await self._get_in_session(session, owner_user_id, plan_id, str(row["revision_id"]))
                for row in rows
            ]
        return tuple(revision for revision in revisions if revision is not None)

    async def save_exact_revision(
        self,
        *,
        owner_user_id: str,
        revision: PlanRevision,
        expected_content_hash: str,
        action_id: str,
        activate: bool,
        replace_conflicts: bool = False,
        actor_type: str = "SYSTEM",
        source_surface: str = "CHAT",
        reason: str | None = None,
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
                        await self._prepare_activation(session, stored, replace_conflicts=replace_conflicts)
                    await self._insert_revision(session, stored)
                    await self._insert_items(session, stored)
                    if activate:
                        await self._insert_active_claims(session, stored)
                    await self._insert_change_event(
                        session, owner_user_id=owner_user_id, plan_id=stored.plan_id,
                        to_revision_id=stored.revision_id, actor_type=actor_type,
                        source_surface=source_surface, operation="SAVE",
                        after_payload=stored.to_dict(), reason=reason,
                        correlation_id=action_id,
                    )
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

    async def attach_standalone_to_combined(
        self,
        *,
        owner_user_id: str,
        combined_plan_id: str,
        base_revision_id: str,
        expected_combined_content_hash: str,
        source_plan_id: str,
        source_revision_id: str,
        expected_source_content_hash: str,
        action_id: str,
        actor_type: str = "USER",
        source_surface: str = "PLAN_UI",
        reason: str | None = None,
    ) -> PlanRevision:
        """Transfer a standalone artifact into a combined revision atomically.

        The source item's logical IDs are deliberately retained.  A retry uses
        the durable action ledger, while a stale source/base identity is
        rejected before any status or active claim is changed.
        """
        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        if not action_id:
            raise PlanPersistenceError("PLAN_ACTION_ID_REQUIRED")
        async with self._session_factory() as session:
            try:
                async with session.begin():
                    duplicate = (
                        await session.execute(
                            text(
                                """
                                SELECT combined_plan_id::text, base_revision_id::text,
                                       source_plan_id::text, source_revision_id::text,
                                       target_revision_id::text, combined_content_hash,
                                       source_content_hash
                                FROM plan_v2_attach_actions
                                WHERE owner_user_id = :owner AND action_id = :action_id
                                FOR UPDATE
                                """
                            ),
                            {"owner": owner_user_id, "action_id": action_id},
                        )
                    ).mappings().first()
                    if duplicate is not None:
                        if (
                            str(duplicate["combined_plan_id"]) != combined_plan_id
                            or str(duplicate["base_revision_id"]) != base_revision_id
                            or str(duplicate["source_plan_id"]) != source_plan_id
                            or str(duplicate["source_revision_id"]) != source_revision_id
                            or str(duplicate["combined_content_hash"]) != expected_combined_content_hash
                            or str(duplicate["source_content_hash"]) != expected_source_content_hash
                        ):
                            raise PlanPersistenceError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
                        result = await self._get_in_session(
                            session, owner_user_id, combined_plan_id, str(duplicate["target_revision_id"])
                        )
                        if result is None:
                            raise PlanPersistenceError("PLAN_READBACK_FAILED")
                        return result

                    combined = await self._get_in_session(
                        session, owner_user_id, combined_plan_id, base_revision_id, for_update=True
                    )
                    source = await self._get_in_session(
                        session, owner_user_id, source_plan_id, source_revision_id, for_update=True
                    )
                    if combined is None or source is None:
                        raise PlanAuthorizationError("PLAN_NOT_FOUND")
                    if combined.domain is not PlanDomain.COMBINED_HEALTH:
                        raise PlanPersistenceError("ATTACH_TARGET_MUST_BE_COMBINED_PLAN")
                    if source.domain not in {PlanDomain.NUTRITION, PlanDomain.WORKOUT}:
                        raise PlanPersistenceError("ATTACH_SOURCE_MUST_BE_STANDALONE")
                    if combined.revision_content_hash != expected_combined_content_hash:
                        raise PlanPersistenceError("PLAN_CONTENT_HASH_MISMATCH")
                    if source.revision_content_hash != expected_source_content_hash:
                        raise PlanPersistenceError("PLAN_CONTENT_HASH_MISMATCH")
                    if combined.lifecycle_status in {
                        PlanLifecycleStatus.CANCELLED,
                        PlanLifecycleStatus.COMPLETED,
                        PlanLifecycleStatus.SUPERSEDED,
                    } or source.lifecycle_status in {
                        PlanLifecycleStatus.CANCELLED,
                        PlanLifecycleStatus.COMPLETED,
                        PlanLifecycleStatus.SUPERSEDED,
                    }:
                        raise PlanPersistenceError("ATTACH_TERMINAL_PLAN_FORBIDDEN")
                    current_source = await self._get_in_session(
                        session, owner_user_id, source_plan_id, None, for_update=True
                    )
                    if current_source is None or current_source.revision_id != source_revision_id:
                        raise PlanPersistenceError("PLAN_REVISION_CONFLICT")
                    current_combined = await self._get_in_session(
                        session, owner_user_id, combined_plan_id, None, for_update=True
                    )
                    if current_combined is None or current_combined.revision_id != base_revision_id:
                        raise PlanPersistenceError("PLAN_REVISION_CONFLICT")
                    existing_ids = {item.plan_item_id for item in combined.items}
                    source_ids = {item.plan_item_id for item in source.items}
                    if existing_ids.intersection(source_ids):
                        raise PlanPersistenceError("PLAN_ITEM_ALREADY_OWNED")

                    merged_summary = dict(combined.summary)
                    merged_summary["attached_source_count"] = int(
                        merged_summary.get("attached_source_count", 0)
                    ) + 1
                    merged_provenance = dict(combined.provenance)
                    merged_provenance["last_ownership_transfer"] = {
                        "source_plan_id": source.plan_id,
                        "source_revision_id": source.revision_id,
                        "source_domain": source.domain.value,
                        "action_id": action_id,
                    }
                    transferred = replace(
                        combined,
                        revision_id=new_revision_id(),
                        revision_number=combined.revision_number + 1,
                        parent_revision_id=combined.revision_id,
                        items=(*combined.items, *source.items),
                        summary=merged_summary,
                        provenance=merged_provenance,
                        created_at=datetime.now(timezone.utc),
                    )
                    await self._assert_parent_is_current(session, transferred)

                    # Supersede both prior owners only in this transaction;
                    # the new combined revision inherits the combined status.
                    await session.execute(
                        text("UPDATE plan_v2_revisions SET lifecycle_status = 'SUPERSEDED' WHERE id = CAST(:id AS uuid)"),
                        {"id": combined.revision_id},
                    )
                    await session.execute(
                        text("UPDATE plan_v2_revisions SET lifecycle_status = 'SUPERSEDED' WHERE id = CAST(:id AS uuid)"),
                        {"id": source.revision_id},
                    )
                    await self._clear_active_claims(session, combined)
                    await self._clear_active_claims(session, source)
                    await self._insert_revision(session, transferred)
                    await self._insert_items(session, transferred)
                    if transferred.lifecycle_status is PlanLifecycleStatus.ACTIVE:
                        await self._prepare_activation(session, transferred, replace_conflicts=False)
                        await self._insert_active_claims(session, transferred)
                    await self._insert_change_event(
                        session, owner_user_id=owner_user_id, plan_id=combined.plan_id,
                        from_revision_id=combined.revision_id, to_revision_id=transferred.revision_id,
                        actor_type=actor_type, source_surface=source_surface,
                        operation="ATTACH_TRANSFER_IN", affected_item_ids=sorted(source_ids),
                        before_payload=combined.to_dict(), after_payload=transferred.to_dict(),
                        reason=reason or "EXPLICIT_OWNERSHIP_TRANSFER", correlation_id=action_id,
                    )
                    superseded_source = replace(source, lifecycle_status=PlanLifecycleStatus.SUPERSEDED)
                    await self._insert_change_event(
                        session, owner_user_id=owner_user_id, plan_id=source.plan_id,
                        from_revision_id=source.revision_id, to_revision_id=None,
                        actor_type=actor_type, source_surface=source_surface,
                        operation="ATTACH_TRANSFER_OUT", affected_item_ids=sorted(source_ids),
                        before_payload=source.to_dict(), after_payload=superseded_source.to_dict(),
                        reason=reason or "EXPLICIT_OWNERSHIP_TRANSFER", correlation_id=action_id,
                    )
                    await session.execute(
                        text(
                            """
                            INSERT INTO plan_v2_attach_actions (
                                owner_user_id, action_id, combined_plan_id, base_revision_id,
                                source_plan_id, source_revision_id, target_revision_id,
                                combined_content_hash, source_content_hash
                            ) VALUES (
                                :owner, :action_id, CAST(:combined_plan_id AS uuid), CAST(:base_revision_id AS uuid),
                                CAST(:source_plan_id AS uuid), CAST(:source_revision_id AS uuid), CAST(:target_revision_id AS uuid),
                                :combined_content_hash, :source_content_hash
                            )
                            """
                        ),
                        {
                            "owner": owner_user_id, "action_id": action_id,
                            "combined_plan_id": combined_plan_id, "base_revision_id": base_revision_id,
                            "source_plan_id": source_plan_id, "source_revision_id": source_revision_id,
                            "target_revision_id": transferred.revision_id,
                            "combined_content_hash": expected_combined_content_hash,
                            "source_content_hash": expected_source_content_hash,
                        },
                    )
                    verified = await self._get_in_session(
                        session, owner_user_id, transferred.plan_id, transferred.revision_id
                    )
                    self._assert_readback(transferred, verified)
            except (PlanPersistenceError, PlanAuthorizationError):
                raise
            except Exception as exc:
                raise PlanPersistenceError("PLAN_PERSISTENCE_TRANSACTION_FAILED") from exc
        read_back = await self.get(owner_user_id, transferred.plan_id, transferred.revision_id)
        self._assert_readback(transferred, read_back)
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
        replace_conflicts: bool = False,
        actor_type: str = "SYSTEM",
        source_surface: str = "CHAT",
        reason: str | None = None,
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
                        await self._prepare_activation(session, changed, replace_conflicts=replace_conflicts)
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
                    if status is PlanLifecycleStatus.ACTIVE:
                        await self._insert_active_claims(session, changed)
                    elif status in {
                        PlanLifecycleStatus.PAUSED,
                        PlanLifecycleStatus.CANCELLED,
                        PlanLifecycleStatus.COMPLETED,
                        PlanLifecycleStatus.SUPERSEDED,
                    }:
                        await self._clear_active_claims(session, changed)
                    await self._insert_change_event(
                        session, owner_user_id=owner_user_id, plan_id=changed.plan_id,
                        from_revision_id=current.revision_id, to_revision_id=changed.revision_id,
                        actor_type=actor_type, source_surface=source_surface,
                        operation="SET_STATUS", before_payload=current.to_dict(),
                        after_payload=changed.to_dict(), reason=reason,
                        correlation_id=action_id,
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
                INSERT INTO plan_v2_plans (id, owner_user_id, domain, artifact_kind, plan_schema_version)
                VALUES (CAST(:plan_id AS uuid), :owner, :domain, :artifact_kind, :schema)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "plan_id": revision.plan_id, "owner": revision.owner_user_id,
                "domain": revision.domain.value, "artifact_kind": revision.artifact_kind.value,
                "schema": revision.plan_schema_version,
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

    async def _prepare_activation(
        self, session: AsyncSession, revision: PlanRevision, *, replace_conflicts: bool
    ) -> None:
        """Reject active overlap by default; replacement must be explicit."""
        if not replace_conflicts:
            domains = (
                ("NUTRITION", "WORKOUT")
                if revision.domain is PlanDomain.COMBINED_HEALTH
                else (revision.domain.value,)
            )
            row = (
                await session.execute(
                    text(
                        """
                        SELECT content_domain
                        FROM plan_v2_active_claims
                        WHERE owner_user_id = :owner
                          AND content_domain = ANY(:domains)
                          AND effective_period && daterange(:period_start, :period_end, '[]')
                          AND NOT (plan_id = CAST(:plan_id AS uuid) AND revision_id = CAST(:revision_id AS uuid))
                        LIMIT 1
                        """
                    ),
                    {
                        "owner": revision.owner_user_id, "domains": list(domains),
                        "period_start": revision.request.period_start,
                        "period_end": revision.request.period_end,
                        "plan_id": revision.plan_id, "revision_id": revision.revision_id,
                    },
                )
            ).first()
            if row is not None:
                raise PlanPersistenceError("ACTIVE_SCHEDULE_CONFLICT")
            return
        await self._supersede_active_overlaps(session, revision)

    async def _supersede_active_overlaps(self, session: AsyncSession, revision: PlanRevision) -> None:
        domains = (
            ("NUTRITION", "WORKOUT")
            if revision.domain is PlanDomain.COMBINED_HEALTH
            else (revision.domain.value,)
        )
        await session.execute(
            text(
                """
                UPDATE plan_v2_revisions
                SET lifecycle_status = 'SUPERSEDED'
                WHERE owner_user_id = :owner AND domain = ANY(:domains)
                  AND lifecycle_status = 'ACTIVE'
                  AND id <> CAST(:revision_id AS uuid)
                  AND period_start <= :period_end AND period_end >= :period_start
                """
            ),
            {
                "owner": revision.owner_user_id, "domains": list(domains),
                "revision_id": revision.revision_id, "period_start": revision.request.period_start,
                "period_end": revision.request.period_end,
            },
        )
        await session.execute(
            text(
                """
                DELETE FROM plan_v2_active_claims
                WHERE owner_user_id = :owner AND content_domain = ANY(:domains)
                  AND effective_period && daterange(:period_start, :period_end, '[]')
                """
            ),
            {
                "owner": revision.owner_user_id, "domains": list(domains),
                "period_start": revision.request.period_start,
                "period_end": revision.request.period_end,
            },
        )

    async def _insert_active_claims(self, session: AsyncSession, revision: PlanRevision) -> None:
        domains = (
            ("NUTRITION", "WORKOUT")
            if revision.domain is PlanDomain.COMBINED_HEALTH
            else (revision.domain.value,)
        )
        for domain in domains:
            await session.execute(
                text(
                    """
                    INSERT INTO plan_v2_active_claims (
                        owner_user_id, content_domain, plan_id, revision_id, effective_period
                    ) VALUES (
                        :owner, :domain, CAST(:plan_id AS uuid), CAST(:revision_id AS uuid),
                        daterange(:period_start, :period_end, '[]')
                    ) ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "owner": revision.owner_user_id, "domain": domain,
                    "plan_id": revision.plan_id, "revision_id": revision.revision_id,
                    "period_start": revision.request.period_start,
                    "period_end": revision.request.period_end,
                },
            )

    async def _clear_active_claims(self, session: AsyncSession, revision: PlanRevision) -> None:
        await session.execute(
            text(
                """
                DELETE FROM plan_v2_active_claims
                WHERE owner_user_id = :owner AND plan_id = CAST(:plan_id AS uuid)
                  AND revision_id = CAST(:revision_id AS uuid)
                """
            ),
            {"owner": revision.owner_user_id, "plan_id": revision.plan_id, "revision_id": revision.revision_id},
        )

    async def _insert_change_event(
        self, session: AsyncSession, *, owner_user_id: str, plan_id: str,
        from_revision_id: str | None = None, to_revision_id: str | None = None,
        actor_type: str, source_surface: str, operation: str,
        before_payload: dict[str, Any] | None = None,
        after_payload: dict[str, Any] | None = None,
        affected_item_ids: list[str] | None = None,
        reason: str | None = None, correlation_id: str | None = None,
    ) -> None:
        from uuid import uuid4
        await session.execute(
            text(
                """
                INSERT INTO plan_v2_change_events (
                    event_id, owner_user_id, plan_id, from_revision_id, to_revision_id,
                    actor_type, source_surface, operation, affected_item_ids,
                    before_payload, after_payload, reason, correlation_id
                ) VALUES (
                    CAST(:event_id AS uuid), :owner, CAST(:plan_id AS uuid),
                    CAST(:from_revision_id AS uuid), CAST(:to_revision_id AS uuid),
                    :actor_type, :source_surface, :operation, CAST(:affected_item_ids AS jsonb),
                    CAST(:before_payload AS jsonb), CAST(:after_payload AS jsonb),
                    :reason, :correlation_id
                )
                """
            ),
            {
                "event_id": str(uuid4()), "owner": owner_user_id, "plan_id": plan_id,
                "from_revision_id": from_revision_id, "to_revision_id": to_revision_id,
                "actor_type": actor_type, "source_surface": source_surface,
                "operation": operation,
                "affected_item_ids": _json(affected_item_ids or []),
                "before_payload": _json(before_payload) if before_payload is not None else None,
                "after_payload": _json(after_payload) if after_payload is not None else None,
                "reason": reason, "correlation_id": correlation_id,
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
