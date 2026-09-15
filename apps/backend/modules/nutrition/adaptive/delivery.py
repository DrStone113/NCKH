"""Typed projections for N3.2.1 development/shadow chat delivery.

This module converts a trusted *read* from the existing canonical dish tool
into a reference candidate.  It never writes a canonical catalog record and
is deliberately separate from external/staging candidate ingestion.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from .contracts import (
    CandidateSource,
    CandidateStatus,
    CanonicalIngredientMapping,
    MappingStatus,
    NutrientTotals,
    RawIngredient,
    RecipeCandidate,
    RecipeEvidenceBundle,
    TrustDomain,
)
from .engine import RecipeQualityGate
from .intelligence import RankedRecommendation
from .eligibility import CandidateEligibilityGate
from .contracts import ConstraintContext


class TrustedDeliveryError(ValueError):
    """A trusted tool result cannot be safely turned into a feedback card."""


def validate_candidate_for_exposure(
    ranked: RankedRecommendation, *, owner_user_id: str,
    gate: CandidateEligibilityGate, constraints: ConstraintContext,
) -> None:
    """Re-resolve identity before constructing a RecommendationEvent.

    Do not trust a RankedRecommendation merely because some upstream caller
    constructed one. This shares the pre-rank contract and nutrient authority.
    """
    gate.require(ranked.candidate, owner_user_id=owner_user_id, constraints=constraints)


def canonical_catalog_reference(suggestion: Mapping[str, Any]) -> RecipeCandidate:
    """Build a read-only candidate from ``suggest_dish``'s canonical result.

    Its identity is deterministic for the canonical dish id.  The candidate
    lives only in the owner-scoped recommendation event store; it is not a
    candidate ingestion or a catalog mutation path.
    """

    dish_id = str(suggestion.get("id") or "").strip()
    title = str(suggestion.get("name") or "").strip()
    components = suggestion.get("components")
    if not dish_id or not title or not isinstance(components, list) or not components:
        raise TrustedDeliveryError("CANONICAL_DISH_REFERENCE_INCOMPLETE")

    raw_ingredients: list[RawIngredient] = []
    mappings: list[CanonicalIngredientMapping] = []
    allergen_ids: set[str] = set()
    for component in components:
        if not isinstance(component, Mapping):
            raise TrustedDeliveryError("CANONICAL_DISH_COMPONENT_INVALID")
        name = str(component.get("name") or "").strip()
        food_id = str(component.get("food_id") or "").strip()
        grams = component.get("serving_grams")
        if not name or not food_id or not isinstance(grams, (int, float)) or grams <= 0:
            raise TrustedDeliveryError("CANONICAL_DISH_COMPONENT_INCOMPLETE")
        allergens = tuple(sorted(str(value) for value in component.get("allergen_ids") or () if str(value)))
        raw = RawIngredient(
            raw_text=name,
            amount=float(grams),
            unit="g",
            declared_state=str(component.get("food_state") or "UNKNOWN"),
            ingredient_name=name,
        )
        raw_ingredients.append(raw)
        mappings.append(
            CanonicalIngredientMapping(
                raw_ingredient=raw,
                canonical_food_id=food_id,
                canonical_food_name=name,
                grams=float(grams),
                status=MappingStatus.EXACT,
                confidence="CANONICAL",
                canonical_state=str(component.get("food_state") or "UNKNOWN"),
                allergen_ids=allergens,
            )
        )
        allergen_ids.update(allergens)

    try:
        nutrition = NutrientTotals(
            energy_kcal=float(suggestion["total_calories"]),
            protein_g=float(suggestion["total_protein"]),
            carbohydrate_g=float(suggestion["total_carbs"]),
            fat_g=float(suggestion["total_fat"]),
        ).rounded()
    except (KeyError, TypeError, ValueError) as exc:
        raise TrustedDeliveryError("CANONICAL_DISH_NUTRITION_INCOMPLETE") from exc

    source = CandidateSource(
        source_type="LOCAL_CANONICAL",
        source_id="VIETNAMESE_DISH_CATALOG",
        source_recipe_id=dish_id,
    )
    tags = {str(value) for value in (suggestion.get("dietary_tags") or {}).get("objective", ())}
    tags.update(f"contains_allergen:{value}" for value in allergen_ids)
    draft_evidence = RecipeEvidenceBundle(
        source=source,
        raw_source_text="",
        raw_ingredients=tuple(raw_ingredients),
        mappings=tuple(mappings),
        calculated_nutrition=nutrition,
        source_reported_nutrition=None,
        derived_allergen_ids=tuple(sorted(allergen_ids)),
        duplicate_candidates=(),
        validation_codes=(),
    )
    candidate = RecipeCandidate(
        candidate_id=str(uuid5(NAMESPACE_URL, f"n3-canonical-dish:{dish_id}")),
        trust_domain=TrustDomain.CANONICAL_PRODUCTION_RECIPE,
        title=title,
        aliases=(),
        source=source,
        raw_ingredients=tuple(raw_ingredients),
        mappings=tuple(mappings),
        canonical_nutrition=nutrition,
        source_reported_nutrition=None,
        allergen_ids=tuple(sorted(allergen_ids)),
        dietary_tags=tuple(sorted(tags)),
        evidence=draft_evidence.with_hash(),
        status=CandidateStatus.VALIDATED,
        lifecycle_history=("READ_ONLY_CANONICAL_REFERENCE", CandidateStatus.VALIDATED.value),
        validation_codes=(),
        recipe_origin="CANONICAL_CATALOG_REFERENCE",
        runtime_recipe_identity=f"canonical-dish:{dish_id}",
    )
    validation_codes = RecipeQualityGate().evaluate(candidate)
    if not RecipeQualityGate.hard_pass(validation_codes):
        raise TrustedDeliveryError("CANONICAL_DISH_REFERENCE_FAILED_HARD_GATE")
    evidence = replace(candidate.evidence, validation_codes=validation_codes).with_hash()
    return replace(candidate, evidence=evidence, validation_codes=validation_codes)


def structured_chat_payload(
    ranked: RankedRecommendation,
    recommendation_event_id: str,
    *,
    meal_type: str | None,
) -> dict[str, Any]:
    """Expose only typed, user-facing delivery fields to the chat renderer."""

    candidate = ranked.candidate
    nutrition = candidate.canonical_nutrition
    if nutrition is None:
        raise TrustedDeliveryError("DELIVERY_REQUIRES_CANONICAL_NUTRITION")
    serving_grams = sum(
        mapping.grams or 0.0
        for mapping in candidate.mappings
        if isinstance(mapping.grams, (int, float)) and mapping.grams > 0
    ) or 100.0
    per_100g = 100.0 / serving_grams
    ingredients = [
        mapping.canonical_food_name
        or mapping.raw_ingredient.ingredient_name
        or mapping.raw_ingredient.raw_text
        for mapping in candidate.mappings
    ]
    return {
        "type": "structured",
        "text": "Đây là gợi ý dinh dưỡng ở chế độ thử nghiệm.",
        "meal_name": candidate.title,
        "actions": [
            {
                "kind": "food",
                "wger_id": 0,
                "name": candidate.title,
                "details": {
                    "dish_name": candidate.title,
                    "meal_type": meal_type or "lunch",
                    "serving_grams": round(serving_grams, 2),
                    "calories": round(nutrition.energy_kcal * per_100g, 4),
                    "protein": round(nutrition.protein_g * per_100g, 4),
                    "carbs": round(nutrition.carbohydrate_g * per_100g, 4),
                    "fat": round(nutrition.fat_g * per_100g, 4),
                    "display_ingredients": ingredients,
                    "recommendation_candidate_id": candidate.candidate_id,
                    "recommendation_event_id": recommendation_event_id,
                    "recommendation_policy_version": ranked.policy_version,
                    "recommendation_reason_codes": list(ranked.public_reason_codes()),
                    "recommendation_source_type": ranked.source_type.value,
                    "feedback_eligible": True,
                    "delivery_mode": "DEVELOPMENT_SHADOW",
                },
            }
        ],
    }


__all__ = ["TrustedDeliveryError", "canonical_catalog_reference", "structured_chat_payload"]
