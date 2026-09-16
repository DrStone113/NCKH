"""Run one isolated research test case and append a JSONL record.

Example (run from ``apps/backend``)::

    python -m scripts.run_experiment --condition A \
        --case tests/fixtures/example_experiment_case.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NUTRITION_ABLATION_PROMPT_VERSION,
    ExperimentConfig,
)
from services.experiment.llm import FixedOpenAIResearchClient
from services.experiment.models import ExperimentTestCase
from services.experiment.rag import PostgresFrozenRagProvider
from services.experiment.records import append_jsonl
from services.experiment.runner import ResearchExperimentRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one controlled nutrition-chatbot experiment run."
    )
    parser.add_argument(
        "--condition",
        required=True,
        choices=("A", "B", "C", "D", *NUTRITION_ABLATION_ARMS),
    )
    parser.add_argument("--case", required=True, type=Path, dest="case_path")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research-results.jsonl"),
        help="Append-only JSONL output path (default: research-results.jsonl).",
    )
    parser.add_argument("--experiment-id", default="phase1")
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--max-agent-steps", type=int)
    parser.add_argument("--prompt-version")
    parser.add_argument("--frozen-time")
    parser.add_argument("--rag-top-k", type=int)
    parser.add_argument("--rag-threshold", type=float)
    parser.add_argument("--corpus-version")
    parser.add_argument("--corpus-hash")
    return parser


def _config_from_args(args: argparse.Namespace) -> ExperimentConfig:
    values: dict[str, Any] = {"condition": args.condition}
    if (
        args.condition in NUTRITION_ABLATION_ARMS
        and args.prompt_version is None
    ):
        values["prompt_version"] = NUTRITION_ABLATION_PROMPT_VERSION
    for field, argument in (
        ("model", "model"),
        ("temperature", "temperature"),
        ("seed", "seed"),
        ("max_tokens", "max_tokens"),
        ("max_agent_steps", "max_agent_steps"),
        ("prompt_version", "prompt_version"),
        ("frozen_time", "frozen_time"),
        ("rag_top_k", "rag_top_k"),
        ("rag_threshold", "rag_threshold"),
        ("corpus_version", "corpus_version"),
        ("corpus_hash", "corpus_hash"),
    ):
        value = getattr(args, argument)
        if value is not None:
            values[field] = value
    return ExperimentConfig.model_validate(values)


def _load_case(path: Path) -> ExperimentTestCase:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return ExperimentTestCase.model_validate(payload)


async def _run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    test_case = _load_case(args.case_path)
    client = FixedOpenAIResearchClient.from_backend_settings()
    rag_provider = PostgresFrozenRagProvider() if config.rag_enabled else None
    runner = ResearchExperimentRunner(
        completion_client=client,
        rag_provider=rag_provider,
    )
    record = await runner.run(
        experiment_id=args.experiment_id,
        config=config,
        test_case=test_case,
    )
    append_jsonl(args.output, record)
    print(
        json.dumps(
            {
                "run_id": record.run_id,
                "condition": record.condition,
                "output": str(args.output.resolve()),
                "error": record.error,
            },
            ensure_ascii=False,
        )
    )
    return 1 if record.error else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(
            json.dumps(
                {"error": f"EXPERIMENT_INPUT_INVALID: {type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
