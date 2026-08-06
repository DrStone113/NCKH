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

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from services.agent.tool_registry import ToolDescriptor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — design.md §9.4 / requirement 4.1, 4.4
# ---------------------------------------------------------------------------

#: Lower / upper bounds on the actual scaled ``total_calories`` relative to
#: ``target_kcal`` (Requirement 4.1).
_KCAL_LOWER_FACTOR = 0.7
_KCAL_UPPER_FACTOR = 1.5

#: Allowed values for ``meal_type`` (design.md §6.1, MealTypeLiteral).
_VALID_MEAL_TYPES: frozenset[str] = frozenset(
    {"breakfast", "lunch", "dinner", "snack"}
)

#: Allowed dietary restriction tags (Requirement 4.4).
_VALID_RESTRICTIONS: frozenset[str] = frozenset(
    {"vegetarian", "vegan", "low_carb", "high_protein", "no_seafood"}
)

# --- Ingredient-name based dietary classification ---------------------------
#
# The bundled ``vietnamese_dishes.json`` does not tag dishes with explicit
# dietary attributes, so we classify by ingredient name. Lists below are
# anchored to the exact strings used in
# ``backend/data/vietnamese_dishes.json`` and ``vietnamese_foods.json``.

_SEAFOOD_INGREDIENT_NAMES: frozenset[str] = frozenset({
    "Cua bể",
    "Cá hồi",
    "Cá ngừ",
    "Cá rô phi",
    "Cá thu",
    "Mực tươi",
    "Tôm biển",
})

_LAND_MEAT_INGREDIENT_NAMES: frozenset[str] = frozenset({
    "Chả lợn",
    "Giò lụa",
    "Giò thủ lợn",
    "Lòng lợn (ruột non)",
    "Sườn lợn",
    "Thịt bò loại I",
    "Thịt gà ta",
    "Thịt lợn nạc",
    "Thịt lợn nửa nạc, nửa mỡ",
    "Thịt vịt",
    "Xúc xích",
})

_EGG_INGREDIENT_NAMES: frozenset[str] = frozenset({
    "Trứng gà",
    "Trứng vịt",
})

_DAIRY_INGREDIENT_NAMES: frozenset[str] = frozenset({
    "Sữa bò tươi",
    "Sữa chua (từ sữa bò)",
})

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
                "Tập con của "
                "{vegetarian, vegan, low_carb, high_protein, no_seafood}."
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
        "query": {
            "type": "string",
            "default": "",
            "description": "Từ khóa tìm kiếm tên món ăn (ví dụ: 'cơm', 'bún', 'phở', 'cháo', 'mì', 'miến', 'salad').",
        },
    },
    "required": ["meal_type", "target_kcal"],
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


# Computed at module import.
_DISHES: tuple[_DishRecord, ...] = ()


