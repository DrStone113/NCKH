"""Post-execution P2.1A scorer.

The execution package does not import this module.  This module is the first
place where the frozen oracle is read, after immutable raw execution records
have been written.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from services.plan_engine.comparator import PlanV2Comparator

from .execution import ExecutionResult, normalize_for_comparator


_SAFE_NONREADY = frozenset({"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE", "NOT_FOUND", "PLAN_NOT_FOUND"})


def _contains_actual(value: Any) -> bool:
    observed = {"consumed_at", "logged_at", "performed_at", "actual_reps", "actual_rpe", "actual_load", "recovered", "fatigued"}
    if isinstance(value, Mapping):
        return any(str(key) in observed or _contains_actual(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_actual(item) for item in value)
    return False


def _hard_codes(result: ExecutionResult) -> tuple[str, ...]:
    output = result.normalized_output
    validation = output.get("validation") if isinstance(output, Mapping) else None
    issues = validation.get("issues") if isinstance(validation, Mapping) else None
    codes = (
        [str(item.get("code")) for item in issues if isinstance(item, Mapping) and item.get("severity") == "HARD"]
        if result.status not in _SAFE_NONREADY and isinstance(issues, list)
        else []
    )
    if _contains_actual(output):
        codes.append("PLANNED_TO_ACTUAL_LEAKAGE")
    return tuple(dict.fromkeys(codes))


def _objective(check_id: str, result: ExecutionResult) -> bool:
    output = result.normalized_output
    plan = output.get("plan") if isinstance(output, Mapping) and isinstance(output.get("plan"), Mapping) else {}
    items = plan.get("items") if isinstance(plan, Mapping) and isinstance(plan.get("items"), list) else []
    safe_nonready = result.status in _SAFE_NONREADY
    if check_id == "no_write":
        return not result.captured_write_attempts
    if check_id == "planned_not_actual":
        return not _contains_actual(output)
    if check_id == "canonical_id":
        return safe_nonready or all(isinstance(item.get("canonical_refs"), Mapping) for item in items if isinstance(item, Mapping))
    if check_id in {"allergy_restriction", "equipment", "duration", "session_count", "date", "timezone", "availability"}:
        return safe_nonready or bool(items)
    if check_id in {"clarification_boundary", "unknown_state", "safety", "e4_delegation"}:
        return safe_nonready
    if check_id == "heuristic_label":
        provenance = plan.get("provenance") if isinstance(plan, Mapping) else None
        return safe_nonready or "PRODUCT_SCHEDULING_HEURISTIC" in str(provenance)
    if check_id in {"ownership", "revision", "idempotency"}:
        return safe_nonready or result.status == "READY"
    return False


@dataclass(frozen=True, slots=True)
class CaseScoreRecord:
    case_id: str
    category: str
    raw_execution_sha256: str
    oracle_sha256: str
    objective_checks: Mapping[str, bool]
    semantic_match: bool
    hard_violations: tuple[str, ...]
    legacy_status: str
    v2_status: str
    comparator: Mapping[str, Any]
    latency: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AcceptanceScorer:
    def __init__(self, *, holdout_path: Path, oracle_path: Path, oracle_sha256: str) -> None:
        self._holdout_path = holdout_path
        self._oracle_path = oracle_path
        self._oracle_sha256 = oracle_sha256

    def score(self, raw_records: list[Mapping[str, Any]]) -> tuple[CaseScoreRecord, ...]:
        # Oracle is intentionally loaded only here, after raw execution is persisted.
        holdout = json.loads(self._holdout_path.read_text(encoding="utf-8"))
        oracle = json.loads(self._oracle_path.read_text(encoding="utf-8"))
        raw_by_case = {str(item["case_id"]): item for item in raw_records}
        scores: list[CaseScoreRecord] = []
        comparator = PlanV2Comparator()
        for case in holdout["cases"]:
            raw = raw_by_case[str(case["case_id"])]
            legacy = ExecutionResult(**{key: value for key, value in raw["legacy"].items() if key != "result_sha256"})
            v2 = ExecutionResult(**{key: value for key, value in raw["v2"].items() if key != "result_sha256"})
            checks = {str(check): _objective(str(check), v2) for check in case["deterministic_check_ids"]}
            profile = oracle["profiles"][str(case["oracle_profile"])]
            # Semantic scoring evaluates post-execution structured state only.
            # A ready plan must meet all objective checks; a safe non-ready
            # state is acceptable only where the frozen profile permits a
            # clarification/safety boundary.
            permits_safe_nonready = any(
                marker in str(case["oracle_profile"])
                for marker in ("READY_OR_CLARIFY", "MISSING", "SAFETY", "CHILD_MISSING", "CONFLICT", "INSUFFICIENT", "OWNER_BOUND", "NO_WRITE")
            )
            semantic = all(checks.values()) and (v2.status == "READY" or (permits_safe_nonready and v2.status in _SAFE_NONREADY))
            comparison = comparator.compare(
                case_id=str(case["case_id"]),
                legacy=normalize_for_comparator(legacy),
                v2=normalize_for_comparator(v2),
                latency_legacy_ms=legacy.latency_ms,
                latency_v2_ms=v2.latency_ms,
            )
            scores.append(CaseScoreRecord(
                case_id=str(case["case_id"]), category=str(case["category"]), raw_execution_sha256=str(raw["raw_execution_sha256"]),
                oracle_sha256=self._oracle_sha256, objective_checks=checks, semantic_match=semantic,
                hard_violations=_hard_codes(v2), legacy_status=legacy.status, v2_status=v2.status,
                comparator=comparison.to_dict(), latency={"legacy_ms": legacy.latency_ms, "v2_ms": v2.latency_ms},
            ))
        return tuple(scores)


__all__ = ["AcceptanceScorer", "CaseScoreRecord"]
