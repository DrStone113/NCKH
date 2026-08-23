from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.nutrition.calculator import (
    CanonicalNutritionInput,
    CanonicalValue,
    calculate_canonical_nutrition,
)


_ROOT_GOLDEN = next(
    (
        parent / "contracts" / "nutrition_policy_v1_0_1_golden.json"
        for parent in Path(__file__).resolve().parents
        if (parent / "contracts" / "nutrition_policy_v1_0_1_golden.json").is_file()
    ),
    None,
)
GOLDEN_PATH = _ROOT_GOLDEN or (
    Path(__file__).resolve().parents[1]
    / "services"
    / "nutrition"
    / "nutrition_policy_v1_0_1_golden.json"
)


def test_packaged_and_shared_golden_contracts_match() -> None:
    packaged = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "nutrition"
        / "nutrition_policy_v1_0_1_golden.json"
    )
    if _ROOT_GOLDEN is not None:
        assert json.loads(packaged.read_text(encoding="utf-8")) == json.loads(
            _ROOT_GOLDEN.read_text(encoding="utf-8")
        )


@pytest.mark.parametrize("case", json.loads(GOLDEN_PATH.read_text(encoding="utf-8")))
def test_backend_matches_shared_flutter_golden(case: dict) -> None:
    raw = case["input"]
    state = calculate_canonical_nutrition(
        CanonicalNutritionInput(
            age=CanonicalValue.known(raw["age"]),
            equation_sex=CanonicalValue.known(raw["equation_sex"]),
            height_cm=CanonicalValue.known(raw["height_cm"]),
            weight_kg=CanonicalValue.known(raw["weight_kg"]),
            activity_level=CanonicalValue.known(raw["activity_level"]),
            health_goal=CanonicalValue.known(raw["health_goal"]),
        )
    )
    expected = case["expected"]
    assert state.status.value == expected["status"]
    assert state.bmi == pytest.approx(expected["bmi"])
    assert state.bmi_classification == expected["bmi_classification"]
    assert state.estimated_rmr_kcal_per_day == pytest.approx(expected["rmr"])
    assert state.estimated_tdee_kcal_per_day == pytest.approx(expected["tdee"])
    if expected["target"] is None:
        assert state.calorie_target_kcal_per_day is None
    else:
        assert state.calorie_target_kcal_per_day == pytest.approx(expected["target"])
    if expected["adjustment"] is None:
        assert state.energy_adjustment_kcal_per_day is None
    else:
        assert state.energy_adjustment_kcal_per_day == pytest.approx(expected["adjustment"])
    if expected["protein_planning"] is None:
        assert state.protein is None
    else:
        assert state.protein is not None
        assert state.protein.planning_g_per_day == pytest.approx(expected["protein_planning"])
    assert state.fluid is not None
    assert state.fluid.approximate_fluid_goal_ml_per_day == pytest.approx(expected["fluid_ml"])
