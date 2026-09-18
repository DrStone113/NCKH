"""Validate, aggregate, and render a sanitized development benchmark report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from services.experiment.analysis import summarize_development_batch
from services.experiment.benchmark import BenchmarkSplit, load_and_verify_benchmark, sha256_file
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.evaluation_export import (
    evaluate_batch_records,
    load_run_records,
    select_experiment_records,
    validate_batch_records,
)
from services.experiment.records import repository_state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a sanitized deterministic aggregate from a paired batch."
    )
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--experiment-id")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _percent(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate * 100:.1f}%"


def render_report(summary: dict[str, Any]) -> str:
    experiment = summary["experiment"]
    lines = [
        "# Nutrition calculation ablation — development analysis",
        "",
        "## Classification",
        "",
        "```text",
        "ARTIFACT_CLASS = DEVELOPMENT_ONLY",
        "CONFIRMATORY_EVIDENCE = NO",
        "CLINICAL_VALIDATION = NO",
        "PRODUCTION_ROLLOUT_AUTHORITY = NO",
        "```",
        "",
        "This report is a deterministic aggregate of the complete paired calculation",
        "batch. Raw provider responses remain in ignored local logs and are not copied",
        "into this tracked artifact.",
        "",
        "## Frozen execution identity",
        "",
        f"- Experiment: `{experiment['experiment_id']}`",
        f"- Benchmark: `{experiment['benchmark_version']}` ({experiment['case_count']} cases)",
        f"- Runs: `{experiment['run_count']}`",
        f"- Requested model route: `{', '.join(experiment['requested_models'])}`",
        f"- Provider-reported model: `{', '.join(experiment['actual_models'])}`",
        f"- Execution commit: `{', '.join(str(value) for value in experiment['execution_commits'])}`",
        f"- Protocol / prompt: `{experiment['protocol_id']}` / `{experiment['prompt_version']}`",
        f"- Temperature / max tokens: `{experiment['temperature']}` / `{experiment['max_tokens']}`",
        f"- RAG: top-k `{experiment['rag_top_k']}`, threshold `{experiment['rag_threshold']}`",
        f"- Corpus: `{experiment['corpus_version']}` / `{experiment['corpus_hash']}`",
        f"- Records SHA-256: `{experiment['records_sha256']}`",
        "",
        "## Answer accuracy",
        "",
        "Missing values count as incorrect. A value is correct when it meets its",
        "predeclared absolute or relative tolerance.",
        "",
        "| Arm | All 4 correct | BMI | RMR | TDEE | Target | Median latency | Mean tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ("S0", "S1", "S2", "S3"):
        data = summary["arms"][arm]
        values = data["answer"]["by_value"]
        lines.append(
            "| {arm} | {all4} | {bmi} | {rmr} | {tdee} | {target} | {latency:.0f} ms | {tokens:.0f} |".format(
                arm=arm,
                all4=_percent(data["answer"]["all_values_correct"]["rate"]),
                bmi=_percent(values["bmi"]["correct_over_all_runs"]["rate"]),
                rmr=_percent(values["rmr"]["correct_over_all_runs"]["rate"]),
                tdee=_percent(values["tdee"]["correct_over_all_runs"]["rate"]),
                target=_percent(values["calorie-target"]["correct_over_all_runs"]["rate"]),
                latency=data["latency_ms"]["median"],
                tokens=data["total_tokens"]["mean"],
            )
        )

    comparison = summary["paired_answer_comparisons"]["S1_to_S2"]
    lines.extend(
        [
            "",
            "## RQ2 development contrast: S1 → S2",
            "",
            f"- Correct on all four values: `{comparison['baseline_correct']}/{comparison['pairs']}` → `{comparison['treatment_correct']}/{comparison['pairs']}`.",
            f"- Absolute paired rate difference: `{comparison['absolute_rate_difference'] * 100:.1f}` percentage points.",
            f"- Improved / worsened pairs: `{comparison['improved']}` / `{comparison['worsened']}`.",
            f"- Exact two-sided McNemar p-value: `{comparison['exact_mcnemar_p_two_sided']:.6g}`.",
            "",
            "## Tool-path audit",
            "",
            "| Arm | Invoked | Successful | Exact arguments | All 4 structured values correct |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for arm in ("S2", "S3"):
        tool = summary["arms"][arm]["tool"]
        lines.append(
            f"| {arm} | {_percent(tool['invoked']['rate'])} | {_percent(tool['succeeded']['rate'])} | {_percent(tool['arguments_exact']['rate'])} | {_percent(tool['all_values_correct']['rate'])} |"
        )
    lines.extend(
        [
            "",
            "Tool correctness is reported separately from answer correctness. A valid",
            "deterministic calculation is still counted wrong against the benchmark when",
            "the model supplied the wrong activity level or goal.",
            "",
            "## Interpretation boundary",
            "",
            "- This benchmark supports only a development-stage RQ2 analysis.",
            "- It does not test RQ1 because calculation cases have no source-linked knowledge gold.",
            "- It does not isolate RQ3 because the same profile facts are explicit in each query.",
            "- It is not confirmatory, clinically validated, or authority for production rollout.",
            "- Pilot/final claims require separately frozen cases and genuine independent human/domain review.",
            "",
        ]
    )
    return "\n".join(lines)


def _write(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ExperimentError("EXPERIMENT_ANALYSIS_OUTPUT_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[3]
    analysis_commit, clean = repository_state(repo_root)
    if clean is not True or analysis_commit is None:
        raise ExperimentError("EXPERIMENT_ANALYSIS_REQUIRES_CLEAN_WORKTREE")
    benchmark, manifest = load_and_verify_benchmark(args.benchmark, args.manifest)
    records = select_experiment_records(
        load_run_records(args.records), args.experiment_id
    )
    validate_batch_records(
        records,
        benchmark=benchmark,
        manifest=manifest,
        split=BenchmarkSplit.DEVELOPMENT,
        repetitions=args.repetitions,
    )
    evaluations = evaluate_batch_records(
        records, benchmark=benchmark, manifest=manifest
    )
    summary = summarize_development_batch(
        records=records,
        evaluations=evaluations,
        benchmark=benchmark,
        manifest=manifest,
        records_sha256=sha256_file(args.records),
    )
    summary["analysis"] = {
        "analysis_commit": analysis_commit,
        "analysis_worktree_clean": clean,
    }
    _write(
        args.output_json,
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        overwrite=args.overwrite,
    )
    _write(args.output_report, render_report(summary), overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "experiment_id": records[0].experiment_id,
                "runs": len(records),
                "output_json": str(args.output_json.resolve()),
                "output_report": str(args.output_report.resolve()),
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
        detail = str(exc) if isinstance(exc, ExperimentError) else safe_error_detail(exc)
        print(json.dumps({"error": detail}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
