"""
TDEE (Total Daily Energy Expenditure) calculator using Mifflin-St Jeor formula.
Pure functions — no side effects, no I/O.
"""

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

GOAL_ADJUSTMENTS = {
    "lose_weight": -500,   # calorie deficit
    "maintain": 0,
    "gain_muscle": +300,   # calorie surplus
}

MINIMUM_SAFE_CALORIES = 1200.0


def calculate_bmr(age: int, gender: str, height_cm: float, weight_kg: float) -> float:
    """
    Calculate Basal Metabolic Rate using Mifflin-St Jeor formula.

    Male:   10*weight + 6.25*height - 5*age + 5
    Female: 10*weight + 6.25*height - 5*age - 161

    Args:
        age: Age in years.
        gender: "male" or "female".
        height_cm: Height in centimetres.
        weight_kg: Weight in kilograms.

    Returns:
        BMR in kcal/day.

    Raises:
        ValueError: If gender is not "male" or "female".
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        return base + 5
    elif gender == "female":
        return base - 161
    else:
        raise ValueError(f"Invalid gender '{gender}'. Must be 'male' or 'female'.")


def calculate_tdee(bmr: float, activity_level: str) -> float:
    """
    Calculate Total Daily Energy Expenditure.

    Args:
        bmr: Basal Metabolic Rate in kcal/day.
        activity_level: One of the keys in ACTIVITY_MULTIPLIERS.

    Returns:
        TDEE in kcal/day.

    Raises:
        ValueError: If activity_level is not a recognised key.
    """
    if activity_level not in ACTIVITY_MULTIPLIERS:
        valid = ", ".join(ACTIVITY_MULTIPLIERS.keys())
        raise ValueError(
            f"Invalid activity_level '{activity_level}'. Must be one of: {valid}."
        )
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def get_recommended_calories(tdee: float, health_goal: str) -> float:
    """
    Adjust TDEE based on the user's health goal and enforce a minimum safe intake.

    Args:
        tdee: Total Daily Energy Expenditure in kcal/day.
        health_goal: One of the keys in GOAL_ADJUSTMENTS.

    Returns:
        Recommended daily calorie intake (>= 1200 kcal).

    Raises:
        ValueError: If health_goal is not a recognised key.
    """
    if health_goal not in GOAL_ADJUSTMENTS:
        valid = ", ".join(GOAL_ADJUSTMENTS.keys())
        raise ValueError(
            f"Invalid health_goal '{health_goal}'. Must be one of: {valid}."
        )
    result = tdee + GOAL_ADJUSTMENTS[health_goal]
    return max(result, MINIMUM_SAFE_CALORIES)
