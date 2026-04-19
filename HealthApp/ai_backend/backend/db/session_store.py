"""
In-memory session cache with TTL-based expiry.
Thread-safe via threading.Lock.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict

SESSION_TTL_MINUTES = 30


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class Session:
    session_id: str
    turns: list[ChatTurn] = field(default_factory=list)
    last_active: datetime = field(default_factory=datetime.utcnow)


class SessionStore:
    def __init__(self, ttl_minutes: int = SESSION_TTL_MINUTES) -> None:
        self._store: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)

    def _is_expired(self, session: Session) -> bool:
        return datetime.utcnow() - session.last_active > self._ttl

    def get_or_create_session(self, session_id: str) -> Session:
        with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                session = Session(session_id=session_id)
                self._store[session_id] = session
            return session

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                session = Session(session_id=session_id)
                self._store[session_id] = session
            session.turns.append(ChatTurn(role=role, content=content))
            session.last_active = datetime.utcnow()

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
