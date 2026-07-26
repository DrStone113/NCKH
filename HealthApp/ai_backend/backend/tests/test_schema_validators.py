"""
Unit tests for Pydantic validators của domain types trong `models/schemas.py`.

Test cho task 1.3 (Validates: Requirements 3.4, 3.8, 3.12):
  - UserProfile: age ∈ [10, 120], weight_kg ∈ [30, 300], height_cm ∈ [100, 250]
                 và các field enum (gender, activity_level, health_goal).
  - Plan: validator `end_date - start_date + 1 == duration_days`
          và `duration_days ∈ [3, 120]`.
  - MealPlanPayload: `len(components) >= 1` và
                     `|total_calories - sum(components[i].calories)| <= 1.0`.

Note: các Pydantic class này được định nghĩa trong task 1.2. Nếu task 1.2 chưa
được merge, mọi test sẽ fail ở giai đoạn import. Khi task 1.2 hoàn thành, các
test sẽ pass.
"""

import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

# Cho phép import `models.schemas` khi chạy `pytest` từ thư mục `backend/`.
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (  # noqa: E402
    FoodComponent,
    MealPlanPayload,
    Plan,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_user_profile_kwargs(**overrides):
    """Trả về kwargs hợp lệ cho UserProfile, cho phép override từng field."""
    kwargs = dict(
        user_id="user-1",
        age=30,
        gender="male",
        height_cm=170.0,
        weight_kg=70.0,
        activity_level="moderate",
        health_goal="maintain",
        dietary_restrictions=[],
    )
    kwargs.update(overrides)
    return kwargs


def _valid_plan_kwargs(**overrides):
    """Trả về kwargs hợp lệ cho Plan với end_date - start_date + 1 == duration_days."""
    kwargs = dict(
        id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        goal="lose_weight",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 7),  # 7 ngày: 1..7 inclusive
        duration_days=7,
        daily_kcal_target=2000.0,
        daily_protein_target=120.0,
        status="active",
        created_at="2024-01-01T00:00:00",
    )
    kwargs.update(overrides)
    return kwargs


def _component(calories=100.0, **overrides):
    kwargs = dict(
        name="Cơm trắng",
        serving_grams=100,
        calories=calories,
        protein=2.0,
        carbs=22.0,
        fat=0.5,
    )
    kwargs.update(overrides)
    return FoodComponent(**kwargs)


def _valid_meal_plan_payload_kwargs(**overrides):
    components = [
        _component(calories=300.0),
        _component(name="Thịt heo", calories=200.0, protein=18.0),
    ]
    kwargs = dict(
        meal_type="lunch",
        dish_name="Cơm thịt heo",
        components=components,
        total_calories=500.0,  # khớp đúng tổng các component
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# UserProfile — Requirements 3.12
# ---------------------------------------------------------------------------


class TestUserProfileValidators:
    """Test miền hợp lệ và miền không hợp lệ của UserProfile."""

    def test_valid_profile_at_boundaries(self):
        """Profile hợp lệ tại các giá trị biên không raise."""
        # Biên dưới
        UserProfile(**_valid_user_profile_kwargs(
            age=10, height_cm=100.0, weight_kg=30.0,
        ))
        # Biên trên
        UserProfile(**_valid_user_profile_kwargs(
            age=120, height_cm=250.0, weight_kg=300.0,
        ))

    def test_typical_valid_profile(self):
        """Profile điển hình phải parse được mà không lỗi."""
        profile = UserProfile(**_valid_user_profile_kwargs())
        assert profile.age == 30
        assert profile.gender == "male"
        assert profile.health_goal == "maintain"

    @pytest.mark.parametrize("invalid_age", [-1, 0, 9, 121, 200])
    def test_age_outside_10_to_120_raises(self, invalid_age):
        """age ngoài [10, 120] → ValidationError."""
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(age=invalid_age))

    @pytest.mark.parametrize("invalid_weight", [0, 10.0, 29.9, 300.1, 500.0])
    def test_weight_kg_outside_30_to_300_raises(self, invalid_weight):
        """weight_kg < 30 hoặc > 300 → ValidationError."""
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(weight_kg=invalid_weight))

    @pytest.mark.parametrize("invalid_height", [0, 50.0, 99.9, 250.1, 400.0])
    def test_height_cm_outside_100_to_250_raises(self, invalid_height):
        """height_cm ngoài [100, 250] → ValidationError."""
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(height_cm=invalid_height))

    def test_invalid_gender_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(gender="other"))

    def test_invalid_activity_level_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(activity_level="extreme"))

    def test_invalid_health_goal_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(**_valid_user_profile_kwargs(health_goal="bulk_up"))


# ---------------------------------------------------------------------------
# Plan — Requirements 3.4
# ---------------------------------------------------------------------------


