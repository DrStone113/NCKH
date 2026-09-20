"""Tool dispatcher: bridge between the agent loop and tool implementations.

This module implements ``ToolDispatcher.dispatch`` for **server-side** tools
(task 8.1). Client-side dispatch with ``pendingCalls`` and ``correlation_id``
matching, idempotency caching, and audit logging are layered on top in
tasks 8.2 / 8.3 / 8.4 of the chatbot redesign spec.

Design references:
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.3, §8.2 / §9.3.
- Requirements 1.1, 1.4 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract (from design.md §8.2 dispatch pseudocode):

- ``dispatch`` validates ``call.arguments`` against the tool's JSON schema
  via :meth:`ToolRegistry.validate` and returns a :class:`ToolResult` with
  ``error="UNKNOWN_TOOL"`` or ``"INVALID_ARGS"`` on validation failure.
- For ``descriptor.side == "server"``, the tool function is invoked under
  ``asyncio.wait_for(timeout_ms / 1000)``. ``asyncio.TimeoutError`` becomes
  ``ToolResult(ok=False, error="TIMEOUT")``; any other exception is logged
  and returned as ``ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")``.
- ``dispatch`` MUST NEVER raise out to the caller.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable

from sqlalchemy import text

from .llm_client import ToolCall
from .tool_registry import ToolDescriptor, ToolRegistry
from services.workout_planner.integration import WorkoutRuntimeContext
from services.agent.tools.plan_v2 import PLAN_V2_TOOL_NAMES, PlanRuntimeContext

logger = logging.getLogger(__name__)

#: Tools whose results should be diversified across a chat session by feeding
#: back recently returned ids. ``suggest_dish`` picks deterministically by
#: ``(|total_calories - target|, id)``; because every dish is scaled to the
#: target kcal, that distance is near-zero for *all* candidates, so the same
#: dish would otherwise win on every turn. See design.md §9.4 / requirement
#: 4.3, which already specifies ``recent_dish_ids`` for this purpose — the
#: planner passed it, but plain chat never did.
_RECENT_IDS_ARG = "recent_dish_ids"
_RECENT_IDS_TOOLS = frozenset({"suggest_dish"})
_E4_RUNTIME_TOOLS = frozenset(
    {
        "suggest_workout",
        "build_personalized_workout",
        "get_workout_substitutions",
        "save_workout_plan",
        "log_workout_result",
    }
)
_PLAN_V2_RUNTIME_TOOLS = PLAN_V2_TOOL_NAMES
_PRIVATE_SNAPSHOT_READS = frozenset(
    {
        "get_user_profile",
        "get_today_meals",
        "get_today_exercises",
        "get_lifestyle_logs",
        "get_active_plan",
        "get_active_plan_v2",
    }
)

#: FIFO window size for chat-driven diversification.
#:
#: design.md §6 caps ``recent_dish_ids`` at 6 for the *planner* (a 7-day meal
#: plan only needs to avoid repeats within a short stretch). In free-form chat
#: a window of 6 makes the suggestion cycle repeat every 7 turns even though
#: ~60 dishes qualify for a given meal type, so chat keeps a wider window.
#: ``suggest_dish`` falls back to previously seen dishes when the window
#: excludes every candidate, so a large window can never cause NO_DISH_FOUND.
_RECENT_IDS_MAXLEN = 40

#: Upper bound on how many sessions keep a diversity window. The per-request
#: dispatcher in ``modules/chat/router.py`` is short-lived, but the one on
#: ``app.state`` lives for the whole process, so cap the map to stop it from
#: growing without bound if ``cleanup_session`` is never called for a session.
_RECENT_IDS_MAX_SESSIONS = 512

# Stable domain outcomes that tools intentionally surface to the agent. Other
# ValueError messages remain internal so implementation details are not leaked.
_PUBLIC_TOOL_VALUE_ERRORS = frozenset(
    {
        "NO_DISH_FOUND",
        "INVALID_MEAL_TYPE",
        "INVALID_TARGET_KCAL",
        "INVALID_DIETARY_RESTRICTIONS",
        "INVALID_RECENT_DISH_IDS",
        "NO_EXERCISES_FOUND",
        "INVALID_MUSCLE_GROUP",
        "INVALID_DURATION",
        "INVALID_EQUIPMENT",
        "INVALID_LEVEL",
        "INVALID_USER_STATE",
        "INVALID_GOAL",
        "UNSAFE_TO_RECOMMEND_WORKOUT",
        "PLAN_NOT_FOUND",
        "PLAN_REVISION_CONFLICT",
        "PLAN_ITEM_NOT_FOUND",
        "PLAN_NOT_READY",
        "PLAN_CONTENT_HASH_MISMATCH",
        "INVALID_PLAN_SAVE_TRANSITION",
        "INVALID_PLAN_LIFECYCLE_TRANSITION",
        "INVALID_PLAN_PATCH",
        "PLAN_PATCH_OPERATION_REQUIRES_DOMAIN_RESOLUTION",
        "E4_WEEKLY_SCHEDULE_CAPABILITY_REQUIRED",
    }
)


def _normalise_plan_profile(
    raw: Any, *, user_id: str | None, goal: str | None
) -> dict[str, Any]:
    """Reduce Flutter's rich user context to the planner profile schema."""
    source = raw if isinstance(raw, dict) else {}
    restrictions = source.get("dietary_restrictions") or source.get(
        "dietaryRestrictions"
    )
    if isinstance(restrictions, str):
        restrictions = [restrictions] if restrictions.strip() else []
    elif not isinstance(restrictions, list):
        restrictions = []

    safety_profile = source.get("nutrition_safety_profile") or source.get(
        "nutritionSafetyProfile"
    )
    if not isinstance(safety_profile, dict):
        safety_profile = {}

    return {
        "user_id": user_id or source.get("user_id") or source.get("id"),
        "age": source.get("age"),
        "gender": source.get("gender"),
        "equation_sex": source.get("equation_sex")
        or source.get("equationSex"),
        "nutrition_safety_profile": safety_profile,
        "height_cm": source.get("height_cm") or source.get("height"),
        "weight_kg": source.get("weight_kg") or source.get("weight"),
        "activity_level": source.get("activity_level")
        or source.get("activityLevel"),
        "health_goal": goal
        or source.get("health_goal")
        or source.get("healthGoal"),
        "dietary_restrictions": restrictions,
    }


