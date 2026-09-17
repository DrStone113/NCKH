"""Promote the reviewed calculation pack to a development-only benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from services.experiment.benchmark_promotion import (
    load_and_verify_promoted_calculation_benchmark,
    write_calculation_development_benchmark,
)
from services.experiment.errors import ExperimentError, safe_error_detail


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote a unanimously approved calculation review to a "
            "development-only runnable benchmark."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("data/research/benchmark_candidates/calculation_v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/benchmarks/calculation_development_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    source: Path = args.source_dir
    output: Path = args.output_dir
    return {
        "candidate_path": source / "nutrition_calculation_candidates_v1.json",
        "candidate_manifest_path": (
            source / "nutrition_calculation_candidates_v1.manifest.json"
        ),
        "review_template_path": (
            source / "nutrition_calculation_review_template_v1.csv"
        ),
        "completed_review_path": (
            source / "nutrition_calculation_review_completed_v1.csv"
        ),
        "review_manifest_path": (
            source / "nutrition_calculation_review_completed_v1.manifest.json"
        ),
        "benchmark_path": output / "nutrition_calculation_development_v1.json",
        "benchmark_manifest_path": (
            output / "nutrition_calculation_development_v1.manifest.json"
        ),
    }


def _run(args: argparse.Namespace) -> int:
    paths = _paths(args)
    repo_root = Path(__file__).resolve().parents[3]
    write_calculation_development_benchmark(
        **paths,
        repo_root=repo_root,
        overwrite=args.overwrite,
    )
    benchmark, manifest = load_and_verify_promoted_calculation_benchmark(**paths)
    provenance = manifest.promotion_provenance
    print(
        json.dumps(
            {
                "benchmark_version": benchmark.benchmark_version,
                "case_count": len(benchmark.cases),
                "split_counts": manifest.split_counts,
                "category_counts": manifest.category_counts,
                "benchmark_file_sha256": manifest.benchmark_file_sha256,
                "manifest_hash": manifest.manifest_hash,
                "promotion_scope": (
                    provenance.promotion_scope if provenance is not None else None
                ),
                "human_domain_signoff": (
                    provenance.human_domain_signoff
                    if provenance is not None
                    else None
                ),
                "benchmark": str(paths["benchmark_path"].resolve()),
                "manifest": str(paths["benchmark_manifest_path"].resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


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
