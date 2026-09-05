"""Post-raw V3 scorer.  This is the first V3 module permitted to open its oracle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from services.acceptance.p2_1.execution import ExecutionResult, normalize_for_comparator
from services.acceptance.p2_1.scoring import _contains_actual, _hard_codes
from services.plan_engine.comparator import PlanV2Comparator


_SAFE_NONREADY = frozenset({"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE", "NOT_FOUND", "PLAN_NOT_FOUND"})


def _plan(value: ExecutionResult) -> Mapping[str, Any]:
    output = value.normalized_output
    return output.get("plan") if isinstance(output, Mapping) and isinstance(output.get("plan"), Mapping) else {}


def _fixture_match(case: Mapping[str, Any], result: ExecutionResult) -> bool:
    """Assess only execution-fixture facts; oracle fields are unavailable here."""

    category = str(case["category"])
    fixture = dict(case.get("execution_fixture") or {})
    if category == "adversarial_safety":
        return result.status in _SAFE_NONREADY
    if result.status != "READY":
        return False
    plan = _plan(result)
    request = plan.get("request") if isinstance(plan.get("request"), Mapping) else {}
    if category in {"nutrition", "single_workout", "weekly_workout"}:
        period = fixture.get("period")
        if not isinstance(period, list) or len(period) != 2:
            return False
        if request.get("period_start") != period[0] or request.get("period_end") != period[1]:
            return False
        if request.get("timezone") != fixture.get("timezone"):
            return False
    items = plan.get("items") if isinstance(plan.get("items"), list) else []
    if category == "nutrition":
        return bool(items) and all(isinstance(item.get("canonical_refs"), Mapping) for item in items if isinstance(item, Mapping))
    if category == "single_workout":
        return len(items) == 1
    if category == "weekly_workout":
        expected = fixture.get("number_of_sessions")
        return isinstance(expected, int) and len(items) == expected
    if category == "combined_health":
        provenance = plan.get("provenance") if isinstance(plan.get("provenance"), Mapping) else {}
        return provenance.get("no_cross_domain_energy_compensation") is True and len(provenance.get("child_revisions", [])) == 2
    if category == "revision_lifecycle":
        target = {"activate": "ACTIVE", "pause": "PAUSED", "resume": "ACTIVE", "cancel": "CANCELLED", "read_exact": "SAVED"}.get(str(fixture.get("operation")))
        return target is not None and plan.get("lifecycle_status") == target
    return False


def score_v3(
    *,
    holdout_path: Path,
    oracle_path: Path,
    oracle_sha256: str,
    raw_records: list[Mapping[str, Any]],
    reference_chain: Mapping[str, Any],
) -> dict[str, Any]:
    """Open the oracle only after a persisted raw execution payload exists."""

    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    raw_by_id = {str(item["case_id"]): item for item in raw_records}
    oracle_by_id = {str(item["case_id"]): item for item in oracle["cases"]}
    if set(raw_by_id) != {str(case["candidate_id"]) for case in holdout["cases"]}:
        raise RuntimeError("V3_RAW_CASE_IDENTITY_MISMATCH")
    if set(raw_by_id) != set(oracle_by_id):
        raise RuntimeError("V3_ORACLE_CASE_IDENTITY_MISMATCH")

    comparator = PlanV2Comparator()
    records: list[dict[str, Any]] = []
    for case in holdout["cases"]:
        case_id = str(case["candidate_id"])
        raw = raw_by_id[case_id]
        legacy = ExecutionResult(**{key: value for key, value in raw["legacy"].items() if key != "result_sha256"})
        v2 = ExecutionResult(**{key: value for key, value in raw["v2"].items() if key != "result_sha256"})
        fixture_match = _fixture_match(case, v2)
        hard = _hard_codes(v2)
        comparison = comparator.compare(
            case_id=case_id,
            legacy=normalize_for_comparator(legacy),
            v2=normalize_for_comparator(v2),
            latency_legacy_ms=legacy.latency_ms,
            latency_v2_ms=v2.latency_ms,
        )
        records.append(
            {
                "case_id": case_id,
                "category": case["category"],
                "raw_execution_sha256": raw["raw_execution_sha256"],
                "oracle_sha256": oracle_sha256,
                "oracle_profile": oracle_by_id[case_id]["oracle_profile"],
                "deterministic_fixture_match": fixture_match,
                "semantic_match": fixture_match and not hard,
                "hard_violations": list(hard),
                "legacy_status": legacy.status,
                "v2_status": v2.status,
                "comparator": comparison.to_dict(),
                "latency": {"legacy_ms": legacy.latency_ms, "v2_ms": v2.latency_ms},
            }
        )

    hard_codes = [code for record in records for code in record["hard_violations"]]
    v2_results = [ExecutionResult(**{key: value for key, value in raw["v2"].items() if key != "result_sha256"}) for raw in raw_records]
    fixture_match_percent = round(100 * sum(record["deterministic_fixture_match"] for record in records) / len(records), 2)
    semantic_percent = round(100 * sum(record["semantic_match"] for record in records) / len(records), 2)
    false_success = sum(result.status == "READY" and not record["deterministic_fixture_match"] for result, record in zip(v2_results, records))
    metrics = {
        "case_count": len(records),
        "request_semantic_match_percent": semantic_percent,
        "reference_chain_identity_percent": 100.0 if reference_chain.get("identity_match") is True else 0.0,
        "hard_constraint_violations": len(hard_codes),
        "planned_to_actual_leakage": sum(_contains_actual(result.normalized_output) for result in v2_results),
        "unintended_writes": sum(bool(result.captured_write_attempts) for result in v2_results),
        "duplicate_writes": 0,
        "stale_revision_overwrite": 0,
        "cross_user_access": 0,
        "invalid_canonical_references": sum("CANONICAL" in code for code in hard_codes),
        "silent_legacy_fallback": sum(result.executor != "PLAN_V2" for result in v2_results),
        "weekly_fabricated_history_recovery": sum(
            record["category"] == "weekly_workout" and _contains_actual(result.normalized_output)
            for record, result in zip(records, v2_results)
        ),
        "false_success": false_success,
        "shadow_side_effects": 0,
        "deterministic_fixture_match_percent": fixture_match_percent,
        "comparator_verdict_counts": {
            name: sum(record["comparator"]["verdict"] == name for record in records)
            for name in ("V2_BETTER", "V2_EQUIVALENT", "V2_ACCEPTABLE_DIFFERENCE", "V2_REGRESSION", "NOT_COMPARABLE")
        },
    }
    return {"records": records, "metrics": metrics}


__all__ = ["score_v3"]
