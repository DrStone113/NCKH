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
    MetricDefinition(name="calculate_tdee_tool_invoked", direction="higher_is_better", unit="binary", deterministic_inputs=("run tool trace",), description="Whether calculate_tdee was invoked when the arm offered it."),
    MetricDefinition(name="calculate_tdee_tool_succeeded", direction="higher_is_better", unit="binary", deterministic_inputs=("run tool trace",), description="Whether at least one calculate_tdee invocation completed successfully."),
    MetricDefinition(name="calculate_tdee_argument_match_rate", direction="higher_is_better", unit="proportion", deterministic_inputs=("benchmark profile", "tool arguments"), description="Exact match rate between benchmark profile fields and calculate_tdee arguments."),
    MetricDefinition(name="tool_numerical_absolute_error", direction="lower_is_better", unit="source unit", deterministic_inputs=("expected", "structured tool result"), description="Absolute difference between a benchmark value and the corresponding structured calculate_tdee result."),
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


def _visible_response(text: str) -> str:
    """Exclude provider-exposed reasoning blocks from answer-content metrics."""

    return re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )


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


def _cited_retrieval_chunks(
    record: ExperimentRunRecord, response: str
) -> list[dict[str, Any]]:
    if record.retrieval_trace is None:
        return []
    return [
        chunk
        for chunk in record.retrieval_trace.get("chunks", [])
        if isinstance(chunk.get("chunk_id"), str)
        and f"[{chunk['chunk_id']}]" in response
    ]


def _citation_presence(
    case: BenchmarkCase, response: str, record: ExperimentRunRecord
) -> MetricResult:
    if not case.scoring_metadata.citation_required:
        return MetricResult(metric="citation_presence", status="not_applicable", value=None)
    normalized = _normalize(response)
    markers = ("nguon", "source", "vien dinh duong", "who", "doi:")
    cited_chunks = _cited_retrieval_chunks(record, response)
    present = bool(cited_chunks) or any(marker in normalized for marker in markers)
    return MetricResult(
        metric="citation_presence",
        status="scored",
        value=int(present),
        details={"cited_retrieval_chunk_ids": [chunk["chunk_id"] for chunk in cited_chunks]},
    )


def _citation_source_correctness(
    case: BenchmarkCase,
    response: str,
    record: ExperimentRunRecord,
    annotations: EvaluationAnnotations | None,
) -> MetricResult:
    if not case.reference_sources:
        return MetricResult(
            metric="citation_source_correctness",
            status="not_applicable",
            value=None,
        )
    valid = {source.source_id for source in case.reference_sources}
    if annotations is not None and annotations.cited_source_ids:
        cited = set(annotations.cited_source_ids)
        return MetricResult(
            metric="citation_source_correctness",
            status="scored",
            value=len(cited & valid) / len(cited),
            details={"scoring_mode": "explicit_annotation"},
        )

    relevant_coordinates = {
        (source.dataset_file, source.source_record_id)
        for source in case.reference_sources
        if source.source_type == "frozen_corpus_record"
    }
    cited_chunks = _cited_retrieval_chunks(record, response)
    if record.retrieval_trace is None or not relevant_coordinates:
        return MetricResult(
            metric="citation_source_correctness",
            status="requires_annotation",
            value=None,
        )
    correct = sum(
        (
            chunk.get("source", {}).get("dataset_file"),
            chunk.get("source", {}).get("source_record_id"),
        )
        in relevant_coordinates
        for chunk in cited_chunks
    )
    return MetricResult(
        metric="citation_source_correctness",
        status="scored",
        value=0.0 if not cited_chunks else correct / len(cited_chunks),
        details={
            "scoring_mode": "retrieval_chunk_id",
            "cited_count": len(cited_chunks),
            "correct_count": correct,
        },
    )


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


_NUMBER_TOKEN = (
    r"-?(?:\d{1,3}(?:[ .\u00a0,]\d{3})+|\d+)(?:[.,]\d+)?"
)


