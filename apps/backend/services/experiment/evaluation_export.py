"""Integrity-gated export of deterministic benchmark evaluations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from services.experiment.benchmark import (
    BenchmarkCase,
    BenchmarkFile,
    BenchmarkManifest,
    BenchmarkSplit,
)
from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    ExperimentConfig,
    NutritionAblationArm,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.evaluation import (
    EvaluationAnnotations,
    MetricResult,
    evaluate_record,
)
from services.experiment.records import ExperimentRunRecord

EVALUATION_EXPORT_SCHEMA_VERSION = "1.0"
_DERIVED_CONFIG_FIELDS = {
    "profile_enabled",
    "rag_enabled",
    "nutrition_tools_enabled",
    "fallback_models",
}


class RunAnnotation(BaseModel):
    """Optional explicit human annotation keyed to one immutable run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    annotations: EvaluationAnnotations


class RunEvaluation(BaseModel):
    """One auditable evaluation row; failed runs deliberately have no metrics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = EVALUATION_EXPORT_SCHEMA_VERSION
    experiment_id: str
    benchmark_version: str
    benchmark_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str
    condition: NutritionAblationArm
    test_case_id: str
    repetition_index: int = Field(ge=1)
    schedule_index: int = Field(ge=1)
    evaluation_status: Literal["scored", "run_error"]
    record_error: str | None
    metrics: tuple[MetricResult, ...]


def load_run_records(path: Path) -> tuple[ExperimentRunRecord, ...]:
    records: list[ExperimentRunRecord] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(ExperimentRunRecord.model_validate_json(line))
                except Exception as exc:
                    raise ExperimentError(
                        "EXPERIMENT_RUN_RECORD_INVALID",
                        f"line={line_number}; {safe_error_detail(exc)}",
                    ) from exc
    except ExperimentError:
        raise
    except OSError as exc:
        raise ExperimentError(
            "EXPERIMENT_RUN_RECORDS_UNREADABLE", safe_error_detail(exc)
        ) from exc
    if not records:
        raise ExperimentError("EXPERIMENT_RUN_RECORDS_EMPTY")
    return tuple(records)


def load_annotations(path: Path) -> dict[str, EvaluationAnnotations]:
    annotations: dict[str, EvaluationAnnotations] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = RunAnnotation.model_validate_json(line)
                except Exception as exc:
                    raise ExperimentError(
                        "EXPERIMENT_ANNOTATION_INVALID",
                        f"line={line_number}; {safe_error_detail(exc)}",
                    ) from exc
                if row.run_id in annotations:
                    raise ExperimentError(
                        "EXPERIMENT_ANNOTATION_DUPLICATED", row.run_id
                    )
                annotations[row.run_id] = row.annotations
    except ExperimentError:
        raise
    except OSError as exc:
        raise ExperimentError(
            "EXPERIMENT_ANNOTATIONS_UNREADABLE", safe_error_detail(exc)
        ) from exc
    return annotations


def select_experiment_records(
    records: Sequence[ExperimentRunRecord], experiment_id: str | None
) -> tuple[ExperimentRunRecord, ...]:
    experiment_ids = {record.experiment_id for record in records}
    if experiment_id is None:
        if len(experiment_ids) != 1:
            raise ExperimentError(
                "EXPERIMENT_ID_REQUIRED", ",".join(sorted(experiment_ids))
            )
        return tuple(records)
    selected = tuple(
        record for record in records if record.experiment_id == experiment_id
    )
    if not selected:
        raise ExperimentError("EXPERIMENT_ID_NOT_FOUND", experiment_id)
    return selected


def _validated_config(record: ExperimentRunRecord) -> ExperimentConfig:
    payload = dict(record.config)
    for field in _DERIVED_CONFIG_FIELDS:
        payload.pop(field, None)
    try:
        config = ExperimentConfig.model_validate(payload)
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_RECORD_CONFIG_INVALID",
            f"run_id={record.run_id}; {safe_error_detail(exc)}",
        ) from exc
    if (
        config.serialize() != record.config
        or config.config_hash() != record.config_hash
    ):
        raise ExperimentError("EXPERIMENT_RECORD_CONFIG_HASH_MISMATCH", record.run_id)
    return config


def _validate_record(
    record: ExperimentRunRecord,
    *,
    case: BenchmarkCase,
    manifest: BenchmarkManifest,
    split: BenchmarkSplit,
) -> ExperimentConfig:
    expected_metadata = (
        record.benchmark_version == manifest.benchmark_version
        and record.benchmark_file_sha256 == manifest.benchmark_file_sha256
        and record.benchmark_manifest_hash == manifest.manifest_hash
        and record.benchmark_case_hash == case.case_hash()
        and record.benchmark_split == split.value
        and record.user_query == case.user_query
    )
    if not expected_metadata:
        raise ExperimentError("EXPERIMENT_RECORD_BENCHMARK_MISMATCH", record.run_id)
    if record.repetition_index is None or record.schedule_index is None:
        raise ExperimentError("EXPERIMENT_RECORD_BATCH_METADATA_MISSING", record.run_id)

    config = _validated_config(record)
    if (
        config.condition != record.condition
        or config.protocol_id != record.protocol_id
        or config.model != record.model_requested
        or config.temperature != record.temperature
        or config.seed != record.seed
    ):
        raise ExperimentError("EXPERIMENT_RECORD_CONTROL_MISMATCH", record.run_id)

    expected_profile = (
        case.profile.model_dump(mode="json") if config.profile_enabled else None
    )
    if record.profile_snapshot_or_null != expected_profile:
        raise ExperimentError("EXPERIMENT_RECORD_PROFILE_MISMATCH", record.run_id)
    expected_tools = ["calculate_tdee"] if config.nutrition_tools_enabled else []
    if record.tools_offered != expected_tools:
        raise ExperimentError("EXPERIMENT_RECORD_TOOLS_MISMATCH", record.run_id)

    if record.retrieval_trace is not None:
        if not config.rag_enabled:
            raise ExperimentError("EXPERIMENT_RECORD_RAG_MISMATCH", record.run_id)
        if (
            record.retrieval_trace.get("corpus_version") != config.corpus_version
            or record.retrieval_trace.get("corpus_hash") != config.corpus_hash
        ):
            raise ExperimentError("EXPERIMENT_RECORD_CORPUS_MISMATCH", record.run_id)
    elif config.rag_enabled and record.error is None:
        raise ExperimentError("EXPERIMENT_RECORD_RAG_MISSING", record.run_id)

    if split == BenchmarkSplit.FINAL and record.worktree_clean is not True:
        raise ExperimentError("EXPERIMENT_FINAL_RECORD_NOT_CLEAN", record.run_id)
    return config


def validate_batch_records(
    records: Sequence[ExperimentRunRecord],
    *,
    benchmark: BenchmarkFile,
    manifest: BenchmarkManifest,
    split: BenchmarkSplit,
    expected_arms: Sequence[NutritionAblationArm] = NUTRITION_ABLATION_ARMS,
    repetitions: int = 1,
) -> None:
    if repetitions < 1:
        raise ExperimentError("EXPERIMENT_BATCH_REPETITIONS_INVALID")
    arms = tuple(expected_arms)
    if not arms or len(arms) != len(set(arms)):
        raise ExperimentError("EXPERIMENT_BATCH_ARMS_INVALID")
    if any(arm not in NUTRITION_ABLATION_ARMS for arm in arms):
        raise ExperimentError("EXPERIMENT_BATCH_ARM_INVALID")

    cases = {
        case.case_id: case for case in benchmark.cases if case.split == split
    }
    if not cases:
        raise ExperimentError("EXPERIMENT_BENCHMARK_SPLIT_EMPTY", split.value)

    expected_combinations = {
        (case_id, arm, repetition_index)
        for case_id in cases
        for arm in arms
        for repetition_index in range(1, repetitions + 1)
    }
    actual_combinations: set[tuple[str, str, int]] = set()
    schedule_indexes: list[int] = []
    control_projections: list[dict[str, object]] = []
    requested_models: set[str] = set()
    actual_models: set[str] = set()
    git_commits: set[str] = set()

    for record in records:
        case = cases.get(record.test_case_id)
        if case is None:
            raise ExperimentError("EXPERIMENT_RECORD_CASE_UNKNOWN", record.test_case_id)
        config = _validate_record(
            record, case=case, manifest=manifest, split=split
        )
        combination = (
            record.test_case_id,
            record.condition,
            record.repetition_index,
        )
        if combination in actual_combinations:
            raise ExperimentError("EXPERIMENT_RECORD_COMBINATION_DUPLICATED")
        actual_combinations.add(combination)
        schedule_indexes.append(record.schedule_index)

        projection = config.model_dump(mode="json")
        projection.pop("condition")
        control_projections.append(projection)
        requested_models.add(record.model_requested)
        if record.model_actual is not None:
            actual_models.add(record.model_actual)
        if record.git_commit is None:
            raise ExperimentError("EXPERIMENT_RECORD_COMMIT_MISSING", record.run_id)
        git_commits.add(record.git_commit)

    if actual_combinations != expected_combinations:
        raise ExperimentError(
            "EXPERIMENT_BATCH_INCOMPLETE",
            f"expected={len(expected_combinations)}, actual={len(actual_combinations)}",
        )
    if sorted(schedule_indexes) != list(range(1, len(records) + 1)):
        raise ExperimentError("EXPERIMENT_BATCH_SCHEDULE_INVALID")
    if any(
        projection != control_projections[0]
        for projection in control_projections[1:]
    ):
        raise ExperimentError("EXPERIMENT_BATCH_CONFIG_MISMATCH")
    if len(requested_models) != 1 or len(actual_models) > 1:
        raise ExperimentError("EXPERIMENT_BATCH_MODEL_MISMATCH")
    if len(git_commits) != 1:
        raise ExperimentError("EXPERIMENT_BATCH_COMMIT_MISMATCH")


def evaluate_batch_records(
    records: Sequence[ExperimentRunRecord],
    *,
    benchmark: BenchmarkFile,
    manifest: BenchmarkManifest,
    annotations: Mapping[str, EvaluationAnnotations] | None = None,
) -> tuple[RunEvaluation, ...]:
    case_by_id = {case.case_id: case for case in benchmark.cases}
    annotations = annotations or {}
    unknown_annotations = set(annotations) - {record.run_id for record in records}
    if unknown_annotations:
        raise ExperimentError(
            "EXPERIMENT_ANNOTATION_RUN_UNKNOWN",
            ",".join(sorted(unknown_annotations)),
        )

    exports: list[RunEvaluation] = []
    for record in sorted(records, key=lambda item: item.schedule_index or 0):
        if record.repetition_index is None or record.schedule_index is None:
            raise ExperimentError("EXPERIMENT_RECORD_BATCH_METADATA_MISSING")
        metrics = (
            ()
            if record.error is not None
            else evaluate_record(
                case_by_id[record.test_case_id],
                record,
                annotations.get(record.run_id),
            )
        )
        exports.append(
            RunEvaluation(
                experiment_id=record.experiment_id,
                benchmark_version=manifest.benchmark_version,
                benchmark_manifest_hash=manifest.manifest_hash,
                run_id=record.run_id,
                condition=record.condition,
                test_case_id=record.test_case_id,
                repetition_index=record.repetition_index,
                schedule_index=record.schedule_index,
                evaluation_status=(
                    "run_error" if record.error is not None else "scored"
                ),
                record_error=record.error,
                metrics=metrics,
            )
        )
    return tuple(exports)


def write_evaluations(
    path: Path,
    evaluations: Sequence[RunEvaluation],
    *,
    overwrite: bool = False,
) -> None:
    if path.exists() and not overwrite:
        raise ExperimentError("EXPERIMENT_EVALUATION_OUTPUT_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for evaluation in evaluations:
                handle.write(
                    json.dumps(
                        evaluation.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                handle.write("\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "EVALUATION_EXPORT_SCHEMA_VERSION",
    "RunAnnotation",
    "RunEvaluation",
    "evaluate_batch_records",
    "load_annotations",
    "load_run_records",
    "select_experiment_records",
    "validate_batch_records",
    "write_evaluations",
]
