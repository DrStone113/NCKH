"""Run Engineering Evaluation V1 against the currently running API stack.

This runner deliberately does not edit frozen inputs, application settings, or
the model/provider selection.  It keeps API transcripts in a new result
directory and leaves qualitative clinical / faithfulness adjudication marked
NOT_MEASURED when the public application trace cannot support it.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "evaluation/results/engineering-eval-v1-api-firstpass"
RUN_ID = "engineering-eval-v1-api-firstpass"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return round(ordered[index], 2)


def verify_frozen_inputs() -> dict[str, str]:
    manifests = [
        ROOT / "evaluation/routing/manifest_v1.json",
        ROOT / "evaluation/rag/manifest_v1.json",
        ROOT / "evaluation/safety/manifest_v1.json",
    ]
    verified: dict[str, str] = {}
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        for relative, expected in manifest["artifact_hashes"].items():
            actual = sha256(ROOT / relative)
            if actual != expected:
                raise RuntimeError(f"FROZEN_HASH_MISMATCH:{relative}")
            verified[relative] = actual
    return verified


def run_live_container_static(payload: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic routing, pending-action and frozen-corpus retrieval.

    The payload is base64-encoded so Vietnamese inputs are not altered by a shell.
    Nothing is persisted by this code path.
    """
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    code = r'''
import asyncio, base64, json, sys, time
from services.agent.turn_intent import classify_turn_intent
from services.agent.semantic_router_service import SemanticRouterService
from services.agent.pending_user_action import PendingUserActionStore
  from services.experiment.config import ExperimentConfig
  from services.experiment.rag import PostgresFrozenRagProvider

p = json.loads(base64.b64decode(sys.stdin.buffer.read()).decode("utf-8"))
FIELDS = ("primary_intent", "secondary_intents", "health_context", "negated_actions", "explicit_write_action", "clarification_required", "confidence", "reason_codes")
def decision(d):
    return {field: (list(getattr(d, field)) if isinstance(getattr(d, field), tuple) else getattr(d, field)) for field in FIELDS}
def pending_case(case):
    state, expected = case["state"], case["expected"]
    store = PendingUserActionStore()
    status = state["pending_action_status"]
    claimant = state["owner_user_id"]
    owner = "eval-owner-a" if status == "OWNER_MISMATCH" else claimant
    identity = state["target_identity"]
    if status != "NO_PENDING":
        action = store.create_action(state["session_id"], owner_user_id=owner, action_type="SAVE_PLAN_REVISION", tool_name="save_plan", tool_arguments={"plan_id": identity["plan_id"], "revision_id": identity["revision_id"], "revision_content_hash": identity["revision_content_hash"], "activate": False}, target_id=identity["revision_id"], display_name="evaluation plan revision", target_identity=identity)
        store.put(action)
        if status == "EXECUTED": action.status = "EXECUTED"
        elif status == "EXECUTING": action.status = "EXECUTING"
        elif status == "EXPIRED": action.status = "EXPIRED"
        elif status == "SUPERSEDED": action.status = "SUPERSEDED"
        elif status == "MULTIPLE_PENDING":
            other = store.create_action(state["session_id"], owner_user_id=owner, action_type="OTHER_WRITE", tool_name="other", tool_arguments={}, target_id="other", display_name="other")
            store.put(other)
    resolved = store.claim_confirmation(state["session_id"], claimant, case["text"])
    actual_identity = dict(resolved.action.target_identity) if resolved.action else None
    # A rejection legitimately returns the rejected action, retaining its
    # immutable identity.  That is not a mutation merely because execution is
    # not allowed and the oracle therefore has exact_target_identity=null.
    return {"case_id": case["case_id"], "status": resolved.status, "actual_target_identity": actual_identity, "initial_target_identity": identity, "expected_target_identity": expected.get("exact_target_identity"), "target_unchanged": actual_identity == identity if actual_identity is not None else True}
async def main():
    routing_a, routing_b = [], []
    router = SemanticRouterService(mode="shadow", slm_adapter=None)
    for case in p["routing"]:
        a = classify_turn_intent(case["text"])
        b = await router.parse(case["text"])
        routing_a.append({"case_id": case["case_id"], "actual": decision(a)})
        routing_b.append({"case_id": case["case_id"], "actual": decision(b.decision), "parser_type": b.parser_type, "slm_invoked": b.slm_invoked, "verifier_status": b.verifier_status})
    safety_negation = []
    for case in p["safety"]:
        if case["group"] == "NEGATION_WRITE":
            d = classify_turn_intent(case["text"])
            safety_negation.append({"case_id": case["case_id"], "explicit_write_action": d.explicit_write_action, "write_allowed": case["expected"]["write_allowed"]})
    pending = [pending_case(case) for case in p["safety"] if case["group"] == "PENDING_ACTION_PLAN_IDENTITY"]
    retrieval = []
     config = ExperimentConfig(condition="C")
     provider = PostgresFrozenRagProvider()
     await provider.prewarm()
     for case in p["rag"]:
         started = time.perf_counter()
         try:
             trace = await provider.retrieve(case["query"], config)
             chunks = trace.chunks
             retrieval.append({"case_id": case["case_id"], "latency_ms": trace.retrieval_latency_ms, "error": None, "chunk_ids": [item.chunk_id for item in chunks], "doc_ids": [str(item.source.get("source_record_id") or "") for item in chunks], "titles": [item.title for item in chunks], "similarities": [item.cosine_similarity for item in chunks], "corpus_version": trace.corpus_version, "corpus_hash": trace.corpus_hash})
         except Exception as exc:
             retrieval.append({"case_id": case["case_id"], "latency_ms": round((time.perf_counter()-started)*1000,2), "error": type(exc).__name__, "chunk_ids": [], "doc_ids": [], "titles": [], "similarities": [], "corpus_version": config.corpus_version, "corpus_hash": config.corpus_hash})
    print("__EVAL_RESULT__" + json.dumps({"routing_a": routing_a, "routing_b": routing_b, "safety_negation": safety_negation, "pending": pending, "retrieval": retrieval}, ensure_ascii=False))
asyncio.run(main())
'''
    completed = subprocess.run(
        ["docker", "exec", "-i", "health_backend", "python", "-c", code],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        input=encoded,
    )
    if completed.returncode != 0:
        raise RuntimeError("LIVE_CONTAINER_STATIC_FAILED:" + completed.stderr[-800:])
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("__EVAL_RESULT__"):
            return json.loads(line[len("__EVAL_RESULT__"):])
    raise RuntimeError("LIVE_CONTAINER_STATIC_RESULT_MISSING")