def _parse_localized_number(token: str) -> float | None:
    compact = re.sub(r"[\s\u00a0]", "", token)
    if not compact:
        return None
    sign = ""
    if compact[0] in "+-":
        sign, compact = compact[0], compact[1:]
    if not compact:
        return None

    if "." in compact and "," in compact:
        decimal_separator = "." if compact.rfind(".") > compact.rfind(",") else ","
        thousands_separator = "," if decimal_separator == "." else "."
        compact = compact.replace(thousands_separator, "")
        compact = compact.replace(decimal_separator, ".")
    elif "." in compact or "," in compact:
        separator = "." if "." in compact else ","
        groups = compact.split(separator)
        if (
            len(groups) > 2
            and all(len(group) == 3 for group in groups[1:])
        ) or (
            len(groups) == 2
            and 1 <= len(groups[0]) <= 3
            and len(groups[1]) == 3
        ):
            compact = "".join(groups)
        elif len(groups) == 2:
            compact = ".".join(groups)
        else:
            return None
    try:
        return float(sign + compact)
    except ValueError:
        return None


def extract_numeric_value(
    response: str,
    labels: tuple[str, ...],
    *,
    unit: str | None = None,
) -> float | None:
    """Extract a same-line keyed value followed by its declared unit.

    Requiring the unit avoids treating section ordinals, activity factors, and
    percentage adjustments as the requested result.  We intentionally do not
    infer a value from an unkeyed number elsewhere in the answer.
    """

    normalized = _normalize(_visible_response(response))
    normalized = normalized.replace("{,}", ",").replace("{.}", ".")
    lines = normalized.splitlines()
    unit_aliases = {
        "kg/m^2": ("kg/m^2", "kg/m2", "kg/m²"),
        "kcal/day": ("kcal/day", "kcal/ngay", "calo/ngay"),
    }.get(unit or "", (unit,) if unit else ())
    normalized_unit_aliases = tuple(
        _normalize(alias) for alias in unit_aliases if alias
    )

    def qualified_number(
        segment: str, *, allow_unitless_bmi: bool = False
    ) -> float | None:
        for number_match in re.finditer(_NUMBER_TOKEN, segment):
            if number_match.start() > 100:
                break
            if normalized_unit_aliases:
                after_number = segment[number_match.end() :]
                range_tail = (
                    rf"^[^\d\n]{{0,20}}?"
                    rf"(?:{_NUMBER_TOKEN}[^\d\n]{{0,20}}?)?"
                    rf"(?:{'|'.join(re.escape(alias) for alias in normalized_unit_aliases)})"
                )
                if not re.search(range_tail, after_number):
                    # BMI is routinely reported as an index without its
                    # conventional kg/m^2 unit.  A keyed same-line BMI value
                    # remains unambiguous, unlike an unqualified energy value.
                    if unit != "kg/m^2" or not allow_unitless_bmi:
                        continue
            parsed = _parse_localized_number(number_match.group(0))
            if parsed is not None:
                return parsed
        return None

    for label in labels:
        normalized_label = _normalize(label)
        if normalized_label in normalized_unit_aliases:
            # A unit such as ``kcal/day`` is not a semantic label and would
            # otherwise make every energy value a candidate for every metric.
            continue
        escaped = re.escape(normalized_label)
        candidates: list[float] = []
        unitless_bmi_candidates: list[float] = []
        for line_index, line in enumerate(lines):
            for label_match in re.finditer(escaped, line):
                suffix = line[label_match.end() : label_match.end() + 180]
                parsed = qualified_number(suffix)
                if parsed is not None:
                    candidates.append(parsed)
                    continue
                if unit == "kg/m^2" and "|" in line:
                    parsed = qualified_number(suffix, allow_unitless_bmi=True)
                    if parsed is not None:
                        unitless_bmi_candidates.append(parsed)
                        continue
                if line.lstrip().startswith("#"):
                    # Some tool-grounded answers put the label in a section
                    # heading and the sole value in an otherwise unlabeled
                    # table row directly below it.
                    section_lines: list[str] = []
                    for following in lines[line_index + 1 : line_index + 8]:
                        if following.lstrip().startswith("#"):
                            break
                        section_lines.append(following)
                    for following in section_lines:
                        parsed = qualified_number(following)
                        if parsed is not None:
                            candidates.append(parsed)
                            break
        if candidates:
            # Prefer the final explicit summary when a value is restated.
            return candidates[-1]
        if unitless_bmi_candidates:
            return unitless_bmi_candidates[-1]
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
            aliases = {
                "calorie-target": (
                    "mức năng lượng mục tiêu",
                    "năng lượng mục tiêu",
                    "mức mục tiêu",
                    "mục tiêu",
                    "mục tiêu năng lượng",
                    "lượng calo mục tiêu",
                    "mức khuyến nghị",
                    "duy trì cân nặng",
                    "calorie target",
                    "target daily energy",
                )
            }.get(expected.value_id, ())
            observed = extract_numeric_value(
                response,
                (*aliases, *expected.accepted_labels),
                unit=expected.unit,
            )
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


