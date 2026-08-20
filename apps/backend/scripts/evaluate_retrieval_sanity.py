"""Run the small Phase 2 engineering retrieval diagnostic (not a benchmark)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from services.experiment.config import ExperimentConfig
from services.experiment.errors import ExperimentError
from services.experiment.rag import PostgresFrozenRagProvider

DEFAULT_SET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "retrieval_sanity_set.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, dest="set_path")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.6)
    return parser


async def _run(args: argparse.Namespace) -> int:
    cases: list[dict[str, Any]] = json.loads(
        args.set_path.read_text(encoding="utf-8")
    )
    config = ExperimentConfig(
        condition="C", rag_top_k=args.top_k, rag_threshold=args.threshold
    )
    provider = PostgresFrozenRagProvider()
    await provider.prewarm()

    hits = 0
    reciprocal_rank_sum = 0.0
    results: list[dict[str, Any]] = []
    for case in cases:
        expected = {
            (item["dataset_file"], item["source_record_id"])
            for item in case["relevant_records"]
        }
        try:
            trace = await provider.retrieve(case["query"], config)
            returned = [
                (chunk.source["dataset_file"], chunk.source["source_record_id"])
                for chunk in trace.chunks
            ]
            first_rank = next(
                (rank for rank, key in enumerate(returned, start=1) if key in expected),
                None,
            )
            error = None
        except ExperimentError as exc:
            returned = []
            first_rank = None
            error = str(exc)
        if first_rank is not None:
            hits += 1
            reciprocal_rank_sum += 1.0 / first_rank
        results.append(
            {
                "query_id": case["query_id"],
                "returned_record_ids": [f"{file}#{record}" for file, record in returned],
                "first_relevant_rank": first_rank,
                "error": error,
            }
        )

    count = len(cases)
    payload = {
        "diagnostic_only": True,
        "not_a_scientific_benchmark": True,
        "query_count": count,
        "top_k": args.top_k,
        "threshold": args.threshold,
        "recall_at_k": hits / count if count else 0.0,
        "mrr": reciprocal_rank_sum / count if count else 0.0,
        "cases": results,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(result["error"] is None for result in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
