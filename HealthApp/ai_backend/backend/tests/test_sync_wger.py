"""
Unit tests for sync_wger.py script.

Requirements: 2.2, 2.3, 2.4
"""
import sys
from pathlib import Path

# Add backend/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    WgerExerciseData,
    WgerIngredientData,
    WgerMuscle,
    WgerEquipmentItem,
)
from scripts.sync_wger import build_exercise_text, build_ingredient_text


def test_build_exercise_text_basic():
    """Test build_exercise_text with basic exercise data."""
    exercise = WgerExerciseData(
        id=123,
        name="Push-up",
        description="A basic upper body exercise",
        category_id=1,
        category_name="Arms",
        muscles=[
            WgerMuscle(id=1, name_en="Chest", is_front=True),
            WgerMuscle(id=2, name_en="Triceps", is_front=True),
        ],
        equipment=[
            WgerEquipmentItem(id=1, name="Body weight"),
        ],
    )
    
    text = build_exercise_text(exercise)
    
    # Verify all required fields are present
    assert "Push-up" in text
    assert "Arms" in text
    assert "Chest" in text
    assert "Triceps" in text
    assert "Body weight" in text
    assert "A basic upper body exercise" in text


def test_build_exercise_text_no_muscles():
    """Test build_exercise_text with no muscles."""
    exercise = WgerExerciseData(
        id=456,
        name="Walking",
        description="Basic cardio",
        category_id=2,
        category_name="Cardio",
        muscles=[],
        equipment=[],
    )
    
    text = build_exercise_text(exercise)
    
    assert "Walking" in text
    assert "Cardio" in text
    assert "No specific muscles" in text
    assert "No equipment" in text


def test_build_ingredient_text_basic():
    """Test build_ingredient_text with basic ingredient data."""
    ingredient = WgerIngredientData(
        id=789,
        name="Chicken Breast",
        energy=165.0,
        protein=31.0,
        carbohydrates=0.0,
        fat=3.6,
    )
    
    text = build_ingredient_text(ingredient)
    
    # Verify all required fields are present
    assert "Chicken Breast" in text
    assert "165.0" in text
    assert "31.0" in text
    assert "0.0" in text
    assert "3.6" in text
    assert "kcal/100g" in text
    assert "g/100g" in text


def test_build_ingredient_text_null_values():
    """Test build_ingredient_text with null macro values."""
    ingredient = WgerIngredientData(
        id=999,
        name="Unknown Food",
        energy=None,
        protein=None,
        carbohydrates=None,
        fat=None,
    )
    
    text = build_ingredient_text(ingredient)
    
    assert "Unknown Food" in text
    assert "N/A" in text


def test_build_exercise_text_completeness():
    """
    Test that build_exercise_text includes all required components.
    
    Requirements: 2.2
    """
    exercise = WgerExerciseData(
        id=100,
        name="Bench Press",
        description="Compound chest exercise",
        category_id=3,
        category_name="Strength",
        muscles=[
            WgerMuscle(id=1, name_en="Pectorals", is_front=True),
            WgerMuscle(id=2, name_en="Deltoids", is_front=True),
        ],
        equipment=[
            WgerEquipmentItem(id=1, name="Barbell"),
            WgerEquipmentItem(id=2, name="Bench"),
        ],
    )
    
    text = build_exercise_text(exercise)
    
    # Property: text must contain name, category, all muscles, all equipment, and description
    assert exercise.name in text
    assert exercise.category_name in text
    assert exercise.description in text
    
    for muscle in exercise.muscles:
        assert muscle.name_en in text
    
    for equip in exercise.equipment:
        assert equip.name in text


def test_build_ingredient_text_completeness():
    """
    Test that build_ingredient_text includes all required components.
    
    Requirements: 2.3
    """
    ingredient = WgerIngredientData(
        id=200,
        name="Brown Rice",
        energy=370.0,
        protein=7.9,
        carbohydrates=77.2,
        fat=2.9,
    )
    
    text = build_ingredient_text(ingredient)
    
    # Property: text must contain name and all macro values
    assert ingredient.name in text
    assert str(ingredient.energy) in text or f"{ingredient.energy:.1f}" in text
    assert str(ingredient.protein) in text or f"{ingredient.protein:.1f}" in text
    assert str(ingredient.carbohydrates) in text or f"{ingredient.carbohydrates:.1f}" in text
    assert str(ingredient.fat) in text or f"{ingredient.fat:.1f}" in text


if __name__ == "__main__":
    # Run tests manually
    test_build_exercise_text_basic()
    test_build_exercise_text_no_muscles()
    test_build_ingredient_text_basic()
    test_build_ingredient_text_null_values()
    test_build_exercise_text_completeness()
    test_build_ingredient_text_completeness()
    print("All tests passed!")
