"""Canonical Vietnamese ingredient records and auditable recipe quality.

The frozen source files remain byte-for-byte unchanged.  This module adds a
runtime canonical layer with stable food IDs, per-field source provenance,
food-state metadata, deterministic allergen taxonomy, and quality signals.
Only nutrient sources explicitly marked ``ACTIVE`` in the source registry may
provide runtime nutrient values.
"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FOODS_FILE = DATA_DIR / "vietnamese_foods.json"
SOURCE_REGISTRY_FILE = DATA_DIR / "food_source_registry_v1.json"

CANONICAL_POLICY_VERSION = "canonical-food-v1.0.0"
ALLERGEN_TAXONOMY_VERSION = "allergen-taxonomy-v1.0.0"
SOURCE_ACCESSED_AT = "2026-08-30"


class CanonicalFoodError(ValueError):
    """Raised when canonical food sources violate an audit invariant."""


class MatchQuality(str, Enum):
    EXACT = "EXACT"
    CLOSE_VARIANT = "CLOSE_VARIANT"
    GENERIC_PARENT = "GENERIC_PARENT"
    SUBSTITUTED_WITH_JUSTIFICATION = "SUBSTITUTED_WITH_JUSTIFICATION"
    UNRESOLVED = "UNRESOLVED"


AUTO_PUBLISH_MATCH_QUALITIES = frozenset(
    {MatchQuality.EXACT.value}
)

_NUTRIENT_FIELDS = {
    "energy_kcal": "kcal",
    "protein": "g",
    "fat": "g",
    "carbohydrates": "g",
    "fiber": "g",
    "calcium": "mg",
    "iron": "mg",
    "magnesium": "mg",
    "phosphorus": "mg",
    "potassium": "mg",
    "sodium": "mg",
    "zinc": "mg",
    "vitamin_c": "mg",
}

_COOKING_TERMS: tuple[tuple[str, str], ...] = (
    ("luộc", "BOILED"),
    ("nướng", "GRILLED"),
    ("rang", "ROASTED"),
    ("chiên", "FRIED"),
    ("chao dầu", "FRIED"),
    ("quay", "ROASTED"),
    ("hấp", "STEAMED"),
    ("hầm", "STEWED"),
    ("kho", "BRAISED"),
    ("xào", "STIR_FRIED"),
)
_RAW_TERMS = ("tươi", "sống")
_DRIED_TERMS = ("khô", "sấy")
_PROCESSED_TERMS: tuple[tuple[str, str], ...] = (
    ("lên men", "FERMENTED"),
    ("sữa chua", "FERMENTED"),
    ("mắm", "FERMENTED"),
    ("bột", "MILLED"),
    ("dầu", "EXTRACTED"),
    ("nước", "EXTRACTED"),
    ("giò", "PROCESSED"),
    ("chả", "PROCESSED"),
    ("xúc xích", "PROCESSED"),
    ("bánh", "PROCESSED"),
)

_CRUSTACEAN_TERMS = ("tôm", "cua", "ghẹ", "rạm", "tép")
_MOLLUSC_TERMS = (
    "mực",
    "sò",
    "ốc",
    "hến",
    "trai",
    "nghêu",
    "ngao",
    "bạch tuộc",
)
_FISH_TERMS = ("cá", "nước mắm", "mắm cá")
_PEANUT_TERMS = ("lạc", "đậu phộng")
_TREE_NUT_TERMS = (
    "hạt điều",
    "hạt dẻ",
    "hạnh nhân",
    "óc chó",
    "mắc ca",
    "macadamia",
)
_SOY_TERMS = ("đậu tương", "đậu nành", "đậu phụ", "tàu hũ")
_WHEAT_TERMS = ("bột mì", "bánh mì", "mì sợi", "mì căn")
_SESAME_TERMS = ("vừng", "mè")

_DISH_REGION_RULES: tuple[dict[str, str], ...] = (
    {
        "token": "BUN_CHA",
        "match_mode": "EXACT",
        "region": "North",
        "source_url": (
            "https://www.vietnam.travel/things-to-do/10-must-try-hanoi-dishes"
        ),
        "confidence": "HIGH",
    },
    {
        "token": "BUN_BO_HUE",
        "match_mode": "EXACT",
        "region": "Central",
        "source_url": (
            "https://vietnam.travel/vi/things-to-do/"
            "beyond-pho-5-awesome-vietnamese-noodles"
        ),
        "confidence": "HIGH",
    },
    {
        "token": "CAO_LAU",
        "match_mode": "EXACT",
        "region": "Central",
        "source_url": (
            "https://vietnam.travel/vi/things-to-do/"
            "beyond-pho-5-awesome-vietnamese-noodles"
        ),
        "confidence": "HIGH",
    },
    {
        "token": "COM_TAM",
        "match_mode": "PREFIX",
        "region": "South",
        "source_url": (
            "https://www.vietnam.travel/vi/things-to-do/"
            "explore-delicious-dishes-ho-chi-minh-city"
        ),
        "confidence": "HIGH",
    },
    {
        "token": "HU_TIEU",
        "match_mode": "EXACT",
        "region": "South",
        "source_url": (
            "https://vietnam.travel/vi/things-to-do/"
            "beyond-pho-5-awesome-vietnamese-noodles"
        ),
        "confidence": "HIGH",
    },
    {
        "token": "PHO",
        "match_mode": "PREFIX",
        "region": "National",
        "source_url": "https://vietnam.travel/things-to-do/must-try-noodles-vietnam",
        "confidence": "MEDIUM",
    },
)


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalFoodError(f"INVALID_CANONICAL_SOURCE:{path.name}") from exc


def _safe_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _ascii_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    ascii_text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", ascii_text.upper()).strip("_")


def resolve_dish_region(name: str) -> dict[str, Any]:
    """Return only sourced cultural-region metadata; never guess a region."""

    normalized = _ascii_key(name)
    for rule in _DISH_REGION_RULES:
        token = rule["token"]
        matched = normalized == token or (
            rule["match_mode"] == "PREFIX" and normalized.startswith(f"{token}_")
        )
        if matched:
            return {
                "region": rule["region"],
                "source_url": rule["source_url"],
                "confidence": rule["confidence"],
                "method": "CURATED_CULTURAL_SOURCE",
            }
    return {
        "region": "Unknown",
        "source_url": None,
        "confidence": "UNKNOWN",
        "method": "UNRESOLVED",
    }


def _source_record_id(food: dict[str, Any]) -> int:
    value = food.get("ma_so") or food.get("stt")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalFoodError("INVALID_VIETNAM_FCT_RECORD_ID") from exc


@lru_cache(maxsize=1)
def _load_source_registry_cached() -> dict[str, Any]:
    raw = _read_json(SOURCE_REGISTRY_FILE)
    if not isinstance(raw, dict) or not isinstance(raw.get("sources"), list):
        raise CanonicalFoodError("INVALID_SOURCE_REGISTRY_SHAPE")

    sources = raw["sources"]
    source_ids = [str(source.get("source_id", "")) for source in sources]
    priorities = [source.get("priority") for source in sources]
    if any(not source_id for source_id in source_ids) or len(source_ids) != len(
        set(source_ids)
    ):
        raise CanonicalFoodError("INVALID_OR_DUPLICATE_SOURCE_ID")
    if priorities != list(range(len(priorities))):
        raise CanonicalFoodError("NON_CONTIGUOUS_SOURCE_PRIORITY")

    active_nutrient_sources = [
        source
        for source in sources
        if source.get("kind") == "NUTRIENT_DATABASE"
        and source.get("ingestion_status") == "ACTIVE"
    ]
    if [source["source_id"] for source in active_nutrient_sources] != [
        "VIETNAM_FCT"
    ]:
        raise CanonicalFoodError("UNAPPROVED_ACTIVE_NUTRIENT_SOURCE")
    return raw


def load_source_registry() -> dict[str, Any]:
    """Return a caller-owned copy of the ordered source policy."""

    return deepcopy(_load_source_registry_cached())


def _food_description(name: str, name_en: str | None) -> dict[str, Any]:
    folded = name.casefold()
    cooking_method = "NONE"
    state = "UNKNOWN"
    processing = "UNSPECIFIED"

    for term, method in _COOKING_TERMS:
        if term in folded:
            cooking_method = method
            state = "COOKED"
            processing = "COOKED"
            break
    if state == "UNKNOWN" and any(term in folded for term in _DRIED_TERMS):
        state = "DRIED"
        processing = "DRIED"
    if state == "UNKNOWN" and any(term in folded for term in _RAW_TERMS):
        state = "RAW"
        processing = "NONE"
    if processing == "UNSPECIFIED":
        for term, method in _PROCESSED_TERMS:
            if term in folded:
                processing = method
                state = "PROCESSED"
                break

    return {
        "food": name,
        "species_or_type": name_en or None,
        "part_or_cut": None,
        "processing": processing,
        "cooking_method": cooking_method,
        "state": state,
        "derivation": {
            "method": "SOURCE_NAME_PARSER",
            "version": CANONICAL_POLICY_VERSION,
            "confidence": "HIGH" if state != "UNKNOWN" else "UNKNOWN",
            "used_for_exact_matching": False,
        },
    }


def derive_allergen_ids(name: str, source_record_id: int) -> list[str]:
    """Derive canonical allergen IDs from source taxonomy and exact names."""

    folded = name.casefold()
    allergens: set[str] = set()

    if any(term in folded for term in _CRUSTACEAN_TERMS):
        allergens.add("CRUSTACEAN")
    elif any(term in folded for term in _MOLLUSC_TERMS):
        allergens.add("MOLLUSC")
    elif 8000 <= source_record_id < 9000 or any(
        term in folded for term in _FISH_TERMS
    ):
        allergens.add("FISH")
    if 9000 <= source_record_id < 10000:
        allergens.add("EGG")
    if 10000 <= source_record_id < 11000:
        allergens.add("MILK")
    if any(term in folded for term in _PEANUT_TERMS):
        allergens.add("PEANUT")
    if any(term in folded for term in _TREE_NUT_TERMS):
        allergens.add("TREE_NUT")
    if any(term in folded for term in _SOY_TERMS):
        allergens.add("SOY")
    if any(term in folded for term in _WHEAT_TERMS):
        allergens.add("WHEAT_GLUTEN")
    if any(term in folded for term in _SESAME_TERMS):
        allergens.add("SESAME")
    return sorted(allergens)


def _contains_terms(value: str, terms: Iterable[str]) -> bool:
    return any(term in value for term in terms)


def derive_objective_food_tags(
    name: str, source_record_id: int, allergen_ids: Iterable[str]
) -> list[str]:
    """Return only ingredient facts that can be deterministically derived."""

    folded = name.casefold()
    tags = {f"contains_allergen:{item}" for item in allergen_ids}
    allergen_set = set(allergen_ids)
    if allergen_set & {"FISH", "CRUSTACEAN", "MOLLUSC"}:
        tags.add("contains_seafood")
    is_land_meat = 7000 <= source_record_id < 8000
    if is_land_meat:
        tags.add("contains_land_meat")
    if "EGG" in allergen_set:
        tags.add("contains_egg")
    if "MILK" in allergen_set:
        tags.add("contains_dairy")
    if is_land_meat and _contains_terms(folded, ("lợn", "heo")):
        tags.add("contains_pork")
    if is_land_meat and "bò" in folded:
        tags.add("contains_beef")
    if is_land_meat and _contains_terms(
        folded, ("gà", "vịt", "ngan", "chim")
    ):
        tags.add("contains_poultry")
    return sorted(tags)


def energy_consistency(
    energy_kcal: float, protein_g: float, carbohydrate_g: float, fat_g: float
) -> dict[str, Any]:
    """Return a 4/4/9 QA signal without replacing source energy."""

    macro_energy = 4.0 * protein_g + 4.0 * carbohydrate_g + 9.0 * fat_g
    if energy_kcal <= 0:
        return {
            "status": "NOT_APPLICABLE",
            "source_energy_kcal": round(energy_kcal, 3),
            "macro_energy_kcal": round(macro_energy, 3),
            "relative_delta": None,
            "method": "4P+4C+9F_QA_ONLY",
        }
    relative_delta = abs(energy_kcal - macro_energy) / energy_kcal
    status = "PASS" if relative_delta <= 0.10 else "REVIEW" if relative_delta <= 0.20 else "FAIL"
    return {
        "status": status,
        "source_energy_kcal": round(energy_kcal, 3),
        "macro_energy_kcal": round(macro_energy, 3),
        "relative_delta": round(relative_delta, 6),
        "method": "4P+4C+9F_QA_ONLY",
        "note": "Fiber, organic acids and source energy conventions can explain differences.",
    }


def _canonical_food(food: dict[str, Any]) -> dict[str, Any]:
    source_record_id = _source_record_id(food)
    source_name_vi = str(food.get("name") or "").strip()
    name = source_name_vi or str(food.get("name_en") or "").strip()
    if not name:
        raise CanonicalFoodError(f"MISSING_FOOD_NAME:{source_record_id}")
    allergens = derive_allergen_ids(name, source_record_id)
    description = _food_description(name, food.get("name_en"))
    nutrients = {}
    for field, unit in _NUTRIENT_FIELDS.items():
        reported = field in food and food.get(field) is not None
        nutrients[field] = {
            "value": _safe_float(food.get(field)) if reported else None,
            "unit": unit,
            "basis": "PER_100G_EDIBLE_PORTION",
            "data_status": "REPORTED" if reported else "MISSING",
            "source_id": "VIETNAM_FCT",
            "source_record_id": source_record_id,
            "source_edition": "2007",
            "original_value": _safe_float(food.get(field)) if reported else None,
            "original_unit": unit if reported else None,
            "original_basis": "PER_100G_EDIBLE_PORTION" if reported else None,
            "normalized_value": _safe_float(food.get(field)) if reported else None,
            "normalized_unit": unit,
            "normalization_rule": (
                "IDENTITY_SOURCE_PER_100G"
                if reported
                else "MISSING_PRESERVED_AS_NULL"
            ),
            "review_status": "SOURCE_IMPORTED" if reported else "MISSING",
        }
    energy_qa = energy_consistency(
        _safe_float(nutrients["energy_kcal"]["value"]),
        _safe_float(nutrients["protein"]["value"]),
        _safe_float(nutrients["carbohydrates"]["value"]),
        _safe_float(nutrients["fat"]["value"]),
    )
    canonical = deepcopy(food)
    canonical.update(
        {
            "name": name,
            "name_vi": source_name_vi or None,
            "canonical_name_language": "vi" if source_name_vi else "en",
            "food_id": f"VN_FCT_{source_record_id:05d}",
            "canonical_key": (
                f"{_ascii_key(name)}__{description['state']}__"
                f"{description['processing']}__VN_FCT_{source_record_id:05d}"
            ),
            "canonical_description": description,
            "nutrients_per_100g": nutrients,
            "source": {
                "dataset": "VIETNAM_FCT",
                "edition": "2007",
                "source_record_id": source_record_id,
                "official_url": (
                    "https://chuyentrang.viendinhduong.vn/viewfilenew/vi/"
                    "thu-vien-sach-chuyen-nganh/189/1.html"
                ),
                "accessed_at": SOURCE_ACCESSED_AT,
                "match_quality": MatchQuality.EXACT.value,
            },
            "allergen_ids": allergens,
            "allergen_taxonomy_version": ALLERGEN_TAXONOMY_VERSION,
            "objective_tags": derive_objective_food_tags(
                name, source_record_id, allergens
            ),
            "verification": {
                "review_status": (
                    "DATA_REVIEW_REQUIRED"
                    if energy_qa["status"] == "FAIL"
                    else "REVIEW_REQUIRED"
                    if energy_qa["status"] == "REVIEW"
                    else "SOURCE_IMPORTED"
                ),
                "policy_version": CANONICAL_POLICY_VERSION,
                "energy_qa": energy_qa,
            },
        }
    )
    return canonical


@lru_cache(maxsize=1)
def _load_canonical_food_catalog_cached() -> tuple[dict[str, Any], ...]:
    # Loading the registry first makes an unapproved active fallback fatal.
    _load_source_registry_cached()
    raw = _read_json(FOODS_FILE)
    if not isinstance(raw, list):
        raise CanonicalFoodError("INVALID_VIETNAM_FCT_SHAPE")
    foods = tuple(_canonical_food(food) for food in raw if isinstance(food, dict))
    food_ids = [food["food_id"] for food in foods]
    names = [food["name"].strip().casefold() for food in foods]
    if len(food_ids) != len(set(food_ids)):
        raise CanonicalFoodError("DUPLICATE_CANONICAL_FOOD_ID")
    if len(names) != len(set(names)):
        raise CanonicalFoodError("DUPLICATE_CANONICAL_FOOD_NAME")
    return foods


def load_canonical_food_catalog() -> list[dict[str, Any]]:
    """Return canonical foods while preserving legacy nutrient fields."""

    return deepcopy(list(_load_canonical_food_catalog_cached()))


@lru_cache(maxsize=1)
def _canonical_foods_by_name() -> dict[str, dict[str, Any]]:
    return {food["name"]: food for food in _load_canonical_food_catalog_cached()}


def resolve_food_match(name: str) -> dict[str, Any]:
    """Resolve an exact Vietnamese FCT match; never invent a substitution."""

    food = _canonical_foods_by_name().get(name)
    if food is None:
        return {
            "food_id": None,
            "quality": MatchQuality.UNRESOLVED.value,
            "auto_publishable": False,
            "review_status": "DATA_REVIEW_REQUIRED",
        }
    return {
        "food_id": food["food_id"],
        "quality": MatchQuality.EXACT.value,
        "auto_publishable": True,
        "review_status": "APPROVED",
        "source_id": "VIETNAM_FCT",
        "source_record_id": food["source"]["source_record_id"],
        "source_state": food["canonical_description"]["state"],
        "source_processing": food["canonical_description"]["processing"],
    }


def _dish_objective_tags(
    foods: list[dict[str, Any]], *, ingredient_complete: bool
) -> list[str]:
    tags = {
        tag
        for food in foods
        for tag in food.get("objective_tags", [])
        if tag.startswith("contains_")
    }
    if not ingredient_complete:
        return sorted(tags)
    contains_animal = bool(
        tags
        & {
            "contains_land_meat",
            "contains_seafood",
            "contains_egg",
            "contains_dairy",
        }
    )
    if not (tags & {"contains_land_meat", "contains_seafood"}):
        tags.add("vegetarian")
    if not contains_animal:
        tags.add("vegan")
    return sorted(tags)


def enrich_dish_quality(dish: dict[str, Any]) -> dict[str, Any]:
    """Attach exact matches, serving provenance and reproducible nutrition."""

    enriched = deepcopy(dish)
    foods_by_name = _canonical_foods_by_name()
    ingredients = enriched.get("ingredients") or []
    enriched_ingredients: list[dict[str, Any]] = []
    matched_foods: list[dict[str, Any]] = []
    totals = {"energy": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    quantified_weight = 0.0

    for ingredient in ingredients:
        item = deepcopy(ingredient)
        name = str(item.get("name", ""))
        match = resolve_food_match(name)
        item["food_id"] = match["food_id"]
        item["match"] = match
        food = foods_by_name.get(name)
        grams = _safe_float(item.get("grams"))
        if food is not None and grams > 0:
            matched_foods.append(food)
            quantified_weight += grams
            factor = grams / 100.0
            totals["energy"] += _safe_float(food.get("energy_kcal")) * factor
            totals["protein"] += _safe_float(food.get("protein")) * factor
            totals["carbs"] += _safe_float(food.get("carbohydrates")) * factor
            totals["fat"] += _safe_float(food.get("fat")) * factor
            item["food_state"] = food["canonical_description"]["state"]
            item["allergen_ids"] = list(food["allergen_ids"])
        else:
            item["food_state"] = "UNKNOWN"
            item["allergen_ids"] = []
        enriched_ingredients.append(item)

    ingredient_complete = len(matched_foods) == len(enriched_ingredients) and bool(
        enriched_ingredients
    )
    energy_qa = energy_consistency(
        totals["energy"], totals["protein"], totals["carbs"], totals["fat"]
    )
    reported = _safe_float(enriched.get("estimated_calories"))
    if totals["energy"] > 0 and reported > 0:
        catalog_delta = abs(totals["energy"] - reported) / totals["energy"]
        catalog_alignment = (
            "PASS" if catalog_delta <= 0.10 else "REVIEW" if catalog_delta <= 0.20 else "FAIL"
        )
    else:
        catalog_delta = None
        catalog_alignment = "NOT_APPLICABLE"

    publishable = ingredient_complete and energy_qa["status"] != "FAIL"
    if not ingredient_complete:
        review_status = "DATA_REVIEW_REQUIRED"
    elif catalog_alignment in {"REVIEW", "FAIL"}:
        review_status = "LEGACY_SERVING_REVIEW_REQUIRED"
    else:
        review_status = "APPROVED"

    source_servings = (enriched.get("normalization") or {}).get("source_servings")
    enriched["ingredients"] = enriched_ingredients
    enriched["serving"] = {
        "definition": (
            "NORMALIZED_PER_SERVING"
            if enriched.get("catalog_status") == "normalized_reference_recipe"
            else "CATALOG_PORTION"
        ),
        "serving_weight_g": round(quantified_weight, 2),
        "weight_basis": "SUM_OF_QUANTIFIED_INGREDIENTS",
        "recipe_total_weight_g": None,
        "number_of_servings": None,
        "source_recipe_servings": source_servings,
        "provenance": {
            "method": "INGREDIENT_WEIGHT_SUM",
            "complete_recipe_weight_known": False,
        },
    }
    enriched["nutrition"] = {
        "method": "RECIPE_CALCULATED",
        "energy_kcal": round(totals["energy"], 2),
        "protein_g": round(totals["protein"], 2),
        "fat_g": round(totals["fat"], 2),
        "carbohydrate_g": round(totals["carbs"], 2),
        "source_ids": ["VIETNAM_FCT"],
        "yield_factor_applied": False,
        "retention_factor_applied": False,
        "limitation": (
            "Cooking yield and nutrient retention are not applied until the "
            "recipe has reviewed cooking-state metadata."
        ),
    }
    enriched["quality"] = {
        "ingredient_match_complete": ingredient_complete,
        "match_quality_counts": {
            quality.value: sum(
                item["match"]["quality"] == quality.value
                for item in enriched_ingredients
            )
            for quality in MatchQuality
        },
        "publishable_for_nutrition_calculation": publishable,
        "review_status": review_status,
        "nutrition_consistency": energy_qa,
        "catalog_energy_alignment": {
            "status": catalog_alignment,
            "catalog_estimated_kcal": round(reported, 2),
            "recipe_calculated_kcal": round(totals["energy"], 2),
            "relative_delta": (
                round(catalog_delta, 6) if catalog_delta is not None else None
            ),
        },
        "policy_version": CANONICAL_POLICY_VERSION,
    }
    enriched["dietary_tags"] = {
        "objective": _dish_objective_tags(
            matched_foods, ingredient_complete=ingredient_complete
        ),
        "heuristic": [],
    }
    enriched["region_metadata"] = resolve_dish_region(str(enriched.get("name", "")))
    enriched["region"] = enriched["region_metadata"]["region"]
    return enriched


def clear_canonical_food_cache() -> None:
    _load_source_registry_cached.cache_clear()
    _load_canonical_food_catalog_cached.cache_clear()
    _canonical_foods_by_name.cache_clear()


__all__ = [
    "ALLERGEN_TAXONOMY_VERSION",
    "AUTO_PUBLISH_MATCH_QUALITIES",
    "CANONICAL_POLICY_VERSION",
    "FOODS_FILE",
    "SOURCE_REGISTRY_FILE",
    "CanonicalFoodError",
    "MatchQuality",
    "clear_canonical_food_cache",
    "derive_allergen_ids",
    "energy_consistency",
    "enrich_dish_quality",
    "load_canonical_food_catalog",
    "load_source_registry",
    "resolve_food_match",
    "resolve_dish_region",
]
