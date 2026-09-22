from __future__ import annotations

from datetime import date
from dataclasses import replace

import pytest

from services.agent.pending_user_action import PendingUserActionStore
from services.agent.tools.plan_v2 import PlanRuntimeContext, _revision_payload, build_nutrition_plan, save_plan
from services.agent.tools import register_server_tools
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry
from services.agent.llm_client import ToolCall
from services.plan_engine.contracts import (
    ContextState,
    PlanDomain,
    PlanItem,
    PlanItemType,
    PlanPatch,
    PlanPatchOperation,
    PlanRequest,
    PlanRevision,
)
from services.plan_engine.development_scenarios import development_scenarios
from services.plan_engine.engine import MemoryPlanRepository, PlanContextResolver, PlanEngine, PlanValidator


def _context(user_id: str = "plan-user"):
    return PlanContextResolver.resolve(
        user_id,
        {
            "user_id": user_id,
            "age": 31,
            "equation_sex": "male",
            "height_cm": 172,
            "weight_kg": 70,
            "activity_level": "moderate",
            "health_goal": "maintain",
            "dietary_restrictions": ["no_pork"],
        },
    )


def _request(start: date = date(2026, 9, 1), end: date = date(2026, 9, 2)):
    return PlanRequest(PlanDomain.NUTRITION, start, end, "Asia/Ho_Chi_Minh")


def test_nutrition_draft_uses_canonical_items_and_never_observations():
    engine = PlanEngine(MemoryPlanRepository())
    revision = engine.build_nutrition_plan(_context(), _request())

    assert revision.validation.ready
    assert revision.lifecycle_status.value == "DRAFT"
    assert len(revision.items) == 6
    assert all(item.canonical_refs["dish_id"] for item in revision.items)
    assert all(item.item_type is PlanItemType.MEAL for item in revision.items)
    assert revision.summary["planned_not_consumed"] is True
    assert all(
        not {"actual_reps", "consumed_at", "logged_at", "performed_at"}.intersection(item.content)
        for item in revision.items
    )


def test_plan_revision_preview_round_trips_with_same_identity_hash():
    revision = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(
        _context(), _request()
    )
    restored = PlanRevision.from_dict(revision.to_dict())

    assert restored == revision
    assert restored.revision_content_hash == revision.revision_content_hash


def test_presentation_exposes_only_provenanced_catalog_images_without_mutating_revision():
    revision = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(
        _context(), _request()
    )
    original_hash = revision.revision_content_hash

    payload = _revision_payload(revision)
    presented_items = [
        item
        for day in payload["presentation"]["days"]
        for item in day["items"]
    ]

    assert revision.revision_content_hash == original_hash
    assert all(
        "image_url" not in item or item["image_url"].startswith("https://")
        for item in presented_items
    )


def test_missing_context_remains_missing_and_is_not_defaulted_to_zero():
    context = PlanContextResolver.resolve("u", {"user_id": "u"})
    revision = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(context, _request())

    assert context.profile.state is ContextState.MISSING
    assert revision.validation.status.value == "CLARIFICATION_REQUIRED"
    assert revision.items == ()


def test_intake_v2_nested_context_and_allergy_are_resolved_authoritatively():
    context = PlanContextResolver.resolve(
        "nested-user",
        {
            "general_profile": {
                "age": 28, "equation_sex": "female", "height_cm": 160,
                "weight_kg": 55, "activity_level": "LIGHT", "health_goal": "MAINTAIN",
            },
            "nutrition_profile": {"food_allergies": ["PEANUT"]},
        },
    )
    revision = PlanEngine(MemoryPlanRepository()).build_nutrition_plan(context, _request())

    assert context.profile.state is ContextState.KNOWN
    assert "no_peanut" in context.dietary_constraints.value
    assert revision.validation.ready
    assert all("PEANUT" not in item.content["allergen_ids"] for item in revision.items)


def test_patch_creates_new_revision_and_preserves_parent():
    engine = PlanEngine(MemoryPlanRepository())
    original = engine.build_nutrition_plan(_context(), _request())
    patch = PlanPatch(
        target_plan_id=original.plan_id,
        target_revision_id=original.revision_id,
        expected_revision_number=original.revision_number,
        operation=PlanPatchOperation.CHANGE_TIME,
        target_item_id=original.items[0].plan_item_id,
        requested_change={"schedule_slot": "snack"},
        request_source="TEST",
        reason="user availability",
    )
    revised = engine.revise(_context(), patch)

    assert revised.revision_number == 2
    assert revised.parent_revision_id == original.revision_id
    assert original.items[0].schedule_slot == "breakfast"
    assert revised.items[0].schedule_slot == "snack"
    assert revised.revision_content_hash != original.revision_content_hash


