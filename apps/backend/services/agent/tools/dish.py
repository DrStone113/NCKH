"""``suggest_dish`` server-side tool.

Selects a Vietnamese dish whose ``meal_types`` contains the requested
``meal_type`` and whose total calories — after scaling each component's
``serving_grams`` — fall inside ``[0.7 * target_kcal, 1.5 * target_kcal]``
while keeping every ``component.serving_grams ≥ 1``. When ``recent_dish_ids``
is non-empty and another fitting dish exists, the tool prefers a dish whose
``id`` is not in that list.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §6.1 (FoodComponent shape), §9.4 (formal contract).
- Requirements 4.1, 4.3, 4.4, 7.8 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract
--------
``suggest_dish(meal_type, target_kcal, dietary_restrictions=(), recent_dish_ids=()) -> dict``

Returns a JSON-serialisable dish payload::

    {
        "id": int,
        "name": str,
        "meal_types": [str, ...],
        "components": [
            {
                "name": str,
                "serving_grams": int,            # >= 1
                "calories": float,
                "protein": float,
                "carbs": float,
                "fat": float,
            }, ...
        ],
        "total_calories": float,                 # in [0.7*target, 1.5*target]
        "total_protein": float,
        "total_carbs": float,
        "total_fat": float,
    }

Raises ``ValueError`` with one of: ``"INVALID_MEAL_TYPE"``,
``"INVALID_TARGET_KCAL"``, ``"INVALID_DIETARY_RESTRICTIONS"``,
``"NO_DISH_FOUND"`` when inputs are out-of-domain or no dish in the catalog
satisfies all constraints.

The tool is idempotent: identical arguments deterministically produce the
same dish. Selection is total-ordered by ``(|actual_total - target|, id)``.

Note
----
This module only *defines* :data:`TOOL_DESCRIPTOR`. Registration into the
shared :class:`ToolRegistry` happens centrally in task 12.1
(``register_server_tools``). The data files are loaded exactly once at
module import time per Requirement 7.8.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from modules.nutrition.catalog import DishCatalogError, load_dish_catalog
from modules.nutrition.canonical_foods import (
    CanonicalFoodError,
    load_canonical_food_catalog,
    resolve_dish_region,
)
from services.agent.tool_registry import ToolDescriptor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — design.md §9.4 / requirement 4.1, 4.4
# ---------------------------------------------------------------------------

#: Lower / upper bounds on the actual scaled ``total_calories`` relative to
#: ``target_kcal`` (Requirement 4.1).
_KCAL_LOWER_FACTOR = 0.7
_KCAL_UPPER_FACTOR = 1.5

# Không co/giãn một suất ăn vô hạn chỉ để chạm đúng target kcal. Trước đây
# một phần bún 400 g có thể bị kéo thành hơn 1 kg cho mục tiêu 900 kcal.
_MIN_PORTION_SCALE = 0.65
_MAX_PORTION_SCALE = 1.60

#: Allowed values for ``meal_type`` (design.md §6.1, MealTypeLiteral).
_VALID_MEAL_TYPES: frozenset[str] = frozenset(
    {"breakfast", "lunch", "dinner", "snack"}
)

#: Allowed dietary restriction tags (Requirement 4.4).
_VALID_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "vegetarian",
        "vegan",
        "low_carb",
        "high_protein",
        "no_seafood",
        "no_pork",
        "no_beef",
        "no_peanut",
        "no_tree_nut",
        "no_milk",
        "no_egg",
        "no_fish",
        "no_crustacean",
        "no_mollusc",
        "no_soy",
        "no_wheat_gluten",
        "no_sesame",
    }
)

_ALLERGEN_RESTRICTIONS: dict[str, str] = {
    "no_peanut": "PEANUT",
    "no_tree_nut": "TREE_NUT",
    "no_milk": "MILK",
    "no_egg": "EGG",
    "no_fish": "FISH",
    "no_crustacean": "CRUSTACEAN",
    "no_mollusc": "MOLLUSC",
    "no_soy": "SOY",
    "no_wheat_gluten": "WHEAT_GLUTEN",
    "no_sesame": "SESAME",
}

#: ratio thresholds used by ``low_carb`` / ``high_protein`` filters. The
#: design does not pin numeric thresholds, so reasonable nutrition-science
#: defaults are applied: low-carb ≤ 40% of kcal from carbs, high-protein
#: ≥ 25% of kcal from protein.
_LOW_CARB_KCAL_RATIO_MAX = 0.40
_HIGH_PROTEIN_KCAL_RATIO_MIN = 0.25


# ---------------------------------------------------------------------------
# JSON Schema — passed to the LLM via ToolRegistry.schemas()
# ---------------------------------------------------------------------------

_SUGGEST_DISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "meal_type": {
            "type": "string",
            "enum": sorted(_VALID_MEAL_TYPES),
            "description": "Loại bữa ăn cần gợi ý.",
        },
        "target_kcal": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": (
                "Mục tiêu calo cho bữa ăn này. Dish được scale để "
                "total_calories ∈ [0.7 * target_kcal, 1.5 * target_kcal]."
            ),
        },
        "dietary_restrictions": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(_VALID_RESTRICTIONS)},
            "uniqueItems": True,
            "default": [],
            "description": (
                "Các hạn chế ăn uống/dị nguyên canonical; ví dụ vegetarian, "
                "vegan, no_seafood, no_peanut, no_milk, no_egg hoặc no_soy."
            ),
        },
        "recent_dish_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "default": [],
            "description": (
                "Danh sách dish.id đã được gợi ý gần đây; tool ưu tiên dish "
                "có id không thuộc danh sách này nếu tồn tại candidate khác."
            ),
        },
        "exposure_counts": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
            "default": {},
            "description": "So lan dish.id da duoc goi y gan day; chi dung de phat hien exposure, khong bao gio ghi de hard constraint.",
        },
        "query": {
            "type": "string",
            "default": "",
            "description": (
                "Từ khóa tìm kiếm tên món ăn (ví dụ: 'cơm', 'bún', 'phở', "
                "'cháo', 'mì', 'miến', 'salad')."
            ),
        },
        "latitude": {
            "type": "number",
            "description": (
                "Vĩ độ GPS của người dùng (tùy chọn, dùng để gợi ý món ăn "
                "theo vùng miền)."
            ),
        },
        "longitude": {
            "type": "number",
            "description": (
                "Kinh độ GPS của người dùng (tùy chọn, dùng để gợi ý món ăn "
                "theo vùng miền)."
            ),
        },
    },
    "required": ["meal_type", "target_kcal"],
    "additionalProperties": False,
}

_SEARCH_DISH_CATALOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "maxLength": 160,
            "default": "",
            "description": "Tên món hoặc nguyên liệu cần tìm; để trống để duyệt toàn bộ catalog theo trang.",
        },
        "dish_id": {
            "type": "integer",
            "minimum": 1,
            "description": "ID canonical chính xác khi cần đọc một món cụ thể.",
        },
        "meal_type": {
            "type": "string",
            "enum": sorted(_VALID_MEAL_TYPES),
            "description": "Bộ lọc loại bữa, không bắt buộc.",
        },
        "dietary_restrictions": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(_VALID_RESTRICTIONS)},
            "uniqueItems": True,
            "default": [],
        },
        "ingredient_exclusions": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 100},
            "uniqueItems": True,
            "default": [],
        },
        "page": {"type": "integer", "minimum": 1, "default": 1},
        "page_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
        },
        "include_details": {
            "type": "boolean",
            "default": False,
            "description": "Trả nguyên liệu, provenance và quality; tối đa 5 kết quả mỗi trang.",
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Data loading (once at import time per Requirement 7.8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ComponentSpec:
    """Pre-resolved per-ingredient nutrition rates (per gram).

    Storing per-gram rates lets us scale to any integer ``serving_grams``
    in O(1) without re-reading the foods table.
    """

    name: str
    base_grams: int                  # Original grams from vietnamese_dishes.json.
    kcal_per_g: float
    protein_per_g: float
    carbs_per_g: float
    fat_per_g: float
    food_id: str
    food_state: str
    allergen_ids: tuple[str, ...]
    source_id: str
    source_record_id: int | None
    match_quality: str


@dataclass(frozen=True, slots=True)
class _DishRecord:
    """A dish prepared at module load: components + base totals + flags."""

    id: int
    name: str
    meal_types: frozenset[str]
    components: tuple[_ComponentSpec, ...]
    base_total_calories: float
    base_total_protein: float
    base_total_carbs: float
    base_total_fat: float
    contains_seafood: bool
    contains_land_meat: bool
    contains_egg: bool
    contains_dairy: bool
    allergen_ids: frozenset[str]
    objective_tags: frozenset[str]
    catalog_status: str | None
    provenance: dict[str, Any] | None
    quality: dict[str, Any]
    serving: dict[str, Any]
    source_catalog_calories: float


# Computed at module import.
_DISHES: tuple[_DishRecord, ...] = ()


def _safe_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _build_component(
    ingredient: dict[str, Any],
    foods_by_name: dict[str, dict[str, Any]],
) -> _ComponentSpec | None:
    """Resolve nutrition for one ingredient, or return ``None`` if missing."""
    name = ingredient.get("name")
    grams = ingredient.get("grams")
    if not isinstance(name, str) or not isinstance(grams, (int, float)):
        return None
    food = foods_by_name.get(name)
    if food is None:
        return None
    base_grams = max(int(round(float(grams))), 1)
    return _ComponentSpec(
        name=name,
        base_grams=base_grams,
        kcal_per_g=_safe_float(food.get("energy_kcal")) / 100.0,
        protein_per_g=_safe_float(food.get("protein")) / 100.0,
        carbs_per_g=_safe_float(food.get("carbohydrates")) / 100.0,
        fat_per_g=_safe_float(food.get("fat")) / 100.0,
        food_id=str(ingredient.get("food_id") or food.get("food_id") or ""),
        food_state=str(ingredient.get("food_state") or "UNKNOWN"),
        allergen_ids=tuple(sorted(ingredient.get("allergen_ids") or [])),
        source_id=str((ingredient.get("match") or {}).get("source_id") or ""),
        source_record_id=(ingredient.get("match") or {}).get("source_record_id"),
        match_quality=str(
            (ingredient.get("match") or {}).get("quality") or "UNRESOLVED"
        ),
    )


def _build_dish_record(
    dish: dict[str, Any],
    foods_by_name: dict[str, dict[str, Any]],
) -> _DishRecord | None:
    """Resolve a single dish into a :class:`_DishRecord`, or skip on errors."""
    try:
        dish_id = int(dish["id"])
        name = str(dish["name"])
        raw_meal_types = dish.get("meal_types") or []
        meal_types = frozenset(
            mt for mt in raw_meal_types if mt in _VALID_MEAL_TYPES
        )
        if not meal_types:
            return None
        ingredients = dish.get("ingredients") or []
        if not ingredients:
            return None

        components: list[_ComponentSpec] = []
        for ing in ingredients:
            spec = _build_component(ing, foods_by_name)
            if spec is None:
                # Missing nutrition data → skip the dish entirely so we never
                # return inconsistent totals.
                return None
            components.append(spec)

        base_kcal = sum(c.kcal_per_g * c.base_grams for c in components)
        base_protein = sum(c.protein_per_g * c.base_grams for c in components)
        base_carbs = sum(c.carbs_per_g * c.base_grams for c in components)
        base_fat = sum(c.fat_per_g * c.base_grams for c in components)
        if base_kcal <= 0:
            # Cannot scale a dish with zero energy.
            return None
        quality = dict(dish.get("quality") or {})
        if quality.get("publishable_for_nutrition_calculation") is False:
            return None

        # Never force ingredient energy to match a legacy dish-level estimate.
        # Nutrition is calculated from canonical food records; disagreement
        # remains visible in quality.catalog_energy_alignment for review.
        objective_tags = frozenset(
            (dish.get("dietary_tags") or {}).get("objective") or []
        )
        allergen_ids = frozenset(
            allergen
            for component in components
            for allergen in component.allergen_ids
        )

        return _DishRecord(
            id=dish_id,
            name=name,
            meal_types=meal_types,
            components=tuple(components),
            base_total_calories=base_kcal,
            base_total_protein=base_protein,
            base_total_carbs=base_carbs,
            base_total_fat=base_fat,
            contains_seafood="contains_seafood" in objective_tags,
            contains_land_meat="contains_land_meat" in objective_tags,
            contains_egg="contains_egg" in objective_tags,
            contains_dairy="contains_dairy" in objective_tags,
            allergen_ids=allergen_ids,
            objective_tags=objective_tags,
            catalog_status=(
                str(dish["catalog_status"])
                if dish.get("catalog_status")
                else None
            ),
            provenance=(
                dict(dish["provenance"])
                if isinstance(dish.get("provenance"), dict)
                else None
            ),
            quality=quality,
            serving=dict(dish.get("serving") or {}),
            source_catalog_calories=_safe_float(dish.get("estimated_calories")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Skipping malformed dish entry: %s (%s)", dish, exc)
        return None


def _load_dishes() -> tuple[_DishRecord, ...]:
    try:
        foods_raw = load_canonical_food_catalog()
    except CanonicalFoodError as exc:
        logger.error("Unable to load canonical food catalog: %s", exc)
        return ()
    foods_by_name = {
        str(f["name"]): f for f in foods_raw if isinstance(f, dict) and "name" in f
    }

    try:
        dishes_raw = load_dish_catalog()
    except DishCatalogError as exc:
        logger.error("Unable to load merged dish catalog: %s", exc)
        return ()

    records: list[_DishRecord] = []
    for entry in dishes_raw:
        if not isinstance(entry, dict):
            continue
        rec = _build_dish_record(entry, foods_by_name)
        if rec is not None:
            records.append(rec)

    # Sort by id for stable iteration; selection ties also use id ascending.
    records.sort(key=lambda r: r.id)
    logger.info(
        "suggest_dish: loaded %d merged dishes", len(records)
    )
    return tuple(records)


# Eagerly load at import time. ``_DISHES`` is treated as immutable thereafter.
_DISHES = _load_dishes()


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _passes_dietary_restrictions(
    dish: _DishRecord, restrictions: frozenset[str]
) -> bool:
    """Return True if ``dish`` satisfies every restriction in ``restrictions``.

    Definitions:
      - ``no_seafood``  : no ingredient in ``_SEAFOOD_INGREDIENT_NAMES``.
      - ``vegetarian``  : no land meat AND no seafood.
      - ``vegan``       : vegetarian AND no eggs AND no dairy.
      - ``low_carb``    : carbs contribute ≤ 40% of base kcal
        (``4 * total_carbs / total_calories ≤ 0.40``).
      - ``high_protein``: protein contributes ≥ 25% of base kcal
        (``4 * total_protein / total_calories ≥ 0.25``).
    """
    if any(
        allergen_id in dish.allergen_ids
        for restriction, allergen_id in _ALLERGEN_RESTRICTIONS.items()
        if restriction in restrictions
    ):
        return False
    if "no_seafood" in restrictions and dish.contains_seafood:
        return False
    if "no_pork" in restrictions and "contains_pork" in dish.objective_tags:
        return False
    if "no_beef" in restrictions and "contains_beef" in dish.objective_tags:
        return False
    if "vegetarian" in restrictions and (
        dish.contains_land_meat or dish.contains_seafood
    ):
        return False
    if "vegan" in restrictions and (
        dish.contains_land_meat
        or dish.contains_seafood
        or dish.contains_egg
        or dish.contains_dairy
    ):
        return False
    if "low_carb" in restrictions:
        carb_kcal_ratio = (4.0 * dish.base_total_carbs) / dish.base_total_calories
        if carb_kcal_ratio > _LOW_CARB_KCAL_RATIO_MAX:
            return False
    if "high_protein" in restrictions:
        protein_kcal_ratio = (
            4.0 * dish.base_total_protein
        ) / dish.base_total_calories
        if protein_kcal_ratio < _HIGH_PROTEIN_KCAL_RATIO_MIN:
            return False
    return True


def _passes_ingredient_exclusions(dish: _DishRecord, exclusions: frozenset[str]) -> bool:
    """Reject an explicitly excluded ingredient or dish name, case-insensitively."""

    if not exclusions:
        return True
    searchable = " ".join(_remove_accents(value.casefold()) for value in (dish.name, *(component.name for component in dish.components)))
    return not any(exclusion in searchable for exclusion in exclusions)


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ScaledDish:
    """Result of scaling a :class:`_DishRecord` to a target kcal."""

    record: _DishRecord
    components: tuple[dict[str, Any], ...]
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float
    scale_factor: float


def _scale_dish(
    dish: _DishRecord, target_kcal: float
) -> _ScaledDish | None:
    """Return a scaled variant of ``dish`` honouring the calorie window
    and minimum-grams constraint, or ``None`` if it cannot fit.

    Algorithm:
      1. ``raw_scale = target_kcal / dish.base_total_calories``.
      2. Clamp the portion to ``[0.65, 1.60]`` and lift ``scale`` if needed
         so the smallest component still rounds to ≥ 1g.
      3. Scale every component's ``serving_grams`` by ``scale`` and round
         to the nearest integer (floor to 1).
      4. Recompute calories/macros from per-gram rates × actual grams.
      5. Reject if the recomputed ``total_calories`` falls outside
         ``[0.7*target, 1.5*target]``.
    """
    if dish.base_total_calories <= 0:
        return None
    raw_scale = target_kcal / dish.base_total_calories
    min_base_g = min(c.base_grams for c in dish.components)
    # Smallest scale that keeps every component ≥ 1g after rounding to nearest
    # integer. ``round`` rounds half-to-even; using ``> 0.5 / min_base_g``
    # would be marginally tighter but the conservative ``1/min_base_g``
    # guarantees ``round(scale * min_base_g) ≥ 1`` for any rounding mode.
    min_safe_scale = 1.0 / float(min_base_g)
    scale = min(
        max(raw_scale, min_safe_scale, _MIN_PORTION_SCALE),
        _MAX_PORTION_SCALE,
    )

    components_out: list[dict[str, Any]] = []
    total_kcal = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0
    for c in dish.components:
        scaled_g = max(1, int(round(c.base_grams * scale)))
        kcal_i = c.kcal_per_g * scaled_g
        protein_i = c.protein_per_g * scaled_g
        carbs_i = c.carbs_per_g * scaled_g
        fat_i = c.fat_per_g * scaled_g
        components_out.append(
            {
                "name": c.name,
                "food_id": c.food_id,
                "food_state": c.food_state,
                "allergen_ids": list(c.allergen_ids),
                "source_id": c.source_id,
                "source_record_id": c.source_record_id,
                "match_quality": c.match_quality,
                "serving_grams": scaled_g,
                "calories": round(kcal_i, 2),
                "protein": round(protein_i, 2),
                "carbs": round(carbs_i, 2),
                "fat": round(fat_i, 2),
            }
        )
        total_kcal += kcal_i
        total_protein += protein_i
        total_carbs += carbs_i
        total_fat += fat_i

    lower = _KCAL_LOWER_FACTOR * target_kcal
    upper = _KCAL_UPPER_FACTOR * target_kcal
    if not (lower <= total_kcal <= upper):
        return None

    return _ScaledDish(
        record=dish,
        components=tuple(components_out),
        total_calories=round(total_kcal, 2),
        total_protein=round(total_protein, 2),
        total_carbs=round(total_carbs, 2),
        total_fat=round(total_fat, 2),
        scale_factor=round(scale, 4),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_restrictions(
    dietary_restrictions: Iterable[str] | None,
) -> frozenset[str]:
    if dietary_restrictions is None:
        return frozenset()
    if isinstance(dietary_restrictions, (str, bytes)):
        # A bare string is almost certainly a caller mistake.
        raise ValueError("INVALID_DIETARY_RESTRICTIONS")
    try:
        items = frozenset(dietary_restrictions)
    except TypeError as exc:
        raise ValueError("INVALID_DIETARY_RESTRICTIONS") from exc
    if not items.issubset(_VALID_RESTRICTIONS):
        raise ValueError("INVALID_DIETARY_RESTRICTIONS")
    return items


def _normalize_recent_ids(
    recent_dish_ids: Iterable[int] | None,
) -> frozenset[int]:
    if recent_dish_ids is None:
        return frozenset()
    if isinstance(recent_dish_ids, (str, bytes)):
        raise ValueError("INVALID_RECENT_DISH_IDS")
    try:
        return frozenset(int(x) for x in recent_dish_ids)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_RECENT_DISH_IDS") from exc


def _normalize_exposure_counts(value: Any) -> dict[int, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("INVALID_EXPOSURE_COUNTS")
    counts: dict[int, int] = {}
    for raw_id, raw_count in value.items():
        try:
            dish_id = int(raw_id)
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_EXPOSURE_COUNTS") from exc
        if dish_id < 0 or count < 0:
            raise ValueError("INVALID_EXPOSURE_COUNTS")
        counts[dish_id] = count
    return counts


def _remove_accents(text: str) -> str:
    accents_map = {
        'a': 'áàảãạăắằẳẵặâấầẩẫậ',
        'A': 'ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬ',
        'd': 'đ',
        'D': 'Đ',
        'e': 'éèẻẽẹêếềểễệ',
        'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
        'i': 'íìỉĩị',
        'I': 'ÍÌỈĨỊ',
        'o': 'óòỏõọôốồổỗộơớờởỡợ',
        'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
        'u': 'úùủũụưứừửữự',
        'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
        'y': 'ýỳỷỹỵ',
        'Y': 'ÝÝỲỶỸỴ'
    }
    res = list(text)
    for i, char in enumerate(res):
        for rep, chars in accents_map.items():
            if char in chars:
                res[i] = rep
                break
    return "".join(res)


def _get_dish_region_metadata(dish_name: str) -> dict[str, Any]:
    return resolve_dish_region(dish_name)


def _get_dish_region(dish_name: str) -> str:
    """Compatibility helper backed only by curated region metadata."""

    return str(_get_dish_region_metadata(dish_name)["region"])


def _get_region_from_gps(lat: float, lng: float) -> str | None:
    if not (8.0 <= lat <= 24.0 and 100.0 <= lng <= 110.0):
        return None
    if lat >= 20.0:
        return "North"
    elif lat >= 15.0:
        return "Central"
    else:
        return "South"


def suggest_dish(
    meal_type: str,
    target_kcal: float,
    dietary_restrictions: Sequence[str] | Iterable[str] = (),
    ingredient_exclusions: Sequence[str] | Iterable[str] = (),
    recent_dish_ids: Sequence[int] | Iterable[int] = (),
    exposure_counts: dict[str, int] | None = None,
    query: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Pick a Vietnamese dish for ``meal_type`` near ``target_kcal``.

    Parameters
    ----------
    meal_type:
        One of ``"breakfast"``, ``"lunch"``, ``"dinner"``, ``"snack"``.
    target_kcal:
        Target calories for the dish; must be strictly positive.
    dietary_restrictions:
        Optional subset of
        Canonical dietary/allergen restrictions listed in the tool schema.
    recent_dish_ids:
        Optional iterable of dish ids recently chosen — the tool prefers a
        dish whose ``id`` is not in this set whenever another fitting
        candidate exists.
    query:
        Optional search query or keyword to match dish names.
    latitude:
        Optional user latitude coordinate for regional suggestions.
    longitude:
        Optional user longitude coordinate for regional suggestions.

    Returns
    -------
    dict
        See the module docstring for the payload shape.

    Raises
    ------
    ValueError
        ``"INVALID_MEAL_TYPE"``, ``"INVALID_TARGET_KCAL"``,
        ``"INVALID_DIETARY_RESTRICTIONS"``, ``"INVALID_RECENT_DISH_IDS"``,
        or ``"NO_DISH_FOUND"``.
    """
    if meal_type not in _VALID_MEAL_TYPES:
        raise ValueError("INVALID_MEAL_TYPE")
    try:
        target_kcal_f = float(target_kcal)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_TARGET_KCAL") from exc
    # ``NaN`` and non-positive values are rejected; ``NaN != NaN`` is the
    # standard finite/positive guard.
    if not (target_kcal_f > 0) or target_kcal_f != target_kcal_f:
        raise ValueError("INVALID_TARGET_KCAL")

    restrictions = _normalize_restrictions(dietary_restrictions)
    exclusions = frozenset(
        _remove_accents(value.casefold())
        for value in ingredient_exclusions
        if isinstance(value, str) and value.strip()
    )
    recent_ids = _normalize_recent_ids(recent_dish_ids)
    exposures = _normalize_exposure_counts(exposure_counts)

    clean_query = _remove_accents(query.strip().lower()) if isinstance(query, str) else ""

    user_region = None
    if latitude is not None and longitude is not None:
        try:
            user_region = _get_region_from_gps(float(latitude), float(longitude))
        except (ValueError, TypeError):
            pass

    # Filter and scale every catalog entry that is meal_type / restriction
    # compatible. We separate "preferred" (id ∉ recent) from "fallback".
    preferred: list[_ScaledDish] = []
    fallback: list[_ScaledDish] = []
    for dish in _DISHES:
        if meal_type not in dish.meal_types:
            continue
        if not _passes_dietary_restrictions(dish, restrictions):
            continue
        if not _passes_ingredient_exclusions(dish, exclusions):
            continue
        if clean_query and clean_query not in _remove_accents(dish.name.lower()):
            continue

        # Region filter: only apply if the user did NOT type an explicit query
        if user_region and not clean_query:
            dish_region = _get_dish_region(dish.name)
            if dish_region not in {"Unknown", "National", user_region}:
                continue

        scaled = _scale_dish(dish, target_kcal_f)
        if scaled is None:
            continue
        if dish.id in recent_ids:
            fallback.append(scaled)
        else:
            preferred.append(scaled)

    candidates = preferred or fallback
    if not candidates:
        raise ValueError("NO_DISH_FOUND")

    # Ưu tiên món cần co/giãn khẩu phần ít nhất. Nếu chỉ xếp theo kcal sau
    # scale thì gần như mọi món đều bằng target và kết quả vô tình chọn theo id.
    best = min(
        candidates,
        key=lambda s: (
            (
                0
                if not user_region
                or clean_query
                or _get_dish_region(s.record.name) == user_region
                else 1
                if _get_dish_region(s.record.name) == "National"
                else 2
            ),
            # Exposure is a soft penalty after hard filters and region
            # applicability, but before deterministic tie-breaks. A heavily
            # repeated dish must lose when another nutritionally valid option
            # exists.
            min(5.0, exposures.get(s.record.id, 0) * 0.05),
            abs(s.scale_factor - 1.0),
            abs(s.total_calories - target_kcal_f),
            exposures.get(s.record.id, 0),
            s.record.id,
        ),
    )
    rec = best.record
    result: dict[str, Any] = {
        "id": rec.id,
        "name": rec.name,
        "meal_types": sorted(rec.meal_types),
        "components": [dict(c) for c in best.components],
        "total_calories": best.total_calories,
        "total_protein": best.total_protein,
        "total_carbs": best.total_carbs,
        "total_fat": best.total_fat,
        "catalog_calories": round(rec.source_catalog_calories, 2),
        "recipe_calculated_calories": round(rec.base_total_calories, 2),
        "serving_scale": best.scale_factor,
        "region": _get_dish_region(rec.name),
        "region_metadata": _get_dish_region_metadata(rec.name),
        "allergen_ids": sorted(rec.allergen_ids),
        "dietary_tags": {
            "objective": sorted(rec.objective_tags),
            "heuristic": [],
        },
        "quality": dict(rec.quality),
        "serving": dict(rec.serving),
        "nutrition_method": "RECIPE_CALCULATED_FROM_CANONICAL_INGREDIENTS",
    }
    if rec.catalog_status:
        result["catalog_status"] = rec.catalog_status
    if rec.provenance:
        result["provenance"] = dict(rec.provenance)
    return result


