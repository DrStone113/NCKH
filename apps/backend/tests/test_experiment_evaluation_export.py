from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.experiment.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_VERSION,
    RUBRIC_VERSION,
    Answerability,
    BenchmarkCase,
    BenchmarkCategory,
    BenchmarkFile,
    BenchmarkManifest,
    BenchmarkSplit,
    RequiredFact,
    ScoringMetadata,
    canonical_json_bytes,
    sha256_canonical,
    sha256_file,
)
from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NUTRITION_ABLATION_MODEL,
    NUTRITION_ABLATION_PROMPT_VERSION,
    ExperimentConfig,
)
from services.experiment.errors import ExperimentError
from services.experiment.evaluation_export import (
    evaluate_batch_records,
    validate_batch_records,
    write_evaluations,
)
from services.experiment.models import ExperimentProfile
from services.experiment.records import ExperimentRunRecord
from scripts import evaluate_benchmark


def _profile() -> ExperimentProfile:
    return ExperimentProfile(
        profile_id="evaluation-profile",
        age=28,
        sex="male",
        height_cm=170,
        weight_kg=68,
        activity_level="moderate",
        goal="maintain",
    )


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="evaluation-case-001",
        category=BenchmarkCategory.GENERAL_NUTRITION,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query="Protein có vai trò gì?",
        profile=_profile(),
        required_facts=(
            RequiredFact(
                fact_id="mentions-protein",
                description="Response addresses protein.",
                acceptable_terms=("protein", "chất đạm"),
            ),
        ),
        required_constraints=(),
        reference_sources=(),
        objective_expected_values=(),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.NOT_ANSWERABLE_FROM_CORPUS,
            research_questions=("RQ1",),
            objective_metrics=("required_fact_coverage",),
            human_rubrics=("factual_correctness",),
        ),
    )


def _benchmark() -> BenchmarkFile:
    return BenchmarkFile(
        benchmark_version=BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        cases=(_case(),),
    )


def _manifest(file_hash: str = "b" * 64) -> BenchmarkManifest:
    return BenchmarkManifest(
        benchmark_version=BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        case_count=1,
        category_counts={"general_nutrition": 1},
        split_counts={"development": 1},
        benchmark_file_sha256=file_hash,
        creation_commit="fixture-commit",
        creation_worktree_clean=True,
        rubric_version=RUBRIC_VERSION,
        reference_source_versions={},
        corpus_version="offline-v1-636",
        manifest_hash="c" * 64,
    )


def _retrieval_trace(config: ExperimentConfig) -> dict[str, Any]:
    return {
        "query": _case().user_query,
        "expanded_query": None,
        "top_k": config.rag_top_k,
        "threshold": config.rag_threshold,
        "retrieval_latency_ms": 1.0,
        "corpus_version": config.corpus_version,
        "corpus_hash": config.corpus_hash,
        "chunks": [],
    }


def _records(error_arm: str | None = None) -> tuple[ExperimentRunRecord, ...]:
    case = _case()
    manifest = _manifest()
    records = []
    for index, arm in enumerate(NUTRITION_ABLATION_ARMS, start=1):
        config = ExperimentConfig(
            condition=arm,
            model=NUTRITION_ABLATION_MODEL,
            prompt_version=NUTRITION_ABLATION_PROMPT_VERSION,
        )
        records.append(
            ExperimentRunRecord(
                experiment_id="evaluation-test",
                run_id=f"run-{arm}",
                condition=arm,
                protocol_id=config.protocol_id,
                benchmark_version=BENCHMARK_VERSION,
                benchmark_file_sha256=manifest.benchmark_file_sha256,
                benchmark_manifest_hash=manifest.manifest_hash,
                benchmark_case_hash=case.case_hash(),
                benchmark_split=BenchmarkSplit.DEVELOPMENT.value,
                batch_schedule_seed=42,
                repetition_index=1,
                schedule_index=index,
                test_case_id=case.case_id,
                timestamp="2026-09-17T00:00:00+00:00",
                config=config.serialize(),
                config_hash=config.config_hash(),
                user_query=case.user_query,
                profile_snapshot_or_null=(
                    case.profile.model_dump(mode="json")
                    if config.profile_enabled
                    else None
                ),
                rendered_system_prompt="fixture prompt",
                model_requested=config.model,
                model_actual="qwen3.8-flash",
                temperature=config.temperature,
                seed=config.seed,
                tools_offered=(
                    ["calculate_tdee"]
                    if config.nutrition_tools_enabled
                    else []
                ),
                retrieval_trace=(
                    _retrieval_trace(config) if config.rag_enabled else None
                ),
                token_usage={"total_tokens": 12},
                completion_finish_reasons=["stop"],
                final_response="Protein là một chất dinh dưỡng đa lượng.",
                latency_ms=10.0,
                error=(
                    "EXPERIMENT_LLM_FAILED: fixture"
                    if arm == error_arm
                    else None
                ),
                git_commit="same-commit",
                worktree_clean=True,
            )
        )
    return tuple(records)


