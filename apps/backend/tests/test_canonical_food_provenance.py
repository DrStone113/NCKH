from __future__ import annotations

import pytest

from modules.nutrition.canonical_foods import (
    MatchQuality,
    energy_consistency,
    enrich_dish_quality,
    load_canonical_food_catalog,
    load_source_registry,
    resolve_food_match,
)
from modules.nutrition.catalog import load_dish_catalog
from modules.nutrition.router import (
    get_food_source_registry,
    get_nutrition_stats,
)
from services.agent.tools.dish import suggest_dish


def _foods_by_name() -> dict[str, dict]:
    return {food["name"]: food for food in load_canonical_food_catalog()}


def test_source_priority_is_explicit_but_only_vietnam_fct_is_active() -> None:
    registry = load_source_registry()
    sources = registry["sources"]

    assert [source["priority"] for source in sources] == list(range(10))
    assert [source["source_id"] for source in sources[:4]] == [
        "VIETNAM_FCT",
        "FAO_INFOODS",
        "ASEANFOODS",
        "USDA_FDC",
    ]
    assert [
        source["source_id"]
        for source in sources
        if source["kind"] == "NUTRIENT_DATABASE"
        and source["ingestion_status"] == "ACTIVE"
    ] == ["VIETNAM_FCT"]
    assert next(source for source in sources if source["source_id"] == "USDA_FDC")[
        "license"
    ]["spdx_or_terms"] == "CC0-1.0"
    assert next(source for source in sources if source["source_id"] == "THAI_FCD")[
        "license"
    ]["review_status"] == "COMMERCIAL_PERMISSION_REQUIRED"


def test_all_source_foods_have_stable_ids_and_field_level_provenance() -> None:
    foods = load_canonical_food_catalog()

    assert len(foods) == 526
    assert len({food["food_id"] for food in foods}) == 526
    assert len({food["canonical_key"] for food in foods}) == 526
    for food in foods:
        assert food["food_id"].startswith("VN_FCT_")
        assert food["source"]["dataset"] == "VIETNAM_FCT"
        assert food["source"]["match_quality"] == "EXACT"
        for nutrient in food["nutrients_per_100g"].values():
            assert nutrient["source_id"] == "VIETNAM_FCT"
            assert nutrient["source_record_id"] == food["source"][
                "source_record_id"
            ]
            assert nutrient["source_edition"] == "2007"
            assert "original_value" in nutrient
            assert "original_unit" in nutrient
            assert "normalized_value" in nutrient
            assert "normalization_rule" in nutrient
            assert "review_status" in nutrient
            if nutrient["data_status"] == "MISSING":
                assert nutrient["original_value"] is None
                assert nutrient["normalized_value"] is None
            else:
                assert nutrient["original_value"] == nutrient["normalized_value"]

    vodka = next(food for food in foods if food["name"] == "Rượu trắng (cồn 39 g)")
    assert vodka["nutrients_per_100g"]["protein"]["value"] is None
    assert vodka["nutrients_per_100g"]["protein"]["data_status"] == "MISSING"


def test_raw_cooked_and_dried_foods_are_distinct_canonical_records() -> None:
    foods = _foods_by_name()

    assert foods["Ngô nếp luộc"]["canonical_description"]["state"] == "COOKED"
    assert foods["Mực tươi"]["canonical_description"]["state"] == "RAW"
    assert foods["Mực khô"]["canonical_description"]["state"] == "DRIED"
    assert foods["Mực tươi"]["food_id"] != foods["Mực khô"]["food_id"]
    assert foods["Mực tươi"]["canonical_description"]["derivation"][
        "used_for_exact_matching"
    ] is False
    assert "contains_land_meat" not in foods["Quả trứng gà"]["objective_tags"]
    assert "contains_beef" not in foods["Sữa bò tươi"]["objective_tags"]


@pytest.mark.parametrize(
    ("food_name", "expected_allergen"),
    [
        ("Tôm biển", "CRUSTACEAN"),
        ("Mực tươi", "MOLLUSC"),
        ("Cá hồi", "FISH"),
        ("Nước mắm loại II", "FISH"),
        ("Trứng gà", "EGG"),
        ("Sữa bò tươi", "MILK"),
        ("Lạc hạt", "PEANUT"),
        ("Đậu tương (đậu nành)", "SOY"),
        ("Bột mì", "WHEAT_GLUTEN"),
    ],
)
def test_allergens_are_derived_from_canonical_food_taxonomy(
    food_name: str, expected_allergen: str
) -> None:
    assert expected_allergen in _foods_by_name()[food_name]["allergen_ids"]


