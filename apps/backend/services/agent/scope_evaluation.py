"""Metrics for labelled Hybrid Domain-Scope Router evaluations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from services.agent.scope_guard import ScopeCategory, ScopeIntent


_IN_SCOPE = frozenset(
    {
        ScopeCategory.IN_SCOPE_NUTRITION,
        ScopeCategory.IN_SCOPE_MEAL_PLAN,
        ScopeCategory.IN_SCOPE_FITNESS,
        ScopeCategory.IN_SCOPE_PROFILE_APP,
        ScopeCategory.IN_SCOPE_GENERAL_WELLNESS,
        ScopeCategory.SAFETY_ESCALATION,
    }
)


@dataclass(frozen=True, slots=True)
class ScopeEvaluationRecord:
    expected_scope: ScopeCategory
    predicted_scope: ScopeCategory
    expected_intent: ScopeIntent
    predicted_intent: ScopeIntent
    latency_ms: float
    judge_calls: int = 0


def summarize_scope_evaluation(
    records: Iterable[ScopeEvaluationRecord],
    *,
    judge_cost_usd: float = 0.0,
) -> dict[str, Any]:
    rows = tuple(records)
    if not rows:
        raise ValueError("at least one evaluation record is required")

    true_oos = sum(row.expected_scope == ScopeCategory.OUT_OF_SCOPE for row in rows)
    predicted_oos = sum(row.predicted_scope == ScopeCategory.OUT_OF_SCOPE for row in rows)
    true_positive_oos = sum(
        row.expected_scope == ScopeCategory.OUT_OF_SCOPE
        and row.predicted_scope == ScopeCategory.OUT_OF_SCOPE
        for row in rows
    )
    in_scope = tuple(row for row in rows if row.expected_scope in _IN_SCOPE)
    ambiguous = tuple(
        row for row in rows if row.expected_scope == ScopeCategory.AMBIGUOUS
    )
    safety = tuple(
        row for row in rows if row.expected_scope == ScopeCategory.SAFETY_ESCALATION
    )
    false_refusals = sum(
        row.expected_scope in _IN_SCOPE
        and row.predicted_scope == ScopeCategory.OUT_OF_SCOPE
        for row in rows
    )
    oos_leaks = sum(
        row.expected_scope == ScopeCategory.OUT_OF_SCOPE
        and row.predicted_scope in _IN_SCOPE
        for row in rows
    )
    judge_calls = sum(row.judge_calls for row in rows)
    precision = _safe_ratio(true_positive_oos, predicted_oos)
    recall = _safe_ratio(true_positive_oos, true_oos)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    latencies = sorted(max(0.0, row.latency_ms) for row in rows)

    return {
        "sample_count": len(rows),
        "intent_accuracy": _safe_ratio(
            sum(row.expected_intent == row.predicted_intent for row in rows),
            len(rows),
        ),
        "in_scope_intent_accuracy": _safe_ratio(
            sum(row.expected_intent == row.predicted_intent for row in in_scope),
            len(in_scope),
        ),
        "oos_precision": precision,
        "oos_recall": recall,
        "oos_f1": f1,
        "false_refusal_rate": _safe_ratio(false_refusals, len(in_scope)),
        "oos_leakage_rate": _safe_ratio(oos_leaks, true_oos),
        "ambiguous_accuracy": _safe_ratio(
            sum(row.predicted_scope == ScopeCategory.AMBIGUOUS for row in ambiguous),
            len(ambiguous),
        ),
        "safety_recall": _safe_ratio(
            sum(row.predicted_scope == ScopeCategory.SAFETY_ESCALATION for row in safety),
            len(safety),
        ),
        "latency_ms_p50": _nearest_rank(latencies, 0.50),
        "latency_ms_p95": _nearest_rank(latencies, 0.95),
        "judge_calls": judge_calls,
        "judge_calls_per_1000": judge_calls * 1000.0 / len(rows),
        "estimated_judge_cost_usd": judge_calls * max(0.0, judge_cost_usd),
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _nearest_rank(values: list[float], percentile: float) -> float:
    index = max(0, math.ceil(percentile * len(values)) - 1)
    return values[index]


__all__ = ["ScopeEvaluationRecord", "summarize_scope_evaluation"]
