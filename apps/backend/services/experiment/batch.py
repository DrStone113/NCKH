"""Deterministic paired batch execution for the S0-S3 research protocol."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from services.experiment.benchmark import (
    BenchmarkFile,
    BenchmarkManifest,
    BenchmarkSplit,
)
from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    ExperimentConfig,
    NutritionAblationArm,
)
from services.experiment.errors import ExperimentError
from services.experiment.models import ExperimentTestCase
from services.experiment.records import ExperimentRunRecord, append_jsonl
from services.experiment.runner import ResearchExperimentRunner


class BatchScheduleItem(BaseModel):
    """One immutable position in a reproducible paired-run schedule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schedule_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    condition: NutritionAblationArm
    test_case_id: str = Field(min_length=1)
    benchmark_case_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class BatchRunSummary(BaseModel):
    """Compact result returned after every scheduled record is persisted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    benchmark_version: str
    benchmark_split: BenchmarkSplit
    arms: tuple[NutritionAblationArm, ...]
    repetitions: int = Field(ge=1)
    schedule_seed: int
    scheduled_runs: int = Field(ge=1)
    resumed_runs: int = Field(default=0, ge=0)
    executed_runs: int = Field(default=0, ge=0)
    completed_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)


def configs_for_arms(
    template: ExperimentConfig,
    arms: Sequence[NutritionAblationArm] = NUTRITION_ABLATION_ARMS,
) -> dict[NutritionAblationArm, ExperimentConfig]:
    """Clone all non-treatment controls and vary only the condition."""

    selected = tuple(arms)
    if not selected:
        raise ExperimentError("EXPERIMENT_BATCH_ARMS_EMPTY")
    if len(selected) != len(set(selected)):
        raise ExperimentError("EXPERIMENT_BATCH_ARMS_DUPLICATED")

    base = template.model_dump(mode="python")
    configs: dict[NutritionAblationArm, ExperimentConfig] = {}
    for arm in selected:
        if arm not in NUTRITION_ABLATION_ARMS:
            raise ExperimentError("EXPERIMENT_BATCH_ARM_INVALID", str(arm))
        configs[arm] = ExperimentConfig.model_validate(
            {**base, "condition": arm}
        )

    _validate_comparable_configs(configs)
    return configs


def _validate_comparable_configs(
    configs: Mapping[NutritionAblationArm, ExperimentConfig],
) -> None:
    if any(config.condition != arm for arm, config in configs.items()):
        raise ExperimentError("EXPERIMENT_BATCH_CONFIG_MISMATCH")
    projections = []
    for config in configs.values():
        projection = config.model_dump(mode="json")
        projection.pop("condition")
        projections.append(projection)
    if any(projection != projections[0] for projection in projections[1:]):
        raise ExperimentError("EXPERIMENT_BATCH_CONFIG_MISMATCH")


def build_schedule(
    benchmark: BenchmarkFile,
    *,
    split: BenchmarkSplit,
    arms: Sequence[NutritionAblationArm] = NUTRITION_ABLATION_ARMS,
    repetitions: int = 1,
    schedule_seed: int,
) -> tuple[BatchScheduleItem, ...]:
    """Build a complete, cross-runtime-stable schedule using SHA-256 order."""

    if repetitions < 1:
        raise ExperimentError("EXPERIMENT_BATCH_REPETITIONS_INVALID")
    selected_arms = tuple(arms)
    if not selected_arms:
        raise ExperimentError("EXPERIMENT_BATCH_ARMS_EMPTY")
    if len(selected_arms) != len(set(selected_arms)):
        raise ExperimentError("EXPERIMENT_BATCH_ARMS_DUPLICATED")
    if any(arm not in NUTRITION_ABLATION_ARMS for arm in selected_arms):
        raise ExperimentError("EXPERIMENT_BATCH_ARM_INVALID")

    cases = tuple(
        sorted(
            (case for case in benchmark.cases if case.split == split),
            key=lambda case: case.case_id,
        )
    )
    if not cases:
        raise ExperimentError("EXPERIMENT_BENCHMARK_SPLIT_EMPTY", split.value)

    candidates: list[tuple[str, int, NutritionAblationArm, str, str]] = []
    for repetition_index in range(1, repetitions + 1):
        for case in cases:
            case_hash = case.case_hash()
            for arm in selected_arms:
                identity = (
                    f"{schedule_seed}\x1f{repetition_index}\x1f"
                    f"{case.case_id}\x1f{arm}"
                )
                order_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                candidates.append(
                    (
                        order_key,
                        repetition_index,
                        arm,
                        case.case_id,
                        case_hash,
                    )
                )

    candidates.sort(key=lambda item: (item[0], item[1], item[3], item[2]))
    return tuple(
        BatchScheduleItem(
            schedule_index=index,
            repetition_index=repetition_index,
            condition=arm,
            test_case_id=case_id,
            benchmark_case_hash=case_hash,
        )
        for index, (_, repetition_index, arm, case_id, case_hash) in enumerate(
            candidates, start=1
        )
    )


def validate_resume_prefix(
    records: Sequence[ExperimentRunRecord],
    schedule: Sequence[BatchScheduleItem],
    *,
    experiment_id: str,
    benchmark: BenchmarkFile,
    manifest: BenchmarkManifest,
    split: BenchmarkSplit,
    configs: Mapping[NutritionAblationArm, ExperimentConfig],
    schedule_seed: int,
) -> None:
    """Require an exact, duplicate-free prefix of the immutable schedule."""

    if len(records) > len(schedule):
        raise ExperimentError("EXPERIMENT_BATCH_RESUME_TOO_MANY_RECORDS")
    for index, record in enumerate(records):
        item = schedule[index]
        config = configs[item.condition]
        checks = (
            record.schedule_index == item.schedule_index,
            record.repetition_index == item.repetition_index,
            record.condition == item.condition,
            record.test_case_id == item.test_case_id,
            record.benchmark_case_hash == item.benchmark_case_hash,
            record.experiment_id == experiment_id,
            record.benchmark_version == benchmark.benchmark_version,
            record.benchmark_file_sha256 == manifest.benchmark_file_sha256,
            record.benchmark_manifest_hash == manifest.manifest_hash,
            record.benchmark_split == split.value,
            record.batch_schedule_seed == schedule_seed,
            record.config_hash == config.config_hash(),
            record.config == config.serialize(),
            record.model_requested == config.model,
        )
        if not all(checks):
            raise ExperimentError(
                "EXPERIMENT_BATCH_RESUME_PREFIX_MISMATCH",
                f"record={index + 1}",
            )
class NutritionAblationBatchRunner:
    """Execute and durably append every item in a verified benchmark split."""

    def __init__(self, runner: ResearchExperimentRunner) -> None:
        self.runner = runner

    async def run(
        self,
        *,
        experiment_id: str,
        benchmark: BenchmarkFile,
        manifest: BenchmarkManifest,
        split: BenchmarkSplit,
        configs: Mapping[NutritionAblationArm, ExperimentConfig],
        repetitions: int,
        schedule_seed: int,
        output_path: Path,
        resume_records: Sequence[ExperimentRunRecord] = (),
    ) -> BatchRunSummary:
        if manifest.benchmark_version != benchmark.benchmark_version:
            raise ExperimentError("EXPERIMENT_BENCHMARK_VERSION_MISMATCH")
        if not configs:
            raise ExperimentError("EXPERIMENT_BATCH_ARMS_EMPTY")
        _validate_comparable_configs(configs)
        if any(
            config.corpus_version != manifest.corpus_version
            for config in configs.values()
        ):
            raise ExperimentError("EXPERIMENT_BENCHMARK_CORPUS_MISMATCH")

        arms = tuple(configs)
        schedule = build_schedule(
            benchmark,
            split=split,
            arms=arms,
            repetitions=repetitions,
            schedule_seed=schedule_seed,
        )
        validate_resume_prefix(
            resume_records,
            schedule,
            experiment_id=experiment_id,
            benchmark=benchmark,
            manifest=manifest,
            split=split,
            configs=configs,
            schedule_seed=schedule_seed,
        )
        case_by_id = {case.case_id: case for case in benchmark.cases}
        failed_runs = sum(record.error is not None for record in resume_records)
        resumed_runs = len(resume_records)

        for item in schedule[resumed_runs:]:
            case = case_by_id[item.test_case_id]
            record = await self.runner.run(
                experiment_id=experiment_id,
                config=configs[item.condition],
                test_case=ExperimentTestCase(
                    test_case_id=case.case_id,
                    user_query=case.user_query,
                    profile=case.profile,
                ),
            )
            record = record.model_copy(
                update={
                    "benchmark_version": benchmark.benchmark_version,
                    "benchmark_file_sha256": manifest.benchmark_file_sha256,
                    "benchmark_manifest_hash": manifest.manifest_hash,
                    "benchmark_case_hash": item.benchmark_case_hash,
                    "benchmark_split": split.value,
                    "batch_schedule_seed": schedule_seed,
                    "repetition_index": item.repetition_index,
                    "schedule_index": item.schedule_index,
                }
            )
            append_jsonl(output_path, record)
            if record.error is not None:
                failed_runs += 1

        return BatchRunSummary(
            experiment_id=experiment_id,
            benchmark_version=benchmark.benchmark_version,
            benchmark_split=split,
            arms=arms,
            repetitions=repetitions,
            schedule_seed=schedule_seed,
            scheduled_runs=len(schedule),
            resumed_runs=resumed_runs,
            executed_runs=len(schedule) - resumed_runs,
            completed_runs=len(schedule) - failed_runs,
            failed_runs=failed_runs,
        )


__all__ = [
    "BatchRunSummary",
    "BatchScheduleItem",
    "NutritionAblationBatchRunner",
    "build_schedule",
    "configs_for_arms",
    "validate_resume_prefix",
]
