from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from services.plan_engine.comparator import ComparatorVerdict, PlanV2Comparator
from services.plan_engine.contracts import ContextState, ContextValue, PlanDomain, PlanItem, PlanItemType, PlanRequest
from services.plan_engine.engine import MemoryPlanRepository, PlanContextResolver, PlanEngine, PlanValidator
from services.plan_engine.nutrition_horizon import NutritionPlanningHorizonState, variety_score
from services.plan_engine.weekly_scheduler import (
    PlanningHorizonState,
    WeeklyScheduleError,
    WeeklyWorkoutRequest,
    WeeklyWorkoutScheduler,
    validate_weekly_plan,
)


def _request() -> PlanRequest:
    return PlanRequest(PlanDomain.WORKOUT, date(2026, 9, 7), date(2026, 9, 13), "Asia/Ho_Chi_Minh")


def test_weekly_scheduler_preserves_explicit_vietnamese_days():
    plan = WeeklyWorkoutScheduler().schedule(
        WeeklyWorkoutRequest(
            plan_request=_request(), number_of_sessions=3,
            explicit_available_days=("thứ 2", "thứ 4", "thứ 6"), default_duration_minutes=45,
        )
    )

    assert [slot.scheduled_date.isoformat() for slot in plan.slots] == ["2026-09-07", "2026-09-09", "2026-09-11"]
    assert all("USER_REQUESTED_SCHEDULE" in slot.provenance for slot in plan.slots)
    assert all("E4_PER_SESSION_DELEGATION_REQUIRED" in slot.provenance for slot in plan.slots)


def test_weekly_scheduler_count_only_is_deterministic_product_heuristic():
    request = WeeklyWorkoutRequest(plan_request=_request(), number_of_sessions=3, default_duration_minutes=30)
    first = WeeklyWorkoutScheduler().schedule(request)
    second = WeeklyWorkoutScheduler().schedule(request)

    assert first == second
    assert len(first.slots) == 3
    assert all("PRODUCT_SCHEDULING_HEURISTIC" in slot.provenance for slot in first.slots)


@pytest.mark.parametrize("session_count", [2, 3, 4])
@pytest.mark.parametrize("duration", [30, 45, 60])
def test_weekly_scheduler_covers_count_and_time_budgets(session_count: int, duration: int):
    plan = WeeklyWorkoutScheduler().schedule(
        WeeklyWorkoutRequest(plan_request=_request(), number_of_sessions=session_count, default_duration_minutes=duration)
    )

    assert len(plan.slots) == session_count
    assert all(slot.duration_minutes == duration for slot in plan.slots)
    assert validate_weekly_plan(plan) == ()


def test_weekly_scheduler_honours_consecutive_and_uneven_user_availability():
    request = WeeklyWorkoutRequest(
        plan_request=_request(), number_of_sessions=3,
        explicit_available_days=("2026-09-07", "2026-09-08", "2026-09-13"),
        duration_by_day={"2026-09-07": 30, "2026-09-08": 45, "2026-09-13": 60},
    )
    plan = WeeklyWorkoutScheduler().schedule(request)

    assert [slot.scheduled_date.isoformat() for slot in plan.slots] == ["2026-09-07", "2026-09-08", "2026-09-13"]
    assert [slot.duration_minutes for slot in plan.slots] == [30, 45, 60]


def test_weekly_scheduler_fails_closed_when_requested_slots_cannot_fit():
    with pytest.raises(WeeklyScheduleError, match="SCHEDULE_INSUFFICIENT_AVAILABLE_DAYS"):
        WeeklyWorkoutScheduler().schedule(
            WeeklyWorkoutRequest(
                plan_request=_request(), number_of_sessions=3, explicit_available_days=("2026-09-07", "2026-09-09"),
            )
        )


def test_planning_horizon_never_fabricates_actual_training_state():
    actual = ContextValue.unavailable(ContextState.NOT_LOADED, source="TRAINING_STATE")
    horizon = PlanningHorizonState(actual)
    plan = WeeklyWorkoutScheduler().schedule(WeeklyWorkoutRequest(plan_request=_request(), number_of_sessions=2))

    projection = horizon.projection()
    assert projection["planned_is_not_actual"] is True
    assert "recovered" not in projection
    assert validate_weekly_plan(plan, horizon=horizon) == ()


def test_weekly_revision_wraps_one_ready_e4_session_per_slot():
    context = PlanContextResolver.resolve("weekly-owner", {"user_id": "weekly-owner"})
    request = _request()
    slots = WeeklyWorkoutScheduler().schedule(
        WeeklyWorkoutRequest(plan_request=request, number_of_sessions=2, default_duration_minutes=45)
    ).slots
    sessions = tuple(
        (
            slot.scheduled_date,
            {
                "status": "READY",
                "plan_id": f"00000000-0000-4000-8000-00000000000{index + 1}",
                "integration_version": "e4.1",
                "presentation": {
                    "exercises": [{"canonical_exercise_id": f"exercise-{index + 1}"}],
                    "estimated_duration_minutes": 45,
                    "exercise_policy_version": "exercise-prescription-policy-v1.1.0",
                    "catalog_version": "canonical-exercise-v1",
                },
            },
            slot.provenance,
        )
        for index, slot in enumerate(slots)
    )
    revision = PlanEngine(MemoryPlanRepository()).build_workout_revision(context, request, e4_sessions=sessions)

    assert revision.validation.ready
    assert len(revision.items) == 2
    assert all(item.content["e4_presentation"]["exercises"] for item in revision.items)
    assert all("E4_AUTHORITATIVE_PLAN" in item.reason_codes for item in revision.items)


