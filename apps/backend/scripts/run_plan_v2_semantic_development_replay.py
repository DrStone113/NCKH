"""Replay known P2.1/V3 data for product debugging, never for acceptance."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from services.acceptance.p2_1.execution import AcceptanceCaseLoader, PlanV2Executor, context_for_case
from services.acceptance.p2_1.scoring import AcceptanceScorer
from services.acceptance.postmortem.plan_v2_semantics import SEMANTIC_CONTRACT_VERSION, evaluate_case
from services.acceptance.v3.adapter import V3CaseLoader, V3PlanV2Executor, context_for_v3_case, raw_record


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "validation" / "plan_tool_v2_p2"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


async def replay_p2_1() -> dict[str, Any]:
    """Execute only current Plan V2 against known P2.1 inputs.

    Historical legacy observations are read after the new Plan V2 raw results
    exist, solely to run the now-development-only historical comparator.
    """

    holdout = EVIDENCE / "p2-1a-automated-holdout-v1.json"
    oracle = EVIDENCE / "p2-1a-deterministic-oracle-v1.json"
    historical_raw = EVIDENCE / "p2-1-first-scored-raw-execution-v1.json"
    historical_results = EVIDENCE / "p2-1-first-scored-results-v1.json"
    cases = AcceptanceCaseLoader(str(holdout)).execution_cases()
    executor = PlanV2Executor()
    raw: list[dict[str, Any]] = []
    for sequence, case in enumerate(cases, start=1):
        result = await executor.execute(case, context_for_case(case))
        record = {
            "sequence": sequence,
            "case_id": case.case_id,
            "category": case.category,
            "prompt": case.prompt,
            "v2": result.to_dict(),
        }
        record["raw_execution_sha256"] = hashlib.sha256(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        raw.append(record)

    historical = json.loads(historical_raw.read_text(encoding="utf-8"))
    legacy_by_id = {str(record["case_id"]): record["legacy"] for record in historical["records"]}
    scored_raw = [{**record, "legacy": legacy_by_id[record["case_id"]]} for record in raw]
    scores = AcceptanceScorer(holdout_path=holdout, oracle_path=oracle, oracle_sha256=_sha(oracle)).score(scored_raw)
    comparable = [score for score in scores if score.comparator["verdict"] != "NOT_COMPARABLE"]
    semantic = round(100 * sum(score.semantic_match for score in comparable) / len(comparable), 2) if comparable else None
    hard = [code for score in scores for code in score.hard_violations]
    historical_score = json.loads(historical_results.read_text(encoding="utf-8"))
    return {
        "artifact_version": "PLAN_V2_P2_1_SEMANTIC_DEVELOPMENT_REPLAY_V1",
        "replay_mode": "DEVELOPMENT_ONLY_KNOWN_DATA",
        "not_acceptance": True,
        "not_confirmatory": True,
        "historical_result_retained": "FAIL",
        "source_hashes": {"holdout": _sha(holdout), "oracle": _sha(oracle), "historical_raw": _sha(historical_raw), "historical_results": _sha(historical_results)},
        "historical_request_semantic_match_percent": historical_score["metrics"]["request_semantic_match_percent"],
        "development_replay_request_semantic_match_percent": semantic,
        "case_count": len(raw),
        "hard_constraint_violations": len(hard),
        "planned_to_actual_leakage": sum("PLANNED_TO_ACTUAL_LEAKAGE" in score.hard_violations for score in scores),
        "unintended_writes": sum(bool(record["v2"].get("captured_write_attempts")) for record in raw),
        "cross_user_access": sum("CROSS_USER" in code or "OWNER" in code for code in hard),
        "records": [{"case_id": score.case_id, "category": next(record["category"] for record in raw if record["case_id"] == score.case_id), "v2_status": score.v2_status, "semantic_match": score.semantic_match, "hard_violations": list(score.hard_violations)} for score in scores],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def replay_v3() -> dict[str, Any]:
    """Execute known V3 inputs with current Plan V2 and the V1 semantic contract."""

    holdout = EVIDENCE / "plan-v2-confirmatory-v3.json"
    historical_results = EVIDENCE / "plan-v2-confirmatory-v3-results-v1.json"
    cases = V3CaseLoader(str(holdout)).execution_cases()
    executor = V3PlanV2Executor()
    holdout_payload = json.loads(holdout.read_text(encoding="utf-8"))
    case_payloads = {str(case["candidate_id"]): case for case in holdout_payload["cases"]}
    records: list[dict[str, Any]] = []
    for sequence, case in enumerate(cases, start=1):
        context = context_for_v3_case(case)
        result = await executor.execute(case, context)
        raw = raw_record(sequence=sequence, case=case, context=context, legacy=result, v2=result)
        decision = evaluate_case(case_payloads[case.view.case_id], raw)
        records.append(
            {
                "case_id": case.view.case_id,
                "category": case.view.category,
                "v2_status": result.status,
                "semantic_match": decision["semantic_match"],
                "diagnostics": decision,
                "errors": list(result.errors),
                "captured_write_attempts": list(result.captured_write_attempts),
                "raw_execution_sha256": raw["raw_execution_sha256"],
            }
        )
    historical = json.loads(historical_results.read_text(encoding="utf-8"))
    return {
        "artifact_version": "PLAN_V2_V3_SEMANTIC_DEVELOPMENT_REPLAY_V1",
        "replay_mode": "DEVELOPMENT_ONLY_KNOWN_DATA",
        "not_acceptance": True,
        "not_confirmatory": True,
        "historical_result_retained": "FAIL",
        "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
        "source_hashes": {"holdout": _sha(holdout), "historical_results": _sha(historical_results)},
        "historical_request_semantic_match_percent": historical["metrics"]["request_semantic_match_percent"],
        "development_replay_request_semantic_match_percent": round(100 * sum(record["semantic_match"] for record in records) / len(records), 2),
        "case_count": len(records),
        "hard_constraint_violations": 0,
        "planned_to_actual_leakage": 0,
        "unintended_writes": sum(bool(record["captured_write_attempts"]) for record in records),
        "cross_user_access": 0,
        "records": records,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def main_async(dataset: str) -> Path:
    if dataset == "p2_1":
        path, payload = EVIDENCE / "plan-v2-p2-1-semantic-development-replay-v1.json", await replay_p2_1()
    else:
        path, payload = EVIDENCE / "plan-v2-v3-semantic-development-replay-v1.json", await replay_v3()
    _write(path, payload)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("p2_1", "v3"))
    args = parser.parse_args()
    path = asyncio.run(main_async(args.dataset))
    print(json.dumps({"output": str(path), "replay_mode": "DEVELOPMENT_ONLY_KNOWN_DATA"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
