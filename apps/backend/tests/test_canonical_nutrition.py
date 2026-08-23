from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from services.agent.context_trace import ContextTraceRecorder
from services.nutrition.calculator import (
    CalorieTargetStatus,
    CanonicalNutritionInput,
    CanonicalValue,
    ConsumedMealNutrition,
    InputStatus,
    NutritionStatus,
    NutritionSafetyProfile,
    RangeStatus,
    SafetyAnswer,
    calculate_canonical_nutrition,
    summarize_daily_nutrition,
)
from services.nutrition.registry import FORMULA_REGISTRY, POLICY_VERSION


def _input(**overrides) -> CanonicalNutritionInput:
    values = {
        "age": CanonicalValue.known(30),
        "equation_sex": CanonicalValue.known("male"),
        "height_cm": CanonicalValue.known(175.0),
        "weight_kg": CanonicalValue.known(70.0),
        "activity_level": CanonicalValue.known("moderate"),
        "health_goal": CanonicalValue.known("maintain"),
        "unsupported_reasons": (),
    }
    values.update(overrides)
    return CanonicalNutritionInput(**values)


@pytest.mark.parametrize(
    ("bmi", "expected"),
    [
        (18.4999, "Thiếu cân"),
        (18.5, "Bình thường"),
        (22.9999, "Bình thường"),
        (23.0, "Thừa cân"),
        (24.9999, "Thừa cân"),
        (25.0, "Béo phì độ I"),
        (29.9999, "Béo phì độ I"),
        (30.0, "Béo phì độ II"),
    ],
)
def test_bmi_cutoffs_use_unrounded_value(bmi, expected):
    height_cm = 200.0
    state = calculate_canonical_nutrition(
        _input(
            height_cm=CanonicalValue.known(height_cm),
            weight_kg=CanonicalValue.known(bmi * 4.0),
        )
    )
    assert state.bmi == pytest.approx(bmi)
    assert state.bmi_classification == expected


def test_rounding_v1_is_half_up_but_classification_uses_raw_bmi():
    state = calculate_canonical_nutrition(
        _input(
            height_cm=CanonicalValue.known(100.0),
            weight_kg=CanonicalValue.known(18.505),
        )
    )
    assert state.to_dict()["bmi"] == 18.51
    assert state.bmi_classification == "Bình thường"


@pytest.mark.parametrize(
    ("sex", "expected"),
    [("male", 1648.75), ("female", 1482.75)],
)
def test_mifflin_equations_require_explicit_equation_sex(sex, expected):
    state = calculate_canonical_nutrition(
        _input(equation_sex=CanonicalValue.known(sex))
    )
    assert state.estimated_rmr_kcal_per_day == pytest.approx(expected)


def test_unknown_equation_sex_has_no_fallback():
    state = calculate_canonical_nutrition(
        _input(equation_sex=CanonicalValue.known("unknown"))
    )
    assert state.status is NutritionStatus.INPUT_UNAVAILABLE
    assert state.estimated_rmr_kcal_per_day is None
    assert state.input_conflicts == ("equation_sex",)


@pytest.mark.parametrize(
    ("level", "factor"),
    [
        ("sedentary", 1.2),
        ("light", 1.375),
        ("moderate", 1.55),
        ("active", 1.725),
        ("very_active", 1.9),
    ],
)
def test_all_activity_categories(level, factor):
    state = calculate_canonical_nutrition(
        _input(activity_level=CanonicalValue.known(level))
    )
    assert state.activity_category == level
    assert state.activity_factor == factor
    assert state.estimated_tdee_kcal_per_day == pytest.approx(1648.75 * factor)


@pytest.mark.parametrize(
    ("goal", "expected_adjustment"),
    [
        ("maintain", 0.0),
        ("lose_weight", -255.55625),
        ("gain_muscle", 255.55625),
    ],
)
def test_maintain_loss_and_gain_use_approved_adjustment(goal, expected_adjustment):
    state = calculate_canonical_nutrition(
        _input(health_goal=CanonicalValue.known(goal))
    )
    assert state.energy_adjustment_kcal_per_day == pytest.approx(expected_adjustment)
    assert state.calorie_target_kcal_per_day == pytest.approx(
        state.estimated_tdee_kcal_per_day + expected_adjustment
    )