def test_nested_actual_values_in_plan_are_hard_rejected():
    item = PlanItem(
        plan_item_id="1", scheduled_date=date(2026, 9, 7), schedule_slot="workout",
        item_type=PlanItemType.WORKOUT_SESSION, canonical_refs={"exercise_ids": ["e1"]},
        content={"e4_presentation": {"exercises": [{"actual_reps": 8}]}},
    )
    # Build a small valid wrapper with no dependency on E4.
    from services.plan_engine.contracts import PlanLifecycleStatus, PlanRevision, PlanValidationResult, PlanValidationStatus
    revision = PlanRevision(
        plan_id="p", domain=PlanDomain.WORKOUT, revision_id="r", revision_number=1, parent_revision_id=None,
        owner_user_id="u", request=PlanRequest(PlanDomain.WORKOUT, date(2026, 9, 7), date(2026, 9, 7), "Asia/Ho_Chi_Minh"),
        lifecycle_status=PlanLifecycleStatus.DRAFT, validation=PlanValidationResult(PlanValidationStatus.READY),
        policy_versions={}, catalog_versions={}, goal_snapshot={}, constraint_snapshot={}, items=(item,), summary={}, explanation_metadata={}, provenance={},
    )
    assert "PLANNED_TO_ACTUAL_LEAKAGE" in [issue.code for issue in PlanValidator().validate(revision).issues]


def test_nutrition_horizon_is_not_consumed_state_and_variety_is_soft():
    item = PlanItem(
        plan_item_id="m", scheduled_date=date(2026, 9, 7), schedule_slot="breakfast", item_type=PlanItemType.MEAL,
        canonical_refs={"dish_id": "d1", "food_ids": ["f1"]}, content={"total_calories": 300, "primary_protein": "egg"},
    )
    state = NutritionPlanningHorizonState.empty(ContextValue.unavailable(ContextState.NOT_LOADED, source="CONSUMED"))
    state = state.add_planned_meal(item)

    assert state.to_dict()["planned_is_not_consumed"] is True
    assert state.to_dict()["planned_day_totals"]["2026-09-07"]["calories"] == 300
    assert variety_score((item, item))["classification"] == "SOFT_PLANNING_TARGET"


@pytest.mark.parametrize("days", [1, 3, 7])
def test_multi_day_nutrition_keeps_planned_totals_out_of_consumed_state(days: int):
    context = PlanContextResolver.resolve(
        "nutrition-p2",
        {
            "user_id": "nutrition-p2", "age": 28, "equation_sex": "female", "height_cm": 160,
            "weight_kg": 55, "activity_level": "light", "health_goal": "maintain",
            "dietary_restrictions": ["no_pork"],
        },
    )
    revision = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(
        context,
        PlanRequest(PlanDomain.NUTRITION, date(2026, 9, 7), date.fromordinal(date(2026, 9, 7).toordinal() + days - 1), "Asia/Ho_Chi_Minh"),
    )

    assert revision.validation.ready
    assert len(revision.summary["daily"]) == days
    assert revision.provenance["planning_horizon"]["planned_is_not_consumed"] is True
    assert all("consumed_at" not in item.content for item in revision.items)


def test_comparator_counts_safe_v2_rejection_as_better_not_regression():
    result = PlanV2Comparator().compare(
        case_id="safe-reject",
        legacy={"status": "READY", "validation": {"hard_violation_count": 1, "issues": [{"code": "SAFETY", "severity": "HARD"}]}},
        v2={"status": "CLARIFICATION_REQUIRED", "validation": {"hard_violation_count": 0, "issues": []}},
    )

    assert result.verdict is ComparatorVerdict.V2_BETTER
    metrics = PlanV2Comparator.acceptance_metrics((result,))
    assert metrics["v2_hard_constraint_violations"] == 0


def test_p2_acceptance_v1_is_preserved_as_contaminated_development_data():
    root = Path(__file__).resolve().parents[1] / "validation" / "plan_tool_v2_p2"
    raw = (root / "acceptance-v1.json").read_bytes()
    dataset = json.loads(raw)
    manifest = json.loads((root / "acceptance-manifest-v1.json").read_text(encoding="utf-8"))
    qualification = json.loads((root / "acceptance-v1-qualification-status.json").read_text(encoding="utf-8"))

    assert len(dataset["cases"]) >= 120
    assert hashlib.sha256(raw).hexdigest() == manifest["content_sha256"]
    assert manifest["frozen_before_first_acceptance_run"] is True
    assert {case["area"] for case in dataset["cases"]} == set(manifest["distribution"])
    assert qualification["status"] == "CONTAMINATED"
    assert qualification["dataset_role"] == "CONTAMINATED_DEVELOPMENT"
    assert qualification["acceptance_eligible"] is False
