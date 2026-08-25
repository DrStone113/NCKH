"""Freeze a completed human-reviewed D3.0.1 dataset and oracle pair."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from services.agent.context_planner.validation.contracts import DatasetType
from services.agent.context_planner.validation.datasets import freeze_reviewed_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-type", required=True, choices=["NATURAL_SHADOW", "ADVERSARIAL_HOLDOUT"])
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--oracles", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    oracles = json.loads(args.oracles.read_text(encoding="utf-8"))
    identity, _ = freeze_reviewed_dataset(
        dataset_type=DatasetType(args.dataset_type), dataset_version=args.dataset_version,
        case_payloads=cases, oracle_payloads=oracles,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    args.manifest.write_text(
        json.dumps(identity.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
