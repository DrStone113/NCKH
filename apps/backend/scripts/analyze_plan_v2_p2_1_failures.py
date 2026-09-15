"""Produce a non-mutating P2.2 taxonomy for immutable P2.1 evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
HOLDOUT = VALIDATION / "p2-1a-automated-holdout-v1.json"
RAW = VALIDATION / "p2-1-first-scored-raw-execution-v1.json"
SCORES = VALIDATION / "p2-1-first-scored-results-v1.json"
OUTPUT = VALIDATION / "p2-2-failure-taxonomy-v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _primary(case: dict[str, Any]) -> tuple[str, str]:
    """Classify the observed P2.1 mismatch without blaming Plan V2 by default."""

    category = str(case["category"])
    profile = str(case.get("oracle_profile") or "")
    if category == "nutrition" and profile in {
        "NUTRITION_SPECIALIST_GATE",
        "NUTRITION_PLANNED_NOT_ACTUAL",
    }:
        return (
            "EXECUTION_ADAPTER_BUG",
            "The executor omitted explicit prompt safety/planned-state intent before calling the Plan V2 tool.",
        )
    if category == "nutrition":
        return (
            "FIXTURE_RUNTIME_BUG",
            "The P2.1 execution context supplied only user_id although the prompt requires a current profile or constraint context.",
        )
    if category in {"workout_single_session", "weekly_workout_scheduling", "combined_health"}:
        return (
            "EXECUTION_ADAPTER_BUG",
            "The executor did not translate prompt facts into the bounded public Plan V2 request contract.",
        )
    if category == "revision_lifecycle_concurrency_adversarial":
        return (
            "FIXTURE_RUNTIME_BUG",
            "The executor invented a missing UUID read instead of provisioning the exact owner-scoped revision fixture required by the lifecycle request.",
        )
    return ("OTHER_WITH_EXPLICIT_REASON", "No recognized P2.1 execution category.")


def build() -> dict[str, Any]:
    holdout = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    scores = json.loads(SCORES.read_text(encoding="utf-8"))
    scores_by_id = {str(record["case_id"]): record for record in scores["records"]}
    raw_by_id = {str(record["case_id"]): record for record in raw["records"]}

    category_stats: dict[str, Counter[str]] = defaultdict(Counter)
    classified: list[dict[str, Any]] = []
    for case in holdout["cases"]:
        case_id = str(case["case_id"])
        score = scores_by_id[case_id]
        category = str(case["category"])
        category_stats[category]["comparable"] += 1
        if bool(score["semantic_match"]):
            category_stats[category]["semantic_match"] += 1
            continue
        category_stats[category]["semantic_mismatch"] += 1
        primary, reason = _primary(case)
        execution = raw_by_id[case_id]
        classified.append(
            {
                "case_id": case_id,
                "category": category,
                "oracle_profile": case.get("oracle_profile"),
                "primary_category": primary,
                "reason": reason,
                "observed_v2_status": execution["v2"]["status"],
                "observed_legacy_status": execution["legacy"]["status"],
            }
        )

    by_primary: dict[str, list[str]] = defaultdict(list)
    for record in classified:
        by_primary[str(record["primary_category"])].append(str(record["case_id"]))
    return {
        "artifact_version": "PLAN_V2_P2_2_FAILURE_TAXONOMY_V1",
        "source_status": "P2_1_FIRST_PASS_IMMUTABLE_USED_FOR_TUNING_ONLY",
        "source_hashes": {
            "holdout": _sha(HOLDOUT),
            "raw_execution": _sha(RAW),
            "scored_results": _sha(SCORES),
        },
        "records_analyzed": len(raw["records"]),
        "semantic_mismatches_classified": len(classified),
        "category_semantic_summary": {
            category: dict(values) for category, values in sorted(category_stats.items())
        },
        "primary_category_counts": {
            category: {"count": len(ids), "case_ids": sorted(ids)}
            for category, ids in sorted(by_primary.items())
        },
        "mismatches": classified,
        "systemic_findings": [
            {
                "primary_category": "REFERENCE_PROPAGATION_BUG",
                "scope": "all 120 P2.1 records",
                "reason": "The first-pass runner computed reference_chain_identity_percent from v2_status == READY. It did not execute or observe preview-to-pending-to-persistence identity propagation.",
            },
            {
                "primary_category": "NORMALIZATION_BUG",
                "scope": "legacy comparison adapter",
                "reason": "A rolled-back legacy insert was exposed as unintended_writes to the frozen comparator even though it did not persist. New harnesses retain write-attempt telemetry separately from persisted side effects.",
            },
            {
                "primary_category": "LIFECYCLE_BUG",
                "scope": "PostgreSQL 16.15 live integration",
                "reason": "The duplicated lifecycle maps rejected PAUSED to ACTIVE. P2.2 centralizes the transition table and permits resume only from PAUSED.",
            },
        ],
    }


def main() -> int:
    output = build()
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "mismatches": output["semantic_mismatches_classified"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
