from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from modules.nutrition.adaptive.contracts import (
    CandidateSource,
    RawIngredient,
    TrustDomain,
)
from modules.nutrition.adaptive.engine import (
    CanonicalIngredientMapper,
    build_recipe_candidate,
)
from modules.nutrition.adaptive.external import (
    ExternalAcquisitionResult,
    ExternalDiscoveryError,
    ExternalRecipeDetails,
)
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from services.agent.llm_client import ToolCall
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry
from services.agent.tools.recipe_web import (
    build_search_recipe_web_descriptor,
    build_search_recipe_web_tool,
)


def _candidate(*, verified: bool):
    raw_ingredient = RawIngredient(
        raw_text="120 g Tomato",
        amount=120.0,
        unit="g",
        ingredient_name="Tomato",
    )
    nutrition = (
        SimpleNamespace(
            energy_kcal=420.0,
            protein_g=24.0,
            carbohydrate_g=48.0,
            fat_g=14.0,
        )
        if verified
        else None
    )
    return SimpleNamespace(
        candidate_id="external-candidate-1",
        title="Pizza Margherita",
        source=SimpleNamespace(
            source_id="THEMEALDB_OFFICIAL_API",
            source_url="https://www.themealdb.com/api/json/v1/1/lookup.php?i=1",
        ),
        mappings=(
            SimpleNamespace(
                raw_ingredient=raw_ingredient,
                canonical_food_id="canonical-tomato",
                canonical_food_name="Tomato",
                grams=120.0,
                canonical_state="RAW",
                status=SimpleNamespace(value="EXACT" if verified else "UNMAPPED"),
                reason_code=None if verified else "CANONICAL_INGREDIENT_UNMAPPED",
            ),
        ),
        raw_ingredients=(raw_ingredient,),
        canonical_nutrition=nutrition,
        evidence=SimpleNamespace(
            calculation_version="canonical-ingredient-sum-v1"
        ),
        validation_codes=("MAPPING_COVERAGE_INCOMPLETE",) if not verified else (),
    )


class _FakeAcquisition:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def acquire_and_stage(self, request, search_query, constraints):
        self.calls.append((request, search_query, constraints))
        return self.result


class _UnavailableAcquisition:
    async def acquire_and_stage(self, request, search_query, constraints):
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_HTTP_UNAVAILABLE")


def _result(
    *,
    candidates=(),
    staged=(),
    adaptations=(),
    fallback=None,
    recipe_details=None,
):
    return ExternalAcquisitionResult(
        trigger_reason="UNKNOWN_REQUESTED_DISH",
        candidates=tuple(candidates),
        staged_candidates=tuple(staged),
        adaptations=tuple(adaptations),
        public_trace=("Đang tìm thêm lựa chọn phù hợp",),
        debug_trace={},
        fallback_reason=fallback,
        recipe_details=recipe_details or {},
    )


@pytest.mark.asyncio
async def test_verified_web_recipe_uses_only_canonical_recalculated_nutrition():
    candidate = _candidate(verified=True)
    details = ExternalRecipeDetails(
        raw_ingredients=candidate.raw_ingredients,
        instructions=("Prepare the tomato.", "Bake the pizza."),
        recipe_yield="2 servings",
        cuisine="Italian",
        category="Main",
    )
    service = _FakeAcquisition(
        _result(
            candidates=(candidate,),
            staged=(candidate,),
            recipe_details={candidate.candidate_id: details},
        )
    )
    tool = build_search_recipe_web_tool(
        AdaptiveRecipeRepository(), acquisition_service=service
    )

    payload = await tool(
        query="  Pizza   Margherita ",
        meal_type="dinner",
        target_kcal=420,
        dietary_restrictions=("vegetarian",),
        limit=2,
    )

    assert payload["status"] == "VERIFIED_SHADOW_RESULTS"
    assert payload["canonical_write_authorized"] is False
    assert payload["meal_logging_authorized"] is False
    assert payload["recipes"][0]["verification_status"] == "VERIFIED_SHADOW"
    assert payload["recipes"][0]["nutrition_method"] == (
        "RECALCULATED_FROM_CANONICAL_INGREDIENTS"
    )
    assert payload["recipes"][0]["instructions"] == [
        "Prepare the tomato.",
        "Bake the pizza.",
    ]
    assert payload["recipes"][0]["ingredients"][0]["normalized_grams"] == 120
    assert payload["recipes"][0]["calculated_nutrition"]["total_calories"] == 420
    assert payload["recipes"][0]["composition_table"] == "VIETNAM_FCT_2007"
    request, search_query, constraints = service.calls[0]
    assert request.query == "Pizza Margherita"
    assert search_query.query == "Pizza Margherita"
    assert search_query.meal_type is None
    assert search_query.limit == 2
    assert constraints.dietary_exclusions == frozenset({"vegetarian"})


