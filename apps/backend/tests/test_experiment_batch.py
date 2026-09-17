from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from services.experiment.batch import (
    NutritionAblationBatchRunner,
    build_schedule,
    configs_for_arms,
)
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
from services.experiment.llm import ResearchLLMResponse
from services.experiment.models import (
    ExperimentProfile,
    FrozenRagChunk,
    RetrievalTrace,
)
from services.experiment.runner import ResearchExperimentRunner
from scripts import run_benchmark


class _CompletionClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        config: ExperimentConfig,
    ) -> ResearchLLMResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "condition": config.condition,
            }
        )
        return ResearchLLMResponse(
            content=f"answer-{config.condition}",
            model_actual="fixed-model",
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
            },
            finish_reason="stop",
        )


class _RagProvider:
    async def prewarm(self) -> None:
        return None

    async def retrieve(
        self, query: str, config: ExperimentConfig
    ) -> RetrievalTrace:
        return RetrievalTrace(
            query=query,
            top_k=config.rag_top_k,
            threshold=config.rag_threshold,
            retrieval_latency_ms=1.0,
            corpus_version=config.corpus_version,
            corpus_hash=config.corpus_hash,
            chunks=(
                FrozenRagChunk(
                    chunk_id="fixture-chunk",
                    rank=1,
                    title="Fixture",
                    content="frozen evidence",
                    content_hash="a" * 64,
                    source={
                        "dataset_file": "fixture.json",
                        "source_record_id": "fixture:1",
                    },
                    cosine_similarity=0.9,
                    fusion_score=0.01,
                ),
            ),
        )


def _profile() -> ExperimentProfile:
    return ExperimentProfile(
        profile_id="batch-profile",
        age=30,
        sex="female",
        height_cm=165,
        weight_kg=60,
        activity_level="moderate",
        goal="maintain",
        target_weight_kg=60,
        dietary_restrictions=("vegetarian",),
        allergies=("peanut",),
    )


def _case(case_id: str = "batch-case-001") -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        category=BenchmarkCategory.GENERAL_NUTRITION,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query="Give a short nutrition answer.",
        profile=_profile(),
        required_facts=(),
        required_constraints=(),
        reference_sources=(),
        objective_expected_values=(),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.NOT_ANSWERABLE_FROM_CORPUS,
            research_questions=("RQ1", "RQ2"),
            objective_metrics=(),
            human_rubrics=("factual_correctness",),
        ),
    )


def _benchmark() -> BenchmarkFile:
    return BenchmarkFile(
        benchmark_version=BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        cases=(_case(),),
    )


def _manifest() -> BenchmarkManifest:
    return BenchmarkManifest(
        benchmark_version=BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        case_count=1,
        category_counts={"general_nutrition": 1},
        split_counts={"development": 1},
        benchmark_file_sha256="b" * 64,
        creation_commit="fixture-commit",
        creation_worktree_clean=True,
        rubric_version=RUBRIC_VERSION,
        reference_source_versions={},
        corpus_version="offline-v1-636",
        manifest_hash="c" * 64,
    )


def _template() -> ExperimentConfig:
    return ExperimentConfig(
        condition="S0",
        model=NUTRITION_ABLATION_MODEL,
        prompt_version=NUTRITION_ABLATION_PROMPT_VERSION,
    )


def _write_verified_benchmark(tmp_path: Path) -> tuple[Path, Path]:
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
    manifest_path = tmp_path / "benchmark.manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest_payload, indent=2))
    return benchmark_path, manifest_path


def test_schedule_is_complete_and_reproducible() -> None:
    benchmark = _benchmark()
    first = build_schedule(
        benchmark,
        split=BenchmarkSplit.DEVELOPMENT,
        repetitions=2,
        schedule_seed=42,
    )
    second = build_schedule(
        benchmark,
        split=BenchmarkSplit.DEVELOPMENT,
        repetitions=2,
        schedule_seed=42,
    )

    assert first == second
    assert len(first) == 8
    assert {item.condition for item in first} == set(NUTRITION_ABLATION_ARMS)
    assert {item.repetition_index for item in first} == {1, 2}
    assert [item.schedule_index for item in first] == list(range(1, 9))
    assert len(
        {
            (item.test_case_id, item.condition, item.repetition_index)
            for item in first
        }
    ) == 8


