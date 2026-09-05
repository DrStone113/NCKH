"""Oracle-blind V3 fixture projection and real-entrypoint execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, Mapping

from services.acceptance.p2_1.execution import (
    CaseExecutionContext,
    ExecutionCaseView,
    ExecutionResult,
    LegacyPlanReadOnlyExecutor,
    _safe_json,
)
from services.agent.tools import plan_v2
from services.plan_engine.contracts import PlanDomain, PlanRequest
from services.plan_engine.engine import PlanContextResolver, PlanEngine


_FORBIDDEN_EXECUTION_FIELDS = frozenset(
    {
        "expected_output",
        "oracle_checks",
        "semantic_verdict",
        "acceptance_result",
        "expected_canonical_entity",
        "expected_comparator_result",
    }
)
_NON_COMPARABLE = frozenset({"combined_health", "revision_lifecycle", "adversarial_safety"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class V3ExecutionCase:
    """The V3 data visible to execution, excluding every oracle field."""

    view: ExecutionCaseView
    execution_fixture: Mapping[str, Any]


class V3CaseLoader:
    """Project frozen V3 cases without opening, accepting, or deriving oracle data."""

    def __init__(self, holdout_path: str) -> None:
        self._holdout_path = holdout_path

    def execution_cases(self) -> tuple[V3ExecutionCase, ...]:
        with open(self._holdout_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        cases: list[V3ExecutionCase] = []
        for raw in payload["cases"]:
            prohibited = _FORBIDDEN_EXECUTION_FIELDS & set(raw)
            if prohibited:
                raise ValueError(f"V3_EXECUTION_PROJECTION_FORBIDDEN_FIELD:{sorted(prohibited)}")
            fixture = dict(raw.get("execution_fixture") or {})
            cases.append(
                V3ExecutionCase(
                    view=ExecutionCaseView(
                        case_id=str(raw["candidate_id"]),
                        category=str(raw["category"]),
                        prompt=str(raw["prompt"]),
                        fixture={"execution_fixture": _canonical(fixture)},
                    ),
                    execution_fixture=fixture,
                )
            )
        return tuple(cases)


def context_for_v3_case(case: V3ExecutionCase) -> CaseExecutionContext:
    fixture = case.execution_fixture
    period = fixture.get("period")
    if isinstance(period, list) and len(period) == 2 and all(isinstance(value, str) for value in period):
        period_start, period_end = period
    else:
        period_start = period_end = "2027-01-01"
    owner = f"p2-v3-{case.view.case_id}"
    profile = dict(fixture.get("profile") or {})
    profile["user_id"] = owner
    return CaseExecutionContext(
        case_id=case.view.case_id,
        owner_user_id=owner,
        session_id=f"p2-v3-session-{case.view.case_id}",
        period_start=period_start,
        period_end=period_end,
        timezone=str(fixture.get("timezone") or "Asia/Ho_Chi_Minh"),
        profile_fixture=profile,
        plan_state_fixture={},
        nutrition_state_fixture={"state": "NOT_LOADED"},
        training_state_fixture={"state": "NOT_LOADED"},
    )


class V3LegacyReadOnlyAdapter:
    """Use the real legacy rollback executor only where a counterpart exists."""

    def __init__(self, executor: LegacyPlanReadOnlyExecutor) -> None:
        self._executor = executor

    async def execute(self, case: V3ExecutionCase, context: CaseExecutionContext) -> ExecutionResult:
        if case.view.category in _NON_COMPARABLE:
            return ExecutionResult(
                executor="LEGACY_READ_ONLY",
                case_id=case.view.case_id,
                status="NOT_COMPARABLE",
                normalized_output={},
                structured_entities={},
                clarification=None,
                refusal=None,
                intended_actions=(),
                captured_write_attempts=(),
                errors=(),
                latency_ms=0.0,
                not_comparable_reason="LEGACY_HAS_NO_EQUIVALENT_V3_ENTRYPOINT",
            )
        category = {
            "single_workout": "workout_single_session",
            "weekly_workout": "weekly_workout_scheduling",
        }.get(case.view.category, case.view.category)
        legacy_view = ExecutionCaseView(
            case_id=case.view.case_id,
            category=category,
            prompt=case.view.prompt,
            fixture=case.view.fixture,
        )
        return await self._executor.execute(legacy_view, context)


class V3PlanV2Executor:
    """Map V3 execution fixtures to existing public Plan V2 entry points."""

    @staticmethod
    def _runtime(context: CaseExecutionContext) -> plan_v2.PlanRuntimeContext:
        return plan_v2.PlanRuntimeContext(
            user_id=context.owner_user_id,
            session_id=context.session_id,
            user_context=dict(context.profile_fixture),
            db_session=None,
            authenticated_principal=True,
        )

    @staticmethod
    def _result(case_id: str, started: float, output: Any, *, actions: tuple[str, ...] = ()) -> ExecutionResult:
        safe = _safe_json(output)
        status = str(safe.get("status") or "UNKNOWN") if isinstance(safe, Mapping) else "UNKNOWN"
        plan = safe.get("plan") if isinstance(safe, Mapping) and isinstance(safe.get("plan"), Mapping) else {}
        return ExecutionResult(
            executor="PLAN_V2",
            case_id=case_id,
            status=status,
            normalized_output=safe,
            structured_entities={
                key: plan.get(key)
                for key in ("plan_id", "revision_id", "parent_revision_id", "revision_content_hash", "lifecycle_status")
                if plan.get(key) is not None
            },
            clarification=status if status in {"CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"} else None,
            refusal=status if status not in {"READY", "CLARIFICATION_REQUIRED", "REQUIRES_SPECIALIST_GUIDANCE"} else None,
            intended_actions=actions,
            captured_write_attempts=(),
            errors=(),
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )

    @staticmethod
    def _exception(case_id: str, started: float, exc: Exception) -> ExecutionResult:
        return ExecutionResult(
            executor="PLAN_V2",
            case_id=case_id,
            status="EXECUTOR_ERROR",
            normalized_output={},
            structured_entities={},
            clarification=None,
            refusal=None,
            intended_actions=(),
            captured_write_attempts=(),
            errors=(type(exc).__name__, str(exc)),
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )

    async def execute(self, case: V3ExecutionCase, context: CaseExecutionContext) -> ExecutionResult:
        started = perf_counter()
        fixture = case.execution_fixture
        runtime = self._runtime(context)
        try:
            if case.view.category == "nutrition":
                output = await plan_v2.build_nutrition_plan(
                    period_start=context.period_start,
                    period_end=context.period_end,
                    timezone=context.timezone,
                    goal_override=str(context.profile_fixture.get("health_goal") or "") or None,
                    _runtime_context=runtime,
                )
            elif case.view.category in {"single_workout", "weekly_workout"}:
                output = await plan_v2.build_workout_schedule(
                    period_start=context.period_start,
                    period_end=context.period_end,
                    timezone=context.timezone,
                    goal_override=str(context.profile_fixture.get("health_goal") or "") or None,
                    duration_minutes=fixture.get("duration_minutes") if isinstance(fixture.get("duration_minutes"), int) else None,
                    equipment=tuple(str(item) for item in fixture.get("equipment", ()) if isinstance(item, str)),
                    number_of_sessions=fixture.get("number_of_sessions") if isinstance(fixture.get("number_of_sessions"), int) else None,
                    available_days=tuple(str(item) for item in fixture.get("available_days", ()) if isinstance(item, str)),
                    duration_by_day=dict(fixture.get("duration_by_day") or {}),
                    _runtime_context=runtime,
                )
            elif case.view.category == "combined_health":
                output = await self._combined_output(context, runtime)
            elif case.view.category == "revision_lifecycle":
                output = await self._lifecycle_output(case, context, runtime)
            elif case.view.category == "adversarial_safety":
                unknown_runtime = plan_v2.PlanRuntimeContext(
                    user_id=context.owner_user_id,
                    session_id=context.session_id,
                    user_context={"user_id": context.owner_user_id},
                    db_session=None,
                    authenticated_principal=True,
                )
                output = await plan_v2.build_nutrition_plan(
                    period_start="2027-01-01",
                    period_end="2027-01-01",
                    timezone=context.timezone,
                    _runtime_context=unknown_runtime,
                )
            else:
                raise ValueError(f"UNSUPPORTED_V3_CATEGORY:{case.view.category}")
        except Exception as exc:  # The observed result, not an oracle verdict.
            return self._exception(case.view.case_id, started, exc)
        return self._result(case.view.case_id, started, output)

    async def _combined_output(
        self, context: CaseExecutionContext, runtime: plan_v2.PlanRuntimeContext
    ) -> Mapping[str, Any]:
        """Provision only the named fixture references, then call PlanEngine."""

        fixture_profile = {
            "user_id": context.owner_user_id,
            "age": 30,
            "equation_sex": "female",
            "height_cm": 165,
            "weight_kg": 60,
            "activity_level": "moderate",
            "health_goal": "maintain",
        }
        child_runtime = plan_v2.PlanRuntimeContext(
            user_id=context.owner_user_id,
            session_id=context.session_id,
            user_context=fixture_profile,
            db_session=None,
            authenticated_principal=True,
        )
        nutrition = await plan_v2.build_nutrition_plan(
            period_start="2027-07-01",
            period_end="2027-07-01",
            timezone=context.timezone,
            _runtime_context=child_runtime,
        )
        workout = await plan_v2.build_workout_schedule(
            period_start="2027-07-01",
            period_end="2027-07-01",
            timezone=context.timezone,
            duration_minutes=30,
            equipment=("bodyweight",),
            number_of_sessions=1,
            available_days=("monday",),
            _runtime_context=child_runtime,
        )
        if nutrition.get("status") != "READY" or workout.get("status") != "READY":
            return {"status": "CLARIFICATION_REQUIRED", "fixture_status": {"nutrition": nutrition.get("status"), "workout": workout.get("status")}}
        repository = PlanEngine().repository
        children = tuple(
            revision
            for revision in (
                repository.get(context.owner_user_id, str(nutrition["plan_id"]), str(nutrition["revision_id"])),
                repository.get(context.owner_user_id, str(workout["plan_id"]), str(workout["revision_id"])),
            )
            if revision is not None
        )
        if len(children) != 2:
            return {"status": "CLARIFICATION_REQUIRED", "fixture_status": "COMBINED_CHILD_PLAN_MISSING"}
        request = PlanRequest(
            domain=PlanDomain.COMBINED_HEALTH,
            period_start=date(2027, 7, 1),
            period_end=date(2027, 7, 1),
            timezone=context.timezone,
            request_source="P2_V3_FIXTURE",
        )
        combined_context = PlanContextResolver.resolve(context.owner_user_id, fixture_profile)
        revision = PlanEngine().build_combined_container(combined_context, request, children)
        return plan_v2._revision_payload(revision)

    async def _lifecycle_output(
        self,
        case: V3ExecutionCase,
        context: CaseExecutionContext,
        runtime: plan_v2.PlanRuntimeContext,
    ) -> Mapping[str, Any]:
        fixture_profile = {
            "user_id": context.owner_user_id,
            "age": 31,
            "equation_sex": "female",
            "height_cm": 164,
            "weight_kg": 60,
            "activity_level": "moderate",
            "health_goal": "maintain",
        }
        fixture_runtime = plan_v2.PlanRuntimeContext(
            user_id=context.owner_user_id,
            session_id=context.session_id,
            user_context=fixture_profile,
            db_session=None,
            authenticated_principal=True,
        )
        preview = await plan_v2.build_nutrition_plan(
            period_start="2027-08-01",
            period_end="2027-08-01",
            timezone=context.timezone,
            _runtime_context=fixture_runtime,
        )
        if preview.get("status") != "READY":
            return preview
        saved = await plan_v2.save_plan(
            plan_id=str(preview["plan_id"]),
            revision_id=str(preview["revision_id"]),
            revision_content_hash=str(preview["revision_content_hash"]),
            request_id=f"p2-v3-fixture-save-{case.view.case_id}",
            activate=False,
            _runtime_context=fixture_runtime,
        )
        if saved.get("status") != "READY":
            return saved
        operation = str(case.execution_fixture.get("operation") or "read_exact")
        plan_id, revision_id = str(saved["plan_id"]), str(saved["revision_id"])
        if operation == "read_exact":
            return await plan_v2.get_plan(plan_id=plan_id, revision_id=revision_id, _runtime_context=fixture_runtime)
        if operation in {"pause", "resume"}:
            activated = await plan_v2.set_plan_status(
                plan_id=plan_id,
                revision_id=revision_id,
                expected_revision_number=1,
                status="ACTIVE",
                request_id=f"p2-v3-fixture-activate-{case.view.case_id}",
                _runtime_context=fixture_runtime,
            )
            if activated.get("status") != "READY":
                return activated
        if operation == "resume":
            paused = await plan_v2.set_plan_status(
                plan_id=plan_id,
                revision_id=revision_id,
                expected_revision_number=1,
                status="PAUSED",
                request_id=f"p2-v3-fixture-pause-{case.view.case_id}",
                _runtime_context=fixture_runtime,
            )
            if paused.get("status") != "READY":
                return paused
        target = {"activate": "ACTIVE", "pause": "PAUSED", "resume": "ACTIVE", "cancel": "CANCELLED"}.get(operation)
        if target is None:
            return {"status": "INVALID_V3_LIFECYCLE_OPERATION"}
        return await plan_v2.set_plan_status(
            plan_id=plan_id,
            revision_id=revision_id,
            expected_revision_number=1,
            status=target,
            request_id=f"p2-v3-fixture-{operation}-{case.view.case_id}",
            _runtime_context=fixture_runtime,
        )


def raw_record(
    *, sequence: int, case: V3ExecutionCase, context: CaseExecutionContext, legacy: ExecutionResult, v2: ExecutionResult
) -> dict[str, Any]:
    """Serialize the observed result without oracle content."""

    record = {
        "sequence": sequence,
        "case_id": case.view.case_id,
        "category": case.view.category,
        "prompt": case.view.prompt,
        "execution_context": {
            "owner_user_id": context.owner_user_id,
            "period_start": context.period_start,
            "period_end": context.period_end,
            "timezone": context.timezone,
        },
        "legacy": legacy.to_dict(),
        "v2": v2.to_dict(),
    }
    record["raw_execution_sha256"] = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
    return record


__all__ = [
    "V3CaseLoader",
    "V3ExecutionCase",
    "V3LegacyReadOnlyAdapter",
    "V3PlanV2Executor",
    "context_for_v3_case",
    "raw_record",
]
