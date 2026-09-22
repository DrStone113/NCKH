"""Deterministically summarize recorded acceptance pipeline execution.

The grader reads frozen cases, the frozen architecture projection, and captured
redacted application events.  It never calls a model and never alters results.
"""
from __future__ import annotations

import json
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "evaluation" / "acceptance_vn" / "cases.jsonl"
PROJECTION = ROOT / "evaluation" / "acceptance_vn" / "expected_channels.json"
OUT = ROOT / "evaluation" / "results" / "acceptance-full-pipeline-001"


def _tool_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for event in row.get("events", []):
        trace = event.get("event") if event.get("type") == "debug_trace" else None
        if not isinstance(trace, dict) or trace.get("operation") != "TOOL_CALL":
            continue
        payload = trace.get("sanitized_payload")
        if isinstance(payload, dict) and isinstance(payload.get("name"), str):
            names.append(payload["name"])
    return names


def _domain_name(case: dict[str, Any]) -> str:
    return str(case.get("report_domain") or case.get("domain") or "UNKNOWN")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, default=OUT)
    args = parser.parse_args()
    output_dir = args.result_dir.resolve()
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    expected = {row["case_id"]: row for row in projection["projection"]}
    result_file = output_dir / "full_pipeline.jsonl"
    rows = [json.loads(line) for line in result_file.read_text(encoding="utf-8").splitlines() if line] if result_file.exists() else []
    by_id = {row["case_id"]: row for row in rows}
    per_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    complete = len(rows) == len(cases) and len(by_id) == len(cases)
    for case in cases:
        row, rule = by_id.get(case["case_id"]), expected[case["case_id"]]
        tools = _tool_names(row) if row else []
        expected_tools = set(rule["expected_tool_names"])
        expected_called = bool(expected_tools & set(tools)) if expected_tools else None
        forbidden_rag = bool(rule["rag_forbidden"] and "query_rag" in tools)
        rag_required_used = bool(rule["rag_required"] and "query_rag" in tools)
        no_error = bool(row and not row.get("error") and not row.get("client_tool_requested"))
        if rule["expected_channel"] == "NO_EVIDENCE":
            channel_ok = no_error and bool(str(row.get("response") if row else "").strip()) and not tools
        elif expected_tools:
            channel_ok = no_error and bool(expected_called) and not forbidden_rag
        else:
            channel_ok = no_error and not forbidden_rag
        per_domain[_domain_name(case)].append({
            "channel_ok": channel_ok, "expected_called": expected_called,
            "forbidden_rag": forbidden_rag, "rag_required_used": rag_required_used,
        })
    flat = [item for items in per_domain.values() for item in items]
    expected_tool_rows = [item for item in flat if item["expected_called"] is not None]
    rag_required_rows = [item for item in flat if item["rag_required_used"] or any(False for _ in ())]
    # Determine required rows from projection directly; a false result is still counted.
    required_total = sum(rule["rag_required"] for rule in expected.values())
    required_used = sum(bool(by_id.get(case["case_id"]) and "query_rag" in _tool_names(by_id[case["case_id"]])) for case in cases if expected[case["case_id"]]["rag_required"])
    report_domains = {
        domain: {
            "cases": len(items),
            "channel_success": round(sum(item["channel_ok"] for item in items) / len(items), 4),
        }
        for domain, items in sorted(per_domain.items())
    }
    summary: dict[str, Any] = {
        "FULL_PIPELINE_CASES": len(cases),
        "FULL_PIPELINE_CASES_COMPLETED": len(rows),
        "FULL_PIPELINE_COMPLETE": complete,
        "EXPECTED_CHANNEL_ACCURACY": round(sum(item["channel_ok"] for item in flat) / len(flat), 4) if complete else "NOT_MEASURED",
        "EXPECTED_TOOL_CALLED_RATE": round(sum(bool(item["expected_called"]) for item in expected_tool_rows) / len(expected_tool_rows), 4) if complete and expected_tool_rows else "NOT_MEASURED",
        "FORBIDDEN_TOOL_CALLS": sum(item["forbidden_rag"] for item in flat) if complete else "NOT_MEASURED",
        "RAG_REQUIRED_AND_USED_RATE": round(required_used / required_total, 4) if complete and required_total else "NOT_MEASURED",
        "RAG_FORBIDDEN_BUT_USED_COUNT": sum(item["forbidden_rag"] for item in flat) if complete else "NOT_MEASURED",
        "NO_EVIDENCE_HANDLING_RATE": report_domains.get("NO_EVIDENCE", {}).get("channel_success", "NOT_MEASURED") if complete else "NOT_MEASURED",
        "FULL_PIPELINE_SUCCESS": round(sum(item["channel_ok"] for item in flat) / len(flat), 4) if complete else "NOT_MEASURED",
        "semantic_answer_grading": "NOT_MEASURED_PENDING_INDEPENDENT_JUDGE_CONFIGURATION",
        "by_domain": report_domains,
    }
    (output_dir / "full_pipeline_deterministic_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
