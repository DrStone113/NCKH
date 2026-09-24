"""Keep the public Plan preview router aligned with each builder signature."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from modules.plans import v2_router
from services.auth import AuthenticatedPrincipal
from services.plan_engine.application_service import PlanApplicationService
from services.plan_engine.persistence import PlanAuthorizationError


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["WORKOUT", "COMBINED_HEALTH"])
async def test_workout_preview_does_not_receive_nutrition_only_constraints(monkeypatch, domain):
    nutrition_calls = []
    workout_calls = []

    async def fake_nutrition(**kwargs):
        nutrition_calls.append(kwargs)
        return {"status": "CLARIFICATION_REQUIRED"}

    async def fake_workout(
        *, period_start, period_end, timezone, goal_override,
        temporary_preferences, temporary_exclusions, _runtime_context,
        duration_minutes, number_of_sessions, training_location, equipment,
    ):
        workout_calls.append({"period_start": period_start, "timezone": timezone})
        return {"status": "CLARIFICATION_REQUIRED"}

    monkeypatch.setattr(v2_router.plan_v2, "build_nutrition_plan", fake_nutrition)
    monkeypatch.setattr(v2_router.plan_v2, "build_workout_schedule", fake_workout)
    body = v2_router.DraftRequest(
        domain=domain,
        period_start=date(2026, 9, 23),
        period_end=date(2026, 9, 29),
        timezone="Asia/Ho_Chi_Minh",
        schedule_constraints=["dinner at 18:00"],
    )

    result = await v2_router.create_plan_preview(
        body, principal=AuthenticatedPrincipal(user_id="e2e-owner")
    )

    assert result["status"] == "CLARIFICATION_REQUIRED"
    assert workout_calls
    if domain == "COMBINED_HEALTH":
        assert nutrition_calls[0]["schedule_constraints"] == ["dinner at 18:00"]
    else:
        assert not nutrition_calls


@pytest.mark.asyncio
async def test_missing_owned_preview_is_not_disclosed_as_a_conflict():
    repository = AsyncMock()
    repository.get_preview.return_value = None

    with pytest.raises(PlanAuthorizationError, match="PLAN_NOT_FOUND"):
        await PlanApplicationService(repository).save_exact(
            owner_user_id="other-user",
            plan_id="a-plan",
            revision_id="a-revision",
            content_hash="a" * 64,
            action_id="foreign-save",
        )
    repository.save_exact_revision.assert_not_awaited()


@pytest.mark.asyncio
async def test_combined_preview_exposes_component_clarification_codes(monkeypatch):
    async def nutrition(**kwargs):
        return {"status": "READY", "plan": {}}

    async def workout(**kwargs):
        return {
            "status": "CLARIFICATION_REQUIRED",
            "validation": {"issues": [{"code": "EXERCISE_SAFETY_CONTEXT_REQUIRED"}]},
        }

    monkeypatch.setattr(v2_router.plan_v2, "build_nutrition_plan", nutrition)
    monkeypatch.setattr(v2_router.plan_v2, "build_workout_schedule", workout)
    body = v2_router.DraftRequest(
        domain="COMBINED_HEALTH", period_start=date(2026, 9, 23),
        period_end=date(2026, 9, 29), timezone="Asia/Ho_Chi_Minh",
    )

    result = await v2_router.create_plan_preview(
        body, principal=AuthenticatedPrincipal(user_id="owner"),
    )

    assert result["clarification_codes"] == ["EXERCISE_SAFETY_CONTEXT_REQUIRED"]
