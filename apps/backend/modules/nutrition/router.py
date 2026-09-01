"""
Nutrition API Router
Provides endpoints for Vietnamese food and dish data
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from modules.nutrition.catalog import DishCatalogError, load_dish_catalog
from modules.nutrition.canonical_foods import (
    CanonicalFoodError,
    load_canonical_food_catalog,
    load_source_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

# Cache
_dishes_cache: List[Dict[str, Any]] = []
_foods_cache: List[Dict[str, Any]] = []


def load_dishes() -> List[Dict[str, Any]]:
    """Load the merged legacy + source-verified Vietnamese dish catalog."""
    global _dishes_cache
    if _dishes_cache:
        return _dishes_cache

    try:
        _dishes_cache = load_dish_catalog()
        logger.info("Loaded %d Vietnamese dishes", len(_dishes_cache))
        return _dishes_cache
    except DishCatalogError as e:
        logger.error("Error loading Vietnamese dish catalog: %s", e)
        return []


def load_foods() -> List[Dict[str, Any]]:
    """Load canonical Vietnamese foods with source-level provenance."""
    global _foods_cache
    if _foods_cache:
        return _foods_cache

    try:
        _foods_cache = load_canonical_food_catalog()
        logger.info("Loaded %d Vietnamese foods", len(_foods_cache))
        return _foods_cache
    except CanonicalFoodError as e:
        logger.error("Error loading canonical Vietnamese foods: %s", e)
        return []


@router.get("/vietnamese-dishes")
async def get_vietnamese_dishes(
    search: str = None,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """
    Get Vietnamese dishes
    
    Query params:
    - search: Search by dish name
    - limit: Maximum number of results (default 100)
    """
    dishes = load_dishes()
    
    # Filter by search query
    if search:
        search_lower = search.lower()
        dishes = [
            dish for dish in dishes
            if search_lower in dish.get('name', '').lower()
        ]
    
    # Apply limit
    dishes = dishes[:limit]
    
    return dishes


@router.get("/vietnamese-dishes/{dish_id}")
async def get_dish_by_id(dish_id: int) -> Dict[str, Any]:
    """Get a specific Vietnamese dish by ID"""
    dishes = load_dishes()
    
    for dish in dishes:
        if dish.get('id') == dish_id:
            return dish
    
    raise HTTPException(status_code=404, detail=f"Dish {dish_id} not found")


@router.get("/vietnamese-foods")
async def get_vietnamese_foods(
    search: str = None,
    category: str = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get Vietnamese foods
    
    Query params:
    - search: Search by food name
    - category: Filter by category
    - limit: Maximum number of results (default 100)
    """
    foods = load_foods()
    
    # Filter by search query
    if search:
        search_lower = search.lower()
        foods = [
            food for food in foods
            if search_lower in food.get('name', '').lower()
        ]
    
    # Filter by category
    if category:
        foods = [
            food for food in foods
            if food.get('category', '').lower() == category.lower()
        ]
    
    # Apply limit
    foods = foods[:limit]
    
    return foods


@router.get("/vietnamese-foods/{food_id}")
async def get_food_by_id(food_id: int) -> Dict[str, Any]:
    """Get a specific Vietnamese food by ID"""
    foods = load_foods()
    
    for food in foods:
        if food.get('ma_so') == food_id or food.get('stt') == food_id:
            return food
    
    raise HTTPException(status_code=404, detail=f"Food {food_id} not found")


@router.get("/categories")
async def get_food_categories() -> List[str]:
    """Get all food categories"""
    foods = load_foods()
    categories = set()
    
    for food in foods:
        if 'category' in food:
            categories.add(food['category'])
    
    return sorted(list(categories))


@router.get("/food-sources")
async def get_food_source_registry() -> Dict[str, Any]:
    """Expose source priority, ingestion status and license-review state."""

    return load_source_registry()


@router.get("/stats")
async def get_nutrition_stats() -> Dict[str, Any]:
    """Get nutrition database statistics"""
    dishes = load_dishes()
    foods = load_foods()
    source_registry = load_source_registry()
    
    return {
        "total_dishes": len(dishes),
        "total_foods": len(foods),
        "canonical_foods": sum(bool(food.get("food_id")) for food in foods),
        "active_nutrient_sources": [
            source["source_id"]
            for source in source_registry["sources"]
            if source.get("kind") == "NUTRIENT_DATABASE"
            and source.get("ingestion_status") == "ACTIVE"
        ],
        "categories": len(set(food.get('category', '') for food in foods)),
        "verified_recipes": sum(
            1 for dish in dishes if dish.get("catalog_status") == "verified_recipe"
        ),
        "verified_complete_meals": sum(
            1
            for dish in dishes
            if dish.get("catalog_status") == "verified_complete_meal"
        ),
        "normalized_reference_recipes": sum(
            1
            for dish in dishes
            if dish.get("catalog_status") == "normalized_reference_recipe"
        ),
    }
