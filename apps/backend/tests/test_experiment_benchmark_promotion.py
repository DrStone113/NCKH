from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.experiment import (
    benchmark_authoring,
    benchmark_promotion,
    benchmark_review,
)
from services.experiment.batch import build_schedule
from services.experiment.benchmark import (
    CALCULATION_DEVELOPMENT_BENCHMARK_VERSION,
    BenchmarkFile,
    BenchmarkSplit,
    load_and_verify_benchmark,
)
from services.experiment.benchmark_authoring import write_calculation_candidate_pack
from services.experiment.benchmark_promotion import (
    CALCULATION_PROMOTION_PIPELINE_VERSION,
    load_and_verify_promoted_calculation_benchmark,
    write_calculation_development_benchmark,
)
from services.experiment.benchmark_review import write_completed_calculation_review
from services.experiment.errors import ExperimentError
from scripts import promote_calculation_benchmark

REVIEWED_AT = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)


def _reviewed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    source = tmp_path / "source"
    monkeypatch.setattr(
        benchmark_authoring,
        "repository_state",
        lambda _: ("candidate-commit", True),
    )
    candidate_path, candidate_manifest_path, review_template_path = (
        write_calculation_candidate_pack(source, repo_root=tmp_path)
    )
    completed_review_path = source / "nutrition_calculation_review_completed_v1.csv"
    review_manifest_path = (
        source / "nutrition_calculation_review_completed_v1.manifest.json"
    )
    monkeypatch.setattr(
        benchmark_review,
        "repository_state",
        lambda _: ("review-commit", True),
    )
    write_completed_calculation_review(
        candidate_path=candidate_path,
        candidate_manifest_path=candidate_manifest_path,
        review_template_path=review_template_path,
        completed_review_path=completed_review_path,
        review_manifest_path=review_manifest_path,
        repo_root=tmp_path,
        reviewer_id="codex-ai-assisted-review-v1",
        reviewed_at=REVIEWED_AT,
    )
    return {
        "candidate_path": candidate_path,
        "candidate_manifest_path": candidate_manifest_path,
        "review_template_path": review_template_path,
        "completed_review_path": completed_review_path,
        "review_manifest_path": review_manifest_path,
    }


def _promoted_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    paths = _reviewed_source(tmp_path, monkeypatch)
    output = tmp_path / "output"
    paths.update(
        {
            "benchmark_path": output / "benchmark.json",
            "benchmark_manifest_path": output / "benchmark.manifest.json",
        }
    )
    monkeypatch.setattr(
        benchmark_promotion,
        "repository_state",
        lambda _: ("promotion-commit", True),
    )
    write_calculation_development_benchmark(
        **paths,
        repo_root=tmp_path,
    )
    return paths


def test_promoted_benchmark_is_runnable_and_review_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _promoted_pack(tmp_path, monkeypatch)

    benchmark, manifest = load_and_verify_promoted_calculation_benchmark(**paths)
    ordinary_benchmark, ordinary_manifest = load_and_verify_benchmark(
        paths["benchmark_path"], paths["benchmark_manifest_path"]
    )
    schedule = build_schedule(
        benchmark,
        split=BenchmarkSplit.DEVELOPMENT,
        repetitions=1,
        schedule_seed=42,
    )

    assert benchmark == ordinary_benchmark
    assert manifest == ordinary_manifest
    assert benchmark.benchmark_version == CALCULATION_DEVELOPMENT_BENCHMARK_VERSION
    assert len(benchmark.cases) == 60
    assert manifest.case_count == 60
    assert manifest.category_counts == {"energy_calculation": 60}
    assert manifest.split_counts == {"development": 60}
    assert manifest.reference_source_versions == {
        "nutrition-policy-v1.0.1": "nutrition-policy-v1.0.1"
    }
    assert len(schedule) == 240
    assert manifest.promotion_provenance is not None
    assert (
        manifest.promotion_provenance.promotion_pipeline_version
        == CALCULATION_PROMOTION_PIPELINE_VERSION
    )
    assert manifest.promotion_provenance.human_domain_signoff is False
    assert manifest.promotion_provenance.approved_candidate_count == 60
    assert manifest.creation_commit == "promotion-commit"


def test_calculation_development_version_rejects_non_development_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _promoted_pack(tmp_path, monkeypatch)
    benchmark, _ = load_and_verify_promoted_calculation_benchmark(**paths)
    changed_case = benchmark.cases[0].model_copy(
        update={"split": BenchmarkSplit.FINAL}
    )

    with pytest.raises(ValidationError):
        BenchmarkFile(
            benchmark_version=CALCULATION_DEVELOPMENT_BENCHMARK_VERSION,
            schema_version=benchmark.schema_version,
            cases=(changed_case, *benchmark.cases[1:]),
        )


def test_promotion_verifier_rejects_review_chain_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _promoted_pack(tmp_path, monkeypatch)
    paths["completed_review_path"].write_bytes(
        paths["completed_review_path"].read_bytes() + b"tampered"
    )

    with pytest.raises(ExperimentError):
        load_and_verify_promoted_calculation_benchmark(**paths)


def test_promotion_requires_clean_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _reviewed_source(tmp_path, monkeypatch)
    paths.update(
        {
            "benchmark_path": tmp_path / "benchmark.json",
            "benchmark_manifest_path": tmp_path / "benchmark.manifest.json",
        }
    )
    monkeypatch.setattr(
        benchmark_promotion,
        "repository_state",
        lambda _: ("dirty-promotion", False),
    )

    with pytest.raises(
        ExperimentError, match="EXPERIMENT_PROMOTION_REQUIRES_CLEAN_WORKTREE"
    ):
        write_calculation_development_benchmark(
            **paths,
            repo_root=tmp_path,
        )


def test_promotion_cli_writes_verified_development_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _reviewed_source(tmp_path, monkeypatch)
    output = tmp_path / "cli-output"
    monkeypatch.setattr(
        benchmark_promotion,
        "repository_state",
        lambda _: ("cli-promotion-commit", True),
    )

    exit_code = promote_calculation_benchmark.main(
        [
            "--source-dir",
            str(paths["candidate_path"].parent),
            "--output-dir",
            str(output),
        ]
    )
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert (
        summary["benchmark_version"]
        == CALCULATION_DEVELOPMENT_BENCHMARK_VERSION
    )
    assert summary["case_count"] == 60
    assert summary["split_counts"] == {"development": 60}
    assert summary["promotion_scope"] == "DEVELOPMENT_ONLY"
    assert summary["human_domain_signoff"] is False
    assert Path(summary["benchmark"]).exists()
    assert Path(summary["manifest"]).exists()
