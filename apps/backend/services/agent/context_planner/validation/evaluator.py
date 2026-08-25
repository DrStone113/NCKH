"""Separate D3.0.1 metrics with preserved per-case failure taxonomy."""

from __future__ import annotations

from collections import Counter
import math
import statistics
from types import SimpleNamespace
from typing import Any, Iterable

from ..contracts import DataStatus, MemoryPolicy, RagPolicy, SourceId
from ..matrix import ALL_KNOWN_TOOLS
from ..planner import ContextPlanner
from ..registry import PrivacyClass, SOURCE_REGISTRY
from .contracts import DatasetIdentity, FailureCategory, OracleCase
from .datasets import planner_snapshot
from .hashing import verify_frozen_payload


_WRITE_TOOLS = frozenset({
    "log_meal", "log_weight", "log_exercise", "log_lifestyle",
    "set_lifestyle_reminder", "navigate_to_screen", "create_long_term_plan",
    "mark_plan_item_complete", "create_plan", "append_plan_items",
})
_SAFETY_SOURCES = frozenset({SourceId.NUTRITION_SAFETY, SourceId.CANONICAL_NUTRITION, SourceId.MEDICAL_EVIDENCE})


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _distribution(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)

    def percentile(p: float) -> float:
        index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
        return ordered[index]

    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "p90": round(percentile(0.90), 4),
        "p95": round(percentile(0.95), 4),
    }