def test_stale_revision_cannot_branch_silently():
    engine = PlanEngine(MemoryPlanRepository())
    original = engine.build_nutrition_plan(_context(), _request())
    patch = PlanPatch(
        original.plan_id, original.revision_id, PlanPatchOperation.REMOVE_ITEM,
        original.items[0].plan_item_id, {}, "TEST", "remove", original.revision_number,
    )
    engine.revise(_context(), patch)

    with pytest.raises(ValueError, match="PLAN_REVISION_CONFLICT"):
        engine.revise(_context(), patch)


def test_typed_patch_supports_add_replace_goal_and_constraints_without_prose():
    engine = PlanEngine(MemoryPlanRepository())
    original = engine.build_nutrition_plan(_context(), _request())
    added = {
        "plan_item_id": "canonical-added-item",
        "scheduled_date": "2026-09-01",
        "schedule_slot": "snack",
        "item_type": "MEAL",
        "canonical_refs": {"dish_id": 1},
        "content": {"dish_name": "Canonical snack"},
    }
    add = PlanPatch(
        original.plan_id, original.revision_id, PlanPatchOperation.ADD_ITEM, None,
        {"item": added}, "TEST", "add canonical item", original.revision_number,
    )
    revised = engine.revise(_context(), add)
    assert revised.items[-1].plan_item_id == "canonical-added-item"

    replacement = {**added, "schedule_slot": "late_snack", "canonical_refs": {"dish_id": 2}}
    replace = PlanPatch(
        revised.plan_id, revised.revision_id, PlanPatchOperation.REPLACE_ITEM,
        "canonical-added-item", {"item": replacement}, "TEST", "replace", revised.revision_number,
    )
    revised = engine.revise(_context(), replace)
    assert revised.items[-1].plan_item_id == "canonical-added-item"
    assert revised.items[-1].canonical_refs == {"dish_id": 2}

    goal = PlanPatch(
        revised.plan_id, revised.revision_id, PlanPatchOperation.CHANGE_GOAL, None,
        {"goal_override": "maintain"}, "TEST", "goal", revised.revision_number,
    )
    revised = engine.revise(_context(), goal)
    assert revised.request.goal_override == "maintain"

    constraints = PlanPatch(
        revised.plan_id, revised.revision_id, PlanPatchOperation.CHANGE_CONSTRAINT, None,
        {"temporary_exclusions": ["no_peanut"]}, "TEST", "constraint", revised.revision_number,
    )
    revised = engine.revise(_context(), constraints)
    assert revised.request.temporary_exclusions == ("no_peanut",)


def test_cross_user_read_is_rejected():
    engine = PlanEngine(MemoryPlanRepository())
    revision = engine.build_nutrition_plan(_context("owner"), _request())

    assert engine.repository.get("other", revision.plan_id, revision.revision_id) is None


def test_combined_plan_owns_canonical_items_without_mixed_energy_math():
    engine = PlanEngine(MemoryPlanRepository())
    nutrition = engine.build_nutrition_plan(_context(), _request())
    container_request = PlanRequest(
        PlanDomain.COMBINED_HEALTH, date(2026, 9, 1), date(2026, 9, 2), "Asia/Ho_Chi_Minh"
    )
    container = engine.build_combined_container(_context(), container_request, (nutrition,))

    assert len(container.items) == len(nutrition.items)
    assert container.provenance["generator"] == "P2_COMBINED_PLAN_ORCHESTRATOR"
    assert container.provenance["canonical_item_owner"] == "COMBINED_REVISION"
    assert container.summary["meal_item_count"] == len(nutrition.items)
    assert container.provenance["no_cross_domain_energy_compensation"] is True
    assert container.provenance["child_revisions"][0]["revision_id"] == nutrition.revision_id


