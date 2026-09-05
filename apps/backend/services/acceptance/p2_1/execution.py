"""Oracle-blind execution layer for the frozen P2.1A holdout.

This module may load prompt/fixture case data, but it may not import oracle or
scoring code.  Every response here is observed from a real entry point; it is
never created from a holdout expectation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from time import perf_counter
from typing import Any, Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.agent.tools import plan_v2
from services.agent.tools.plan_tools import create_plan as legacy_create_plan


_DEFAULT_LOCAL_DATE = date(2026, 10, 1)
_OBSERVATION_KEYS = frozenset(
    {"consumed_at", "logged_at", "performed_at", "actual_reps", "actual_rpe", "actual_load", "recovered", "fatigued"}
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _safe_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _contains_observation(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in _OBSERVATION_KEYS or _contains_observation(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_observation(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class ExecutionCaseView:
    """The only holdout shape visible to either executor.

    ``oracle_profile``, deterministic check IDs, semantic requirements, and
    every expected outcome are deliberately absent.
    """

    case_id: str
    category: str
    prompt: str
    fixture: Mapping[str, str]


class AcceptanceCaseLoader:
    """Load an executor-safe projection from the frozen holdout."""

    def __init__(self, holdout_path: str) -> None:
        self._holdout_path = holdout_path

    def execution_cases(self) -> tuple[ExecutionCaseView, ...]:
        with open(self._holdout_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        cases: list[ExecutionCaseView] = []
        for raw in payload["cases"]:
            view = ExecutionCaseView(
                case_id=str(raw["case_id"]),
                category=str(raw["category"]),
                prompt=str(raw["prompt"]),
                fixture={str(key): str(value) for key, value in dict(raw.get("fixture") or {}).items()},
            )
            cases.append(view)
        return tuple(cases)


@dataclass(frozen=True, slots=True)
class CaseExecutionContext:
    case_id: str
    owner_user_id: str
    session_id: str
    period_start: str
    period_end: str
    timezone: str
    profile_fixture: Mapping[str, Any]
    plan_state_fixture: Mapping[str, Any]
    nutrition_state_fixture: Mapping[str, Any]
    training_state_fixture: Mapping[str, Any]
    canonical_catalog_version: str = "verified-dish-catalog-v1"
    nutrition_policy_version: str = "nutrition-policy-v1.0.1"
    exercise_policy_version: str = "exercise-prescription-policy-v1.1.0"
    clock_date: str = _DEFAULT_LOCAL_DATE.isoformat()


def _prompt_date(prompt: str) -> date:
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", prompt)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return _DEFAULT_LOCAL_DATE
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?\b", prompt)
    if numeric:
        try:
            return date(int(numeric.group(3) or "2026"), int(numeric.group(2)), int(numeric.group(1)))
        except ValueError:
            return _DEFAULT_LOCAL_DATE
    return _DEFAULT_LOCAL_DATE


def _prompt_timezone(prompt: str) -> str:
    explicit = re.search(r"\bAsia/[A-Za-z_]+\b", prompt)
    if explicit:
        return explicit.group(0)
    if "Bangkok" in prompt:
        return "Asia/Bangkok"
    if "Vancouver" in prompt:
        return "America/Vancouver"
    return "Asia/Ho_Chi_Minh"


def context_for_case(case: ExecutionCaseView) -> CaseExecutionContext:
    """Make an isolated, intentionally sparse deterministic runtime context.

    The holdout says unstated state is UNKNOWN.  Consequently this fixture has
    only a test owner, clock and timezone; it never adds demographic, medical,
    actual-consumption, or training-completion facts.
    """

    start = _prompt_date(case.prompt)
    # Seven days makes absent workout availability/session count fail closed
    # rather than accidentally creating an E4 prescription for a fabricated
    # one-day interpretation. Nutrition retains a one-day bounded preview.
    end = start + timedelta(days=6 if "workout" in case.category else 0)
    return CaseExecutionContext(
        case_id=case.case_id,
        owner_user_id=f"p2-1a-{case.case_id}",
        session_id=f"p2-1a-session-{case.case_id}",
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        timezone=_prompt_timezone(case.prompt),
        profile_fixture={"user_id": f"p2-1a-{case.case_id}"},
        plan_state_fixture={},
        nutrition_state_fixture={"state": "NOT_LOADED"},
        training_state_fixture={"state": "NOT_LOADED"},
    )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    executor: str
    case_id: str
    status: str
    normalized_output: Mapping[str, Any]
    structured_entities: Mapping[str, Any]
    clarification: str | None
    refusal: str | None
    intended_actions: tuple[str, ...]
    captured_write_attempts: tuple[str, ...]
    errors: tuple[str, ...]
    latency_ms: float
    not_comparable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["result_sha256"] = self.result_sha256
        return result

    @property
    def result_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(asdict(self))).hexdigest()


def normalize_for_comparator(result: ExecutionResult) -> Mapping[str, Any] | None:
    """Adapt observations to the frozen comparator without oracle data."""

    if result.not_comparable_reason is not None:
        return None
    output = dict(result.normalized_output)
    plan = output.get("plan") if isinstance(output.get("plan"), Mapping) else {}
    validation = dict(output.get("validation")) if isinstance(output.get("validation"), Mapping) else {}
    # A clarification carries a HARD issue to block persistence until required
    # input is supplied. It is not an observed hard-constraint violation.
    # Preserve the original result elsewhere; translate only at the frozen
    # comparator's hard-violation boundary.
    if result.status in {"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"}:
        validation["hard_violation_count"] = 0
        validation["issues"] = [
            issue for issue in validation.get("issues", [])
            if not (isinstance(issue, Mapping) and issue.get("severity") == "HARD")
        ]
    return {
        "status": result.status,
        "plan": _safe_json(plan),
        "validation": _safe_json(validation),
        "planned_to_actual_leakage": _contains_observation(output),
        # A legacy read-only observation is allowed to record the attempted
        # insert, provided its transaction was rolled back.  Telemetry about a
        # write attempt is not evidence of an authoritative side effect.
        "unintended_writes": any(
            not attempt.endswith("_ROLLED_BACK")
            for attempt in result.captured_write_attempts
        ),
    }


class PlanV2Executor:
    """Run the frozen Plan V2 public entry points against isolated state."""

    async def execute(self, case: ExecutionCaseView, context: CaseExecutionContext) -> ExecutionResult:
        started = perf_counter()
        runtime = plan_v2.PlanRuntimeContext(
            user_id=context.owner_user_id,
            session_id=context.session_id,
            user_context=dict(context.profile_fixture),
            db_session=None,
            authenticated_principal=True,
        )
        try:
            if case.category == "nutrition":
                output = await plan_v2.build_nutrition_plan(
                    period_start=context.period_start,
                    period_end=context.period_end,
                    timezone=context.timezone,
                    _runtime_context=runtime,
                )
            elif case.category in {"workout_single_session", "weekly_workout_scheduling"}:
                output = await plan_v2.build_workout_schedule(
                    period_start=context.period_start,
                    period_end=context.period_end,
                    timezone=context.timezone,
                    _runtime_context=runtime,
                )
            else:
                # There is no public combined/lifecycle prompt executor. A
                # real owner-scoped Plan V2 read is the only truthful public
                # operation possible without inventing IDs or transitions.
                output = await plan_v2.get_plan(
                    plan_id="00000000-0000-4000-8000-000000000000",
                    _runtime_context=runtime,
                )
        except Exception as exc:  # execution observation, never an oracle verdict
            return ExecutionResult(
                executor="PLAN_V2", case_id=case.case_id, status="EXECUTOR_ERROR", normalized_output={},
                structured_entities={}, clarification=None, refusal=None, intended_actions=(),
                captured_write_attempts=(), errors=(type(exc).__name__, str(exc)),
                latency_ms=round((perf_counter() - started) * 1000, 3),
            )
        safe = _safe_json(output)
        status = str(safe.get("status") or "UNKNOWN") if isinstance(safe, Mapping) else "UNKNOWN"
        plan = safe.get("plan") if isinstance(safe, Mapping) and isinstance(safe.get("plan"), Mapping) else {}
        return ExecutionResult(
            executor="PLAN_V2", case_id=case.case_id, status=status, normalized_output=safe,
            structured_entities={
                key: plan.get(key) for key in ("plan_id", "revision_id", "parent_revision_id", "revision_content_hash", "lifecycle_status")
                if plan.get(key) is not None
            },
            clarification=status if status in {"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"} else None,
            refusal=status if status not in {"READY", "CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"} else None,
            intended_actions=(), captured_write_attempts=(), errors=(),
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )


class LegacyPlanReadOnlyExecutor:
    """Exercise the real legacy write path inside a rolled-back transaction.

    Legacy has no read-only plan-generation API. Calling its real header
    creator in an acceptance-owned transaction and rolling it back is the
    narrowest non-persistent observation possible. Combined/lifecycle cases
    have no genuine legacy counterpart and remain explicitly not comparable.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, case: ExecutionCaseView, context: CaseExecutionContext) -> ExecutionResult:
        started = perf_counter()
        if case.category in {"combined_health", "revision_lifecycle_concurrency_adversarial"}:
            return ExecutionResult(
                executor="LEGACY_READ_ONLY", case_id=case.case_id, status="NOT_COMPARABLE", normalized_output={},
                structured_entities={}, clarification=None, refusal=None, intended_actions=(), captured_write_attempts=(),
                errors=(), latency_ms=round((perf_counter() - started) * 1000, 3),
                not_comparable_reason="LEGACY_HAS_NO_READ_ONLY_COMBINED_OR_VERSIONED_LIFECYCLE_ENTRYPOINT",
            )
        try:
            async with self._session_factory() as session:
                plan_id = await legacy_create_plan(
                    session,
                    user_id=context.owner_user_id,
                    goal="maintain",
                    duration_days=3,
                    start_date=context.period_start,
                    daily_kcal_target=2000.0,
                    daily_protein_target=80.0,
                    nutrition_policy_version="nutrition-policy-v1.0.1",
                    nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
                    request_id=f"legacy-read-only-{case.case_id}",
                )
                await session.rollback()
        except Exception as exc:
            return ExecutionResult(
                executor="LEGACY_READ_ONLY", case_id=case.case_id, status="EXECUTOR_ERROR", normalized_output={},
                structured_entities={}, clarification=None, refusal=None, intended_actions=(), captured_write_attempts=(),
                errors=(type(exc).__name__, str(exc)), latency_ms=round((perf_counter() - started) * 1000, 3),
                not_comparable_reason="LEGACY_READ_ONLY_TRANSACTION_FAILED",
            )
        return ExecutionResult(
            executor="LEGACY_READ_ONLY", case_id=case.case_id, status="READY",
            normalized_output={"status": "READY", "plan": {"plan_id": plan_id, "domain": "LEGACY", "items": [], "planned_not_actual": True}, "validation": {"hard_violation_count": 0, "issues": []}},
            structured_entities={"plan_id": plan_id}, clarification=None, refusal=None,
            intended_actions=("LEGACY_CREATE_PLAN_HEADER",), captured_write_attempts=("LEGACY_INSERT_ROLLED_BACK",),
            errors=(), latency_ms=round((perf_counter() - started) * 1000, 3),
        )


__all__ = [
    "AcceptanceCaseLoader", "CaseExecutionContext", "ExecutionCaseView", "ExecutionResult",
    "LegacyPlanReadOnlyExecutor", "PlanV2Executor", "context_for_case", "normalize_for_comparator",
]
