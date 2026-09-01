import pytest
from services.agent.tools.dish import (
    suggest_dish,
    _get_region_from_gps,
    _get_dish_region,
)

def test_get_region_from_gps():
    # Hanoi (North)
    assert _get_region_from_gps(21.0285, 105.8542) == "North"
    # Da Nang (Central)
    assert _get_region_from_gps(16.0544, 108.2022) == "Central"
    # HCMC (South)
    assert _get_region_from_gps(10.8231, 106.6297) == "South"
    # Outside Vietnam
    assert _get_region_from_gps(37.7749, -122.4194) is None
    assert _get_region_from_gps(0.0, 0.0) is None

def test_get_dish_region():
    assert _get_dish_region("Phở bò") == "National"
    assert _get_dish_region("Bún chả") == "North"
    assert _get_dish_region("Bún bò Huế") == "Central"
    assert _get_dish_region("Cao lầu") == "Central"
    assert _get_dish_region("Cơm tấm sườn") == "South"
    assert _get_dish_region("Hủ tiếu") == "South"
    assert _get_dish_region("Cơm gà") == "Unknown"
    assert _get_dish_region("Sữa chua") == "Unknown"

def test_suggest_dish_regional_filtering():
    # South location should prefer South or National dishes, not North
    # Hủ tiếu (id=19, South) and Cơm tấm sườn (id=11, South)
    res_south = suggest_dish(
        meal_type="lunch",
        target_kcal=600,
        latitude=10.8231,
        longitude=106.6297
    )
    assert res_south["region"] == "South"
    assert res_south["region"] != "North"

    # North location should prefer North or National dishes, not South
    res_north = suggest_dish(
        meal_type="breakfast",
        target_kcal=500,
        latitude=21.0285,
        longitude=105.8542
    )
    assert res_north["region"] in ("North", "National")
    assert res_north["region"] != "South"

def test_suggest_dish_query_override():
    # Even if user is in North, querying a South dish should return that South dish
    res = suggest_dish(
        meal_type="lunch",
        target_kcal=600,
        query="hủ tiếu",
        latitude=21.0285,
        longitude=105.8542
    )
    assert "Hủ tiếu" in res["name"]
    assert res["region"] == "South"
