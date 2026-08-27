"""Validate the live dish catalog and its source-verified overlay.

Run from ``apps/backend`` with ``python scripts/validate_dish_catalog.py``.
The command is read-only and exits non-zero when curated records lose an exact
food-table match, provenance, food-group coverage, or calorie consistency.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from modules.nutrition.catalog import (  # noqa: E402
    CURATED_DISHES_FILE,
    REFERENCE_DISHES_FILE,
    load_dish_catalog,
)
from scripts.build_reference_dish_catalog import (  # noqa: E402
    principal_ingredients_present,
)


FOODS_FILE = BACKEND_DIR / "data" / "vietnamese_foods.json"
TRUSTED_SOURCE_PREFIXES = (
    "https://chuyentrang.viendinhduong.vn/",
    "https://viendinhduong.vn/",
    "https://www.fao.org/",
)
REQUIRED_COMPLETE_MEAL_GROUPS = {"carb", "protein", "veggie", "fruit"}
REFERENCE_SOURCE_PREFIX = "https://github.com/QuocAn55/"
REFERENCE_ACADEMIC_URL = "https://aclanthology.org/2024.paclic-1.4/"
REFERENCE_IMAGE_PREFIX = "https://monngonmoingay.com/"
REFERENCE_SOURCE_SHA256 = (
    "79a8135e108a6ff1b66338737b816aa1021522b44ae902c98b439398194fcadb"
)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _calories(
    dish: dict[str, Any], foods_by_name: dict[str, dict[str, Any]]
) -> float:
    return sum(
        float(foods_by_name[ingredient["name"]]["energy_kcal"])
        * float(ingredient["grams"])
        / 100.0
        for ingredient in dish["ingredients"]
    )


def validate() -> list[str]:
    errors: list[str] = []
    catalog = load_dish_catalog()
    overlay = _read_json(CURATED_DISHES_FILE)
    reference_overlay = _read_json(REFERENCE_DISHES_FILE)
    foods = _read_json(FOODS_FILE)
    foods_by_name = {food["name"]: food for food in foods}
    curated = [*overlay.get("overrides", []), *overlay.get("additions", [])]
    references = reference_overlay.get("additions", [])

    ids = [int(dish["id"]) for dish in catalog]
    names = [str(dish["name"]).strip().casefold() for dish in catalog]
    if len(ids) != len(set(ids)):
        errors.append("duplicate live dish id")
    if len(names) != len(set(names)):
        errors.append("duplicate live dish name")
    if len(catalog) != 300:
        errors.append(f"expected 300 live dishes, found {len(catalog)}")

    for dish in curated:
        label = f"id={dish.get('id')} name={dish.get('name')}"
        source_url = str(dish.get("provenance", {}).get("source_url", ""))
        if not source_url.startswith(TRUSTED_SOURCE_PREFIXES):
            errors.append(f"{label}: untrusted or missing source_url")

        ingredients = dish.get("ingredients") or []
        if not ingredients:
            errors.append(f"{label}: no ingredients")
            continue
        missing = [
            ingredient.get("name")
            for ingredient in ingredients
            if ingredient.get("name") not in foods_by_name
        ]
        if missing:
            errors.append(f"{label}: missing exact food matches {missing}")
            continue

        calculated = _calories(dish, foods_by_name)
        reported = float(dish.get("estimated_calories") or 0)
        relative_gap = abs(calculated - reported) / reported if reported else 1.0
        if relative_gap > 0.02:
            errors.append(
                f"{label}: calorie gap {relative_gap:.1%} "
                f"({calculated:.1f} calculated vs {reported:.1f} reported)"
            )

        if dish.get("catalog_status") == "verified_complete_meal":
            categories = {ingredient.get("category") for ingredient in ingredients}
            missing_groups = REQUIRED_COMPLETE_MEAL_GROUPS - categories
            if missing_groups:
                errors.append(f"{label}: missing food groups {sorted(missing_groups)}")

    source_metadata = reference_overlay.get("source", {})
    if source_metadata.get("source_sha256") != REFERENCE_SOURCE_SHA256:
        errors.append("reference catalog source SHA-256 is not pinned")

    for dish in references:
        label = f"id={dish.get('id')} name={dish.get('name')}"
        provenance = dish.get("provenance", {})
        if dish.get("catalog_status") != "normalized_reference_recipe":
            errors.append(f"{label}: invalid reference catalog status")
        if not str(provenance.get("source_url", "")).startswith(
            REFERENCE_SOURCE_PREFIX
        ):
            errors.append(f"{label}: missing pinned ViFoodRec source")
        if provenance.get("academic_reference_url") != REFERENCE_ACADEMIC_URL:
            errors.append(f"{label}: missing PACLIC reference")
        if not str(provenance.get("source_image_url", "")).startswith(
            REFERENCE_IMAGE_PREFIX
        ):
            errors.append(f"{label}: recipe is not from Món Ngon Mỗi Ngày")

        ingredients = dish.get("ingredients") or []
        if len(ingredients) < 2:
            errors.append(f"{label}: fewer than two quantified ingredients")
            continue
        missing = [
            ingredient.get("name")
            for ingredient in ingredients
            if ingredient.get("name") not in foods_by_name
        ]
        if missing:
            errors.append(f"{label}: missing food-table matches {missing}")
            continue
        if any(not ingredient.get("source_names") for ingredient in ingredients):
            errors.append(f"{label}: missing auditable source ingredient names")
        if not principal_ingredients_present(dish["name"], ingredients, foods_by_name):
            errors.append(f"{label}: named main ingredient was lost in normalization")

        coverage = float(
            dish.get("normalization", {}).get("quantified_weight_coverage") or 0
        )
        if coverage < 0.60:
            errors.append(f"{label}: quantified weight coverage {coverage:.1%}")

        calculated = _calories(dish, foods_by_name)
        reported = float(dish.get("estimated_calories") or 0)
        relative_gap = abs(calculated - reported) / reported if reported else 1.0
        if relative_gap > 0.02:
            errors.append(
                f"{label}: calorie gap {relative_gap:.1%} "
                f"({calculated:.1f} calculated vs {reported:.1f} reported)"
            )

    verified_recipes = sum(
        dish.get("catalog_status") == "verified_recipe" for dish in catalog
    )
    complete_meals = sum(
        dish.get("catalog_status") == "verified_complete_meal" for dish in catalog
    )
    reference_recipes = sum(
        dish.get("catalog_status") == "normalized_reference_recipe"
        for dish in catalog
    )
    print(
        "dish catalog:",
        f"live={len(catalog)}",
        f"verified_recipes={verified_recipes}",
        f"verified_complete_meals={complete_meals}",
        f"normalized_reference_recipes={reference_recipes}",
        f"errors={len(errors)}",
    )
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
