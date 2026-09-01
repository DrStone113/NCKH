"""Developer-only execution telemetry for chat turns.

``DebugTraceBuilder`` observes routing and tool execution.  It is intentionally
not a model-reasoning viewer: provider scratchpads are classified as
``INTERNAL_REASONING`` and their content is discarded before this trace is
built or streamed.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final


_SENSITIVE_KEY_PARTS: Final[tuple[str, ...]] = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "firebase",
    "cookie",
    "password",
    "secret",
    "private_key",
    "service_account",
    "credential",
    "email",
    "phone",
    "latitude",
    "longitude",
    "location",
)
_BEARER_RE: Final[re.Pattern[str]] = re.compile(r"\bBearer\s+[^\s]+", re.IGNORECASE)
_JWT_RE: Final[re.Pattern[str]] = re.compile(r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_.-]+")
_PEM_RE: Final[re.Pattern[str]] = re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----")
_INLINE_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[=:]\s*[^\s,;]+",
    re.IGNORECASE,
)
_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
)
_PHONE_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)\+?\d[\d .()-]{7,}\d(?!\w)")
_INLINE_LOCATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(latitude|longitude|location)\s*[=:]\s*[^\s,;]+", re.IGNORECASE
)
_MAX_DEPTH: Final[int] = 8
_MAX_STRING_LENGTH: Final[int] = 512


def redact_debug_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    """Recursively redact credentials and unnecessary identifying fields."""

    normalized_key = (key or "").lower()
    if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            str(item_key): redact_debug_value(
                item_value, key=str(item_key), depth=depth + 1
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_debug_value(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        redacted = _BEARER_RE.sub("[REDACTED]", value)
        redacted = _JWT_RE.sub("[REDACTED_JWT]", redacted)
        redacted = _PEM_RE.sub("[REDACTED_PRIVATE_KEY]", redacted)
        redacted = _INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
        redacted = _INLINE_LOCATION_RE.sub(
            lambda match: f"{match.group(1)}=[REDACTED]", redacted
        )
        if len(redacted) > _MAX_STRING_LENGTH:
            return redacted[:_MAX_STRING_LENGTH] + "…[TRUNCATED]"
        return redacted
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_debug_value(str(value), key=key, depth=depth + 1)


@dataclass(frozen=True, slots=True)
class DeveloperTraceEvent:
    timestamp: str
    category: str
    component: str
    operation: str
    sanitized_payload: dict[str, Any]
    correlation_id: str | None = None
    latency_ms: float | None = None
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": self.timestamp,
            "category": self.category,
            "component": self.component,
            "operation": self.operation,
            "sanitized_payload": self.sanitized_payload,
        }
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.result is not None:
            payload["result"] = self.result
        return payload


@dataclass(slots=True)
class DebugTraceBuilder:
    """In-memory, bounded developer telemetry; never chat history."""

    enabled: bool = False
    events: list[DeveloperTraceEvent] = field(default_factory=list)
    max_events: int = 100

    def record(
        self,
        category: str,
        component: str,
        operation: str,
        *,
        payload: Any = None,
        correlation_id: str | None = None,
        latency_ms: float | None = None,
        result: str | None = None,
    ) -> DeveloperTraceEvent | None:
        if not self.enabled or len(self.events) >= self.max_events:
            return None
        safe_payload = redact_debug_value(payload if payload is not None else {})
        if not isinstance(safe_payload, dict):
            safe_payload = {"value": safe_payload}
        event = DeveloperTraceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            component=component,
            operation=operation,
            sanitized_payload=safe_payload,
            correlation_id=correlation_id,
            latency_ms=latency_ms,
            result=result,
        )
        self.events.append(event)
        return event


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def classify_provider_token(token: Any) -> str:
    """Classify provider stream data without retaining hidden reasoning text."""

    token_type = str(getattr(token, "token_type", "token")).lower()
    if token_type in {"thought", "analysis", "thinking", "reasoning", "reasoning_content"}:
        return "INTERNAL_REASONING"
    if token_type in {"reasoning_summary", "display_reasoning_summary"}:
        return "REASONING_SUMMARY_ALLOWED"
    if token_type in {"usage", "usage_metadata"}:
        return "USAGE"
    if token_type in {"error", "provider_error"}:
        return "ERROR"
    return "VISIBLE_CONTENT"


__all__ = [
    "DebugTraceBuilder",
    "DeveloperTraceEvent",
    "classify_provider_token",
    "elapsed_ms",
    "redact_debug_value",
]
