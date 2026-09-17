"""Generate the deterministic 60-case calculation review candidate pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from services.experiment.benchmark_authoring import (
    load_and_verify_calculation_candidate_pack,
    write_calculation_candidate_pack,
)
from services.experiment.errors import ExperimentError, safe_error_detail


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate 60 deterministic nutrition calculation candidates and "
            "a CSV human-review template. The output is not a frozen benchmark."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/benchmark_candidates/calculation_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[3]
    candidate_path, manifest_path, review_path = (
        write_calculation_candidate_pack(
            args.output_dir,
            repo_root=repo_root,
            overwrite=args.overwrite,
        )
    )
    candidate_file, manifest = load_and_verify_calculation_candidate_pack(
        candidate_path, manifest_path, review_path
    )
    print(
        json.dumps(
            {
                "status": candidate_file.status,
                "candidate_count": manifest.candidate_count,
                "policy_version": manifest.policy_version,
                "generation_commit": manifest.generation_commit,
                "candidate_file": str(candidate_path.resolve()),
                "manifest_file": str(manifest_path.resolve()),
                "review_template": str(review_path.resolve()),
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
