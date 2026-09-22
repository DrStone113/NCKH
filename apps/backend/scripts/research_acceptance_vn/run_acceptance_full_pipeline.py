"""Run frozen acceptance cases against an isolated application server.

The runner supports the Acceptance V2 split without creating any new case
corpus: architecture cases are selected from the read-only case audit, while
outcome cases retain path flexibility.  It records only user-visible output,
redacted debug events, and the explicitly enabled isolated-harness evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jwt
import websockets

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings

ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "evaluation" / "acceptance_vn" / "cases.jsonl"
PROJECTION = ROOT / "evaluation" / "acceptance_vn" / "expected_channels.json"
RUBRIC = ROOT / "evaluation" / "acceptance_vn" / "grading_rubric_v1.json"
AUDIT = ROOT / "evaluation" / "results" / "acceptance-case-audit" / "case_audit.jsonl"
RESULT_DIR = ROOT / "evaluation" / "results" / "acceptance-v2"
VERSION = "offline-acceptance-vn-4954"
CORPUS_HASH = "f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a"
VALID_CONCURRENCY = (1, 2, 4, 8, 12, 16)
CASE_TOTAL_TIMEOUT_SECONDS = 120


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _grounding_control_flow_metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate application-owned grounding lifecycle traces per turn."""

    required = validator_called = direct = after_repair = fallback = capture_missing = bypass = 0
    final_states = {"VALIDATED_DIRECT", "VALIDATED_AFTER_REPAIR", "GROUNDING_FALLBACK"}
    for row in rows:
        traces = [
            event.get("event")
            for event in row.get("events", [])
            if event.get("type") == "debug_trace" and isinstance(event.get("event"), dict)
        ]
        activation = next((trace for trace in traces if trace.get("operation") == "GROUNDING_ACTIVATION"), None)
        activation_payload = activation.get("sanitized_payload") if isinstance(activation, dict) else {}
        if not isinstance(activation_payload, dict) or not activation_payload.get("grounding_required"):
            continue
        required += 1
        validations = [trace for trace in traces if trace.get("operation") == "GROUNDING_VALIDATION"]
        if any(isinstance(trace.get("sanitized_payload"), dict) and trace["sanitized_payload"].get("validator_called") for trace in validations):
            validator_called += 1
        captures = [trace for trace in traces if trace.get("operation") == "GROUNDING_EVIDENCE_CAPTURE"]
        if not any(isinstance(trace.get("sanitized_payload"), dict) and trace["sanitized_payload"].get("evidence_capture_ok") for trace in captures):
            capture_missing += 1
        states = {trace.get("operation") for trace in traces if trace.get("operation") in final_states}
        direct += int("VALIDATED_DIRECT" in states)
        after_repair += int("VALIDATED_AFTER_REPAIR" in states)
        fallback += int("GROUNDING_FALLBACK" in states)
        if len(states) != 1 or not validations:
            bypass += 1
    return {
        "GROUNDING_REQUIRED_TURNS": required,
        "VALIDATOR_CALLED_TURNS": validator_called,
        "VALIDATED_DIRECT": direct,
        "VALIDATED_AFTER_REPAIR": after_repair,
        "GROUNDING_FALLBACK": fallback,
        "GROUNDING_BYPASS_COUNT": bypass,
        "EVIDENCE_CAPTURE_MISSING": capture_missing,
    }


