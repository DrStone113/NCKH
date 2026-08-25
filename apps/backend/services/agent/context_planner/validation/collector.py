"""Append-only, privacy-aware collection of genuine D3.0 shadow turns."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Iterable
from uuid import uuid4

from .privacy import redact_query
from .token_measurement import TokenMeasurements


NATURAL_COLLECTION_SCHEMA_VERSION = "natural-shadow-record-v1"


class NaturalShadowCollector:
    """Collect routing evidence only; raw health profiles are never accepted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._sequence_ids: dict[str, str] = {}
        self._lock = threading.Lock()

    def _sequence_id(self, session_id: str) -> str:
        # Mapping remains process-local. Neither the raw session ID nor a
        # reversible derivative is persisted in the artifact.
        return self._sequence_ids.setdefault(session_id, f"sequence-{uuid4().hex}")

    def collect(
        self, *, session_id: str, query: str, conversational_context: Iterable[str],
        shadow_result: Any, token_measurements: TokenMeasurements,
    ) -> dict[str, Any]:
        redacted_query, query_redactions = redact_query(query)
        redacted_context: list[str] = []
        redaction_categories = set(query_redactions)
        for turn in list(conversational_context)[-4:]:
            redacted, categories = redact_query(str(turn))
            redacted_context.append(redacted)
            redaction_categories.update(categories)
        bundle = shadow_result.bundle
        statuses = {
            source.value: status.value
            for section in bundle.sections
            for source, status in section.source_status
        }
        record = {
            "record_schema_version": NATURAL_COLLECTION_SCHEMA_VERSION,
            "record_id": f"natural-{uuid4().hex}",
            "sequence_id": self._sequence_id(session_id),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "query": redacted_query,
            "conversational_context": redacted_context,
            "redaction_categories": sorted(redaction_categories),
            "source_statuses": statuses,
            "shadow_context_plan": shadow_result.plan.to_dict(),
            "planner_version": shadow_result.plan.plan_version,
            "token_measurements": token_measurements.to_dict(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record


_collectors: dict[str, NaturalShadowCollector] = {}
_collectors_lock = threading.Lock()


def get_natural_collector(path: str) -> NaturalShadowCollector:
    resolved = str(Path(path).resolve())
    with _collectors_lock:
        return _collectors.setdefault(resolved, NaturalShadowCollector(resolved))


__all__ = ["NATURAL_COLLECTION_SCHEMA_VERSION", "NaturalShadowCollector", "get_natural_collector"]
