"""Canonical deterministic calculator for approved ``nutrition-policy-v1.0.1``."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Generic, TypeVar

from .registry import POLICY, POLICY_VERSION, formula_provenance


T = TypeVar("T")


class InputStatus(str, Enum):
    KNOWN = "KNOWN"
    MISSING = "MISSING"
    NOT_LOADED = "NOT_LOADED"
    STALE = "STALE"
    ERROR = "ERROR"
    CONFLICT = "CONFLICT"


class NutritionStatus(str, Enum):
    READY = "READY"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    REQUIRES_SPECIALIST_GUIDANCE = "REQUIRES_SPECIALIST_GUIDANCE"


class CalorieTargetStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_SPECIALIST_GUIDANCE = "REQUIRES_SPECIALIST_GUIDANCE"


class RangeStatus(str, Enum):
    BELOW_RANGE = "BELOW_RANGE"
    WITHIN_RANGE = "WITHIN_RANGE"
    ABOVE_RANGE = "ABOVE_RANGE"
    UNAVAILABLE = "UNAVAILABLE"


class SafetyAnswer(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"


@dataclass(frozen=True, slots=True)
class NutritionSafetyProfile:
    """Self-reported applicability facts; values are never inferred."""

    pregnancy: SafetyAnswer = SafetyAnswer.NOT_PROVIDED
    lactation: SafetyAnswer = SafetyAnswer.NOT_PROVIDED
    eating_disorder_risk_or_history: SafetyAnswer = SafetyAnswer.NOT_PROVIDED
    serious_renal_condition: SafetyAnswer = SafetyAnswer.NOT_PROVIDED
    fluid_restricted_cardiac_condition: SafetyAnswer = SafetyAnswer.NOT_PROVIDED
    clinically_complex_metabolic_condition: SafetyAnswer = SafetyAnswer.NOT_PROVIDED

    def to_dict(self) -> dict[str, str]:
        return {
            name: getattr(self, name).value
            for name in _SAFETY_FIELD_NAMES
        }

    @property
    def affirmative_reasons(self) -> tuple[str, ...]:
        return tuple(
            f"SAFETY_PROFILE:{name.upper()}"
            for name in _SAFETY_FIELD_NAMES
            if getattr(self, name) is SafetyAnswer.YES
        )

    @property
    def has_incomplete_answers(self) -> bool:
        return any(
            getattr(self, name) in {SafetyAnswer.UNKNOWN, SafetyAnswer.NOT_PROVIDED}
            for name in _SAFETY_FIELD_NAMES
        )


_SAFETY_FIELD_NAMES = (
    "pregnancy",
    "lactation",
    "eating_disorder_risk_or_history",
    "serious_renal_condition",
    "fluid_restricted_cardiac_condition",
    "clinically_complex_metabolic_condition",
)


@dataclass(frozen=True, slots=True)
class CanonicalValue(Generic[T]):
    value: T | None
    source: str
    status: InputStatus
    observed_at: str | None = None
    conflict: dict[str, object] | None = None

    @classmethod
    def known(cls, value: T, *, source: str = "explicit_input") -> "CanonicalValue[T]":
        return cls(value=value, source=source, status=InputStatus.KNOWN)

    @classmethod
    def unavailable(
        cls, status: InputStatus, *, source: str = "unknown"
    ) -> "CanonicalValue[T]":
        if status is InputStatus.KNOWN:
            raise ValueError("KNOWN requires a value")
        return cls(value=None, source=source, status=status)


@dataclass(frozen=True, slots=True)
class CanonicalNutritionInput:
    age: CanonicalValue[int]
    equation_sex: CanonicalValue[str]
    height_cm: CanonicalValue[float]
    weight_kg: CanonicalValue[float]
    activity_level: CanonicalValue[str]
    health_goal: CanonicalValue[str]
    safety_profile: NutritionSafetyProfile = field(default_factory=NutritionSafetyProfile)
    unsupported_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NumericRange:
    minimum: float
    maximum: float

    def to_dict(self, *, decimals: int) -> dict[str, float]:
        return {
            "minimum": _round_half_up(self.minimum, decimals),
            "maximum": _round_half_up(self.maximum, decimals),
        }


@dataclass(frozen=True, slots=True)
class ProteinRecommendation:
    branch: str
    reference_minimum_g_per_kg: float
    recommended_g_per_kg: NumericRange
    planning_g_per_kg: float
    reference_minimum_g_per_day: float
    recommended_g_per_day: NumericRange
    planning_g_per_day: float

    def to_dict(self) -> dict[str, object]:
        decimals = int(POLICY["rounding"]["macro_storage_decimals"])
        return {
            "branch": self.branch,
            "reference_minimum_g_per_kg": self.reference_minimum_g_per_kg,
            "recommended_g_per_kg": self.recommended_g_per_kg.to_dict(
                decimals=1
            ),
            "planning_g_per_kg": self.planning_g_per_kg,
            "reference_minimum_g_per_day": _round_half_up(
                self.reference_minimum_g_per_day, decimals
            ),
            "recommended_g_per_day": self.recommended_g_per_day.to_dict(
                decimals=decimals
            ),
            "planning_g_per_day": _round_half_up(
                self.planning_g_per_day, decimals
            ),
        }


@dataclass(frozen=True, slots=True)
class FluidGoal:
    approximate_fluid_goal_ml_per_day: float
    status: str = "HEURISTIC"
    is_physiological_requirement: bool = False
    includes_food_water: bool = False
    climate_adjusted: bool = False
    exercise_adjusted: bool = False

    def to_dict(self) -> dict[str, object]:
        decimals = int(POLICY["rounding"]["fluid_storage_decimals_ml"])
        return {
            "approximate_fluid_goal_ml_per_day": _round_half_up(
                self.approximate_fluid_goal_ml_per_day, decimals
            ),
            "status": self.status,
            "is_physiological_requirement": self.is_physiological_requirement,
            "includes_food_water": self.includes_food_water,
            "climate_adjusted": self.climate_adjusted,
            "exercise_adjusted": self.exercise_adjusted,
        }


@dataclass(frozen=True, slots=True)
class CanonicalNutritionState:
    status: NutritionStatus
    bmi: float | None = None
    bmi_classification_code: str | None = None
    bmi_classification: str | None = None
    estimated_rmr_kcal_per_day: float | None = None
    estimated_tdee_kcal_per_day: float | None = None
    activity_category: str | None = None
    activity_factor: float | None = None
    calorie_target_status: CalorieTargetStatus = CalorieTargetStatus.UNAVAILABLE
    calorie_target_kcal_per_day: float | None = None
    energy_adjustment_kcal_per_day: float | None = None
    protein: ProteinRecommendation | None = None
    carbohydrate_range_g_per_day: NumericRange | None = None
    fat_range_g_per_day: NumericRange | None = None
    fluid: FluidGoal | None = None
    warnings: tuple[str, ...] = ()
    unsupported_reasons: tuple[str, ...] = ()
    input_conflicts: tuple[str, ...] = ()
    safety_profile: NutritionSafetyProfile = field(default_factory=NutritionSafetyProfile)
    policy_version: str = POLICY_VERSION
    formula_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        energy_decimals = int(POLICY["rounding"]["energy_storage_decimals"])
        macro_decimals = int(POLICY["rounding"]["macro_storage_decimals"])
        return {
            "status": self.status.value,
            "bmi": (
                _round_half_up(
                    self.bmi, int(POLICY["rounding"]["bmi_storage_decimals"])
                )
                if self.bmi is not None
                else None
            ),
            "bmi_classification_code": self.bmi_classification_code,
            "bmi_classification": self.bmi_classification,
            "estimated_rmr_kcal_per_day": _optional_round(
                self.estimated_rmr_kcal_per_day, energy_decimals
            ),
            "estimated_tdee_kcal_per_day": _optional_round(
                self.estimated_tdee_kcal_per_day, energy_decimals
            ),
            "activity_category": self.activity_category,
            "activity_factor": self.activity_factor,
            "calorie_target_status": self.calorie_target_status.value,
            "calorie_target_kcal_per_day": _optional_round(
                self.calorie_target_kcal_per_day, energy_decimals
            ),
            "energy_adjustment_kcal_per_day": _optional_round(
                self.energy_adjustment_kcal_per_day, energy_decimals
            ),
            "protein": self.protein.to_dict() if self.protein else None,
            "carbohydrate_range_g_per_day": (
                self.carbohydrate_range_g_per_day.to_dict(decimals=macro_decimals)
                if self.carbohydrate_range_g_per_day
                else None
            ),
            "fat_range_g_per_day": (
                self.fat_range_g_per_day.to_dict(decimals=macro_decimals)
                if self.fat_range_g_per_day
                else None
            ),
            "fluid": self.fluid.to_dict() if self.fluid else None,
            "warnings": list(self.warnings),
            "unsupported_reasons": list(self.unsupported_reasons),
            "input_conflicts": list(self.input_conflicts),
            "safety_profile": self.safety_profile.to_dict(),
            "policy_version": self.policy_version,
            "formula_ids": list(self.formula_ids),
            "formula_provenance": formula_provenance(list(self.formula_ids)),
        }

    def to_display_dict(self) -> dict[str, object]:
        """Return ROUNDING_V1 presentation values without changing raw state."""
        return {
            "bmi": _optional_round(self.bmi, 1),
            "estimated_rmr_kcal_per_day": _optional_round(
                self.estimated_rmr_kcal_per_day, -1
            ),
            "estimated_tdee_kcal_per_day": _optional_round(
                self.estimated_tdee_kcal_per_day, -1
            ),
            "calorie_target_kcal_per_day": _optional_round(
                self.calorie_target_kcal_per_day, -1
            ),
            "protein_planning_g_per_day": (
                _round_half_up(self.protein.planning_g_per_day, 0)
                if self.protein
                else None
            ),
            "carbohydrate_range_g_per_day": (
                self.carbohydrate_range_g_per_day.to_dict(decimals=0)
                if self.carbohydrate_range_g_per_day
                else None
            ),
            "fat_range_g_per_day": (
                self.fat_range_g_per_day.to_dict(decimals=0)
                if self.fat_range_g_per_day
                else None
            ),
            "approximate_fluid_goal_ml_per_day": (
                _round_half_up(
                    self.fluid.approximate_fluid_goal_ml_per_day, -2
                )
                if self.fluid
                else None
            ),
        }


def _round_half_up(value: float, decimals: int) -> float:
    quantum = Decimal("1").scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _optional_round(value: float | None, decimals: int) -> float | None:
    return _round_half_up(value, decimals) if value is not None else None


def _is_known(value: CanonicalValue[object]) -> bool:
    return value.status is InputStatus.KNOWN and value.value is not None


def _bmi_classification(bmi: float) -> tuple[str, str]:
    boundaries = POLICY["bmi"]["boundaries"]
    codes = POLICY["bmi"]["codes"]
    labels = POLICY["bmi"]["labels"]
    for index, boundary in enumerate(boundaries):
        if bmi < float(boundary):
            return str(codes[index]), str(labels[index])
    return str(codes[-1]), str(labels[-1])


def _input_issues(input_state: CanonicalNutritionInput) -> tuple[list[str], list[str]]:
    unavailable: list[str] = []
    conflicts: list[str] = []
    for name in (
        "age",
        "equation_sex",
        "height_cm",
        "weight_kg",
        "activity_level",
        "health_goal",
    ):
        value = getattr(input_state, name)
        if value.status is InputStatus.CONFLICT:
            conflicts.append(name)
        if not _is_known(value):
            unavailable.append(f"{name}:{value.status.value}")
    return unavailable, conflicts


def _protein_recommendation(
    *, weight_kg: float, health_goal: str, activity_level: str
) -> ProteinRecommendation:
    if health_goal == "lose_weight":
        branch = "weight_loss"
    elif health_goal == "gain_muscle":
        branch = "gain_resistance"
    elif activity_level == "sedentary":
        branch = "sedentary_maintenance"
    else:
        branch = "active_maintenance"

    rules = POLICY["protein"]["branches"][branch]
    minimum = float(rules["minimum"])
    maximum = float(rules["maximum"])
    planning = float(rules["planning"])
    reference = float(POLICY["protein"]["reference_g_per_kg"])
    return ProteinRecommendation(
        branch=branch,
        reference_minimum_g_per_kg=reference,
        recommended_g_per_kg=NumericRange(minimum, maximum),
        planning_g_per_kg=planning,
        reference_minimum_g_per_day=reference * weight_kg,
        recommended_g_per_day=NumericRange(
            minimum * weight_kg, maximum * weight_kg
        ),
        planning_g_per_day=planning * weight_kg,
    )


def calculate_canonical_nutrition(
    input_state: CanonicalNutritionInput,
) -> CanonicalNutritionState:
    """Calculate canonical state without inventing defaults for absent inputs."""

    formula_ids: list[str] = []
    warnings: list[str] = []
    bmi: float | None = None
    bmi_classification_code: str | None = None
    bmi_classification: str | None = None

    if _is_known(input_state.height_cm) and _is_known(input_state.weight_kg):
        height_cm = float(input_state.height_cm.value)
        weight_kg = float(input_state.weight_kg.value)
        if height_cm > 0 and weight_kg > 0:
            bmi = weight_kg / ((height_cm / 100.0) ** 2)
            bmi_classification_code, bmi_classification = _bmi_classification(bmi)
            formula_ids.extend(
                [
                    str(POLICY["bmi"]["formula_id"]),
                    str(POLICY["bmi"]["classification_formula_id"]),
                ]
            )
            warnings.append("BMI_CLASSIFICATION_IS_SCREENING_NOT_DIAGNOSIS")

    unavailable, conflicts = _input_issues(input_state)
    formula_ids.append(str(POLICY["safety_profile"]["formula_id"]))
    unsupported = list(
        dict.fromkeys(
            (*input_state.unsupported_reasons, *input_state.safety_profile.affirmative_reasons)
        )
    )
    if input_state.safety_profile.has_incomplete_answers:
        warnings.append("SAFETY_SCREENING_INCOMPLETE")
    if _is_known(input_state.age):
        age = int(input_state.age.value)
        minimum_age = int(POLICY["supported_age"]["minimum"])
        maximum_age = int(POLICY["supported_age"]["maximum"])
        if not minimum_age <= age <= maximum_age:
            unsupported.append("AGE_OUTSIDE_SUPPORTED_19_64")

    if unsupported:
        return CanonicalNutritionState(
            status=NutritionStatus.UNSUPPORTED,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(warnings + ["SPECIALIST_GUIDANCE_REQUIRED"]),
            unsupported_reasons=tuple(dict.fromkeys(unsupported)),
            input_conflicts=tuple(conflicts),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    if unavailable:
        return CanonicalNutritionState(
            status=NutritionStatus.INPUT_UNAVAILABLE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(warnings + [f"INPUT_UNAVAILABLE:{item}" for item in unavailable]),
            input_conflicts=tuple(conflicts),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    invalid_fields: list[str] = []
    if int(input_state.age.value) <= 0:
        invalid_fields.append("age")
    if float(input_state.height_cm.value) <= 0:
        invalid_fields.append("height_cm")
    if float(input_state.weight_kg.value) <= 0:
        invalid_fields.append("weight_kg")
    if invalid_fields:
        return CanonicalNutritionState(
            status=NutritionStatus.INPUT_UNAVAILABLE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(
                warnings + [f"INVALID_INPUT:{field}" for field in invalid_fields]
            ),
            input_conflicts=tuple(invalid_fields),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    age = int(input_state.age.value)
    equation_sex = str(input_state.equation_sex.value)
    height_cm = float(input_state.height_cm.value)
    weight_kg = float(input_state.weight_kg.value)
    activity_level = str(input_state.activity_level.value)
    health_goal = str(input_state.health_goal.value)

    if equation_sex not in {"male", "female"}:
        return CanonicalNutritionState(
            status=NutritionStatus.INPUT_UNAVAILABLE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(warnings + ["INVALID_EQUATION_SEX"]),
            input_conflicts=("equation_sex",),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    activity_factors = POLICY["activity"]["factors"]
    if activity_level not in activity_factors:
        return CanonicalNutritionState(
            status=NutritionStatus.INPUT_UNAVAILABLE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(warnings + ["INVALID_ACTIVITY_LEVEL"]),
            input_conflicts=("activity_level",),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )
    if health_goal not in {"lose_weight", "maintain", "gain_muscle"}:
        return CanonicalNutritionState(
            status=NutritionStatus.INPUT_UNAVAILABLE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            warnings=tuple(warnings + ["INVALID_HEALTH_GOAL"]),
            input_conflicts=("health_goal",),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    sex_constant = 5.0 if equation_sex == "male" else -161.0
    estimated_rmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + sex_constant
    activity_factor = float(activity_factors[activity_level])
    estimated_tdee = estimated_rmr * activity_factor
    formula_ids.extend(
        [str(POLICY["rmr"]["formula_id"]), str(POLICY["activity"]["formula_id"])]
    )
    warnings.extend(
        ["RMR_IS_ESTIMATED_NOT_MEASURED", "TDEE_ACTIVITY_FACTOR_IS_HEURISTIC"]
    )

    fluid = FluidGoal(
        approximate_fluid_goal_ml_per_day=(
            weight_kg * float(POLICY["fluid"]["ml_per_kg"])
        )
    )
    formula_ids.extend(
        [
            str(POLICY["fluid"]["formula_id"]),
            str(POLICY["rounding"]["formula_id"]),
        ]
    )
    warnings.append("FLUID_GOAL_IS_APPROXIMATE_HEURISTIC")

    if bmi_classification_code == "UNDERWEIGHT":
        formula_ids.append(str(POLICY["bmi"]["applicability_formula_id"]))
        return CanonicalNutritionState(
            status=NutritionStatus.REQUIRES_SPECIALIST_GUIDANCE,
            bmi=bmi,
            bmi_classification_code=bmi_classification_code,
            bmi_classification=bmi_classification,
            estimated_rmr_kcal_per_day=estimated_rmr,
            estimated_tdee_kcal_per_day=estimated_tdee,
            activity_category=activity_level,
            activity_factor=activity_factor,
            calorie_target_status=CalorieTargetStatus.REQUIRES_SPECIALIST_GUIDANCE,
            fluid=fluid,
            warnings=tuple(
                warnings
                + [
                    "UNDERWEIGHT_BMI_REQUIRES_SPECIALIST_GUIDANCE",
                ]
            ),
            input_conflicts=tuple(conflicts),
            safety_profile=input_state.safety_profile,
            formula_ids=tuple(dict.fromkeys(formula_ids)),
        )

    adjustment = 0.0
    if health_goal == "lose_weight":
        adjustment = -min(
            estimated_tdee * float(POLICY["calories"]["adjustment_fraction"]),
            float(POLICY["calories"]["loss_cap_kcal"]),
        )
        formula_ids.append(str(POLICY["calories"]["loss_formula_id"]))
    elif health_goal == "gain_muscle":
        adjustment = min(
            estimated_tdee * float(POLICY["calories"]["adjustment_fraction"]),
            float(POLICY["calories"]["gain_cap_kcal"]),
        )
        formula_ids.append(str(POLICY["calories"]["gain_formula_id"]))
    else:
        formula_ids.append(str(POLICY["calories"]["maintenance_formula_id"]))

    calculated_target = estimated_tdee + adjustment
    gate = float(POLICY["calories"]["specialist_gate_kcal"])
    target_status = CalorieTargetStatus.AVAILABLE
    target: float | None = calculated_target
    state_status = NutritionStatus.READY
    if calculated_target < gate:
        state_status = NutritionStatus.REQUIRES_SPECIALIST_GUIDANCE
        target_status = CalorieTargetStatus.REQUIRES_SPECIALIST_GUIDANCE
        target = None
        formula_ids.append(str(POLICY["calories"]["safety_formula_id"]))
        warnings.append("LOW_ENERGY_TARGET_REQUIRES_SPECIALIST_GUIDANCE")

    protein = _protein_recommendation(
        weight_kg=weight_kg,
        health_goal=health_goal,
        activity_level=activity_level,
    )
    formula_ids.extend(
        [
            str(POLICY["protein"]["reference_formula_id"]),
            str(POLICY["protein"]["formula_id"]),
        ]
    )

    carbohydrate_range: NumericRange | None = None
    fat_range: NumericRange | None = None
    if target is not None:
        carbohydrate_range = NumericRange(
            target * float(POLICY["carbohydrate"]["minimum_energy_fraction"])
            / float(POLICY["carbohydrate"]["kcal_per_gram"]),
            target * float(POLICY["carbohydrate"]["maximum_energy_fraction"])
            / float(POLICY["carbohydrate"]["kcal_per_gram"]),
        )
        fat_range = NumericRange(
            target * float(POLICY["fat"]["minimum_energy_fraction"])
            / float(POLICY["fat"]["kcal_per_gram"]),
            target * float(POLICY["fat"]["maximum_energy_fraction"])
            / float(POLICY["fat"]["kcal_per_gram"]),
        )
        formula_ids.extend(
            [
                str(POLICY["carbohydrate"]["formula_id"]),
                str(POLICY["fat"]["formula_id"]),
            ]
        )

    return CanonicalNutritionState(
        status=state_status,
        bmi=bmi,
        bmi_classification_code=bmi_classification_code,
        bmi_classification=bmi_classification,
        estimated_rmr_kcal_per_day=estimated_rmr,
        estimated_tdee_kcal_per_day=estimated_tdee,
        activity_category=activity_level,
        activity_factor=activity_factor,
        calorie_target_status=target_status,
        calorie_target_kcal_per_day=target,
        energy_adjustment_kcal_per_day=adjustment,
        protein=protein,
        carbohydrate_range_g_per_day=carbohydrate_range,
        fat_range_g_per_day=fat_range,
        fluid=fluid,
        warnings=tuple(warnings),
        input_conflicts=tuple(conflicts),
        safety_profile=input_state.safety_profile,
        formula_ids=tuple(dict.fromkeys(formula_ids)),
    )


@dataclass(frozen=True, slots=True)
class ConsumedMealNutrition:
    energy_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    record_status: str = "CONSUMED"


@dataclass(frozen=True, slots=True)
class DailyNutritionSummary:
    status: InputStatus
    energy_consumed_kcal: float | None = None
    protein_consumed_g: float | None = None
    carbohydrate_consumed_g: float | None = None
    fat_consumed_g: float | None = None
    energy_remaining_kcal: float | None = None
    over_target: bool | None = None
    energy_status: RangeStatus = RangeStatus.UNAVAILABLE
    protein_status: RangeStatus = RangeStatus.UNAVAILABLE
    carbohydrate_status: RangeStatus = RangeStatus.UNAVAILABLE
    fat_status: RangeStatus = RangeStatus.UNAVAILABLE
    warning: str | None = None
    policy_version: str = POLICY_VERSION
    formula_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "energy_consumed_kcal": _optional_round(self.energy_consumed_kcal, 1),
            "protein_consumed_g": _optional_round(self.protein_consumed_g, 1),
            "carbohydrate_consumed_g": _optional_round(
                self.carbohydrate_consumed_g, 1
            ),
            "fat_consumed_g": _optional_round(self.fat_consumed_g, 1),
            "energy_remaining_kcal": _optional_round(self.energy_remaining_kcal, 1),
            "over_target": self.over_target,
            "energy_status": self.energy_status.value,
            "protein_status": self.protein_status.value,
            "carbohydrate_status": self.carbohydrate_status.value,
            "fat_status": self.fat_status.value,
            "warning": self.warning,
            "policy_version": self.policy_version,
            "formula_ids": list(self.formula_ids),
            "formula_provenance": formula_provenance(list(self.formula_ids)),
        }


def _range_status(value: float, target: NumericRange | None) -> RangeStatus:
    if target is None:
        return RangeStatus.UNAVAILABLE
    if value < target.minimum:
        return RangeStatus.BELOW_RANGE
    if value > target.maximum:
        return RangeStatus.ABOVE_RANGE
    return RangeStatus.WITHIN_RANGE


def summarize_daily_nutrition(
    meals: CanonicalValue[tuple[ConsumedMealNutrition, ...]],
    canonical: CanonicalNutritionState,
) -> DailyNutritionSummary:
    """Summarize authoritative consumed meals without clamping remaining values."""

    if meals.status is not InputStatus.KNOWN or meals.value is None:
        return DailyNutritionSummary(
            status=meals.status,
            warning=f"CONSUMED_MEALS_{meals.status.value}",
            formula_ids=(str(POLICY["daily_summary"]["formula_id"]),),
        )

    consumed = tuple(meal for meal in meals.value if meal.record_status == "CONSUMED")
    energy = sum(meal.energy_kcal for meal in consumed)
    protein = sum(meal.protein_g for meal in consumed)
    carbohydrate = sum(meal.carbohydrate_g for meal in consumed)
    fat = sum(meal.fat_g for meal in consumed)

    target = canonical.calorie_target_kcal_per_day
    remaining = target - energy if target is not None else None
    over_target = energy > target if target is not None else None
    if target is None:
        energy_status = RangeStatus.UNAVAILABLE
    elif energy > target:
        energy_status = RangeStatus.ABOVE_RANGE
    else:
        energy_status = RangeStatus.WITHIN_RANGE

    return DailyNutritionSummary(
        status=InputStatus.KNOWN,
        energy_consumed_kcal=energy,
        protein_consumed_g=protein,
        carbohydrate_consumed_g=carbohydrate,
        fat_consumed_g=fat,
        energy_remaining_kcal=remaining,
        over_target=over_target,
        energy_status=energy_status,
        protein_status=_range_status(
            protein, canonical.protein.recommended_g_per_day if canonical.protein else None
        ),
        carbohydrate_status=_range_status(
            carbohydrate, canonical.carbohydrate_range_g_per_day
        ),
        fat_status=_range_status(fat, canonical.fat_range_g_per_day),
        warning=(
            None
            if target is not None
            else "CANONICAL_CALORIE_TARGET_UNAVAILABLE"
        ),
        formula_ids=tuple(
            dict.fromkeys(
                (
                    str(POLICY["daily_summary"]["formula_id"]),
                    *canonical.formula_ids,
                )
            )
        ),
    )


__all__ = [
    "CalorieTargetStatus",
    "CanonicalNutritionInput",
    "CanonicalNutritionState",
    "CanonicalValue",
    "ConsumedMealNutrition",
    "DailyNutritionSummary",
    "FluidGoal",
    "InputStatus",
    "NumericRange",
    "NutritionStatus",
    "ProteinRecommendation",
    "RangeStatus",
    "NutritionSafetyProfile",
    "SafetyAnswer",
    "calculate_canonical_nutrition",
    "summarize_daily_nutrition",
]
