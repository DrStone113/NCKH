"""Load the live Vietnamese dish catalog with sourced quality overlays.

The legacy ``vietnamese_dishes.json`` remains unchanged because it is an
approved input of the frozen research corpus.  Runtime consumers use the
versioned overlay to replace low-quality recipes and append newly verified
complete meals without silently changing that experiment's source bytes.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.nutrition.canonical_foods import (
    CanonicalFoodError,
    clear_canonical_food_cache,
    enrich_dish_quality,
)


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BASE_DISHES_FILE = DATA_DIR / "vietnamese_dishes.json"
CURATED_DISHES_FILE = DATA_DIR / "vietnamese_dishes_curated_v1.json"
REFERENCE_DISHES_FILE = DATA_DIR / "vietnamese_dishes_reference_v1.json"


class DishCatalogError(ValueError):
    """Raised when catalog sources cannot be merged without ambiguity."""


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DishCatalogError(f"INVALID_DISH_CATALOG:{path.name}") from exc


def _dish_id(item: dict[str, Any], *, source: str) -> int:
    try:
        return int(item["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DishCatalogError(f"INVALID_DISH_ID:{source}") from exc


@lru_cache(maxsize=1)
def _load_dish_catalog_cached() -> tuple[dict[str, Any], ...]:
    base_raw = _read_json(BASE_DISHES_FILE)
    overlay_raw = _read_json(CURATED_DISHES_FILE)
    reference_raw = _read_json(REFERENCE_DISHES_FILE)
    if (
        not isinstance(base_raw, list)
        or not isinstance(overlay_raw, dict)
        or not isinstance(reference_raw, dict)
    ):
        raise DishCatalogError("INVALID_DISH_CATALOG_SHAPE")

    dishes_by_id: dict[int, dict[str, Any]] = {}
    for item in base_raw:
        if not isinstance(item, dict):
            raise DishCatalogError("INVALID_BASE_DISH")
        dish_id = _dish_id(item, source=BASE_DISHES_FILE.name)
        if dish_id in dishes_by_id:
            raise DishCatalogError(f"DUPLICATE_DISH_ID:{dish_id}")
        dishes_by_id[dish_id] = deepcopy(item)

    overrides = overlay_raw.get("overrides", [])
    curated_additions = overlay_raw.get("additions", [])
    reference_additions = reference_raw.get("additions", [])
    if (
        not isinstance(overrides, list)
        or not isinstance(curated_additions, list)
        or not isinstance(reference_additions, list)
    ):
        raise DishCatalogError("INVALID_DISH_OVERLAY_SHAPE")

    for item in overrides:
        if not isinstance(item, dict):
            raise DishCatalogError("INVALID_DISH_OVERRIDE")
        dish_id = _dish_id(item, source=CURATED_DISHES_FILE.name)
        if dish_id not in dishes_by_id:
            raise DishCatalogError(f"UNKNOWN_DISH_OVERRIDE:{dish_id}")
        dishes_by_id[dish_id] = {**dishes_by_id[dish_id], **deepcopy(item)}

    for source_path, additions in (
        (CURATED_DISHES_FILE, curated_additions),
        (REFERENCE_DISHES_FILE, reference_additions),
    ):
        for item in additions:
            if not isinstance(item, dict):
                raise DishCatalogError("INVALID_DISH_ADDITION")
            dish_id = _dish_id(item, source=source_path.name)
            if dish_id in dishes_by_id:
                raise DishCatalogError(f"DUPLICATE_DISH_ADDITION:{dish_id}")
            dishes_by_id[dish_id] = deepcopy(item)

    try:
        catalog = tuple(
            enrich_dish_quality(dishes_by_id[dish_id])
            for dish_id in sorted(dishes_by_id)
        )
    except CanonicalFoodError as exc:
        raise DishCatalogError("INVALID_CANONICAL_FOOD_LAYER") from exc
    names = [str(item.get("name", "")).strip().casefold() for item in catalog]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise DishCatalogError("INVALID_OR_DUPLICATE_DISH_NAME")
    return catalog


def load_dish_catalog() -> list[dict[str, Any]]:
    """Return a caller-owned copy of the merged, deterministic catalog."""

    return deepcopy(list(_load_dish_catalog_cached()))


def clear_dish_catalog_cache() -> None:
    """Clear the process cache for tests or an explicit administrative reload."""

    _load_dish_catalog_cached.cache_clear()
    clear_canonical_food_cache()


def dish_source_image_url(dish_id: object) -> str | None:
    """Return a safe, catalog-provenanced image URL for UI presentation.

    This is derived at read time, so it does not alter an immutable Plan V2
    revision, its hash, or the distinction between a planned and eaten meal.
    """

    try:
        normalized_id = int(str(dish_id))
    except (TypeError, ValueError):
        return None
    for dish in _load_dish_catalog_cached():
        if int(dish.get("id", -1)) != normalized_id:
            continue
        provenance = dish.get("provenance")
        raw_url = (
            provenance.get("source_image_url")
            if isinstance(provenance, dict)
            else None
        )
        if not isinstance(raw_url, str):
            return None
        image_url = raw_url.strip()
        parsed = urlparse(image_url)
        return image_url if parsed.scheme == "https" and parsed.netloc else None
    return None


__all__ = [
    "BASE_DISHES_FILE",
    "CURATED_DISHES_FILE",
    "REFERENCE_DISHES_FILE",
    "DishCatalogError",
    "clear_dish_catalog_cache",
    "dish_source_image_url",
    "load_dish_catalog",
]