def test_loss_and_gain_caps():
    high = _input(
        age=CanonicalValue.known(19),
        height_cm=CanonicalValue.known(250.0),
        weight_kg=CanonicalValue.known(300.0),
        activity_level=CanonicalValue.known("very_active"),
    )
    loss = calculate_canonical_nutrition(
        replace(high, health_goal=CanonicalValue.known("lose_weight"))
    )
    gain = calculate_canonical_nutrition(
        replace(high, health_goal=CanonicalValue.known("gain_muscle"))
    )
    assert loss.energy_adjustment_kcal_per_day == -500.0
    assert gain.energy_adjustment_kcal_per_day == 300.0


def test_low_energy_gate_does_not_clamp_or_return_target():
    state = calculate_canonical_nutrition(
        _input(
            age=CanonicalValue.known(64),
            equation_sex=CanonicalValue.known("female"),
            height_cm=CanonicalValue.known(100.0),
            weight_kg=CanonicalValue.known(30.0),
            activity_level=CanonicalValue.known("sedentary"),
            health_goal=CanonicalValue.known("lose_weight"),
        )
    )
    assert state.status is NutritionStatus.REQUIRES_SPECIALIST_GUIDANCE
    assert state.calorie_target_status is CalorieTargetStatus.REQUIRES_SPECIALIST_GUIDANCE
    assert state.calorie_target_kcal_per_day is None
    assert state.carbohydrate_range_g_per_day is None
    assert state.fat_range_g_per_day is None


@pytest.mark.parametrize(
    ("goal", "activity", "branch", "minimum", "maximum", "planning"),
    [
        ("maintain", "sedentary", "sedentary_maintenance", 0.8, 1.0, 0.9),
        ("maintain", "light", "active_maintenance", 1.2, 1.4, 1.3),
        ("lose_weight", "sedentary", "weight_loss", 1.4, 1.6, 1.5),
        ("gain_muscle", "active", "gain_resistance", 1.4, 1.8, 1.6),
    ],
)
def test_protein_branches(goal, activity, branch, minimum, maximum, planning):
    state = calculate_canonical_nutrition(
        _input(
            health_goal=CanonicalValue.known(goal),
            activity_level=CanonicalValue.known(activity),
        )
    )
    assert state.protein is not None
    assert state.protein.branch == branch
    assert state.protein.reference_minimum_g_per_kg == 0.8
    assert state.protein.recommended_g_per_kg.minimum == minimum
    assert state.protein.recommended_g_per_kg.maximum == maximum
    assert state.protein.planning_g_per_kg == planning
    assert state.protein.planning_g_per_day == pytest.approx(planning * 70)


def test_carb_and_fat_ranges_derive_from_canonical_energy():
    state = calculate_canonical_nutrition(_input())
    energy = state.calorie_target_kcal_per_day
    assert energy is not None
    assert state.carbohydrate_range_g_per_day.minimum == pytest.approx(energy * 0.45 / 4)
    assert state.carbohydrate_range_g_per_day.maximum == pytest.approx(energy * 0.65 / 4)
    assert state.fat_range_g_per_day.minimum == pytest.approx(energy * 0.20 / 9)
    assert state.fat_range_g_per_day.maximum == pytest.approx(energy * 0.35 / 9)


@pytest.mark.parametrize("status", [InputStatus.MISSING, InputStatus.NOT_LOADED, InputStatus.STALE, InputStatus.ERROR])
def test_unavailable_input_statuses_are_not_defaulted(status):
    state = calculate_canonical_nutrition(
        _input(age=CanonicalValue.unavailable(status))
    )
    assert state.status is NutritionStatus.INPUT_UNAVAILABLE
    assert state.estimated_rmr_kcal_per_day is None
    assert any(status.value in warning for warning in state.warnings)