def _catalog_page(page: int, page_size: int, *, include_details: bool) -> tuple[int, int]:
    if (
        isinstance(page, bool)
        or isinstance(page_size, bool)
        or not isinstance(page, int)
        or not isinstance(page_size, int)
        or page < 1
        or page_size < 1
        or page_size > 20
    ):
        raise ValueError("INVALID_CATALOG_PAGE")
    if include_details and page_size > 5:
        raise ValueError("DETAIL_PAGE_TOO_LARGE")
    start = (page - 1) * page_size
    return start, start + page_size


def _dish_search_rank(dish: _DishRecord, query: str) -> int | None:
    if not query:
        return 4
    name = _remove_accents(dish.name.casefold())
    ingredients = " ".join(
        _remove_accents(component.name.casefold()) for component in dish.components
    )
    if name == query:
        return 0
    if name.startswith(query):
        return 1
    if query in name:
        return 2
    searchable = f"{name} {ingredients}"
    if all(token in searchable for token in query.split()):
        return 3
    return None


def _catalog_dish_payload(
    record: _DishRecord, *, include_details: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dish_id": record.id,
        "name": record.name,
        "meal_types": sorted(record.meal_types),
        "nutrition": {
            "method": "RECIPE_CALCULATED_FROM_CANONICAL_INGREDIENTS",
            "energy_kcal": round(record.base_total_calories, 2),
            "protein_g": round(record.base_total_protein, 2),
            "carbohydrate_g": round(record.base_total_carbs, 2),
            "fat_g": round(record.base_total_fat, 2),
        },
        "serving": dict(record.serving),
        "ingredient_names": [component.name for component in record.components],
        "allergen_ids": sorted(record.allergen_ids),
        "dietary_tags": sorted(record.objective_tags),
        "recommendation_eligible": True,
    }
    if include_details:
        payload["components"] = [
            {
                "name": component.name,
                "food_id": component.food_id,
                "food_state": component.food_state,
                "serving_grams": component.base_grams,
                "calories": round(component.kcal_per_g * component.base_grams, 2),
                "protein": round(component.protein_per_g * component.base_grams, 2),
                "carbs": round(component.carbs_per_g * component.base_grams, 2),
                "fat": round(component.fat_per_g * component.base_grams, 2),
                "allergen_ids": list(component.allergen_ids),
                "source_id": component.source_id,
                "source_record_id": component.source_record_id,
                "match_quality": component.match_quality,
            }
            for component in record.components
        ]
        payload["quality"] = dict(record.quality)
        payload["provenance"] = (
            dict(record.provenance) if record.provenance is not None else None
        )
        # This catalog owns ingredient amounts and recalculated nutrients, but
        # it does not own cooking prose. Expose that absence explicitly so the
        # model cannot silently invent steps from the ingredient list.
        payload["instructions"] = []
        payload["instruction_status"] = "UNAVAILABLE_IN_CANONICAL_CATALOG"
    return payload


