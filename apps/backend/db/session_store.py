"""
In-memory session cache with TTL-based expiry.
Thread-safe via threading.Lock.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import uuid4

from sqlalchemy import text

SESSION_TTL_MINUTES = 30


@dataclass
class ChatTurn:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    thoughts: str = ""
    structured_data: dict | None = None


@dataclass
class Session:
    session_id: str
    turns: list[ChatTurn] = field(default_factory=list)
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionStore:
    def __init__(self, ttl_minutes: int = SESSION_TTL_MINUTES) -> None:
        self._store: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)

    def _is_expired(self, session: Session) -> bool:
        return datetime.now(timezone.utc) - session.last_active > self._ttl

    def get_or_create_session(self, session_id: str) -> Session:
        with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                session = Session(session_id=session_id)
                self._store[session_id] = session
            return session

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        thoughts: str = "",
        structured_data: dict | None = None,
    ) -> None:
        with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                session = Session(session_id=session_id)
                self._store[session_id] = session
            session.turns.append(
                ChatTurn(
                    role=role,
                    content=content,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    thoughts=thoughts,
                    structured_data=structured_data,
                )
            )
            session.last_active = datetime.now(timezone.utc)

    def appendTurn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        thoughts: str = "",
        structured_data: dict | None = None,
    ) -> None:
        self.append_turn(
            session_id,
            role,
            content,
            tool_call_id,
            tool_name,
            thoughts,
            structured_data,
        )

    def get_history(self, session_id: str, max_turns: int = 10) -> list[ChatTurn]:
        with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                return []
            return session.turns[-max_turns:]

    def cleanup_expired(self) -> int:
        with self._lock:
            expired_ids = [
                sid for sid, session in self._store.items()
                if self._is_expired(session)
            ]
            for sid in expired_ids:
                del self._store[sid]
            return len(expired_ids)


# Singleton instance
session_store = SessionStore()


class DbSessionStore:
    """Append-only chat_messages writer used by AgentOrchestrator."""

    def __init__(self, db_session) -> None:
        self.db_session = db_session

    async def appendTurn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        thoughts: str = "",
        structured_data: dict | None = None,
    ) -> str:
        # Always record in memory cache so conversation history works in standalone mode
        session_store.append_turn(
            session_id,
            role,
            content,
            tool_call_id,
            tool_name,
            thoughts,
            structured_data,
        )
        msg_id = str(uuid4())
        if self.db_session is None:
            return msg_id
        from db.db_status import is_db_offline, mark_db_offline
        try:
            await self.db_session.execute(
                text(
                    """
                    INSERT INTO chat_messages (
                        id, session_id, role, content, tool_call_id, tool_name,
                        thoughts, structured_data
                    ) VALUES (
                        :id, :session_id, :role, :content, :tool_call_id, :tool_name,
                        :thoughts, CAST(:structured_data AS JSONB)
                    )
                    """
                ),
                {
                    "id": msg_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "thoughts": thoughts,
                    "structured_data": (
                        json.dumps(structured_data, ensure_ascii=False)
                        if structured_data is not None
                        else None
                    ),
                },
            )
        except Exception as e:
            mark_db_offline(60.0)
            import logging

            logging.getLogger(__name__).warning(
                "Database unavailable in DbSessionStore.appendTurn: %s", e
            )
        return msg_id