_TOOL_RESULT_FIELDS = {
    "bmi": "bmi",
    "rmr": "estimated_rmr_kcal_per_day",
    "tdee": "estimated_tdee_kcal_per_day",
    "calorie-target": "calorie_target_kcal_per_day",
}


def _calculate_tdee_tool_metrics(
    case: BenchmarkCase, record: ExperimentRunRecord
) -> list[MetricResult]:
    offered = "calculate_tdee" in record.tools_offered
    calls = [
        call for call in record.tool_calls if call.get("name") == "calculate_tdee"
    ]
    successful = [
        call
        for call in calls
        if call.get("ok") is True and isinstance(call.get("result"), dict)
    ]
    base_status = "scored" if offered else "not_applicable"
    results = [
        MetricResult(
            metric="calculate_tdee_tool_invoked",
            status=base_status,
            value=int(bool(calls)) if offered else None,
        ),
        MetricResult(
            metric="calculate_tdee_tool_succeeded",
            status=base_status,
            value=int(bool(successful)) if offered else None,
        ),
    ]
    if not offered:
        results.append(
            MetricResult(
                metric="calculate_tdee_argument_match_rate",
                status="not_applicable",
                value=None,
            )
        )
        results.extend(
            MetricResult(
                metric="tool_numerical_absolute_error",
                status="not_applicable",
                value=None,
                details={"value_id": expected.value_id},
            )
            for expected in case.objective_expected_values
        )
        return results
    if not successful:
        results.append(
            MetricResult(
                metric="calculate_tdee_argument_match_rate",
                status="extraction_failed",
                value=None,
            )
        )
        results.extend(
            MetricResult(
                metric="tool_numerical_absolute_error",
                status="extraction_failed",
                value=None,
                details={"value_id": expected.value_id},
            )
            for expected in case.objective_expected_values
        )
        return results

    selected = successful[-1]
    arguments = selected.get("arguments") or {}
    expected_arguments = {
        "age": case.profile.age,
        "sex": case.profile.sex,
        "height_cm": case.profile.height_cm,
        "weight_kg": case.profile.weight_kg,
        "activity_level": case.profile.activity_level,
        "goal": case.profile.goal,
    }
    matched_fields = [
        field
        for field, expected_value in expected_arguments.items()
        if arguments.get(field) == expected_value
    ]
    mismatched_fields = sorted(set(expected_arguments) - set(matched_fields))
    results.append(
        MetricResult(
            metric="calculate_tdee_argument_match_rate",
            status="scored",
            value=len(matched_fields) / len(expected_arguments),
            details={"mismatched_fields": mismatched_fields},
        )
    )
    tool_result = selected["result"]
    for expected in case.objective_expected_values:
        field = _TOOL_RESULT_FIELDS.get(expected.value_id)
        observed = tool_result.get(field) if field else None
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            results.append(
                MetricResult(
                    metric="tool_numerical_absolute_error",
                    status="extraction_failed",
                    value=None,
                    details={"value_id": expected.value_id, "result_field": field},
                )
            )
            continue
        absolute = abs(float(observed) - expected.expected)
        relative = (
            absolute
            if expected.expected == 0
            else absolute / abs(expected.expected)
        )
        results.append(
            MetricResult(
                metric="tool_numerical_absolute_error",
                status="scored",
                value=absolute,
                details={
                    "value_id": expected.value_id,
                    "expected": expected.expected,
                    "observed": float(observed),
                    "unit": expected.unit,
                    "result_field": field,
                    "within_absolute_tolerance": absolute
                    <= expected.absolute_tolerance,
                    "within_relative_tolerance": relative
                    <= expected.relative_tolerance,
                },
            )
        )
    return results


