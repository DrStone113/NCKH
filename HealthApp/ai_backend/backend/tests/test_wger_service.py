"""
Unit tests for WgerService

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 8.7
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from services.wger_service import WgerService
from models.schemas import WgerExerciseData, WgerIngredientData


@pytest.fixture
def wger_service():
    """Create a WgerService instance for testing"""
    return WgerService()


@pytest.mark.asyncio
async def test_wger_enabled_false_returns_empty_list(wger_service):
    """Test that WGER_ENABLED=false returns empty list without calling API"""
    wger_service.enabled = False
    db_mock = AsyncMock()
    
    exercises = await wger_service.fetch_all_exercises(db_mock)
    ingredients = await wger_service.fetch_all_ingredients(db_mock)
    
    assert exercises == []
    assert ingredients == []
    # Verify no DB calls were made
    db_mock.execute.assert_not_called()


@pytest.mark.asyncio
async def test_parse_exercises_basic():
    """Test parsing exercise data from API response"""
    service = WgerService()
    
    raw_data = [
        {
            "id": 1,
            "name": "Push-up",
            "description": "A basic exercise",
            "category": {"id": 10, "name": "Chest"},
            "muscles": [{"id": 1, "name_en": "Pectoralis", "is_front": True}],
            "muscles_secondary": [],
            "equipment": [],
            "images": [{"image": "http://example.com/image.jpg"}],
        }
    ]
    
    exercises = service._parse_exercises(raw_data)
    
    assert len(exercises) == 1
    assert exercises[0].id == 1
    assert exercises[0].name == "Push-up"
    assert exercises[0].category_name == "Chest"
    assert len(exercises[0].muscles) == 1
    assert exercises[0].muscles[0].name_en == "Pectoralis"


@pytest.mark.asyncio
async def test_parse_ingredients_basic():
    """Test parsing ingredient data from API response"""
    service = WgerService()
    
    raw_data = [
        {
            "id": 100,
            "name": "Chicken Breast",
            "energy": 165.0,
            "protein": 31.0,
            "carbohydrates": 0.0,
            "fat": 3.6,
            "fiber": None,
            "sugar": None,
        }
    ]
    
    ingredients = service._parse_ingredients(raw_data)
    
    assert len(ingredients) == 1
    assert ingredients[0].id == 100
    assert ingredients[0].name == "Chicken Breast"
    assert ingredients[0].energy == 165.0
    assert ingredients[0].protein == 31.0


def test_wger_service_initialization():
    """Test that WgerService initializes with correct settings"""
    service = WgerService()
    
    assert service.base_url is not None
    assert service.timeout > 0
    assert service.cache_ttl_hours > 0
    assert isinstance(service.enabled, bool)
