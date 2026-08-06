"""
Nutrition API Router
Provides endpoints for Vietnamese food and dish data
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

# Load data files
# router.py -> nutrition/ -> modules/ -> backend/
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DISHES_FILE = DATA_DIR / "vietnamese_dishes.json"
FOODS_FILE = DATA_DIR / "vietnamese_foods.json"

# Cache
_dishes_cache: List[Dict[str, Any]] = []
_foods_cache: List[Dict[str, Any]] = []


def load_dishes() -> List[Dict[str, Any]]:
    """Load Vietnamese dishes from JSON file"""
    global _dishes_cache
    if _dishes_cache:
        return _dishes_cache

    try:
        with open(DISHES_FILE, 'r', encoding='utf-8') as f:
            _dishes_cache = json.load(f)
        logger.info("Loaded %d Vietnamese dishes", len(_dishes_cache))
        return _dishes_cache
    except Exception as e:
        logger.error("Error loading dishes from %s: %s", DISHES_FILE, e)
        return []


def load_foods() -> List[Dict[str, Any]]:
    """Load Vietnamese foods from JSON file"""
    global _foods_cache
    if _foods_cache:
        return _foods_cache

    try:
        with open(FOODS_FILE, 'r', encoding='utf-8') as f:
            _foods_cache = json.load(f)
        logger.info("Loaded %d Vietnamese foods", len(_foods_cache))
        return _foods_cache
    except Exception as e:
        logger.error("Error loading foods from %s: %s", FOODS_FILE, e)
        return []


@router.get("/vietnamese-dishes")
async def get_vietnamese_dishes(
    search: str = None,
    limit: int = 100
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
async def get_dish_by_id(dish_id: str) -> Dict[str, Any]:
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
async def get_food_by_id(food_id: str) -> Dict[str, Any]:
    """Get a specific Vietnamese food by ID"""
    foods = load_foods()
    
    for food in foods:
        if food.get('id') == food_id:
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


@router.get("/stats")
async def get_nutrition_stats() -> Dict[str, Any]:
    """Get nutrition database statistics"""
    dishes = load_dishes()
    foods = load_foods()
    
    return {
        "total_dishes": len(dishes),
        "total_foods": len(foods),
        "categories": len(set(food.get('category', '') for food in foods)),
    }