def _constraint_metrics(
    case: BenchmarkCase,
    response: str,
    annotations: EvaluationAnnotations | None,
) -> list[MetricResult]:
    if not case.required_constraints:
        return [
            MetricResult(metric="constraint_satisfaction_rate", status="not_applicable", value=None),
            MetricResult(metric="allergen_violation_rate", status="not_applicable", value=None),
            MetricResult(metric="dietary_restriction_violation_rate", status="not_applicable", value=None),
        ]
    scoring_mode = "explicit_annotation"
    if annotations is None:
        if any(
            not constraint.required_terms and not constraint.prohibited_terms
            for constraint in case.required_constraints
        ):
            return [
                MetricResult(metric=name, status="requires_annotation", value=None)
                for name in (
                    "constraint_satisfaction_rate",
                    "allergen_violation_rate",
                    "dietary_restriction_violation_rate",
                )
            ]
        scoring_mode = "declared_term_rules"
        normalized = _normalize(response)
        satisfied = set()
        violated = set()
        for constraint in case.required_constraints:
            required_ok = not constraint.required_terms or any(
                _normalize(term) in normalized for term in constraint.required_terms
            )
            prohibited_hit = any(
                _normalize(term) in normalized for term in constraint.prohibited_terms
            )
            if prohibited_hit:
                violated.add(constraint.constraint_id)
            if required_ok and not prohibited_hit:
                satisfied.add(constraint.constraint_id)
    else:
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
        return MetricResult(
            metric=metric,
            status="scored",
            value=len(ids & selected) / len(ids),
            details={"scoring_mode": scoring_mode},
        )

    return [
        MetricResult(
            metric="constraint_satisfaction_rate",
            status="scored",
            value=len(all_ids & satisfied) / len(all_ids),
            details={
                "scoring_mode": scoring_mode,
                "satisfied_constraint_ids": sorted(all_ids & satisfied),
                "violated_constraint_ids": sorted(all_ids & violated),
            },
        ),
        rate(allergen_ids, violation=True),
        rate(dietary_ids, violation=True),
    ]


def evaluate_record(
    case: BenchmarkCase,
    record: ExperimentRunRecord,
    annotations: EvaluationAnnotations | None = None,
) -> tuple[MetricResult, ...]:
    """Score only deterministic or explicitly annotated quantities."""

    visible_response = _visible_response(record.final_response)
    results = [
        MetricResult(metric="latency", status="scored", value=record.latency_ms),
        _fact_coverage(case, visible_response),
        _citation_presence(case, visible_response, record),
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
    results.extend(_numeric_metrics(case, visible_response, annotations))
    results.extend(_calculate_tdee_tool_metrics(case, record))
    results.extend(_constraint_metrics(case, visible_response, annotations))
    results.append(
        _citation_source_correctness(
            case, visible_response, record, annotations
        )
    )
    return tuple(results)


__all__ = [
    "EvaluationAnnotations",
    "MetricDefinition",
    "MetricResult",
    "OBJECTIVE_METRICS",
    "evaluate_record",
    "extract_numeric_value",
]
