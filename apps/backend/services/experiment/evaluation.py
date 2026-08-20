"""Deterministic metric definitions and non-LLM scoring primitives."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from services.experiment.benchmark import BenchmarkCase
from services.experiment.records import ExperimentRunRecord


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    direction: Literal["higher_is_better", "lower_is_better", "descriptive"]
    unit: str
    deterministic_inputs: tuple[str, ...]
    description: str


OBJECTIVE_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(name="numerical_absolute_error", direction="lower_is_better", unit="source unit", deterministic_inputs=("expected", "observed"), description="Absolute difference between a keyed expected and extracted value."),
    MetricDefinition(name="numerical_relative_error", direction="lower_is_better", unit="proportion", deterministic_inputs=("expected", "observed"), description="Absolute error divided by the absolute expected value."),
    MetricDefinition(name="calorie_target_error", direction="lower_is_better", unit="kcal/day", deterministic_inputs=("expected calorie target", "observed calorie target"), description="Absolute error of a daily calorie target."),
    MetricDefinition(name="constraint_satisfaction_rate", direction="higher_is_better", unit="proportion", deterministic_inputs=("constraint annotations",), description="Satisfied applicable constraints divided by applicable constraints."),
    MetricDefinition(name="allergen_violation_rate", direction="lower_is_better", unit="proportion", deterministic_inputs=("allergen violation annotations",), description="Violated allergen exclusions divided by applicable allergen exclusions."),
    MetricDefinition(name="dietary_restriction_violation_rate", direction="lower_is_better", unit="proportion", deterministic_inputs=("dietary violation annotations",), description="Violated dietary restrictions divided by applicable dietary restrictions."),
    MetricDefinition(name="required_fact_coverage", direction="higher_is_better", unit="proportion", deterministic_inputs=("required acceptable terms", "response text"), description="Required facts with at least one accepted expression divided by required facts."),
    MetricDefinition(name="citation_presence", direction="higher_is_better", unit="binary", deterministic_inputs=("response text",), description="Whether an explicit source attribution is present when required."),
    MetricDefinition(name="citation_source_correctness", direction="higher_is_better", unit="proportion", deterministic_inputs=("citation annotations", "reference source IDs"), description="Correct cited sources divided by cited sources; requires blinded human source annotation when text is ambiguous."),
    MetricDefinition(name="retrieval_recall_at_k", direction="higher_is_better", unit="proportion", deterministic_inputs=("retrieval trace", "corpus references"), description="Whether any relevant frozen corpus record occurs in the retrieved top-k."),
    MetricDefinition(name="retrieval_MRR", direction="higher_is_better", unit="reciprocal rank", deterministic_inputs=("retrieval trace", "corpus references"), description="Reciprocal rank of the first relevant frozen corpus record."),
    MetricDefinition(name="latency", direction="lower_is_better", unit="milliseconds", deterministic_inputs=("run record",), description="Measured isolated run latency, excluding embedding prewarm."),
    MetricDefinition(name="token_usage", direction="descriptive", unit="tokens", deterministic_inputs=("provider usage",), description="Provider-reported prompt, completion, and total tokens."),
)


class EvaluationAnnotations(BaseModel):
    """Non-LLM annotations used where free text cannot be scored safely."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observed_values: dict[str, float] = Field(default_factory=dict)
    satisfied_constraint_ids: tuple[str, ...] = ()
    violated_constraint_ids: tuple[str, ...] = ()
    cited_source_ids: tuple[str, ...] = ()


class MetricResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    status: Literal["scored", "not_applicable", "requires_annotation", "extraction_failed"]
    value: float | int | None
    details: dict[str, Any] = Field(default_factory=dict)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _fact_coverage(case: BenchmarkCase, response: str) -> MetricResult:
    if not case.required_facts:
        return MetricResult(metric="required_fact_coverage", status="not_applicable", value=None)
    normalized = _normalize(response)
    covered = [
        fact.fact_id
        for fact in case.required_facts
        if any(_normalize(term) in normalized for term in fact.acceptable_terms)
    ]
    return MetricResult(
        metric="required_fact_coverage",
        status="scored",
        value=len(covered) / len(case.required_facts),
        details={"covered_fact_ids": covered, "required_count": len(case.required_facts)},
    )


def _citation_presence(case: BenchmarkCase, response: str) -> MetricResult:
    if not case.scoring_metadata.citation_required:
        return MetricResult(metric="citation_presence", status="not_applicable", value=None)
    normalized = _normalize(response)
    markers = ("nguon", "source", "vien dinh duong", "who", "doi:")
    present = any(marker in normalized for marker in markers)
    return MetricResult(metric="citation_presence", status="scored", value=int(present))


def _retrieval_metrics(case: BenchmarkCase, record: ExperimentRunRecord) -> list[MetricResult]:
    relevant = {
        (source.dataset_file, source.source_record_id)
        for source in case.reference_sources
        if source.source_type == "frozen_corpus_record"
    }
    if not relevant or record.retrieval_trace is None:
        status = "not_applicable"
        return [
            MetricResult(metric="retrieval_recall_at_k", status=status, value=None),
            MetricResult(metric="retrieval_MRR", status=status, value=None),
        ]
    chunks = record.retrieval_trace.get("chunks", [])
    first_rank = next(
        (
            index
            for index, chunk in enumerate(chunks, start=1)
            if (
                chunk.get("source", {}).get("dataset_file"),
                chunk.get("source", {}).get("source_record_id"),
            )
            in relevant
        ),
        None,
    )
    return [
        MetricResult(metric="retrieval_recall_at_k", status="scored", value=int(first_rank is not None)),
        MetricResult(metric="retrieval_MRR", status="scored", value=0.0 if first_rank is None else 1.0 / first_rank),
    ]


