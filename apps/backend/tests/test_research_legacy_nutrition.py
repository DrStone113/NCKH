"""Regression lock for historical research nutrition behaviour."""

from __future__ import annotations

import ast
import inspect

import pytest

import services.experiment.legacy_nutrition as legacy_nutrition
from services.experiment.legacy_nutrition import (
    LEGACY_ACTIVITY_MULTIPLIERS,
    LEGACY_GOAL_ADJUSTMENTS,
    RESEARCH_NUTRITION_POLICY_VERSION,
    calculate_tdee_research_legacy_v1,
)


def test_research_legacy_policy_identity_is_frozen():
    assert RESEARCH_NUTRITION_POLICY_VERSION == "research-legacy-v1"
    assert dict(LEGACY_ACTIVITY_MULTIPLIERS) == {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    with pytest.raises(TypeError):
        LEGACY_ACTIVITY_MULTIPLIERS["sedentary"] = 9.9  # type: ignore[index]
    with pytest.raises(TypeError):
        LEGACY_GOAL_ADJUSTMENTS["maintain"] = 9.9  # type: ignore[index]


def test_research_legacy_import_graph_is_isolated_from_production_calculator():
    tree = ast.parse(inspect.getsource(legacy_nutrition))
    dependencies = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    dependencies.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert dependencies == {"__future__", "types"}
    assert not any(
        dependency.startswith("services.nutrition")
        for dependency in dependencies
    )


@pytest.mark.parametrize(
    ("activity_level", "factor"),
    [
        ("sedentary", 1.2),
        ("light", 1.375),
        ("moderate", 1.55),
        ("active", 1.725),
        ("very_active", 1.9),
    ],
)
def test_research_legacy_activity_outputs_are_invariant(activity_level, factor):
    result = calculate_tdee_research_legacy_v1(
        age=30,
        sex="male",
        height_cm=175,
        weight_kg=70,
        activity_level=activity_level,
        goal="maintain",
    )
    assert result == {
        "bmr": 1648.75,
        "tdee": 1648.75 * factor,
        "daily_kcal": 1648.75 * factor,
    }


@pytest.mark.parametrize(
    ("goal", "adjustment"),
    [("lose_weight", -500.0), ("maintain", 0.0), ("gain_muscle", 300.0)],
)
def test_research_legacy_goal_outputs_are_invariant(goal, adjustment):
    result = calculate_tdee_research_legacy_v1(
        age=28,
        sex="female",
        height_cm=165,
        weight_kg=60,
        activity_level="sedentary",
        goal=goal,
    )
    assert result["bmr"] == 1330.25
    assert result["tdee"] == pytest.approx(1596.3)
    assert result["daily_kcal"] == pytest.approx(1596.3 + adjustment)


def test_research_legacy_preserves_raw_float_and_return_shape():
    result = calculate_tdee_research_legacy_v1(
        age=31,
        sex="female",
        height_cm=163,
        weight_kg=57,
        activity_level="light",
        goal="lose_weight",
    )
    expected_bmr = 1272.75
    expected_tdee = expected_bmr * 1.375
    assert result == {
        "bmr": expected_bmr,
        "tdee": expected_tdee,
        "daily_kcal": expected_tdee - 500.0,
    }
    assert result["tdee"] != round(result["tdee"])
