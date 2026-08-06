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
        Tool-specific payload on success; ``None`` on failure.
    """

    ok: bool
    error: str | None = None
    data: Any = None


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
    ) -> None:
        self.registry = registry
        self.gateway = gateway
        self.db_session = db_session
        self._pending_calls: dict[str, tuple[str, asyncio.Future[ToolResult]]] = {}
        # session_id -> tool_name -> FIFO of ids already returned this session.
        self._recent_ids: dict[str, dict[str, deque[int]]] = {}

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
        # Top-level guard: nothing below this try block is permitted to
        # surface an exception. The agent loop must always receive a
        # ToolResult so it can append a tool turn to the conversation.
        try:
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

            invocation_id: str | None = None
            if self.db_session is not None:
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
                self._apply_recent_ids(session_id, call)
                result = await self._dispatch_server(
                    descriptor, call, timeout_s, session_id
                )
                self._remember_result_id(session_id, call, result)
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

            await self._finalize_invocation(invocation_id, result, started)
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
            return await asyncio.wait_for(future, timeout=timeout_s)
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
            future.set_result(ToolResult(ok=True, data=payload.get("data")))
            return
        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("code") or error.get("message")
        future.set_result(ToolResult(ok=False, error=str(error or "TOOL_INTERNAL_ERROR")))

    def cleanup_session(self, session_id: str) -> None:
        for call_id, (pending_session_id, future) in list(self._pending_calls.items()):
            if pending_session_id != session_id:
                continue
            self._pending_calls.pop(call_id, None)
            if not future.done():
                future.set_result(ToolResult(ok=False, error="DISCONNECTED"))
        self._recent_ids.pop(session_id, None)

    # ------------------------------------------------------- diversity helpers
    def _apply_recent_ids(self, session_id: str, call: ToolCall) -> None:
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
    ) -> ToolResult:
        """Run a server-side tool under a wall-clock timeout."""
        fn = descriptor.fn
        if fn is None:
            logger.error(
                "Server tool %r has no implementation bound", descriptor.name
            )
            return ToolResult(ok=False, error="TOOL_INTERNAL_ERROR")

        try:
            awaitable = self._build_awaitable(fn, call.arguments)
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
            if msg in ("NO_DISH_FOUND", "INVALID_MEAL_TYPE", "INVALID_TARGET_KCAL", "INVALID_DIETARY_RESTRICTIONS", "INVALID_RECENT_DISH_IDS"):
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
