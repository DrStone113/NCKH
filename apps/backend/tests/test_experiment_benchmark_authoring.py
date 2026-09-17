from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from services.experiment import benchmark_authoring
from services.experiment.benchmark import ScoringMetadata
from services.experiment.benchmark_authoring import (
    CALCULATION_CANDIDATE_STATUS,
    EXPECTED_CALCULATION_CANDIDATE_COUNT,
    build_calculation_candidates,
    load_and_verify_calculation_candidate_pack,
    write_calculation_candidate_pack,
)
from services.experiment.errors import ExperimentError
from services.nutrition.registry import POLICY_VERSION
from scripts import generate_calculation_candidates


def test_rq3_is_available_for_personalization_benchmarks() -> None:
    metadata = ScoringMetadata(
        answerability="constraint_based",
        research_questions=("RQ3",),
        objective_metrics=("constraint_satisfaction_rate",),
        human_rubrics=("personalization",),
    )

    assert metadata.research_questions == ("RQ3",)


def test_calculation_candidates_are_balanced_and_policy_derived() -> None:
    candidate_file = build_calculation_candidates()
    candidates = candidate_file.candidates

    assert candidate_file.status == CALCULATION_CANDIDATE_STATUS
    assert candidate_file.policy_version == POLICY_VERSION
    assert len(candidates) == EXPECTED_CALCULATION_CANDIDATE_COUNT
    assert len({candidate.candidate_id for candidate in candidates}) == 60
    assert Counter(candidate.proposed_case.profile.sex for candidate in candidates) == {
        "male": 30,
        "female": 30,
    }
    assert Counter(
        candidate.proposed_case.profile.activity_level for candidate in candidates
    ) == {
        "sedentary": 12,
        "light": 12,
        "moderate": 12,
        "active": 12,
        "very_active": 12,
    }
    goal_counts = Counter(
        candidate.proposed_case.profile.goal for candidate in candidates
    )
    assert goal_counts == {
        "lose_weight": 20,
        "maintain": 20,
        "gain_muscle": 20,
    }

    for candidate in candidates:
        case = candidate.proposed_case
        profile = case.profile
        projection = candidate.canonical_output_projection
        expected = {
            value.value_id: value.expected for value in case.objective_expected_values
        }
        assert candidate.review_status == CALCULATION_CANDIDATE_STATUS
        assert case.split.value == "development"
        assert case.scoring_metadata.research_questions == ("RQ2",)
        assert candidate.canonical_input["age"] == profile.age
        assert candidate.canonical_input["equation_sex"] == profile.sex
        assert candidate.canonical_input["height_cm"] == profile.height_cm
        assert candidate.canonical_input["weight_kg"] == profile.weight_kg
        assert candidate.canonical_input["activity_level"] == profile.activity_level
        assert candidate.canonical_input["health_goal"] == profile.goal
        assert projection["status"] == "READY"
        assert projection["calorie_target_status"] == "AVAILABLE"
        assert projection["policy_version"] == POLICY_VERSION
        assert expected == {
            "bmi": projection["bmi"],
            "rmr": projection["estimated_rmr_kcal_per_day"],
            "tdee": projection["estimated_tdee_kcal_per_day"],
            "calorie-target": projection["calorie_target_kcal_per_day"],
        }


def test_candidate_pack_round_trip_and_review_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        benchmark_authoring,
        "repository_state",
        lambda _: ("authoring-commit", True),
    )
    candidate_path, manifest_path, review_path = write_calculation_candidate_pack(
        tmp_path / "pack", repo_root=tmp_path
    )

    candidate_file, manifest = load_and_verify_calculation_candidate_pack(
        candidate_path, manifest_path, review_path
    )
    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        review_rows = list(csv.DictReader(handle))

    assert len(candidate_file.candidates) == 60
    assert manifest.candidate_count == 60
    assert manifest.category_counts == {"energy_calculation": 60}
    assert manifest.proposed_split_counts == {"development": 60}
    assert manifest.generation_commit == "authoring-commit"
    assert manifest.generation_worktree_clean is True
    assert len(review_rows) == 60
    assert review_rows[0]["review_decision"] == ""
    assert review_rows[0]["reviewer_id"] == ""

    review_path.write_bytes(review_path.read_bytes() + b"tampered")
    with pytest.raises(
        ExperimentError, match="EXPERIMENT_CANDIDATE_PACK_HASH_MISMATCH"
    ):
        load_and_verify_calculation_candidate_pack(
            candidate_path, manifest_path, review_path
        )


def test_candidate_pack_requires_clean_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        benchmark_authoring,
        "repository_state",
        lambda _: ("dirty-commit", False),
    )

    with pytest.raises(
        ExperimentError, match="EXPERIMENT_CANDIDATE_REQUIRES_CLEAN_WORKTREE"
    ):
        write_calculation_candidate_pack(tmp_path / "pack", repo_root=tmp_path)


def test_candidate_cli_writes_and_verifies_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        benchmark_authoring,
        "repository_state",
        lambda _: ("cli-commit", True),
    )
    output_dir = tmp_path / "cli-pack"

    exit_code = generate_calculation_candidates.main(
        ["--output-dir", str(output_dir)]
    )
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["status"] == CALCULATION_CANDIDATE_STATUS
    assert summary["candidate_count"] == 60
    assert summary["generation_commit"] == "cli-commit"
    assert Path(summary["candidate_file"]).exists()
    assert Path(summary["manifest_file"]).exists()
    assert Path(summary["review_template"]).exists()
