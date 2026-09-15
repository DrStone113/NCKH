"""Deterministic N3 candidate construction, validation, and portion fitting."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from modules.nutrition.canonical_foods import energy_consistency, load_canonical_food_catalog

from .contracts import (
    CandidateSource,
    CandidateStatus,
    CanonicalIngredientMapping,
    ConstraintContext,
    IngredientScaleClass,
    MappingStatus,
    NutrientTotals,
    PortionFitResult,
    RawIngredient,
    RecipeCandidate,
    RecipeEvidenceBundle,
    TrustDomain,
)


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
SOURCE_REGISTRY_FILE = DATA_DIR / "adaptive_recipe_source_registry_v1.json"
CALCULATION_VERSION = "canonical-ingredient-sum-v1"
SOURCE_NUTRITION_CONFLICT_RELATIVE_DELTA = 0.20
PORTION_TARGET_TOLERANCE = 0.10
PROHIBITED_UNTRUSTED_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "ignore prior instructions",
    "system message",
    "system prompt",
    "system instructions",
    "developer message",
    "developer instructions",
    "tool_call",
    "tool-call",
    "call_tool",
    "<script",
    "<iframe",
    "javascript:",
    "onerror=",
    "onclick=",
)


class AdaptiveRecipeError(ValueError):
    """Raised for typed N3 contract violations."""


def _normalise_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    ascii_text = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AdaptiveRecipeError("INVALID_NUMERIC_VALUE") from exc
    if not math.isfinite(result):
        raise AdaptiveRecipeError("NON_FINITE_NUMERIC_VALUE")
    return result


def _canonical_food_index(
    foods: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    catalog = list(foods) if foods is not None else load_canonical_food_catalog()
    index: dict[str, list[Mapping[str, Any]]] = {}
    for food in catalog:
        name = str(food.get("name") or "").strip()
        food_id = str(food.get("food_id") or "").strip()
        if not name or not food_id:
            continue
        for candidate in (name, food.get("name_en"), *(food.get("aliases") or ())):
            if isinstance(candidate, str) and _normalise_key(candidate):
                bucket = index.setdefault(_normalise_key(candidate), [])
                if not any(str(item.get("food_id")) == food_id for item in bucket):
                    bucket.append(food)
    return {key: tuple(value) for key, value in index.items()}


def load_adaptive_source_registry(path: Path = SOURCE_REGISTRY_FILE) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_REGISTRY") from exc
    sources = raw.get("sources") if isinstance(raw, dict) else None
    if not isinstance(sources, list):
        raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_REGISTRY")
    index: dict[str, dict[str, Any]] = {}
    required = {
        "source_id",
        "display_name",
        "source_type",
        "source_class",
        "access_status",
        "discovery_allowed",
        "fetch_allowed",
        "staging_allowed",
        "candidate_storage",
        "recipe_storage_allowed",
        "instruction_display_allowed",
        "instruction_storage_allowed",
        "ingredient_metadata_storage_allowed",
        "license_status",
        "raw_source_text_storage",
        "snapshot_cache",
        "promotion_eligible",
        "attribution_required",
        "structured_data_support",
        "preferred_fetch_method",
        "allowed_hosts",
        "rate_limit_policy",
        "authentication",
        "robots_search_restrictions",
        "terms_url",
        "license_url",
        "last_verified_at",
        "verification_evidence",
    }
    for source in sources:
        if not isinstance(source, dict) or required - set(source):
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_POLICY")
        source_id = str(source["source_id"])
        if source_id in index:
            raise AdaptiveRecipeError("DUPLICATE_ADAPTIVE_SOURCE_ID")
        if source["access_status"] not in {
            "APPROVED",
            "LIMITED",
            "BLOCKED",
            "REQUIRES_REVIEW",
        }:
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_STATUS")
        if source["raw_source_text_storage"] not in {"NONE", "EVIDENCE_ONLY", "OWNER_ONLY"}:
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_STORAGE_POLICY")
        if source["preferred_fetch_method"] not in {
            "NONE",
            "API_FETCH",
            "HTTP_FETCH",
            "PLAYWRIGHT_FETCH",
            "SEARCH_DISCOVERY_ONLY",
        }:
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_FETCH_POLICY")
        if not isinstance(source["allowed_hosts"], list) or not all(
            isinstance(host, str) and host.strip() and "/" not in host
            for host in source["allowed_hosts"]
        ):
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_HOST_POLICY")
        if not isinstance(source["rate_limit_policy"], dict):
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_RATE_POLICY")
        if not all(isinstance(source[key], bool) for key in (
            "discovery_allowed",
            "fetch_allowed",
            "staging_allowed",
            "recipe_storage_allowed",
            "instruction_display_allowed",
            "instruction_storage_allowed",
            "ingredient_metadata_storage_allowed",
            "promotion_eligible",
            "attribution_required",
        )):
            raise AdaptiveRecipeError("INVALID_ADAPTIVE_SOURCE_BOOLEAN_POLICY")
        index[source_id] = dict(source)
    return index


class CanonicalIngredientMapper:
    """Exact canonical mapping only; it never silently substitutes a food."""

    def __init__(
        self,
        foods: Iterable[Mapping[str, Any]] | None = None,
        *,
        unit_gram_conversions: Mapping[tuple[str, str], float] | None = None,
    ) -> None:
        self._foods_by_key = _canonical_food_index(foods)
        self._foods_by_id: dict[str, Mapping[str, Any]] = {}
        for matches in self._foods_by_key.values():
            for food in matches:
                food_id = str(food.get("food_id") or "")
                if food_id:
                    self._foods_by_id[food_id] = food
        self._unit_gram_conversions = {
            (str(food_id), str(unit).casefold()): _safe_float(factor)
            for (food_id, unit), factor in (unit_gram_conversions or {}).items()
        }

    def map(self, ingredient: RawIngredient) -> CanonicalIngredientMapping:
        raw_key = _normalise_key(ingredient.ingredient_name or ingredient.raw_text)
        matches = self._foods_by_key.get(raw_key, ())
        if len(matches) > 1:
            return CanonicalIngredientMapping(
                raw_ingredient=ingredient,
                canonical_food_id=None,
                canonical_food_name=None,
                grams=self._to_grams(ingredient.amount, ingredient.unit, None),
                status=MappingStatus.AMBIGUOUS,
                confidence="LOW",
                reason_code="AMBIGUOUS_CANONICAL_INGREDIENT",
                candidate_food_ids=tuple(sorted(str(item["food_id"]) for item in matches)),
                candidate_reasons=("MULTIPLE_EXACT_ALIAS_MATCHES",),
            )
        if not matches:
            grams = self._to_grams(ingredient.amount, ingredient.unit, None)
            return CanonicalIngredientMapping(
                raw_ingredient=ingredient,
                canonical_food_id=None,
                canonical_food_name=None,
                grams=grams,
                status=MappingStatus.UNMAPPED,
                confidence="NONE",
                reason_code="CANONICAL_INGREDIENT_UNMAPPED",
            )

        food = matches[0]
        food_id = str(food["food_id"])
        grams = self._to_grams(ingredient.amount, ingredient.unit, food_id)
        if grams is None:
            return CanonicalIngredientMapping(
                raw_ingredient=ingredient,
                canonical_food_id=food_id,
                canonical_food_name=str(food.get("name") or ""),
                grams=None,
                status=MappingStatus.EXACT,
                confidence="HIGH",
                canonical_state=str((food.get("canonical_description") or {}).get("state") or "UNKNOWN"),
                reason_code="QUANTITY_NOT_RESOLVED",
                allergen_ids=tuple(sorted(str(value) for value in food.get("allergen_ids") or ())),
            )

        description = food.get("canonical_description") or {}
        canonical_state = str(description.get("state") or "UNKNOWN")
        declared = (ingredient.declared_state or "").strip().upper()
        state_mismatch = declared and declared not in {"UNKNOWN", canonical_state}
        return CanonicalIngredientMapping(
            raw_ingredient=ingredient,
            canonical_food_id=food_id,
            canonical_food_name=str(food.get("name") or ""),
            grams=grams,
            status=MappingStatus.EXACT if not state_mismatch else MappingStatus.AMBIGUOUS,
            confidence="HIGH" if not state_mismatch else "LOW",
            canonical_state=canonical_state,
            reason_code="RAW_COOKED_STATE_MISMATCH" if state_mismatch else None,
            allergen_ids=tuple(sorted(str(value) for value in food.get("allergen_ids") or ())),
        )

    def _to_grams(self, amount: float | None, unit: str, food_id: str | None) -> float | None:
        try:
            quantity = _safe_float(amount)
        except AdaptiveRecipeError:
            return None
        if quantity <= 0:
            return None
        normalized_unit = (unit or "").strip().casefold()
        factors = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "mg": 0.001}
        factor = factors.get(normalized_unit)
        if factor is None and food_id is not None:
            factor = self._unit_gram_conversions.get((food_id, normalized_unit))
        return None if factor is None else round(quantity * factor, 4)

    def food_for(self, mapping: CanonicalIngredientMapping) -> Mapping[str, Any] | None:
        if mapping.canonical_food_id is None:
            return None
        return self._foods_by_id.get(mapping.canonical_food_id)

    def nutrition_for(self, mapping: CanonicalIngredientMapping, grams: float | None = None) -> NutrientTotals:
        food = self.food_for(mapping)
        actual_grams = mapping.grams if grams is None else grams
        if food is None or actual_grams is None:
            raise AdaptiveRecipeError("CANONICAL_NUTRITION_REQUIRES_EXACT_MAPPING")
        factor = actual_grams / 100.0
        return NutrientTotals(
            energy_kcal=_safe_float(food.get("energy_kcal")) * factor,
            protein_g=_safe_float(food.get("protein")) * factor,
            carbohydrate_g=_safe_float(food.get("carbohydrates")) * factor,
            fat_g=_safe_float(food.get("fat")) * factor,
        )


def calculate_canonical_nutrition(
    mappings: Iterable[CanonicalIngredientMapping], mapper: CanonicalIngredientMapper
) -> NutrientTotals:
    total = NutrientTotals()
    for mapping in mappings:
        if mapping.status not in {MappingStatus.EXACT, MappingStatus.HIGH_CONFIDENCE}:
            raise AdaptiveRecipeError("CANONICAL_CALCULATION_REQUIRES_FULL_MAPPING")
        total = total.plus(mapper.nutrition_for(mapping))
    return total.rounded()


def _derived_dietary_tags(
    mappings: Iterable[CanonicalIngredientMapping], mapper: CanonicalIngredientMapper
) -> tuple[str, ...]:
    allergens = {allergen for mapping in mappings for allergen in mapping.allergen_ids}
    tags = {f"contains_allergen:{allergen}" for allergen in allergens}
    for mapping in mappings:
        food = mapper.food_for(mapping) or {}
        tags.update(str(tag).strip().lower() for tag in food.get("objective_tags") or () if str(tag).strip())
    return tuple(sorted(tags))


_DIETARY_RESTRICTION_ALLERGENS = {
    "no_crustacean": "CRUSTACEAN",
    "no_mollusc": "MOLLUSC",
    "no_fish": "FISH",
    "no_egg": "EGG",
    "no_milk": "MILK",
    "no_peanut": "PEANUT",
    "no_tree_nut": "TREE_NUT",
    "no_soy": "SOY",
    "no_wheat_gluten": "WHEAT_GLUTEN",
    "no_sesame": "SESAME",
}


def _normalise_restriction(value: str) -> str:
    return _normalise_key(value).replace(" ", "_")


def _dietary_restriction_codes(
    candidate: RecipeCandidate, constraints: ConstraintContext
) -> tuple[str, ...]:
    """Evaluate the same normalized restriction identifiers used by nutrition.

    N3 uses the canonical ingredient tags and deterministic nutrient totals;
    it never asks a language model to infer whether a recipe is suitable.
    Unknown restriction identifiers fail closed instead of being silently
    ignored.
    """

    tags = {str(tag).lower() for tag in candidate.dietary_tags}
    allergens = set(candidate.allergen_ids)
    nutrition = candidate.canonical_nutrition
    codes: list[str] = []
    for raw_restriction in constraints.dietary_exclusions:
        restriction = _normalise_restriction(raw_restriction)
        allergen = _DIETARY_RESTRICTION_ALLERGENS.get(restriction)
        if allergen:
            if allergen in allergens:
                codes.append(f"DIETARY_RESTRICTION_VIOLATION:{restriction}")
            continue
        if restriction == "no_pork":
            violates = "contains_pork" in tags
        elif restriction == "no_beef":
            violates = "contains_beef" in tags
        elif restriction == "no_seafood":
            violates = bool(
                {"contains_seafood", "contains_fish", "contains_crustacean", "contains_mollusc"}
                & tags
            )
        elif restriction == "vegetarian":
            violates = bool(
                {
                    "contains_land_meat",
                    "contains_seafood",
                    "contains_pork",
                    "contains_beef",
                    "contains_fish",
                    "contains_crustacean",
                    "contains_mollusc",
                }
                & tags
            )
        elif restriction == "vegan":
            violates = bool(
                {
                    "contains_pork",
                    "contains_beef",
                    "contains_land_meat",
                    "contains_seafood",
                    "contains_fish",
                    "contains_crustacean",
                    "contains_mollusc",
                    "contains_egg",
                    "contains_milk",
                }
                & tags
            )
        elif restriction == "low_carb":
            violates = nutrition is None or nutrition.energy_kcal <= 0 or (
                (4.0 * nutrition.carbohydrate_g) / nutrition.energy_kcal > 0.40
            )
        elif restriction == "high_protein":
            violates = nutrition is None or nutrition.energy_kcal <= 0 or (
                (4.0 * nutrition.protein_g) / nutrition.energy_kcal < 0.25
            )
        else:
            codes.append(f"DIETARY_RESTRICTION_UNVERIFIABLE:{restriction or 'EMPTY'}")
            continue
        if violates:
            codes.append(f"DIETARY_RESTRICTION_VIOLATION:{restriction}")
    return tuple(codes)


def _untrusted_content_codes(raw_source_text: str) -> tuple[str, ...]:
    normalized = raw_source_text.casefold()
    return (
        ("UNTRUSTED_CONTENT_QUARANTINED",)
        if any(marker in normalized for marker in PROHIBITED_UNTRUSTED_MARKERS)
        else ()
    )


class RecipeQualityGate:
    """Hard deterministic checks. Semantic review may append evidence only."""

    def __init__(self, *, existing_titles: Iterable[str] = ()) -> None:
        self._existing_titles = {_normalise_key(value) for value in existing_titles}

    def evaluate(
        self,
        candidate: RecipeCandidate,
        constraints: ConstraintContext = ConstraintContext(),
    ) -> tuple[str, ...]:
        codes: list[str] = []
        if not candidate.title.strip() or not candidate.raw_ingredients:
            codes.append("RECIPE_IDENTITY_INVALID")
        if len(candidate.mappings) != len(candidate.raw_ingredients):
            codes.append("MAPPING_COVERAGE_INCOMPLETE")
        if any(mapping.status not in {MappingStatus.EXACT, MappingStatus.HIGH_CONFIDENCE} for mapping in candidate.mappings):
            codes.append("MAPPING_COVERAGE_INCOMPLETE")
        if any(mapping.grams is None or mapping.grams <= 0 for mapping in candidate.mappings):
            codes.append("UNIT_NORMALIZATION_INVALID")
        if any(mapping.reason_code == "RAW_COOKED_STATE_MISMATCH" for mapping in candidate.mappings):
            codes.append("INGREDIENT_STATE_CONFLICT")
        if candidate.canonical_nutrition is None:
            codes.append("CANONICAL_NUTRITION_UNAVAILABLE")
        else:
            nutrition = candidate.canonical_nutrition
            if min(nutrition.energy_kcal, nutrition.protein_g, nutrition.carbohydrate_g, nutrition.fat_g) < 0:
                codes.append("NEGATIVE_NUTRIENT_VALUE")
            if nutrition.energy_kcal <= 0 or nutrition.energy_kcal > 2500:
                codes.append("PORTION_NUTRIENT_OUTLIER")
            consistency = energy_consistency(
                nutrition.energy_kcal,
                nutrition.protein_g,
                nutrition.carbohydrate_g,
                nutrition.fat_g,
            )
            if consistency["status"] == "FAIL":
                codes.append("ENERGY_MACRO_SANITY_FAIL")
            elif consistency["status"] == "REVIEW":
                codes.append("ENERGY_MACRO_SANITY_REVIEW")
        candidate_allergens = set(candidate.allergen_ids)
        if candidate_allergens & constraints.allergen_exclusions:
            codes.append("ALLERGEN_VIOLATION")
        codes.extend(_dietary_restriction_codes(candidate, constraints))
        if _normalise_key(candidate.title) in self._existing_titles:
            codes.append("DUPLICATE_RECIPE_CANDIDATE")
        if candidate.source_reported_nutrition and candidate.canonical_nutrition:
            codes.extend(
                _nutrition_conflict_codes(
                    candidate.source_reported_nutrition, candidate.canonical_nutrition
                )
            )
        codes.extend(_untrusted_content_codes(candidate.evidence.raw_source_text))
        return tuple(sorted(set(codes)))

    @staticmethod
    def hard_pass(codes: Iterable[str]) -> bool:
        hard_prefixes = (
            "RECIPE_IDENTITY_INVALID",
            "MAPPING_COVERAGE_INCOMPLETE",
            "UNIT_NORMALIZATION_INVALID",
            "INGREDIENT_STATE_CONFLICT",
            "CANONICAL_NUTRITION_UNAVAILABLE",
            "NEGATIVE_NUTRIENT_VALUE",
            "PORTION_NUTRIENT_OUTLIER",
            "ENERGY_MACRO_SANITY_FAIL",
            "ALLERGEN_VIOLATION",
            "DIETARY_RESTRICTION_VIOLATION",
            "DIETARY_RESTRICTION_UNVERIFIABLE",
            "DUPLICATE_RECIPE_CANDIDATE",
            "UNTRUSTED_CONTENT_QUARANTINED",
        )
        return not any(code.startswith(hard_prefixes) for code in codes)


def _nutrition_conflict(source: NutrientTotals, canonical: NutrientTotals) -> bool:
    return bool(_nutrition_conflict_codes(source, canonical))


def _nutrition_conflict_codes(source: NutrientTotals, canonical: NutrientTotals) -> tuple[str, ...]:
    fields = (
        ("ENERGY_CONFLICT", source.energy_kcal, canonical.energy_kcal),
        ("PROTEIN_CONFLICT", source.protein_g, canonical.protein_g),
        ("CARB_CONFLICT", source.carbohydrate_g, canonical.carbohydrate_g),
        ("FAT_CONFLICT", source.fat_g, canonical.fat_g),
    )
    codes = [
        code
        for code, reported, calculated in fields
        if calculated > 0
        and abs(reported - calculated) / calculated
        > SOURCE_NUTRITION_CONFLICT_RELATIVE_DELTA
    ]
    return tuple(("SOURCE_NUTRITION_CONFLICT", *codes)) if codes else ()


def build_recipe_candidate(
    *,
    trust_domain: TrustDomain,
    title: str,
    source: CandidateSource,
    raw_ingredients: Sequence[RawIngredient],
    raw_source_text: str = "",
    aliases: Sequence[str] = (),
    source_reported_nutrition: NutrientTotals | None = None,
    owner_user_id: str | None = None,
    recipe_origin: str = "SOURCE_RECIPE",
    runtime_recipe_identity: str | None = None,
    extraction_method: str | None = None,
    structured_data_present: bool | None = None,
    mapping_count_coverage: float | None = None,
    mapping_mass_coverage: float | None = None,
    untrusted_content: str | None = None,
    mapper: CanonicalIngredientMapper | None = None,
    source_policies: Mapping[str, Mapping[str, Any]] | None = None,
    quality_gate: RecipeQualityGate | None = None,
    constraints: ConstraintContext = ConstraintContext(),
) -> RecipeCandidate:
    if trust_domain == TrustDomain.CANONICAL_PRODUCTION_RECIPE:
        raise AdaptiveRecipeError("N3_CANNOT_CREATE_CANONICAL_PRODUCTION_RECIPE")
    if trust_domain == TrustDomain.FROZEN_RESEARCH_RECIPE:
        raise AdaptiveRecipeError("N3_CANNOT_MUTATE_FROZEN_RESEARCH_RECIPE")
    if trust_domain not in {
        TrustDomain.PERSONAL_RECIPE,
        TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        TrustDomain.STAGING_RECIPE,
    }:
        raise AdaptiveRecipeError("N3_RECIPE_CANDIDATE_DOMAIN_INVALID")
    if trust_domain == TrustDomain.PERSONAL_RECIPE and not (owner_user_id or "").strip():
        raise AdaptiveRecipeError("PERSONAL_RECIPE_REQUIRES_OWNER")
    if not title.strip() or not raw_ingredients:
        raise AdaptiveRecipeError("RECIPE_REQUIRES_TITLE_AND_INGREDIENTS")

    policy = (source_policies or load_adaptive_source_registry()).get(source.source_id)
    if policy is None:
        raise AdaptiveRecipeError("UNKNOWN_RECIPE_SOURCE")
    if source.source_type != policy["source_type"]:
        raise AdaptiveRecipeError("RECIPE_SOURCE_TYPE_MISMATCH")
    if source.license_status and source.license_status != policy["license_status"]:
        raise AdaptiveRecipeError("RECIPE_SOURCE_LICENSE_MISMATCH")
    if policy["access_status"] == "BLOCKED":
        raise AdaptiveRecipeError("RECIPE_SOURCE_BLOCKED")
    if policy["access_status"] == "REQUIRES_REVIEW":
        raise AdaptiveRecipeError("RECIPE_SOURCE_REQUIRES_REVIEW")
    if (
        trust_domain in {TrustDomain.RUNTIME_EXTERNAL_CANDIDATE, TrustDomain.STAGING_RECIPE}
        and not policy["staging_allowed"]
    ):
        raise AdaptiveRecipeError("RECIPE_SOURCE_STAGING_FORBIDDEN")
    if trust_domain != TrustDomain.PERSONAL_RECIPE and policy["candidate_storage"] == "PERSONAL_ONLY":
        raise AdaptiveRecipeError("SOURCE_PERSONAL_ONLY")
    if trust_domain == TrustDomain.PERSONAL_RECIPE and policy["candidate_storage"] != "PERSONAL_ONLY":
        raise AdaptiveRecipeError("PERSONAL_RECIPE_REQUIRES_PERSONAL_SOURCE")
    if raw_source_text and policy["raw_source_text_storage"] == "NONE":
        raise AdaptiveRecipeError("RECIPE_SOURCE_TEXT_STORAGE_FORBIDDEN")

    base = RecipeCandidate.draft(
        trust_domain=trust_domain,
        title=title,
        aliases=tuple(alias.strip() for alias in aliases if alias.strip()),
        source=source,
        raw_ingredients=tuple(raw_ingredients),
        raw_source_text=raw_source_text,
        source_reported_nutrition=source_reported_nutrition,
        owner_user_id=owner_user_id,
        recipe_origin=recipe_origin,
    )
    active_mapper = mapper or CanonicalIngredientMapper()
    mappings = tuple(active_mapper.map(item) for item in base.raw_ingredients)
    try:
        calculated = calculate_canonical_nutrition(mappings, active_mapper)
    except AdaptiveRecipeError:
        calculated = None
    allergens = tuple(sorted({item for mapping in mappings for item in mapping.allergen_ids}))
    evidence = RecipeEvidenceBundle(
        source=source,
        raw_source_text=raw_source_text,
        raw_ingredients=base.raw_ingredients,
        mappings=mappings,
        calculated_nutrition=calculated,
        source_reported_nutrition=source_reported_nutrition,
        derived_allergen_ids=allergens,
        duplicate_candidates=(),
        validation_codes=(),
        calculation_version=CALCULATION_VERSION,
        extraction_method=extraction_method,
        structured_data_present=structured_data_present,
        mapping_count_coverage=mapping_count_coverage,
        mapping_mass_coverage=mapping_mass_coverage,
    ).with_hash()
    mapped = replace(
        base,
        mappings=mappings,
        canonical_nutrition=calculated,
        allergen_ids=allergens,
        dietary_tags=_derived_dietary_tags(mappings, active_mapper),
        evidence=evidence,
        status=CandidateStatus.CALCULATED if calculated else CandidateStatus.MAPPED,
        lifecycle_history=base.lifecycle_history
        + (CandidateStatus.MAPPED.value,)
        + ((CandidateStatus.CALCULATED.value,) if calculated else ()),
    )
    gate = quality_gate or RecipeQualityGate()
    codes = gate.evaluate(mapped, constraints)
    if untrusted_content:
        codes = tuple(sorted(set(codes) | set(_untrusted_content_codes(untrusted_content))))
    evidence = replace(mapped.evidence, validation_codes=codes).with_hash()
    status = CandidateStatus.VALIDATED if gate.hard_pass(codes) else CandidateStatus.QUARANTINED
    return replace(
        mapped,
        evidence=evidence,
        validation_codes=codes,
        status=status,
        lifecycle_history=mapped.lifecycle_history + (status.value,),
        quality_score=1.0 if gate.hard_pass(codes) else None,
        runtime_recipe_identity=runtime_recipe_identity,
    )


class RecipePortionFitter:
    """A deterministic, bounded coordinate-search portion optimizer.

    Bounds are product recipe heuristics, not nutrient evidence. Food values are
    always recalculated from canonical composition records.
    """

    _BOUNDS: Mapping[IngredientScaleClass, tuple[float, float]] = {
        IngredientScaleClass.ANCHOR: (0.80, 1.25),
        IngredientScaleClass.SCALABLE: (0.55, 1.75),
        IngredientScaleClass.LIMITED_SCALABLE: (0.40, 1.15),
        IngredientScaleClass.FLAVOR_BOUNDED: (0.75, 1.25),
        IngredientScaleClass.OPTIONAL: (0.0, 1.50),
        IngredientScaleClass.FIXED: (1.0, 1.0),
    }

    def __init__(
        self,
        mapper: CanonicalIngredientMapper,
        *,
        scale_classes: Mapping[str, IngredientScaleClass] | None = None,
    ) -> None:
        self._mapper = mapper
        self._scale_classes = dict(scale_classes or {})

    def fit(
        self,
        candidate: RecipeCandidate,
        constraints: ConstraintContext,
        *,
        preferred_serving_scale: float | None = None,
    ) -> PortionFitResult:
        gate_codes = RecipeQualityGate().evaluate(candidate, constraints)
        if not RecipeQualityGate.hard_pass(gate_codes):
            return PortionFitResult(
                status="NO_FEASIBLE_RECIPE_ADAPTATION",
                ingredient_grams={},
                nutrition=None,
                reason_codes=tuple(sorted(set(gate_codes))),
            )
        if constraints.target_kcal is None and constraints.target_protein_g is None:
            return PortionFitResult(
                status="FIT_NOT_REQUIRED",
                ingredient_grams=self._gram_payload(candidate, [1.0] * len(candidate.mappings)),
                nutrition=candidate.canonical_nutrition,
                reason_codes=("NO_PORTION_TARGET",),
                objective_score=0.0,
            )
        if constraints.target_kcal is not None and constraints.target_kcal <= 0:
            raise AdaptiveRecipeError("INVALID_PORTION_KCAL_TARGET")
        if constraints.target_protein_g is not None and constraints.target_protein_g < 0:
            raise AdaptiveRecipeError("INVALID_PORTION_PROTEIN_TARGET")
        if preferred_serving_scale is not None and not (0.80 <= preferred_serving_scale <= 1.25):
            raise AdaptiveRecipeError("INVALID_PERSONAL_PORTION_PRIOR")

        classes = [self._classify(mapping) for mapping in candidate.mappings]
        scales = [1.0] * len(candidate.mappings)
        for _ in range(12):
            changed = False
            for index, scale_class in enumerate(classes):
                options = self._scale_options(scale_class)
                best_scale = min(
                    options,
                    key=lambda option: self._objective(
                        candidate,
                        scales[:index] + [option] + scales[index + 1 :],
                        constraints,
                        preferred_serving_scale=preferred_serving_scale,
                    ),
                )
                if best_scale != scales[index]:
                    scales[index] = best_scale
                    changed = True
            if not changed:
                break
        nutrition = self._nutrition(candidate, scales)
        if not self._meets_target(nutrition, constraints):
            return PortionFitResult(
                status="NO_FEASIBLE_RECIPE_ADAPTATION",
                ingredient_grams={},
                nutrition=None,
                reason_codes=("PORTION_TARGET_OUTSIDE_CULINARY_BOUNDS",),
                objective_score=round(
                    self._objective(
                        candidate,
                        scales,
                        constraints,
                        preferred_serving_scale=preferred_serving_scale,
                    ),
                    6,
                ),
            )
        return PortionFitResult(
            status="FIT",
            ingredient_grams=self._gram_payload(candidate, scales),
            nutrition=nutrition.rounded(),
            reason_codes=("CANONICAL_INGREDIENT_RECALCULATION",),
            objective_score=round(self._objective(candidate, scales, constraints), 6),
        )

    def create_adapted_variant(
        self,
        candidate: RecipeCandidate,
        constraints: ConstraintContext,
    ) -> RecipeCandidate | None:
        """Return a new, recalculated revision; never alter source evidence.

        The base candidate remains the externally acquired recipe.  The
        resulting revision is explicitly marked so a caller cannot present its
        quantities as if they had been published by the external source.
        """

        fit = self.fit(candidate, constraints)
        if fit.status != "FIT":
            return None
        ingredients: list[RawIngredient] = []
        for index, mapping in enumerate(candidate.mappings):
            key = f"{mapping.canonical_food_id}:{index}"
            grams = fit.ingredient_grams.get(key)
            if grams is None:
                raise AdaptiveRecipeError("ADAPTED_RECIPE_GRAMS_MISSING")
            raw = mapping.raw_ingredient
            ingredients.append(
                RawIngredient(
                    raw_text=raw.raw_text,
                    amount=grams,
                    unit="g",
                    declared_state=mapping.canonical_state or raw.declared_state,
                    ingredient_name=raw.ingredient_name,
                    preparation_state=raw.preparation_state,
                    optional=raw.optional,
                    quantity_uncertain=False,
                )
            )
        return build_recipe_candidate(
            trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
            title=candidate.title,
            aliases=candidate.aliases,
            source=candidate.source,
            raw_ingredients=tuple(ingredients),
            raw_source_text=candidate.evidence.raw_source_text,
            source_reported_nutrition=candidate.source_reported_nutrition,
            recipe_origin="ADAPTED_RECIPE_VARIANT",
            runtime_recipe_identity=candidate.runtime_recipe_identity,
            extraction_method=candidate.evidence.extraction_method,
            structured_data_present=candidate.evidence.structured_data_present,
            mapper=self._mapper,
            constraints=constraints,
        )

    def _classify(self, mapping: CanonicalIngredientMapping) -> IngredientScaleClass:
        if mapping.canonical_food_id in self._scale_classes:
            return self._scale_classes[mapping.canonical_food_id]
        name = (mapping.canonical_food_name or "").casefold()
        if any(token in name for token in ("dầu", "oil", "mỡ", "sauce", "nước mắm", "đường")):
            return IngredientScaleClass.LIMITED_SCALABLE
        if any(token in name for token in ("muối", "tiêu", "ớt", "rau thơm", "gia vị")):
            return IngredientScaleClass.FLAVOR_BOUNDED
        food = self._mapper.food_for(mapping) or {}
        tags = set(food.get("objective_tags") or ())
        if tags & {"contains_land_meat", "contains_seafood", "contains_egg"}:
            return IngredientScaleClass.ANCHOR
        return IngredientScaleClass.SCALABLE

    def _scale_options(self, scale_class: IngredientScaleClass) -> tuple[float, ...]:
        low, high = self._BOUNDS[scale_class]
        count = int(round((high - low) / 0.05))
        return tuple(round(low + (index * 0.05), 2) for index in range(count + 1))

    def _nutrition(self, candidate: RecipeCandidate, scales: Sequence[float]) -> NutrientTotals:
        total = NutrientTotals()
        for mapping, scale in zip(candidate.mappings, scales):
            if mapping.grams is None:
                raise AdaptiveRecipeError("PORTION_FITTER_REQUIRES_GRAMS")
            total = total.plus(self._mapper.nutrition_for(mapping, mapping.grams * scale))
        return total

    def _objective(
        self,
        candidate: RecipeCandidate,
        scales: Sequence[float],
        constraints: ConstraintContext,
        *,
        preferred_serving_scale: float | None = None,
    ) -> float:
        nutrition = self._nutrition(candidate, scales)
        energy_term = (
            abs(nutrition.energy_kcal - constraints.target_kcal) / constraints.target_kcal
            if constraints.target_kcal
            else 0.0
        )
        protein_term = (
            abs(nutrition.protein_g - constraints.target_protein_g) / max(constraints.target_protein_g, 1.0)
            if constraints.target_protein_g is not None
            else 0.0
        )
        distortion = sum((scale - 1.0) ** 2 for scale in scales) / max(len(scales), 1)
        preference_distance = (
            sum((scale - preferred_serving_scale) ** 2 for scale in scales) / max(len(scales), 1)
            if preferred_serving_scale is not None
            else 0.0
        )
        # Personal portions are a small soft tie-breaker.  They cannot relax
        # the target tolerance or ingredient-class culinary bounds above.
        return energy_term + protein_term + (0.05 * distortion) + (0.02 * preference_distance)

    @staticmethod
    def _meets_target(nutrition: NutrientTotals, constraints: ConstraintContext) -> bool:
        if constraints.target_kcal is not None:
            if abs(nutrition.energy_kcal - constraints.target_kcal) / constraints.target_kcal > PORTION_TARGET_TOLERANCE:
                return False
        if constraints.target_protein_g is not None:
            if nutrition.protein_g < constraints.target_protein_g * (1.0 - PORTION_TARGET_TOLERANCE):
                return False
        return True

    @staticmethod
    def _gram_payload(candidate: RecipeCandidate, scales: Sequence[float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for index, (mapping, scale) in enumerate(zip(candidate.mappings, scales)):
            key = f"{mapping.canonical_food_id}:{index}"
            result[key] = round((mapping.grams or 0.0) * scale, 2)
        return result


__all__ = [
    "AdaptiveRecipeError",
    "CALCULATION_VERSION",
    "CanonicalIngredientMapper",
    "PORTION_TARGET_TOLERANCE",
    "RecipePortionFitter",
    "RecipeQualityGate",
    "SOURCE_NUTRITION_CONFLICT_RELATIVE_DELTA",
    "build_recipe_candidate",
    "calculate_canonical_nutrition",
    "load_adaptive_source_registry",
]
