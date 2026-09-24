"""Atomic, session- and owner-bound actions awaiting confirmation.

The store intentionally keeps execution state separate from chat history.  It
survives websocket reconnects in the running service, has a documented 20
minute confirmation TTL, and retains terminal state briefly so a second tab
receives ``ALREADY_EXECUTED`` instead of issuing a duplicate write.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Final
from uuid import uuid4


_AFFIRMATIVE: Final[frozenset[str]] = frozenset(
    {"có", "co", "ok", "oke", "đồng ý", "dong y", "yes", "y"}
)
_NEGATIVE: Final[frozenset[str]] = frozenset(
    {
        "không",
        "khong",
        "không cần",
        "khong can",
        "không lưu",
        "khong luu",
        "thôi",
        "thoi",
        "bỏ qua",
        "bo qua",
        "hủy",
        "huy",
        "no",
        "nope",
    }
)
_PENDING: Final[str] = "PENDING_CONFIRMATION"
_CLAIMED: Final[str] = "EXECUTING"
_EXECUTED: Final[str] = "EXECUTED"
_SUPERSEDED: Final[str] = "SUPERSEDED"
_EXPIRED: Final[str] = "EXPIRED"
_TERMINAL: Final[frozenset[str]] = frozenset({_EXECUTED, _SUPERSEDED, _EXPIRED})


def is_explicit_confirmation(text: str) -> bool:
    return " ".join(text.strip().lower().split()) in _AFFIRMATIVE


def is_explicit_rejection(text: str) -> bool:
    normalized = " ".join(text.strip().lower().replace(",", " ").replace(".", " ").split())
    return normalized in _NEGATIVE or any(
        phrase in normalized
        for phrase in ("đừng lưu", "không lưu", "thôi không", "chỉ xem")
    )


@dataclass(slots=True)
class PendingUserAction:
    action_id: str
    session_id: str
    owner_user_id: str
    action_type: str
    tool_name: str
    tool_arguments: dict[str, Any]
    target_id: str
    display_name: str
    created_at: datetime
    expires_at: datetime
    status: str = _PENDING
    persisted_reference_id: str | None = None
    # A write target can be a compound immutable identity.  Meal logging
    # continues to use a catalog id; Plan V2 uses plan/revision/hash.
    target_identity: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PendingActionResolution:
    status: str
    action: PendingUserAction | None = None


class PendingUserActionStore:
    """Thread-safe action lifecycle store.

    Product policy: users have 20 minutes to confirm an action. Terminal
    state is retained for one hour to make retries/multi-device confirmation
    idempotent and explainable. This is process-local operational state; it is
    never persisted as a normal chat message.
    """

    def __init__(
        self,
        ttl_minutes: int = 20,
        terminal_retention_minutes: int = 60,
    ) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._terminal_retention = timedelta(minutes=terminal_retention_minutes)
        self._actions: dict[str, PendingUserAction] = {}
        self._by_session: dict[str, list[str]] = {}
        self._dish_candidates: dict[
            tuple[str, str], tuple[dict[str, Any], dict[str, Any], datetime]
        ] = {}
        self._lock = threading.Lock()

    def create_action(
        self,
        session_id: str,
        *,
        owner_user_id: str,
        action_type: str,
        tool_name: str,
        tool_arguments: dict[str, Any],
        target_id: str,
        display_name: str,
        action_id: str | None = None,
        target_identity: dict[str, str] | None = None,
    ) -> PendingUserAction:
        now = datetime.now(timezone.utc)
        return PendingUserAction(
            action_id=action_id or f"pa_{uuid4().hex}",
            session_id=session_id,
            owner_user_id=owner_user_id or "anonymous",
            action_type=action_type,
            tool_name=tool_name,
            tool_arguments=dict(tool_arguments),
            target_id=target_id,
            display_name=display_name,
            created_at=now,
            expires_at=now + self._ttl,
            target_identity=dict(target_identity or {}),
        )

    def create_dish_log_action(
        self,
        session_id: str,
        *,
        owner_user_id: str,
        suggestion: dict[str, Any],
        suggestion_arguments: Any,
    ) -> PendingUserAction | None:
        """Create an exact write payload from a trusted catalog suggestion."""

        dish_id = suggestion.get("id")
        dish_name = suggestion.get("name")
        components = suggestion.get("components")
        if type(dish_id) is int and dish_id > 0:
            dish_id = str(dish_id)
        if (
            not isinstance(dish_id, str)
            or not dish_id.strip()
            or not isinstance(dish_name, str)
            or not dish_name.strip()
            or not isinstance(components, list)
        ):
            return None
        arguments = suggestion_arguments if isinstance(suggestion_arguments, dict) else {}
        meal_type = arguments.get("meal_type")
        if meal_type not in {"breakfast", "lunch", "dinner", "snack"}:
            return None
        allowed_component_keys = {
            "name", "serving_grams", "calories", "protein", "carbs", "fat",
        }
        copied_components = [
            {key: value for key, value in component.items() if key in allowed_component_keys}
            for component in components
            if isinstance(component, dict)
        ]
        if not copied_components:
            return None
        serving_grams = sum(
            float(component.get("serving_grams") or 0)
            for component in copied_components
            if isinstance(component.get("serving_grams"), (int, float))
        )
        action_id = f"pa_{uuid4().hex}"
        action = self.create_action(
            session_id,
            owner_user_id=owner_user_id,
            action_type="LOG_RECOMMENDED_DISH",
            tool_name="log_meal",
            tool_arguments={
                "meal_type": meal_type,
                "dish_name": dish_name.strip(),
                "catalog_dish_id": dish_id.strip(),
                "serving_grams": serving_grams if serving_grams > 0 else None,
                "components": copied_components,
                # Stable write key is reused for all retries of this action.
                "request_id": f"dish-log-{action_id}",
            },
            target_id=dish_id.strip(),
            display_name=dish_name.strip(),
            action_id=action_id,
        )
        return action

    def remember_dish_candidate(
        self,
        session_id: str,
        *,
        owner_user_id: str,
        suggestion: dict[str, Any],
        suggestion_arguments: Any,
    ) -> bool:
        """Cache a trusted catalog candidate for a later explicit write request."""

        action = self.create_dish_log_action(
            session_id,
            owner_user_id=owner_user_id,
            suggestion=suggestion,
            suggestion_arguments=suggestion_arguments,
        )
        if action is None:
            return False
        key = (session_id, owner_user_id or "anonymous")
        with self._lock:
            self._dish_candidates[key] = (
                {
                    "id": action.target_id,
                    "name": action.display_name,
                    "components": action.tool_arguments["components"],
                },
                {"meal_type": action.tool_arguments["meal_type"]},
                datetime.now(timezone.utc) + self._ttl,
            )
        return True

    def create_dish_log_action_from_candidate(
        self, session_id: str, *, owner_user_id: str
    ) -> PendingUserAction | None:
        """Promote only the latest non-expired owner/session candidate."""

        key = (session_id, owner_user_id or "anonymous")
        with self._lock:
            candidate = self._dish_candidates.pop(key, None)
            if candidate is None:
                return None
            suggestion, arguments, expires_at = candidate
            if expires_at <= datetime.now(timezone.utc):
                self._dish_candidates.pop(key, None)
                return None
        return self.create_dish_log_action(
            session_id,
            owner_user_id=owner_user_id,
            suggestion=suggestion,
            suggestion_arguments=arguments,
        )

    def has_dish_candidate(self, session_id: str, *, owner_user_id: str) -> bool:
        key = (session_id, owner_user_id or "anonymous")
        with self._lock:
            candidate = self._dish_candidates.get(key)
            return candidate is not None and candidate[2] > datetime.now(timezone.utc)

    def discard_dish_candidate(self, session_id: str, *, owner_user_id: str) -> bool:
        key = (session_id, owner_user_id or "anonymous")
        with self._lock:
            return self._dish_candidates.pop(key, None) is not None

    def create_plan_save_action(
        self,
        session_id: str,
        *,
        owner_user_id: str,
        plan_payload: dict[str, Any],
    ) -> PendingUserAction | None:
        """Bind confirmation to the previewed Plan V2 revision byte-for-byte."""

        plan_id = plan_payload.get("plan_id")
        revision_id = plan_payload.get("revision_id")
        revision_hash = plan_payload.get("revision_content_hash")
        lifecycle = plan_payload.get("lifecycle_status")
        validation = plan_payload.get("validation")
        if (
            not isinstance(plan_id, str)
            or not isinstance(revision_id, str)
            or not isinstance(revision_hash, str)
            or len(revision_hash) != 64
            or lifecycle not in {_PENDING, "DRAFT"}
            or not isinstance(validation, dict)
            or validation.get("status") != "READY"
            or validation.get("hard_violation_count") not in {0, 0.0}
        ):
            return None
        # Transition the in-memory draft only after a displayable exact action
        # was assembled.  This does not write legacy plans or observations;
        # it makes a pending revision distinguishable from a merely generated
        # draft and prevents an unrelated save from being treated as this
        # preview.
        try:
            from services.plan_engine.engine import PlanEngine

            revision = PlanEngine().repository.get(owner_user_id or "anonymous", plan_id, revision_id)
            if revision is None or revision.revision_content_hash != revision_hash:
                return None
            if revision.lifecycle_status.value == "DRAFT":
                PlanEngine().mark_pending_confirmation(revision)
            elif revision.lifecycle_status.value != _PENDING:
                return None
        except Exception:
            return None
        # The response card is the pending revision view.  Lifecycle is not
        # part of the immutable content hash, so this cannot change what is
        # later committed; it only avoids presenting an already-pending item
        # as a free-floating draft.
        plan_payload["lifecycle_status"] = _PENDING
        nested_plan = plan_payload.get("plan")
        if isinstance(nested_plan, dict):
            nested_plan["lifecycle_status"] = _PENDING
        presentation = plan_payload.get("presentation")
        if isinstance(presentation, dict):
            presentation["lifecycle_status"] = _PENDING
        action_id = f"pa_{uuid4().hex}"
        domain = str(plan_payload.get("domain") or "kế hoạch")
        return self.create_action(
            session_id,
            owner_user_id=owner_user_id,
            action_type="SAVE_PLAN_REVISION",
            tool_name="save_plan",
            tool_arguments={
                "plan_id": plan_id,
                "revision_id": revision_id,
                "revision_content_hash": revision_hash,
                "request_id": f"plan-save-{action_id}",
                # Saving and activation are intentionally separate lifecycle
                # commands.  A confirmation such as "lưu" must never make a
                # plan ACTIVE by implication.
                "activate": False,
            },
            target_id=revision_id,
            target_identity={
                "plan_id": plan_id,
                "revision_id": revision_id,
                "revision_content_hash": revision_hash,
            },
            display_name=f"phiên bản kế hoạch {domain.lower()}",
            action_id=action_id,
        )

    def put(self, action: PendingUserAction) -> None:
        with self._lock:
            self._cleanup_locked()
            for existing in self._session_actions_locked(action.session_id):
                if (
                    existing.status == _PENDING
                    and existing.owner_user_id == action.owner_user_id
                    and existing.action_type == action.action_type
                ):
                    existing.status = _SUPERSEDED
            self._actions[action.action_id] = action
            self._by_session.setdefault(action.session_id, []).append(action.action_id)

    def claim_confirmation(
        self, session_id: str, owner_user_id: str, text: str
    ) -> PendingActionResolution:
        is_confirmation = is_explicit_confirmation(text)
        is_rejection = is_explicit_rejection(text)
        if not is_confirmation and not is_rejection:
            return PendingActionResolution("NO_MATCH")
        owner = owner_user_id or "anonymous"
        with self._lock:
            self._cleanup_locked()
            session_actions = self._session_actions_locked(session_id)
            if not session_actions:
                return PendingActionResolution("NO_MATCH")
            own_actions = [a for a in session_actions if a.owner_user_id == owner]
            if not own_actions:
                return PendingActionResolution("OWNER_MISMATCH")
            pending = [a for a in own_actions if a.status == _PENDING]
            if len(pending) > 1:
                return PendingActionResolution("AMBIGUOUS")
            if len(pending) == 1:
                action = pending[0]
                if is_rejection:
                    action.status = _SUPERSEDED
                    return PendingActionResolution("REJECTED", action)
                action.status = _CLAIMED
                return PendingActionResolution("CLAIMED", action)
            if is_rejection:
                return PendingActionResolution("NO_MATCH")
            claimed = [a for a in own_actions if a.status == _CLAIMED]
            if claimed:
                return PendingActionResolution("IN_PROGRESS", claimed[-1])
            executed = [a for a in own_actions if a.status == _EXECUTED]
            if executed:
                return PendingActionResolution("ALREADY_EXECUTED", executed[-1])
            expired = [a for a in own_actions if a.status == _EXPIRED]
            if expired:
                return PendingActionResolution("ACTION_EXPIRED", expired[-1])
            return PendingActionResolution("NO_MATCH")

    def complete(
        self, action: PendingUserAction, *, persisted_reference_id: str | None) -> bool:
        with self._lock:
            current = self._actions.get(action.action_id)
            if current is not action or current.status != _CLAIMED:
                return False
            current.status = _EXECUTED
            current.persisted_reference_id = persisted_reference_id or current.target_id
            return True

    def release(self, action: PendingUserAction) -> None:
        with self._lock:
            current = self._actions.get(action.action_id)
            if current is action and current.status == _CLAIMED:
                current.status = _PENDING

    def _session_actions_locked(self, session_id: str) -> list[PendingUserAction]:
        return [
            self._actions[action_id]
            for action_id in self._by_session.get(session_id, ())
            if action_id in self._actions
        ]

    def _cleanup_locked(self) -> None:
        now = datetime.now(timezone.utc)
        for action in tuple(self._actions.values()):
            if action.status in {_PENDING, _CLAIMED} and action.expires_at <= now:
                action.status = _EXPIRED
            if action.status in _TERMINAL and action.expires_at + self._terminal_retention <= now:
                self._actions.pop(action.action_id, None)
                ids = self._by_session.get(action.session_id, [])
                if action.action_id in ids:
                    ids.remove(action.action_id)
                if not ids:
                    self._by_session.pop(action.session_id, None)


pending_user_actions = PendingUserActionStore()


__all__ = [
    "PendingActionResolution",
    "PendingUserAction",
    "PendingUserActionStore",
    "is_explicit_confirmation",
    "is_explicit_rejection",
    "pending_user_actions",
]
