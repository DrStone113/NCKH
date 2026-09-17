"""Complete and verify the AI-assisted technical review of calculation cases."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from services.experiment.benchmark_review import (
    load_and_verify_completed_calculation_review,
    write_completed_calculation_review,
)
from services.experiment.errors import ExperimentError, safe_error_detail


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_reviewed_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("reviewed-at must include a timezone")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Independently recalculate and technically review all 60 nutrition "
            "calculation candidates. This does not impersonate human signoff."
        )
    )
    parser.add_argument(
        "--pack-dir",
        type=Path,
        default=Path("data/research/benchmark_candidates/calculation_v1"),
    )
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=_parse_reviewed_at, default=_utc_now())
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> int:
    pack_dir: Path = args.pack_dir
    candidate_path = pack_dir / "nutrition_calculation_candidates_v1.json"
    candidate_manifest_path = (
        pack_dir / "nutrition_calculation_candidates_v1.manifest.json"
    )
    review_template_path = (
        pack_dir / "nutrition_calculation_review_template_v1.csv"
    )
    completed_review_path = (
        pack_dir / "nutrition_calculation_review_completed_v1.csv"
    )
    review_manifest_path = (
        pack_dir / "nutrition_calculation_review_completed_v1.manifest.json"
    )
    repo_root = Path(__file__).resolve().parents[3]
    write_completed_calculation_review(
        candidate_path=candidate_path,
        candidate_manifest_path=candidate_manifest_path,
        review_template_path=review_template_path,
        completed_review_path=completed_review_path,
        review_manifest_path=review_manifest_path,
        repo_root=repo_root,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        overwrite=args.overwrite,
    )
    candidate_file, _, manifest = load_and_verify_completed_calculation_review(
        candidate_path=candidate_path,
        candidate_manifest_path=candidate_manifest_path,
        review_template_path=review_template_path,
        completed_review_path=completed_review_path,
        review_manifest_path=review_manifest_path,
    )
    print(
        json.dumps(
            {
                "status": manifest.status,
                "reviewer_id": manifest.reviewer_id,
                "reviewer_kind": manifest.reviewer_kind,
                "candidate_count": len(candidate_file.candidates),
                "decision_counts": manifest.decision_counts,
                "human_domain_signoff": manifest.human_domain_signoff,
                "promotion_scope": manifest.promotion_scope,
                "development_promotion_eligible": (
                    manifest.development_promotion_eligible
                ),
                "completed_review": str(completed_review_path.resolve()),
                "review_manifest": str(review_manifest_path.resolve()),
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
