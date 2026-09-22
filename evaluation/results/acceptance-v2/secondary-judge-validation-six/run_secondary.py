"""Read-only secondary grading of six canonical acceptance answers."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
sys.path.insert(0, str(BACKEND))
from config import settings  # noqa: E402
from scripts.research_acceptance_vn.grade_acceptance_outcomes import (  # noqa: E402
    RUBRIC,
    _parse,
    _tool_evidence,
    _without_hidden_reasoning,
)

OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "evaluation/results/acceptance-v2"
MODEL = "vc/qwen3.8-max"
PROVIDER = "vc via api.vilao.ai"
RUNS = {
    "AVN-087": "outcome-question-aware-affected16-canonical-avN175-recovery1",
    "AVN-099": "outcome-question-aware-affected16-canonical-avN175-recovery1",
    "AVN-100": "outcome-question-aware-affected16-canonical-avN175-recovery1",
    "AVN-168": "outcome-final-hardening-3case-run3",
    "AVN-171": "outcome-question-aware-affected16-canonical-avN175-recovery1",
    "AVN-174": "outcome-final-hardening-3case-run3",
}


def load_record(case_id: str) -> tuple[dict, Path]:
    artifact = SOURCE / RUNS[case_id] / "full_pipeline.jsonl"
    rows = [json.loads(line) for line in artifact.read_text(encoding="utf-8").splitlines() if line]
    matches = [row for row in rows if row.get("case_id") == case_id]
    if len(matches) != 1:
        raise RuntimeError(f"INVALID_CANONICAL_RECORD:{case_id}")
    row = matches[0]
    if not row.get("query") or not row.get("response") or not isinstance(row.get("events"), list):
        raise RuntimeError(f"INCOMPLETE_CANONICAL_RECORD:{case_id}")
    return row, artifact


def grade(client: OpenAI, case_id: str) -> dict:
    row, artifact = load_record(case_id)
    prompt = {
        "rubric": RUBRIC,
        "output_schema": {
            "relevance": "PASS|FAIL",
            "faithfulness": "PASS|FAIL",
            "unsupported_claims": "integer >= 0",
            "provenance": "PASS|FAIL|NOT_APPLICABLE",
            "no_evidence_handling": "PASS|FAIL|NOT_APPLICABLE",
            "short_reason": "one concise evidence-based sentence",
        },
        "query": row["query"],
        "evidence_available_during_turn": _tool_evidence(row),
        "final_answer": row["response"],
    }
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=4096,
        messages=[
            {"role": "system", "content": "Return only the requested JSON object. Do not reveal reasoning. Include short_reason as one concise evidence-based sentence."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    content = _without_hidden_reasoning(response.choices[0].message.content or "")
    parsed = _parse(content, require_short_reason=True)
    parsed_raw = json.loads(content)
    if set(parsed_raw) != set(parsed):
        raise ValueError("EXTRA_OR_MISSING_GRADE_FIELDS")
    return {
        "case_id": case_id,
        "grade": parsed,
        "model": MODEL,
        "provider": PROVIDER,
        "rubric_sha256": hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest(),
        "canonical_artifact": str(artifact.relative_to(ROOT)).replace("\\", "/"),
        "canonical_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "judge_input_sha256": hashlib.sha256(json.dumps(prompt, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "max_tokens": 4096,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("probe", "remaining"))
    args = parser.parse_args()
    output = OUT / "secondary_vc_qwenmax_judgments.jsonl"
    prior = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] if output.exists() else []
    selected = ["AVN-087"] if args.mode == "probe" else list(RUNS)[1:]
    if args.mode == "remaining" and (not prior or [row["case_id"] for row in prior] != list(RUNS)[:len(prior)]):
        raise RuntimeError("VALID_PROBE_REQUIRED_FIRST")
    selected = [case_id for case_id in selected if case_id not in {row["case_id"] for row in prior}]
    client = OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key or "dummy-key", max_retries=0, timeout=90)
    with output.open("a", encoding="utf-8") as handle:
        for case_id in selected:
            judged = grade(client, case_id)
            handle.write(json.dumps(judged, ensure_ascii=False) + "\n")
            handle.flush()
            print(json.dumps({"case_id": case_id, "grade": judged["grade"]}, ensure_ascii=False), flush=True)
            if case_id != selected[-1]:
                time.sleep(15)


if __name__ == "__main__":
    main()
