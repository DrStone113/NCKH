"""Unit tests for ``services.agent.tools.tdee.calculate_tdee``.

Validates Requirements 4.7 and 3.12 from
``backend/.kiro/specs/chatbot-redesign/requirements.md``:

  - 4.7: With a valid ``UserProfile``, return ``{bmr, tdee, daily_kcal}`` with
    ``daily_kcal`` adjusted by ``activity_level`` and ``health_goal``.
  - 3.12: Reject profiles missing required fields or with out-of-range values
    by raising ``ValueError("INVALID_PROFILE")``.

These are example-based unit tests; property tests for idempotent reads live
in task 4.9 and are out of scope here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow running ``pytest`` from the ``backend/`` directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import UserProfile  # noqa: E402
from services.agent.tool_registry import ToolDescriptor  # noqa: E402
from services.agent.tools.tdee import (  # noqa: E402
    ACTIVITY_MULTIPLIERS,
    HEALTH_GOALS,
    TOOL_DESCRIPTOR,
    calculate_tdee,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(**overrides) -> dict:
    base = {
        "user_id": "u1",
        "age": 30,
        "gender": "male",
        "equation_sex": "male",
        "height_cm": 175.0,
        "weight_kg": 70.0,
        "activity_level": "moderate",
        "health_goal": "maintain",
        "dietary_restrictions": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path — formula correctness (Requirement 4.7)
# ---------------------------------------------------------------------------


def test_male_maintain_moderate_matches_mifflin_st_jeor():
    # BMR(male) = 10*70 + 6.25*175 - 5*30 + 5 = 700 + 1093.75 - 150 + 5 = 1648.75
    # TDEE = 1648.75 * 1.55 = 2555.5625
    # daily_kcal = TDEE + 0
    result = calculate_tdee(UserProfile(**_profile()))
    assert result["bmr"] == 1649.0
    assert result["tdee"] == 2556.0
    assert result["daily_kcal"] == 2556.0


def test_female_lose_weight_sedentary_applies_deficit():
    # BMR(female) = 10*60 + 6.25*165 - 5*28 - 161 = 600 + 1031.25 - 140 - 161 = 1330.25
    # TDEE = 1330.25 * 1.2 = 1596.3
    # policy-v1 deficit = 10% of TDEE (below the 500 kcal cap)
    result = calculate_tdee(
        _profile(
            gender="female",
            equation_sex="female",
            age=28,
            height_cm=165.0,
            weight_kg=60.0,
            activity_level="sedentary",
            health_goal="lose_weight",
        )
    )
    assert result["bmr"] == 1330.0
    assert result["tdee"] == 1596.0
    assert result["daily_kcal"] == 1437.0


def test_gain_muscle_applies_surplus():
    result = calculate_tdee(_profile(health_goal="gain_muscle"))
    assert result["daily_kcal"] == 2811.0


@pytest.mark.parametrize(
    "level,multiplier",
    list(ACTIVITY_MULTIPLIERS.items()),
)
def test_activity_level_multipliers(level, multiplier):
    result = calculate_tdee(_profile(activity_level=level))
    assert result["tdee"] == pytest.approx(1648.75 * multiplier, abs=0.5)


@pytest.mark.parametrize("goal", sorted(HEALTH_GOALS))
def test_health_goal_adjustments(goal):
    result = calculate_tdee(_profile(health_goal=goal))
    expected = {"maintain": 2556.0, "lose_weight": 2300.0, "gain_muscle": 2811.0}[goal]
    assert result["daily_kcal"] == expected


def test_accepts_dict_arguments_directly():
    """Dispatcher passes ``call.arguments`` as a plain dict — must be supported."""
    result = calculate_tdee(_profile())
    assert {"bmr", "tdee", "daily_kcal", "policy_version", "formula_ids"} <= set(result)


def test_accepts_validated_user_profile_instance():
    profile = UserProfile(**_profile())
    result = calculate_tdee(profile)
    assert {"bmr", "tdee", "daily_kcal", "policy_version", "formula_ids"} <= set(result)


def test_structured_safety_profile_flows_through_tool_boundary():
    result = calculate_tdee(
        _profile(nutrition_safety_profile={"pregnancy": "YES"})
    )
    assert result["status"] == "UNSUPPORTED"
    assert result["daily_kcal"] is None
    assert result["safety_profile"]["pregnancy"] == "YES"


def test_unknown_safety_answer_is_not_converted_to_no():
    result = calculate_tdee(
        _profile(nutrition_safety_profile={"pregnancy": "UNKNOWN"})
    )
    assert result["status"] == "READY"
    assert result["safety_profile"]["pregnancy"] == "UNKNOWN"
    assert "SAFETY_SCREENING_INCOMPLETE" in result["warnings"]


# ---------------------------------------------------------------------------
# Validation failures — Requirement 3.12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    [
        "age",
        "height_cm",
        "weight_kg",
        "activity_level",
        "health_goal",
    ],
)
def test_missing_required_field_raises_invalid_profile(missing_field):
    bad = _profile()
    del bad[missing_field]
    with pytest.raises(ValueError, match=r"^INVALID_PROFILE$"):
        calculate_tdee(bad)


@pytest.mark.parametrize("field", ["equation_sex", "gender"])
def test_optional_identity_fields_may_be_omitted(field):
    profile = _profile()
    del profile[field]
    result = calculate_tdee(profile)
    if field == "equation_sex":
        assert result["status"] == "INPUT_UNAVAILABLE"
        assert result["bmr"] is None
        assert any("equation_sex:MISSING" in item for item in result["warnings"])
    else:
        assert result["status"] == "READY"


@pytest.mark.parametrize(
    "field,value",
    [
        ("age", 5),       # below 10
        ("age", 121),     # above 120
        ("height_cm", 99.0),
        ("height_cm", 251.0),
        ("weight_kg", 29.0),
        ("weight_kg", 301.0),
    ],
)
def test_out_of_range_value_raises_invalid_profile(field, value):
    bad = _profile(**{field: value})
    with pytest.raises(ValueError, match=r"^INVALID_PROFILE$"):
        calculate_tdee(bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("equation_sex", "other"),
        ("activity_level", "extreme"),
        ("health_goal", "bulk"),
    ],
)
def test_invalid_enum_raises_invalid_profile(field, value):
    bad = _profile(**{field: value})
    with pytest.raises(ValueError, match=r"^INVALID_PROFILE$"):
        calculate_tdee(bad)


def test_non_mapping_input_raises_invalid_profile():
    with pytest.raises(ValueError, match=r"^INVALID_PROFILE$"):
        calculate_tdee("not a profile")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Descriptor wiring (Requirement 2.5 — registered with side="server")
# ---------------------------------------------------------------------------


def test_tool_descriptor_metadata():
    assert isinstance(TOOL_DESCRIPTOR, ToolDescriptor)
    assert TOOL_DESCRIPTOR.name == "calculate_tdee"
    assert TOOL_DESCRIPTOR.side == "server"
    assert TOOL_DESCRIPTOR.idempotent is True
    assert TOOL_DESCRIPTOR.fn is calculate_tdee


def test_tool_descriptor_schema_matches_user_profile():
    schema = TOOL_DESCRIPTOR.parameters_schema
    assert schema["type"] == "object"
    required = set(schema["required"])
    assert {
        "user_id",
        "age",
        "height_cm",
        "weight_kg",
        "activity_level",
        "health_goal",
    }.issubset(required)
    props = schema["properties"]
    assert props["age"]["minimum"] == 10 and props["age"]["maximum"] == 120
    assert props["height_cm"]["minimum"] == 100 and props["height_cm"]["maximum"] == 250
    assert props["weight_kg"]["minimum"] == 30 and props["weight_kg"]["maximum"] == 300
    assert props["gender"]["type"] == ["string", "null"]
    assert set(props["equation_sex"]["enum"]) == {"male", "female", None}
    assert set(props["activity_level"]["enum"]) == set(ACTIVITY_MULTIPLIERS.keys())
    assert set(props["health_goal"]["enum"]) == set(HEALTH_GOALS)


def test_tool_descriptor_schema_validates_via_registry():
    """Round-trip: a valid UserProfile dict must pass ToolRegistry.validate
    and an invalid one must fail with ``INVALID_ARGS`` (Requirement 1.1)."""
    from services.agent.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(TOOL_DESCRIPTOR)

    ok, err = registry.validate("calculate_tdee", _profile())
    assert (ok, err) == (True, None)

    ok, err = registry.validate("calculate_tdee", {"age": 30})  # missing fields
    assert ok is False
    assert err == "INVALID_ARGS"

    ok, err = registry.validate("calculate_tdee", _profile(age=5))
    assert ok is False
    assert err == "INVALID_ARGS"