@pytest.mark.asyncio
async def test_unverified_web_recipe_is_reference_only_without_nutrition():
    candidate = _candidate(verified=False)
    details = ExternalRecipeDetails(
        raw_ingredients=candidate.raw_ingredients,
        instructions=("Prepare the tomato.",),
    )
    service = _FakeAcquisition(
        _result(
            candidates=(candidate,),
            fallback="NO_VERIFIED_EXTERNAL_RECIPE",
            recipe_details={candidate.candidate_id: details},
        )
    )
    tool = build_search_recipe_web_tool(
        AdaptiveRecipeRepository(), acquisition_service=service
    )

    payload = await tool(query="pizza")

    assert payload["status"] == "REFERENCE_ONLY_RESULTS"
    recipe = payload["recipes"][0]
    assert recipe["verification_status"] == "REFERENCE_ONLY"
    assert "calculated_nutrition" not in recipe
    assert recipe["nutrition_status"] == "UNAVAILABLE_UNRESOLVED_INGREDIENTS"
    assert recipe["ingredients"][0]["source_text"] == "120 g Tomato"
    assert recipe["ingredients"][0]["mapping_status"] == "UNMAPPED"
    assert recipe["instructions"] == ["Prepare the tomato."]
    assert recipe["source_url"].startswith("https://www.themealdb.com/")
    assert payload["meal_logging_authorized"] is False


@pytest.mark.asyncio
async def test_beefsteak_retries_with_bounded_steak_alias():
    candidate = _candidate(verified=False)
    details = ExternalRecipeDetails(
        raw_ingredients=candidate.raw_ingredients,
        instructions=("Cook the steak.",),
    )

    class AliasAcquisition:
        def __init__(self):
            self.calls = []

        async def acquire_and_stage(self, request, search_query, constraints):
            self.calls.append(search_query.query)
            if search_query.query == "beefsteak":
                return _result(candidates=(), fallback="NO_EXTERNAL_RECIPE_FOUND")
            return _result(
                candidates=(candidate,),
                fallback="NO_VERIFIED_EXTERNAL_RECIPE",
                recipe_details={candidate.candidate_id: details},
            )

    service = AliasAcquisition()
    tool = build_search_recipe_web_tool(
        AdaptiveRecipeRepository(), acquisition_service=service
    )

    payload = await tool(query="beefsteak", limit=1)

    assert service.calls == ["beefsteak", "steak"]
    assert payload["status"] == "REFERENCE_ONLY_RESULTS"
    assert payload["requested_query"] == "beefsteak"
    assert payload["matched_search_query"] == "steak"
    assert payload["recipes"][0]["instructions"] == ["Cook the steak."]


@pytest.mark.asyncio
async def test_external_search_failure_is_contained_and_never_invents_result():
    tool = build_search_recipe_web_tool(
        AdaptiveRecipeRepository(),
        acquisition_service=_UnavailableAcquisition(),
    )

    payload = await tool(query="pizza")

    assert payload == {
        "status": "EXTERNAL_RECIPE_SEARCH_UNAVAILABLE",
        "recipes": [],
        "canonical_write_authorized": False,
        "meal_logging_authorized": False,
    }


def test_web_recipe_descriptor_is_bounded_and_registerable():
    descriptor = build_search_recipe_web_descriptor(
        AdaptiveRecipeRepository(),
        acquisition_service=_UnavailableAcquisition(),
    )
    registry = ToolRegistry()
    registry.register(descriptor)

    assert registry.validate("search_recipe_web", {"query": "pizza"}) == (
        True,
        None,
    )
    assert registry.validate(
        "search_recipe_web", {"query": "pizza", "limit": 4}
    ) == (False, "INVALID_ARGS")
    assert descriptor.timeout_ms == 30_000


@pytest.mark.asyncio
async def test_web_recipe_tool_dispatches_through_agent_registry():
    descriptor = build_search_recipe_web_descriptor(
        AdaptiveRecipeRepository(),
        acquisition_service=_UnavailableAcquisition(),
    )
    registry = ToolRegistry()
    registry.register(descriptor)

    result = await ToolDispatcher(registry).dispatch(
        "session-1",
        ToolCall(
            id="web-recipe-1",
            name="search_recipe_web",
            arguments={"query": "pizza"},
        ),
        timeout_ms=1_000,
    )

    assert result.ok is True
    assert result.data["status"] == "EXTERNAL_RECIPE_SEARCH_UNAVAILABLE"


def test_unresolved_external_quantity_is_stable_during_duplicate_check():
    candidate = build_recipe_candidate(
        trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        title="Recipe with salt to taste",
        source=CandidateSource(
            source_type="API",
            source_id="THEMEALDB_OFFICIAL_API",
            source_url="https://www.themealdb.com/api/json/v1/1/lookup.php?i=1",
        ),
        raw_ingredients=(
            RawIngredient(
                raw_text="Salt to taste",
                amount=None,
                unit="unknown",
                ingredient_name="Salt",
                quantity_uncertain=True,
            ),
        ),
        mapper=CanonicalIngredientMapper(()),
    )
    repository = AdaptiveRecipeRepository()

    repository.save_candidate(candidate)
    saved_copy = repository.save_candidate(
        replace(candidate, candidate_id="candidate-copy")
    )

    assert saved_copy.candidate_id == "candidate-copy"
