"""Grade the frozen flexible-path acceptance answers with one predeclared judge.

The judge never receives expected tools, architecture labels, historical scores,
or hidden reasoning.  It sees only the query, evidence available during that
turn, visible final answer, and source metadata.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from config import settings

ROOT = Path(__file__).resolve().parents[4]
PROJECTION = ROOT / "evaluation/acceptance_vn/expected_channels.json"
AUDIT = ROOT / "evaluation/results/acceptance-case-audit/case_audit.jsonl"
PRIMARY = ROOT / "evaluation/results/acceptance-v2/outcome-c12-run1/full_pipeline.jsonl"
RECOVERY = ROOT / "evaluation/results/acceptance-v2/outcome-c12-timeout-recovery1/full_pipeline.jsonl"
RAG_EVIDENCE_RERUN = ROOT / "evaluation/results/acceptance-v2/outcome-c12-rag-evidence-rerun1/full_pipeline.jsonl"
OUT = ROOT / "evaluation/results/acceptance-v2/outcome-judge"
SUPPLEMENTAL_MODEL = "MiniMax-M2.7"
SUPPLEMENTAL_CONFIG_ID = "supplemental-minimax-m2-7-v1"

RUBRIC = """Grade one Vietnamese health/nutrition assistant answer strictly from the supplied evidence.
Return JSON only with relevance PASS or FAIL, faithfulness PASS or FAIL,
unsupported_claims nonnegative integer, provenance PASS or FAIL or NOT_APPLICABLE,
and no_evidence_handling PASS or FAIL or NOT_APPLICABLE. Relevance means directly
answering the request. Faithfulness means material factual health/nutrition claims
are supported by supplied tool/retrieval evidence or deterministic application state.
Unsupported claims are material factual assertions not supported by that evidence.
Provenance passes only when attributions correspond to supplied evidence. If adequate
evidence is unavailable, no-evidence handling passes only when the answer does not
invent an authoritative fact. Do not provide explanations, medical advice, or reasoning."""

SUPPLEMENTAL_RUBRIC = RUBRIC + """
Also return short_reason: one concise evidence-based sentence. Do not return
chain-of-thought, hidden reasoning, or text outside the JSON object."""
SUPPLEMENTAL_OUTPUT_SCHEMA = {
    "relevance": "PASS|FAIL",
    "faithfulness": "PASS|FAIL",
    "unsupported_claims": "integer >= 0",
    "provenance": "PASS|FAIL|NOT_APPLICABLE",
    "no_evidence_handling": "PASS|FAIL|NOT_APPLICABLE",
    "short_reason": "one concise evidence-based sentence",
}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _tool_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for event in row.get("events", []):
        trace = event.get("event") if event.get("type") == "debug_trace" else None
        if not isinstance(trace, dict) or trace.get("operation") not in {
            "TOOL_RESULT",
            "CONTEXT_RAG_EVIDENCE",
        }:
            continue
        payload = trace.get("sanitized_payload")
        if not isinstance(payload, dict):
            continue
        item: dict[str, Any] = {"tool": payload.get("name"), "ok": payload.get("ok")}
        if "acceptance_evidence" in payload:
            item["result"] = payload["acceptance_evidence"]
        evidence.append(item)
    return evidence


def _is_homogeneous_run(*, input_artifact: Path | None, judge_model: str | None, rejudge_all: bool) -> bool:
    """Whether a run must retain its explicit single-model config on resume."""

    return bool(rejudge_all or (input_artifact is not None and judge_model))


def _load_input_artifact(path: Path, *, expected_case_count: int | None) -> dict[str, dict[str, Any]]:
    """Validate an explicit full or partial artifact without inventing rows."""
    artifact = path / "full_pipeline.jsonl" if path.is_dir() else path
    rows = _rows(artifact)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise RuntimeError("OUTCOME_INPUT_CASE_ID_INVALID")
        if case_id in by_id:
            raise RuntimeError("OUTCOME_INPUT_DUPLICATE_CASE_ID:" + case_id)
        if not isinstance(row.get("query"), str) or not str(row.get("response") or "").strip():
            raise RuntimeError("OUTCOME_INPUT_UNJUDGEABLE_RECORD:" + case_id)
        if not isinstance(row.get("events"), list):
            raise RuntimeError("OUTCOME_INPUT_EVIDENCE_ENVELOPE_MISSING:" + case_id)
        by_id[case_id] = row
    if not by_id:
        raise RuntimeError("OUTCOME_INPUT_EMPTY")
    if expected_case_count is not None and len(by_id) != expected_case_count:
        raise RuntimeError(f"OUTCOME_INPUT_CASE_COUNT_MISMATCH:{len(by_id)}!={expected_case_count}")
    return by_id


def _without_hidden_reasoning(content: str) -> str:
    """Discard provider-emitted reasoning before parsing or persisting a grade."""

    return re.sub(r"<think>.*?</think>\s*", "", content, flags=re.I | re.S).strip()


def _parse(content: str, *, require_short_reason: bool = False) -> dict[str, Any]:
    content = _without_hidden_reasoning(content)
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(stripped[start:])
    if not isinstance(value, dict):
        raise ValueError("JUDGE_RESPONSE_NOT_OBJECT")
    relevance = value.get("relevance")
    faithfulness = value.get("faithfulness")
    provenance = value.get("provenance")
    no_evidence = value.get("no_evidence_handling")
    unsupported = value.get("unsupported_claims")
    if relevance not in {"PASS", "FAIL"} or faithfulness not in {"PASS", "FAIL"}:
        raise ValueError("JUDGE_RESPONSE_INVALID_BINARY_FIELDS")
    if provenance not in {"PASS", "FAIL", "NOT_APPLICABLE"}:
        raise ValueError("JUDGE_RESPONSE_INVALID_PROVENANCE")
    if no_evidence not in {"PASS", "FAIL", "NOT_APPLICABLE"}:
        raise ValueError("JUDGE_RESPONSE_INVALID_NO_EVIDENCE")
    if not isinstance(unsupported, int) or unsupported < 0:
        raise ValueError("JUDGE_RESPONSE_INVALID_UNSUPPORTED_COUNT")
    result = {"relevance": relevance, "faithfulness": faithfulness, "unsupported_claims": unsupported, "provenance": provenance, "no_evidence_handling": no_evidence}
    if require_short_reason:
        short_reason = value.get("short_reason")
        if not isinstance(short_reason, str) or not short_reason.strip() or len(short_reason.strip()) > 500:
            raise ValueError("JUDGE_RESPONSE_INVALID_SHORT_REASON")
        result["short_reason"] = short_reason.strip()
    return result


async def _grade(
    client: AsyncOpenAI,
    row: dict[str, Any],
    *,
    model: str,
    rubric: str,
    require_short_reason: bool,
    config_id: str | None,
) -> dict[str, Any]:
    prompt = {
        "rubric": rubric,
        "query": row["query"],
        "evidence_available_during_turn": _tool_evidence(row),
        "final_answer": row.get("response") or "",
    }
    response = await client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=1024 if require_short_reason else None,
        messages=[
            {"role": "system", "content": "Return only the requested JSON object. Do not reveal reasoning."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    content = response.choices[0].message.content or ""
    judged = {"case_id": row["case_id"], "grade": _parse(content, require_short_reason=require_short_reason)}
    if config_id is not None:
        judged.update({"judge_model": model, "judge_config_id": config_id})
    return judged


def _freeze_supplemental_config(output_dir: Path) -> dict[str, Any]:
    config = {
        "ANSWER_JUDGE_CONFIG_ID": SUPPLEMENTAL_CONFIG_ID,
        "ANSWER_JUDGE_PROVIDER": "openai_compatible",
        "ANSWER_JUDGE_MODEL": SUPPLEMENTAL_MODEL,
        "ANSWER_JUDGE_TEMPERATURE": 0,
        "ANSWER_JUDGE_RUBRIC": SUPPLEMENTAL_RUBRIC,
        "ANSWER_JUDGE_RUBRIC_SHA256": hashlib.sha256(SUPPLEMENTAL_RUBRIC.encode("utf-8")).hexdigest(),
        "ANSWER_JUDGE_OUTPUT_SCHEMA": SUPPLEMENTAL_OUTPUT_SCHEMA,
        "ANSWER_JUDGE_MIXED_MODELS": "YES",
        "hidden_reasoning_policy": "Discard complete <think> blocks before parsing; never persist raw provider content.",
        "scope": "Only the 15 previously ungraded frozen flexible-path outcome cases.",
    }
    path = output_dir / "supplemental_judge_config.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != config:
        raise RuntimeError("SUPPLEMENTAL_ANSWER_JUDGE_CONFIGURATION_ALREADY_FROZEN_DIFFERENTLY")
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config


def _historical_answers() -> dict[str, dict[str, Any]]:
    """Return the historical, mixed-run answer set without modifying it."""

    primary = {row["case_id"]: row for row in _rows(PRIMARY)}
    primary.update({row["case_id"]: row for row in _rows(RECOVERY)})
    if RAG_EVIDENCE_RERUN.exists():
        primary.update({row["case_id"]: row for row in _rows(RAG_EVIDENCE_RERUN)})
    return primary


def _outcome_oracles() -> dict[str, dict[str, Any]]:
    """Load the fixed applicability oracle; it is never inferred from grades."""

    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))["projection"]
    audited = {
        row["case_id"]
        for row in _rows(AUDIT)
        if bool(row.get("path_oracle_may_be_too_strict"))
    }
    result = {row["case_id"]: row for row in projection if row["case_id"] in audited}
    if len(result) != 55 or set(result) != audited:
        raise RuntimeError("OUTCOME_APPLICABILITY_ORACLE_IDENTITY_MISMATCH")
    return result


def _write_metrics(
    *,
    output_dir: Path,
    answers: dict[str, dict[str, Any]],
    judged_rows: list[dict[str, Any]],
    historical: bool,
) -> dict[str, Any]:
    """Write denominator-correct outcome metrics without changing a judge grade."""

    latest = {row["case_id"]: row for row in judged_rows if "case_id" in row}
    grades = {
        case_id: row["grade"]
        for case_id, row in latest.items()
        if case_id in answers and isinstance(row.get("grade"), dict)
    }
    if set(grades) != set(answers):
        raise RuntimeError("OUTCOME_JUDGE_SET_INCOMPLETE")
    # Keep the append-only checkpoint log intact, while exposing one stable
    # latest judgment per frozen case for reporting and reproduction.
    canonical = [latest[case_id] for case_id in answers]
    (output_dir / "judgments_canonical.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in canonical),
        encoding="utf-8",
    )
    all_oracles = _outcome_oracles()
    oracle = {case_id: all_oracles[case_id] for case_id in answers if case_id in all_oracles}
    if set(oracle) != set(answers):
        raise RuntimeError("OUTCOME_METRIC_ORACLE_SET_MISMATCH")
    provenance_applicable = [
        grade for grade in grades.values()
        if grade["provenance"] != "NOT_APPLICABLE"
    ]
    no_evidence_applicable_ids = [
        case_id for case_id, rule in oracle.items()
        if rule["expected_channel"] == "NO_EVIDENCE"
    ]
    no_evidence_correct = sum(
        grades[case_id]["no_evidence_handling"] == "PASS"
        for case_id in no_evidence_applicable_ids
    )
    metrics = {
        "ANSWER_QUALITY_CASES": len(answers),
        "RELEVANCE_PASS": sum(grade["relevance"] == "PASS" for grade in grades.values()),
        "FAITHFULNESS_PASS": sum(grade["faithfulness"] == "PASS" for grade in grades.values()),
        "UNSUPPORTED_CLAIM_CASES": sum(grade["unsupported_claims"] > 0 for grade in grades.values()),
        "UNSUPPORTED_CLAIM_TOTAL": sum(grade["unsupported_claims"] for grade in grades.values()),
        "PROVENANCE_APPLICABLE": len(provenance_applicable),
        "PROVENANCE_CORRECT": sum(grade["provenance"] == "PASS" for grade in provenance_applicable),
        "NO_EVIDENCE_APPLICABLE": len(no_evidence_applicable_ids),
        "NO_EVIDENCE_CORRECT": no_evidence_correct,
        "NO_EVIDENCE_ACCURACY": (
            no_evidence_correct / len(no_evidence_applicable_ids)
            if no_evidence_applicable_ids else None
        ),
        "METRIC_DENOMINATOR_SOURCE": "frozen expected_channels projection, not judge labels",
        "HISTORICAL_EVIDENCE_CAPTURE_DEFECT": "YES" if historical else "NO",
    }
    metrics["RELEVANCE_RATE"] = metrics["RELEVANCE_PASS"] / len(answers)
    metrics["FAITHFULNESS_RATE"] = metrics["FAITHFULNESS_PASS"] / len(answers)
    metrics["UNSUPPORTED_CLAIM_CASE_RATE"] = metrics["UNSUPPORTED_CLAIM_CASES"] / len(answers)
    metrics["PROVENANCE_CORRECTNESS"] = (
        metrics["PROVENANCE_CORRECT"] / metrics["PROVENANCE_APPLICABLE"]
        if metrics["PROVENANCE_APPLICABLE"] else None
    )
    (output_dir / "outcome_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


async def main_async(
    execute: bool,
    forced_case_ids: set[str],
    supplemental_missing: bool,
    *,
    outcome_result_dir: Path | None,
    input_artifact: Path | None,
    expected_case_count: int | None,
    recovery_result_dirs: list[Path],
    output_dir: Path,
    judge_model: str | None,
    rejudge_all: bool,
    summarize_only: bool,
) -> int:
    if input_artifact is not None:
        primary = _load_input_artifact(input_artifact, expected_case_count=expected_case_count)
    elif outcome_result_dir is not None:
        primary = {
            row["case_id"]: row
            for row in _rows(outcome_result_dir / "full_pipeline.jsonl")
        }
        for recovery_dir in recovery_result_dirs:
            recovery_rows = _rows(recovery_dir / "full_pipeline.jsonl")
            for row in recovery_rows:
                if row.get("case_id") not in primary:
                    raise RuntimeError("OUTCOME_RECOVERY_CASE_ID_NOT_IN_PRIMARY")
                primary[row["case_id"]] = row
    else:
        primary = _historical_answers()
    if input_artifact is None and (len(primary) != 55 or any(not str(row.get("response") or "").strip() for row in primary.values())):
        raise RuntimeError("OUTCOME_FINAL_ANSWER_SET_INCOMPLETE")
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_model = judge_model or settings.llm_model
    # An explicit artifact plus an explicitly pinned judge model is a new
    # homogeneous run.  This keeps its checkpoint resumable: a later command
    # can grade only missing rows without silently falling back to the legacy
    # generation-model config.
    homogeneous = _is_homogeneous_run(
        input_artifact=input_artifact,
        judge_model=judge_model,
        rejudge_all=rejudge_all,
    )
    if supplemental_missing and (outcome_result_dir is not None or judge_model or rejudge_all):
        raise RuntimeError("SUPPLEMENTAL_MISSING_IS_HISTORICAL_ONLY")
    if homogeneous:
        if output_dir == OUT:
            raise RuntimeError("HOMOGENEOUS_JUDGE_REQUIRES_SEPARATE_OUTPUT_DIR")
        if not judge_model:
            raise RuntimeError("HOMOGENEOUS_JUDGE_MODEL_REQUIRED")
        config = {
            "ANSWER_JUDGE_PROVIDER": "openai_compatible",
            "ANSWER_JUDGE_MODEL": selected_model,
            "ANSWER_JUDGE_TEMPERATURE": 0,
            "ANSWER_JUDGE_RUBRIC": RUBRIC,
            "ANSWER_JUDGE_RUBRIC_SHA256": hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest(),
            "ANSWER_JUDGE_MIXED_MODELS": "NO",
            "methodological_limitation": "All records in this explicit frozen artifact are re-judged with one configured model.",
        }
    else:
        # Retain the exact historical config shape so a plumbing fix cannot
        # rewrite or relabel already collected mixed-model evidence.
        config = {
            "ANSWER_JUDGE_PROVIDER": "openai_compatible",
            "ANSWER_JUDGE_MODEL": settings.llm_model,
            "ANSWER_JUDGE_TEMPERATURE": 0,
            "ANSWER_JUDGE_RUBRIC": RUBRIC,
            "ANSWER_JUDGE_RUBRIC_SHA256": hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest(),
            "methodological_limitation": "Judge uses the same configured provider/model family as generation because no independently configured judge model was available.",
        }
    config_path = output_dir / "judge_config.json"
    if config_path.exists() and json.loads(config_path.read_text(encoding="utf-8")) != config:
        raise RuntimeError("ANSWER_JUDGE_CONFIGURATION_ALREADY_FROZEN_DIFFERENTLY")
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = output_dir / "judgments.jsonl"
    prior = {row["case_id"]: row for row in _rows(output)} if output.exists() else {}
    supplemental_config: dict[str, Any] | None = None
    if supplemental_missing:
        forced_case_ids = {case_id for case_id, row in prior.items() if "grade" not in row}
        if not 1 <= len(forced_case_ids) <= 15:
            raise RuntimeError(f"SUPPLEMENTAL_JUDGE_REMAINING_CASE_COUNT_INVALID:{len(forced_case_ids)}")
        supplemental_config = _freeze_supplemental_config(output_dir)
    if not execute:
        if summarize_only:
            output = output_dir / "judgments.jsonl"
            metrics = _write_metrics(
                output_dir=output_dir,
                answers=primary,
                judged_rows=_rows(output) if output.exists() else [],
                historical=input_artifact is None and outcome_result_dir is None,
            )
            print(json.dumps({"status": "METRICS_SUMMARIZED", **metrics}, ensure_ascii=False))
            return 0
        print(json.dumps({"status": "SUPPLEMENTAL_JUDGE_CONFIG_FROZEN" if supplemental_config else "JUDGE_CONFIG_FROZEN", "cases": len(forced_case_ids) if supplemental_config else len(primary)}, ensure_ascii=False))
        return 0
    missing = forced_case_ids - set(primary)
    if missing:
        raise RuntimeError("UNKNOWN_OUTCOME_CASE_IDS:" + ",".join(sorted(missing)))
    client = AsyncOpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key or "dummy-key", max_retries=0)
    try:
        with output.open("a", encoding="utf-8") as handle:
            for row in primary.values():
                if forced_case_ids and row["case_id"] not in forced_case_ids:
                    continue
                if (
                    not rejudge_all
                    and not forced_case_ids
                    and row["case_id"] in prior
                    and "grade" in prior[row["case_id"]]
                ):
                    continue
                try:
                    judged = await _grade(
                        client,
                        row,
                        model=SUPPLEMENTAL_MODEL if supplemental_config else selected_model,
                        rubric=SUPPLEMENTAL_RUBRIC if supplemental_config else RUBRIC,
                        require_short_reason=bool(supplemental_config),
                        config_id=SUPPLEMENTAL_CONFIG_ID if supplemental_config else None,
                    )
                except Exception as exc:
                    judged = {"case_id": row["case_id"], "judge_error": type(exc).__name__}
                    if supplemental_config:
                        judged.update({"judge_model": SUPPLEMENTAL_MODEL, "judge_config_id": SUPPLEMENTAL_CONFIG_ID})
                handle.write(json.dumps(judged, ensure_ascii=False) + "\n")
                handle.flush()
    finally:
        await client.close()
    completed_rows = _rows(output)
    completed_case_ids = {
        row["case_id"] for row in completed_rows if isinstance(row.get("grade"), dict)
    }
    if completed_case_ids == set(primary):
        metrics = _write_metrics(
            output_dir=output_dir,
            answers=primary,
            judged_rows=completed_rows,
            historical=input_artifact is None and outcome_result_dir is None,
        )
        print(json.dumps({"status": "JUDGED", "cases": len(completed_rows), **metrics}, ensure_ascii=False))
    else:
        print(json.dumps({
            "status": "JUDGE_CHECKPOINTED",
            "graded_cases": len(completed_case_ids),
            "remaining_cases": len(set(primary) - completed_case_ids),
        }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case-ids", default="", help="comma-separated existing outcome case IDs to rejudge")
    parser.add_argument("--supplemental-missing", action="store_true", help="grade exactly the 15 latest rows without a valid grade using the frozen supplemental config")
    parser.add_argument("--outcome-result-dir", type=Path, help="one complete new 55-case outcome artifact to judge")
    parser.add_argument("--input", type=Path, help="explicit full_pipeline.jsonl or artifact directory; supports a subset")
    parser.add_argument("--mode", choices=("full", "subset"), default="full")
    parser.add_argument("--expected-case-count", type=int, help="required unique records for explicit input")
    parser.add_argument("--recovery-result-dir", type=Path, action="append", default=[], help="completed retry artifact whose rows replace matching primary timeouts")
    parser.add_argument("--output-dir", type=Path, default=OUT, help="separate directory for this judge run")
    parser.add_argument("--judge-model", help="one predeclared model for a new homogeneous judge run")
    parser.add_argument("--rejudge-all", action="store_true", help="grade all 55 answers even when the output directory already has rows")
    parser.add_argument("--summarize-only", action="store_true", help="write denominator-correct metrics from an already complete judge output")
    args = parser.parse_args()
    forced_case_ids = {case_id.strip() for case_id in args.case_ids.split(",") if case_id.strip()}
    if args.supplemental_missing and forced_case_ids:
        raise RuntimeError("SUPPLEMENTAL_MISSING_CANNOT_COMBINE_WITH_CASE_IDS")
    if args.input and args.outcome_result_dir:
        raise RuntimeError("INPUT_CANNOT_COMBINE_WITH_OUTCOME_RESULT_DIR")
    if args.mode == "full" and args.input and args.expected_case_count not in {None, 55}:
        raise RuntimeError("FULL_MODE_REQUIRES_55_CASES")
    if args.mode == "subset" and not args.input:
        raise RuntimeError("SUBSET_MODE_REQUIRES_INPUT")
    return asyncio.run(main_async(
        args.execute,
        forced_case_ids,
        args.supplemental_missing,
        outcome_result_dir=args.outcome_result_dir.resolve() if args.outcome_result_dir else None,
        input_artifact=args.input.resolve() if args.input else None,
        expected_case_count=(args.expected_case_count or (55 if args.mode == "full" and args.input else None)),
        recovery_result_dirs=[path.resolve() for path in args.recovery_result_dir],
        output_dir=args.output_dir.resolve(),
        judge_model=args.judge_model,
        rejudge_all=args.rejudge_all,
        summarize_only=args.summarize_only,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