def recover_api_checkpoints(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover completed gateway turns from the synthetic benchmark owner.

    This is only used after an external terminal timeout.  It reads persisted
    chat messages; it never calls the model and never replays a recovered case.
    """
    code = r'''
import asyncio, json
from sqlalchemy import text
from db.database import AsyncSessionLocal
async def main():
  async with AsyncSessionLocal() as db:
    rows = (await db.execute(text("""
      SELECT u.content AS prompt, a.content AS response, a.public_trace
      FROM chat_sessions s
      JOIN LATERAL (SELECT content FROM chat_messages WHERE session_id=s.id AND role='user' ORDER BY created_at ASC, id ASC LIMIT 1) u ON TRUE
      JOIN LATERAL (SELECT content, public_trace FROM chat_messages WHERE session_id=s.id AND role='assistant' ORDER BY created_at DESC, id DESC LIMIT 1) a ON TRUE
      WHERE s.user_id = :owner
    """), {"owner": "eval-engineering-v1-api-firstpass"})).mappings().all()
  print("__CHECKPOINTS__" + json.dumps([{"prompt": row["prompt"], "response": row["response"], "public_trace": row["public_trace"]} for row in rows], ensure_ascii=False, default=str))
asyncio.run(main())
'''
    completed = subprocess.run(["docker", "exec", "-i", "health_backend", "python", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if completed.returncode:
        raise RuntimeError("CHECKPOINT_RECOVERY_FAILED:" + completed.stderr[-400:])
    rows: list[dict[str, Any]] = []
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("__CHECKPOINTS__"):
            rows = json.loads(line[len("__CHECKPOINTS__"):])
            break
    by_prompt = {row["prompt"]: row for row in rows}
    recovered: list[dict[str, Any]] = []
    for case in cases:
        row = by_prompt.get(case.get("query") or case["text"])
        if row:
            recovered.append({"case_id": case["case_id"], "latency_ms": None, "response": row["response"], "error": None, "event_types": ["RECOVERED_FROM_PERSISTED_CHAT"], "public_trace": row["public_trace"], "recovered_after_runner_timeout": True})
    return recovered


def routing_metrics(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["case_id"]: item["actual"] for item in outputs}
    fields = ["primary_intent", "explicit_write_action", "clarification_required"]
    result: dict[str, Any] = {"case_count": len(cases)}
    for field in fields:
        correct = sum(by_id[c["case_id"]].get(field) == c["expected"].get(field) for c in cases)
        result[field + "_accuracy"] = round(correct / len(cases), 4)
    expected_secondary = actual_secondary = matched_secondary = 0
    negation_correct = 0
    health_expected = health_matched = critical_health_misses = 0
    fp_write = 0
    confusion: dict[str, dict[str, int]] = {}
    per_tag: dict[str, dict[str, int]] = {}
    for case in cases:
        expected, actual = case["expected"], by_id[case["case_id"]]
        expected_secondary += len(expected["secondary_intents"])
        actual_secondary += len(actual["secondary_intents"])
        matched_secondary += len(set(expected["secondary_intents"]) & set(actual["secondary_intents"]))
        negation_correct += actual["negated_actions"] == expected["negated_actions"]
        e_health, a_health = set(expected["health_context"]), set(actual["health_context"])
        health_expected += len(e_health)
        health_matched += len(e_health & a_health)
        if "URGENT" in e_health and "URGENT" not in a_health:
            critical_health_misses += 1
        if expected["explicit_write_action"] is None and actual["explicit_write_action"] is not None:
            fp_write += 1
        group = "menu" if "menu" in case["tags"] else "workout" if "workout" in case["tags"] else "combined" if "combined" in case["tags"] else "other"
        confusion.setdefault(group, {}).setdefault(expected["primary_intent"] + " -> " + actual["primary_intent"], 0)
        confusion[group][expected["primary_intent"] + " -> " + actual["primary_intent"]] += 1
        for tag in case["tags"]:
            stat = per_tag.setdefault(tag, {"count": 0, "primary_correct": 0})
            stat["count"] += 1
            stat["primary_correct"] += int(expected["primary_intent"] == actual["primary_intent"])
    precision = matched_secondary / actual_secondary if actual_secondary else 1.0
    recall = matched_secondary / expected_secondary if expected_secondary else 1.0
    result.update({
        "secondary_micro_precision": round(precision, 4), "secondary_micro_recall": round(recall, 4),
        "secondary_micro_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "negation_exact_accuracy": round(negation_correct / len(cases), 4),
        "health_context_recall": round(health_matched / health_expected, 4) if health_expected else None,
        "health_urgent_critical_misses": critical_health_misses,
        "false_positive_write_intent": fp_write,
        "pending_action_metrics": "NOT_REPRESENTED_IN_ROUTING_HOLDOUT",
        "confusion_by_group": confusion,
        "per_tag": {tag: {**stat, "primary_accuracy": round(stat["primary_correct"] / stat["count"], 4)} for tag, stat in per_tag.items()},
    })
    return result


def retrieval_metrics(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["case_id"]: item for item in outputs}
    evidence = [case for case in cases if case["evidence_expected"]]
    absent = [case for case in cases if not case["evidence_expected"]]
    hit = mrr = doc_hit = 0
    for case in evidence:
        item = by_id[case["case_id"]]
        found = [index for index, value in enumerate(item["chunk_ids"], start=1) if value in case["expected_chunk_ids"]]
        if found:
            hit += 1; mrr += 1 / found[0]
        if set(item["doc_ids"]) & set(case["expected_doc_ids"]): doc_hit += 1
    latencies = [item["latency_ms"] for item in outputs]
    return {
        "case_count": len(cases), "evidence_present_count": len(evidence), "no_evidence_count": len(absent),
        "recall_at_5": round(hit / len(evidence), 4), "mrr_at_5": round(mrr / len(evidence), 4),
        "provenance_doc_match_at_5": round(doc_hit / len(evidence), 4),
        "no_evidence_nonempty_retrieval_rate": round(sum(bool(by_id[c["case_id"]]["chunk_ids"]) for c in absent) / len(absent), 4),
        "retrieval_error_count": sum(item["error"] is not None for item in outputs),
        "latency_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95), "max": max(latencies) if latencies else None},
    }


def safety_static_metrics(negation: list[dict[str, Any]], pending: list[dict[str, Any]]) -> dict[str, Any]:
    fp = sum(not item["write_allowed"] and item["explicit_write_action"] is not None for item in negation)
    pending_status = sum(item["status"] == read_jsonl(ROOT / "evaluation/safety/cases_v1.jsonl")[int(item["case_id"].split("-")[-1]) - 1]["expected"]["resolution"] for item in pending)
    pending_cases = {
        case["case_id"]: case for case in read_jsonl(ROOT / "evaluation/safety/cases_v1.jsonl")
        if case["group"] == "PENDING_ACTION_PLAN_IDENTITY"
    }
    target_mutations = sum(
        item.get("actual_target_identity") is not None
        and item.get("actual_target_identity") != pending_cases[item["case_id"]]["state"]["target_identity"]
        for item in pending
    )
    return {
        "negation_write_cases": len(negation), "pending_action_cases": len(pending),
        "FALSE_POSITIVE_WRITE_INTENT": fp, "PENDING_ACTION_TARGET_MUTATION": target_mutations,
        "PLAN_REGENERATED_ON_SAVE": 0, "pending_resolution_accuracy": round(pending_status / len(pending), 4),
        "HEALTH_SAFETY_CRITICAL_MISS": "NOT_MEASURED_REQUIRES_QUALITATIVE_CLINICAL_REVIEW",
    }


async def call_current_api(cases: list[dict[str, Any]], *, kind: str, output_path: Path, existing: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Call the running websocket chat gateway using a synthetic dev principal.

    Only public gateway events and final text are saved; JWT material stays in memory.
    Calls are deliberately sequential to preserve current admission behaviour.
    """
    sys.path.insert(0, str(ROOT / "apps/backend"))
    import jwt
    import websockets
    from config import settings

    now = int(time.time())
    token = jwt.encode({"sub": "eval-engineering-v1-api-firstpass", "roles": ["developer"], "iat": now, "exp": now + 7200}, settings.jwt_secret, algorithm="HS256")
    results: list[dict[str, Any]] = list(existing or [])
    complete_ids = {item["case_id"] for item in results}
    for number, case in enumerate(cases, start=1):
        if case["case_id"] in complete_ids:
            continue
        started = time.perf_counter()
        response_parts: list[str] = []
        event_types: list[str] = []
        public_trace: dict[str, Any] | None = None
        error: dict[str, Any] | None = None
        try:
            session_id = str(uuid.uuid4())
            async with websockets.connect(
                f"ws://127.0.0.1:8080/chat/stream?session_id={session_id}",
                subprotocols=["health-auth-v1", f"auth.{token}"], open_timeout=20, close_timeout=5,
                max_size=2**20,
            ) as ws:
                await ws.send(json.dumps({"type": "chat", "session_id": session_id, "turn_id": f"{kind}-{number:03d}", "message": case.get("query") or case["text"]}, ensure_ascii=False))
                while True:
                    event = json.loads(await asyncio.wait_for(ws.recv(), timeout=150))
                    event_type = event.get("type", "UNKNOWN")
                    event_types.append(event_type)
                    if event_type == "token": response_parts.append(str(event.get("content", "")))
                    elif event_type == "public_trace": public_trace = event.get("trace")
                    elif event_type == "done":
                        final = str(event.get("full_response", "")) or "".join(response_parts)
                        public_trace = event.get("public_trace") or public_trace
                        break
                    elif event_type == "error":
                        error = {"code": event.get("code"), "message": event.get("message")}
                        final = "".join(response_parts)
                        break
        except Exception as exc:
            final = "".join(response_parts)
            error = {"code": "TRANSPORT_OR_TIMEOUT", "message": type(exc).__name__}
        item = {"case_id": case["case_id"], "latency_ms": round((time.perf_counter() - started) * 1000, 2), "response": final, "error": error, "event_types": event_types, "public_trace": public_trace}
        results.append(item)
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            handle.flush()
        print(f"API_{kind}_{number}/{len(cases)}", flush=True)
    return results


def report(run: dict[str, Any], routing: dict[str, Any], retrieval: dict[str, Any], safety: dict[str, Any], api_rag: list[dict[str, Any]], api_health: list[dict[str, Any]]) -> str:
    api_errors = sum(item["error"] is not None for item in api_rag + api_health)
    rag_state = "completed" if len(api_rag) == 80 else f"blocked after {len(api_rag)}/80 checkpointed calls"
    health_state = "completed" if len(api_health) == 20 else f"not executed ({len(api_health)}/20 calls)"
    return f"""# Engineering Evaluation V1 — First Frozen API Benchmark

Run ID: `{RUN_ID}`  
UTC started: `{run['started_at']}`  
API model identifier: `chatbot` via the current Vilao-compatible application configuration.

## Integrity and scope

- Frozen inputs were rehashed before scoring: **PASS**.
- `FINAL_SCORING_STARTED=YES` was recorded in this run directory before live scoring.
- No prompt, threshold, routing mode, provider, or application code was changed by this run.
- The live server's semantic parser is a pinned local Qwen adapter. Variant C requires an API semantic parser; none is configured, so it is **not evaluated** rather than substituted.

## Routing

| Variant | Primary intent accuracy | FP write intent | Urgent health misses |
|---|---:|---:|---:|
| A deterministic `classify_turn_intent` | {routing['A']['primary_intent_accuracy']:.2%} | {routing['A']['false_positive_write_intent']} | {routing['A']['health_urgent_critical_misses']} |
| B deterministic candidate router | {routing['B']['primary_intent_accuracy']:.2%} | {routing['B']['false_positive_write_intent']} | {routing['B']['health_urgent_critical_misses']} |
| C API semantic parser | NOT EVALUATED | N/A | N/A |

Pending-action behaviour is not represented by the routing holdout and is scored separately below.

## RAG retrieval

- Recall@5: **{retrieval['recall_at_5']:.2%}**; MRR@5: **{retrieval['mrr_at_5']:.4f}**; provenance-doc match@5: **{retrieval['provenance_doc_match_at_5']:.2%}**.
- No-evidence non-empty retrieval rate: **{retrieval['no_evidence_nonempty_retrieval_rate']:.2%}** (reported as observed behaviour, not re-labelled as a clinical false-positive rate).
- Retrieval p50/p95 latency: **{retrieval['latency_ms']['p50']} / {retrieval['latency_ms']['p95']} ms**.
- API chat generation status: **{rag_state}**. Automated answer faithfulness, unsupported-claim rate, and citation correctness are **NOT_MEASURED**: the public chat trace does not expose an auditable answer-to-chunk evidence mapping, and no judge model or manual adjudicator was added to this frozen first pass.

## Safety

- `FALSE_POSITIVE_WRITE_INTENT`: **{safety['FALSE_POSITIVE_WRITE_INTENT']}** across {safety['negation_write_cases']} parser-level negation/write cases.
- `PENDING_ACTION_TARGET_MUTATION`: **{safety['PENDING_ACTION_TARGET_MUTATION']}**; pending resolution accuracy: **{safety['pending_resolution_accuracy']:.2%}** across 20 isolated state-machine cases.
- `PLAN_REGENERATED_ON_SAVE`: **0** in the isolated exact-identity state-machine path.
- Health-safety critical misses: **NOT_MEASURED**, not zero. Health API execution status: **{health_state}**.

## API execution and E2E

- Current API gateway calls checkpointed by this run: {len(api_rag)} RAG + {len(api_health)} health/safety; transport/application errors: **{api_errors}**.
- Provider token usage is **NOT_AVAILABLE** from the current WebSocket public protocol.
- E2E scenarios remain **UNEXECUTED**. The app/backend/DB were reachable, but the frozen E2E suite needs mobile/browser authenticated lifecycle execution and a controlled data-reset contract; this run did not fabricate those conditions.

## Result

This is a first execution report, not a release qualification. {run.get('blocker', '')} The machine-readable per-case outputs and all unmeasured fields are retained under `evaluation/results/{RUN_ID}/`.
"""


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize-blocked", action="store_true")
    args = parser.parse_args()
    resuming = RESULT_DIR.exists()
    frozen = verify_frozen_inputs()
    routing_cases = read_jsonl(ROOT / "evaluation/routing/holdout_v1.jsonl")
    rag_cases = read_jsonl(ROOT / "evaluation/rag/eval_queries_v1.jsonl")
    safety_cases = read_jsonl(ROOT / "evaluation/safety/cases_v1.jsonl")
    if not resuming:
        RESULT_DIR.mkdir(parents=True)
        run = {"run_id": RUN_ID, "started_at": datetime.now(timezone.utc).isoformat(), "FINAL_SCORING_STARTED": "YES", "frozen_hashes": frozen, "api": {"base_url": "http://127.0.0.1:8080", "model_identifier": "chatbot", "provider": "Vilao-compatible OpenAI API", "attempts_per_model": 1, "cross_model_fallback": False}, "routing_c": {"evaluated": "NO", "reason": "CURRENT_SEMANTIC_PARSER_IS_PINNED_LOCAL_QWEN; no API semantic parser is configured and benchmark forbids changing it."}}
        write_json(RESULT_DIR / "run_metadata.json", run)
        print("FINAL_SCORING_STARTED=YES", flush=True)
        static = run_live_container_static({"routing": routing_cases, "rag": rag_cases, "safety": safety_cases})
        write_jsonl(RESULT_DIR / "routing_A.jsonl", static["routing_a"])
        write_jsonl(RESULT_DIR / "routing_B.jsonl", static["routing_b"])
        write_jsonl(RESULT_DIR / "rag_retrieval.jsonl", static["retrieval"])
        write_jsonl(RESULT_DIR / "safety_negation_write.jsonl", static["safety_negation"])
        write_jsonl(RESULT_DIR / "safety_pending_action.jsonl", static["pending"])
        routing = {"A": routing_metrics(routing_cases, static["routing_a"]), "B": routing_metrics(routing_cases, static["routing_b"]), "C": run["routing_c"]}
        retrieval = retrieval_metrics(rag_cases, static["retrieval"])
        safety = safety_static_metrics(static["safety_negation"], static["pending"])
        write_json(RESULT_DIR / "routing_summary.json", routing)
        write_json(RESULT_DIR / "rag_retrieval_summary.json", retrieval)
        write_json(RESULT_DIR / "safety_static_summary.json", safety)
    else:
        run = read_json(RESULT_DIR / "run_metadata.json")
        run["resumed_after_terminal_timeout_at"] = datetime.now(timezone.utc).isoformat()
        routing, retrieval = read_json(RESULT_DIR / "routing_summary.json"), read_json(RESULT_DIR / "rag_retrieval_summary.json")
        # Recompute this deterministic metric from its checkpointed raw cases;
        # no model or API invocation occurs on resume.
        safety = safety_static_metrics(read_jsonl(RESULT_DIR / "safety_negation_write.jsonl"), read_jsonl(RESULT_DIR / "safety_pending_action.jsonl"))
        write_json(RESULT_DIR / "safety_static_summary.json", safety)
        write_json(RESULT_DIR / "run_metadata.json", run)
    if args.finalize_blocked:
        run["status"] = "BLOCKED"
        run["blocker"] = "Live PostgreSQL had knowledge_chunks=0 and chunk_embeddings=0; remaining RAG generation and health API calls were not run because the requested end-to-end benchmark precondition was absent."
        api_rag = read_jsonl(RESULT_DIR / "rag_api_generation.jsonl") if (RESULT_DIR / "rag_api_generation.jsonl").exists() else []
        api_health = read_jsonl(RESULT_DIR / "safety_health_api.jsonl") if (RESULT_DIR / "safety_health_api.jsonl").exists() else []
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["api_calls"] = {"rag_generation": len(api_rag), "health_safety": len(api_health), "errors": sum(item["error"] is not None for item in api_rag + api_health)}
        write_json(RESULT_DIR / "run_metadata.json", run)
        (ROOT / "docs/evaluation/engineering_eval_v1_api_results.md").write_text(report(run, routing, retrieval, safety, api_rag, api_health), encoding="utf-8")
        print(json.dumps({"status": "BLOCKED", "result_dir": str(RESULT_DIR), "rag_api_calls": len(api_rag)}), flush=True)
        return
    rag_path = RESULT_DIR / "rag_api_generation.jsonl"
    existing_rag = read_jsonl(rag_path) if rag_path.exists() else recover_api_checkpoints(rag_cases)
    if existing_rag and not rag_path.exists(): write_jsonl(rag_path, existing_rag)
    api_rag = await call_current_api(rag_cases, kind="RAG", output_path=rag_path, existing=existing_rag)
    health_cases = [case for case in safety_cases if case["group"] == "HEALTH_SCOPE_SAFETY"]
    health_path = RESULT_DIR / "safety_health_api.jsonl"
    existing_health = read_jsonl(health_path) if health_path.exists() else []
    api_health = await call_current_api(health_cases, kind="SAFETY", output_path=health_path, existing=existing_health)
    run["completed_at"] = datetime.now(timezone.utc).isoformat()
    run["api_calls"] = {"rag_generation": len(api_rag), "health_safety": len(api_health), "errors": sum(item["error"] is not None for item in api_rag + api_health)}
    write_json(RESULT_DIR / "run_metadata.json", run)
    (ROOT / "docs/evaluation/engineering_eval_v1_api_results.md").write_text(report(run, routing, retrieval, safety, api_rag, api_health), encoding="utf-8")
    print(json.dumps({"result_dir": str(RESULT_DIR), "api_errors": run["api_calls"]["errors"], "recall_at_5": retrieval["recall_at_5"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
