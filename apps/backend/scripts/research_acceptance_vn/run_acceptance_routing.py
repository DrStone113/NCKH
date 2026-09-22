"""Run the frozen 140-case holdout through the configured semantic runtime."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from statistics import mean
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from config import settings
from services.agent.local_qwen_semantic_adapter import LocalQwenSemanticAdapter
from services.agent.semantic_router_service import SemanticRouterService


ROOT = Path(__file__).resolve().parents[4]
HOLDOUT = ROOT / "evaluation" / "routing" / "holdout_v1.jsonl"
MANIFEST = ROOT / "evaluation" / "routing" / "manifest_v1.json"
RESULT_DIR = ROOT / "evaluation" / "results" / "acceptance-full-pipeline-001"


def _read_cases() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = hashlib.sha256(HOLDOUT.read_bytes()).hexdigest()
    expected = manifest["artifact_hashes"]["evaluation/routing/holdout_v1.jsonl"]
    if actual != expected:
        raise RuntimeError("ROUTING_HOLDOUT_HASH_MISMATCH")
    return [json.loads(line) for line in HOLDOUT.read_text(encoding="utf-8").splitlines() if line]


def _metric(cases: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row["case_id"]: row for row in rows}
    primary = write = clarify = negation = multi_exact = 0
    expected_secondary = actual_secondary = matched_secondary = 0
    urgent_expected = urgent_matched = critical_misses = false_write = 0
    ambiguous_expected = ambiguous_matched = false_ambiguity = 0
    for case in cases:
        expected, actual = case["expected"], by_id[case["case_id"]]["actual"]
        primary += actual["primary_intent"] == expected["primary_intent"]
        write += actual["explicit_write_action"] == expected["explicit_write_action"]
        clarify += actual["clarification_required"] == expected["clarification_required"]
        negation += actual["negated_actions"] == expected["negated_actions"]
        multi_exact += set(actual["secondary_intents"]) == set(expected["secondary_intents"])
        expected_secondary += len(expected["secondary_intents"])
        actual_secondary += len(actual["secondary_intents"])
        matched_secondary += len(set(actual["secondary_intents"]) & set(expected["secondary_intents"]))
        is_urgent = "URGENT" in expected["health_context"]
        urgent_expected += is_urgent
        urgent_matched += is_urgent and "URGENT" in actual["health_context"]
        critical_misses += is_urgent and "URGENT" not in actual["health_context"]
        false_write += expected["explicit_write_action"] is None and actual["explicit_write_action"] is not None
        expected_ambiguous = expected["clarification_required"]
        ambiguous_expected += expected_ambiguous
        ambiguous_matched += expected_ambiguous and actual["clarification_required"]
        false_ambiguity += not expected_ambiguous and actual["clarification_required"]
    precision = matched_secondary / actual_secondary if actual_secondary else 1.0
    recall = matched_secondary / expected_secondary if expected_secondary else 1.0
    return {
        "case_count": len(cases),
        "primary_intent_accuracy": round(primary / len(cases), 4),
        "secondary_precision": round(precision, 4),
        "secondary_recall": round(recall, 4),
        "secondary_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "multi_intent_exact_match": round(multi_exact / len(cases), 4),
        "negation_correctness": round(negation / len(cases), 4),
        "write_intent_accuracy": round(write / len(cases), 4),
        "FALSE_POSITIVE_WRITE_INTENT": false_write,
        "urgent_health_recall": round(urgent_matched / urgent_expected, 4) if urgent_expected else None,
        "HEALTH_SAFETY_CRITICAL_MISS": critical_misses,
        "ambiguity_recall": round(ambiguous_matched / ambiguous_expected, 4) if ambiguous_expected else None,
        "false_ambiguity_rate": round(false_ambiguity / (len(cases) - ambiguous_expected), 4) if len(cases) != ambiguous_expected else None,
        "PENDING_ACTION_TARGET_MUTATION": "NOT_REPRESENTED_IN_ROUTING_HOLDOUT",
        "latency_ms": {"mean": round(mean(row["semantic"]["latency_ms"] for row in rows), 3)},
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--result-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    if not settings.server_semantic_router_local_model_path or not settings.server_semantic_router_local_model_sha256:
        raise RuntimeError("LOCAL_SEMANTIC_RUNTIME_NOT_CONFIGURED")
    cases = _read_cases()
    result_dir = args.result_dir.resolve()
    # A per-run directory may already contain launcher logs before the first
    # checkpoint exists; only the result file itself controls resume safety.
    result_dir.mkdir(parents=True, exist_ok=True)
    output = result_dir / "routing.jsonl"
    if output.exists() and not args.resume:
        raise RuntimeError("ROUTING_RESULT_ALREADY_EXISTS")
    prior = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line] if output.exists() else []
    completed = {item["case_id"] for item in prior}
    adapter = LocalQwenSemanticAdapter(
        settings.server_semantic_router_local_model_path,
        model_name=settings.server_semantic_router_model or "Qwen/Qwen3-0.6B",
        expected_model_sha256=settings.server_semantic_router_local_model_sha256,
        timeout_seconds=settings.server_semantic_router_timeout_seconds,
    )
    await adapter.prewarm()
    router = SemanticRouterService(
        mode=settings.server_semantic_router_mode,
        slm_adapter=adapter,
        slm_confidence_threshold=settings.server_semantic_router_confidence,
    )
    with output.open("a", encoding="utf-8") as handle:
        for index, case in enumerate(cases, start=1):
            if case["case_id"] in completed:
                continue
            result = await router.parse(case["text"])
            actual = result.to_debug_dict()
            row = {"case_id": case["case_id"], "actual": {key: actual[key] for key in ("primary_intent", "secondary_intents", "health_context", "negated_actions", "explicit_write_action", "clarification_required")}, "semantic": actual}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"ROUTING {index}/{len(cases)}", flush=True)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != len(cases):
        raise RuntimeError("ROUTING_CHECKPOINT_INCOMPLETE")
    metadata = {
        "SEMANTIC_MODEL": adapter.model_name,
        "SEMANTIC_MODEL_HASH": settings.server_semantic_router_local_model_sha256,
        "SEMANTIC_ADAPTER": "LocalQwenSemanticAdapter",
        "MODEL_INFERENCE_EXECUTED": sum(bool(row["semantic"]["slm_invoked"]) for row in rows),
        "MODE": settings.server_semantic_router_mode,
        "metrics": _metric(cases, rows),
    }
    (result_dir / "routing_summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