def _write_verified_inputs(
    tmp_path: Path, records: tuple[ExperimentRunRecord, ...]
) -> tuple[Path, Path, Path]:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_bytes(
        canonical_json_bytes(_benchmark().model_dump(mode="json"), indent=2)
    )
    manifest_payload: dict[str, Any] = {
        "benchmark_version": BENCHMARK_VERSION,
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "case_count": 1,
        "category_counts": {"general_nutrition": 1},
        "split_counts": {"development": 1},
        "benchmark_file_sha256": sha256_file(benchmark_path),
        "creation_commit": "fixture-commit",
        "creation_worktree_clean": True,
        "rubric_version": RUBRIC_VERSION,
        "reference_source_versions": {},
        "corpus_version": "offline-v1-636",
    }
    manifest_payload["manifest_hash"] = sha256_canonical(manifest_payload)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest_payload, indent=2))

    records_path = tmp_path / "records.jsonl"
    with records_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            payload = record.model_copy(
                update={
                    "benchmark_file_sha256": manifest_payload[
                        "benchmark_file_sha256"
                    ],
                    "benchmark_manifest_hash": manifest_payload["manifest_hash"],
                }
            )
            handle.write(payload.model_dump_json())
            handle.write("\n")
    return benchmark_path, manifest_path, records_path


def test_valid_batch_exports_deterministic_metrics() -> None:
    records = _records()
    validate_batch_records(
        records,
        benchmark=_benchmark(),
        manifest=_manifest(),
        split=BenchmarkSplit.DEVELOPMENT,
    )

    evaluations = evaluate_batch_records(
        records,
        benchmark=_benchmark(),
        manifest=_manifest(),
    )

    assert len(evaluations) == 4
    assert all(item.evaluation_status == "scored" for item in evaluations)
    for evaluation in evaluations:
        fact_metric = next(
            metric
            for metric in evaluation.metrics
            if metric.metric == "required_fact_coverage"
        )
        assert fact_metric.value == 1.0


def test_tampered_config_hash_is_rejected() -> None:
    records = list(_records())
    records[0] = records[0].model_copy(update={"config_hash": "0" * 64})

    with pytest.raises(
        ExperimentError, match="EXPERIMENT_RECORD_CONFIG_HASH_MISMATCH"
    ):
        validate_batch_records(
            records,
            benchmark=_benchmark(),
            manifest=_manifest(),
            split=BenchmarkSplit.DEVELOPMENT,
        )


def test_failed_run_is_retained_without_metrics() -> None:
    records = _records(error_arm="S2")
    validate_batch_records(
        records,
        benchmark=_benchmark(),
        manifest=_manifest(),
        split=BenchmarkSplit.DEVELOPMENT,
    )
    evaluations = evaluate_batch_records(
        records,
        benchmark=_benchmark(),
        manifest=_manifest(),
    )
    failed = next(item for item in evaluations if item.condition == "S2")

    assert failed.evaluation_status == "run_error"
    assert failed.record_error == "EXPERIMENT_LLM_FAILED: fixture"
    assert failed.metrics == ()


def test_evaluation_cli_validates_and_writes_jsonl(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    benchmark_path, manifest_path, records_path = _write_verified_inputs(
        tmp_path, _records()
    )
    output_path = tmp_path / "evaluations.jsonl"
    exit_code = evaluate_benchmark.main(
        [
            "--benchmark",
            str(benchmark_path),
            "--manifest",
            str(manifest_path),
            "--records",
            str(records_path),
            "--split",
            "development",
            "--output",
            str(output_path),
        ]
    )
    summary = json.loads(capsys.readouterr().out)
    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]

    assert exit_code == 0
    assert summary["evaluated_runs"] == 4
    assert summary["run_errors"] == 0
    assert len(rows) == 4
    assert all(row["evaluation_status"] == "scored" for row in rows)

    with pytest.raises(
        ExperimentError, match="EXPERIMENT_EVALUATION_OUTPUT_EXISTS"
    ):
        write_evaluations(output_path, (), overwrite=False)
