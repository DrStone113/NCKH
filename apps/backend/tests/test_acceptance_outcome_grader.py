"""Focused contracts for the frozen flexible-path outcome grader."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "research_acceptance_vn"
    / "grade_acceptance_outcomes.py"
)
_SPEC = importlib.util.spec_from_file_location("acceptance_outcome_grader", _SCRIPT)
assert _SPEC and _SPEC.loader
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)


def test_grader_reads_structured_acceptance_evidence_from_debug_envelope() -> None:
    row = {
        "events": [
            {
                "type": "debug_trace",
                "event": {
                    "operation": "TOOL_RESULT",
                    "sanitized_payload": {
                        "name": "query_rag",
                        "ok": True,
                        "acceptance_evidence": [
                            {"title": "Nguồn chính thức", "content": "Dữ kiện"}
                        ],
                    },
                },
            },
            {
                "type": "debug_trace",
                "event": {
                    "operation": "CONTEXT_RAG_EVIDENCE",
                    "sanitized_payload": {
                        "name": "query_rag",
                        "ok": True,
                        "acceptance_evidence": [
                            {"title": "Ngữ cảnh ban đầu", "content": "Dữ kiện khác"}
                        ],
                    },
                },
            },
        ]
    }

    assert grader._tool_evidence(row) == [
        {
            "tool": "query_rag",
            "ok": True,
            "result": [{"title": "Nguồn chính thức", "content": "Dữ kiện"}],
        },
        {
            "tool": "query_rag",
            "ok": True,
            "result": [{"title": "Ngữ cảnh ban đầu", "content": "Dữ kiện khác"}],
        },
    ]


def test_subset_input_accepts_explicit_case_count(tmp_path: Path) -> None:
    artifact = tmp_path / "full_pipeline.jsonl"
    artifact.write_text(json.dumps({"case_id": "AVN-081", "query": "q", "response": "a", "events": []}) + "\n", encoding="utf-8")

    assert set(grader._load_input_artifact(artifact, expected_case_count=1)) == {"AVN-081"}


def test_subset_input_rejects_duplicate_or_count_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "full_pipeline.jsonl"
    row = {"case_id": "AVN-081", "query": "q", "response": "a", "events": []}
    artifact.write_text("\n".join(json.dumps(row) for _ in range(2)), encoding="utf-8")

    with pytest.raises(RuntimeError, match="DUPLICATE"):
        grader._load_input_artifact(artifact, expected_case_count=2)


def test_explicit_model_subset_run_is_homogeneous_and_checkpoint_resumable() -> None:
    # It must not require --rejudge-all merely to preserve MiniMax on resume.
    assert grader._is_homogeneous_run(
        input_artifact=Path("artifact"), judge_model="MiniMax-M2.7", rejudge_all=False,
    )
    assert not grader._is_homogeneous_run(
        input_artifact=Path("artifact"), judge_model=None, rejudge_all=False,
    )