class TestPlanValidators:
    """Test ràng buộc end_date - start_date + 1 == duration_days và domain duration_days."""

    def test_valid_plan_duration_matches_dates(self):
        plan = Plan(**_valid_plan_kwargs())
        assert plan.duration_days == 7
        assert (plan.end_date - plan.start_date).days + 1 == plan.duration_days

    def test_valid_plan_three_days(self):
        Plan(**_valid_plan_kwargs(
            start_date=date(2024, 5, 1),
            end_date=date(2024, 5, 3),
            duration_days=3,
        ))

    def test_valid_plan_120_days(self):
        Plan(**_valid_plan_kwargs(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 29),  # 1/1 → 29/4 inclusive = 120 days
            duration_days=120,
        ))

    def test_end_before_start_plus_duration_raises(self):
        """end_date - start_date + 1 < duration_days → ValidationError."""
        with pytest.raises(ValidationError):
            Plan(**_valid_plan_kwargs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),  # 5 ngày
                duration_days=7,
            ))

    def test_end_after_start_plus_duration_raises(self):
        """end_date - start_date + 1 > duration_days → ValidationError."""
        with pytest.raises(ValidationError):
            Plan(**_valid_plan_kwargs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 10),  # 10 ngày
                duration_days=7,
            ))

    def test_off_by_one_at_end_date_raises(self):
        """Off-by-one: end - start + 1 = 8 nhưng duration_days = 7 → fail."""
        with pytest.raises(ValidationError):
            Plan(**_valid_plan_kwargs(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 8),
                duration_days=7,
            ))

    @pytest.mark.parametrize("invalid_duration", [0, 1, 2, 121, 365])
    def test_duration_days_outside_3_to_120_raises(self, invalid_duration):
        """duration_days ngoài [3, 120] → ValidationError."""
        # Đặt end_date sao cho khớp duration_days để không bị fail bởi validator khác.
        from datetime import timedelta

        start = date(2024, 1, 1)
        end = start + timedelta(days=max(invalid_duration - 1, 0))
        with pytest.raises(ValidationError):
            Plan(**_valid_plan_kwargs(
                start_date=start,
                end_date=end,
                duration_days=invalid_duration,
            ))


# ---------------------------------------------------------------------------
# MealPlanPayload — Requirements 3.8
# ---------------------------------------------------------------------------


class TestMealPlanPayloadValidators:
    """Test ràng buộc len(components) >= 1 và |total_calories - sum| <= 1.0."""

    def test_valid_payload_total_matches_sum(self):
        payload = MealPlanPayload(**_valid_meal_plan_payload_kwargs())
        assert payload.total_calories == 500.0
        assert sum(c.calories for c in payload.components) == 500.0

    def test_valid_payload_within_one_kcal_tolerance(self):
        """Sai số đúng 1.0 kcal vẫn được chấp nhận."""
        components = [_component(calories=300.0), _component(calories=200.0)]
        # total_calories lệch 1.0 vẫn ok
        MealPlanPayload(
            meal_type="lunch",
            dish_name="Lunch combo",
            components=components,
            total_calories=501.0,
        )
        MealPlanPayload(
            meal_type="lunch",
            dish_name="Lunch combo",
            components=components,
            total_calories=499.0,
        )

    def test_empty_components_raises(self):
        """len(components) == 0 → ValidationError."""
        with pytest.raises(ValidationError):
            MealPlanPayload(
                meal_type="lunch",
                dish_name="Empty",
                components=[],
                total_calories=0.0,
            )

    def test_total_calories_far_below_sum_raises(self):
        """|total_calories - sum| > 1.0 (total thấp hơn) → ValidationError."""
        components = [_component(calories=300.0), _component(calories=200.0)]
        with pytest.raises(ValidationError):
            MealPlanPayload(
                meal_type="lunch",
                dish_name="Mismatch",
                components=components,
                total_calories=480.0,  # lệch 20 kcal
            )

    def test_total_calories_far_above_sum_raises(self):
        """|total_calories - sum| > 1.0 (total cao hơn) → ValidationError."""
        components = [_component(calories=300.0), _component(calories=200.0)]
        with pytest.raises(ValidationError):
            MealPlanPayload(
                meal_type="lunch",
                dish_name="Mismatch",
                components=components,
                total_calories=520.0,  # lệch 20 kcal
            )

    def test_total_calories_just_above_tolerance_raises(self):
        """Sai số 1.5 kcal (vượt 1.0) → ValidationError."""
        components = [_component(calories=300.0), _component(calories=200.0)]
        with pytest.raises(ValidationError):
            MealPlanPayload(
                meal_type="lunch",
                dish_name="Just over",
                components=components,
                total_calories=501.5,
            )

    def test_single_component_payload_valid(self):
        """len(components) == 1 vẫn hợp lệ."""
        MealPlanPayload(
            meal_type="snack",
            dish_name="Just one",
            components=[_component(calories=150.0)],
            total_calories=150.0,
        )
