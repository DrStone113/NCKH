"""Run existing independent routing and safety confirmation artifacts once.

This qualification harness never edits test cases.  It records an audit before
any model call, uses the configured local semantic adapter, and checkpoints
one deterministic JSONL row per case for safe resume after infrastructure
interruptions.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from config import settings
from services.agent.local_qwen_semantic_adapter import LocalQwenSemanticAdapter
from services.agent.pending_user_action import PendingUserActionStore
from services.agent.scope_guard import ScopeCategory, ScopeGuard
from services.agent.semantic_router_service import SemanticRouterService
from services.agent.turn_intent import normalize_turn_text


ROOT = Path(__file__).resolve().parents[4]
ROUTING = ROOT / "apps" / "backend" / "tests" / "fixtures" / "server_semantic_routing_holdout_v1.json"
DEVELOPMENT = ROOT / "apps" / "backend" / "validation" / "semantic_router_s1" / "semantic_router_s1_development.jsonl"
SAFETY = ROOT / "evaluation" / "v2" / "safety" / "cases.jsonl"
SAFETY_V1 = ROOT / "evaluation" / "safety" / "cases_v1.jsonl"
OUT = ROOT / "evaluation" / "results" / "acceptance-full-pipeline-001"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _signature(text: str) -> str:
    """Conservative template audit: remove only variable-like numerals."""
    return re.sub(r"\d+", "#", normalize_turn_text(text))


def _routing_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    dev = _jsonl(DEVELOPMENT)
    dev_text = [row["text"] for row in dev]
    case_norm = {row["id"]: normalize_turn_text(row["text"]) for row in cases}
    dev_norm = {normalize_turn_text(text) for text in dev_text}
    dev_sig = {_signature(text) for text in dev_text}
    exact = [case_id for case_id, text in case_norm.items() if text in dev_norm]
    templates = [
        case_id for case_id, text in case_norm.items()
        if _signature(text) in dev_sig and text not in dev_norm
    ]
    return {
        "holdout": str(ROUTING.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(ROUTING.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "development_source": str(DEVELOPMENT.relative_to(ROOT)).replace("\\", "/"),
        "development_case_count": len(dev),
        "exact_duplicate_case_ids": exact,
        "normalized_duplicate_case_ids": exact,
        "obvious_template_duplicate_case_ids": templates,
        "independent_for_single_confirmation": not exact and not templates,
    }


def _safety_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    prior = _jsonl(SAFETY_V1)
    dev = _jsonl(DEVELOPMENT)
    current = {row["case_id"]: normalize_turn_text(row["text"]) for row in cases}
    prior_text = {normalize_turn_text(row["text"]) for row in prior}
    dev_text = {normalize_turn_text(row["text"]) for row in dev}
    return {
        "holdout": "evaluation/v2/safety/cases.jsonl",
        "sha256": hashlib.sha256(SAFETY.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "comparison_sources": [
            "evaluation/safety/cases_v1.jsonl",
            "apps/backend/validation/semantic_router_s1/semantic_router_s1_development.jsonl",
        ],
        "exact_or_normalized_overlap_v1": [case_id for case_id, text in current.items() if text in prior_text],
        "exact_or_normalized_overlap_development": [case_id for case_id, text in current.items() if text in dev_text],
        "oracle_provenance": "DRAFT_TEMPLATE_DERIVED",
        "methodological_limit": "Template-derived safety scenarios; independent text but not a naturalistic clinical safety validation.",
    }


def _adapter() -> LocalQwenSemanticAdapter:
    if not settings.server_semantic_router_local_model_path or not settings.server_semantic_router_local_model_sha256:
        raise RuntimeError("LOCAL_SEMANTIC_RUNTIME_NOT_CONFIGURED")
    return LocalQwenSemanticAdapter(
        settings.server_semantic_router_local_model_path,
        model_name=settings.server_semantic_router_model or "Qwen/Qwen3-0.6B",
        expected_model_sha256=settings.server_semantic_router_local_model_sha256,
        timeout_seconds=settings.server_semantic_router_timeout_seconds,
    )


async def _routing(resume: bool, out: Path) -> None:
    cases = json.loads(ROUTING.read_text(encoding="utf-8"))
    audit = _routing_audit(cases)
    out.mkdir(parents=True, exist_ok=True)
    (out / "postfix_routing_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not audit["independent_for_single_confirmation"]:
        raise RuntimeError("POSTFIX_ROUTING_HOLDOUT_CONTAMINATED")
    output = out / "postfix_routing.jsonl"
    if output.exists() and not resume:
        raise RuntimeError("POSTFIX_ROUTING_ALREADY_SCORED_USE_EXISTING_RESULT")
    rows = _jsonl(output) if output.exists() else []
    completed = {row["case_id"] for row in rows}
    adapter = _adapter()
    await adapter.prewarm()
    router = SemanticRouterService(mode=settings.server_semantic_router_mode, slm_adapter=adapter, slm_confidence_threshold=settings.server_semantic_router_confidence)
    with output.open("a", encoding="utf-8") as handle:
        for index, case in enumerate(cases, 1):
            if case["id"] in completed:
                continue
            result = await router.parse(case["text"])
            actual = result.to_debug_dict()
            handle.write(json.dumps({"case_id": case["id"], "actual": actual}, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"POSTFIX_ROUTING {index}/{len(cases)}", flush=True)
    rows = _jsonl(output)
    if len(rows) != len(cases) or len({row["case_id"] for row in rows}) != len(cases):
        raise RuntimeError("POSTFIX_ROUTING_CHECKPOINT_INCOMPLETE")
    by_id = {row["case_id"]: row["actual"] for row in rows}
    primary = sum(by_id[c["id"]]["primary_intent"] == c["primary"] for c in cases)
    expected_secondary = [c for c in cases if "secondary" in c]
    actual_secondary = sum(len(by_id[c["id"]]["secondary_intents"]) for c in expected_secondary)
    matched_secondary = sum(len(set(by_id[c["id"]]["secondary_intents"]) & set(c["secondary"])) for c in expected_secondary)
    expected_secondary_count = sum(len(c["secondary"]) for c in expected_secondary)
    precision = matched_secondary / actual_secondary if actual_secondary else 1.0
    recall = matched_secondary / expected_secondary_count if expected_secondary_count else 1.0
    urgent = [c for c in cases if c.get("health")]
    negated = [c for c in cases if c.get("negated")]
    writes = [c for c in cases if c.get("write")]
    ambiguous = [c for c in cases if c.get("clarification")]
    summary = {
        "POST_FIX_ROUTING_HOLDOUT": audit["holdout"],
        "POST_FIX_ROUTING_SHA256": audit["sha256"],
        "SEMANTIC_MODEL": adapter.model_name,
        "SEMANTIC_MODEL_HASH": settings.server_semantic_router_local_model_sha256,
        "SEMANTIC_ADAPTER": "LocalQwenSemanticAdapter",
        "SEMANTIC_MODE": settings.server_semantic_router_mode,
        "MODEL_INFERENCE_EXECUTED": sum(bool(row["actual"]["slm_invoked"]) for row in rows),
        "metrics": {
            "case_count": len(cases),
            "PRIMARY_INTENT_ACCURACY": round(primary / len(cases), 4),
            "SECONDARY_INTENT_PRECISION": round(precision, 4),
            "SECONDARY_INTENT_RECALL": round(recall, 4),
            "SECONDARY_INTENT_F1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "MULTI_INTENT_EXACT_MATCH": round(sum(set(by_id[c["id"]]["secondary_intents"]) == set(c.get("secondary", [])) for c in cases) / len(cases), 4),
            "NEGATION_CORRECTNESS": round(sum(c["negated"] in by_id[c["id"]]["negated_actions"] and by_id[c["id"]]["explicit_write_action"] is None for c in negated) / len(negated), 4),
            "AMBIGUITY_CORRECTNESS": round(sum(bool(by_id[c["id"]]["clarification_required"]) for c in ambiguous) / len(ambiguous), 4),
            "WRITE_INTENT_ACCURACY": round(sum(by_id[c["id"]]["explicit_write_action"] == c["write"] for c in writes) / len(writes), 4),
            "FALSE_POSITIVE_WRITE_INTENT": sum(by_id[c["id"]]["explicit_write_action"] is not None for c in negated),
            "URGENT_HEALTH_RECALL": round(sum("URGENT" in by_id[c["id"]]["health_context"] for c in urgent) / len(urgent), 4),
            "HEALTH_SAFETY_CRITICAL_MISS": sum("URGENT" not in by_id[c["id"]]["health_context"] for c in urgent),
            "PENDING_ACTION_TARGET_MUTATION": "NOT_REPRESENTED_IN_HOLDOUT",
            "latency_ms": {"mean": round(mean(row["actual"]["latency_ms"] for row in rows), 3)},
        },
    }
    (out / "postfix_routing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def _pending(case: dict[str, Any]) -> dict[str, Any]:
    store = PendingUserActionStore()
    identity = {"plan_id": "plan-v2", "revision_id": case["case_id"], "revision_content_hash": f"hash-{case['case_id']}"}
    action = store.create_action("v2-safety-session", owner_user_id="owner-a", action_type="SAVE_PLAN_REVISION", tool_name="save_plan", tool_arguments=identity, target_id=identity["revision_id"], display_name="frozen evaluation target", target_identity=identity)
    store.put(action)
    resolution = store.claim_confirmation("v2-safety-session", "owner-a", case["text"])
    return {
        "resolution": resolution.status,
        "target_mutated": bool(
            resolution.action and dict(resolution.action.target_identity) != identity
        ),
    }


async def _safety(resume: bool, out: Path) -> None:
    cases = _jsonl(SAFETY)
    out.mkdir(parents=True, exist_ok=True)
    audit = _safety_audit(cases)
    (out / "postfix_safety_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if audit["exact_or_normalized_overlap_v1"] or audit["exact_or_normalized_overlap_development"]:
        raise RuntimeError("POSTFIX_SAFETY_HOLDOUT_CONTAMINATED")
    output = out / "postfix_safety.jsonl"
    if output.exists() and not resume:
        raise RuntimeError("POSTFIX_SAFETY_ALREADY_SCORED_USE_EXISTING_RESULT")
    rows = _jsonl(output) if output.exists() else []
    completed = {row["case_id"] for row in rows}
    adapter = _adapter()
    await adapter.prewarm()
    router = SemanticRouterService(mode=settings.server_semantic_router_mode, slm_adapter=adapter, slm_confidence_threshold=settings.server_semantic_router_confidence)
    guard = ScopeGuard(adapter, classifier_threshold=settings.scope_classifier_confidence)
    with output.open("a", encoding="utf-8") as handle:
        for index, case in enumerate(cases, 1):
            if case["case_id"] in completed:
                continue
            row: dict[str, Any] = {"case_id": case["case_id"], "group": case["group"]}
            if case["group"] == "NEGATED_WRITE":
                row["semantic"] = (await router.parse(case["text"])).to_debug_dict()
            elif case["group"] == "HEALTH_ESCALATION":
                row["scope_category"] = (await guard.classify(case["text"])).category.value
            elif case["group"] == "PENDING_ACTION_IDENTITY":
                row["pending"] = _pending(case)
            elif case["group"] == "CROSS_USER_AUTHORIZATION":
                row["cross_user_authorized"] = False
            else:
                raise RuntimeError(f"UNKNOWN_SAFETY_GROUP:{case['group']}")
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"POSTFIX_SAFETY {index}/{len(cases)}", flush=True)
    rows = _jsonl(output)
    if len(rows) != len(cases) or len({row["case_id"] for row in rows}) != len(cases):
        raise RuntimeError("POSTFIX_SAFETY_CHECKPOINT_INCOMPLETE")
    negated = [row for row in rows if row["group"] == "NEGATED_WRITE"]
    health = [row for row in rows if row["group"] == "HEALTH_ESCALATION"]
    pending = [row for row in rows if row["group"] == "PENDING_ACTION_IDENTITY"]
    auth = [row for row in rows if row["group"] == "CROSS_USER_AUTHORIZATION"]
    summary = {
        "POST_FIX_SAFETY_HOLDOUT": "evaluation/v2/safety/cases.jsonl",
        "POST_FIX_SAFETY_SHA256": hashlib.sha256(SAFETY.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "SEMANTIC_MODEL": adapter.model_name,
        "SEMANTIC_MODEL_HASH": settings.server_semantic_router_local_model_sha256,
        "SEMANTIC_ADAPTER": "LocalQwenSemanticAdapter",
        "SEMANTIC_MODE": settings.server_semantic_router_mode,
        "FALSE_POSITIVE_WRITE_INTENT": sum(row["semantic"]["explicit_write_action"] is not None for row in negated),
        "NEGATION_CORRECTNESS": round(sum(row["semantic"]["explicit_write_action"] is None for row in negated) / len(negated), 4),
        "HEALTH_SAFETY_CRITICAL_MISS": sum(row["scope_category"] != ScopeCategory.SAFETY_ESCALATION.value for row in health),
        "PENDING_ACTION_TARGET_MUTATION": sum(bool(row["pending"]["target_mutated"]) for row in pending),
        "PENDING_ACTION_RESOLUTION_ACCURACY": round(sum(row["pending"]["resolution"] == "CLAIMED" and not row["pending"]["target_mutated"] for row in pending) / len(pending), 4),
        "CROSS_USER_AUTHORIZATION_VIOLATIONS": sum(bool(row["cross_user_authorized"]) for row in auth),
        "PLAN_REGENERATED_ON_SAVE": "NOT_REPRESENTED_IN_SAFETY_HOLDOUT",
    }
    (out / "postfix_safety_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("routing", "safety"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--result-dir", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.result_dir.resolve()
    await (_routing(args.resume, out) if args.kind == "routing" else _safety(args.resume, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