def extract_numeric_value(response: str, labels: tuple[str, ...]) -> float | None:
    """Extract a nearby number without semantic inference or an LLM judge."""

    normalized = _normalize(response).replace(",", ".")
    for label in labels:
        escaped = re.escape(_normalize(label))
        patterns = (
            rf"{escaped}.{{0,60}}?(-?\d+(?:\.\d+)?)",
            rf"(-?\d+(?:\.\d+)?).{{0,30}}?{escaped}",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                return float(match.group(1))
    return None


def _numeric_metrics(
    case: BenchmarkCase,
    response: str,
    annotations: EvaluationAnnotations | None,
) -> list[MetricResult]:
    results: list[MetricResult] = []
    for expected in case.objective_expected_values:
        observed = None
        if annotations is not None:
            observed = annotations.observed_values.get(expected.value_id)
        if observed is None:
            observed = extract_numeric_value(response, expected.accepted_labels)
        if observed is None:
            results.append(MetricResult(metric=expected.metric, status="extraction_failed", value=None, details={"value_id": expected.value_id}))
            continue
        absolute = abs(observed - expected.expected)
        value = absolute
        if expected.metric == "numerical_relative_error":
            value = math.inf if expected.expected == 0 and absolute else (0.0 if expected.expected == 0 else absolute / abs(expected.expected))
        results.append(
            MetricResult(
                metric=expected.metric,
                status="scored",
                value=value,
                details={
                    "value_id": expected.value_id,
                    "expected": expected.expected,
                    "observed": observed,
                    "unit": expected.unit,
                    "within_absolute_tolerance": absolute <= expected.absolute_tolerance,
                    "within_relative_tolerance": (absolute / abs(expected.expected) if expected.expected else absolute) <= expected.relative_tolerance,
                },
            )
        )
    return results


def _constraint_metrics(
    case: BenchmarkCase, annotations: EvaluationAnnotations | None
) -> list[MetricResult]:
    if not case.required_constraints:
        return [
            MetricResult(metric="constraint_satisfaction_rate", status="not_applicable", value=None),
            MetricResult(metric="allergen_violation_rate", status="not_applicable", value=None),
            MetricResult(metric="dietary_restriction_violation_rate", status="not_applicable", value=None),
        ]
    if annotations is None:
        return [
            MetricResult(metric=name, status="requires_annotation", value=None)
            for name in (
                "constraint_satisfaction_rate",
                "allergen_violation_rate",
                "dietary_restriction_violation_rate",
            )
        ]
    satisfied = set(annotations.satisfied_constraint_ids)
    violated = set(annotations.violated_constraint_ids)
    all_ids = {constraint.constraint_id for constraint in case.required_constraints}
    allergen_ids = {constraint.constraint_id for constraint in case.required_constraints if constraint.constraint_type == "allergen_exclusion"}
    dietary_ids = {constraint.constraint_id for constraint in case.required_constraints if constraint.constraint_type == "dietary_restriction"}

    def rate(ids: set[str], *, violation: bool) -> MetricResult:
        metric = "allergen_violation_rate" if ids is allergen_ids else "dietary_restriction_violation_rate"
        if not ids:
            return MetricResult(metric=metric, status="not_applicable", value=None)
        selected = violated if violation else satisfied
        return MetricResult(metric=metric, status="scored", value=len(ids & selected) / len(ids))

    return [
        MetricResult(metric="constraint_satisfaction_rate", status="scored", value=len(all_ids & satisfied) / len(all_ids)),
        rate(allergen_ids, violation=True),
        rate(dietary_ids, violation=True),
    ]


def evaluate_record(
    case: BenchmarkCase,
    record: ExperimentRunRecord,
    annotations: EvaluationAnnotations | None = None,
) -> tuple[MetricResult, ...]:
    """Score only deterministic or explicitly annotated quantities."""

    results = [
        MetricResult(metric="latency", status="scored", value=record.latency_ms),
        _fact_coverage(case, record.final_response),
        _citation_presence(case, record.final_response),
    ]
    total_tokens = (record.token_usage or {}).get("total_tokens")
    results.append(
        MetricResult(
            metric="token_usage",
            status="scored" if total_tokens is not None else "not_applicable",
            value=total_tokens,
            details=record.token_usage or {},
        )
    )
    results.extend(_retrieval_metrics(case, record))
    results.extend(_numeric_metrics(case, record.final_response, annotations))
    results.extend(_constraint_metrics(case, annotations))
    if case.reference_sources:
        if annotations is None:
            results.append(MetricResult(metric="citation_source_correctness", status="requires_annotation", value=None))
        else:
            valid = {source.source_id for source in case.reference_sources}
            cited = set(annotations.cited_source_ids)
            results.append(MetricResult(metric="citation_source_correctness", status="scored" if cited else "not_applicable", value=(len(cited & valid) / len(cited)) if cited else None))
    return tuple(results)


__all__ = [
    "EvaluationAnnotations",
    "MetricDefinition",
    "MetricResult",
    "OBJECTIVE_METRICS",
    "evaluate_record",
    "extract_numeric_value",
]
