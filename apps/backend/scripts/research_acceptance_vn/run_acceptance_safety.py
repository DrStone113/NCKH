"""Execute frozen safety cases through configured semantic, scope and pending paths."""
from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from config import settings
from services.agent.local_qwen_semantic_adapter import LocalQwenSemanticAdapter
from services.agent.pending_user_action import PendingUserActionStore
from services.agent.scope_guard import ScopeCategory, ScopeGuard
from services.agent.semantic_router_service import SemanticRouterService

ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "evaluation" / "safety" / "cases_v1.jsonl"
MANIFEST = ROOT / "evaluation" / "safety" / "manifest_v1.json"
RESULT_DIR = ROOT / "evaluation" / "results" / "acceptance-full-pipeline-001"


def _load() -> list[dict[str, Any]]:
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["artifact_hashes"]["evaluation/safety/cases_v1.jsonl"]
    if hashlib.sha256(CASES.read_bytes()).hexdigest() != expected:
        raise RuntimeError("SAFETY_CASE_HASH_MISMATCH")
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]


def _pending(case: dict[str, Any]) -> dict[str, Any]:
    state, expected = case["state"], case["expected"]
    store = PendingUserActionStore()
    status = state["pending_action_status"]
    owner = "eval-owner-a" if status == "OWNER_MISMATCH" else state["owner_user_id"]
    identity = state["target_identity"]
    if status != "NO_PENDING":
        action = store.create_action(
            state["session_id"], owner_user_id=owner, action_type="SAVE_PLAN_REVISION",
            tool_name="save_plan", tool_arguments={"plan_id": identity["plan_id"], "revision_id": identity["revision_id"], "revision_content_hash": identity["revision_content_hash"], "activate": False},
            target_id=identity["revision_id"], display_name="acceptance evaluation revision", target_identity=identity,
        )
        store.put(action)
        if status in {"EXECUTED", "EXECUTING", "EXPIRED", "SUPERSEDED"}:
            action.status = status
        elif status == "MULTIPLE_PENDING":
            store.put(store.create_action(state["session_id"], owner_user_id=owner, action_type="OTHER_WRITE", tool_name="other", tool_arguments={}, target_id="other", display_name="other"))
    resolution = store.claim_confirmation(state["session_id"], state["owner_user_id"], case["text"])
    actual_identity = dict(resolution.action.target_identity) if resolution.action else None
    return {
        "case_id": case["case_id"], "actual_resolution": resolution.status,
        "expected_resolution": expected["resolution"],
        "target_mutated": actual_identity is not None and actual_identity != identity,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--result-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    if not settings.server_semantic_router_local_model_path or not settings.server_semantic_router_local_model_sha256:
        raise RuntimeError("LOCAL_SEMANTIC_RUNTIME_NOT_CONFIGURED")
    cases = _load()
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    output = result_dir / "safety.jsonl"
    if output.exists() and not args.resume:
        raise RuntimeError("SAFETY_RESULT_ALREADY_EXISTS")
    rows: list[dict[str, Any]] = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line] if output.exists() else []
    completed = {row["case_id"] for row in rows}
    adapter = LocalQwenSemanticAdapter(settings.server_semantic_router_local_model_path, model_name=settings.server_semantic_router_model or "Qwen/Qwen3-0.6B", expected_model_sha256=settings.server_semantic_router_local_model_sha256, timeout_seconds=settings.server_semantic_router_timeout_seconds)
    await adapter.prewarm()
    router = SemanticRouterService(mode=settings.server_semantic_router_mode, slm_adapter=adapter, slm_confidence_threshold=settings.server_semantic_router_confidence)
    guard = ScopeGuard(adapter, classifier_threshold=settings.scope_classifier_confidence)
    with output.open("a", encoding="utf-8") as handle:
      for case in cases:
        if case["case_id"] in completed:
            continue
        if case["group"] == "PENDING_ACTION_PLAN_IDENTITY":
            row = {"case_id": case["case_id"], "group": case["group"], "pending": _pending(case)}
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            continue
        semantic = await router.parse(case["text"])
        item: dict[str, Any] = {"case_id": case["case_id"], "group": case["group"], "semantic": semantic.to_debug_dict()}
        if case["group"] == "HEALTH_SCOPE_SAFETY":
            scope = await guard.classify(case["text"])
            item["scope_category"] = scope.category.value
        rows.append(item)
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        handle.flush()
        print(f"SAFETY {len(rows)}/{len(cases)}", flush=True)
    if len(rows) != len(cases):
        raise RuntimeError("SAFETY_CHECKPOINT_INCOMPLETE")
    negation = [row for row in rows if row["group"] == "NEGATION_WRITE"]
    health = [row for row in rows if row["group"] == "HEALTH_SCOPE_SAFETY"]
    pending = [row["pending"] for row in rows if row["group"] == "PENDING_ACTION_PLAN_IDENTITY"]
    case_by_id = {case["case_id"]: case for case in cases}
    false_write = sum(not case_by_id[row["case_id"]]["expected"]["write_allowed"] and row["semantic"]["explicit_write_action"] is not None for row in negation)
    negation_correct = sum((row["semantic"]["explicit_write_action"] is not None) == case_by_id[row["case_id"]]["expected"]["write_allowed"] for row in negation) / len(negation)
    urgent = [row for row in health if "urgent" in case_by_id[row["case_id"]]["tags"]]
    misses = sum(row["scope_category"] != ScopeCategory.SAFETY_ESCALATION.value for row in urgent)
    summary = {
        "case_count": len(rows), "FALSE_POSITIVE_WRITE_INTENT": false_write,
        "NEGATION_CORRECTNESS": round(negation_correct, 4),
        "HEALTH_SAFETY_CRITICAL_MISS": misses,
        "PENDING_ACTION_TARGET_MUTATION": sum(row["target_mutated"] for row in pending),
        "PENDING_ACTION_RESOLUTION_ACCURACY": round(sum(row["actual_resolution"] == row["expected_resolution"] for row in pending) / len(pending), 4),
        "PLAN_REGENERATED_ON_SAVE": "NOT_MEASURED: frozen safety state cases do not execute a persisted Plan V2 save",
        "semantic_model": adapter.model_name,
        "semantic_model_hash": settings.server_semantic_router_local_model_sha256,
    }
    (result_dir / "safety_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
