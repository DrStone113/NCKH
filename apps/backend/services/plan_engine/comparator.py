"""Engineering acceptance comparator for legacy plans and Plan V2.

The comparator evaluates semantic invariants.  It is deliberately not a
scientific evaluation and does not require dish/exercise byte equality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping


class ComparatorVerdict(str, Enum):
    V2_BETTER = "V2_BETTER"
    V2_EQUIVALENT = "V2_EQUIVALENT"
    V2_ACCEPTABLE_DIFFERENCE = "V2_ACCEPTABLE_DIFFERENCE"
    V2_REGRESSION = "V2_REGRESSION"
    NOT_COMPARABLE = "NOT_COMPARABLE"


_DIMENSIONS = (
    "request_completion_status", "hard_constraint_violations", "canonical_entity_validity",
    "nutrition_target_applicability", "dietary_restriction_adherence", "allergen_adherence",
    "food_exclusion_adherence", "workout_safety_compliance", "equipment_compliance",
    "exercise_policy_compliance", "time_budget_compliance", "planned_to_actual_leakage",
    "unintended_writes", "determinism", "plan_completeness", "user_requested_schedule_adherence",
    "lifecycle_correctness",
)
_HARD_DIMENSIONS = frozenset(
    {
        "hard_constraint_violations", "canonical_entity_validity", "dietary_restriction_adherence",
        "allergen_adherence", "food_exclusion_adherence", "workout_safety_compliance",
        "equipment_compliance", "exercise_policy_compliance", "time_budget_compliance",
        "planned_to_actual_leakage", "unintended_writes",
    }
)


@dataclass(frozen=True, slots=True)
class ComparableDimension:
    name: str
    legacy: str
    v2: str
    comparable: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class PlanComparisonResult:
    case_id: str
    legacy_status: str
    v2_status: str
    legacy_plan_summary: Mapping[str, Any]
    v2_plan_summary: Mapping[str, Any]
    comparable_dimensions: tuple[ComparableDimension, ...]
    hard_violations_legacy: tuple[str, ...]
    hard_violations_v2: tuple[str, ...]
    soft_differences: tuple[str, ...]
    latency_legacy_ms: float
    latency_v2_ms: float
    verdict: ComparatorVerdict
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["verdict"] = self.verdict.value
        return result


class PlanV2Comparator:
    """Compare normalized plan result mappings supplied by adapters/callers."""

    dimensions = _DIMENSIONS

    def compare(
        self,
        *,
        case_id: str,
        legacy: Mapping[str, Any] | None,
        v2: Mapping[str, Any] | None,
        latency_legacy_ms: float = 0.0,
        latency_v2_ms: float = 0.0,
    ) -> PlanComparisonResult:
        legacy_data = dict(legacy or {})
        v2_data = dict(v2 or {})
        legacy_status = str(legacy_data.get("status") or "NOT_AVAILABLE")
        v2_status = str(v2_data.get("status") or "NOT_AVAILABLE")
        legacy_hard = _hard_violations(legacy_data)
        v2_hard = _hard_violations(v2_data)
        comparisons: list[ComparableDimension] = []
        soft: list[str] = []
        for dimension in self.dimensions:
            legacy_value, legacy_known = _dimension(legacy_data, dimension)
            v2_value, v2_known = _dimension(v2_data, dimension)
            comparable = legacy_known and v2_known
            if not comparable:
                comparisons.append(ComparableDimension(dimension, legacy_value, v2_value, False, "NOT_COMPARABLE"))
                continue
            reason = "SEMANTIC_MATCH" if legacy_value == v2_value else "SEMANTIC_DIFFERENCE"
            comparisons.append(ComparableDimension(dimension, legacy_value, v2_value, True, reason))
            if dimension not in _HARD_DIMENSIONS and legacy_value != v2_value:
                soft.append(f"{dimension}:{legacy_value}->{v2_value}")
        verdict, reasons = _verdict(legacy_status, v2_status, legacy_hard, v2_hard, comparisons)
        return PlanComparisonResult(
            case_id=case_id, legacy_status=legacy_status, v2_status=v2_status,
            legacy_plan_summary=_summary(legacy_data), v2_plan_summary=_summary(v2_data),
            comparable_dimensions=tuple(comparisons), hard_violations_legacy=tuple(legacy_hard),
            hard_violations_v2=tuple(v2_hard), soft_differences=tuple(soft),
            latency_legacy_ms=round(latency_legacy_ms, 3), latency_v2_ms=round(latency_v2_ms, 3),
            verdict=verdict, reason_codes=tuple(reasons),
        )

    def run_case(
        self, *, case_id: str, legacy_runner: Callable[[], Mapping[str, Any]], v2_runner: Callable[[], Mapping[str, Any]]
    ) -> PlanComparisonResult:
        started = perf_counter()
        legacy = legacy_runner()
        legacy_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        v2 = v2_runner()
        v2_ms = (perf_counter() - started) * 1000
        return self.compare(case_id=case_id, legacy=legacy, v2=v2, latency_legacy_ms=legacy_ms, latency_v2_ms=v2_ms)

    @staticmethod
    def acceptance_metrics(results: Iterable[PlanComparisonResult]) -> dict[str, Any]:
        rows = tuple(results)
        comparable = [row for row in rows if row.verdict is not ComparatorVerdict.NOT_COMPARABLE]
        semantic = [row for row in comparable if row.verdict is not ComparatorVerdict.V2_REGRESSION]
        return {
            "case_count": len(rows), "comparable_case_count": len(comparable),
            "v2_hard_constraint_violations": sum(len(row.hard_violations_v2) for row in rows),
            "v2_planned_to_actual_leakage": sum("PLANNED_TO_ACTUAL_LEAKAGE" in row.hard_violations_v2 for row in rows),
            "v2_unintended_writes": sum("UNINTENDED_WRITE" in row.hard_violations_v2 for row in rows),
            "request_semantic_match_percent": round(100 * len(semantic) / len(comparable), 2) if comparable else None,
            "verdict_counts": {value.value: sum(row.verdict is value for row in rows) for value in ComparatorVerdict},
        }


def _summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    plan = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else payload
    items = plan.get("items") if isinstance(plan, Mapping) else None
    return {
        "domain": plan.get("domain") if isinstance(plan, Mapping) else None,
        "item_count": len(items) if isinstance(items, list) else 0,
        "lifecycle_status": plan.get("lifecycle_status") if isinstance(plan, Mapping) else None,
        "planned_not_actual": plan.get("planned_not_actual") if isinstance(plan, Mapping) else None,
    }


def _hard_violations(payload: Mapping[str, Any]) -> list[str]:
    validation = payload.get("validation")
    issues = validation.get("issues") if isinstance(validation, Mapping) else None
    found = [str(item.get("code")) for item in issues if isinstance(item, Mapping) and item.get("severity") == "HARD"] if isinstance(issues, list) else []
    hard_count = validation.get("hard_violation_count") if isinstance(validation, Mapping) else None
    if isinstance(hard_count, (int, float)) and hard_count > len(found):
        found.extend(["UNSPECIFIED_HARD_VIOLATION"] * (int(hard_count) - len(found)))
    for marker, code in (("planned_to_actual_leakage", "PLANNED_TO_ACTUAL_LEAKAGE"), ("unintended_writes", "UNINTENDED_WRITE")):
        if payload.get(marker) is True:
            found.append(code)
    return list(dict.fromkeys(found))


def _dimension(payload: Mapping[str, Any], name: str) -> tuple[str, bool]:
    # Adapters may provide a direct normalized dimension.  This keeps legacy
    # lack-of-concept explicit rather than pretending absent data is a failure.
    dimensions = payload.get("comparison_dimensions")
    if isinstance(dimensions, Mapping) and name in dimensions:
        value = dimensions[name]
        if value is None or value == "NOT_COMPARABLE":
            return "NOT_COMPARABLE", False
        return str(value), True
    validation = payload.get("validation") if isinstance(payload.get("validation"), Mapping) else {}
    plan = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else payload
    mapping = {
        "request_completion_status": payload.get("status"),
        "hard_constraint_violations": validation.get("hard_violation_count"),
        "canonical_entity_validity": not any("CANONICAL" in code for code in _hard_violations(payload)),
        "planned_to_actual_leakage": "PLANNED_TO_ACTUAL_LEAKAGE" not in _hard_violations(payload),
        "unintended_writes": "UNINTENDED_WRITE" not in _hard_violations(payload),
        "lifecycle_correctness": plan.get("lifecycle_status") if isinstance(plan, Mapping) else None,
        "plan_completeness": len(plan.get("items", [])) if isinstance(plan, Mapping) and isinstance(plan.get("items"), list) else None,
    }
    value = mapping.get(name)
    return (str(value), value is not None)


def _verdict(
    legacy_status: str, v2_status: str, legacy_hard: list[str], v2_hard: list[str], dimensions: list[ComparableDimension]
) -> tuple[ComparatorVerdict, list[str]]:
    if not any(item.comparable for item in dimensions):
        return ComparatorVerdict.NOT_COMPARABLE, ["NO_SHARED_SEMANTIC_DIMENSIONS"]
    if not v2_hard and legacy_hard:
        return ComparatorVerdict.V2_BETTER, ["V2_PREVENTED_LEGACY_HARD_VIOLATION"]
    if v2_hard and not legacy_hard:
        return ComparatorVerdict.V2_REGRESSION, ["V2_HARD_INVARIANT_VIOLATION"]
    if v2_status in {"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"} and legacy_status in {"READY", "SUCCESS"}:
        return ComparatorVerdict.V2_BETTER, ["V2_SAFE_REJECTION_OR_CLARIFICATION"]
    hard_differences = [item for item in dimensions if item.comparable and item.name in _HARD_DIMENSIONS and item.legacy != item.v2]
    if hard_differences:
        return ComparatorVerdict.V2_REGRESSION, ["COMPARABLE_HARD_SEMANTIC_REGRESSION"]
    soft_differences = [item for item in dimensions if item.comparable and item.legacy != item.v2]
    if soft_differences:
        return ComparatorVerdict.V2_ACCEPTABLE_DIFFERENCE, ["NON_IDENTICAL_SEMANTICALLY_SAFE_PLAN"]
    return ComparatorVerdict.V2_EQUIVALENT, ["SEMANTICALLY_EQUIVALENT"]


__all__ = ["ComparableDimension", "ComparatorVerdict", "PlanComparisonResult", "PlanV2Comparator"]