def test_conflicting_input_is_reported_and_not_used():
    state = calculate_canonical_nutrition(
        _input(
            weight_kg=CanonicalValue(
                value=70.0,
                source="profile",
                status=InputStatus.CONFLICT,
                conflict={"reason": "two weights"},
            )
        )
    )
    assert state.status is NutritionStatus.INPUT_UNAVAILABLE
    assert state.input_conflicts == ("weight_kg",)
    assert state.bmi is None


def test_unsupported_age_and_legacy_clinical_reason_return_no_prescriptive_targets():
    age_state = calculate_canonical_nutrition(_input(age=CanonicalValue.known(18)))
    clinical_state = calculate_canonical_nutrition(
        _input(unsupported_reasons=("SERIOUS_RENAL_DISEASE",))
    )
    for state in (age_state, clinical_state):
        assert state.status is NutritionStatus.UNSUPPORTED
        assert state.calorie_target_kcal_per_day is None
        assert state.protein is None
        assert state.fluid is None


@pytest.mark.parametrize(
    ("age", "expected_status"),
    [
        (18, NutritionStatus.UNSUPPORTED),
        (19, NutritionStatus.READY),
        (64, NutritionStatus.READY),
        (65, NutritionStatus.UNSUPPORTED),
    ],
)
def test_supported_population_age_boundaries(age, expected_status):
    state = calculate_canonical_nutrition(_input(age=CanonicalValue.known(age)))
    assert state.status is expected_status
    if expected_status is NutritionStatus.UNSUPPORTED:
        assert state.calorie_target_kcal_per_day is None
        assert state.protein is None
        assert state.fluid is None
    else:
        assert state.calorie_target_kcal_per_day is not None


@pytest.mark.parametrize(
    "reason",
    [
        "PREGNANCY",
        "LACTATION",
        "EATING_DISORDER_RISK",
        "SERIOUS_RENAL_DISEASE",
        "FLUID_RESTRICTED_CARDIAC_DISEASE",
        "CLINICALLY_COMPLEX_METABOLIC_DISEASE",
    ],
)
def test_structured_safety_yes_never_returns_prescriptive_targets(reason):
    field = {
        "PREGNANCY": "pregnancy",
        "LACTATION": "lactation",
        "EATING_DISORDER_RISK": "eating_disorder_risk_or_history",
        "SERIOUS_RENAL_DISEASE": "serious_renal_condition",
        "FLUID_RESTRICTED_CARDIAC_DISEASE": "fluid_restricted_cardiac_condition",
        "CLINICALLY_COMPLEX_METABOLIC_DISEASE": "clinically_complex_metabolic_condition",
    }[reason]
    state = calculate_canonical_nutrition(
        _input(safety_profile=NutritionSafetyProfile(**{field: SafetyAnswer.YES}))
    )
    assert state.status is NutritionStatus.UNSUPPORTED
    assert state.unsupported_reasons == (f"SAFETY_PROFILE:{field.upper()}",)
    assert state.calorie_target_kcal_per_day is None
    assert state.protein is None
    assert state.carbohydrate_range_g_per_day is None
    assert state.fat_range_g_per_day is None
    assert state.fluid is None


def test_unknown_safety_is_preserved_and_target_remains_available_with_warning():
    state = calculate_canonical_nutrition(
        _input(
            safety_profile=NutritionSafetyProfile(
                pregnancy=SafetyAnswer.UNKNOWN,
                lactation=SafetyAnswer.NO,
                eating_disorder_risk_or_history=SafetyAnswer.NO,
                serious_renal_condition=SafetyAnswer.NO,
                fluid_restricted_cardiac_condition=SafetyAnswer.NO,
                clinically_complex_metabolic_condition=SafetyAnswer.NO,
            )
        )
    )
    assert state.status is NutritionStatus.READY
    assert state.calorie_target_kcal_per_day is not None
    assert state.safety_profile.pregnancy is SafetyAnswer.UNKNOWN
    assert "SAFETY_SCREENING_INCOMPLETE" in state.warnings


