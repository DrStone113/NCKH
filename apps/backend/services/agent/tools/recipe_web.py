"""Policy-gated recipe lookup used only after the local catalog misses.

The tool never promotes external content into the canonical dish catalog. A
recipe receives nutrient fields only after every ingredient and quantity has
passed deterministic canonical mapping and the N3 quality gate. Otherwise the
tool returns source attribution metadata only.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterable

from modules.nutrition.adaptive.contracts import ConstraintContext, RecipeCandidate
from modules.nutrition.adaptive.discovery import (
    DiscoveryReason,
    RecipeDiscoveryRequest,
)
from modules.nutrition.adaptive.engine import (
    AdaptiveRecipeError,
    CanonicalIngredientMapper,
    RecipePortionFitter,
    load_adaptive_source_registry,
)
from modules.nutrition.adaptive.external import (
    ExternalCandidateFactory,
    ExternalRecipeAcquisitionService,
    ExternalRecipeDetails,
    FetchStrategy,
    HttpRecipeFetcher,
    RecipeSearchQuery,
    StructuredRecipeExtractionService,
    TheMealDbSearchProvider,
)
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from services.agent.tool_registry import ToolDescriptor


_VALID_MEAL_TYPES = ("breakfast", "dinner", "lunch", "snack")
_VALID_RESTRICTIONS = (
    "high_protein",
    "low_carb",
    "no_beef",
    "no_crustacean",
    "no_egg",
    "no_fish",
    "no_milk",
    "no_mollusc",
    "no_peanut",
    "no_pork",
    "no_seafood",
    "no_sesame",
    "no_soy",
    "no_tree_nut",
    "no_wheat_gluten",
    "vegan",
    "vegetarian",
)

SEARCH_RECIPE_WEB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 2,
            "maxLength": 120,
            "description": (
                "Tên món cần tìm sau khi suggest_dish báo NO_DISH_FOUND. "
                "Chỉ truyền tên/từ khóa món ăn, không truyền dữ liệu cá nhân. "
                "Với món quốc tế, ưu tiên tên tiếng Anh."
            ),
        },
        "meal_type": {
            "type": "string",
            "enum": list(_VALID_MEAL_TYPES),
        },
        "target_kcal": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": 2500,
        },
        "dietary_restrictions": {
            "type": "array",
            "items": {"type": "string", "enum": list(_VALID_RESTRICTIONS)},
            "uniqueItems": True,
            "default": [],
        },
        "confirmed_ingredient_grams": {
            "type": "object",
            "additionalProperties": {
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 5000,
            },
            "default": {},
            "description": (
                "Khối lượng gram do người dùng xác nhận, khóa phải khớp "
                "source_text của nguyên liệu đã trả về. Không được tự đoán."
            ),
        },
        "purpose": {
            "type": "string",
            "enum": ["catalog_miss", "instructions_only"],
            "default": "catalog_miss",
            "description": (
                "catalog_miss khi món không có trong catalog; instructions_only "
                "khi món local có dinh dưỡng nhưng thiếu cách làm."
            ),
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 3,
            "default": 3,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


_DESCRIPTION = (
    "Tìm công thức từ nguồn API đã được phê duyệt sau khi catalog nội bộ "
    "không có món, hoặc khi món local có dinh dưỡng nhưng thiếu cách làm và "
    "người dùng hỏi rõ về cách nấu. Kết quả VERIFIED_SHADOW có "
    "dinh dưỡng được tính lại từ nguyên liệu canonical. Mọi kết quả có thể trả "
    "nguyên liệu và cách làm từ nguồn kèm attribution; REFERENCE_ONLY phải giữ "
    "trạng thái từng nguyên liệu và không được suy diễn calo, dùng để ghi bữa "
    "ăn, hoặc coi là món đã xác minh. Không gửi thông tin sức khỏe hay dữ liệu "
    "cá nhân trong query."
)


def _search_query_variants(query: str) -> tuple[str, ...]:
    """Return bounded, explicit aliases for common cross-language dish names."""

    folded = "".join(
        character
        for character in unicodedata.normalize("NFD", query.casefold())
        if unicodedata.category(character) != "Mn"
    )
    folded = " ".join(folded.replace("đ", "d").split())
    aliases = {
        "beefsteak": "steak",
        "beef steak": "steak",
        "bit tet": "steak",
        "bo bit tet": "steak",
    }
    alias = aliases.get(folded)
    return (query, alias) if alias and alias.casefold() != query.casefold() else (query,)


def _default_acquisition_service(
    repository: AdaptiveRecipeRepository,
) -> ExternalRecipeAcquisitionService:
    policies = load_adaptive_source_registry()
    mapper = CanonicalIngredientMapper()
    return ExternalRecipeAcquisitionService(
        search_providers=(
            TheMealDbSearchProvider(source_policies=policies),
        ),
        fetchers={
            FetchStrategy.API_FETCH: HttpRecipeFetcher(
                FetchStrategy.API_FETCH,
                source_policies=policies,
            )
        },
        extractor=StructuredRecipeExtractionService(),
        candidate_factory=ExternalCandidateFactory(
            mapper,
            source_policies=policies,
        ),
        repository=repository,
        source_policies=policies,
        portion_fitter=RecipePortionFitter(mapper),
    )


def _details_for(
    candidate: RecipeCandidate,
    details: ExternalRecipeDetails | None,
) -> ExternalRecipeDetails:
    return details or ExternalRecipeDetails(
        raw_ingredients=candidate.raw_ingredients,
        instructions=(),
    )


def _ingredient_payload(candidate: RecipeCandidate) -> list[dict[str, Any]]:
    return [
        {
            "source_text": mapping.raw_ingredient.raw_text,
            "source_amount": mapping.raw_ingredient.amount,
            "source_unit": mapping.raw_ingredient.unit,
            "canonical_food_id": mapping.canonical_food_id,
            "canonical_food_name": mapping.canonical_food_name,
            "normalized_grams": (
                round(float(mapping.grams), 2)
                if mapping.grams is not None
                else None
            ),
            "food_state": mapping.canonical_state,
            "mapping_status": mapping.status.value,
            "reason_code": mapping.reason_code,
        }
        for mapping in candidate.mappings
    ]


def _verified_recipe(
    candidate: RecipeCandidate,
    details: ExternalRecipeDetails | None,
) -> dict[str, Any]:
    nutrition = candidate.canonical_nutrition
    if nutrition is None:
        raise ValueError("EXTERNAL_RECIPE_CANONICAL_NUTRITION_REQUIRED")
    recipe_details = _details_for(candidate, details)
    return {
        "candidate_id": candidate.candidate_id,
        "title": candidate.title,
        "verification_status": "VERIFIED_SHADOW",
        "source": candidate.source.source_id,
        "source_url": candidate.source.source_url,
        "attribution_required": True,
        "ingredients": _ingredient_payload(candidate),
        "instructions": list(recipe_details.instructions),
        "recipe_yield": recipe_details.recipe_yield,
        "cuisine": recipe_details.cuisine,
        "category": recipe_details.category,
        "calculated_nutrition": {
            "total_calories": nutrition.energy_kcal,
            "total_protein": nutrition.protein_g,
            "total_carbs": nutrition.carbohydrate_g,
            "total_fat": nutrition.fat_g,
        },
        "nutrition_method": "RECALCULATED_FROM_CANONICAL_INGREDIENTS",
        "composition_table": "VIETNAM_FCT_2007",
        "nutrition_basis": "PER_100G_EDIBLE_PORTION",
        "calculation_version": candidate.evidence.calculation_version,
        "nutrition_status": "VERIFIED",
        "delivery_mode": "DEVELOPMENT_SHADOW",
    }


def _reference_recipe(
    candidate: RecipeCandidate,
    details: ExternalRecipeDetails | None,
) -> dict[str, Any]:
    recipe_details = _details_for(candidate, details)
    return {
        "title": candidate.title,
        "verification_status": "REFERENCE_ONLY",
        "source": candidate.source.source_id,
        "source_url": candidate.source.source_url,
        "attribution_required": True,
        "ingredients": _ingredient_payload(candidate),
        "instructions": list(recipe_details.instructions),
        "recipe_yield": recipe_details.recipe_yield,
        "cuisine": recipe_details.cuisine,
        "category": recipe_details.category,
        "nutrition_status": "UNAVAILABLE_UNRESOLVED_INGREDIENTS",
        "reason_codes": list(candidate.validation_codes),
    }


def build_search_recipe_web_tool(
    repository: AdaptiveRecipeRepository,
    *,
    acquisition_service: Any | None = None,
):
    service = acquisition_service or _default_acquisition_service(repository)

    async def search_recipe_web(
        query: str,
        meal_type: str | None = None,
        target_kcal: float | None = None,
        dietary_restrictions: Iterable[str] = (),
        confirmed_ingredient_grams: dict[str, float] | None = None,
        purpose: str = "catalog_miss",
        limit: int = 3,
    ) -> dict[str, Any]:
        clean_query = " ".join(query.split())
        constraints = tuple(dict.fromkeys(dietary_restrictions))
        request = RecipeDiscoveryRequest(
            query=clean_query,
            reason=(
                DiscoveryReason.INSUFFICIENT_LOCAL_CANDIDATES
                if purpose == "instructions_only"
                else DiscoveryReason.UNKNOWN_REQUESTED_DISH
            ),
            local_viable_count=1 if purpose == "instructions_only" else 0,
            diversity_score=0.0,
            meal_type=meal_type,
            dietary_constraints=constraints,
        )
        result = None
        matched_search_query = clean_query
        try:
            for search_term in _search_query_variants(clean_query):
                matched_search_query = search_term
                result = await service.acquire_and_stage(
                    request,
                    # TheMealDB name search accepts a dish term, not a sentence
                    # containing the meal slot or dietary constraints.
                    RecipeSearchQuery(
                        query=search_term,
                        limit=limit,
                        confirmed_ingredient_grams=confirmed_ingredient_grams or {},
                    ),
                    ConstraintContext(
                        dietary_exclusions=frozenset(constraints),
                        target_kcal=target_kcal,
                    ),
                )
                if result.candidates or result.staged_candidates or result.adaptations:
                    break
        except (AdaptiveRecipeError, OSError, TimeoutError):
            return {
                "status": "EXTERNAL_RECIPE_SEARCH_UNAVAILABLE",
                "recipes": [],
                "canonical_write_authorized": False,
                "meal_logging_authorized": False,
            }

        if result is None:
            raise RuntimeError("EXTERNAL_RECIPE_SEARCH_RESULT_REQUIRED")

        verified_candidates = (
            [
                (
                    revision.candidate,
                    result.recipe_details.get(revision.base_candidate_id),
                )
                for revision in result.adaptations
            ]
            or [
                (candidate, result.recipe_details.get(candidate.candidate_id))
                for candidate in result.staged_candidates
            ]
        )
        if verified_candidates:
            recipes = [
                _verified_recipe(candidate, details)
                for candidate, details in verified_candidates[:limit]
            ]
            status = "VERIFIED_SHADOW_RESULTS"
        else:
            safe_reference_candidates = [
                candidate
                for candidate in result.candidates
                if "UNTRUSTED_CONTENT_QUARANTINED"
                not in candidate.validation_codes
            ]
            recipes = [
                _reference_recipe(
                    candidate,
                    result.recipe_details.get(candidate.candidate_id),
                )
                for candidate in safe_reference_candidates[:limit]
            ]
            status = "REFERENCE_ONLY_RESULTS" if recipes else "NO_EXTERNAL_RECIPE_FOUND"

        return {
            "status": status,
            "recipes": recipes,
            "requested_query": clean_query,
            "purpose": purpose,
            "matched_search_query": matched_search_query,
            "fallback_reason": result.fallback_reason,
            "public_trace": list(result.public_trace),
            "canonical_write_authorized": False,
            "meal_logging_authorized": False,
        }

    return search_recipe_web


def build_search_recipe_web_descriptor(
    repository: AdaptiveRecipeRepository,
    *,
    acquisition_service: Any | None = None,
) -> ToolDescriptor:
    return ToolDescriptor(
        name="search_recipe_web",
        description=_DESCRIPTION,
        parameters_schema=SEARCH_RECIPE_WEB_SCHEMA,
        side="server",
        fn=build_search_recipe_web_tool(
            repository,
            acquisition_service=acquisition_service,
        ),
        idempotent=True,
        timeout_ms=30_000,
    )


__all__ = [
    "SEARCH_RECIPE_WEB_SCHEMA",
    "build_search_recipe_web_descriptor",
    "build_search_recipe_web_tool",
]
