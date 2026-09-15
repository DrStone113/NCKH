"""N3.3R source/reference authority shared by ranking and exposure creation.

No catalog writes or alternative nutrient formula. Noncanonical identities are
resolved from an owner-scoped repository; canonical identities from the product
catalog. Development callers may inject an explicit isolated authority.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Callable, Iterable, Mapping
from uuid import UUID, NAMESPACE_URL, uuid5

from .contracts import CandidateStatus, ConstraintContext, MappingStatus, RecipeCandidate, TrustDomain
from .engine import (
    AdaptiveRecipeError, CanonicalIngredientMapper, RecipeQualityGate,
    calculate_canonical_nutrition, load_adaptive_source_registry, _derived_dietary_tags,
)


class ExclusionReason(str, Enum):
    INVALID_CANONICAL_REFERENCE = "INVALID_CANONICAL_REFERENCE"
    INVALID_SOURCE_REFERENCE = "INVALID_SOURCE_REFERENCE"
    UNMAPPED_REQUIRED_INGREDIENT = "UNMAPPED_REQUIRED_INGREDIENT"
    INELIGIBLE_SOURCE_STATE = "INELIGIBLE_SOURCE_STATE"
    ALLERGY_VIOLATION = "ALLERGY_VIOLATION"
    RESTRICTION_VIOLATION = "RESTRICTION_VIOLATION"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"


@dataclass(frozen=True)
class CandidateEligibility:
    candidate_id: str
    eligible: bool
    reasons: tuple[ExclusionReason, ...] = ()


class CandidateEligibilityGate:
    version = "N3_3R_SOURCE_ELIGIBILITY_V1"

    def __init__(
        self, *, foods: Iterable[Mapping[str, Any]] | None = None,
        dishes: Iterable[Mapping[str, Any]] | None = None,
        candidate_lookup: Callable[[str, str], RecipeCandidate | None] | None = None,
    ) -> None:
        self._food_input = tuple(foods) if foods is not None else None
        self._dish_input = tuple(dishes) if dishes is not None else None
        self._foods: dict[str, Mapping[str, Any]] | None = None
        self._dishes: dict[str, Mapping[str, Any]] | None = None
        self._mapper: CanonicalIngredientMapper | None = None
        self._local_mapper: CanonicalIngredientMapper | None = None
        self._lookup = candidate_lookup

    def _load(self) -> None:
        if self._foods is not None:
            return
        from modules.nutrition.canonical_foods import load_canonical_food_catalog
        from modules.nutrition.catalog import load_dish_catalog
        foods = self._food_input if self._food_input is not None else load_canonical_food_catalog()
        dishes = self._dish_input if self._dish_input is not None else load_dish_catalog()
        self._foods = {str(row['food_id']): row for row in foods}
        self._dishes = {str(row['id']): row for row in dishes}
        self._mapper = CanonicalIngredientMapper(foods)

    def evaluate(self, candidate: RecipeCandidate, *, owner_user_id: str,
                 constraints: ConstraintContext = ConstraintContext()) -> CandidateEligibility:
        self._load()
        reasons: list[ExclusionReason] = []
        def reject(reason: ExclusionReason) -> CandidateEligibility:
            return CandidateEligibility(candidate.candidate_id, False, tuple(dict.fromkeys(reasons + [reason])))
        try:
            UUID(candidate.candidate_id)
        except (ValueError, TypeError, AttributeError):
            return reject(ExclusionReason.INVALID_SOURCE_REFERENCE)
        if candidate.status not in {CandidateStatus.VALIDATED, CandidateStatus.STAGING, CandidateStatus.SHADOW_ELIGIBLE}:
            return reject(ExclusionReason.INELIGIBLE_SOURCE_STATE)
        if not candidate.mappings or len(candidate.mappings) != len(candidate.raw_ingredients):
            return reject(ExclusionReason.UNMAPPED_REQUIRED_INGREDIENT)
        for mapping in candidate.mappings:
            if mapping.status not in {MappingStatus.EXACT, MappingStatus.HIGH_CONFIDENCE}:
                return reject(ExclusionReason.UNMAPPED_REQUIRED_INGREDIENT)
            food = self._foods.get(mapping.canonical_food_id)
            if food is None:
                return reject(ExclusionReason.INVALID_CANONICAL_REFERENCE)
            if (mapping.canonical_food_name != food.get('name') or
                mapping.canonical_state != (food.get('canonical_description') or {}).get('state', 'UNKNOWN') or
                set(mapping.allergen_ids) != set(food.get('allergen_ids') or ())):
                return reject(ExclusionReason.INVALID_CANONICAL_REFERENCE)
            if mapping.grams is None or not math.isfinite(mapping.grams) or mapping.grams <= 0:
                return reject(ExclusionReason.UNMAPPED_REQUIRED_INGREDIENT)

        source = candidate.source
        if candidate.trust_domain == TrustDomain.CANONICAL_PRODUCTION_RECIPE:
            record = self._dishes.get(source.source_recipe_id or '')
            if (source.source_id != 'VIETNAMESE_DISH_CATALOG' or source.source_type != 'LOCAL_CANONICAL' or
                record is None or candidate.status != CandidateStatus.VALIDATED or candidate.owner_user_id or
                candidate.candidate_id != str(uuid5(NAMESPACE_URL, f'n3-canonical-dish:{source.source_recipe_id}')) or
                candidate.title != record.get('name') or
                Counter(item.canonical_food_id for item in candidate.mappings) !=
                Counter(str(item.get('food_id')) for item in record.get('ingredients', ()))):
                return reject(ExclusionReason.INVALID_CANONICAL_REFERENCE)
        elif candidate.trust_domain in {TrustDomain.PERSONAL_RECIPE, TrustDomain.STAGING_RECIPE, TrustDomain.RUNTIME_EXTERNAL_CANDIDATE}:
            policy = load_adaptive_source_registry().get(source.source_id)
            if not policy or source.source_type != policy.get('source_type'):
                return reject(ExclusionReason.INVALID_SOURCE_REFERENCE)
            if candidate.trust_domain == TrustDomain.PERSONAL_RECIPE:
                if (not owner_user_id or candidate.owner_user_id != owner_user_id or
                    policy.get('candidate_storage') != 'PERSONAL_ONLY'):
                    return reject(ExclusionReason.INVALID_SOURCE_REFERENCE)
            elif (candidate.owner_user_id or not policy.get('staging_allowed') or
                  policy.get('access_status') not in {'APPROVED', 'LIMITED'}):
                return reject(ExclusionReason.INELIGIBLE_SOURCE_STATE)
            if candidate.trust_domain == TrustDomain.STAGING_RECIPE and candidate.status != CandidateStatus.SHADOW_ELIGIBLE:
                return reject(ExclusionReason.INELIGIBLE_SOURCE_STATE)
            if not {'EXTRACTED', 'MAPPED', 'CALCULATED', 'VALIDATED'}.issubset(candidate.lifecycle_history):
                return reject(ExclusionReason.INELIGIBLE_SOURCE_STATE)
            try:
                registered = self._lookup(candidate.candidate_id, owner_user_id) if self._lookup else None
            except AdaptiveRecipeError:
                registered = None
            if registered is None or registered != candidate:
                return reject(ExclusionReason.INVALID_SOURCE_REFERENCE)
        else:
            return reject(ExclusionReason.INELIGIBLE_SOURCE_STATE)

        evidence = candidate.evidence
        if (evidence.with_hash().evidence_hash != evidence.evidence_hash or
            evidence.source != source or evidence.mappings != candidate.mappings or
            evidence.raw_ingredients != candidate.raw_ingredients or
            evidence.calculated_nutrition != candidate.canonical_nutrition):
            return reject(ExclusionReason.INVALID_SOURCE_REFERENCE)
        # The mapper lowercases objective tags, while catalog projections keep
        # canonical allergen codes uppercase. Compare tag semantics using the
        # same case normalization as the dietary gate; allergen IDs stay exact.
        required_tags = {tag.casefold() for tag in _derived_dietary_tags(candidate.mappings, self._mapper)}
        candidate_tags = {tag.casefold() for tag in candidate.dietary_tags}
        if (set(candidate.allergen_ids) != {a for m in candidate.mappings for a in m.allergen_ids} or
            not required_tags.issubset(candidate_tags)):
            return reject(ExclusionReason.INVALID_CANONICAL_REFERENCE)
        nutrition = candidate.canonical_nutrition
        if nutrition is None:
            return reject(ExclusionReason.SAFETY_VIOLATION)
        mapper = self._mapper
        if candidate.trust_domain == TrustDomain.CANONICAL_PRODUCTION_RECIPE:
            # Match the existing trusted tool's numeric conversion exactly;
            # do not change raw catalog values or define a second formula.
            if self._local_mapper is None:
                from services.agent.tools.dish import _safe_float
                self._local_mapper = CanonicalIngredientMapper(tuple(
                    {**food, **{key: _safe_float(food.get(key)) for key in ('energy_kcal', 'protein', 'carbohydrates', 'fat')}}
                    for food in self._foods.values()
                ))
            mapper = self._local_mapper
        try:
            calculated = calculate_canonical_nutrition(candidate.mappings, mapper)
        except AdaptiveRecipeError:
            return reject(ExclusionReason.SAFETY_VIOLATION)
        for name in ('energy_kcal', 'protein_g', 'carbohydrate_g', 'fat_g'):
            value = getattr(nutrition, name)
            # Tool projections round each component to .01 before summing.
            if not math.isfinite(value) or not math.isclose(value, getattr(calculated, name), rel_tol=0, abs_tol=.01 * len(candidate.mappings) + 1e-8):
                return reject(ExclusionReason.SAFETY_VIOLATION)
        codes = RecipeQualityGate().evaluate(candidate, constraints)
        if 'ALLERGEN_VIOLATION' in codes:
            reasons.append(ExclusionReason.ALLERGY_VIOLATION)
        if any(code.startswith('DIETARY_RESTRICTION_') for code in codes):
            reasons.append(ExclusionReason.RESTRICTION_VIOLATION)
        if not RecipeQualityGate.hard_pass(codes) and not reasons:
            reasons.append(ExclusionReason.SAFETY_VIOLATION)
        return CandidateEligibility(candidate.candidate_id, not reasons, tuple(reasons))

    def require(self, candidate: RecipeCandidate, *, owner_user_id: str,
                constraints: ConstraintContext = ConstraintContext()) -> None:
        result = self.evaluate(candidate, owner_user_id=owner_user_id, constraints=constraints)
        if not result.eligible:
            raise AdaptiveRecipeError(result.reasons[0].value)

    def metadata(self, candidate: RecipeCandidate) -> Mapping[str, Any]:
        self._load()
        record = self._dishes.get(candidate.source.source_recipe_id or '', {}) if candidate.trust_domain == TrustDomain.CANONICAL_PRODUCTION_RECIPE else {}
        return record

    def ingredient_names(self, candidate: RecipeCandidate) -> tuple[str, ...]:
        self._load()
        return tuple(str(self._foods[m.canonical_food_id].get('name') or '') for m in candidate.mappings)
