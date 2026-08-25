"""Export reviewable D3.0.1 candidate artifacts; does not freeze or evaluate them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.agent.context_planner.validation.adversarial_candidates import (
    adversarial_candidates, oracle_review_template,
)
from services.agent.context_planner.validation.datasets import (
    adversarial_candidate_identity, load_natural_records,
    natural_collecting_identity, regression_identity,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--natural-jsonl", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "adversarial-candidates.json", [item.content_dict() for item in adversarial_candidates()])
    _write(args.output_dir / "adversarial-oracle-review-template.json", oracle_review_template())
    _write(args.output_dir / "adversarial-candidate-manifest.json", adversarial_candidate_identity().to_dict())
    _write(args.output_dir / "natural-collecting-manifest.json", natural_collecting_identity(args.natural_jsonl).to_dict())
    _write(args.output_dir / "natural-candidates.json", load_natural_records(args.natural_jsonl))
    _write(args.output_dir / "regression-manifest.json", regression_identity().to_dict())


if __name__ == "__main__":
    main()
