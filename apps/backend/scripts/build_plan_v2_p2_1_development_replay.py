"""Record P2.1 failure-pattern replay without relabelling it as acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
OUTPUT = VALIDATION / "p2-2-p2-1-development-replay-v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    raw = VALIDATION / "p2-1-first-scored-raw-execution-v1.json"
    results = VALIDATION / "p2-1-first-scored-results-v1.json"
    taxonomy = VALIDATION / "p2-2-failure-taxonomy-v1.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    failures = json.loads(taxonomy.read_text(encoding="utf-8"))
    return {
        "artifact_version": "PLAN_V2_P2_2_P2_1_DEVELOPMENT_REPLAY_V1",
        "dataset_status": "USED_FOR_TUNING_AFTER_FIRST_PASS",
        "not_acceptance": True,
        "not_unseen": True,
        "not_a_second_first_pass": True,
        "historical_scored_result": {
            "request_semantic_match_percent": data["metrics"]["request_semantic_match_percent"],
            "reference_chain_identity_percent": data["metrics"]["reference_chain_identity_percent"],
            "first_pass_result": "FAIL",
        },
        "replay_scope": {
            "exact_120_case_rescore": "NOT_PERFORMED",
            "reason": "The old execution schema omitted profile and lifecycle fixture references. Re-scoring known data through a changed fixture adapter would not measure product improvement.",
            "generalized_failure_regressions": [
                "test_plan_lifecycle_p2_2.py",
                "test_plan_reference_chain_live.py",
                "test_plan_sql_repository_live.py",
                "test_plan_v2_api_live.py",
                "test_plan_v2_p2_1_execution_harness.py",
            ],
            "failure_patterns_covered": failures["primary_category_counts"],
        },
        "source_hashes": {
            "raw_execution": _sha(raw),
            "historical_results": _sha(results),
            "taxonomy": _sha(taxonomy),
        },
    }


def main() -> int:
    payload = build()
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "status": payload["dataset_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
