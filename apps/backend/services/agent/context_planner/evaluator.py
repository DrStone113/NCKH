"""Engineering metrics for the synthetic D3.0 shadow scenario set."""

from __future__ import annotations

from collections import defaultdict
import statistics
from typing import Iterable

from .development_scenarios import DEVELOPMENT_SCENARIOS, DevelopmentScenario, SCENARIO_SET_VERSION
from .planner import ContextPlanner


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate_scenarios(
    scenarios: Iterable[DevelopmentScenario] = DEVELOPMENT_SCENARIOS,
    *, current_context_characters: int = 12000,
) -> dict[str, object]:
    planner = ContextPlanner()
    rows: list[dict[str, object]] = []
    by_intent: dict[str, list[dict[str, object]]] = defaultdict(list)
    latencies: list[float] = []
    planned_sizes: list[int] = []

    for scenario in scenarios:
        user_context = {"source_statuses": {source.value: status.value for source, status in scenario.source_statuses}}
        first = planner.plan_shadow(
            scenario.query, user_context=user_context,
            current_production_context_size_characters=current_context_characters,
        )
        second = planner.plan_shadow(
            scenario.query, user_context=user_context,
            current_production_context_size_characters=current_context_characters,
        )
        expected_required = set(scenario.expected_required_sources)
        actual_required = set(first.plan.required_sources)
        expected_forbidden = set(scenario.expected_forbidden_sources)
        actual_requested = actual_required | set(first.plan.optional_sources)
        expected_tools = set(scenario.expected_tools)
        actual_tools = set(first.plan.permitted_tools)
        expected_missing = expected_required
        actual_missing = set(first.bundle.missing_required_sources)
        deterministic = (
            first.classification.to_dict() == second.classification.to_dict()
            and first.plan.to_dict() == second.plan.to_dict()
            and first.bundle.to_dict() == second.bundle.to_dict()
        )
        row = {
            "scenario_id": scenario.scenario_id,
            "expected_intent": scenario.expected_primary_intent.value,
            "actual_intent": first.plan.primary_intent.value,
            "intent_correct": first.plan.primary_intent == scenario.expected_primary_intent and first.plan.secondary_intents == scenario.expected_secondary_intents,
            "required_hits": len(expected_required & actual_required),
            "required_total": len(expected_required),
            "forbidden_violations": len(expected_forbidden & actual_requested),
            "rag_correct": first.plan.rag_policy == scenario.expected_rag_policy,
            "tool_hits": len(expected_tools & actual_tools),
            "expected_tools": len(expected_tools),
            "actual_tools": len(actual_tools),
            "missing_correct": actual_missing == expected_missing,
            "validators_correct": set(first.plan.required_validators) == set(scenario.expected_validators),
            "deterministic": deterministic,
            "latency_ms": first.latency_ms,
            "planned_characters": first.bundle.planned_context_size_characters,
        }
        rows.append(row)
        by_intent[scenario.expected_primary_intent.value].append(row)
        latencies.append(first.latency_ms)
        planned_sizes.append(first.bundle.planned_context_size_characters)

    def summarize(items: list[dict[str, object]]) -> dict[str, float | int]:
        required_hits = sum(int(item["required_hits"]) for item in items)
        required_total = sum(int(item["required_total"]) for item in items)
        tool_hits = sum(int(item["tool_hits"]) for item in items)
        expected_tools = sum(int(item["expected_tools"]) for item in items)
        actual_tools = sum(int(item["actual_tools"]) for item in items)
        return {
            "turns": len(items),
            "primary_intent_accuracy": _ratio(sum(bool(item["intent_correct"]) for item in items), len(items)),
            "required_source_recall": _ratio(required_hits, required_total),
            "forbidden_source_violation_rate": _ratio(sum(int(item["forbidden_violations"]) for item in items), len(items)),
            "rag_routing_accuracy": _ratio(sum(bool(item["rag_correct"]) for item in items), len(items)),
            "tool_precision": _ratio(tool_hits, actual_tools),
            "tool_recall": _ratio(tool_hits, expected_tools),
            "missing_data_accuracy": _ratio(sum(bool(item["missing_correct"]) for item in items), len(items)),
            "validator_accuracy": _ratio(sum(bool(item["validators_correct"]) for item in items), len(items)),
            "determinism_rate": _ratio(sum(bool(item["deterministic"]) for item in items), len(items)),
        }

    sorted_latency = sorted(latencies)
    p95_index = max(0, min(len(sorted_latency) - 1, int(0.95 * len(sorted_latency)) - 1))
    overall = summarize(rows)
    overall.update({
        "mean_planned_context_characters": round(statistics.mean(planned_sizes), 2) if planned_sizes else 0,
        "mean_current_context_characters": current_context_characters,
        "mean_context_reduction_rate": round(1 - statistics.mean(planned_sizes) / current_context_characters, 6) if planned_sizes else 0,
        "mean_planner_latency_ms": round(statistics.mean(latencies), 4) if latencies else 0,
        "p95_planner_latency_ms": round(sorted_latency[p95_index], 4) if sorted_latency else 0,
    })
    misclassified = [
        {"scenario_id": item["scenario_id"], "expected": item["expected_intent"], "actual": item["actual_intent"]}
        for item in rows if not item["intent_correct"]
    ]
    return {
        "scenario_set_version": SCENARIO_SET_VERSION,
        "synthetic_development_turns": len(rows),
        "overall": overall,
        "per_intent": {key: summarize(value) for key, value in sorted(by_intent.items())},
        "misclassified_scenarios": misclassified,
    }


__all__ = ["evaluate_scenarios"]