def test_save_is_exact_idempotent_and_supersedes_overlapping_active_plan():
    engine = PlanEngine(MemoryPlanRepository())
    first = engine.build_nutrition_plan(_context(), _request())
    saved_first = engine.save_exact_revision(
        _context(), plan_id=first.plan_id, revision_id=first.revision_id,
        content_hash_value=first.revision_content_hash, request_id="save-first",
    )
    retried = engine.save_exact_revision(
        _context(), plan_id=first.plan_id, revision_id=first.revision_id,
        content_hash_value=first.revision_content_hash, request_id="save-first",
    )
    second = engine.build_nutrition_plan(_context(), _request())
    saved_second = engine.save_exact_revision(
        _context(), plan_id=second.plan_id, revision_id=second.revision_id,
        content_hash_value=second.revision_content_hash, request_id="save-second",
    )

    assert retried == saved_first
    assert saved_second.lifecycle_status.value == "ACTIVE"
    assert engine.repository.get("plan-user", first.plan_id, first.revision_id).lifecycle_status.value == "SUPERSEDED"


def test_validator_blocks_planned_to_actual_leakage():
    engine = PlanEngine(MemoryPlanRepository())
    revision = engine.build_nutrition_plan(_context(), _request())
    leaked = revision.items[0]
    leaked = PlanItem(
        plan_item_id=leaked.plan_item_id,
        scheduled_date=leaked.scheduled_date,
        schedule_slot=leaked.schedule_slot,
        item_type=leaked.item_type,
        canonical_refs=leaked.canonical_refs,
        content={**leaked.content, "consumed_at": "2026-09-01T07:00:00+07:00"},
    )
    invalid = replace(revision, items=(leaked, *revision.items[1:]))
    result = PlanValidator().validate(invalid)

    assert result.hard_violation_count == 1
    assert result.issues[0].code == "PLANNED_TO_ACTUAL_LEAKAGE"


@pytest.mark.asyncio
async def test_pending_action_saves_the_previewed_hash_and_not_a_regeneration():
    runtime = PlanRuntimeContext(
        "pending-user", "session-1",
        {
            "user_id": "pending-user", "age": 30, "equation_sex": "female",
            "height_cm": 165, "weight_kg": 58, "activity_level": "light",
            "health_goal": "maintain", "dietary_restrictions": [],
        },
        None,
    )
    preview = await build_nutrition_plan(
        period_start="2026-09-01", period_end="2026-09-01", timezone="Asia/Ho_Chi_Minh",
        _runtime_context=runtime,
    )
    store = PendingUserActionStore()
    action = store.create_plan_save_action("session-1", owner_user_id="pending-user", plan_payload=preview)

    assert action is not None
    assert action.target_identity["revision_id"] == preview["revision_id"]
    assert action.target_identity["revision_content_hash"] == preview["revision_content_hash"]
    store.put(action)
    resolution = store.claim_confirmation("session-1", "pending-user", "ok")
    assert resolution.status == "CLAIMED"
    saved = await save_plan(**action.tool_arguments, _runtime_context=runtime)
    identity = {
        "plan_id": saved["read_back_plan_id"],
        "revision_id": saved["read_back_revision_id"],
        "revision_content_hash": saved["read_back_revision_content_hash"],
    }
    assert identity == action.target_identity
    assert store.complete(action, persisted_reference_id=saved["read_back_revision_id"])


@pytest.mark.asyncio
async def test_public_plan_tool_receives_only_dispatcher_injected_authoritative_context():
    registry = ToolRegistry()
    register_server_tools(registry)
    gateway = type(
        "Gateway",
        (),
        {
            "user_id": "gateway-owner",
            "user_context": {
                "general_profile": {
                    "age": 30, "equation_sex": "male", "height_cm": 172,
                    "weight_kg": 68, "activity_level": "moderate", "health_goal": "maintain",
                },
                "nutrition_profile": {"food_allergies": ["PEANUT"]},
            },
        },
    )()
    result = await ToolDispatcher(registry, gateway=gateway).dispatch(
        "p1-dispatch", ToolCall("p1-call", "build_nutrition_plan", {
            "period_start": "2026-09-01", "period_end": "2026-09-01", "timezone": "Asia/Ho_Chi_Minh",
        }), 5_000,
    )

    assert result.ok
    assert result.data["status"] == "READY"
    assert result.data["plan"]["owner_user_id"] == "gateway-owner"
    assert all("PEANUT" not in item["content"]["allergen_ids"] for item in result.data["plan"]["items"])


def test_development_fixture_has_at_least_one_hundred_explicit_scenarios():
    scenarios = development_scenarios()
    assert len(scenarios) >= 100
    ids = {scenario.scenario_id for scenario in scenarios}
    assert len(ids) == len(scenarios)
    areas = {scenario.area for scenario in scenarios}
    assert {"nutrition_week", "workout_week", "combined_reference", "write_integrity", "actual_separation"} <= areas
