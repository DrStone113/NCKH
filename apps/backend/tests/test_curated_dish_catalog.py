from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.nutrition.catalog import (
    BASE_DISHES_FILE,
    CURATED_DISHES_FILE,
    REFERENCE_DISHES_FILE,
    load_dish_catalog,
)
from modules.nutrition.router import (
    get_dish_by_id,
    get_food_by_id,
    get_nutrition_stats,
    get_vietnamese_dishes,
)
from services.agent.tools.dish import suggest_dish
from scripts.build_reference_dish_catalog import principal_ingredients_present


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(path: Path):
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _calculated_calories(
    dish: dict[str, object], foods_by_name: dict[str, dict[str, object]]
) -> float:
    return sum(
        float(foods_by_name[ingredient["name"]]["energy_kcal"])
        * float(ingredient["grams"])
        / 100.0
        for ingredient in dish["ingredients"]
    )


def test_live_catalog_preserves_frozen_base_and_applies_curated_overlay():
    base = _load_json(BASE_DISHES_FILE)
    overlay = _load_json(CURATED_DISHES_FILE)
    merged = load_dish_catalog()

    assert len(base) == 90
    assert len(overlay["overrides"]) == 4
    assert len(overlay["additions"]) == 7
    assert len(merged) == 300

    by_id = {dish["id"]: dish for dish in merged}
    assert by_id[2]["name"] == "Phở bò sốt vang"
    assert by_id[7]["estimated_calories"] == 225
    assert by_id[76]["ingredients"][0]["name"] == "Miến dong"
    assert by_id[76]["ingredients"][0]["grams"] == 55
    assert by_id[76]["ingredients"][0]["category"] == "carb"
    assert by_id[76]["ingredients"][0]["food_id"] == "VN_FCT_02015"
    assert by_id[76]["ingredients"][0]["match"]["quality"] == "EXACT"
    assert by_id[97]["catalog_status"] == "verified_complete_meal"
    assert by_id[98]["catalog_status"] == "normalized_reference_recipe"
    assert by_id[300]["catalog_status"] == "normalized_reference_recipe"


def test_reference_catalog_is_sourced_normalized_and_recalculated():
    foods = _load_json(DATA_DIR / "vietnamese_foods.json")
    foods_by_name = {food["name"]: food for food in foods}
    overlay = _load_json(REFERENCE_DISHES_FILE)

    assert len(overlay["additions"]) == 203
    assert overlay["source"]["source_commit"] == (
        "126caa3a8b58708a09b2b2e119ff4923b6f06d82"
    )
    assert overlay["quality_policy"]["website_nutrition_fields_used"] is False

    for dish in overlay["additions"]:
        assert dish["catalog_status"] == "normalized_reference_recipe"
        assert len(dish["ingredients"]) >= 2
        assert dish["normalization"]["quantified_weight_coverage"] >= 0.60
        assert dish["provenance"]["academic_reference_url"] == (
            "https://aclanthology.org/2024.paclic-1.4/"
        )
        assert dish["provenance"]["source_image_url"].startswith(
            "https://monngonmoingay.com/"
        )
        for ingredient in dish["ingredients"]:
            assert ingredient["name"] in foods_by_name
            assert ingredient["source_names"]
        assert principal_ingredients_present(
            dish["name"], dish["ingredients"], foods_by_name
        )
        assert _calculated_calories(dish, foods_by_name) == pytest.approx(
            float(dish["estimated_calories"]), rel=0.02
        )


def test_every_curated_ingredient_is_an_exact_food_table_match():
    foods = _load_json(DATA_DIR / "vietnamese_foods.json")
    foods_by_name = {food["name"]: food for food in foods}
    overlay = _load_json(CURATED_DISHES_FILE)

    for dish in [*overlay["overrides"], *overlay["additions"]]:
        for ingredient in dish["ingredients"]:
            assert ingredient["name"] in foods_by_name, (
                dish["name"],
                ingredient["name"],
            )


def test_curated_calories_match_ingredient_sum_within_two_percent():
    foods = _load_json(DATA_DIR / "vietnamese_foods.json")
    foods_by_name = {food["name"]: food for food in foods}
    overlay = _load_json(CURATED_DISHES_FILE)

    for dish in [*overlay["overrides"], *overlay["additions"]]:
        calculated = _calculated_calories(dish, foods_by_name)
        expected = float(dish["estimated_calories"])
        assert calculated == pytest.approx(expected, rel=0.02), dish["name"]


def test_verified_complete_meals_cover_all_four_food_groups():
    overlay = _load_json(CURATED_DISHES_FILE)
    complete_meals = [
        dish
        for dish in overlay["additions"]
        if dish["catalog_status"] == "verified_complete_meal"
    ]

    assert len(complete_meals) == 6
    for dish in complete_meals:
        categories = {ingredient["category"] for ingredient in dish["ingredients"]}
        assert {"carb", "protein", "veggie", "fruit"} <= categories
        assert len(dish["ingredients"]) >= 7
        assert dish["provenance"]["source_url"].startswith(
            "https://chuyentrang.viendinhduong.vn/"
        )


@pytest.mark.asyncio
async def test_nutrition_detail_routes_use_real_numeric_identifiers():
    dish = await get_dish_by_id(97)
    food = await get_food_by_id(1005)

    assert dish["name"] == "Suất cơm tôm, trứng đúc thịt và cải bắp"
    assert food["name"] == "Gạo lứt"


@pytest.mark.asyncio
async def test_list_route_and_stats_expose_all_300_dishes_by_default():
    dishes = await get_vietnamese_dishes()
    stats = await get_nutrition_stats()

    assert len(dishes) == 300
    assert stats["total_dishes"] == 300
    assert stats["normalized_reference_recipes"] == 203


def test_suggest_dish_exposes_provenance_for_curated_recipe():
    result = suggest_dish(
        meal_type="breakfast",
        target_kcal=300,
        query="miến gà",
    )

    assert result["name"] == "Miến gà"
    assert result["catalog_status"] == "verified_recipe"
    assert result["provenance"]["publisher"] == (
        "Viện Dinh dưỡng Quốc gia - Bộ Y tế"
    )


def test_food_group_codes_prevent_fish_from_passing_no_seafood_filter():
    with pytest.raises(ValueError, match="NO_DISH_FOUND"):
        suggest_dish(
            meal_type="lunch",
            target_kcal=620,
            query="cá trắm sốt cà chua",
            dietary_restrictions=["no_seafood"],
        )