def _context_value(raw: Any, *keys: str) -> Any:
    """Read the first populated key from a dict or profile-like object."""

    if isinstance(raw, dict):
        for key in keys:
            value = raw.get(key)
            if value is not None:
                return value
        return None
    for key in keys:
        value = getattr(raw, key, None)
        if value is not None:
            return value
    return None


def _enrich_workout_arguments(arguments: dict[str, Any], context: Any) -> None:
    """Attach canonical profile data without overwriting explicit user state."""

    if context is None:
        return

    state = arguments.get("user_state")
    state = dict(state) if isinstance(state, dict) else {}
    weight = _context_value(context, "weight_kg", "weight")
    if weight is not None and state.get("weight_kg") is None:
        state["weight_kg"] = weight
    if state:
        arguments["user_state"] = state

    if arguments.get("goal") is None:
        health_goal = _context_value(context, "health_goal", "healthGoal")
        arguments["goal"] = {
            "lose_weight": "weight_loss",
            "gain_muscle": "muscle_gain",
            "maintain": "general_fitness",
        }.get(health_goal, "general_fitness")


# ---------------------------------------------------------------------------- #
# Result type
# ---------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Outcome of a single ``dispatch`` invocation.

    Attributes
    ----------
    ok:
        ``True`` if the tool executed successfully and ``data`` carries the
        return value.
    error:
        Stable error code when ``ok`` is ``False``. One of the strings
        defined by the design (``"UNKNOWN_TOOL"``, ``"INVALID_ARGS"``,
        ``"TIMEOUT"``, ``"TOOL_INTERNAL_ERROR"``, ``"DISCONNECTED"``).
        ``None`` on success.
    data:
        Tool-specific payload. Failed write tools may include their typed
        ``write_status`` here so REJECTED and ERROR remain distinguishable.
    ui_message:
        Optional presentation payload produced by a client tool. It is kept
        outside ``data`` so it can be persisted for history without being sent
        back into the LLM tool transcript.
    """

    ok: bool
    error: str | None = None
    data: Any = None
    ui_message: dict[str, Any] | None = None


# ---------------------------------------------------------------------------- #
# Dispatcher
# ---------------------------------------------------------------------------- #


class ToolDispatcher:
    """Dispatch a :class:`ToolCall` to its registered implementation.

    The dispatcher is intentionally stateless w.r.t. *which* tools exist; it
    delegates to the injected :class:`ToolRegistry`. The ``gateway`` argument
    is reserved for client-side dispatch (task 8.2) and is currently
    unused.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        gateway: Any | None = None,
        db_session: Any | None = None,
        snapshot_cache: Any | None = None,
    ) -> None:
        self.registry = registry
        self.gateway = gateway
        self.db_session = db_session
        self.snapshot_cache = snapshot_cache
        self._pending_calls: dict[str, tuple[str, asyncio.Future[ToolResult]]] = {}
        # session_id -> tool_name -> FIFO of ids already returned this session.
        self._recent_ids: dict[str, dict[str, deque[int]]] = {}
        # A reconnect creates a new dispatcher even when the logical chat or
        # account is unchanged. Track which session/tool windows have already
        # been hydrated from durable, owner-scoped invocation history so the
        # first suggestion after a reconnect does not restart at the same dish.
        self._hydrated_recent_ids: set[tuple[str, str]] = set()
        # Multiple suggestions in one model response are dispatched in
        # parallel by the orchestrator. Serialize only diversity-aware tools
        # per session so each result can exclude the one returned just before
        # it; unrelated reads remain fully parallel.
        self._recent_ids_locks: dict[tuple[str, str], asyncio.Lock] = {}

    # ----------------------------------------------------------------- dispatch
    async def dispatch(
        self,
        session_id: str,
        call: ToolCall,
        timeout_ms: int,
    ) -> ToolResult:
        """Validate ``call`` then run the tool, returning a :class:`ToolResult`.

        This coroutine MUST NEVER raise. Any unexpected exception is logged
        and surfaced as ``ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")``.
        """
        try:
            if self.gateway is not None:
                if call.name == "suggest_dish":
                    lat = getattr(self.gateway, "latitude", None)
                    lng = getattr(self.gateway, "longitude", None)
                    if lat is not None and "latitude" not in call.arguments:
                        call.arguments["latitude"] = lat
                    if lng is not None and "longitude" not in call.arguments:
                        call.arguments["longitude"] = lng

                if call.name == "suggest_workout":
                    _enrich_workout_arguments(
                        call.arguments,
                        getattr(self.gateway, "user_context", None),
                    )

                gateway_user = getattr(self.gateway, "user_id", None)
                if gateway_user and gateway_user not in ("anonymous", ""):
                    if "user_id" in call.arguments or call.name in (
                        "create_plan",
                        "create_long_term_plan",
                        "get_active_plan",
                        "get_lifestyle_logs",
                        "log_lifestyle",
                    ):
                        call.arguments["user_id"] = gateway_user

                if call.name == "create_long_term_plan":
                    context = getattr(self.gateway, "user_context", None)
                    supplied_profile = call.arguments.get("profile")
                    profile = _normalise_plan_profile(
                        context,
                        user_id=call.arguments.get("user_id"),
                        goal=call.arguments.get("goal"),
                    )
                    if isinstance(supplied_profile, dict):
                        supplied = _normalise_plan_profile(
                            supplied_profile,
                            user_id=call.arguments.get("user_id"),
                            goal=call.arguments.get("goal"),
                        )
                        for key, value in supplied.items():
                            if key == "dietary_restrictions":
                                profile[key] = list(
                                    dict.fromkeys(
                                        [
                                            *profile.get(key, []),
                                            *value,
                                        ]
                                    )
                                )
                            elif profile.get(key) is None:
                                profile[key] = value
                    call.arguments["profile"] = profile

            if call.name in {"build_nutrition_plan", "build_workout_schedule"} and isinstance(call.arguments, dict):
                if "temporary_preference" in call.arguments and "temporary_preferences" not in call.arguments:
                    call.arguments["temporary_preferences"] = call.arguments.pop("temporary_preference")
                if "preference" in call.arguments and "temporary_preferences" not in call.arguments:
                    call.arguments["temporary_preferences"] = call.arguments.pop("preference")
                if "preferences" in call.arguments and "temporary_preferences" not in call.arguments:
                    call.arguments["temporary_preferences"] = call.arguments.pop("preferences")
                if "temporary_exclusion" in call.arguments and "temporary_exclusions" not in call.arguments:
                    call.arguments["temporary_exclusions"] = call.arguments.pop("temporary_exclusion")
                if "exclusion" in call.arguments and "temporary_exclusions" not in call.arguments:
                    call.arguments["temporary_exclusions"] = call.arguments.pop("exclusion")
                if "exclusions" in call.arguments and "temporary_exclusions" not in call.arguments:
                    call.arguments["temporary_exclusions"] = call.arguments.pop("exclusions")

                array_keys = {
                    "schedule_constraints",
                    "temporary_preferences",
                    "temporary_exclusions",
                    "requested_modifications",
                    "equipment",
                    "available_days",
                    "unavailable_days",
                    "preferred_days",
                }
                for k in array_keys:
                    val = call.arguments.get(k)
                    if isinstance(val, str):
                        call.arguments[k] = [val]
                    elif isinstance(val, tuple):
                        call.arguments[k] = list(val)

            ok, err = self.registry.validate(call.name, call.arguments)
            if not ok:
                # ``err`` is one of "UNKNOWN_TOOL" / "INVALID_ARGS" per the
                # ``ToolRegistry.validate`` contract.
                return ToolResult(ok=False, error=err)

            descriptor = self.registry.get(call.name)
            if descriptor is None:
                # Defensive: ``validate`` returned ok=True so the descriptor
                # MUST exist, but treat a race / programming error gracefully.
                logger.error(
                    "registry.validate ok but get() returned None for %r",
                    call.name,
                )
                return ToolResult(ok=False, error="UNKNOWN_TOOL")

            # A descriptor may declare it needs longer than the caller's
            # default — ``search_medical_knowledge`` talks to two upstream
            # providers and would be killed at the global 15s. Take the more
            # generous of the two so a slow tool gets its stated budget while a
            # caller can still grant extra time to a fast one.
            #
            # (Before this, ``ToolDescriptor.timeout_ms`` was declared and
            # documented but never actually read anywhere.)
            effective_timeout_ms = max(timeout_ms, descriptor.timeout_ms)
            # Convert to seconds; clamp negative or zero values to a tiny
            # positive number so ``asyncio.wait_for`` raises TimeoutError
            # immediately instead of misbehaving.
            timeout_s = max(effective_timeout_ms / 1000.0, 0.0)
            started = time.perf_counter()

            cache_owner = str(getattr(self.gateway, "user_id", "") or "")
            cacheable_private_read = bool(
                descriptor.idempotent
                and descriptor.name in _PRIVATE_SNAPSHOT_READS
                and cache_owner
                and self.snapshot_cache is not None
            )
            if cacheable_private_read:
                cached = await self.snapshot_cache.get(
                    owner=cache_owner,
                    session_id=session_id,
                    source=descriptor.name,
                    params=call.arguments,
                )
                if isinstance(cached, ToolResult):
                    await self._insert_completed_invocation(
                        session_id, call, descriptor, cached, started
                    )
                    return cached

            invocation_id: str | None = None
            # Writes keep a durable claim/finalize lifecycle. Pure reads need
            # only one audit row after completion, cutting their audit traffic
            # in half without weakening idempotency or write recovery.
            if self.db_session is not None and not descriptor.idempotent:
                invocation_id = await self._insert_invocation(session_id, call, descriptor)

            if not descriptor.idempotent:
                request_id = call.arguments.get("request_id")
                if not isinstance(request_id, str) or not request_id:
                    result = ToolResult(ok=False, error="INVALID_ARGS")
                    await self._finalize_invocation(invocation_id, result, started)
                    return result
                cached = await self._load_idempotent_result(session_id, descriptor.name, request_id)
                if cached is not None:
                    await self._finalize_invocation(invocation_id, cached, started)
                    return cached

            result: ToolResult
            if descriptor.side == "server":
                async def _run_server_call() -> ToolResult:
                    await self._apply_recent_ids(session_id, call)
                    # Preserve ``call.arguments`` exactly for invocation audit and
                    # LLM transcripts. Profile/history snapshots travel only in
                    # this ephemeral private copy after schema validation.
                    server_arguments = dict(call.arguments)
                    if descriptor.name in _E4_RUNTIME_TOOLS:
                        server_arguments["_runtime_context"] = WorkoutRuntimeContext(
                            user_id=getattr(self.gateway, "user_id", None),
                            session_id=session_id,
                            user_context=getattr(self.gateway, "user_context", None),
                            db_session=self.db_session,
                        )
                    if descriptor.name in _PLAN_V2_RUNTIME_TOOLS:
                        server_arguments["_runtime_context"] = PlanRuntimeContext(
                            user_id=getattr(self.gateway, "user_id", None),
                            session_id=session_id,
                            user_context=getattr(self.gateway, "user_context", None),
                            db_session=self.db_session,
                            authenticated_principal=bool(getattr(self.gateway, "authenticated_principal", False)),
                        )
                    server_result = await self._dispatch_server(
                        descriptor, call, timeout_s, session_id, server_arguments
                    )
                    self._remember_result_id(session_id, call, server_result)
                    return server_result

                if descriptor.name in _RECENT_IDS_TOOLS:
                    lock_key = (session_id, descriptor.name)
                    lock = self._recent_ids_locks.setdefault(lock_key, asyncio.Lock())
                    async with lock:
                        result = await _run_server_call()
                else:
                    result = await _run_server_call()
            elif descriptor.side == "client":
                result = await self._dispatch_client(
                    descriptor, call, timeout_s, session_id
                )
            else:
                logger.error(
                    "Unknown descriptor.side=%r for tool %s",
                    descriptor.side,
                    call.name,
                )
                result = ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

            if descriptor.idempotent:
                if cacheable_private_read and result.ok:
                    await self.snapshot_cache.set(
                        owner=cache_owner,
                        session_id=session_id,
                        source=descriptor.name,
                        params=call.arguments,
                        value=result,
                    )
                await self._insert_completed_invocation(
                    session_id, call, descriptor, result, started
                )
            else:
                await self._finalize_invocation(invocation_id, result, started)
                if result.ok and cache_owner and self.snapshot_cache is not None:
                    await self.snapshot_cache.invalidate(
                        owner=cache_owner, session_id=session_id
                    )
            return result

        except Exception:
            # Catch-all: ``dispatch`` MUST never raise (design §8.2
            # post-condition).
            logger.exception(
                "Unexpected error in ToolDispatcher.dispatch "
                "(session=%s, tool=%s, call_id=%s)",
                session_id,
                getattr(call, "name", "<?>"),
                getattr(call, "id", "<?>"),
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

    async def _dispatch_client(
        self,
        descriptor: ToolDescriptor,
        call: ToolCall,
        timeout_s: float,
        session_id: str,
    ) -> ToolResult:
        if self.gateway is None or not hasattr(self.gateway, "send_tool_call"):
            logger.warning("client-side dispatch unavailable for tool=%s", call.name)
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ToolResult] = loop.create_future()
        self._pending_calls[call.id] = (session_id, future)
        try:
            await self.gateway.send_tool_call(
                call.id,
                descriptor.name,
                call.arguments,
                int(timeout_s * 1000),
            )
            result = await asyncio.wait_for(future, timeout=timeout_s)
            # The Flutter client is authoritative for Firestore-backed workout
            # intake. Reflect its read-back-verified patch in this connection
            # immediately so a following confirmation or E4 tool call uses the
            # exact persisted revision rather than the stale turn snapshot.
            if (
                result.ok
                and descriptor.name == "update_workout_profile"
                and self.gateway is not None
                and isinstance(result.data, dict)
                and isinstance(result.data.get("workout_profile"), dict)
            ):
                existing = getattr(self.gateway, "user_context", None)
                if isinstance(existing, dict):
                    self.gateway.user_context = {
                        **existing,
                        "workout_profile": dict(result.data["workout_profile"]),
                    }
            return result
        except asyncio.TimeoutError:
            self._pending_calls.pop(call.id, None)
            return ToolResult(ok=False, error="TIMEOUT")
        except Exception:
            self._pending_calls.pop(call.id, None)
            logger.exception(
                "Client tool dispatch failed (session=%s, tool=%s, call_id=%s)",
                session_id,
                call.name,
                call.id,
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

    def on_tool_result(self, correlation_id: str, payload: dict[str, Any]) -> None:
        pending = self._pending_calls.pop(correlation_id, None)
        if pending is None:
            logger.warning("Dropping unmatched tool_result correlation_id=%s", correlation_id)
            return
        _, future = pending
        if future.done():
            return
        if payload.get("ok") is True:
            raw_ui_message = payload.get("ui_message")
            ui_message = raw_ui_message if isinstance(raw_ui_message, dict) else None
            future.set_result(
                ToolResult(
                    ok=True,
                    data=payload.get("data"),
                    ui_message=ui_message,
                )
            )
            return
        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("code") or error.get("message")
        future.set_result(
            ToolResult(
                ok=False,
                error=str(error or "TOOL_INTERNAL_ERROR"),
                data=payload.get("data"),
            )
        )

    def cleanup_session(self, session_id: str) -> None:
        for call_id, (pending_session_id, future) in list(self._pending_calls.items()):
            if pending_session_id != session_id:
                continue
            self._pending_calls.pop(call_id, None)
            if not future.done():
                future.set_result(ToolResult(ok=False, error="DISCONNECTED"))
        self._recent_ids.pop(session_id, None)
        self._hydrated_recent_ids = {
            key for key in self._hydrated_recent_ids if key[0] != session_id
        }
        self._recent_ids_locks = {
            key: lock
            for key, lock in self._recent_ids_locks.items()
            if key[0] != session_id
        }

    # ------------------------------------------------------- diversity helpers
    async def _apply_recent_ids(self, session_id: str, call: ToolCall) -> None:
        """Merge this session's recently returned ids into ``call.arguments``.

        Without this, ``suggest_dish`` returns the same dish on every turn of a
        conversation: it ranks candidates by ``|total_calories - target_kcal|``,
        but every dish is scaled to hit the target, so that distance is
        effectively zero for all of them and the ``id`` tiebreak always picks
        the same winner.

        Caller-supplied ids are preserved and *extended*, not replaced. The LLM
        reconstructs ``recent_dish_ids`` from conversation history, so it silently
        loses entries whenever history is trimmed or a DB write fails — and an
        incomplete list makes the tool hand back a dish the user just saw. The
        dispatcher's own record is authoritative about what this session already
        received, so the union is what we want.
        """
        if call.name not in _RECENT_IDS_TOOLS:
            return
        await self._hydrate_recent_ids(session_id, call.name)
        seen = self._recent_ids.get(session_id, {}).get(call.name)
        if not seen:
            return

        supplied = call.arguments.get(_RECENT_IDS_ARG)
        merged: list[int] = []
        if isinstance(supplied, (list, tuple)):
            for raw in supplied:
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    continue
                if value not in merged:
                    merged.append(value)
        for value in seen:
            if value not in merged:
                merged.append(value)

        # ``ToolCall.arguments`` is a plain dict owned by this call; mutating it
        # here keeps the tool signature untouched and preserves idempotency of
        # ``suggest_dish`` itself (same arguments still yield the same dish).
        call.arguments[_RECENT_IDS_ARG] = merged

    async def _hydrate_recent_ids(self, session_id: str, tool_name: str) -> None:
        """Load recent ids for the authenticated owner once per connection.

        The in-memory window remains the fast path. This one bounded read only
        runs for the first recommendation after a connection/reconnect and is
        scoped through ``chat_sessions.user_id`` using the verified gateway
        principal. Failure is deliberately fail-open: recommendation safety
        and availability must not depend on optional diversity history.
        """

        hydration_key = (session_id, tool_name)
        if hydration_key in self._hydrated_recent_ids:
            return
        self._hydrated_recent_ids.add(hydration_key)

        owner_user_id = getattr(self.gateway, "user_id", None)
        if (
            self.db_session is None
            or not bool(getattr(self.gateway, "authenticated_principal", False))
            or not isinstance(owner_user_id, str)
            or not owner_user_id.strip()
            or owner_user_id == "anonymous"
        ):
            return

        try:
            from db.db_status import is_db_offline

            if is_db_offline():
                return
            result = await asyncio.wait_for(
                self.db_session.execute(
                    text(
                        """
                        SELECT ti.result->>'id' AS item_id
                        FROM tool_invocations AS ti
                        JOIN chat_sessions AS cs ON cs.id = ti.session_id
                        WHERE cs.user_id = :owner_user_id
                          AND ti.tool_name = :tool_name
                          AND ti.ok = TRUE
                          AND ti.result->>'id' IS NOT NULL
                        ORDER BY ti.created_at DESC
                        LIMIT :history_limit
                        """
                    ),
                    {
                        "owner_user_id": owner_user_id,
                        "tool_name": tool_name,
                        "history_limit": _RECENT_IDS_MAXLEN,
                    },
                ),
                timeout=0.5,
            )
            rows = result.fetchall()
        except Exception as exc:  # noqa: BLE001 - optional diversity history
            logger.info("Durable recommendation history unavailable: %s", exc)
            return

        # SQL returns newest-first; append oldest-first so the deque preserves
        # FIFO meaning and evicts the genuinely oldest exposure next.
        newest_unique: list[int] = []
        for row in rows:
            raw_id = row[0] if row else None
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if item_id not in newest_unique:
                newest_unique.append(item_id)

        window = self._recent_ids.setdefault(session_id, {}).setdefault(
            tool_name, deque(maxlen=_RECENT_IDS_MAXLEN)
        )
        for item_id in reversed(newest_unique):
            if item_id not in window:
                window.append(item_id)

    def _remember_result_id(
        self, session_id: str, call: ToolCall, result: ToolResult
    ) -> None:
        """Record the id this tool just returned so the next turn can skip it."""
        if call.name not in _RECENT_IDS_TOOLS or not result.ok:
            return
        data = result.data
        if not isinstance(data, dict):
            return
        raw_id = data.get("id")
        try:
            item_id = int(raw_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        window = self._recent_ids.setdefault(session_id, {}).setdefault(
            call.name, deque(maxlen=_RECENT_IDS_MAXLEN)
        )
        if item_id in window:
            # Keep FIFO order meaningful: re-appending would evict a genuinely
            # older entry and let the duplicate linger.
            return
        window.append(item_id)
        self._evict_stale_sessions(session_id)

    def _evict_stale_sessions(self, keep_session_id: str) -> None:
        """Drop the oldest diversity windows once the map grows too large."""
        overflow = len(self._recent_ids) - _RECENT_IDS_MAX_SESSIONS
        if overflow <= 0:
            return
        # ``dict`` preserves insertion order, so the head holds the least
        # recently created sessions.
        for stale_id in list(self._recent_ids)[:overflow]:
            if stale_id != keep_session_id:
                self._recent_ids.pop(stale_id, None)
                self._hydrated_recent_ids = {
                    key for key in self._hydrated_recent_ids if key[0] != stale_id
                }
                self._recent_ids_locks = {
                    key: lock
                    for key, lock in self._recent_ids_locks.items()
                    if key[0] != stale_id
                }

    async def _insert_invocation(
        self,
        session_id: str,
        call: ToolCall,
        descriptor: ToolDescriptor,
    ) -> str | None:
        from db.db_status import is_db_offline, mark_db_offline
        if self.db_session is None or is_db_offline():
            return None
        try:
            await asyncio.wait_for(
                self.db_session.execute(
                    text(
                        """
                        INSERT INTO tool_invocations (
                            session_id, correlation_id, tool_name, side, arguments,
                            result, ok, error_code, duration_ms
                        ) VALUES (
                            :session_id, :correlation_id, :tool_name, :side, CAST(:arguments AS JSONB),
                            NULL, NULL, NULL, NULL
                        )
                        """
                    ),
                    {
                        "session_id": session_id,
                        "correlation_id": call.id,
                        "tool_name": call.name,
                        "side": descriptor.side,
                        "arguments": json.dumps(call.arguments),
                    },
                ),
                timeout=0.5,
            )
            return call.id
        except Exception:
            mark_db_offline(60.0)
            logger.warning("Failed to insert tool invocation audit row (DB unavailable)")
            return None

    async def _finalize_invocation(
        self,
        invocation_id: str | None,
        result: ToolResult,
        started: float,
    ) -> None:
        if self.db_session is None or invocation_id is None:
            return
        try:
            await asyncio.wait_for(
                self.db_session.execute(
                    text(
                        """
                        UPDATE tool_invocations
                        SET result = CAST(:result AS JSONB),
                            ok = :ok,
                            error_code = :error_code,
                            duration_ms = :duration_ms
                        WHERE correlation_id = :correlation_id
                        """
                    ),
                    {
                        "correlation_id": invocation_id,
                        "result": json.dumps(result.data if result.ok else None),
                        "ok": result.ok,
                        "error_code": result.error,
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                    },
                ),
                timeout=0.5,
            )
        except Exception:
            logger.exception("Failed to finalize tool invocation audit row")

    async def _insert_completed_invocation(
        self,
        session_id: str,
        call: ToolCall,
        descriptor: ToolDescriptor,
        result: ToolResult,
        started: float,
    ) -> None:
        from db.db_status import is_db_offline, mark_db_offline

        if self.db_session is None or is_db_offline():
            return
        try:
            await asyncio.wait_for(
                self.db_session.execute(
                    text(
                        """
                        INSERT INTO tool_invocations (
                            session_id, correlation_id, tool_name, side, arguments,
                            result, ok, error_code, duration_ms
                        ) VALUES (
                            :session_id, :correlation_id, :tool_name, :side,
                            CAST(:arguments AS JSONB), CAST(:result AS JSONB),
                            :ok, :error_code, :duration_ms
                        )
                        """
                    ),
                    {
                        "session_id": session_id,
                        "correlation_id": call.id,
                        "tool_name": call.name,
                        "side": descriptor.side,
                        "arguments": json.dumps(call.arguments),
                        "result": json.dumps(result.data if result.ok else None),
                        "ok": result.ok,
                        "error_code": result.error,
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                    },
                ),
                timeout=0.5,
            )
        except Exception:
            mark_db_offline(60.0)
            logger.warning("Failed to insert completed read audit row (DB unavailable)")

    async def _load_idempotent_result(
        self,
        session_id: str,
        tool_name: str,
        request_id: str,
    ) -> ToolResult | None:
        from db.db_status import is_db_offline
        if self.db_session is None or is_db_offline():
            return None
        try:
            result = await self.db_session.execute(
                text(
                    """
                    SELECT result, ok, error_code
                    FROM tool_invocations
                    WHERE session_id = :session_id
                      AND tool_name = :tool_name
                      AND arguments->>'request_id' = :request_id
                      AND ok = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "request_id": request_id,
                },
            )
            row = result.first()
            if row is None:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return ToolResult(ok=bool(row[1]), error=row[2], data=payload)
        except Exception:
            logger.exception("Failed to query idempotent tool result cache")
            return None

    # -------------------------------------------------------- _dispatch_server
    async def _dispatch_server(
        self,
        descriptor: ToolDescriptor,
        call: ToolCall,
        timeout_s: float,
        session_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Run a server-side tool under a wall-clock timeout."""
        fn = descriptor.fn
        if fn is None:
            logger.error(
                "Server tool %r has no implementation bound", descriptor.name
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

        try:
            awaitable = self._build_awaitable(fn, arguments if arguments is not None else call.arguments)
        except Exception:
            # Building the call (signature inspection / argument binding)
            # should not normally fail because ``registry.validate`` already
            # accepted the args, but a mismatch between schema and Python
            # signature is possible. Log and report a generic internal error.
            logger.exception(
                "Failed to bind arguments for tool %s (call_id=%s)",
                call.name,
                call.id,
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

        try:
            data = await asyncio.wait_for(awaitable, timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                "Tool %s timed out after %.3fs (session=%s, call_id=%s)",
                call.name,
                timeout_s,
                session_id,
                call.id,
            )
            return ToolResult(ok=False, error="TIMEOUT")
        except asyncio.CancelledError:
            # Re-raise cancellation so structured concurrency works as
            # expected. This is NOT a tool failure — the surrounding task
            # was cancelled. Cancellation is not "raising out" of dispatch
            # in the sense forbidden by the contract; it is cooperative.
            raise
        except ValueError as exc:
            msg = str(exc)
            if msg in _PUBLIC_TOOL_VALUE_ERRORS:
                return ToolResult(ok=False, error=msg)
            logger.exception(
                "Tool %s raised ValueError (session=%s, call_id=%s)",
                call.name,
                session_id,
                call.id,
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")
        except Exception:
            logger.exception(
                "Tool %s raised (session=%s, call_id=%s)",
                call.name,
                session_id,
                call.id,
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

        return ToolResult(ok=True, error=None, data=data)

    # --------------------------------------------------------- _build_awaitable
    @staticmethod
    def _build_awaitable(
        fn: Any, arguments: dict[str, Any]
    ) -> Awaitable[Any]:
        """Return an awaitable that invokes ``fn`` with ``arguments``.

        Calling shape is decided via :func:`inspect.signature`:

        - If ``fn`` declares ``**kwargs`` or has more than one regular
          parameter, ``arguments`` is unpacked with ``**arguments``.
        - If ``fn`` has exactly one regular parameter whose name is **not**
          a key in ``arguments``, ``arguments`` is passed as a single
          positional dict (matches tools like ``calculate_tdee(profile)``
          whose JSON schema mirrors the parameter shape).
        - Otherwise ``arguments`` is unpacked with ``**arguments``.

        Sync functions are wrapped in :func:`asyncio.to_thread` so the
        surrounding ``asyncio.wait_for`` can enforce a wall-clock timeout
        without blocking the event loop.
        """
        use_positional = False
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = None

        if sig is not None:
            has_var_kw = any(
                p.kind is inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            regular = [
                p
                for p in sig.parameters.values()
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            ]
            if (
                not has_var_kw
                and len(regular) == 1
                and regular[0].name not in arguments
            ):
                use_positional = True

        if asyncio.iscoroutinefunction(fn):
            return fn(arguments) if use_positional else fn(**arguments)

        # Sync callable: run in a worker thread.
        if use_positional:
            return asyncio.to_thread(fn, arguments)
        return asyncio.to_thread(fn, **arguments)


__all__ = [
    "ToolDispatcher",
    "ToolResult",
]
