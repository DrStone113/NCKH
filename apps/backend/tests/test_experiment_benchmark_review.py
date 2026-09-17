from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.experiment import benchmark_authoring, benchmark_review
from services.experiment.benchmark_authoring import (
    build_calculation_candidates,
    write_calculation_candidate_pack,
)
from services.experiment.benchmark_review import (
    CALCULATION_REVIEW_STATUS,
    independently_review_candidate,
    load_and_verify_completed_calculation_review,
    write_completed_calculation_review,
)
from services.experiment.errors import ExperimentError
from scripts import review_calculation_candidates

REVIEWED_AT = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)


def _source_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, ...]:
    monkeypatch.setattr(
        benchmark_authoring,
        "repository_state",
        lambda _: ("candidate-commit", True),
    )
    return write_calculation_candidate_pack(tmp_path / "pack", repo_root=tmp_path)


def _completed_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path, Path]:
    candidate_path, candidate_manifest_path, review_template_path = _source_pack(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        benchmark_review,
        "repository_state",
        lambda _: ("review-commit", True),
    )
    completed_path = tmp_path / "pack" / "completed.csv"
    review_manifest_path = tmp_path / "pack" / "completed.manifest.json"
    write_completed_calculation_review(
        candidate_path=candidate_path,
        candidate_manifest_path=candidate_manifest_path,
        review_template_path=review_template_path,
        completed_review_path=completed_path,
        review_manifest_path=review_manifest_path,
        repo_root=tmp_path,
        reviewer_id="codex-ai-assisted-review-v1",
        reviewed_at=REVIEWED_AT,
    )
    return (
        candidate_path,
        candidate_manifest_path,
        review_template_path,
        completed_path,
        review_manifest_path,
    )


def test_independent_calculation_matches_known_first_case() -> None:
    first = build_calculation_candidates().candidates[0]

    result = independently_review_candidate(first)

    assert result.model_dump() == {
        "bmi": 24.22,
        "rmr": 1658.0,
        "tdee": 1989.0,
        "calorie_target": 1790.0,
    }


def test_completed_review_approves_and_verifies_all_60_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _completed_pack(tmp_path, monkeypatch)

    candidate_file, _, manifest = load_and_verify_completed_calculation_review(
        candidate_path=paths[0],
        candidate_manifest_path=paths[1],
        review_template_path=paths[2],
        completed_review_path=paths[3],
        review_manifest_path=paths[4],
    )
    with paths[3].open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert manifest.status == CALCULATION_REVIEW_STATUS
    assert manifest.reviewer_kind == "AI_ASSISTED_TECHNICAL_REVIEW"
    assert manifest.human_domain_signoff is False
    assert manifest.promotion_scope == "DEVELOPMENT_ONLY"
    assert manifest.development_promotion_eligible is True
    assert manifest.decision_counts == {"APPROVE": 60}
    assert manifest.review_execution_commit == "review-commit"
    assert len(candidate_file.candidates) == len(rows) == 60
    assert {row["review_decision"] for row in rows} == {"APPROVE"}
    assert {row["reviewer_id"] for row in rows} == {
        "codex-ai-assisted-review-v1"
    }
    assert all(row["reviewer_notes"] for row in rows)


def test_completed_review_rejects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _completed_pack(tmp_path, monkeypatch)
    paths[3].write_bytes(paths[3].read_bytes() + b"tampered")

    with pytest.raises(ExperimentError):
        load_and_verify_completed_calculation_review(
            candidate_path=paths[0],
            candidate_manifest_path=paths[1],
            review_template_path=paths[2],
            completed_review_path=paths[3],
            review_manifest_path=paths[4],
        )


def test_review_requires_clean_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_path, candidate_manifest_path, review_template_path = _source_pack(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        benchmark_review,
        "repository_state",
        lambda _: ("dirty-review", False),
    )

    with pytest.raises(
        ExperimentError, match="EXPERIMENT_REVIEW_REQUIRES_CLEAN_WORKTREE"
    ):
        write_completed_calculation_review(
            candidate_path=candidate_path,
            candidate_manifest_path=candidate_manifest_path,
            review_template_path=review_template_path,
            completed_review_path=tmp_path / "completed.csv",
            review_manifest_path=tmp_path / "completed.manifest.json",
            repo_root=tmp_path,
            reviewer_id="reviewer",
            reviewed_at=REVIEWED_AT,
        )


def test_review_cli_writes_auditable_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path, _, _ = _source_pack(tmp_path, monkeypatch)
    pack_dir = candidate_path.parent
    monkeypatch.setattr(
        benchmark_review,
        "repository_state",
        lambda _: ("cli-review-commit", True),
    )

    exit_code = review_calculation_candidates.main(
        [
            "--pack-dir",
            str(pack_dir),
            "--reviewer-id",
            "codex-ai-assisted-review-v1",
            "--reviewed-at",
            "2026-09-17T08:00:00Z",
        ]
    )
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["status"] == CALCULATION_REVIEW_STATUS
    assert summary["decision_counts"] == {"APPROVE": 60}
    assert summary["human_domain_signoff"] is False
    assert Path(summary["completed_review"]).exists()
    assert Path(summary["review_manifest"]).exists()
