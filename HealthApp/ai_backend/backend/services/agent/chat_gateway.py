"""WebSocket transport for the tool-using chat agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ChatGateway:
    """Owns one WebSocket connection and one chat session."""

    def __init__(self, websocket: WebSocket, orchestrator: Any, session_id: str, db_session: Any = None) -> None:
        self.websocket = websocket
        self.orchestrator = orchestrator
        self.session_id = session_id
        self.db_session = db_session
        self.user_id: str | None = None
        self.tool_dispatcher: Any | None = getattr(orchestrator, "dispatcher", None)
        self._session_ensured = False

    async def _ensure_session_exists(self) -> None:
        if not self.db_session or self._session_ensured:
            return
        try:
            import uuid
            uuid.UUID(self.session_id)
        except ValueError:
            logger.warning(f"Cannot ensure session: {self.session_id} is not a valid UUID")
            return

        from sqlalchemy import text
        try:
            await self.db_session.execute(
                text(
                    """
                    INSERT INTO chat_sessions (id, user_id)
                    VALUES (:id, :user_id)
                    ON CONFLICT (id) DO UPDATE SET last_active = NOW()
                    """
                ),
                {"id": self.session_id, "user_id": self.user_id}
            )
            await self.db_session.commit()
            self._session_ensured = True
        except Exception as e:
            logger.error(f"Error ensuring session exists: {e}")
            await self.db_session.rollback()

    async def authenticate(self) -> bool:
        """Bypass authentication for now, but validate JWT if provided."""
        token = self.websocket.query_params.get("token")
        if token:
            import jwt
            from config import settings
            try:
                payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
                self.user_id = payload.get("sub") or "anonymous"
            except jwt.PyJWTError:
                await self.websocket.close(code=4401)
                return False
        else:
            self.user_id = "anonymous"

        try:
            import uuid
            uuid.UUID(self.session_id)
            await self._ensure_session_exists()
        except ValueError:
            pass
        return True


    async def run(self) -> None:
        """Receive client messages and route them to the orchestrator/dispatcher."""
        try:
            while True:
                try:
                    data = await self.websocket.receive_json()
                except ValueError:
                    await self.send_error("BAD_MESSAGE", "Message must be valid JSON.")
                    continue

                msg_type = data.get("type") if isinstance(data, dict) else None
                if msg_type in ("chat", "chat_message"):
                    # Extract session_id from JSON payload if present and valid
                    session_id_from_data = data.get("session_id") if isinstance(data, dict) else None
                    if session_id_from_data and session_id_from_data != self.session_id:
                        try:
                            import uuid
                            uuid.UUID(session_id_from_data)
                            self.session_id = session_id_from_data
                            self._session_ensured = False
                        except ValueError:
                            pass

                    # Ensure the session exists in the database
                    await self._ensure_session_exists()

                    message = data.get("message")
                    if not isinstance(message, str) or not message.strip():
                        await self.send_error("BAD_MESSAGE", "message is required.")
                        continue
                    
                    async def _handle_chat_task(sess_id: str, msg: str) -> None:
                        try:
                            await self.orchestrator.handleChatMessage(sess_id, msg)
                            if self.db_session:
                                await self.db_session.commit()
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            if self.db_session:
                                await self.db_session.rollback()
                            await self.send_error("INTERNAL_ERROR", str(e))
                            
                    import asyncio
                    asyncio.create_task(_handle_chat_task(self.session_id, message))
                elif msg_type == "tool_result":
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
                        await self.send_error("INTERNAL_ERROR", str(e))
                else:
                    await self.send_error("BAD_MESSAGE", "Unsupported message type.")
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def send_token(self, content: str) -> None:
        await self.websocket.send_json({"type": "token", "content": content})

    async def send_tool_call(
        self, correlation_id: str, name: str, args: dict[str, Any], timeout_ms: int
    ) -> None:
        await self.websocket.send_json(
            {
                "type": "tool_call",
                "correlation_id": correlation_id,
                "name": name,
                "arguments": args,
                "timeout_ms": timeout_ms,
            }
        )

    async def send_done(self, full_response: str, performed_actions: list[dict[str, Any]], structured_data: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "type": "done",
            "full_response": full_response,
            "performed_actions": performed_actions,
        }
        if structured_data is not None:
            payload["structured"] = structured_data
        await self.websocket.send_json(payload)

    async def send_error(self, code: str, message: str) -> None:
        await self.websocket.send_json({"type": "error", "code": code, "message": message})


__all__ = ["ChatGateway"]