def _data_dir() -> Path:
    # backend/services/agent/tools/dish.py → backend/data
    return Path(__file__).resolve().parent.parent.parent.parent / "data"


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
    base_grams = max(int(grams), 1)
    return _ComponentSpec(
        name=name,
        base_grams=base_grams,
        kcal_per_g=_safe_float(food.get("energy_kcal")) / 100.0,
        protein_per_g=_safe_float(food.get("protein")) / 100.0,
        carbs_per_g=_safe_float(food.get("carbohydrates")) / 100.0,
        fat_per_g=_safe_float(food.get("fat")) / 100.0,
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

        ingredient_name_set = {c.name for c in components}
        base_kcal = sum(c.kcal_per_g * c.base_grams for c in components)
        base_protein = sum(c.protein_per_g * c.base_grams for c in components)
        base_carbs = sum(c.carbs_per_g * c.base_grams for c in components)
        base_fat = sum(c.fat_per_g * c.base_grams for c in components)
        if base_kcal <= 0:
            # Cannot scale a dish with zero energy.
            return None

        return _DishRecord(
            id=dish_id,
            name=name,
            meal_types=meal_types,
            components=tuple(components),
            base_total_calories=base_kcal,
            base_total_protein=base_protein,
            base_total_carbs=base_carbs,
            base_total_fat=base_fat,
            contains_seafood=bool(
                ingredient_name_set & _SEAFOOD_INGREDIENT_NAMES
            ),
            contains_land_meat=bool(
                ingredient_name_set & _LAND_MEAT_INGREDIENT_NAMES
            ),
            contains_egg=bool(
                ingredient_name_set & _EGG_INGREDIENT_NAMES
            ),
            contains_dairy=bool(
                ingredient_name_set & _DAIRY_INGREDIENT_NAMES
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Skipping malformed dish entry: %s (%s)", dish, exc)
        return None


def _load_dishes() -> tuple[_DishRecord, ...]:
    base_dir = _data_dir()
    dishes_path = base_dir / "vietnamese_dishes.json"
    foods_path = base_dir / "vietnamese_foods.json"

    try:
        with foods_path.open(encoding="utf-8") as fh:
            foods_raw = json.load(fh)
    except FileNotFoundError:
        logger.error("vietnamese_foods.json not found at %s", foods_path)
        return ()
    foods_by_name = {
        str(f["name"]): f for f in foods_raw if isinstance(f, dict) and "name" in f
    }

    try:
        with dishes_path.open(encoding="utf-8") as fh:
            dishes_raw = json.load(fh)
    except FileNotFoundError:
        logger.error("vietnamese_dishes.json not found at %s", dishes_path)
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
        "suggest_dish: loaded %d dishes from %s", len(records), dishes_path.name
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
    if "no_seafood" in restrictions and dish.contains_seafood:
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


def _scale_dish(
    dish: _DishRecord, target_kcal: float
) -> _ScaledDish | None:
    """Return a scaled variant of ``dish`` honouring the calorie window
    and minimum-grams constraint, or ``None`` if it cannot fit.

    Algorithm:
      1. ``raw_scale = target_kcal / dish.base_total_calories``.
      2. Lift ``scale`` so the smallest component still rounds to ≥ 1g.
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
    scale = max(raw_scale, min_safe_scale)

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


def suggest_dish(
    meal_type: str,
    target_kcal: float,
    dietary_restrictions: Sequence[str] | Iterable[str] = (),
    recent_dish_ids: Sequence[int] | Iterable[int] = (),
    query: str = "",
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
        ``{"vegetarian", "vegan", "low_carb", "high_protein", "no_seafood"}``.
    recent_dish_ids:
        Optional iterable of dish ids recently chosen — the tool prefers a
        dish whose ``id`` is not in this set whenever another fitting
        candidate exists.
    query:
        Optional search query or keyword to match dish names.

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
    recent_ids = _normalize_recent_ids(recent_dish_ids)

    clean_query = _remove_accents(query.strip().lower()) if isinstance(query, str) else ""

    # Filter and scale every catalog entry that is meal_type / restriction
    # compatible. We separate "preferred" (id ∉ recent) from "fallback".
    preferred: list[_ScaledDish] = []
    fallback: list[_ScaledDish] = []
    for dish in _DISHES:
        if meal_type not in dish.meal_types:
            continue
        if not _passes_dietary_restrictions(dish, restrictions):
            continue
        if clean_query and clean_query not in _remove_accents(dish.name.lower()):
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

    # Deterministic pick: minimise distance to target, tiebreak by id ASC.
    best = min(
        candidates,
        key=lambda s: (abs(s.total_calories - target_kcal_f), s.record.id),
    )
    rec = best.record
    return {
        "id": rec.id,
        "name": rec.name,
        "meal_types": sorted(rec.meal_types),
        "components": [dict(c) for c in best.components],
        "total_calories": best.total_calories,
        "total_protein": best.total_protein,
        "total_carbs": best.total_carbs,
        "total_fat": best.total_fat,
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


__all__ = [
    "TOOL_DESCRIPTOR",
    "suggest_dish",
]
