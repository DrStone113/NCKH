"""Unit tests for backend/services/tdee_calculator.py"""

import pytest

from backend.services.tdee_calculator import (
    ACTIVITY_MULTIPLIERS,
    GOAL_ADJUSTMENTS,
    MINIMUM_SAFE_CALORIES,
    calculate_bmr,
    calculate_tdee,
    get_recommended_calories,
)


# ---------------------------------------------------------------------------
# calculate_bmr
# ---------------------------------------------------------------------------

class TestCalculateBmr:
    def test_male_formula(self):
        # 10*70 + 6.25*175 - 5*25 + 5 = 700 + 1093.75 - 125 + 5 = 1673.75
        assert calculate_bmr(age=25, gender="male", height_cm=175, weight_kg=70) == pytest.approx(1673.75)

    def test_female_formula(self):
        # 10*60 + 6.25*165 - 5*30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
        assert calculate_bmr(age=30, gender="female", height_cm=165, weight_kg=60) == pytest.approx(1320.25)

    def test_invalid_gender_raises(self):
        with pytest.raises(ValueError, match="gender"):
            calculate_bmr(age=25, gender="other", height_cm=170, weight_kg=70)

    def test_returns_float(self):
        result = calculate_bmr(age=20, gender="male", height_cm=180, weight_kg=80)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# calculate_tdee
# ---------------------------------------------------------------------------

class TestCalculateTdee:
    @pytest.mark.parametrize("level,multiplier", ACTIVITY_MULTIPLIERS.items())
    def test_all_activity_levels(self, level, multiplier):
        bmr = 1500.0
        assert calculate_tdee(bmr, level) == pytest.approx(bmr * multiplier)

    def test_invalid_activity_level_raises(self):
        with pytest.raises(ValueError, match="activity_level"):
            calculate_tdee(1500.0, "extreme")

    def test_returns_float(self):
        assert isinstance(calculate_tdee(1500.0, "moderate"), float)


# ---------------------------------------------------------------------------
# get_recommended_calories
# ---------------------------------------------------------------------------

class TestGetRecommendedCalories:
    @pytest.mark.parametrize("goal,adjustment", GOAL_ADJUSTMENTS.items())
    def test_all_goals_above_minimum(self, goal, adjustment):
        tdee = 2000.0
        result = get_recommended_calories(tdee, goal)
        expected = max(tdee + adjustment, MINIMUM_SAFE_CALORIES)
        assert result == pytest.approx(expected)

    def test_minimum_safe_calories_enforced(self):
        # Very low TDEE + lose_weight should still return >= 1200
        result = get_recommended_calories(tdee=1300.0, health_goal="lose_weight")
        assert result >= MINIMUM_SAFE_CALORIES

    def test_minimum_floor_exact(self):
        # 1200 - 500 = 700 → clamped to 1200
        result = get_recommended_calories(tdee=1200.0, health_goal="lose_weight")
        assert result == pytest.approx(MINIMUM_SAFE_CALORIES)

    def test_invalid_goal_raises(self):
        with pytest.raises(ValueError, match="health_goal"):
            get_recommended_calories(2000.0, "bulk")

    def test_maintain_returns_tdee(self):
        tdee = 2200.0
        assert get_recommended_calories(tdee, "maintain") == pytest.approx(tdee)

    def test_gain_muscle_adds_surplus(self):
        tdee = 2000.0
        assert get_recommended_calories(tdee, "gain_muscle") == pytest.approx(2300.0)