@pytest.mark.parametrize(
    ("bmi", "expected_status"),
    [
        (18.49, NutritionStatus.REQUIRES_SPECIALIST_GUIDANCE),
        (18.50, NutritionStatus.READY),
    ],
)
def test_underweight_boundary_has_versioned_specialist_gate(bmi, expected_status):
    state = calculate_canonical_nutrition(
        _input(
            height_cm=CanonicalValue.known(200.0),
            weight_kg=CanonicalValue.known(bmi * 4.0),
        )
    )
    assert state.status is expected_status
    assert state.estimated_rmr_kcal_per_day is not None
    assert state.estimated_tdee_kcal_per_day is not None
    assert state.fluid is not None
    if bmi < 18.5:
        assert state.calorie_target_status is CalorieTargetStatus.REQUIRES_SPECIALIST_GUIDANCE
        assert state.calorie_target_kcal_per_day is None
        assert state.energy_adjustment_kcal_per_day is None
        assert state.protein is None
        assert state.carbohydrate_range_g_per_day is None
        assert state.fat_range_g_per_day is None
    else:
        assert state.calorie_target_kcal_per_day is not None


def test_ordinary_target_below_1200_requires_specialist_without_a_target():
    state = calculate_canonical_nutrition(
        _input(
            age=CanonicalValue.known(64),
            equation_sex=CanonicalValue.known("female"),
            height_cm=CanonicalValue.known(150.0),
            weight_kg=CanonicalValue.known(40.0),
            activity_level=CanonicalValue.known("sedentary"),
            health_goal=CanonicalValue.known("lose_weight"),
        )
    )
    assert state.status is NutritionStatus.REQUIRES_SPECIALIST_GUIDANCE
    assert state.calorie_target_status is CalorieTargetStatus.REQUIRES_SPECIALIST_GUIDANCE
    assert state.calorie_target_kcal_per_day is None
    assert state.carbohydrate_range_g_per_day is None
    assert state.fat_range_g_per_day is None


def test_fluid_goal_has_required_heuristic_metadata():
    fluid = calculate_canonical_nutrition(_input()).fluid
    assert fluid is not None
    assert fluid.approximate_fluid_goal_ml_per_day == 2310.0
    assert fluid.status == "HEURISTIC"
    assert fluid.is_physiological_requirement is False
    assert fluid.includes_food_water is False
    assert fluid.climate_adjusted is False
    assert fluid.exercise_adjusted is False


def test_daily_summary_preserves_authoritative_known_zero():
    canonical = calculate_canonical_nutrition(_input())
    summary = summarize_daily_nutrition(
        CanonicalValue.known(tuple(), source="authoritative.consumed_meals"),
        canonical,
    )
    assert summary.status is InputStatus.KNOWN
    assert summary.energy_consumed_kcal == 0
    assert summary.energy_remaining_kcal == canonical.calorie_target_kcal_per_day
    assert summary.over_target is False
    assert summary.protein_status is RangeStatus.BELOW_RANGE
    payload = summary.to_dict()
    assert payload["policy_version"] == "nutrition-policy-v1.0.1"
    assert "DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1" in payload["formula_ids"]
    assert all(
        item["policy_version"] == "nutrition-policy-v1.0.1"
        for item in payload["formula_provenance"]
    )


def test_daily_summary_ignores_planned_and_does_not_clamp_over_target():
    canonical = calculate_canonical_nutrition(_input())
    target = canonical.calorie_target_kcal_per_day
    assert target is not None
    summary = summarize_daily_nutrition(
        CanonicalValue.known(
            (
                ConsumedMealNutrition(target + 100, 200, 500, 100),
                ConsumedMealNutrition(999, 999, 999, 999, record_status="PLANNED"),
            )
        ),
        canonical,
    )
    assert summary.energy_consumed_kcal == pytest.approx(target + 100)
    assert summary.energy_remaining_kcal == pytest.approx(-100)
    assert summary.over_target is True
    assert summary.energy_status is RangeStatus.ABOVE_RANGE


