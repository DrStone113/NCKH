"""First-pass runner: preflight, execute all cases once, then score."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .execution import (
    AcceptanceCaseLoader,
    ExecutionResult,
    LegacyPlanReadOnlyExecutor,
    PlanV2Executor,
    context_for_case,
)
from .scoring import AcceptanceScorer


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
REGISTER = VALIDATION / "p2-1-first-scored-acceptance-register-v1.json"
HOLDOUT = VALIDATION / "p2-1a-automated-holdout-v1.json"
ORACLE = VALIDATION / "p2-1a-deterministic-oracle-v1.json"
THRESHOLDS = VALIDATION / "acceptance-thresholds-v1.json"
FREEZE = VALIDATION / "implementation-freeze-p2-1r-v1.json"
RAW_OUTPUT = VALIDATION / "p2-1-first-scored-raw-execution-v1.json"
SCORE_OUTPUT = VALIDATION / "p2-1-first-scored-results-v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _write_atomic(path: Path, value: Any) -> str:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return _sha(path)


def harness_sha256() -> str:
    files = (Path(__file__), Path(__file__).with_name("execution.py"), Path(__file__).with_name("scoring.py"))
    return hashlib.sha256(b"".join(path.read_bytes() for path in files)).hexdigest()


def _working_tree_fingerprint() -> dict[str, str]:
    # Git diffs can contain UTF-8 Vietnamese source while the Windows process
    # default is cp1252. Hash raw bytes; a fingerprint needs no decoding.
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=ROOT.parent.parent, capture_output=True, text=False, check=True)
    diff = subprocess.run(["git", "diff", "--binary"], cwd=ROOT.parent.parent, capture_output=True, text=False, check=True)
    return {
        "status_sha256": hashlib.sha256(status.stdout).hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(diff.stdout).hexdigest(),
    }


def _migration_checksums() -> dict[str, str]:
    migrations = sorted((ROOT / "db" / "migrations").glob("*.sql"))
    return {path.name: _sha(path) for path in migrations}


def frozen_hashes() -> dict[str, Any]:
    manifest = json.loads(FREEZE.read_text(encoding="utf-8"))
    implementation = {
        path: {"expected": expected, "actual": _sha(ROOT / path), "matches": _sha(ROOT / path) == expected}
        for path, expected in manifest["sources"].items()
    }
    automated = json.loads((VALIDATION / "p2-1a-automated-freeze-manifest-v1.json").read_text(encoding="utf-8"))
    artifacts = {
        name: {"expected": item["sha256"], "actual": _sha(VALIDATION / item["path"]), "matches": _sha(VALIDATION / item["path"]) == item["sha256"]}
        for name, item in automated["artifacts"].items()
    }
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    register_artifacts = register["frozen_artifacts"]
    exclusion = register_artifacts["exclusion_index"]
    dedup = register_artifacts["dedup_protocol"]
    supplemental = {
        "exclusion_index": {
            "expected": exclusion["file_sha256"],
            "actual": _sha(VALIDATION / exclusion["path"]),
            "matches": _sha(VALIDATION / exclusion["path"]) == exclusion["file_sha256"],
        },
        "dedup_protocol": {
            "expected": dedup["file_sha256"],
            "actual": _sha(VALIDATION / dedup["path"]),
            "matches": _sha(VALIDATION / dedup["path"]) == dedup["file_sha256"],
        },
    }
    return {"implementation": implementation, "artifacts": artifacts, "supplemental": supplemental}


def _toolchain(flutter: Path) -> dict[str, Any]:
    flutter_result = subprocess.run([str(flutter), "--version"], capture_output=True, text=True, timeout=120)
    dart = flutter.with_name("dart.bat")
    dart_result = subprocess.run([str(dart), "--version"], capture_output=True, text=True, timeout=120)
    flutter_text = flutter_result.stdout + flutter_result.stderr
    dart_text = dart_result.stdout + dart_result.stderr
    flutter_match = re.search(r"Flutter\s+(\d+\.\d+\.\d+)", flutter_text)
    dart_match = re.search(r"Dart SDK version:\s*(\d+\.\d+\.\d+)", dart_text)
    return {
        "flutter_exit_code": flutter_result.returncode,
        "dart_exit_code": dart_result.returncode,
        "flutter_version": flutter_match.group(1) if flutter_match else None,
        "dart_version": dart_match.group(1) if dart_match else None,
        "cpython_version": ".".join(map(str, sys.version_info[:3])),
        "usable": bool(flutter_result.returncode == 0 and dart_result.returncode == 0 and flutter_match and dart_match),
    }


async def _postgres_version(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return str((await connection.execute(text("SHOW server_version"))).scalar_one())
    finally:
        await engine.dispose()


async def final_preflight(*, flutter: Path, postgres_url: str) -> dict[str, Any]:
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    hashes = frozen_hashes()
    toolchain = _toolchain(flutter)
    postgres = await _postgres_version(postgres_url)
    result = {
        "first_pass_not_started": register.get("first_pass_started") is False,
        "frozen_plan_implementation_match": all(item["matches"] for item in hashes["implementation"].values()),
        "holdout_hash_match": hashes["artifacts"]["holdout"]["matches"],
        "oracle_hash_match": hashes["artifacts"]["oracle"]["matches"],
        "comparator_hash_match": hashes["implementation"]["services/plan_engine/comparator.py"]["matches"],
        "threshold_hash_match": hashes["artifacts"]["thresholds"]["matches"],
        "exclusion_index_hash_match": hashes["supplemental"]["exclusion_index"]["matches"],
        "dedup_protocol_hash_match": hashes["supplemental"]["dedup_protocol"]["matches"],
        "toolchain_match": toolchain["usable"] and toolchain["flutter_version"] == "3.44.8" and toolchain["dart_version"] == "3.12.2" and toolchain["cpython_version"] == "3.10.21",
        "postgres16": postgres.startswith("16."),
        "hashes": hashes,
        "toolchain": toolchain,
        "postgres_version": postgres,
    }
    result["ok"] = all(value for key, value in result.items() if key in {
        "first_pass_not_started", "frozen_plan_implementation_match", "holdout_hash_match", "oracle_hash_match",
        "comparator_hash_match", "threshold_hash_match", "exclusion_index_hash_match", "dedup_protocol_hash_match",
        "toolchain_match", "postgres16",
    })
    return result


def _start_register(*, preflight: Mapping[str, Any], postgres_url: str) -> None:
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    if register.get("first_pass_started"):
        raise RuntimeError("FIRST_PASS_ALREADY_STARTED")
    register.update({
        "register_status": "FIRST_PASS_RUNNING",
        "first_pass_started": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "final_preflight": preflight,
        "harness": {"version": "P2_1A_EXECUTION_HARNESS_V1", "sha256": harness_sha256()},
        "postgresql": {"url_redacted": re.sub(r"://[^@]+@", "://***@", postgres_url), "version": preflight["postgres_version"]},
        "migration_checksums": _migration_checksums(),
        "working_tree_fingerprint": _working_tree_fingerprint(),
        "scoring_blockers": [],
    })
    _write_atomic(REGISTER, register)


def _finish_register(*, result: str, raw_sha256: str, score_sha256: str) -> None:
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    if register.get("first_pass_started") is not True:
        raise RuntimeError("FIRST_PASS_NOT_STARTED")
    register.update({
        "register_status": "FIRST_PASS_COMPLETE",
        "first_pass_completed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "first_pass_result": result,
        "raw_execution_sha256": raw_sha256,
        "score_result_sha256": score_sha256,
    })
    _write_atomic(REGISTER, register)


async def execute_first_pass(*, flutter: Path, postgres_url: str) -> dict[str, Any]:
    """Run the frozen holdout exactly once. Call only after dev harness tests."""

    preflight = await final_preflight(flutter=flutter, postgres_url=postgres_url)
    if not preflight["ok"]:
        raise RuntimeError("FINAL_PREFLIGHT_FAILED:" + json.dumps(preflight, ensure_ascii=False, default=str))
    _start_register(preflight=preflight, postgres_url=postgres_url)

    # From the register update onward this function changes no code or frozen
    # artifact. It only emits immutable first-pass observations/results.
    engine = create_async_engine(postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    legacy = LegacyPlanReadOnlyExecutor(session_factory)
    v2 = PlanV2Executor()
    try:
        cases = AcceptanceCaseLoader(str(HOLDOUT)).execution_cases()
        if len(cases) != 120 or len({case.case_id for case in cases}) != 120:
            raise RuntimeError("FROZEN_HOLDOUT_CASE_COUNT_OR_IDENTITY_INVALID")
        raw_records: list[dict[str, Any]] = []
        for sequence, case in enumerate(cases, start=1):
            context = context_for_case(case)
            legacy_result = await legacy.execute(case, context)
            v2_result = await v2.execute(case, context)
            raw = {
                "sequence": sequence,
                "case_id": case.case_id,
                "category": case.category,
                "prompt": case.prompt,
                "execution_context": {
                    "owner_user_id": context.owner_user_id,
                    "period_start": context.period_start,
                    "period_end": context.period_end,
                    "timezone": context.timezone,
                    "clock_date": context.clock_date,
                },
                "legacy": legacy_result.to_dict(),
                "v2": v2_result.to_dict(),
            }
            raw["raw_execution_sha256"] = hashlib.sha256(_canonical(raw)).hexdigest()
            raw_records.append(raw)
        raw_payload = {
            "artifact_version": "PLAN_V2_P2_1_FIRST_SCORED_RAW_EXECUTION_V1",
            "status": "COMPLETE",
            "case_count": len(raw_records),
            "contains_oracle_fields": False,
            "records": raw_records,
        }
        raw_sha = _write_atomic(RAW_OUTPUT, raw_payload)

        oracle_sha = _sha(ORACLE)
        scores = AcceptanceScorer(holdout_path=HOLDOUT, oracle_path=ORACLE, oracle_sha256=oracle_sha).score(raw_records)
        threshold = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        hard = [code for score in scores for code in score.hard_violations]
        comparable = [score for score in scores if score.comparator["verdict"] != "NOT_COMPARABLE"]
        semantic_percent = round(100 * sum(score.semantic_match for score in comparable) / len(comparable), 2) if comparable else None
        deterministic_total = sum(len(score.objective_checks) for score in scores)
        deterministic_pass = sum(value for score in scores for value in score.objective_checks.values())
        metrics = {
            "case_count": len(scores),
            "comparable_case_count": len(comparable),
            "request_semantic_match_percent": semantic_percent,
            "hard_constraint_violations": len(hard),
            "planned_to_actual_leakage": sum(code == "PLANNED_TO_ACTUAL_LEAKAGE" for code in hard),
            "unintended_writes": sum(bool(ExecutionResult(**{key: value for key, value in raw["v2"].items() if key != "result_sha256"}).captured_write_attempts) for raw in raw_records),
            "invalid_canonical_references": sum("CANONICAL" in code for code in hard),
            "cross_user_access": sum("CROSS_USER" in code or "OWNER" in code for code in hard),
            "policy_hard_rule_failures": sum("POLICY" in code for code in hard),
            "deterministic_fixture_match_percent": round(100 * deterministic_pass / deterministic_total, 2) if deterministic_total else 0.0,
            "reference_chain_identity_percent": round(100 * sum(score.v2_status == "READY" for score in scores) / len(scores), 2),
            "verdict_counts": {name: sum(score.comparator["verdict"] == name for score in scores) for name in ("V2_BETTER", "V2_EQUIVALENT", "V2_ACCEPTABLE_DIFFERENCE", "V2_REGRESSION", "NOT_COMPARABLE")},
        }
        gates = {
            "hard_constraint_violations": metrics["hard_constraint_violations"] == threshold["hard_gates"]["v2_hard_constraint_violations"],
            "planned_to_actual_leakage": metrics["planned_to_actual_leakage"] == threshold["hard_gates"]["planned_to_actual_leakage"],
            "unintended_writes": metrics["unintended_writes"] == threshold["hard_gates"]["unintended_writes"],
            "invalid_canonical_references": metrics["invalid_canonical_references"] == threshold["hard_gates"]["invalid_canonical_references"],
            "cross_user_access": metrics["cross_user_access"] == threshold["hard_gates"]["cross_user_access"],
            "policy_hard_rule_failures": metrics["policy_hard_rule_failures"] == threshold["hard_gates"]["policy_hard_rule_failures"],
            "request_semantic_match": semantic_percent is not None and semantic_percent / 100 >= threshold["minimum_rates"]["objectively_comparable_request_semantic_match"],
            "reference_chain_and_deterministic_match": metrics["reference_chain_identity_percent"] / 100 >= threshold["minimum_rates"]["reference_chain_and_deterministic_match"] and metrics["deterministic_fixture_match_percent"] == 100.0,
        }
        result = "PASS" if all(gates.values()) else "FAIL"
        score_payload = {
            "artifact_version": "PLAN_V2_P2_1_FIRST_SCORED_RESULTS_V1",
            "status": "COMPLETE",
            "raw_execution_sha256": raw_sha,
            "oracle_sha256": oracle_sha,
            "threshold_sha256": _sha(THRESHOLDS),
            "metrics": metrics,
            "gates": gates,
            "first_pass_result": result,
            "records": [score.to_dict() for score in scores],
        }
        score_sha = _write_atomic(SCORE_OUTPUT, score_payload)
        _finish_register(result=result, raw_sha256=raw_sha, score_sha256=score_sha)
        return score_payload
    finally:
        await engine.dispose()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter", required=True, type=Path)
    parser.add_argument("--postgres-url", required=True)
    args = parser.parse_args()
    payload = asyncio.run(execute_first_pass(flutter=args.flutter, postgres_url=args.postgres_url))
    print(json.dumps({"FIRST_PASS_RESULT": payload["first_pass_result"], "case_count": payload["metrics"]["case_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
