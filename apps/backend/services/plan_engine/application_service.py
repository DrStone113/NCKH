"""Single application boundary for planned Plan V2 state.

Chat, HTTP and mobile projections call this service instead of choosing a
repository or rebuilding a draft themselves.  The service intentionally does
not write meal-consumption or workout-performance observations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from db.database import AsyncSessionLocal

from .contracts import PlanLifecycleStatus, PlanPatch, PlanRevision
from .engine import MemoryPlanRepository, PlanContextResolver, PlanEngine
from .persistence import PlanAuthorizationError, PlanSqlRepository


class PlanApplicationService:
    def __init__(self, repository: PlanSqlRepository | None = None) -> None:
        self.repository = repository or PlanSqlRepository()

    async def preview(self, revision: PlanRevision) -> PlanRevision:
        await self.repository.put_preview(revision)
        return revision

    async def revise_preview(
        self, *, owner_user_id: str, patch: PlanPatch, action_id: str,
        source_surface: str = "PLAN_UI", reason: str | None = None,
    ) -> PlanRevision:
        current = await self.repository.get(owner_user_id, patch.target_plan_id, patch.target_revision_id)
        if current is None:
            raise PlanAuthorizationError("PLAN_NOT_FOUND")
        memory = MemoryPlanRepository()
        memory.put(current)
        revised = PlanEngine(memory).revise(
            PlanContextResolver.resolve(owner_user_id, {"user_id": owner_user_id}), patch
        )
        return await self.repository.put_patch_preview(
            owner_user_id=owner_user_id, before=current, after=revised,
            action_id=action_id,
            actor_type="USER", source_surface=source_surface,
            operation=f"PATCH_{patch.operation.value}", reason=reason or patch.reason,
        )

    async def save_exact(
        self,
        *,
        owner_user_id: str,
        plan_id: str,
        revision_id: str,
        content_hash: str,
        action_id: str,
        actor_type: str = "USER",
        source_surface: str = "CHAT",
    ) -> PlanRevision:
        preview = await self.repository.get_preview(owner_user_id, plan_id, revision_id)
        if preview is None:
            raise PlanAuthorizationError("PLAN_NOT_FOUND")
        return await self.repository.save_exact_revision(
            owner_user_id=owner_user_id,
            revision=preview,
            expected_content_hash=content_hash,
            action_id=action_id,
            activate=False,
            actor_type=actor_type,
            source_surface=source_surface,
            reason="EXPLICIT_USER_SAVE",
        )

    async def set_lifecycle(
        self,
        *,
        owner_user_id: str,
        plan_id: str,
        revision_id: str,
        expected_revision_number: int,
        status: PlanLifecycleStatus,
        action_id: str,
        replace_conflicts: bool = False,
        actor_type: str = "USER",
        source_surface: str = "CHAT",
    ) -> PlanRevision:
        return await self.repository.set_status(
            owner_user_id=owner_user_id,
            plan_id=plan_id,
            revision_id=revision_id,
            expected_revision_number=expected_revision_number,
            status=status,
            action_id=action_id,
            replace_conflicts=replace_conflicts,
            actor_type=actor_type,
            source_surface=source_surface,
            reason="EXPLICIT_LIFECYCLE_ACTION",
        )

    async def history(self, *, owner_user_id: str, plan_id: str) -> tuple[PlanRevision, ...]:
        return await self.repository.list_history(owner_user_id, plan_id)

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
        source_surface: str = "PLAN_UI",
    ) -> PlanRevision:
        return await self.repository.attach_standalone_to_combined(
            owner_user_id=owner_user_id,
            combined_plan_id=combined_plan_id,
            base_revision_id=base_revision_id,
            expected_combined_content_hash=expected_combined_content_hash,
            source_plan_id=source_plan_id,
            source_revision_id=source_revision_id,
            expected_source_content_hash=expected_source_content_hash,
            action_id=action_id,
            actor_type="USER",
            source_surface=source_surface,
            reason="EXPLICIT_OWNERSHIP_TRANSFER",
        )

    async def create_pending_action(
        self,
        *,
        owner_user_id: str,
        session_id: str | None,
        action_type: str,
        tool_name: str,
        plan_id: str,
        revision_id: str,
        content_hash: str,
        payload: dict[str, Any],
        ttl_minutes: int = 20,
        action_id: str | None = None,
    ) -> str:
        if not owner_user_id or owner_user_id == "anonymous":
            raise PlanAuthorizationError("AUTHENTICATED_PRINCIPAL_REQUIRED")
        now = datetime.now(timezone.utc)
        resolved_action_id = action_id or f"pa_{uuid4().hex}"
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO plan_v2_pending_actions (
                            owner_user_id, action_id, session_id, action_type, tool_name,
                            target_plan_id, target_revision_id, target_content_hash,
                            payload, status, created_at, expires_at
                        ) VALUES (
                            :owner, :action_id, :session_id, :action_type, :tool_name,
                            CAST(:plan_id AS uuid), CAST(:revision_id AS uuid), :content_hash,
                            CAST(:payload AS jsonb), 'PENDING_CONFIRMATION', :created_at,
                            :expires_at
                        )
                        ON CONFLICT (owner_user_id, action_id) DO NOTHING
                        """
                    ),
                    {
                        "owner": owner_user_id, "action_id": resolved_action_id,
                        "session_id": session_id, "action_type": action_type,
                        "tool_name": tool_name, "plan_id": plan_id,
                        "revision_id": revision_id, "content_hash": content_hash,
                        "payload": __import__("json").dumps(payload, ensure_ascii=False),
                        "created_at": now, "expires_at": now + timedelta(minutes=ttl_minutes),
                    },
                )
        return resolved_action_id

    async def claim_pending_confirmation(
        self, *, owner_user_id: str, action_id: str
    ) -> dict[str, Any] | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT action_id, target_plan_id::text AS plan_id,
                                   target_revision_id::text AS revision_id,
                                   target_content_hash, payload, status, expires_at
                            FROM plan_v2_pending_actions
                            WHERE owner_user_id = :owner AND action_id = :action_id
                            FOR UPDATE
                            """
                        ),
                        {"owner": owner_user_id, "action_id": action_id},
                    )
                ).mappings().first()
                if row is None:
                    return None
                if row["expires_at"] <= datetime.now(timezone.utc):
                    await session.execute(
                        text(
                            """
                            UPDATE plan_v2_pending_actions
                            SET status = 'EXPIRED'
                            WHERE owner_user_id = :owner AND action_id = :action_id
                            """
                        ),
                        {"owner": owner_user_id, "action_id": action_id},
                    )
                    return None
                if row["status"] != "PENDING_CONFIRMATION":
                    return dict(row)
                await session.execute(
                    text(
                        """
                        UPDATE plan_v2_pending_actions
                        SET status = 'EXECUTING', claimed_at = NOW()
                        WHERE owner_user_id = :owner AND action_id = :action_id
                        """
                    ),
                    {"owner": owner_user_id, "action_id": action_id},
                )
                result = dict(row)
                result["status"] = "EXECUTING"
                return result

    async def find_pending_for_confirmation(
        self, *, owner_user_id: str, session_id: str | None = None
    ) -> dict[str, Any] | None:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT action_id, session_id, action_type, tool_name,
                               target_plan_id::text AS plan_id,
                               target_revision_id::text AS revision_id,
                               target_content_hash, payload, status
                        FROM plan_v2_pending_actions
                        WHERE owner_user_id = :owner
                          AND (:session_id IS NULL OR session_id = :session_id)
                          AND status = 'PENDING_CONFIRMATION'
                          AND expires_at > NOW()
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"owner": owner_user_id, "session_id": session_id},
                )
            ).mappings().first()
        return dict(row) if row is not None else None

    async def complete_pending_action(
        self, *, owner_user_id: str, action_id: str, status: str = "EXECUTED"
    ) -> None:
        if status not in {"EXECUTED", "SUPERSEDED", "EXPIRED"}:
            raise ValueError("INVALID_PENDING_TERMINAL_STATUS")
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE plan_v2_pending_actions
                        SET status = :status, completed_at = NOW()
                        WHERE owner_user_id = :owner AND action_id = :action_id
                        """
                    ),
                    {"owner": owner_user_id, "action_id": action_id, "status": status},
                )

    async def release_pending_action(self, *, owner_user_id: str, action_id: str) -> None:
        """Return an executing confirmation to pending after a failed write."""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE plan_v2_pending_actions
                        SET status = 'PENDING_CONFIRMATION', claimed_at = NULL
                        WHERE owner_user_id = :owner AND action_id = :action_id
                          AND status = 'EXECUTING'
                        """
                    ),
                    {"owner": owner_user_id, "action_id": action_id},
                )

    async def list_change_events(
        self, *, owner_user_id: str, plan_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT event_id::text, from_revision_id::text,
                               to_revision_id::text, actor_type, source_surface,
                               operation, affected_item_ids, before_payload,
                               after_payload, reason, correlation_id, created_at
                        FROM plan_v2_change_events
                        WHERE owner_user_id = :owner AND plan_id = CAST(:plan_id AS uuid)
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"owner": owner_user_id, "plan_id": plan_id, "limit": max(1, min(limit, 500))},
                )
            ).mappings().all()
        return [dict(row) for row in rows]


__all__ = ["PlanApplicationService"]
