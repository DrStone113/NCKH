"""Manage staged authoring of the 270-case single-turn development benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.single_turn_benchmark import (
    load_and_verify_single_turn_benchmark,
    load_and_verify_single_turn_candidates,
    load_and_verify_single_turn_review,
    write_single_turn_benchmark,
    write_single_turn_candidate_pack,
    write_single_turn_review,
)


def _reviewed_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("reviewed-at must include a timezone")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create candidates, record transparent AI-assisted technical review, "
            "or promote the single-turn development benchmark."
        )
    )
    parser.add_argument("stage", choices=("candidates", "review", "promote", "verify"))
    parser.add_argument(
        "--pack-dir",
        type=Path,
        default=Path("data/research/benchmark_candidates/single_turn_v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/benchmarks/single_turn_development_v1"),
    )
    parser.add_argument(
        "--calculation-dir",
        type=Path,
        default=Path("data/research/benchmarks/calculation_development_v1"),
    )
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--reviewed-at",
        type=_reviewed_at,
        default=datetime.now(timezone.utc).replace(microsecond=0),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "candidate_path": args.pack_dir / "nutrition_single_turn_candidates_v1.json",
        "candidate_manifest_path": args.pack_dir
        / "nutrition_single_turn_candidates_v1.manifest.json",
        "calculation_benchmark_path": args.calculation_dir
        / "nutrition_calculation_development_v1.json",
        "calculation_manifest_path": args.calculation_dir
        / "nutrition_calculation_development_v1.manifest.json",
        "review_path": args.pack_dir / "nutrition_single_turn_review_completed_v1.json",
        "review_manifest_path": args.pack_dir
        / "nutrition_single_turn_review_completed_v1.manifest.json",
        "benchmark_path": args.output_dir / "nutrition_single_turn_development_v1.json",
        "benchmark_manifest_path": args.output_dir
        / "nutrition_single_turn_development_v1.manifest.json",
    }


def _run(args: argparse.Namespace) -> int:
    paths = _paths(args)
    repo_root = Path(__file__).resolve().parents[3]
    if args.stage == "candidates":
        write_single_turn_candidate_pack(
            candidate_path=paths["candidate_path"],
            candidate_manifest_path=paths["candidate_manifest_path"],
            calculation_benchmark_path=paths["calculation_benchmark_path"],
            calculation_manifest_path=paths["calculation_manifest_path"],
            repo_root=repo_root,
            overwrite=args.overwrite,
        )
        candidates, manifest = load_and_verify_single_turn_candidates(
            candidate_path=paths["candidate_path"],
            candidate_manifest_path=paths["candidate_manifest_path"],
            calculation_benchmark_path=paths["calculation_benchmark_path"],
            calculation_manifest_path=paths["calculation_manifest_path"],
        )
        payload = {
            "stage": "candidates",
            "status": candidates.status,
            "candidate_count": len(candidates.candidates),
            "category_counts": manifest.category_counts,
            "manifest_hash": manifest.manifest_hash,
        }
    elif args.stage == "review":
        if not args.reviewer_id:
            raise ExperimentError("EXPERIMENT_SINGLE_TURN_REVIEWER_REQUIRED")
        write_single_turn_review(
            candidate_path=paths["candidate_path"],
            candidate_manifest_path=paths["candidate_manifest_path"],
            calculation_benchmark_path=paths["calculation_benchmark_path"],
            calculation_manifest_path=paths["calculation_manifest_path"],
            review_path=paths["review_path"],
            review_manifest_path=paths["review_manifest_path"],
            repo_root=repo_root,
            reviewer_id=args.reviewer_id,
            reviewed_at=args.reviewed_at,
            overwrite=args.overwrite,
        )
        _, _, review, manifest = load_and_verify_single_turn_review(
            candidate_path=paths["candidate_path"],
            candidate_manifest_path=paths["candidate_manifest_path"],
            calculation_benchmark_path=paths["calculation_benchmark_path"],
            calculation_manifest_path=paths["calculation_manifest_path"],
            review_path=paths["review_path"],
            review_manifest_path=paths["review_manifest_path"],
        )
        payload = {
            "stage": "review",
            "status": review.status,
            "reviewer_kind": review.reviewer_kind,
            "human_domain_signoff": review.human_domain_signoff,
            "candidate_count": len(review.entries),
            "manifest_hash": manifest.manifest_hash,
        }
    elif args.stage == "promote":
        write_single_turn_benchmark(
            **paths,
            repo_root=repo_root,
            overwrite=args.overwrite,
        )
        benchmark, manifest = load_and_verify_single_turn_benchmark(**paths)
        payload = {
            "stage": "promote",
            "benchmark_version": benchmark.benchmark_version,
            "case_count": len(benchmark.cases),
            "category_counts": manifest.category_counts,
            "manifest_hash": manifest.manifest_hash,
            "human_domain_signoff": manifest.promotion_provenance.human_domain_signoff,
        }
    else:
        benchmark, manifest = load_and_verify_single_turn_benchmark(**paths)
        payload = {
            "stage": "verify",
            "benchmark_version": benchmark.benchmark_version,
            "case_count": len(benchmark.cases),
            "manifest_hash": manifest.manifest_hash,
        }
    print(json.dumps(payload, ensure_ascii=False))
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
        detail = str(exc) if isinstance(exc, ExperimentError) else safe_error_detail(exc)
        print(json.dumps({"error": detail}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
