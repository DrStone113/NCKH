"""Regression coverage for complete, paginated chatbot catalog discovery."""

from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_server_tools
from services.agent.tools.dish import _DISHES, search_dish_catalog
from services.agent.tools.workout import _EXERCISES, search_exercise_catalog


def _all_ids(search, id_key: str) -> tuple[set[int], dict]:
    ids: set[int] = set()
    page = 1
    last: dict = {}
    while True:
        last = search(page=page, page_size=20)
        ids.update(int(item[id_key]) for item in last["results"])
        if not last["has_more"]:
            return ids, last
        assert last["next_page"] == page + 1
        page = int(last["next_page"])


def test_dish_catalog_search_visits_every_live_record_before_pagination():
    ids, last = _all_ids(search_dish_catalog, "dish_id")

    assert last["catalog_size"] == last["scanned_count"] == len(_DISHES)
    assert last["matched_count"] == len(_DISHES) == 300
    assert ids == {record.id for record in _DISHES}


def test_dish_catalog_tail_record_is_searchable_with_canonical_details():
    result = search_dish_catalog(
        dish_id=300,
        query="suon tiem hoa thanh long",
        page_size=1,
        include_details=True,
    )

    assert result["scanned_count"] == len(_DISHES)
    assert result["matched_count"] == 1
    dish = result["results"][0]
    assert dish["dish_id"] == 300
    assert dish["name"] == "S\u01b0\u1eddn ti\u1ec1m hoa thanh long"
    assert dish["nutrition"]["method"] == "RECIPE_CALCULATED_FROM_CANONICAL_INGREDIENTS"
    assert dish["components"]
    assert all(component["food_id"] for component in dish["components"])
    assert dish["instructions"] == []
    assert dish["instruction_status"] == "UNAVAILABLE_IN_CANONICAL_CATALOG"


def test_dish_catalog_search_applies_safety_filters_to_every_match():
    result = search_dish_catalog(
        dietary_restrictions=["no_pork"], page=1, page_size=20
    )

    assert result["scanned_count"] == len(_DISHES)
    assert result["matched_count"] > 0
    assert all(
        "contains_pork" not in dish["dietary_tags"] for dish in result["results"]
    )


def test_exercise_catalog_search_visits_every_canonical_record_before_pagination():
    ids, last = _all_ids(search_exercise_catalog, "exercise_id")
    canonical_ids = {
        int(record["source_exercise_id"])
        for record in load_canonical_exercise_catalog()
    }

    assert last["catalog_size"] == last["scanned_count"] == 885
    assert last["recommendation_catalog_size"] == len(_EXERCISES) == 884
    assert last["matched_count"] == len(canonical_ids)
    assert ids == canonical_ids


def test_exercise_catalog_tail_record_is_searchable_with_source_details():
    result = search_exercise_catalog(
        exercise_id=1949,
        query="limber 11",
        page_size=1,
        include_details=True,
    )

    assert result["scanned_count"] == 885
    assert result["matched_count"] == 1
    exercise = result["results"][0]
    assert exercise["exercise_id"] == 1949
    assert exercise["name_en"] == "Limber 11"
    assert exercise["instructions"]["text"]
    assert exercise["source"] == "WGER"
    assert exercise["source_license_metadata"]


def test_catalog_tools_are_registered_as_read_only_and_validate_pagination():
    registry = ToolRegistry()
    register_server_tools(registry)

    for name in ("search_dish_catalog", "search_exercise_catalog"):
        descriptor = registry.get(name)
        assert descriptor is not None
        assert descriptor.side == "server"
        assert descriptor.idempotent is True
        assert registry.validate(name, {"page": 1, "page_size": 20}) == (
            True,
            None,
        )
        assert registry.validate(name, {"page": 1, "page_size": 21}) == (
            False,
            "INVALID_ARGS",
        )