def evaluate_frozen_dataset(
    identity: DatasetIdentity,
    case_payloads: list[dict[str, Any]],
    oracles: Iterable[OracleCase],
) -> dict[str, Any]:
    """Reject mutable/unreviewed inputs before running any planner metrics."""

    oracle_list = list(oracles)
    verify_frozen_payload(identity, case_payloads, [item.to_dict() for item in oracle_list])
    current_planner = planner_snapshot()
    if any(
        current_planner[key] != getattr(identity, key)
        for key in ("planner_version", "planner_commit", "planner_content_sha256")
    ):
        raise ValueError("planner snapshot differs from the frozen validation manifest")
    if len(case_payloads) != identity.case_count or len(oracle_list) != identity.case_count:
        raise ValueError("dataset/oracle case count does not match frozen manifest")
    oracle_by_id = {item.case_id: item for item in oracle_list}
    if len(oracle_by_id) != len(oracle_list):
        raise ValueError("duplicate oracle case ID")

    planner = ContextPlanner()
    rows: list[dict[str, Any]] = []
    failure_counts: Counter[str] = Counter()
    latency_values: list[float] = []
    exact_reductions: list[float] = []
    approximate_reductions: list[float] = []
    secondary_tp = secondary_fp = secondary_fn = 0
    required_hits = required_total = source_hits = source_actual = 0
    safety_hits = safety_total = 0
    tool_hits = tool_actual = tool_expected = 0
    validator_hits = validator_total = 0
    optional_selected = optional_available = unnecessary_sensitive = duplicate_retrieval = 0
    token_fields: dict[str, list[float]] = {
        key: [] for key in (
            "production_prompt_tokens", "production_context_tokens",
            "production_tool_schema_tokens", "production_total_tokens",
            "shadow_context_tokens", "shadow_tool_schema_tokens", "shadow_total_tokens",
        )
    }
    exact_token_records = approximate_token_records = 0
    safety_forbidden_violations = unsupported_target_violations = hard_constraint_omissions = 0

    for payload in case_payloads:
        case_id = str(payload.get("case_id") or payload.get("record_id") or "")
        oracle = oracle_by_id.get(case_id)
        if oracle is None:
            raise ValueError(f"missing oracle for case {case_id}")
        statuses = dict(oracle.source_statuses)
        user_context = {"source_statuses": {source.value: status for source, status in statuses.items()}}
        context_history = [SimpleNamespace(role="user", content=item) for item in oracle.conversational_context]
        rag_available = bool(payload.get("rag_already_available"))
        memory = SimpleNamespace(
            history=context_history, pinned_facts=[],
            rag_chunks=[payload.get("untrusted_retrieved_content", "retrieved")] if rag_available else [],
            rag_requested=rag_available, rag_result_status="FOUND" if rag_available else "NOT_REQUESTED",
        )
        first = planner.plan_shadow(
            oracle.query, user_context=user_context, memory_context=memory,
            available_tool_names=ALL_KNOWN_TOOLS,
        )
        second = planner.plan_shadow(
            oracle.query, user_context=user_context, memory_context=memory,
            available_tool_names=ALL_KNOWN_TOOLS,
        )
        failures: set[FailureCategory] = set()
        plan = first.plan
        actual_required = set(plan.required_sources)
        actual_sources = actual_required | set(plan.optional_sources)
        expected_required = set(oracle.required_sources)
        expected_sources = expected_required | set(oracle.optional_sources)
        actual_tools = set(plan.permitted_tools)
        expected_tools = set(oracle.permitted_tools)
        actual_validators = set(plan.required_validators)
        expected_validators = set(oracle.validators)

        intent_correct = plan.primary_intent == oracle.primary_intent
        if not intent_correct:
            failures.add(FailureCategory.INTENT_MISCLASSIFICATION)
        actual_secondary, expected_secondary = set(plan.secondary_intents), set(oracle.secondary_intents)
        secondary_tp += len(actual_secondary & expected_secondary)
        secondary_fp += len(actual_secondary - expected_secondary)
        secondary_fn += len(expected_secondary - actual_secondary)
        missing_sources = expected_required - actual_required
        unnecessary_sources = actual_sources - expected_sources
        forbidden_selected = actual_sources & set(oracle.forbidden_sources)
        if missing_sources:
            failures.add(FailureCategory.MISSING_REQUIRED_SOURCE)
        if unnecessary_sources:
            failures.add(FailureCategory.UNNECESSARY_SOURCE)
        if forbidden_selected:
            failures.add(FailureCategory.FORBIDDEN_SOURCE_SELECTED)
        required_hits += len(expected_required & actual_required)
        required_total += len(expected_required)
        source_hits += len(expected_sources & actual_sources)
        source_actual += len(actual_sources)
        optional_selected += len(set(plan.optional_sources) & set(oracle.optional_sources))
        optional_available += len(oracle.optional_sources)
        unnecessary_sensitive += sum(
            SOURCE_REGISTRY[source].privacy_class != PrivacyClass.PUBLIC
            for source in unnecessary_sources
        )
        expected_safety = expected_required & _SAFETY_SOURCES
        safety_hits += len(expected_safety & actual_required)
        safety_total += len(expected_safety)
        if expected_safety and forbidden_selected:
            safety_forbidden_violations += 1
        if SourceId.NUTRITION_SAFETY in expected_required and SourceId.NUTRITION_SAFETY not in actual_required:
            hard_constraint_omissions += 1

        missing_tools = expected_tools - actual_tools
        unnecessary_tools = actual_tools - expected_tools
        if missing_tools:
            failures.add(FailureCategory.MISSING_TOOL)
        if unnecessary_tools:
            failures.add(FailureCategory.UNNECESSARY_TOOL)
        tool_hits += len(expected_tools & actual_tools)
        tool_expected += len(expected_tools)
        tool_actual += len(actual_tools)

        actual_write = bool(actual_tools & _WRITE_TOOLS)
        if actual_write != oracle.write_permitted:
            failures.add(FailureCategory.WRITE_PERMISSION_ERROR)
        if plan.rag_policy != oracle.rag_policy:
            failures.add(
                FailureCategory.RAG_UNDER_RETRIEVAL
                if oracle.rag_policy == RagPolicy.REQUIRED
                else FailureCategory.RAG_OVER_RETRIEVAL
            )
        if rag_available and "query_rag" in actual_tools:
            failures.add(FailureCategory.RAG_OVER_RETRIEVAL)
            duplicate_retrieval += 1
        if plan.memory_policy.value != oracle.memory_policy:
            failures.add(FailureCategory.MEMORY_ROUTING_ERROR)
        if oracle.primary_intent.value == "FOLLOWUP_EXPLANATION" and (
            SourceId.RECENT_CONVERSATION not in actual_required
            or plan.memory_policy != MemoryPolicy.REQUIRED
        ):
            failures.add(FailureCategory.FOLLOWUP_CONTEXT_ERROR)

        actual_actions = {item.source_id: item.action for item in first.bundle.missing_data_actions}
        expected_actions = dict(oracle.expected_missing_actions)
        freshness_correct = actual_actions == expected_actions
        if not freshness_correct:
            failures.add(FailureCategory.FRESHNESS_ERROR)
        clarification_correct = plan.clarification_required == oracle.clarification_required
        if not clarification_correct:
            failures.add(FailureCategory.CLARIFICATION_ERROR)
        missing_validators = expected_validators - actual_validators
        if missing_validators and expected_safety:
            failures.add(FailureCategory.SAFETY_POLICY_ERROR)
        validator_hits += len(expected_validators & actual_validators)
        validator_total += len(expected_validators)

        canonical_input_status = statuses.get(SourceId.CANONICAL_NUTRITION)
        unsupported_promoted = canonical_input_status in {"UNSUPPORTED", "REQUIRES_SPECIALIST_GUIDANCE"} and SourceId.CANONICAL_NUTRITION not in first.bundle.missing_required_sources
        safety_violation = bool(
            forbidden_selected or failures & {FailureCategory.WRITE_PERMISSION_ERROR, FailureCategory.SAFETY_POLICY_ERROR}
            or unsupported_promoted or expected_safety - actual_required
        )
        if unsupported_promoted:
            failures.add(FailureCategory.SAFETY_POLICY_ERROR)
            unsupported_target_violations += 1

        deterministic = (
            first.classification.to_dict() == second.classification.to_dict()
            and first.plan.to_dict() == second.plan.to_dict()
            and first.bundle.to_dict() == second.bundle.to_dict()
        )
        latency_values.append(first.latency_ms)
        token_data = payload.get("token_measurements")
        if isinstance(token_data, dict):
            for key in token_fields:
                if token_data.get(key) is not None:
                    token_fields[key].append(float(token_data[key]))
            if token_data.get("exact_tokenizer"):
                exact_token_records += 1
            else:
                approximate_token_records += 1
            production = int(token_data.get("production_total_tokens") or 0)
            shadow = int(token_data.get("shadow_total_tokens") or 0)
            if production > 0:
                reduction = 1 - shadow / production
                (exact_reductions if token_data.get("exact_tokenizer") else approximate_reductions).append(reduction)

        for failure in failures:
            failure_counts[failure.value] += 1
        rows.append({
            "case_id": case_id,
            "failures": sorted(item.value for item in failures),
            "intent_correct": intent_correct,
            "rag_correct": plan.rag_policy == oracle.rag_policy,
            "write_expected": oracle.write_permitted, "write_permitted": actual_write,
            "freshness_correct": freshness_correct,
            "clarification_correct": clarification_correct,
            "safety_violation": safety_violation,
            "deterministic": deterministic, "latency_ms": first.latency_ms,
        })

    turns = len(rows)
    secondary_precision = _ratio(secondary_tp, secondary_tp + secondary_fp)
    secondary_recall = _ratio(secondary_tp, secondary_tp + secondary_fn)
    secondary_f1 = (
        2 * secondary_precision * secondary_recall / (secondary_precision + secondary_recall)
        if secondary_precision is not None and secondary_recall is not None and secondary_precision + secondary_recall > 0
        else 1.0 if secondary_precision is None and secondary_recall is None else 0.0
    )
    expected_no_write = [item for item in rows if not item["write_expected"]]
    expected_write = [item for item in rows if item["write_expected"]]
    return {
        "dataset_identity": identity.to_dict(),
        "metrics": {
            "primary_intent_accuracy": _ratio(sum(item["intent_correct"] for item in rows), turns),
            "secondary_intent_precision": secondary_precision,
            "secondary_intent_recall": secondary_recall,
            "secondary_intent_f1": secondary_f1,
            "required_source_recall": _ratio(required_hits, required_total),
            "safety_critical_required_source_recall": _ratio(safety_hits, safety_total),
            "source_precision": _ratio(source_hits, source_actual),
            "optional_source_selection_rate": _ratio(optional_selected, optional_available),
            "unnecessary_sensitive_source_rate": _ratio(unnecessary_sensitive, turns),
            "forbidden_source_violation_rate": _ratio(sum(FailureCategory.FORBIDDEN_SOURCE_SELECTED.value in item["failures"] for item in rows), turns),
            "rag_routing_accuracy": _ratio(sum(item["rag_correct"] for item in rows), turns),
            "unnecessary_rag_rate": _ratio(failure_counts[FailureCategory.RAG_OVER_RETRIEVAL.value], turns),
            "missed_required_rag_rate": _ratio(failure_counts[FailureCategory.RAG_UNDER_RETRIEVAL.value], turns),
            "duplicate_retrieval_planning_rate": _ratio(duplicate_retrieval, turns),
            "tool_precision": _ratio(tool_hits, tool_actual),
            "tool_recall": _ratio(tool_hits, tool_expected),
            "false_write_permission_rate": _ratio(sum(item["write_permitted"] for item in expected_no_write), len(expected_no_write)),
            "missed_write_permission_rate": _ratio(sum(not item["write_permitted"] for item in expected_write), len(expected_write)),
            "freshness_handling_accuracy": _ratio(sum(item["freshness_correct"] for item in rows), turns),
            "clarification_accuracy": _ratio(sum(item["clarification_correct"] for item in rows), turns),
            "memory_routing_accuracy": _ratio(turns - failure_counts[FailureCategory.MEMORY_ROUTING_ERROR.value], turns),
            "validator_recall": _ratio(validator_hits, validator_total),
            "safety_invariant_violations": sum(item["safety_violation"] for item in rows),
            "safety_sensitive_forbidden_source_violations": safety_forbidden_violations,
            "freshness_safety_violations": failure_counts[FailureCategory.FRESHNESS_ERROR.value],
            "unsupported_target_violations": unsupported_target_violations,
            "hard_allergy_restriction_omissions": hard_constraint_omissions,
            "determinism_rate": _ratio(sum(item["deterministic"] for item in rows), turns),
            "planner_latency_ms": _distribution(latency_values),
            "exact_context_token_reduction": _distribution(exact_reductions),
            "approximate_context_token_reduction": _distribution(approximate_reductions),
            "actual_context_token_comparison": {
                "exact_tokenizer_records": exact_token_records,
                "approximate_tokenizer_records": approximate_token_records,
                **{key: _distribution(values) for key, values in token_fields.items()},
            },
        },
        "metric_counts": {
            "turns": turns,
            "intent_correct": sum(item["intent_correct"] for item in rows),
            "required_source_hits": required_hits,
            "required_source_total": required_total,
            "safety_source_hits": safety_hits,
            "safety_source_total": safety_total,
            "rag_correct": sum(item["rag_correct"] for item in rows),
            "tool_hits": tool_hits, "tool_actual": tool_actual, "tool_expected": tool_expected,
            "expected_no_write": len(expected_no_write),
            "false_write_permissions": sum(item["write_permitted"] for item in expected_no_write),
        },
        "failure_taxonomy": dict(sorted(failure_counts.items())),
        "failed_cases": [item for item in rows if item["failures"]],
    }


__all__ = ["evaluate_frozen_dataset"]
