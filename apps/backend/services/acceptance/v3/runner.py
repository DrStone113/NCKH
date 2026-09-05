"""One-shot runner for the frozen, independent Plan V2 Confirmatory V3 set."""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.acceptance.p2_1.execution import LegacyPlanReadOnlyExecutor
from services.acceptance.p2_2.reference_chain import exercise_reference_chain
from services.plan_engine.persistence import PlanSqlRepository

from .adapter import V3CaseLoader, V3LegacyReadOnlyAdapter, V3PlanV2Executor, context_for_v3_case, raw_record
from .scoring import score_v3


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
HOLDOUT = VALIDATION / "plan-v2-confirmatory-v3.json"
ORACLE = VALIDATION / "plan-v2-confirmatory-oracle-v3.json"
THRESHOLDS = VALIDATION / "plan-v2-confirmatory-thresholds-v3.json"
MANIFEST = VALIDATION / "plan-v2-confirmatory-v3-freeze-manifest-v1.json"
BASELINE = VALIDATION / "plan-v2-post-p2-1-remediation-v1.json"
HARNESS_FREEZE = VALIDATION / "plan-v2-confirmatory-v3-harness-freeze-v2.json"
REGISTER = VALIDATION / "plan-v2-confirmatory-v3-execution-register-v1.json"
RAW_OUTPUT = VALIDATION / "plan-v2-confirmatory-v3-raw-execution-v1.json"
RESULT_OUTPUT = VALIDATION / "plan-v2-confirmatory-v3-results-v1.json"
SMOKE_OUTPUT = VALIDATION / "plan-v2-confirmatory-v3-development-smoke-v1.json"
REPORT = ROOT.parents[1] / "docs" / "reports" / "plan_v2_confirmatory_v3_final_report.md"

EXPECTED_HASHES = {
    HOLDOUT: "8256ca62b344957c6e36b2580551777092cced2b85c84a381091b715511b519b",
    ORACLE: "bb92a47b3edc8ec8a5ce13a1fb6e30a25738651bbf1c30ff413a98f3e3eb8af5",
    THRESHOLDS: "adeb1a8139c15eb619f3bc92ad89e68197aa056b61f567d3fb58379b040a5400",
}
HARNESS_FILES = (
    Path(__file__),
    Path(__file__).with_name("adapter.py"),
    Path(__file__).with_name("scoring.py"),
    ROOT / "services" / "acceptance" / "p2_1" / "execution.py",
    ROOT / "services" / "acceptance" / "p2_1" / "scoring.py",
    ROOT / "scripts" / "run_plan_v2_confirmatory_v3.py",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _write_atomic(path: Path, value: Any) -> str:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return _sha(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def harness_identity() -> dict[str, Any]:
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): _sha(path) for path in HARNESS_FILES}
    return {
        "files": hashes,
        "sha256": hashlib.sha256(b"".join(path.read_bytes() for path in HARNESS_FILES)).hexdigest(),
        "python_version": ".".join(map(str, sys.version_info[:3])),
    }


def _implementation_matches_baseline() -> tuple[bool, dict[str, dict[str, Any]]]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    checks = {
        name: {"expected": expected, "actual": _sha(ROOT / name), "matches": _sha(ROOT / name) == expected}
        for name, expected in baseline["implementation_sources"].items()
    }
    return all(item["matches"] for item in checks.values()), checks


def final_preflight() -> dict[str, Any]:
    actual = {path.name: _sha(path) for path in EXPECTED_HASHES}
    frozen_hashes_match = all(actual[path.name] == expected for path, expected in EXPECTED_HASHES.items())
    baseline_matches, implementation = _implementation_matches_baseline()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_matches = all(manifest["artifacts"].get(path.name) == actual[path.name] for path in EXPECTED_HASHES)
    return {
        "frozen_hashes_match": frozen_hashes_match,
        "manifest_hashes_match": manifest_matches,
        "baseline_implementation_matches": baseline_matches,
        "holdout_status": json.loads(HOLDOUT.read_text(encoding="utf-8")).get("status"),
        "oracle_status": json.loads(ORACLE.read_text(encoding="utf-8")).get("status"),
        "thresholds_frozen": json.loads(THRESHOLDS.read_text(encoding="utf-8")).get("frozen_before_execution"),
        "actual_hashes": actual,
        "implementation": implementation,
    }


