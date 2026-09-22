"""Isolated, checkpointed judging of the existing final 55 answers.

No generation, corpus, case, oracle, rubric, or historical judgment is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
sys.path.insert(0, str(BACKEND))
from config import settings  # noqa: E402
from scripts.research_acceptance_vn.grade_acceptance_outcomes import (  # noqa: E402
    RUBRIC,
    _outcome_oracles,
    _parse,
    _tool_evidence,
    _without_hidden_reasoning,
)

OUT = Path(__file__).resolve().parent
RESULTS = ROOT / "evaluation/results/acceptance-v2"
SOURCE_RUNS = (
    "outcome-answer-quality-c12-rerun2",
    "outcome-answer-quality-c12-timeout-recovery1",
    "outcome-answer-quality-c12-timeout-recovery2",
    "outcome-question-aware-affected16-canonical-avN175-recovery1",
    "outcome-final-hardening-3case-run3",
)
MODELS = {
    "judge_a": "cnb/grok-4.5",
    "judge_b": "vc/qwen3.8-max",
    "adjudicator": "zc/glm-5.3-flash",
}
FIELDS = ("relevance", "faithfulness", "unsupported_claims", "provenance", "no_evidence_handling")
METRICS = ("relevance", "faithfulness", "unsupported_claim_present", "provenance", "no_evidence_handling")
RUBRIC_SHA256 = hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest()
SCHEMA = {
    "relevance": "PASS|FAIL",
    "faithfulness": "PASS|FAIL",
    "unsupported_claims": "integer >= 0",
    "provenance": "PASS|FAIL|NOT_APPLICABLE",
    "no_evidence_handling": "PASS|FAIL|NOT_APPLICABLE",
    "short_reason": "one concise evidence-based sentence",
}
SYSTEM = "Return only the requested JSON object. Do not reveal reasoning. Include short_reason as one concise evidence-based sentence."


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_final_rows() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    selected: dict[str, dict[str, Any]] = {}
    source_info: dict[str, dict[str, str]] = {}
    for run in SOURCE_RUNS:
        artifact = RESULTS / run / "full_pipeline.jsonl"
        digest = _sha(artifact)
        for row in _rows(artifact):
            case_id = row.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise RuntimeError("INVALID_SOURCE_CASE_ID")
            selected[case_id] = row
            source_info[case_id] = {
                "path": artifact.relative_to(ROOT).as_posix(),
                "sha256": digest,
            }
    if len(selected) != 55:
        raise RuntimeError(f"FINAL_CASE_COUNT_INVALID:{len(selected)}")
    if any(not row.get("query") or not str(row.get("response") or "").strip() or not isinstance(row.get("events"), list) for row in selected.values()):
        raise RuntimeError("FINAL_CASE_RECORD_INCOMPLETE")
    return [selected[cid] for cid in sorted(selected)], source_info


def _input(row: dict[str, Any], dimensions: tuple[str, ...] = FIELDS) -> dict[str, Any]:
    return {
        "rubric": RUBRIC,
        "output_schema": {key: SCHEMA[key] for key in dimensions} | {"short_reason": SCHEMA["short_reason"]},
        "dimensions_to_grade": list(dimensions),
        "query": row["query"],
        "evidence_available_during_turn": _tool_evidence(row),
        "final_answer": row["response"],
    }


def _parse_dimensions(content: str, dimensions: tuple[str, ...]) -> dict[str, Any]:
    cleaned = _without_hidden_reasoning(content)
    if dimensions == FIELDS:
        value = _parse(cleaned, require_short_reason=True)
    else:
        value = json.loads(cleaned)
        if not isinstance(value, dict) or set(value) != set(dimensions) | {"short_reason"}:
            raise ValueError("ADJUDICATION_SCHEMA_MISMATCH")
        if not isinstance(value.get("short_reason"), str) or not value["short_reason"].strip() or len(value["short_reason"]) > 500:
            raise ValueError("ADJUDICATION_REASON_INVALID")
        for key in dimensions:
            check = value[key]
            if key in ("relevance", "faithfulness") and check not in ("PASS", "FAIL"):
                raise ValueError("ADJUDICATION_BINARY_INVALID")
            if key == "unsupported_claims" and (type(check) is not int or check < 0):
                raise ValueError("ADJUDICATION_COUNT_INVALID")
            if key in ("provenance", "no_evidence_handling") and check not in ("PASS", "FAIL", "NOT_APPLICABLE"):
                raise ValueError("ADJUDICATION_TERNARY_INVALID")
    if set(value) != set(dimensions) | {"short_reason"}:
        raise ValueError("JUDGE_EXTRA_OR_MISSING_FIELDS")
    return value


def _judge(client: OpenAI, row: dict[str, Any], model: str, dimensions: tuple[str, ...] = FIELDS) -> dict[str, Any]:
    prompt = _input(row, dimensions)
    raw = client.chat.completions.with_raw_response.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=4096,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
    )
    response = raw.parse()
    choice = response.choices[0]
    grade = _parse_dimensions(choice.message.content or "", dimensions)
    usage = response.usage.model_dump(exclude_none=True) if response.usage else None
    safe_headers = {key: value for key, value in raw.headers.items() if any(part in key.lower() for part in ("ratelimit", "quota", "balance", "retry-after"))}
    return {
        "case_id": row["case_id"],
        "model": model,
        "temperature": 0,
        "rubric_sha256": RUBRIC_SHA256,
        "dimensions": list(dimensions),
        "grade": grade,
        "input_sha256": hashlib.sha256(json.dumps(prompt, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "finish_reason": choice.finish_reason,
        "usage": usage,
        "quota_headers": safe_headers,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("PROVIDER_KEY_NOT_CONFIGURED")
    return OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key, max_retries=0, timeout=120)


def preflight() -> None:
    rows, source_info = _load_final_rows()
    config_paths = [
        RESULTS / "outcome-judge-question-aware-affected16-canonical-avN175-recovery1/judge_config.json",
        RESULTS / "outcome-judge-final-hardening-3case-run3/judge_config.json",
    ]
    for path in config_paths:
        frozen = json.loads(path.read_text(encoding="utf-8"))
        if frozen["ANSWER_JUDGE_RUBRIC"] != RUBRIC or frozen["ANSWER_JUDGE_RUBRIC_SHA256"] != RUBRIC_SHA256:
            raise RuntimeError("FROZEN_RUBRIC_MISMATCH")
    manifest = {
        "case_count": len(rows),
        "case_ids": [row["case_id"] for row in rows],
        "source_precedence": list(SOURCE_RUNS),
        "sources": source_info,
        "rubric_sha256": RUBRIC_SHA256,
        "models": MODELS,
        "temperature": 0,
        "schema": SCHEMA,
        "input_policy": "Only query, captured tool evidence with provenance metadata, final answer, frozen rubric, and output schema; no historical grades or expected answers.",
    }
    _write_json(OUT / "final_input_manifest.json", manifest)
    client = _client()
    listed = client.models.list().data
    routes = {
        role: [m.model_dump(exclude_none=True) for m in listed if m.id.lower() == model.split("/", 1)[1].lower() and getattr(m, "provider_prefix", "") == model.split("/", 1)[0]]
        for role, model in MODELS.items()
    }
    results = {"routes": routes, "probe_case_id": "AVN-087", "probes": []}
    probe_row = next(row for row in rows if row["case_id"] == "AVN-087")
    for role, model in MODELS.items():
        if not routes[role]:
            results["probes"].append({"role": role, "model": model, "status": "ROUTE_NOT_LISTED"})
            _write_json(OUT / "preflight.json", results)
            continue
        try:
            judged = _judge(client, probe_row, model)
            results["probes"].append({"role": role, "model": model, "status": "VALID", "judgment": judged})
        except Exception as exc:
            results["probes"].append({"role": role, "model": model, "status": "INVALID", "error_type": type(exc).__name__})
        _write_json(OUT / "preflight.json", results)
        print(json.dumps({"role": role, "model": model, "status": results["probes"][-1]["status"]}), flush=True)
        if role != "adjudicator":
            time.sleep(15)
    results["all_routes_valid"] = len(results["probes"]) == 3 and all(p["status"] == "VALID" for p in results["probes"])
    _write_json(OUT / "preflight.json", results)


def _readiness() -> None:
    preflight_path = OUT / "preflight.json"
    if not preflight_path.exists():
        raise RuntimeError("PREFLIGHT_REQUIRED")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    probes = preflight.get("probes") or []
    if len(probes) != 3 or not all(
        p.get("role") == role and p.get("model") == model and p.get("status") == "VALID"
        and p.get("judgment", {}).get("rubric_sha256") == RUBRIC_SHA256
        and p.get("judgment", {}).get("temperature") == 0
        and set(p.get("judgment", {}).get("grade", {})) == set(FIELDS) | {"short_reason"}
        for p, (role, model) in zip(probes, MODELS.items())
    ):
        raise RuntimeError("THREE_VALID_ROUTE_PROBES_REQUIRED")
    now = datetime.now(timezone.utc)
    for probe in probes:
        stamp = datetime.fromisoformat(probe["judgment"]["recorded_at_utc"])
        if stamp.tzinfo is None or (now - stamp).total_seconds() > 86400:
            raise RuntimeError("VALID_PROBE_NOT_RECENT")
    rows, sources = _load_final_rows()
    manifest = json.loads((OUT / "final_input_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("sources") != sources or manifest.get("case_ids") != [row["case_id"] for row in rows] or manifest.get("rubric_sha256") != RUBRIC_SHA256:
        raise RuntimeError("FROZEN_INPUT_MANIFEST_CHANGED")
    for run in ("outcome-judge-question-aware-affected16-canonical-avN175-recovery1", "outcome-judge-final-hardening-3case-run3"):
        frozen = json.loads((RESULTS / run / "judge_config.json").read_text(encoding="utf-8"))
        if frozen.get("ANSWER_JUDGE_RUBRIC") != RUBRIC or frozen.get("ANSWER_JUDGE_RUBRIC_SHA256") != RUBRIC_SHA256:
            raise RuntimeError("FROZEN_RUBRIC_MISMATCH")


def _run_with_backoff(client: OpenAI, row: dict[str, Any], role: str, dimensions: tuple[str, ...] = FIELDS) -> dict[str, Any] | None:
    model = MODELS[role]
    failures = OUT / "judge_failures.jsonl"
    for attempt in range(1, 7):
        try:
            return _judge(client, row, model, dimensions)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            transport = status == 429 or isinstance(status, int) and 500 <= status <= 599 or isinstance(exc, (APIConnectionError, APITimeoutError, TimeoutError, ConnectionResetError))
            format_error = isinstance(exc, (ValueError, json.JSONDecodeError, KeyError, IndexError))
            if not (transport or format_error):
                raise
            failure = {
                "case_id": row["case_id"], "role": role, "model": model,
                "dimensions": list(dimensions), "attempt": attempt,
                "failure_kind": "TRANSPORT" if transport else "STRUCTURED_OUTPUT",
                "error_type": type(exc).__name__, "http_status": status,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            with failures.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
                handle.flush()
            delay = min(10 * (2 ** (attempt - 1)), 60)
            print(json.dumps({"case_id": row["case_id"], "role": role, "failure_kind": failure["failure_kind"], "http_status": status, "attempt": attempt, "backoff_seconds": delay if attempt < 6 else 0}), flush=True)
            if attempt < 6:
                time.sleep(delay)
    return None


def _checkpoint(path: Path, role: str) -> dict[str, dict[str, Any]]:
    rows = _rows(path) if path.exists() else []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = row.get("case_id")
        if not isinstance(cid, str) or cid in by_id or row.get("model") != MODELS[role] or row.get("rubric_sha256") != RUBRIC_SHA256 or row.get("temperature") != 0:
            raise RuntimeError(f"INVALID_{role.upper()}_CHECKPOINT")
        by_id[cid] = row
    return by_id


def _validate_inputs(rows: list[dict[str, Any]], checkpoint: dict[str, dict[str, Any]], role: str) -> None:
    canonical = {row["case_id"]: row for row in rows}
    if not set(checkpoint) <= set(canonical):
        raise RuntimeError(f"UNKNOWN_{role.upper()}_CHECKPOINT_CASE")
    for cid, judged in checkpoint.items():
        dimensions = tuple(judged.get("dimensions", []))
        if role != "adjudicator" and dimensions != FIELDS:
            raise RuntimeError(f"INVALID_{role.upper()}_DIMENSIONS")
        prompt = _input(canonical[cid], dimensions)
        digest = hashlib.sha256(json.dumps(prompt, ensure_ascii=False).encode("utf-8")).hexdigest()
        if judged.get("input_sha256") != digest:
            raise RuntimeError(f"INPUT_HASH_CHANGED:{role}:{cid}")


def _metric_value(grade: dict[str, Any], metric: str) -> Any:
    return grade["unsupported_claims"] > 0 if metric == "unsupported_claim_present" else grade[metric]


def _disputed_dimensions(grade_a: dict[str, Any], grade_b: dict[str, Any]) -> tuple[str, ...]:
    def differs(field: str) -> bool:
        if field == "unsupported_claims":
            return (grade_a[field] > 0) != (grade_b[field] > 0)
        return grade_a[field] != grade_b[field]

    return tuple(field for field in FIELDS if differs(field))


def run_judges() -> None:
    _readiness()
    rows, sources = _load_final_rows()
    manifest = json.loads((OUT / "final_input_manifest.json").read_text(encoding="utf-8"))
    if manifest["sources"] != sources or manifest["case_ids"] != [row["case_id"] for row in rows] or manifest["rubric_sha256"] != RUBRIC_SHA256:
        raise RuntimeError("FROZEN_INPUT_MANIFEST_CHANGED")
    client = _client()
    for role, filename in (("judge_a", "grok_judgments.jsonl"), ("judge_b", "qwen_judgments.jsonl")):
        path = OUT / filename
        done = _checkpoint(path, role)
        _validate_inputs(rows, done, role)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                if row["case_id"] in done:
                    continue
                judged = _run_with_backoff(client, row, role)
                if judged is None:
                    print(json.dumps({"status": "PAUSED_PROVIDER_UNAVAILABLE", "role": role, "next_case_id": row["case_id"], "valid_cases": len(done)}), flush=True)
                    return
                handle.write(json.dumps(judged, ensure_ascii=False) + "\n")
                handle.flush()
                print(json.dumps({"role": role, "case_id": row["case_id"], "completed": len(done) + 1}, ensure_ascii=True), flush=True)
                done[row["case_id"]] = judged
                time.sleep(1)


def adjudicate() -> None:
    _readiness()
    rows, _ = _load_final_rows()
    a = _checkpoint(OUT / "grok_judgments.jsonl", "judge_a")
    b = _checkpoint(OUT / "qwen_judgments.jsonl", "judge_b")
    _validate_inputs(rows, a, "judge_a")
    _validate_inputs(rows, b, "judge_b")
    ids = {row["case_id"] for row in rows}
    if set(a) != ids or set(b) != ids:
        raise RuntimeError("BOTH_COMPLETE_INDEPENDENT_JUDGES_REQUIRED")
    agreement_path = OUT / "agreement.json"
    if not agreement_path.exists():
        raise RuntimeError("PRE_ADJUDICATION_AGREEMENT_REQUIRED")
    agreement = json.loads(agreement_path.read_text(encoding="utf-8"))
    if agreement.get("grok_sha256") != _sha(OUT / "grok_judgments.jsonl") or agreement.get("qwen_sha256") != _sha(OUT / "qwen_judgments.jsonl"):
        raise RuntimeError("INDEPENDENT_JUDGE_ARTIFACT_CHANGED_AFTER_AGREEMENT")
    disputes = {
        cid: _disputed_dimensions(a[cid]["grade"], b[cid]["grade"])
        for cid in ids
    }
    path = OUT / "glm_adjudications.jsonl"
    done = _checkpoint(path, "adjudicator")
    _validate_inputs(rows, done, "adjudicator")
    if any(tuple(done[cid]["dimensions"]) != disputes.get(cid) for cid in done):
        raise RuntimeError("ADJUDICATED_DIMENSIONS_CHANGED")
    client = _client()
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            cid = row["case_id"]
            dimensions = disputes[cid]
            if not dimensions or cid in done:
                continue
            # GLM sees the dimension names, frozen rubric, query, evidence,
            # answer, and source metadata. It sees neither judge's vote.
            judged = _run_with_backoff(client, row, "adjudicator", dimensions)
            if judged is None:
                print(json.dumps({"status": "ADJUDICATION_PENDING", "next_case_id": cid, "completed_cases": len(done)}), flush=True)
                return
            handle.write(json.dumps(judged, ensure_ascii=False) + "\n")
            handle.flush()
            done[cid] = judged
            print(json.dumps({"role": "adjudicator", "case_id": cid, "dimensions": list(dimensions)}, ensure_ascii=True), flush=True)
            time.sleep(1)


def _kappa(pairs: list[tuple[Any, Any]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    labels = {value for pair in pairs for value in pair}
    observed = sum(a == b for a, b in pairs) / n
    expected = sum(
        (sum(a == label for a, _ in pairs) / n) * (sum(b == label for _, b in pairs) / n)
        for label in labels
    )
    return (observed - expected) / (1 - expected) if not math.isclose(expected, 1.0) else (1.0 if math.isclose(observed, 1.0) else None)


def calculate_agreement() -> None:
    _readiness()
    rows, _ = _load_final_rows()
    ids = [row["case_id"] for row in rows]
    a = _checkpoint(OUT / "grok_judgments.jsonl", "judge_a")
    b = _checkpoint(OUT / "qwen_judgments.jsonl", "judge_b")
    _validate_inputs(rows, a, "judge_a")
    _validate_inputs(rows, b, "judge_b")
    if set(a) != set(ids) or set(b) != set(ids):
        raise RuntimeError("BOTH_COMPLETE_INDEPENDENT_JUDGES_REQUIRED")
    agreement: dict[str, dict[str, Any]] = {}
    disagreement_cases = 0
    disagreement_dimensions = 0
    for cid in ids:
        count = len(_disputed_dimensions(a[cid]["grade"], b[cid]["grade"]))
        disagreement_cases += count > 0
        disagreement_dimensions += count
    for metric in METRICS:
        pairs = [
            (_metric_value(a[cid]["grade"], metric), _metric_value(b[cid]["grade"], metric))
            for cid in ids
            if metric != "provenance" or a[cid]["grade"]["provenance"] != "NOT_APPLICABLE" or b[cid]["grade"]["provenance"] != "NOT_APPLICABLE"
        ]
        agrees = sum(x == y for x, y in pairs)
        agreement[metric] = {
            "agreement_count": agrees,
            "disagreement_count": len(pairs) - agrees,
            "denominator": len(pairs),
            "agreement_rate": agrees / len(pairs) if pairs else None,
            "cohens_kappa": _kappa(pairs),
        }
    result = {
        "case_count": len(ids),
        "judge_a": MODELS["judge_a"],
        "judge_b": MODELS["judge_b"],
        "grok_sha256": _sha(OUT / "grok_judgments.jsonl"),
        "qwen_sha256": _sha(OUT / "qwen_judgments.jsonl"),
        "rubric_sha256": RUBRIC_SHA256,
        "disagreement_cases": disagreement_cases,
        "disagreement_dimensions": disagreement_dimensions,
        "metrics": agreement,
        "provenance_applicability": "union of cases where either judge labels provenance applicable",
        "unsupported_comparison": "boolean unsupported_claims > 0",
    }
    _write_json(OUT / "agreement.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def summarize() -> None:
    _readiness()
    rows, _ = _load_final_rows()
    ids = [row["case_id"] for row in rows]
    a = _checkpoint(OUT / "grok_judgments.jsonl", "judge_a")
    b = _checkpoint(OUT / "qwen_judgments.jsonl", "judge_b")
    c = _checkpoint(OUT / "glm_adjudications.jsonl", "adjudicator")
    _validate_inputs(rows, a, "judge_a")
    _validate_inputs(rows, b, "judge_b")
    _validate_inputs(rows, c, "adjudicator")
    if set(a) != set(ids) or set(b) != set(ids):
        raise RuntimeError("INDEPENDENT_JUDGE_SET_INCOMPLETE")
    agreement = json.loads((OUT / "agreement.json").read_text(encoding="utf-8"))
    if agreement["grok_sha256"] != _sha(OUT / "grok_judgments.jsonl") or agreement["qwen_sha256"] != _sha(OUT / "qwen_judgments.jsonl"):
        raise RuntimeError("INDEPENDENT_JUDGE_ARTIFACT_CHANGED_AFTER_AGREEMENT")
    final_rows = []
    for cid in ids:
        grade: dict[str, Any] = {}
        decisions: dict[str, str] = {}
        disputed = _disputed_dimensions(a[cid]["grade"], b[cid]["grade"])
        if disputed and (cid not in c or tuple(c[cid]["dimensions"]) != disputed):
            raise RuntimeError(f"ADJUDICATION_MISSING_OR_WRONG_DIMENSIONS:{cid}")
        for metric in METRICS:
            av = _metric_value(a[cid]["grade"], metric)
            bv = _metric_value(b[cid]["grade"], metric)
            if av == bv:
                grade[metric] = av
                decisions[metric] = "CONSENSUS"
            else:
                grade[metric] = _metric_value(c[cid]["grade"], metric)
                decisions[metric] = "BLIND_GLM_ADJUDICATION"
        final_rows.append({"case_id": cid, "grade": grade, "decision_source": decisions})
    unexpected = set(c) - {r["case_id"] for r in final_rows if "BLIND_GLM_ADJUDICATION" in r["decision_source"].values()}
    if unexpected:
        raise RuntimeError("ADJUDICATION_ON_AGREED_CASE")
    grades = [row["grade"] for row in final_rows]
    provenance = [g for g in grades if g["provenance"] != "NOT_APPLICABLE"]
    oracle = _outcome_oracles()
    if set(oracle) != set(ids):
        raise RuntimeError("FROZEN_NO_EVIDENCE_ORACLE_IDENTITY_MISMATCH")
    no_evidence_ids = [cid for cid in ids if oracle[cid]["expected_channel"] == "NO_EVIDENCE"]
    final_by_id = {row["case_id"]: row["grade"] for row in final_rows}
    no_evidence_correct = sum(final_by_id[cid]["no_evidence_handling"] == "PASS" for cid in no_evidence_ids)
    relevance_pass = sum(g["relevance"] == "PASS" for g in grades)
    faithfulness_pass = sum(g["faithfulness"] == "PASS" for g in grades)
    unsupported_cases = sum(g["unsupported_claim_present"] for g in grades)
    provenance_pass = sum(g["provenance"] == "PASS" for g in provenance)
    metrics = {
        "final_cases": len(grades),
        "grok_qwen_agreement": agreement["metrics"],
        "disagreement_cases": agreement["disagreement_cases"],
        "disagreement_dimensions": agreement["disagreement_dimensions"],
        "adjudicated_cases": len(c),
        "adjudicated_dimensions": sum(len(row["dimensions"]) for row in c.values()),
        "adjudicated_relevance": {"pass": relevance_pass, "denominator": 55, "rate": relevance_pass / 55},
        "adjudicated_faithfulness": {"pass": faithfulness_pass, "denominator": 55, "rate": faithfulness_pass / 55},
        "adjudicated_unsupported_claim_cases": {"cases": unsupported_cases, "denominator": 55, "rate": unsupported_cases / 55},
        "adjudicated_provenance": {"correct": provenance_pass, "applicable": len(provenance), "rate": provenance_pass / len(provenance) if provenance else None},
        "no_evidence_handling": {"correct": no_evidence_correct, "applicable": len(no_evidence_ids), "rate": no_evidence_correct / len(no_evidence_ids) if no_evidence_ids else None},
        "rubric_sha256": RUBRIC_SHA256,
        "temperature": 0,
        "models": MODELS,
        "answer_quality_metrics_complete": True,
    }
    _write_json(OUT / "final_adjudicated_judgments.json", final_rows)
    _write_json(OUT / "final_adjudicated_metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "run-judges", "agreement", "adjudicate", "summarize"))
    args = parser.parse_args()
    if args.command == "preflight":
        preflight()
    elif args.command == "run-judges":
        run_judges()
    elif args.command == "agreement":
        calculate_agreement()
    elif args.command == "adjudicate":
        adjudicate()
    elif args.command == "summarize":
        summarize()


if __name__ == "__main__":
    main()
