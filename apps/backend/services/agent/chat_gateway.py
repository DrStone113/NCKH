"""WebSocket transport for the tool-using chat agent."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_CURRENT_TURN_ID: ContextVar[str | None] = ContextVar(
    "chat_gateway_turn_id", default=None
)


_CONTEXTUAL_FOLLOW_UPS = frozenset(
    {
        "ok",
        "oke",
        "okay",
        "ừ",
        "uh",
        "được",
        "đúng",
        "không",
        "ko",
        "có",
        "bình thường",
        "ổn",
        "không sao",
        "sẵn sàng",
        "tiếp tục",
        "yes",
        "no",
    }
)


def _is_contextual_follow_up(message: Any) -> bool:
    if not isinstance(message, str):
        return False
    normalized = " ".join(message.strip().casefold().split())
    if not normalized or len(normalized.split()) > 8:
        return False
    if normalized in _CONTEXTUAL_FOLLOW_UPS:
        return True
    return normalized.startswith(
        ("không ", "ko ", "mình ", "tôi ", "vậy ", "thế ", "còn ")
    )


def _merge_user_context(current: Any, incoming: Any, message: Any) -> Any:
    """Merge only legacy short follow-ups; scoped snapshots otherwise replace.

    Current mobile clients resolve the conversational domain before sending and
    therefore include the correct typed profile on a reply such as ``oke``.
    The narrow merge keeps older clients working without retaining sensitive
    domain profiles for an unrelated general message.
    """

    if not isinstance(incoming, dict):
        return incoming
    readiness = incoming.get("profile_readiness")
    if isinstance(readiness, dict):
        incoming_scope = readiness.get("scope")
        if (
            incoming_scope == "general"
            and isinstance(current, dict)
            and _is_contextual_follow_up(message)
        ):
            merged = {**current, **incoming}
            for domain_key in (
                "workout_profile",
                "training_state",
                "exercise_history",
                "exercise_history_status",
                "exercise_history_loaded",
                "exercise_history_observed_at",
                "nutrition_profile",
                "dietary_restrictions",
                "nutrition_safety_profile",
                "daily_nutrition_summary",
            ):
                if domain_key not in incoming and domain_key in current:
                    merged[domain_key] = current[domain_key]
            return merged
        return dict(incoming)
    if isinstance(current, dict):
        return {**current, **incoming}
    return incoming


class ChatGateway:
    """Owns one WebSocket connection and one chat session."""

    def __init__(
        self,
        websocket: WebSocket,
        orchestrator: Any,
        session_id: str,
        db_session: Any = None,
        *,
        admission: Any = None,
        metrics: Any = None,
        queue_size: int = 4,
        enforce_backpressure: bool = False,
        retry_after_ms: int = 750,
    ) -> None:
        self.websocket = websocket
        self.orchestrator = orchestrator
        self.session_id = session_id
        self.db_session = db_session
        self.user_id: str | None = None
        self.tool_dispatcher: Any | None = getattr(orchestrator, "dispatcher", None)
        self._session_ensured = False
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.user_context: Any | None = None
        self.developer_authenticated = False
        self.authenticated_principal = False
        self.debug_trace_enabled = False
        self.admission = admission
        self.metrics = metrics
        self.queue_size = max(1, int(queue_size))
        self.enforce_backpressure = enforce_backpressure
        self.retry_after_ms = retry_after_ms

    async def _ensure_session_exists(self) -> bool:
        from db.db_status import is_db_offline, is_connectivity_failure, mark_db_offline
        if not self.db_session or self._session_ensured:
            return True
        if is_db_offline():
            logger.warning("Rejecting chat turn while database availability is unknown")
            return False
        try:
            import uuid
            uuid.UUID(self.session_id)
        except ValueError:
            logger.warning(f"Cannot ensure session: {self.session_id} is not a valid UUID")
            return True

        from sqlalchemy import text
        try:
            claimed = await self.db_session.execute(
                text(
                    """
                    INSERT INTO chat_sessions (id, user_id)
                    VALUES (:id, :user_id)
                    ON CONFLICT (id) DO UPDATE SET last_active = NOW()
                    WHERE chat_sessions.user_id = EXCLUDED.user_id
                    RETURNING user_id
                    """
                ),
                {"id": self.session_id, "user_id": self.user_id}
            )
            claimed_user_id = claimed.scalar_one_or_none()
            if claimed_user_id is None or str(claimed_user_id) != str(self.user_id):
                logger.warning("Rejected chat session owner mismatch for session=%s", self.session_id)
                return False
            await self.db_session.commit()
            self._session_ensured = True
            return True
        except Exception as e:
            if is_connectivity_failure(e):
                mark_db_offline(60.0)
            logger.error(f"Error ensuring session exists: {e}")
            await self.db_session.rollback()
            return False

    async def authenticate(self) -> bool:
        """Require a verified owner before accepting chat or session identity."""
        from services.auth import AuthenticationError, authenticate_token

        token = self._subprotocol_token()
        if not token:
            # Transitional compatibility for already-built clients. New
            # clients must use the request-only WebSocket subprotocol so
            # credentials never appear in access-log URLs.
            token = self.websocket.query_params.get("token")
        if not token:
            await self.websocket.close(code=4401)
            return False
        try:
            principal = await authenticate_token(token)
        except AuthenticationError as exc:
            logger.warning("Rejected chat WebSocket authentication reason=%s", exc)
            await self.websocket.close(code=4401)
            return False
        self.user_id = principal.user_id
        self.authenticated_principal = True
        self.developer_authenticated = principal.is_developer

        from config import settings
        self.debug_trace_enabled = settings.debug_trace_allowed_for(
            developer_authenticated=self.developer_authenticated
        )

        try:
            import uuid
            uuid.UUID(self.session_id)
        except ValueError:
            pass
        return True

    def _subprotocol_token(self) -> str | None:
        headers = getattr(self.websocket, "headers", {})
        raw = headers.get("sec-websocket-protocol", "") if headers else ""
        for protocol in raw.split(","):
            candidate = protocol.strip()
            if candidate.startswith("auth.") and len(candidate) > len("auth."):
                return candidate[len("auth."):]
        return None


    async def run(self) -> None:
        """Receive client messages and route them to the orchestrator/dispatcher."""
        last_backend_stage = "connected"
        last_stream_event = "none"
        queue: asyncio.Queue[tuple[str, str, Any, str | None]] = asyncio.Queue(
            maxsize=self.queue_size if self.enforce_backpressure else 0
        )

        async def _chat_worker() -> None:
            from services.backend_optimization import AdmissionRejected, chat_priority
            from services.agent.llm_client import (
                GarbledOutputError,
                LLMUnavailableError,
            )

            while True:
                sess_id, message, context, turn_id = await queue.get()
                outcome = "completed"
                turn_token = _CURRENT_TURN_ID.set(turn_id)
                try:
                    last_backend_stage = "orchestrator_started"
                    priority, urgent = chat_priority(message)
                    if self.admission is None:
                        await self._handle_chat(sess_id, message, context)
                    else:
                        async with self.admission.slot(
                            priority=priority, urgent=urgent
                        ):
                            await self._handle_chat(sess_id, message, context)
                    last_backend_stage = "orchestrator_completed"
                except AdmissionRejected:
                    last_backend_stage = "admission_rejected"
                    outcome = "busy"
                    if self.metrics:
                        self.metrics.increment("chat.server_busy")
                    await self.send_error(
                        "SERVER_BUSY",
                        "Hệ thống đang bận. Bạn thử lại sau một chút nhé.",
                        retry_after_ms=self.retry_after_ms,
                    )
                except (LLMUnavailableError, GarbledOutputError):
                    last_backend_stage = "provider_error"
                    # The orchestrator already sent the specific, user-safe
                    # provider error. Do not overwrite it with INTERNAL_ERROR.
                    outcome = "failed"
                except Exception as exc:
                    last_backend_stage = f"exception:{type(exc).__name__}"
                    outcome = "failed"
                    logger.exception(
                        "Chat turn failed stage=orchestrator exception_type=%s session=%s",
                        type(exc).__name__,
                        sess_id,
                    )
                    await self.send_error(
                        "INTERNAL_ERROR",
                        "Không thể xử lý yêu cầu lúc này. Bạn thử lại giúp mình nhé.",
                    )
                finally:
                    _CURRENT_TURN_ID.reset(turn_token)
                    if self.metrics:
                        self.metrics.increment(f"chat.turn_{outcome}")
                        self.metrics.gauge("chat.connection_queue_depth", queue.qsize())
                    queue.task_done()

        worker = asyncio.create_task(_chat_worker())
        try:
            while True:
                try:
                    data = await self.websocket.receive_json()
                except ValueError:
                    await self.send_error("BAD_MESSAGE", "Message must be valid JSON.")
                    continue

                msg_type = data.get("type") if isinstance(data, dict) else None
                if msg_type in ("chat", "chat_message"):
                    last_backend_stage = "message_received"
                    # Extract session_id from JSON payload if present and valid
                    session_id_from_data = data.get("session_id") if isinstance(data, dict) else None
                    # The verified connection principal is authoritative. A
                    # client-supplied owner can only confirm, never replace it.
                    user_id_from_data = data.get("user_id") if isinstance(data, dict) else None
                    if user_id_from_data and str(user_id_from_data).strip() != self.user_id:
                        await self.send_error("OWNER_MISMATCH", "User identity does not match the authenticated account.")
                        continue

                    # Extract dynamic user_context / user_profile if provided by client
                    incoming_context = data.get("user_context") or data.get("user_profile") if isinstance(data, dict) else None
                    if incoming_context is not None:
                        self.user_context = _merge_user_context(
                            self.user_context,
                            incoming_context,
                            data.get("message") if isinstance(data, dict) else None,
                        )

                    # Ensure the session exists in the database
                    if not await self._ensure_session_exists():
                        await self.send_error(
                            "SESSION_FORBIDDEN",
                            "Phiên trò chuyện này không thuộc về tài khoản hiện tại.",
                        )
                        continue

                    try:
                        self.latitude = float(data["latitude"]) if data.get("latitude") is not None else None
                        self.longitude = float(data["longitude"]) if data.get("longitude") is not None else None
                    except (ValueError, TypeError):
                        self.latitude = None
                        self.longitude = None

                    message = data.get("message")
                    if not isinstance(message, str) or not message.strip():
                        await self.send_error("BAD_MESSAGE", "message is required.")
                        continue
                    raw_turn_id = data.get("turn_id")
                    turn_id = (
                        raw_turn_id.strip()
                        if isinstance(raw_turn_id, str) and raw_turn_id.strip()
                        else None
                    )
                    if turn_id is not None and len(turn_id) > 128:
                        await self.send_error("BAD_MESSAGE", "turn_id is invalid.")
                        continue
                    
                    if not self.enforce_backpressure and queue.qsize() >= self.queue_size:
                        if self.metrics:
                            self.metrics.increment("chat.queue_would_reject")
                    try:
                        last_backend_stage = "turn_enqueued"
                        queue.put_nowait(
                            (
                                self.session_id,
                                message,
                                dict(self.user_context)
                                if isinstance(self.user_context, dict)
                                else self.user_context,
                                turn_id,
                            )
                        )
                    except asyncio.QueueFull:
                        if self.metrics:
                            self.metrics.increment("chat.queue_rejected")
                        await self.send_error(
                            "CHAT_QUEUE_FULL",
                            "Bạn đang gửi quá nhanh. Hãy đợi tin nhắn trước hoàn tất nhé.",
                            retry_after_ms=self.retry_after_ms,
                        )
                        continue
                    if self.metrics:
                        self.metrics.increment("chat.message_enqueued")
                        self.metrics.gauge("chat.connection_queue_depth", queue.qsize())
                elif msg_type == "tool_result":
                    last_stream_event = "tool_result"
                    correlation_id = data.get("correlation_id")
                    if not isinstance(correlation_id, str) or not correlation_id:
                        await self.send_error("BAD_MESSAGE", "tool_result.correlation_id is required.")
                        continue
                    try:
                        if self.tool_dispatcher and hasattr(self.tool_dispatcher, "on_tool_result"):
                            self.tool_dispatcher.on_tool_result(correlation_id, data)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        await self.send_error(
                            "INTERNAL_ERROR",
                            "Không thể xử lý yêu cầu lúc này. Bạn thử lại giúp mình nhé.",
                        )
                elif msg_type == "semantic_shadow":
                    # Untrusted client output is observation-only. Keep this
                    # outside the chat queue and never merge it into context.
                    from services.agent.semantic_shadow import (
                        SemanticShadowValidationError,
                        validate_semantic_shadow_message,
                    )

                    try:
                        observation = validate_semantic_shadow_message(data)
                    except SemanticShadowValidationError:
                        if self.metrics:
                            self.metrics.increment("semantic_shadow.invalid")
                        continue
                    if self.metrics:
                        self.metrics.increment("semantic_shadow.valid")
                        if observation["slm_invoked"]:
                            self.metrics.increment("semantic_shadow.slm_invoked")
                        else:
                            self.metrics.increment("semantic_shadow.slm_bypassed")
                    await self.send_debug_trace(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "category": "routing",
                            "component": "semantic_router_s1",
                            "operation": "SEMANTIC_SHADOW_OBSERVED",
                            "sanitized_payload": observation,
                            "correlation_id": observation["turn_id"],
                            "latency_ms": (
                                observation.get("parse", {}).get("latency_ms")
                                if isinstance(observation.get("parse"), dict)
                                else None
                            ),
                            "result": "OBSERVED_ONLY",
                        }
                    )
                else:
                    await self.send_error("BAD_MESSAGE", "Unsupported message type.")
        except WebSocketDisconnect as exc:
            logger.info(
                "WebSocket disconnected session=%s server_ws_close_code=%s "
                "server_terminal_reason=client_disconnect last_backend_stage=%s "
                "last_stream_event=%s",
                self.session_id,
                getattr(exc, "code", None),
                last_backend_stage,
                last_stream_event,
            )
        finally:
            # Let an already dequeued, synchronous/fast turn commit its result
            # before cancellation. Long-running provider/tool work is still
            # cancelled immediately on the following loop tick.
            await asyncio.sleep(0)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker

    async def _handle_chat(self, session_id: str, message: str, context: Any) -> None:
        try:
            await self.orchestrator.handleChatMessage(
                session_id, message, user_context=context
            )
        except TypeError:
            await self.orchestrator.handleChatMessage(session_id, message)
        if self.db_session:
            try:
                await self.db_session.commit()
            except Exception as exc:
                logger.warning("DB commit failed: %s", exc)

    async def send_token(self, content: str) -> None:
        await self.websocket.send_json(
            self._turn_payload({"type": "token", "content": content})
        )

    async def send_status(self, content: str) -> None:
        await self.websocket.send_json(
            self._turn_payload({"type": "status", "content": content})
        )

    async def send_public_trace(self, public_trace: dict[str, Any]) -> None:
        """Send an allowlisted, user-safe trace snapshot to the UI."""
        await self.websocket.send_json(
            self._turn_payload({"type": "public_trace", "trace": public_trace})
        )

    async def send_debug_trace(self, debug_trace: dict[str, Any]) -> None:
        """Server-gated execution telemetry for authorised developer builds."""
        if not self.debug_trace_enabled:
            return
        await self.websocket.send_json(
            self._turn_payload({"type": "debug_trace", "event": debug_trace})
        )

    async def send_action_state(self, action_state: dict[str, Any]) -> None:
        """Normal-channel, human-readable pending/persistence state only."""
        await self.websocket.send_json(
            self._turn_payload({"type": "action_state", "state": action_state})
        )

    async def send_tool_call(
        self, correlation_id: str, name: str, args: dict[str, Any], timeout_ms: int
    ) -> None:
        await self.websocket.send_json(
            self._turn_payload({
                "type": "tool_call",
                "correlation_id": correlation_id,
                "name": name,
                "arguments": args,
                "timeout_ms": timeout_ms,
            })
        )

    async def send_done(
        self,
        full_response: str,
        *,
        structured_data: dict[str, Any] | None = None,
        public_trace: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "done",
            "full_response": full_response,
        }
        if structured_data is not None:
            payload["structured"] = structured_data
        if public_trace is not None:
            payload["public_trace"] = public_trace
        await self.websocket.send_json(self._turn_payload(payload))

    async def send_error(
        self,
        code: str,
        message: str,
        *,
        retry_after_ms: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {"type": "error", "code": code, "message": message}
        if retry_after_ms is not None:
            payload["retry_after_ms"] = retry_after_ms
        await self.websocket.send_json(self._turn_payload(payload))

    @staticmethod
    def _turn_payload(payload: dict[str, Any]) -> dict[str, Any]:
        turn_id = _CURRENT_TURN_ID.get()
        if turn_id:
            payload["turn_id"] = turn_id
        return payload


__all__ = ["ChatGateway"]
