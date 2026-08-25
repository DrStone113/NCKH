"""Development-only structured observability for one production chat turn.

The trace is emitted to the backend logger only. It is never returned through
the WebSocket or persisted with chat/research records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import Any
from uuid import uuid4


logger = logging.getLogger("development.context_trace")

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "password",
        "secret",
        "token",
        "api_key",
        "email",
        "name",
    }
)
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s.-]?){8,15}(?!\d)")
_SECRET_RE = re.compile(
    r"(?i)\b(?:bearer\s+[a-z0-9._~+/=-]+|sk-[a-z0-9_-]{12,}|"
    r"(?:api[_ -]?key|access[_ -]?token)\s*[:=]\s*[^\s,;]+)"
)


def _pseudonym(value: object) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"user:{digest}"


def _sanitize(value: Any, key: str | None = None) -> Any:
    normalized_key = (key or "").lower()
    leaf_key = normalized_key.rsplit(".", 1)[-1]
    if leaf_key in _SENSITIVE_KEYS or any(
        marker in normalized_key for marker in ("password", "secret", "token", "api_key")
    ):
        return "[REDACTED]"
    if leaf_key in {"user_id", "userid", "profile_id"}:
        return _pseudonym(value)
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _SECRET_RE.sub(
            "[SECRET]",
            _PHONE_RE.sub("[PHONE]", _EMAIL_RE.sub("[EMAIL]", value)),
        )
    return value


@dataclass(slots=True)
class ContextTrace:
    trace_id: str
    timestamp: str
    user_query: str
    available_sources: list[str] = field(default_factory=list)
    selected_sources: list[str] = field(default_factory=list)
    source_values: dict[str, Any] = field(default_factory=dict)
    source_timestamps: dict[str, Any] = field(default_factory=dict)
    source_status: dict[str, Any] = field(default_factory=dict)
    source_conflicts: dict[str, Any] = field(default_factory=dict)
    rag_requested: bool = False
    rag_result_status: str = "NOT_REQUESTED"
    tools_offered: list[str] = field(default_factory=list)
    tools_called: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    calculation_inputs: dict[str, Any] = field(default_factory=dict)
    calculation_outputs: dict[str, Any] = field(default_factory=dict)
    calculation_provenance: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    final_context_manifest: dict[str, Any] = field(default_factory=dict)
    production_router_behavior: dict[str, Any] = field(default_factory=dict)
    production_sources_accessed: list[str] = field(default_factory=list)
    shadow_primary_intent: str | None = None
    shadow_secondary_intents: list[str] = field(default_factory=list)
    shadow_context_plan: dict[str, Any] = field(default_factory=dict)
    shadow_sources_requested: list[str] = field(default_factory=list)
    shadow_tools_offered: list[str] = field(default_factory=list)
    shadow_rag_policy: str | None = None
    current_context_size_characters: int = 0
    shadow_context_size_characters: int = 0
    shadow_missing_required_sources: list[str] = field(default_factory=list)
    shadow_context_bundle: dict[str, Any] = field(default_factory=dict)
    planner_latency_ms: float | None = None
    shadow_token_measurements: dict[str, Any] = field(default_factory=dict)


class ContextTraceRecorder:
    def __init__(self, user_query: str, *, enabled: bool) -> None:
        self.enabled = enabled
        self.trace = ContextTrace(
            trace_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_query=_sanitize(user_query),
        )
        self._emitted = False

    def capture_initial_context(self, user_context: Any) -> None:
        if not self.enabled or not isinstance(user_context, dict):
            return
        manifest = user_context.get("state_manifest")
        available_sources: set[str] = set()
        for field_name, envelope in (
            manifest.items() if isinstance(manifest, dict) else ()
        ):
            if not isinstance(envelope, dict):
                continue
            source = str(envelope.get("source") or "unknown")
            available_sources.add(source)
            self.trace.source_values[str(field_name)] = _sanitize(
                envelope.get("value"), str(field_name)
            )
            self.trace.source_timestamps[str(field_name)] = envelope.get("observed_at")
            self.trace.source_status[str(field_name)] = envelope.get("status")
            status = str(envelope.get("status") or "UNKNOWN")
            self.trace.validation_results.append(
                {
                    "subject": f"state:{field_name}",
                    "valid": status not in {"ERROR", "CONFLICT"},
                    "status": status,
                }
            )
            if envelope.get("conflict") is not None:
                self.trace.source_conflicts[str(field_name)] = _sanitize(
                    envelope["conflict"]
                )
            if source not in self.trace.selected_sources:
                self.trace.selected_sources.append(source)
        self.trace.available_sources = sorted(available_sources)
        self.trace.production_sources_accessed = list(self.trace.selected_sources)

        calculations = user_context.get("calculation_manifest")
        if isinstance(calculations, dict):
            self.trace.calculation_inputs = _sanitize(
                calculations.get("inputs", {})
            )
            self.trace.calculation_outputs = _sanitize(
                calculations.get("outputs", {})
            )
            provenance = calculations.get("formula_provenance", [])
            if isinstance(provenance, list):
                self.trace.calculation_provenance = _sanitize(provenance)

    def capture_rag(self, context: Any) -> None:
        if not self.enabled:
            return
        self.trace.rag_requested = bool(getattr(context, "rag_requested", False))
        self.trace.rag_result_status = str(
            getattr(context, "rag_result_status", "UNKNOWN")
        )
        structural_sources = []
        if getattr(context, "history", None):
            structural_sources.append("RECENT_CONVERSATION")
        if getattr(context, "pinned_facts", None):
            structural_sources.append("CONFIRMED_MEMORY")
        if self.trace.rag_requested:
            structural_sources.append("RAG")
        for source in structural_sources:
            if source not in self.trace.production_sources_accessed:
                self.trace.production_sources_accessed.append(source)

    def capture_tools_offered(self, schemas: Any) -> None:
        if not self.enabled or not isinstance(schemas, list):
            return
        names: list[str] = []
        for item in schemas:
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            if isinstance(function, dict) and function.get("name"):
                names.append(str(function["name"]))
        self.trace.tools_offered = names

    def capture_tool_call(self, name: str, arguments: Any) -> None:
        if self.enabled:
            self.trace.tools_called.append(
                {"name": name, "arguments": _sanitize(arguments)}
            )

    def capture_tool_result(self, name: str, result: Any) -> None:
        if not self.enabled:
            return
        entry = {
            "name": name,
            "ok": bool(getattr(result, "ok", False)),
            "error": getattr(result, "error", None),
            "data": _sanitize(getattr(result, "data", None)),
        }
        self.trace.tool_results.append(entry)
        data = getattr(result, "data", None)
        if name == "calculate_tdee" and isinstance(data, dict):
            provenance = data.get("formula_provenance")
            if isinstance(provenance, list):
                self.trace.calculation_provenance = _sanitize(provenance)
            self.trace.calculation_outputs = _sanitize(data)
        state = data.get("state") if isinstance(data, dict) else None
        if isinstance(state, dict):
            for field_name, envelope in state.items():
                if not isinstance(envelope, dict):
                    continue
                key = str(field_name)
                self.trace.source_values[key] = _sanitize(
                    envelope.get("value"), key
                )
                self.trace.source_timestamps[key] = envelope.get("observed_at")
                self.trace.source_status[key] = envelope.get("status")
                source = str(envelope.get("source") or "unknown")
                if source not in self.trace.selected_sources:
                    self.trace.selected_sources.append(source)
                if source not in self.trace.production_sources_accessed:
                    self.trace.production_sources_accessed.append(source)
                if envelope.get("conflict") is not None:
                    self.trace.source_conflicts[key] = _sanitize(
                        envelope["conflict"]
                    )
        self.trace.validation_results.append(
            {
                "subject": f"tool:{name}",
                "valid": entry["ok"],
                "error": entry["error"],
            }
        )

    def capture_production_router(self, plan: Any, *, context_size_characters: int) -> None:
        if not self.enabled:
            return
        self.trace.production_router_behavior = {
            "tier": getattr(plan, "tier", None),
            "use_heavy_model": bool(getattr(plan, "use_heavy_model", False)),
            "offer_tools": bool(getattr(plan, "offer_tools", False)),
            "prompt_mode": getattr(plan, "prompt_mode", None),
            "max_steps": getattr(plan, "max_steps", None),
        }
        self.trace.current_context_size_characters = context_size_characters

    def capture_shadow(self, result: Any) -> None:
        """Record only structural planner output; never raw bundle values."""
        if not self.enabled:
            return
        classification = result.classification
        plan = result.plan
        bundle = result.bundle
        self.trace.shadow_primary_intent = classification.primary_intent.value
        self.trace.shadow_secondary_intents = [item.value for item in classification.secondary_intents]
        self.trace.shadow_context_plan = plan.to_dict()
        self.trace.shadow_sources_requested = [
            item.value for item in (*plan.required_sources, *plan.optional_sources)
        ]
        self.trace.shadow_tools_offered = list(plan.permitted_tools)
        self.trace.shadow_rag_policy = plan.rag_policy.value
        self.trace.shadow_context_size_characters = bundle.planned_context_size_characters
        self.trace.shadow_missing_required_sources = [item.value for item in bundle.missing_required_sources]
        self.trace.shadow_context_bundle = bundle.to_dict()
        self.trace.planner_latency_ms = round(float(result.latency_ms), 3)

    def capture_token_measurements(self, measurements: Any) -> None:
        if self.enabled:
            self.trace.shadow_token_measurements = measurements.to_dict()

    def finish(self, *, outcome: str) -> None:
        if not self.enabled:
            return
        self.trace.final_context_manifest = {
            "outcome": outcome,
            "selected_sources": list(dict.fromkeys(self.trace.selected_sources)),
            "rag_result_status": self.trace.rag_result_status,
            "tools_called": [item["name"] for item in self.trace.tools_called],
            "source_status": self.trace.source_status,
            "conflict_fields": sorted(self.trace.source_conflicts),
        }

    def emit(self) -> None:
        if not self.enabled or self._emitted:
            return
        self._emitted = True
        logger.info(
            "CONTEXT_TRACE %s",
            json.dumps(_sanitize(asdict(self.trace)), ensure_ascii=False, default=str),
        )


__all__ = ["ContextTrace", "ContextTraceRecorder"]