def search_dish_catalog(
    query: str = "",
    dish_id: int | None = None,
    meal_type: str | None = None,
    dietary_restrictions: Sequence[str] | Iterable[str] = (),
    ingredient_exclusions: Sequence[str] | Iterable[str] = (),
    page: int = 1,
    page_size: int = 5,
    include_details: bool = False,
) -> dict[str, Any]:
    """Search every live merged dish record, then paginate the matched rows.

    This is a read-only discovery surface. It never promotes staging recipes
    and never replaces :func:`suggest_dish` as the safety-checked
    recommendation path.
    """

    if not isinstance(query, str) or len(query) > 160:
        raise ValueError("INVALID_CATALOG_QUERY")
    if dish_id is not None and (
        isinstance(dish_id, bool) or not isinstance(dish_id, int) or dish_id < 1
    ):
        raise ValueError("INVALID_DISH_ID")
    if meal_type is not None and meal_type not in _VALID_MEAL_TYPES:
        raise ValueError("INVALID_MEAL_TYPE")
    if isinstance(ingredient_exclusions, (str, bytes)):
        raise ValueError("INVALID_INGREDIENT_EXCLUSIONS")
    try:
        exclusions = frozenset(
            _remove_accents(value.strip().casefold())
            for value in ingredient_exclusions
            if isinstance(value, str) and value.strip()
        )
    except TypeError as exc:
        raise ValueError("INVALID_INGREDIENT_EXCLUSIONS") from exc
    restrictions = _normalize_restrictions(dietary_restrictions)
    start, end = _catalog_page(page, page_size, include_details=include_details)
    clean_query = _remove_accents(query.strip().casefold())

    matches: list[tuple[int, _DishRecord]] = []
    for record in _DISHES:
        if dish_id is not None and record.id != dish_id:
            continue
        if meal_type is not None and meal_type not in record.meal_types:
            continue
        if not _passes_dietary_restrictions(record, restrictions):
            continue
        if not _passes_ingredient_exclusions(record, exclusions):
            continue
        rank = _dish_search_rank(record, clean_query)
        if rank is not None:
            matches.append((rank, record))
    matches.sort(key=lambda item: (item[0], item[1].id))
    page_rows = matches[start:end]
    return {
        "catalog": "LIVE_MERGED_DISH_CATALOG",
        "catalog_size": len(_DISHES),
        "scanned_count": len(_DISHES),
        "matched_count": len(matches),
        "page": page,
        "page_size": page_size,
        "has_more": end < len(matches),
        "next_page": page + 1 if end < len(matches) else None,
        "results": [
            _catalog_dish_payload(record, include_details=include_details)
            for _, record in page_rows
        ],
    }