def test_arm_configs_vary_only_condition_and_derived_treatments() -> None:
    configs = configs_for_arms(_template())
    projections = []
    for config in configs.values():
        payload = config.serialize()
        for field in (
            "condition",
            "profile_enabled",
            "rag_enabled",
            "nutrition_tools_enabled",
        ):
            payload.pop(field)
        projections.append(payload)

    assert all(projection == projections[0] for projection in projections[1:])
    assert configs["S0"].profile_enabled is False
    assert configs["S1"].rag_enabled is True
    assert configs["S2"].nutrition_tools_enabled is True
    assert configs["S3"].profile_enabled is True


def test_final_execution_rejects_a_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        run_benchmark,
        "repository_state",
        lambda _: ("dirty-commit", False),
    )

    with pytest.raises(
        RuntimeError, match="EXPERIMENT_FINAL_REQUIRES_CLEAN_WORKTREE"
    ):
        run_benchmark._require_final_execution_state(
            tmp_path, tmp_path / "results.jsonl"
        )


@pytest.mark.asyncio
async def test_plan_only_validates_manifest_and_prints_complete_schedule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    benchmark_path, manifest_path = _write_verified_benchmark(tmp_path)
    output_path = tmp_path / "must-not-exist.jsonl"
    args = run_benchmark._parser().parse_args(
        [
            "--benchmark",
            str(benchmark_path),
            "--manifest",
            str(manifest_path),
            "--split",
            "development",
            "--repetitions",
            "2",
            "--schedule-seed",
            "42",
            "--output",
            str(output_path),
            "--plan-only",
        ]
    )

    exit_code = await run_benchmark._run(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["scheduled_runs"] == 8
    assert payload["arms"] == list(NUTRITION_ABLATION_ARMS)
    assert payload["schedule_seed"] == 42
    assert len(payload["schedule"]) == 8
    assert output_path.exists() is False


@pytest.mark.asyncio
async def test_batch_runner_persists_paired_metadata_and_all_runs(
    tmp_path: Path,
) -> None:
    client = _CompletionClient()
    single_runner = ResearchExperimentRunner(
        completion_client=client,
        rag_provider=_RagProvider(),
        repository_probe=lambda: ("clean-commit", True),
    )
    output = tmp_path / "batch.jsonl"

    summary = await NutritionAblationBatchRunner(single_runner).run(
        experiment_id="batch-test",
        benchmark=_benchmark(),
        manifest=_manifest(),
        split=BenchmarkSplit.DEVELOPMENT,
        configs=configs_for_arms(_template()),
        repetitions=2,
        schedule_seed=42,
        output_path=output,
    )

    rows = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert summary.scheduled_runs == 8
    assert summary.completed_runs == 8
    assert summary.failed_runs == 0
    assert len(rows) == 8
    assert len(client.calls) == 8
    assert {row["condition"] for row in rows} == set(NUTRITION_ABLATION_ARMS)
    assert {row["repetition_index"] for row in rows} == {1, 2}
    assert [row["schedule_index"] for row in rows] == list(range(1, 9))
    assert all(row["benchmark_version"] == BENCHMARK_VERSION for row in rows)
    assert all(row["benchmark_file_sha256"] == "b" * 64 for row in rows)
    assert all(row["benchmark_manifest_hash"] == "c" * 64 for row in rows)
    assert all(row["benchmark_case_hash"] == _case().case_hash() for row in rows)
    assert all(row["benchmark_split"] == "development" for row in rows)
    assert all(row["batch_schedule_seed"] == 42 for row in rows)
    assert all(row["git_commit"] == "clean-commit" for row in rows)
    assert all(row["worktree_clean"] is True for row in rows)

    by_condition = {row["condition"]: row for row in rows}
    assert by_condition["S0"]["profile_snapshot_or_null"] is None
    assert by_condition["S1"]["profile_snapshot_or_null"] is None
    assert by_condition["S2"]["profile_snapshot_or_null"] is None
    assert by_condition["S3"]["profile_snapshot_or_null"]["profile_id"] == (
        "batch-profile"
    )
    assert by_condition["S0"]["retrieval_trace"] is None
    assert by_condition["S1"]["retrieval_trace"] is not None
    assert by_condition["S2"]["tools_offered"] == ["calculate_tdee"]
    assert by_condition["S3"]["tools_offered"] == ["calculate_tdee"]