def test_unresolved_food_is_never_substituted_or_auto_published() -> None:
    match = resolve_food_match("Cá basa không có trong bảng")
    assert match == {
        "food_id": None,
        "quality": MatchQuality.UNRESOLVED.value,
        "auto_publishable": False,
        "review_status": "DATA_REVIEW_REQUIRED",
    }

    dish = enrich_dish_quality(
        {
            "id": 9999,
            "name": "Món thử chưa đối chiếu",
            "meal_types": ["lunch"],
            "ingredients": [
                {"name": "Cá basa không có trong bảng", "grams": 100}
            ],
            "estimated_calories": 100,
        }
    )
    assert dish["ingredients"][0]["match"]["quality"] == "UNRESOLVED"
    assert dish["quality"]["ingredient_match_complete"] is False
    assert dish["quality"]["publishable_for_nutrition_calculation"] is False
    assert "vegan" not in dish["dietary_tags"]["objective"]


def test_energy_449_is_a_qa_signal_with_pass_review_fail_thresholds() -> None:
    assert energy_consistency(400, 20, 50, 13.333)["status"] == "PASS"
    assert energy_consistency(400, 20, 50, 7)["status"] == "REVIEW"
    assert energy_consistency(400, 10, 30, 5)["status"] == "FAIL"


def test_every_live_dish_is_exactly_matched_and_macro_energy_safe() -> None:
    dishes = load_dish_catalog()

    assert len(dishes) == 300
    assert sum(
        dish["quality"]["review_status"] == "LEGACY_SERVING_REVIEW_REQUIRED"
        for dish in dishes
    ) == 70
    for dish in dishes:
        assert dish["quality"]["ingredient_match_complete"] is True
        assert dish["quality"]["publishable_for_nutrition_calculation"] is True
        assert dish["quality"]["nutrition_consistency"]["status"] in {
            "PASS",
            "REVIEW",
        }
        assert all(
            ingredient["match"]["quality"] == "EXACT"
            for ingredient in dish["ingredients"]
        )


def test_dish_tool_uses_canonical_allergen_ids_and_recalculated_energy() -> None:
    with pytest.raises(ValueError, match="NO_DISH_FOUND"):
        suggest_dish(
            meal_type="lunch",
            target_kcal=200,
            query="mực ống hấp củ đậu",
            dietary_restrictions=["no_mollusc"],
        )

    dish = suggest_dish(
        meal_type="lunch",
        target_kcal=200,
        query="mực ống hấp củ đậu",
    )
    assert "MOLLUSC" in dish["allergen_ids"]
    assert all(component["food_id"] for component in dish["components"])
    assert dish["nutrition_method"] == (
        "RECIPE_CALCULATED_FROM_CANONICAL_INGREDIENTS"
    )


@pytest.mark.parametrize(
    ("meal_type", "target_kcal", "query", "restriction"),
    [
        ("breakfast", 300, "xôi lạc", "no_peanut"),
        ("lunch", 500, "bún chả", "no_pork"),
        ("snack", 120, "sữa chua", "no_milk"),
    ],
)
def test_canonical_restrictions_block_matching_dishes(
    meal_type: str, target_kcal: int, query: str, restriction: str
) -> None:
    assert suggest_dish(
        meal_type=meal_type,
        target_kcal=target_kcal,
        query=query,
    )["name"]
    with pytest.raises(ValueError, match="NO_DISH_FOUND"):
        suggest_dish(
            meal_type=meal_type,
            target_kcal=target_kcal,
            query=query,
            dietary_restrictions=[restriction],
        )


def test_region_is_sourced_or_explicitly_unknown() -> None:
    by_name = {dish["name"]: dish for dish in load_dish_catalog()}

    bun_bo_hue = by_name["Bún bò Huế"]
    assert bun_bo_hue["region"] == "Central"
    assert bun_bo_hue["region_metadata"]["confidence"] == "HIGH"
    assert bun_bo_hue["region_metadata"]["source_url"].startswith(
        "https://vietnam.travel/"
    )

    unknown = by_name["Sữa chua"]
    assert unknown["region"] == "Unknown"
    assert unknown["region_metadata"]["source_url"] is None
    assert unknown["region_metadata"]["method"] == "UNRESOLVED"
    assert by_name["Bún chả cá"]["region"] == "Unknown"
    assert by_name["Thịt kho đậu phộng"]["region"] == "Unknown"


@pytest.mark.asyncio
async def test_api_exposes_source_registry_and_canonical_counts() -> None:
    registry = await get_food_source_registry()
    stats = await get_nutrition_stats()

    assert registry["policy"]["fallback_is_not_merge"] is True
    assert stats["canonical_foods"] == 526
    assert stats["active_nutrient_sources"] == ["VIETNAM_FCT"]
