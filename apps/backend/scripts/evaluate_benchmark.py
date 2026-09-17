"""Validate and export deterministic metrics from S0-S3 batch records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence, cast

from pydantic import ValidationError

from services.experiment.benchmark import (
    BenchmarkSplit,
    load_and_verify_benchmark,
)
from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NutritionAblationArm,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.evaluation_export import (
    evaluate_batch_records,
    load_annotations,
    load_run_records,
    select_experiment_records,
    validate_batch_records,
    write_evaluations,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Integrity-check a paired S0-S3 batch and export deterministic "
            "metric rows without an LLM judge."
        )
    )
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument(
        "--split",
        choices=tuple(split.value for split in BenchmarkSplit),
        required=True,
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=NUTRITION_ABLATION_ARMS,
        default=list(NUTRITION_ABLATION_ARMS),
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--experiment-id")
    parser.add_argument(
        "--annotations",
        type=Path,
        help="Optional JSONL human annotations keyed by run_id.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/nutrition-ablation-evaluations.jsonl"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _selected_arms(args: argparse.Namespace) -> tuple[NutritionAblationArm, ...]:
    return cast(tuple[NutritionAblationArm, ...], tuple(args.arms))


def _run(args: argparse.Namespace) -> int:
    benchmark, manifest = load_and_verify_benchmark(
        args.benchmark, args.manifest
    )
    records = select_experiment_records(
        load_run_records(args.records), args.experiment_id
    )
    split = BenchmarkSplit(args.split)
    validate_batch_records(
        records,
        benchmark=benchmark,
        manifest=manifest,
        split=split,
        expected_arms=_selected_arms(args),
        repetitions=args.repetitions,
    )
    annotations = (
        load_annotations(args.annotations) if args.annotations is not None else {}
    )
    evaluations = evaluate_batch_records(
        records,
        benchmark=benchmark,
        manifest=manifest,
        annotations=annotations,
    )
    write_evaluations(args.output, evaluations, overwrite=args.overwrite)

    run_errors = sum(
        evaluation.evaluation_status == "run_error"
        for evaluation in evaluations
    )
    print(
        json.dumps(
            {
                "experiment_id": records[0].experiment_id,
                "benchmark_version": manifest.benchmark_version,
                "split": split.value,
                "evaluated_runs": len(evaluations),
                "scored_runs": len(evaluations) - run_errors,
                "run_errors": run_errors,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 1 if run_errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (
        ExperimentError,
        OSError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        detail = (
            str(exc)
            if isinstance(exc, ExperimentError)
            else safe_error_detail(exc)
        )
        print(json.dumps({"error": detail}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
