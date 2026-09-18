"""Run a verified nutrition benchmark split across paired S0-S3 arms.

Example (run from ``apps/backend``)::

    python -m scripts.run_benchmark --benchmark path/to/benchmark.json \
        --manifest path/to/benchmark.manifest.json --split development \
        --repetitions 2 --output research-results.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence, cast

from pydantic import ValidationError

from services.experiment.batch import (
    NutritionAblationBatchRunner,
    build_schedule,
    configs_for_arms,
)
from services.experiment.benchmark import (
    BenchmarkSplit,
    load_and_verify_benchmark,
)
from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NUTRITION_ABLATION_MODEL,
    NUTRITION_ABLATION_PROMPT_VERSION,
    ExperimentConfig,
    NutritionAblationArm,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.llm import FixedOpenAIResearchClient
from services.experiment.rag import PostgresFrozenRagProvider
from services.experiment.records import repository_state
from services.experiment.records import load_jsonl_records
from services.experiment.runner import ResearchExperimentRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a cryptographically verified benchmark split across "
            "controlled nutrition-ablation arms."
        )
    )
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--split",
        choices=tuple(split.value for split in BenchmarkSplit),
        default=BenchmarkSplit.DEVELOPMENT.value,
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=NUTRITION_ABLATION_ARMS,
        default=list(NUTRITION_ABLATION_ARMS),
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--schedule-seed",
        type=int,
        help="Deterministic schedule seed; defaults to the model seed.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/nutrition-ablation-results.jsonl"),
    )
    parser.add_argument("--experiment-id", default="nutrition-ablation-batch")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume only from an exact verified prefix already present in "
            "--output. Existing failed records remain failed and are not retried."
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate inputs and print the schedule without API or DB calls.",
    )
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


def _template_config_from_args(args: argparse.Namespace) -> ExperimentConfig:
    values: dict[str, Any] = {
        "condition": "S0",
        "model": NUTRITION_ABLATION_MODEL,
        "prompt_version": NUTRITION_ABLATION_PROMPT_VERSION,
    }
    for field in (
        "model",
        "temperature",
        "seed",
        "max_tokens",
        "max_agent_steps",
        "prompt_version",
        "frozen_time",
        "rag_top_k",
        "rag_threshold",
        "corpus_version",
        "corpus_hash",
    ):
        value = getattr(args, field)
        if value is not None:
            values[field] = value
    return ExperimentConfig.model_validate(values)


def _selected_arms(args: argparse.Namespace) -> tuple[NutritionAblationArm, ...]:
    return cast(tuple[NutritionAblationArm, ...], tuple(args.arms))


def _require_final_execution_state(repo_root: Path, output_path: Path) -> None:
    _, worktree_clean = repository_state(repo_root)
    if worktree_clean is not True:
        raise ExperimentError("EXPERIMENT_FINAL_REQUIRES_CLEAN_WORKTREE")

    resolved_repo = repo_root.resolve()
    resolved_output = output_path.resolve()
    try:
        relative_output = resolved_output.relative_to(resolved_repo)
    except ValueError:
        return
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(relative_output)],
        cwd=resolved_repo,
        check=False,
        timeout=5,
    )
    if ignored.returncode != 0:
        raise ExperimentError("EXPERIMENT_FINAL_OUTPUT_MUST_BE_IGNORED")


async def _run(args: argparse.Namespace) -> int:
    benchmark, manifest = load_and_verify_benchmark(
        args.benchmark, args.manifest
    )
    split = BenchmarkSplit(args.split)
    template = _template_config_from_args(args)
    arms = _selected_arms(args)
    configs = configs_for_arms(template, arms)
    schedule_seed = (
        args.schedule_seed if args.schedule_seed is not None else template.seed
    )
    schedule = build_schedule(
        benchmark,
        split=split,
        arms=arms,
        repetitions=args.repetitions,
        schedule_seed=schedule_seed,
    )

    if any(
        config.corpus_version != manifest.corpus_version
        for config in configs.values()
    ):
        raise ExperimentError("EXPERIMENT_BENCHMARK_CORPUS_MISMATCH")

    if args.plan_only:
        print(
            json.dumps(
                {
                    "experiment_id": args.experiment_id,
                    "benchmark_version": benchmark.benchmark_version,
                    "benchmark_file_sha256": manifest.benchmark_file_sha256,
                    "benchmark_manifest_hash": manifest.manifest_hash,
                    "split": split.value,
                    "arms": list(arms),
                    "repetitions": args.repetitions,
                    "schedule_seed": schedule_seed,
                    "scheduled_runs": len(schedule),
                    "schedule": [
                        item.model_dump(mode="json") for item in schedule
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0

    repo_root = Path(__file__).resolve().parents[3]
    if args.output.exists() and not args.resume:
        raise ExperimentError("EXPERIMENT_BATCH_OUTPUT_EXISTS", str(args.output))
    resume_records = load_jsonl_records(args.output) if args.resume else ()
    commit, worktree_clean = repository_state(repo_root)
    if worktree_clean is not True:
        raise ExperimentError("EXPERIMENT_BATCH_REQUIRES_CLEAN_WORKTREE")
    if any(
        record.git_commit != commit or record.worktree_clean is not True
        for record in resume_records
    ):
        raise ExperimentError("EXPERIMENT_BATCH_RESUME_GIT_STATE_MISMATCH")
    if split == BenchmarkSplit.FINAL:
        _require_final_execution_state(repo_root, args.output)

    client = FixedOpenAIResearchClient.from_backend_settings()
    rag_provider = (
        PostgresFrozenRagProvider()
        if any(config.rag_enabled for config in configs.values())
        else None
    )
    runner = NutritionAblationBatchRunner(
        ResearchExperimentRunner(
            completion_client=client,
            rag_provider=rag_provider,
        )
    )
    summary = await runner.run(
        experiment_id=args.experiment_id,
        benchmark=benchmark,
        manifest=manifest,
        split=split,
        configs=configs,
        repetitions=args.repetitions,
        schedule_seed=schedule_seed,
        output_path=args.output,
        resume_records=resume_records,
    )
    print(
        json.dumps(
            {
                **summary.model_dump(mode="json"),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 1 if summary.failed_runs else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
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
        print(
            json.dumps(
                {"error": detail},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