def _select_cases(group: str, case_ids: set[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = _rows(CASES)
    audit = _rows(AUDIT)
    by_id = {str(row["case_id"]): row for row in audit}
    if len(cases) != 200 or len(by_id) != len(cases) or set(by_id) != {row["case_id"] for row in cases}:
        raise RuntimeError("ACCEPTANCE_V2_AUDIT_CASE_IDENTITY_MISMATCH")
    architecture = [row for row in cases if bool(by_id[row["case_id"]].get("architecture_requirement"))]
    outcome = [row for row in cases if bool(by_id[row["case_id"]].get("path_oracle_may_be_too_strict"))]
    if len(architecture) != 145 or len(outcome) != 55 or {x["case_id"] for x in architecture} & {x["case_id"] for x in outcome}:
        raise RuntimeError("ACCEPTANCE_V2_AUDIT_SPLIT_INVALID")
    if group == "architecture":
        selected = architecture
    elif group == "outcome":
        selected = outcome
    elif group == "all":
        selected = cases
    else:
        selected = None
    if selected is not None:
        if case_ids is not None:
            selected_ids = {case["case_id"] for case in selected}
            if not case_ids or not case_ids <= selected_ids:
                raise RuntimeError("ACCEPTANCE_V2_SUBSET_CASE_IDS_NOT_IN_SELECTED_GROUP")
            selected = [case for case in selected if case["case_id"] in case_ids]
        return selected, audit
    # This is a fixed selection derived from existing audit/case metadata. It
    # deliberately samples the required execution categories, never authors a
    # new benchmark row, and is reused verbatim across concurrency trials.
    wanted = (
        ("FOOD_TOOL", None), ("DISH_TOOL", None), ("NUTRITION_KNOWLEDGE", None),
        ("MICRONUTRIENT", None), ("EXERCISE", None), ("RAG_REQUIRED", None),
        ("RAG_FORBIDDEN", None), ("NO_EVIDENCE", None), ("WRITE_OR_READ", None),
    )
    projection = {row["case_id"]: row for row in _load_json(PROJECTION)["projection"]}
    chosen: list[dict[str, Any]] = []
    for category, _ in wanted:
        candidates = []
        for case in cases:
            rule = projection[case["case_id"]]
            domain = str(case.get("report_domain") or case.get("domain") or "")
            matches = {
                "FOOD_TOOL": rule["expected_channel"] == "FOOD_TOOL",
                "DISH_TOOL": rule["expected_channel"] == "DISH_TOOL",
                "NUTRITION_KNOWLEDGE": domain in {"VN_NORMATIVE", "VN_NUTRIENT_REQUIREMENT", "GLOBAL_HEALTH"},
                "MICRONUTRIENT": domain == "VN_MICRONUTRIENT",
                "EXERCISE": domain == "EXERCISE_CATALOG",
                "RAG_REQUIRED": bool(rule["rag_required"]),
                "RAG_FORBIDDEN": bool(rule["rag_forbidden"]),
                "NO_EVIDENCE": rule["expected_channel"] == "NO_EVIDENCE",
                # The acceptance corpus has no safe isolated write/read row.
                # An explicit read path is included and the limitation is
                # retained in metadata instead of fabricating a write case.
                "WRITE_OR_READ": bool(rule["expected_tool_names"]),
            }[category]
            if matches and case not in chosen:
                candidates.append(case)
        if not candidates:
            raise RuntimeError(f"ACCEPTANCE_V2_REPRESENTATIVE_COVERAGE_MISSING:{category}")
        chosen.append(candidates[0])
    if case_ids is not None:
        raise RuntimeError("ACCEPTANCE_V2_SUBSET_NOT_SUPPORTED_FOR_REPRESENTATIVE")
    return chosen, audit


def _preflight(cases: list[dict[str, Any]], audit: list[dict[str, Any]], group: str) -> dict[str, Any]:
    projection = _load_json(PROJECTION)
    rubric = _load_json(RUBRIC)
    if projection.get("case_count") != 200 or projection.get("case_file_sha256") != _sha(CASES):
        raise RuntimeError("ACCEPTANCE_PROJECTION_CASE_HASH_MISMATCH")
    if not rubric.get("prompt_sha256"):
        raise RuntimeError("ACCEPTANCE_RUBRIC_NOT_FROZEN")
    return {
        "ACCEPTANCE_MODEL": "V2_FOUR_GROUPS",
        "CORPUS_VERSION": VERSION,
        "CORPUS_HASH": CORPUS_HASH,
        "CASE_GROUP": group,
        "SELECTED_CASES": len(cases),
        "ARCHITECTURE_COMPLIANCE_CASES": 145,
        "OUTCOME_QUALITY_CASES": 55,
        "CASE_AUDIT_SHA256": _sha(AUDIT),
        "EXPECTED_CHANNEL_PROJECTION_SHA256": _sha(PROJECTION),
        "GRADING_RUBRIC_SHA256": _sha(RUBRIC),
        "PRODUCTION_RAG_TABLES_CHANGED": "NO",
        "PRODUCTION_RUNTIME_DEFAULT_CHANGED": "NO",
        "ACCEPTANCE_CORPUS_INJECTED_BY_HARNESS": "YES",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _test_principal_token() -> str:
    if settings.app_environment.strip().lower() not in {"development", "test"}:
        raise RuntimeError("QUALIFICATION_LOCAL_PRINCIPAL_REQUIRES_DEVELOPMENT_OR_TEST")
    now = int(time.time())
    return jwt.encode(
        {"sub": "acceptance-qualification-runner", "roles": ["developer"], "iat": now, "exp": now + 3600},
        settings.jwt_secret,
        algorithm="HS256",
    )


def _error_from_exception(exc: Exception) -> dict[str, str]:
    name = type(exc).__name__
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        code = "TIMEOUT"
    elif "Connection" in name or "InvalidStatus" in name:
        code = "CONNECTION_RESET"
    else:
        code = "TRANSPORT_OR_APPLICATION_ERROR"
    return {"code": code, "type": name}


async def _run_case_unbounded(case: dict[str, Any], *, ws_url: str, token: str, group: str) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    session_id, turn_id = str(uuid.uuid4()), str(uuid.uuid4())
    events: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    error: dict[str, Any] | None = None
    client_tool_requested = False
    try:
        async with websockets.connect(
            f"{ws_url}?session_id={session_id}", subprotocols=["health-auth-v1", f"auth.{token}"],
            open_timeout=15, close_timeout=5, max_size=2_000_000,
        ) as socket:
            await socket.send(json.dumps({
                "type": "chat", "session_id": session_id, "user_id": "acceptance-qualification-runner",
                "turn_id": turn_id, "message": case["query"],
                "user_context": {"age": 25, "height": 170, "weight": 65, "activity_level": "moderate", "health_goal": "maintain"},
            }, ensure_ascii=False))
            while True:
                message = json.loads(await asyncio.wait_for(socket.recv(), timeout=90))
                kind = message.get("type")
                if kind == "token":
                    answer_parts.append(str(message.get("content") or ""))
                elif kind == "debug_trace":
                    events.append({"type": kind, "event": message.get("event")})
                elif kind in {"status", "public_trace", "action_state"}:
                    events.append({"type": kind, "value": message.get("trace") or message.get("state") or message.get("content")})
                elif kind == "tool_call":
                    client_tool_requested = True
                    events.append({"type": kind, "name": message.get("name"), "arguments": message.get("arguments")})
                    error = {"code": "CLIENT_TOOL_REQUIRES_REAL_FLUTTER_EXECUTOR"}
                    break
                elif kind == "error":
                    error = {"code": message.get("code"), "message": message.get("message")}
                    break
                elif kind == "done":
                    answer = str(message.get("full_response") or "")
                    if answer:
                        answer_parts = [answer]
                    events.append({"type": kind, "structured": message.get("structured"), "public_trace": message.get("public_trace")})
                    break
    except Exception as exc:
        error = _error_from_exception(exc)
    return {
        "case_id": case["case_id"], "query": case["query"], "case_group": group,
        "response": "".join(answer_parts), "events": events, "error": error,
        "client_tool_requested": client_tool_requested, "started_at": started_at,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "provider": "openai_compatible", "requested_model": settings.llm_model,
        "auth_mode": "LOCAL_DEVELOPMENT_TEST_PRINCIPAL_NOT_E2E",
    }


async def _run_case(case: dict[str, Any], *, ws_url: str, token: str, group: str) -> dict[str, Any]:
    """Bound a whole turn; visible progress frames must not reset the deadline forever."""

    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        return await asyncio.wait_for(
            _run_case_unbounded(case, ws_url=ws_url, token=token, group=group),
            timeout=CASE_TOTAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            "case_id": case["case_id"], "query": case["query"], "case_group": group,
            "response": "", "events": [], "error": {"code": "TIMEOUT", "scope": "CASE_TOTAL_DEADLINE"},
            "client_tool_requested": False, "started_at": started_at,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "provider": "openai_compatible", "requested_model": settings.llm_model,
            "auth_mode": "LOCAL_DEVELOPMENT_TEST_PRINCIPAL_NOT_E2E",
        }


async def _execute(cases: list[dict[str, Any]], *, concurrency: int, result_dir: Path, ws_url: str, group: str) -> int:
    if concurrency not in VALID_CONCURRENCY:
        raise RuntimeError("QUALIFICATION_CONCURRENCY_MUST_BE_1_2_4_8_12_OR_16")
    token = _test_principal_token()
    output = result_dir / "full_pipeline.jsonl"
    prior = _rows(output) if output.exists() else []
    completed = {row["case_id"] for row in prior}
    if not completed <= {case["case_id"] for case in cases} or len(completed) != len(prior):
        raise RuntimeError("ACCEPTANCE_V2_CHECKPOINT_CASE_IDENTITY_MISMATCH")
    remaining = [case for case in cases if case["case_id"] not in completed]
    with output.open("a", encoding="utf-8") as handle:
        for start in range(0, len(remaining), concurrency):
            batch = remaining[start:start + concurrency]
            rows = await asyncio.gather(*(_run_case(case, ws_url=ws_url, token=token, group=group) for case in batch))
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
            print(f"ACCEPTANCE_V2 {start + len(batch)}/{len(remaining)}", flush=True)
    return len(prior) + len(remaining)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case-group", choices=("architecture", "outcome", "all", "representative"), default="all")
    parser.add_argument("--case-ids", help="comma-separated existing case IDs; only valid for architecture/outcome/all")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only these existing frozen case IDs within the selected group; repeat as needed.",
    )
    parser.add_argument("--concurrency", type=int, default=4, choices=VALID_CONCURRENCY)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8091/chat/stream")
    parser.add_argument("--result-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    requested_case_ids = {item.strip() for item in (args.case_ids or "").split(",") if item.strip()} or None
    cases, audit = _select_cases(args.case_group, requested_case_ids)
    if args.case_id:
        requested = set(args.case_id)
        available = {case["case_id"] for case in cases}
        missing = sorted(requested - available)
        if missing:
            raise RuntimeError(
                "AFFECTED_SUBSET_CASE_NOT_IN_SELECTED_GROUP:" + ",".join(missing)
            )
        cases = [case for case in cases if case["case_id"] in requested]
    metadata = _preflight(cases, audit, args.case_group)
    if args.case_id:
        metadata["AFFECTED_SUBSET_CASE_IDS"] = [case["case_id"] for case in cases]
    metadata.update({"generation_provider_configured": bool(settings.openai_api_key), "generation_model": settings.llm_model, "CONCURRENCY": args.concurrency, "WS_URL": args.ws_url})
    if not args.execute:
        metadata.update({"GENERATION_STATUS": "PREFLIGHT_COMPLETE_NOT_EXECUTED", "FULL_PIPELINE_COMPLETE": "NO"})
    else:
        started = time.perf_counter()
        completed = asyncio.run(_execute(cases, concurrency=args.concurrency, result_dir=result_dir, ws_url=args.ws_url, group=args.case_group))
        metadata.update({
            "GENERATION_STATUS": "EXECUTED" if completed == len(cases) else "CHECKPOINT_INCOMPLETE",
            "FULL_PIPELINE_COMPLETE": "YES" if completed == len(cases) else "NO",
            "FULL_PIPELINE_CASES_COMPLETED": completed,
            "WALL_CLOCK_SECONDS": round(time.perf_counter() - started, 3),
            "AUTH_MODE": "LOCAL_DEVELOPMENT_TEST_PRINCIPAL_NOT_E2E",
        })
        metadata.update(_grounding_control_flow_metrics(_rows(result_dir / "full_pipeline.jsonl")))
    (result_dir / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