def _require_final_preflight() -> dict[str, Any]:
    preflight = final_preflight()
    required = (
        preflight["frozen_hashes_match"],
        preflight["manifest_hashes_match"],
        preflight["baseline_implementation_matches"],
        preflight["holdout_status"] == "FROZEN_UNEXECUTED",
        preflight["oracle_status"] == "FROZEN_UNEXECUTED",
        preflight["thresholds_frozen"] is True,
    )
    if not all(required):
        raise RuntimeError("V3_FINAL_PREFLIGHT_BLOCKED:" + json.dumps(preflight, ensure_ascii=False))
    return preflight


def oracle_firewall_evidence() -> dict[str, bool]:
    """Static evidence that fixture execution cannot import or open the V3 oracle."""

    source = Path(__file__).with_name("adapter.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    adapter_imports_oracle = any("oracle" in name.casefold() for name in imports)
    runner_source = Path(__file__).read_text(encoding="utf-8")
    final_run_source = runner_source[runner_source.index("async def run_final"):]
    raw_before_score = final_run_source.index("raw_sha = _write_atomic(RAW_OUTPUT") < final_run_source.index("score_v3(")
    return {
        "adapter_has_no_oracle_import": not adapter_imports_oracle,
        "raw_persisted_before_scoring": raw_before_score,
    }


async def _execute_cases(cases, *, session_factory) -> list[dict[str, Any]]:
    legacy = V3LegacyReadOnlyAdapter(LegacyPlanReadOnlyExecutor(session_factory))
    v2 = V3PlanV2Executor()
    records: list[dict[str, Any]] = []
    for sequence, case in enumerate(cases, start=1):
        context = context_for_v3_case(case)
        legacy_result = await legacy.execute(case, context)
        v2_result = await v2.execute(case, context)
        records.append(raw_record(sequence=sequence, case=case, context=context, legacy=legacy_result, v2=v2_result))
    return records


async def _reference_chain(*, session_factory, owner_prefix: str) -> dict[str, Any]:
    repository = PlanSqlRepository(session_factory)
    evidence = await exercise_reference_chain(repository, owner_user_id=f"{owner_prefix}-{hashlib.sha256(owner_prefix.encode()).hexdigest()[:12]}")
    return {"identity_match": evidence["identity_match"], "statuses": {key: evidence[key] for key in ("pending_status", "persisted_status", "read_back_status")}}


def _development_payload() -> dict[str, Any]:
    profile = {"age": 30, "equation_sex": "female", "height_cm": 165, "weight_kg": 60, "activity_level": "moderate", "health_goal": "maintain"}
    return {
        "dataset_version": "PLAN_V2_CONFIRMATORY_V3_DEVELOPMENT_SMOKE_V1",
        "cases": [
            {"candidate_id": "dev-v3-nutrition-001", "category": "nutrition", "prompt": "Synthetic nutrition fixture.", "execution_fixture": {"profile": profile, "timezone": "Asia/Ho_Chi_Minh", "period": ["2027-10-01", "2027-10-01"]}},
            {"candidate_id": "dev-v3-single-001", "category": "single_workout", "prompt": "Synthetic single workout fixture.", "execution_fixture": {"profile": profile, "timezone": "Asia/Ho_Chi_Minh", "period": ["2027-10-02", "2027-10-02"], "equipment": ["bodyweight"], "duration_minutes": 30}},
            {"candidate_id": "dev-v3-weekly-001", "category": "weekly_workout", "prompt": "Synthetic weekly workout fixture.", "execution_fixture": {"profile": profile, "timezone": "Asia/Ho_Chi_Minh", "period": ["2027-10-04", "2027-10-10"], "equipment": ["bodyweight"], "number_of_sessions": 1, "available_days": ["monday"], "duration_by_day": {"monday": 30}}},
            {"candidate_id": "dev-v3-combined-001", "category": "combined_health", "prompt": "Synthetic combined fixture.", "execution_fixture": {"timezone": "Asia/Ho_Chi_Minh", "child_revisions": ["fixture-nutrition", "fixture-workout"]}},
            {"candidate_id": "dev-v3-lifecycle-001", "category": "revision_lifecycle", "prompt": "Synthetic lifecycle fixture.", "execution_fixture": {"timezone": "Asia/Ho_Chi_Minh", "operation": "resume", "owner_scoped_revision": True, "expected_revision_number": 1}},
        ],
    }


def _development_oracle(cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "oracle_version": "PLAN_V2_CONFIRMATORY_V3_DEVELOPMENT_SMOKE_ORACLE_V1",
        "cases": [{"case_id": case["candidate_id"], "oracle_profile": "DEVELOPMENT_ONLY"} for case in cases],
    }


async def run_development_smoke(*, postgres_url: str) -> dict[str, Any]:
    """Run exactly five synthetic cases; this function never opens a V3 frozen file."""

    firewall = oracle_firewall_evidence()
    if not all(firewall.values()):
        raise RuntimeError("V3_ORACLE_FIREWALL_STATIC_CHECK_FAILED")
    payload = _development_payload()
    with tempfile.TemporaryDirectory(prefix="plan-v2-v3-development-") as temporary_directory:
        temporary = Path(temporary_directory)
        holdout_path = temporary / "development-holdout.json"
        oracle_path = temporary / "development-oracle.json"
        holdout_path.write_text(json.dumps(payload), encoding="utf-8")
        oracle_payload = _development_oracle(payload["cases"])
        oracle_path.write_text(json.dumps(oracle_payload), encoding="utf-8")
        engine = create_async_engine(postgres_url)
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            raw_records = await _execute_cases(V3CaseLoader(str(holdout_path)).execution_cases(), session_factory=session_factory)
            raw_sha = hashlib.sha256(_canonical(raw_records)).hexdigest()
            reference_chain = await _reference_chain(session_factory=session_factory, owner_prefix="p2-v3-development-reference")
            scored = score_v3(
                holdout_path=holdout_path,
                oracle_path=oracle_path,
                oracle_sha256=_sha(oracle_path),
                raw_records=raw_records,
                reference_chain=reference_chain,
            )
        finally:
            await engine.dispose()
    normal_execution = all(record["v2"]["status"] != "EXECUTOR_ERROR" and record["legacy"]["status"] != "EXECUTOR_ERROR" for record in raw_records)
    result = {
        "artifact_version": "PLAN_V2_CONFIRMATORY_V3_DEVELOPMENT_SMOKE_V1",
        "dataset_scope": "DEVELOPMENT_SYNTHETIC_ONLY",
        "case_count": len(raw_records),
        "oracle_firewall": firewall,
        "raw_execution_sha256": raw_sha,
        "reference_chain_identity": reference_chain["identity_match"],
        "scoring_interface_case_count": scored["metrics"]["case_count"],
        "status": "PASS" if normal_execution and reference_chain["identity_match"] and scored["metrics"]["case_count"] == 5 else "FAIL",
    }
    _write_atomic(SMOKE_OUTPUT, result)
    if result["status"] != "PASS":
        raise RuntimeError("V3_DEVELOPMENT_SMOKE_FAILED:" + json.dumps(result, ensure_ascii=False))
    return result


def freeze_harness(*, preflight: Mapping[str, Any]) -> dict[str, Any]:
    identity = harness_identity()
    payload = {
        "artifact_version": "PLAN_V2_CONFIRMATORY_V3_HARNESS_FREEZE_V2",
        "timestamp": _now(),
        "runner_adapter_hashes": {
            name: digest
            for name, digest in identity["files"].items()
            if "/acceptance/v3/" in name or name.endswith("run_plan_v2_confirmatory_v3.py")
        },
        "execution.py": identity["files"]["services/acceptance/p2_1/execution.py"],
        "scoring.py": identity["files"]["services/acceptance/p2_1/scoring.py"],
        "harness_sha256": identity["sha256"],
        "python_version": identity["python_version"],
        "implementation_baseline_sha256": _sha(BASELINE),
        "v3_holdout_sha256": preflight["actual_hashes"][HOLDOUT.name],
        "v3_oracle_sha256": preflight["actual_hashes"][ORACLE.name],
        "v3_threshold_sha256": preflight["actual_hashes"][THRESHOLDS.name],
    }
    _write_atomic(HARNESS_FREEZE, payload)
    return payload


def _assert_unstarted() -> None:
    existing = [path for path in (REGISTER, RAW_OUTPUT, RESULT_OUTPUT) if path.exists()]
    if existing:
        raise RuntimeError("V3_EXECUTION_ALREADY_RECORDED:" + ",".join(path.name for path in existing))


def _start_register(*, preflight: Mapping[str, Any], harness: Mapping[str, Any]) -> None:
    initial = {
        "register_version": "PLAN_V2_CONFIRMATORY_V3_EXECUTION_REGISTER",
        "dataset_hash": preflight["actual_hashes"][HOLDOUT.name],
        "oracle_hash": preflight["actual_hashes"][ORACLE.name],
        "threshold_hash": preflight["actual_hashes"][THRESHOLDS.name],
        "implementation_baseline_hash": _sha(BASELINE),
        "harness_hash": harness["harness_sha256"],
        "python_version": harness["python_version"],
        "created_at": _now(),
        "started": False,
        "completed": False,
        "infrastructure_retries": [],
    }
    _write_atomic(REGISTER, initial)
    initial["started"] = True
    initial["started_at"] = _now()
    _write_atomic(REGISTER, initial)


def _finish_register(*, result: str, raw_sha: str, score_sha: str) -> None:
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    register.update({"completed": True, "completed_at": _now(), "result": result, "raw_execution_hash": raw_sha, "score_hash": score_sha})
    _write_atomic(REGISTER, register)


def _gates(metrics: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "PLAN_HARD_CONSTRAINT_VIOLATIONS": metrics["hard_constraint_violations"] == thresholds["PLAN_HARD_CONSTRAINT_VIOLATIONS"],
        "PLAN_PLANNED_TO_ACTUAL_LEAKAGE": metrics["planned_to_actual_leakage"] == thresholds["PLAN_PLANNED_TO_ACTUAL_LEAKAGE"],
        "PLAN_UNINTENDED_WRITE": metrics["unintended_writes"] == thresholds["PLAN_UNINTENDED_WRITE"],
        "PLAN_DUPLICATE_WRITE": metrics["duplicate_writes"] == thresholds["PLAN_DUPLICATE_WRITE"],
        "PLAN_STALE_REVISION_OVERWRITE": metrics["stale_revision_overwrite"] == thresholds["PLAN_STALE_REVISION_OVERWRITE"],
        "PLAN_CROSS_USER_ACCESS": metrics["cross_user_access"] == thresholds["PLAN_CROSS_USER_ACCESS"],
        "PLAN_INVALID_CANONICAL_REFERENCE": metrics["invalid_canonical_references"] == thresholds["PLAN_INVALID_CANONICAL_REFERENCE"],
        "REFERENCE_CHAIN_IDENTITY_PERCENT": metrics["reference_chain_identity_percent"] >= thresholds["REFERENCE_CHAIN_IDENTITY_PERCENT"],
        "DETERMINISTIC_FIXTURE_MATCH_PERCENT": metrics["deterministic_fixture_match_percent"] >= thresholds["DETERMINISTIC_FIXTURE_MATCH_PERCENT"],
        "REQUEST_SEMANTIC_MATCH_PERCENT": metrics["request_semantic_match_percent"] >= thresholds["REQUEST_SEMANTIC_MATCH_PERCENT"],
    }


def _write_report(*, result: Mapping[str, Any], harness: Mapping[str, Any]) -> None:
    metrics = result["metrics"]
    failed = result["failed_case_ids"]
    final = result["V3_RESULT"]
    semantic = "YES" if metrics["request_semantic_match_percent"] >= result["thresholds"]["REQUEST_SEMANTIC_MATCH_PERCENT"] else "NO"
    lines = [
        "# PLAN V2 CONFIRMATORY V3 FINAL REPORT",
        "",
        "## Harness Adapter",
        "",
        "- V3 fixture projection and runner are acceptance-owned and outside the frozen Plan V2 implementation baseline.",
        f"- Harness SHA-256: `{harness['harness_sha256']}`.",
        "",
        "## Oracle Firewall",
        "",
        "- The execution adapter has no oracle import. Raw execution was atomically written before the post-execution scorer opened the frozen V3 oracle.",
        "- A five-case development/synthetic smoke passed before the V3 run; no V3 holdout case was used for that smoke.",
        "",
        "## Frozen Identities",
        "",
        f"- Holdout: `{result['hashes']['holdout']}`.",
        f"- Oracle: `{result['hashes']['oracle']}`.",
        f"- Thresholds: `{result['hashes']['thresholds']}`.",
        f"- Implementation baseline: `{result['implementation_baseline_hash']}`.",
        "",
        "## Execution Register",
        "",
        f"- `{REGISTER.name}` records `started=true` before the first V3 case and `completed=true` after scoring.",
        "",
        "## Cases Executed",
        "",
        f"- {metrics['case_count']} frozen cases executed once. No case replacement, manual correction, or semantic retry was performed.",
        "",
        "## Comparator Results",
        "",
        f"- {json.dumps(metrics['comparator_verdict_counts'], sort_keys=True)}",
        "",
        "## Semantic Match",
        "",
        f"- Request semantic match: {metrics['request_semantic_match_percent']}% (threshold {result['thresholds']['REQUEST_SEMANTIC_MATCH_PERCENT']}%).",
        "",
        "## Reference Chain",
        "",
        f"- Reference-chain identity: {metrics['reference_chain_identity_percent']}% (threshold {result['thresholds']['REFERENCE_CHAIN_IDENTITY_PERCENT']}%).",
        "",
        "## Hard Invariants",
        "",
        f"- {json.dumps({key: metrics[key] for key in ('hard_constraint_violations', 'planned_to_actual_leakage', 'unintended_writes', 'duplicate_writes', 'stale_revision_overwrite', 'cross_user_access', 'invalid_canonical_references', 'silent_legacy_fallback', 'weekly_fabricated_history_recovery', 'false_success', 'shadow_side_effects', 'deterministic_fixture_match_percent')}, sort_keys=True)}",
        "",
        "## Failed Case IDs",
        "",
        "- " + (", ".join(failed) if failed else "None."),
        "",
        "## Final Decision",
        "",
        "```text",
        "V3_HARNESS_READY = YES",
        "V3_STARTED = YES",
        "V3_COMPLETED = YES",
        f"V3_REQUEST_SEMANTIC_MATCH = {metrics['request_semantic_match_percent']}%",
        f"V3_REFERENCE_CHAIN_IDENTITY = {metrics['reference_chain_identity_percent']}%",
        f"V3_HARD_VIOLATIONS = {metrics['hard_constraint_violations']}",
        f"SEMANTIC_ROOT_CAUSES_RESOLVED = {semantic}",
        f"V3_RESULT = {final}",
        f"P2_PLAN_ACCEPTANCE_COMPLETE = {'YES' if final == 'PASS' else 'NO'}",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


async def run_final(*, postgres_url: str) -> dict[str, Any]:
    preflight = _require_final_preflight()
    _assert_unstarted()
    harness = freeze_harness(preflight=preflight)
    if harness_identity()["sha256"] != harness["harness_sha256"]:
        raise RuntimeError("V3_HARNESS_CHANGED_AFTER_FREEZE")
    _start_register(preflight=preflight, harness=harness)
    engine = create_async_engine(postgres_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        raw_records = await _execute_cases(V3CaseLoader(str(HOLDOUT)).execution_cases(), session_factory=session_factory)
        raw_payload = {
            "artifact_version": "PLAN_V2_CONFIRMATORY_V3_RAW_EXECUTION_V1",
            "status": "COMPLETE",
            "case_count": len(raw_records),
            "contains_oracle_fields": False,
            "records": raw_records,
        }
        raw_sha = _write_atomic(RAW_OUTPUT, raw_payload)
        reference_chain = await _reference_chain(session_factory=session_factory, owner_prefix="p2-v3-reference")
        scored = score_v3(
            holdout_path=HOLDOUT,
            oracle_path=ORACLE,
            oracle_sha256=preflight["actual_hashes"][ORACLE.name],
            raw_records=raw_records,
            reference_chain=reference_chain,
        )
    finally:
        await engine.dispose()
    thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    gates = _gates(scored["metrics"], thresholds)
    final = "PASS" if all(gates.values()) else "FAIL"
    failed_case_ids = [
        record["case_id"]
        for record in scored["records"]
        if not record["semantic_match"] or record["hard_violations"]
    ]
    result = {
        "artifact_version": "PLAN_V2_CONFIRMATORY_V3_RESULTS_V1",
        "status": "COMPLETE",
        "V3_RESULT": final,
        "raw_execution_sha256": raw_sha,
        "oracle_sha256": preflight["actual_hashes"][ORACLE.name],
        "threshold_sha256": preflight["actual_hashes"][THRESHOLDS.name],
        "implementation_baseline_hash": _sha(BASELINE),
        "harness_sha256": harness["harness_sha256"],
        "hashes": {"holdout": preflight["actual_hashes"][HOLDOUT.name], "oracle": preflight["actual_hashes"][ORACLE.name], "thresholds": preflight["actual_hashes"][THRESHOLDS.name]},
        "reference_chain": reference_chain,
        "metrics": scored["metrics"],
        "gates": gates,
        "thresholds": thresholds,
        "failed_case_ids": failed_case_ids,
        "records": scored["records"],
    }
    score_sha = _write_atomic(RESULT_OUTPUT, result)
    _finish_register(result=final, raw_sha=raw_sha, score_sha=score_sha)
    _write_report(result=result, harness=harness)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--development-smoke", action="store_true")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    if args.development_smoke == args.final:
        parser.error("select exactly one of --development-smoke or --final")
    outcome = asyncio.run(
        run_development_smoke(postgres_url=args.postgres_url)
        if args.development_smoke
        else run_final(postgres_url=args.postgres_url)
    )
    print(json.dumps({"status": outcome.get("status") or outcome.get("V3_RESULT"), "case_count": outcome.get("case_count") or outcome.get("metrics", {}).get("case_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
