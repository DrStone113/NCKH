"""Deterministic aggregate analysis for paired nutrition ablation batches."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any, Iterable, Sequence

from services.experiment.benchmark import BenchmarkFile, BenchmarkManifest
from services.experiment.errors import ExperimentError
from services.experiment.evaluation import MetricResult
from services.experiment.evaluation_export import RunEvaluation
from services.experiment.records import ExperimentRunRecord

ANALYSIS_SCHEMA_VERSION = "1.0"
_Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int) -> tuple[float, float] | None:
    """Return a two-sided 95% Wilson score interval for a binomial rate."""

    if total == 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    proportion = successes / total
    denominator = 1 + (_Z_95**2 / total)
    center = (proportion + (_Z_95**2 / (2 * total))) / denominator
    margin = (
        _Z_95
        * math.sqrt(
            proportion * (1 - proportion) / total
            + _Z_95**2 / (4 * total**2)
        )
        / denominator
    )
    return center - margin, center + margin


def exact_mcnemar_p(improved: int, worsened: int) -> float:
    """Two-sided exact McNemar p-value using the binomial distribution."""

    if improved < 0 or worsened < 0:
        raise ValueError("discordant counts cannot be negative")
    discordant = improved + worsened
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(0, min(improved, worsened) + 1)
    ) / (2**discordant)
    return min(1.0, 2 * tail)


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {"n": 0, "mean": None, "median": None, "p95": None}
    ordered = sorted(numbers)
    p95 = (
        ordered[0]
        if len(ordered) == 1
        else statistics.quantiles(ordered, n=100, method="inclusive")[94]
    )
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": p95,
    }


def _rate(successes: int, total: int) -> dict[str, Any]:
    interval = wilson_interval(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": None if total == 0 else successes / total,
        "wilson_95": None if interval is None else list(interval),
    }


def _metric(
    evaluation: RunEvaluation,
    name: str,
    *,
    value_id: str | None = None,
) -> MetricResult | None:
    for metric in evaluation.metrics:
        if metric.metric != name:
            continue
        if value_id is None or metric.details.get("value_id") == value_id:
            return metric
    return None


def _is_correct(metric: MetricResult | None) -> bool:
    return bool(
        metric is not None
        and metric.status == "scored"
        and (
            metric.details.get("within_absolute_tolerance") is True
            or metric.details.get("within_relative_tolerance") is True
        )
    )


def _value_summary(
    evaluations: Sequence[RunEvaluation],
    *,
    metric_name: str,
    value_id: str,
) -> dict[str, Any]:
    metrics = [
        _metric(evaluation, metric_name, value_id=value_id)
        for evaluation in evaluations
    ]
    extracted = [metric for metric in metrics if metric and metric.status == "scored"]
    correct = sum(_is_correct(metric) for metric in metrics)
    return {
        "extraction": _rate(len(extracted), len(metrics)),
        "correct_over_all_runs": _rate(correct, len(metrics)),
        "absolute_error": _distribution(
            float(metric.value)
            for metric in extracted
            if isinstance(metric.value, (int, float))
            and not isinstance(metric.value, bool)
            and math.isfinite(float(metric.value))
        ),
    }


def _all_values_correct(
    evaluation: RunEvaluation,
    value_ids: Sequence[str],
    *,
    metric_name: str,
) -> bool:
    return all(
        _is_correct(_metric(evaluation, metric_name, value_id=value_id))
        for value_id in value_ids
    )


def summarize_development_batch(
    *,
    records: Sequence[ExperimentRunRecord],
    evaluations: Sequence[RunEvaluation],
    benchmark: BenchmarkFile,
    manifest: BenchmarkManifest,
    records_sha256: str,
) -> dict[str, Any]:
    """Aggregate a fully validated, paired development batch."""

    if not records or not evaluations:
        raise ExperimentError("EXPERIMENT_ANALYSIS_EMPTY")
    record_by_run = {record.run_id: record for record in records}
    evaluation_by_run = {evaluation.run_id: evaluation for evaluation in evaluations}
    if len(record_by_run) != len(records) or set(record_by_run) != set(evaluation_by_run):
        raise ExperimentError("EXPERIMENT_ANALYSIS_RUN_MISMATCH")
    if any(evaluation.evaluation_status != "scored" for evaluation in evaluations):
        raise ExperimentError("EXPERIMENT_ANALYSIS_RUN_ERRORS")

    value_ids = tuple(
        dict.fromkeys(
            expected.value_id
            for case in benchmark.cases
            for expected in case.objective_expected_values
        )
    )
    arm_summaries: dict[str, Any] = {}
    answer_correctness: dict[tuple[str, str, int], bool] = {}
    for arm in ("S0", "S1", "S2", "S3"):
        arm_evaluations = sorted(
            (evaluation for evaluation in evaluations if evaluation.condition == arm),
            key=lambda item: (item.test_case_id, item.repetition_index),
        )
        arm_records = [record_by_run[item.run_id] for item in arm_evaluations]
        # calorie-target has a different metric name, so rebuild the four-value
        # predicate explicitly rather than counting it twice under the generic
        # numerical metric.
        all_answer_correct: list[bool] = []
        for evaluation in arm_evaluations:
            correctness = []
            for value_id in value_ids:
                metric_name = (
                    "calorie_target_error"
                    if value_id == "calorie-target"
                    else "numerical_absolute_error"
                )
                correctness.append(
                    _is_correct(
                        _metric(evaluation, metric_name, value_id=value_id)
                    )
                )
            is_all_correct = all(correctness)
            all_answer_correct.append(is_all_correct)
            answer_correctness[
                (evaluation.test_case_id, arm, evaluation.repetition_index)
            ] = is_all_correct

        answer_values = {}
        for value_id in value_ids:
            metric_name = (
                "calorie_target_error"
                if value_id == "calorie-target"
                else "numerical_absolute_error"
            )
            answer_values[value_id] = _value_summary(
                arm_evaluations,
                metric_name=metric_name,
                value_id=value_id,
            )

        tool_values = {
            value_id: _value_summary(
                arm_evaluations,
                metric_name="tool_numerical_absolute_error",
                value_id=value_id,
            )
            for value_id in value_ids
        }
        tool_all_correct = [
            _all_values_correct(
                evaluation,
                value_ids,
                metric_name="tool_numerical_absolute_error",
            )
            for evaluation in arm_evaluations
        ]
        invoked = [
            _metric(evaluation, "calculate_tdee_tool_invoked")
            for evaluation in arm_evaluations
        ]
        succeeded = [
            _metric(evaluation, "calculate_tdee_tool_succeeded")
            for evaluation in arm_evaluations
        ]
        argument_match = [
            _metric(evaluation, "calculate_tdee_argument_match_rate")
            for evaluation in arm_evaluations
        ]
        total_tokens = [
            int((record.token_usage or {}).get("total_tokens", 0))
            for record in arm_records
            if (record.token_usage or {}).get("total_tokens") is not None
        ]
        arm_summaries[arm] = {
            "runs": len(arm_evaluations),
            "answer": {
                "all_values_correct": _rate(
                    sum(all_answer_correct), len(all_answer_correct)
                ),
                "by_value": answer_values,
            },
            "tool": {
                "invoked": _rate(
                    sum(metric is not None and metric.value == 1 for metric in invoked),
                    sum(metric is not None and metric.status == "scored" for metric in invoked),
                ),
                "succeeded": _rate(
                    sum(metric is not None and metric.value == 1 for metric in succeeded),
                    sum(metric is not None and metric.status == "scored" for metric in succeeded),
                ),
                "arguments_exact": _rate(
                    sum(metric is not None and metric.value == 1 for metric in argument_match),
                    sum(metric is not None and metric.status == "scored" for metric in argument_match),
                ),
                "all_values_correct": _rate(
                    sum(tool_all_correct),
                    sum(
                        _metric(evaluation, "calculate_tdee_tool_invoked")
                        is not None
                        and _metric(evaluation, "calculate_tdee_tool_invoked").status
                        == "scored"
                        for evaluation in arm_evaluations
                    ),
                ),
                "by_value": tool_values,
            },
            "latency_ms": _distribution(record.latency_ms for record in arm_records),
            "total_tokens": _distribution(total_tokens),
            "finish_reasons": dict(
                sorted(
                    Counter(
                        reason
                        for record in arm_records
                        for reason in record.completion_finish_reasons
                    ).items()
                )
            ),
        }

    def paired_comparison(baseline: str, treatment: str) -> dict[str, Any]:
        paired = []
        for case in benchmark.cases:
            repetitions = sorted(
                evaluation.repetition_index
                for evaluation in evaluations
                if evaluation.test_case_id == case.case_id
                and evaluation.condition == baseline
            )
            for repetition in repetitions:
                paired.append(
                    (
                        answer_correctness[(case.case_id, baseline, repetition)],
                        answer_correctness[(case.case_id, treatment, repetition)],
                    )
                )
        improved = sum(not before and after for before, after in paired)
        worsened = sum(before and not after for before, after in paired)
        baseline_correct = sum(before for before, _ in paired)
        treatment_correct = sum(after for _, after in paired)
        return {
            "baseline": baseline,
            "treatment": treatment,
            "pairs": len(paired),
            "baseline_correct": baseline_correct,
            "treatment_correct": treatment_correct,
            "absolute_rate_difference": (
                treatment_correct - baseline_correct
            ) / len(paired),
            "improved": improved,
            "worsened": worsened,
            "both_correct": sum(before and after for before, after in paired),
            "both_incorrect": sum(
                not before and not after for before, after in paired
            ),
            "exact_mcnemar_p_two_sided": exact_mcnemar_p(improved, worsened),
        }

    requested_models = sorted({record.model_requested for record in records})
    actual_models = sorted(
        {record.model_actual for record in records if record.model_actual is not None}
    )
    commits = sorted({record.git_commit for record in records})
    config = records[0].config
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "classification": {
            "artifact_class": "DEVELOPMENT_ONLY",
            "confirmatory_evidence": False,
            "clinical_validation": False,
            "production_rollout_authority": False,
        },
        "experiment": {
            "experiment_id": records[0].experiment_id,
            "benchmark_version": manifest.benchmark_version,
            "benchmark_manifest_hash": manifest.manifest_hash,
            "benchmark_file_sha256": manifest.benchmark_file_sha256,
            "records_sha256": records_sha256,
            "run_count": len(records),
            "case_count": len(benchmark.cases),
            "requested_models": requested_models,
            "actual_models": actual_models,
            "execution_commits": commits,
            "protocol_id": records[0].protocol_id,
            "prompt_version": config.get("prompt_version"),
            "temperature": config.get("temperature"),
            "max_tokens": config.get("max_tokens"),
            "rag_top_k": config.get("rag_top_k"),
            "rag_threshold": config.get("rag_threshold"),
            "corpus_version": config.get("corpus_version"),
            "corpus_hash": config.get("corpus_hash"),
        },
        "arms": arm_summaries,
        "paired_answer_comparisons": {
            "S1_to_S2": paired_comparison("S1", "S2"),
            "S2_to_S3_descriptive_only": paired_comparison("S2", "S3"),
        },
        "interpretation": {
            "primary_development_contrast": "S1_to_S2",
            "rq1_supported_by_this_benchmark": False,
            "rq3_supported_by_this_benchmark": False,
            "notes": [
                "Calculation cases have no source-linked knowledge gold, so S0/S1 do not test RQ1.",
                "Queries contain the same explicit profile facts available to S3, so S2/S3 do not isolate hidden-profile personalization for RQ3.",
                "Missing answer values count as incorrect in all-values correctness.",
                "Tool accuracy includes model argument selection and the deterministic tool result; it is not substituted for answer accuracy.",
            ],
        },
    }


__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "exact_mcnemar_p",
    "summarize_development_batch",
    "wilson_interval",
]