# ---------------------------------------------------------------------------
# Descriptor — consumed by ``register_server_tools`` (task 12.1)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="suggest_dish",
    description=(
        "Gợi ý một món Việt phù hợp với meal_type và mục tiêu calo, "
        "scale serving_grams sao cho total_calories ∈ "
        "[0.7 * target_kcal, 1.5 * target_kcal] và mọi component "
        "có serving_grams ≥ 1. Hỗ trợ dietary_restrictions và "
        "recent_dish_ids để đa dạng hoá lựa chọn."
    ),
    parameters_schema=_SUGGEST_DISH_SCHEMA,
    side="server",
    fn=suggest_dish,
    idempotent=True,
)

SEARCH_CATALOG_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="search_dish_catalog",
    description=(
        "Quét toàn bộ catalog món ăn live rồi tìm theo tên món, nguyên liệu, ID, "
        "loại bữa và ràng buộc ăn uống. Kết quả được phân trang; dùng "
        "include_details=true với tối đa 5 kết quả để lấy nguyên liệu và dinh dưỡng "
        "tính từ bảng thành phần canonical. Đây là tra cứu, không phải khuyến nghị."
    ),
    parameters_schema=_SEARCH_DISH_CATALOG_SCHEMA,
    side="server",
    fn=search_dish_catalog,
    idempotent=True,
)


__all__ = [
    "SEARCH_CATALOG_DESCRIPTOR",
    "TOOL_DESCRIPTOR",
    "search_dish_catalog",
    "suggest_dish",
]
