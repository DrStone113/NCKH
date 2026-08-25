"""Evaluate one frozen, human-reviewed natural or adversarial dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.agent.context_planner.validation.datasets import (
    dataset_identity_from_dict, oracle_case_from_dict,
)
from services.agent.context_planner.validation.evaluator import evaluate_frozen_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--oracles", required=True, type=Path)
    args = parser.parse_args()
    identity = dataset_identity_from_dict(json.loads(args.manifest.read_text(encoding="utf-8")))
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    oracles = tuple(
        oracle_case_from_dict(item)
        for item in json.loads(args.oracles.read_text(encoding="utf-8"))
    )
    print(json.dumps(evaluate_frozen_dataset(identity, cases, oracles), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
