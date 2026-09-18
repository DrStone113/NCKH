from __future__ import annotations

import pytest

from scripts.analyze_benchmark import render_report
from services.experiment.analysis import exact_mcnemar_p, wilson_interval


def test_wilson_interval_contains_observed_rate() -> None:
    interval = wilson_interval(36, 60)

    assert interval is not None
    assert interval[0] < 0.6 < interval[1]
    assert wilson_interval(0, 0) is None


def test_exact_mcnemar_matches_small_exact_binomial_cases() -> None:
    assert exact_mcnemar_p(0, 0) == 1.0
    assert exact_mcnemar_p(11, 1) == pytest.approx(0.00634765625)
    assert exact_mcnemar_p(6, 6) == 1.0


def test_report_preserves_development_interpretation_boundary() -> None:
    rate = {"rate": 0.5}
    value = {"correct_over_all_runs": rate}
    arm = {
        "answer": {
            "all_values_correct": rate,
            "by_value": {
                "bmi": value,
                "rmr": value,
                "tdee": value,
                "calorie-target": value,
            },
        },
        "tool": {
            "invoked": rate,
            "succeeded": rate,
            "arguments_exact": rate,
            "all_values_correct": rate,
        },
        "latency_ms": {"median": 1000},
        "total_tokens": {"mean": 100},
    }
    summary = {
        "experiment": {
            "experiment_id": "fixture",
            "benchmark_version": "fixture-v1",
            "case_count": 1,
            "run_count": 4,
            "requested_models": ["route"],
            "actual_models": ["model"],
            "execution_commits": ["commit"],
            "protocol_id": "protocol",
            "prompt_version": "prompt",
            "temperature": 0,
            "max_tokens": 10,
            "rag_top_k": 5,
            "rag_threshold": 0.5,
            "corpus_version": "corpus",
            "corpus_hash": "hash",
            "records_sha256": "a" * 64,
        },
        "arms": {name: arm for name in ("S0", "S1", "S2", "S3")},
        "paired_answer_comparisons": {
            "S1_to_S2": {
                "baseline_correct": 0,
                "treatment_correct": 1,
                "pairs": 1,
                "absolute_rate_difference": 1,
                "improved": 1,
                "worsened": 0,
                "exact_mcnemar_p_two_sided": 1,
            }
        },
    }

    report = render_report(summary)

    assert "DEVELOPMENT_ONLY" in report
    assert "does not test RQ1" in report
    assert "does not isolate RQ3" in report
    assert "PRODUCTION_ROLLOUT_AUTHORITY = NO" in report