def test_daily_summary_preserves_missing_state():
    summary = summarize_daily_nutrition(
        CanonicalValue.unavailable(InputStatus.NOT_LOADED),
        calculate_canonical_nutrition(_input()),
    )
    assert summary.status is InputStatus.NOT_LOADED
    assert summary.energy_consumed_kcal is None


def test_formula_registry_is_versioned_and_immutable():
    assert POLICY_VERSION == "nutrition-policy-v1.0.1"
    assert FORMULA_REGISTRY["TDEE_ACTIVITY_FACTOR_V1"].status == "HEURISTIC"
    assert FORMULA_REGISTRY["APPROXIMATE_FLUID_33MLKG_V1"].limitations
    with pytest.raises(TypeError):
        FORMULA_REGISTRY["NEW"] = FORMULA_REGISTRY["BMI_CALC_V1"]  # type: ignore[index]


def test_v1_0_1_preserves_v1_mathematical_rules_as_a_separate_artifact():
    policy_dir = Path(__file__).resolve().parents[1] / "services/nutrition"
    original = json.loads(
        (policy_dir / "nutrition_policy_v1.json").read_text(encoding="utf-8")
    )
    patch = json.loads(
        (policy_dir / "nutrition_policy_v1_0_1.json").read_text(encoding="utf-8")
    )
    assert original["policy_version"] == "nutrition-policy-v1"
    assert patch["base_policy_version"] == original["policy_version"]
    assert patch["compatibility_patch"]["mathematical_rules_changed"] is False
    for key in (
        "supported_age",
        "rmr",
        "activity",
        "calories",
        "protein",
        "carbohydrate",
        "fat",
        "fluid",
        "meal_split",
        "rounding",
    ):
        assert patch[key] == original[key]
    assert patch["bmi"]["boundaries"] == original["bmi"]["boundaries"]
    assert patch["bmi"]["labels"] == original["bmi"]["labels"]


def test_context_trace_captures_formula_provenance():
    recorder = ContextTraceRecorder("nutrition context", enabled=True)
    recorder.capture_initial_context(
        {
            "state_manifest": {},
            "calculation_manifest": {
                "inputs": {"weight_kg": 70},
                "outputs": {"policy_version": "nutrition-policy-v1.0.1"},
                "formula_provenance": [
                    {
                        "formula_id": "RMR_MIFFLIN_ST_JEOR_V1",
                        "policy_version": "nutrition-policy-v1.0.1",
                    }
                ],
            },
        }
    )
    assert recorder.trace.calculation_provenance[0]["formula_id"] == (
        "RMR_MIFFLIN_ST_JEOR_V1"
    )


def test_context_trace_captures_daily_summary_policy_without_state_manifest():
    recorder = ContextTraceRecorder("nutrition context", enabled=True)
    recorder.capture_initial_context(
        {
            "calculation_manifest": {
                "outputs": {
                    "daily_nutrition_summary": {
                        "policy_version": "nutrition-policy-v1.0.1",
                        "formula_ids": [
                            "DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1"
                        ],
                    }
                },
                "formula_provenance": [
                    {
                        "formula_id": "DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1",
                        "policy_version": "nutrition-policy-v1.0.1",
                    }
                ],
            }
        }
    )
    assert recorder.trace.calculation_outputs["daily_nutrition_summary"][
        "policy_version"
    ] == "nutrition-policy-v1.0.1"
    assert recorder.trace.calculation_provenance[0]["formula_id"] == (
        "DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1"
    )


def test_rounding_v1_display_boundaries_use_half_up():
    state = calculate_canonical_nutrition(_input())
    display = state.to_display_dict()
    assert display["bmi"] == 22.9
    assert display["estimated_rmr_kcal_per_day"] == 1650.0
    assert display["approximate_fluid_goal_ml_per_day"] == 2300.0
