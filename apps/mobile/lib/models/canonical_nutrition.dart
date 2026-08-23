import 'dart:math' as math;

/// Generated/shared contract mirror of backend nutrition_policy_v1_0_1.json.
/// Keep changes synchronized through the cross-layer golden parity test.
abstract final class NutritionPolicyV1 {
  static const policyVersion = 'nutrition-policy-v1.0.1';
  static const activityFactors = <String, double>{
    'sedentary': 1.2,
    'light': 1.375,
    'moderate': 1.55,
    'active': 1.725,
    'very_active': 1.9,
  };
  static const mealSplit = <String, double>{
    'breakfast': 0.30,
    'lunch': 0.40,
    'dinner': 0.30,
  };
  static const bmiCategories = <BmiCategoryContract>[
    BmiCategoryContract('UNDERWEIGHT', 'Thiếu cân', '< 18.5'),
    BmiCategoryContract('NORMAL', 'Bình thường', '18.5 - 22.9'),
    BmiCategoryContract('OVERWEIGHT', 'Thừa cân', '23 - 24.9'),
    BmiCategoryContract('OBESITY_I', 'Béo phì độ I', '25 - 29.9'),
    BmiCategoryContract('OBESITY_II', 'Béo phì độ II', '≥ 30'),
  ];
}

class BmiCategoryContract {
  final String code;
  final String label;
  final String displayRange;
  const BmiCategoryContract(this.code, this.label, this.displayRange);
}

enum NutritionInputStatus {
  known,
  missing,
  notLoaded,
  stale,
  error,
  conflict,
}

enum CanonicalNutritionStatus {
  ready,
  inputUnavailable,
  unsupported,
  requiresSpecialistGuidance,
}

enum NutritionRangeStatus { belowRange, withinRange, aboveRange, unavailable }

enum NutritionSafetyAnswer { yes, no, unknown, notProvided }

String _safetyWire(NutritionSafetyAnswer value) => switch (value) {
      NutritionSafetyAnswer.yes => 'YES',
      NutritionSafetyAnswer.no => 'NO',
      NutritionSafetyAnswer.unknown => 'UNKNOWN',
      NutritionSafetyAnswer.notProvided => 'NOT_PROVIDED',
    };

NutritionSafetyAnswer nutritionSafetyAnswerFromWire(Object? value) =>
    switch (value?.toString()) {
      'YES' => NutritionSafetyAnswer.yes,
      'NO' => NutritionSafetyAnswer.no,
      'UNKNOWN' => NutritionSafetyAnswer.unknown,
      _ => NutritionSafetyAnswer.notProvided,
    };

class NutritionSafetyProfile {
  final NutritionSafetyAnswer pregnancy;
  final NutritionSafetyAnswer lactation;
  final NutritionSafetyAnswer eatingDisorderRiskOrHistory;
  final NutritionSafetyAnswer seriousRenalCondition;
  final NutritionSafetyAnswer fluidRestrictedCardiacCondition;
  final NutritionSafetyAnswer clinicallyComplexMetabolicCondition;

  const NutritionSafetyProfile({
    this.pregnancy = NutritionSafetyAnswer.notProvided,
    this.lactation = NutritionSafetyAnswer.notProvided,
    this.eatingDisorderRiskOrHistory = NutritionSafetyAnswer.notProvided,
    this.seriousRenalCondition = NutritionSafetyAnswer.notProvided,
    this.fluidRestrictedCardiacCondition = NutritionSafetyAnswer.notProvided,
    this.clinicallyComplexMetabolicCondition =
        NutritionSafetyAnswer.notProvided,
  });

  factory NutritionSafetyProfile.fromJson(Object? raw) {
    final map =
        raw is Map ? Map<String, dynamic>.from(raw) : const <String, dynamic>{};
    return NutritionSafetyProfile(
      pregnancy: nutritionSafetyAnswerFromWire(map['pregnancy']),
      lactation: nutritionSafetyAnswerFromWire(map['lactation']),
      eatingDisorderRiskOrHistory:
          nutritionSafetyAnswerFromWire(map['eating_disorder_risk_or_history']),
      seriousRenalCondition:
          nutritionSafetyAnswerFromWire(map['serious_renal_condition']),
      fluidRestrictedCardiacCondition: nutritionSafetyAnswerFromWire(
          map['fluid_restricted_cardiac_condition']),
      clinicallyComplexMetabolicCondition: nutritionSafetyAnswerFromWire(
          map['clinically_complex_metabolic_condition']),
    );
  }

  Map<String, String> toJson() => {
        'pregnancy': _safetyWire(pregnancy),
        'lactation': _safetyWire(lactation),
        'eating_disorder_risk_or_history':
            _safetyWire(eatingDisorderRiskOrHistory),
        'serious_renal_condition': _safetyWire(seriousRenalCondition),
        'fluid_restricted_cardiac_condition':
            _safetyWire(fluidRestrictedCardiacCondition),
        'clinically_complex_metabolic_condition':
            _safetyWire(clinicallyComplexMetabolicCondition),
      };

  List<String> get affirmativeReasons => [
        if (pregnancy == NutritionSafetyAnswer.yes) 'SAFETY_PROFILE:PREGNANCY',
        if (lactation == NutritionSafetyAnswer.yes) 'SAFETY_PROFILE:LACTATION',
        if (eatingDisorderRiskOrHistory == NutritionSafetyAnswer.yes)
          'SAFETY_PROFILE:EATING_DISORDER_RISK_OR_HISTORY',
        if (seriousRenalCondition == NutritionSafetyAnswer.yes)
          'SAFETY_PROFILE:SERIOUS_RENAL_CONDITION',
        if (fluidRestrictedCardiacCondition == NutritionSafetyAnswer.yes)
          'SAFETY_PROFILE:FLUID_RESTRICTED_CARDIAC_CONDITION',
        if (clinicallyComplexMetabolicCondition == NutritionSafetyAnswer.yes)
          'SAFETY_PROFILE:CLINICALLY_COMPLEX_METABOLIC_CONDITION',
      ];

  bool get hasIncompleteAnswers => [
        pregnancy,
        lactation,
        eatingDisorderRiskOrHistory,
        seriousRenalCondition,
        fluidRestrictedCardiacCondition,
        clinicallyComplexMetabolicCondition,
      ].any((value) =>
          value == NutritionSafetyAnswer.unknown ||
          value == NutritionSafetyAnswer.notProvided);
}

class CanonicalNutritionValue<T> {
  final T? value;
  final String source;
  final NutritionInputStatus status;

  const CanonicalNutritionValue({
    required this.value,
    required this.source,
    required this.status,
  });

  const CanonicalNutritionValue.known(this.value,
      {this.source = 'explicit_input'})
      : assert(value != null),
        status = NutritionInputStatus.known;
}

class CanonicalNutritionInput {
  final CanonicalNutritionValue<int> age;
  final CanonicalNutritionValue<String> equationSex;
  final CanonicalNutritionValue<double> heightCm;
  final CanonicalNutritionValue<double> weightKg;
  final CanonicalNutritionValue<String> activityLevel;
  final CanonicalNutritionValue<String> healthGoal;
  final NutritionSafetyProfile safetyProfile;
  final List<String> unsupportedReasons;

  const CanonicalNutritionInput({
    required this.age,
    required this.equationSex,
    required this.heightCm,
    required this.weightKg,
    required this.activityLevel,
    required this.healthGoal,
    this.safetyProfile = const NutritionSafetyProfile(),
    this.unsupportedReasons = const [],
  });
}

class NutritionRange {
  final double minimum;
  final double maximum;
  const NutritionRange(this.minimum, this.maximum);
}

class MacroEnergyPercentages {
  final double protein;
  final double carbohydrate;
  final double fat;
  const MacroEnergyPercentages(this.protein, this.carbohydrate, this.fat);
}

MacroEnergyPercentages calculateMacroEnergyPercentages({
  required double proteinGrams,
  required double carbohydrateGrams,
  required double fatGrams,
}) {
  final proteinEnergy = proteinGrams * 4;
  final carbohydrateEnergy = carbohydrateGrams * 4;
  final fatEnergy = fatGrams * 9;
  final totalEnergy = proteinEnergy + carbohydrateEnergy + fatEnergy;
  if (totalEnergy <= 0) return const MacroEnergyPercentages(0, 0, 0);
  return MacroEnergyPercentages(
    proteinEnergy / totalEnergy * 100,
    carbohydrateEnergy / totalEnergy * 100,
    fatEnergy / totalEnergy * 100,
  );
}

class ProteinPolicyResult {
  final String branch;
  final NutritionRange recommendedGramsPerKg;
  final double planningGramsPerKg;
  final double referenceMinimumGramsPerDay;
  final NutritionRange recommendedGramsPerDay;
  final double planningGramsPerDay;

  const ProteinPolicyResult({
    required this.branch,
    required this.recommendedGramsPerKg,
    required this.planningGramsPerKg,
    required this.referenceMinimumGramsPerDay,
    required this.recommendedGramsPerDay,
    required this.planningGramsPerDay,
  });
}

class CanonicalNutritionState {
  final CanonicalNutritionStatus status;
  final double? bmi;
  final String? bmiClassificationCode;
  final String? bmiClassification;
  final double? estimatedRmrKcalPerDay;
  final double? estimatedTdeeKcalPerDay;
  final String? activityCategory;
  final double? activityFactor;
  final double? calorieTargetKcalPerDay;
  final double? energyAdjustmentKcalPerDay;
  final ProteinPolicyResult? protein;
  final NutritionRange? carbohydrateRangeGramsPerDay;
  final NutritionRange? fatRangeGramsPerDay;
  final double? approximateFluidGoalMlPerDay;
  final List<String> warnings;
  final List<String> unsupportedReasons;
  final List<String> inputConflicts;
  final List<String> formulaIds;
  final NutritionSafetyProfile safetyProfile;

  const CanonicalNutritionState({
    required this.status,
    this.bmi,
    this.bmiClassificationCode,
    this.bmiClassification,
    this.estimatedRmrKcalPerDay,
    this.estimatedTdeeKcalPerDay,
    this.activityCategory,
    this.activityFactor,
    this.calorieTargetKcalPerDay,
    this.energyAdjustmentKcalPerDay,
    this.protein,
    this.carbohydrateRangeGramsPerDay,
    this.fatRangeGramsPerDay,
    this.approximateFluidGoalMlPerDay,
    this.warnings = const [],
    this.unsupportedReasons = const [],
    this.inputConflicts = const [],
    this.formulaIds = const [],
    this.safetyProfile = const NutritionSafetyProfile(),
  });

  String get policyVersion => NutritionPolicyV1.policyVersion;
  bool get hasOrdinaryCalorieTarget => calorieTargetKcalPerDay != null;
  double? get displayBmi => _roundTo(bmi, 1);
  double? get displayEstimatedRmrKcalPerDay =>
      _roundTo(estimatedRmrKcalPerDay, -1);
  double? get displayEstimatedTdeeKcalPerDay =>
      _roundTo(estimatedTdeeKcalPerDay, -1);
  double? get displayCalorieTargetKcalPerDay =>
      _roundTo(calorieTargetKcalPerDay, -1);
  double? get displayApproximateFluidGoalMlPerDay =>
      _roundTo(approximateFluidGoalMlPerDay, -2);

  Map<String, Object?> toJson() => {
        'status': _wireEnum(status.name),
        'bmi': _roundTo(bmi, 2),
        'bmi_classification_code': bmiClassificationCode,
        'bmi_classification': bmiClassification,
        'estimated_rmr_kcal_per_day': _roundTo(estimatedRmrKcalPerDay, 0),
        'estimated_tdee_kcal_per_day': _roundTo(estimatedTdeeKcalPerDay, 0),
        'calorie_target_kcal_per_day': _roundTo(calorieTargetKcalPerDay, 0),
        'energy_adjustment_kcal_per_day':
            _roundTo(energyAdjustmentKcalPerDay, 0),
        'approximate_fluid_goal_ml_per_day':
            _roundTo(approximateFluidGoalMlPerDay, 0),
        'policy_version': policyVersion,
        'formula_ids': formulaIds,
        'warnings': warnings,
        'unsupported_reasons': unsupportedReasons,
        'input_conflicts': inputConflicts,
        'safety_profile': safetyProfile.toJson(),
      };
}

String _wireEnum(String value) => value
    .replaceAllMapped(RegExp(r'[A-Z]'), (match) => '_${match.group(0)}')
    .toUpperCase();

double? _roundTo(double? value, int decimals) {
  if (value == null) return null;
  final scale = math.pow(10, decimals).toDouble();
  return (value * scale).round() / scale;
}

double roundNutritionEnergyForDisplay(double value) => _roundTo(value, -1)!;
double roundNutritionMacroForDisplay(double value) => _roundTo(value, 0)!;
double roundNutritionFluidForDisplay(double value) => _roundTo(value, -2)!;

(String, String) _bmiClass(double bmi) {
  if (bmi < 18.5) return ('UNDERWEIGHT', 'Thiếu cân');
  if (bmi < 23.0) return ('NORMAL', 'Bình thường');
  if (bmi < 25.0) return ('OVERWEIGHT', 'Thừa cân');
  if (bmi < 30.0) return ('OBESITY_I', 'Béo phì độ I');
  return ('OBESITY_II', 'Béo phì độ II');
}

CanonicalNutritionState calculateCanonicalNutrition(
  CanonicalNutritionInput input,
) {
  final fields = <String, CanonicalNutritionValue<Object>>{
    'age': input.age,
    'equation_sex': input.equationSex,
    'height_cm': input.heightCm,
    'weight_kg': input.weightKg,
    'activity_level': input.activityLevel,
    'health_goal': input.healthGoal,
  };
  final unavailable = fields.entries
      .where((entry) =>
          entry.value.status != NutritionInputStatus.known ||
          entry.value.value == null)
      .map((entry) => entry.key)
      .toList(growable: false);
  final conflicts = fields.entries
      .where((entry) => entry.value.status == NutritionInputStatus.conflict)
      .map((entry) => entry.key)
      .toList(growable: false);

  final height = input.heightCm.value;
  final weight = input.weightKg.value;
  final bmi = height != null && weight != null && height > 0 && weight > 0
      ? weight / math.pow(height / 100.0, 2)
      : null;
  final bmiClass = bmi == null ? null : _bmiClass(bmi);
  final bmiClassCode = bmiClass?.$1;
  final bmiClassLabel = bmiClass?.$2;
  final bmiIds = bmi == null
      ? <String>['NUTRITION_APPLICABILITY_SCREEN_V1_0_1']
      : <String>[
          'BMI_CALC_V1',
          'BMI_CLASS_VN_MOH_2022_V1',
          'NUTRITION_APPLICABILITY_SCREEN_V1_0_1',
        ];

  final unsupported = <String>[
    ...input.unsupportedReasons,
    ...input.safetyProfile.affirmativeReasons,
  ];
  final safetyWarnings = <String>[
    if (input.safetyProfile.hasIncompleteAnswers) 'SAFETY_SCREENING_INCOMPLETE',
  ];
  final age = input.age.value;
  if (age != null && (age < 19 || age > 64)) {
    unsupported.add('AGE_OUTSIDE_SUPPORTED_19_64');
  }
  if (unsupported.isNotEmpty) {
    return CanonicalNutritionState(
      status: CanonicalNutritionStatus.unsupported,
      bmi: bmi,
      bmiClassificationCode: bmiClassCode,
      bmiClassification: bmiClassLabel,
      unsupportedReasons: List.unmodifiable(unsupported.toSet()),
      inputConflicts: List.unmodifiable(conflicts),
      warnings: List.unmodifiable(safetyWarnings),
      safetyProfile: input.safetyProfile,
      formulaIds: List.unmodifiable(bmiIds),
    );
  }
  if (unavailable.isNotEmpty || height! <= 0 || weight! <= 0 || age! <= 0) {
    return CanonicalNutritionState(
      status: CanonicalNutritionStatus.inputUnavailable,
      bmi: bmi,
      bmiClassificationCode: bmiClassCode,
      bmiClassification: bmiClassLabel,
      inputConflicts: List.unmodifiable(conflicts),
      warnings: List.unmodifiable([
        ...safetyWarnings,
        ...unavailable.map((item) => 'INPUT_UNAVAILABLE:$item'),
      ]),
      safetyProfile: input.safetyProfile,
      formulaIds: List.unmodifiable(bmiIds),
    );
  }
  final knownHeight = height;
  final knownWeight = weight;
  final knownAge = age;

  final sex = input.equationSex.value!;
  final activity = input.activityLevel.value!;
  final goal = input.healthGoal.value!;
  final activityFactor = NutritionPolicyV1.activityFactors[activity];
  if ((sex != 'male' && sex != 'female') ||
      activityFactor == null ||
      !const {'lose_weight', 'maintain', 'gain_muscle'}.contains(goal)) {
    return CanonicalNutritionState(
      status: CanonicalNutritionStatus.inputUnavailable,
      bmi: bmi,
      bmiClassificationCode: bmiClassCode,
      bmiClassification: bmiClassLabel,
      inputConflicts: const ['INVALID_ENUM_INPUT'],
      warnings: List.unmodifiable(safetyWarnings),
      formulaIds: List.unmodifiable(bmiIds),
      safetyProfile: input.safetyProfile,
    );
  }

  final sexConstant = sex == 'male' ? 5.0 : -161.0;
  final rmr =
      10 * knownWeight + 6.25 * knownHeight - 5 * knownAge + sexConstant;
  final tdee = rmr * activityFactor;
  if (bmiClassCode == 'UNDERWEIGHT') {
    return CanonicalNutritionState(
      status: CanonicalNutritionStatus.requiresSpecialistGuidance,
      bmi: bmi,
      bmiClassificationCode: bmiClassCode,
      bmiClassification: bmiClassLabel,
      estimatedRmrKcalPerDay: rmr,
      estimatedTdeeKcalPerDay: tdee,
      activityCategory: activity,
      activityFactor: activityFactor,
      approximateFluidGoalMlPerDay: knownWeight * 33.0,
      warnings: List.unmodifiable([
        ...safetyWarnings,
        'BMI_CLASSIFICATION_IS_SCREENING_NOT_DIAGNOSIS',
        'RMR_IS_ESTIMATED_NOT_MEASURED',
        'TDEE_ACTIVITY_FACTOR_IS_HEURISTIC',
        'UNDERWEIGHT_BMI_REQUIRES_SPECIALIST_GUIDANCE',
        'FLUID_GOAL_IS_APPROXIMATE_HEURISTIC',
      ]),
      formulaIds: List.unmodifiable([
        ...bmiIds,
        'RMR_MIFFLIN_ST_JEOR_V1',
        'TDEE_ACTIVITY_FACTOR_V1',
        'BMI_UNDERWEIGHT_SPECIALIST_GATE_V1_0_1',
        'APPROXIMATE_FLUID_33MLKG_V1',
        'ROUNDING_V1',
      ]),
      safetyProfile: input.safetyProfile,
    );
  }
  var adjustment = 0.0;
  var calorieFormula = 'CALORIE_MAINTENANCE_V1';
  if (goal == 'lose_weight') {
    adjustment = -math.min(tdee * 0.10, 500.0).toDouble();
    calorieFormula = 'CALORIE_WEIGHT_LOSS_10PCT_CAP500_V1';
  } else if (goal == 'gain_muscle') {
    adjustment = math.min(tdee * 0.10, 300.0).toDouble();
    calorieFormula = 'CALORIE_WEIGHT_GAIN_10PCT_CAP300_V1';
  }
  final ordinaryTarget = tdee + adjustment;
  final gated = ordinaryTarget < 1200.0;

  late final String proteinBranch;
  late final double proteinMin;
  late final double proteinMax;
  late final double proteinPlanning;
  if (goal == 'lose_weight') {
    proteinBranch = 'weight_loss';
    proteinMin = 1.4;
    proteinMax = 1.6;
    proteinPlanning = 1.5;
  } else if (goal == 'gain_muscle') {
    proteinBranch = 'gain_resistance';
    proteinMin = 1.4;
    proteinMax = 1.8;
    proteinPlanning = 1.6;
  } else if (activity == 'sedentary') {
    proteinBranch = 'sedentary_maintenance';
    proteinMin = 0.8;
    proteinMax = 1.0;
    proteinPlanning = 0.9;
  } else {
    proteinBranch = 'active_maintenance';
    proteinMin = 1.2;
    proteinMax = 1.4;
    proteinPlanning = 1.3;
  }
  final protein = ProteinPolicyResult(
    branch: proteinBranch,
    recommendedGramsPerKg: NutritionRange(proteinMin, proteinMax),
    planningGramsPerKg: proteinPlanning,
    referenceMinimumGramsPerDay: knownWeight * 0.8,
    recommendedGramsPerDay:
        NutritionRange(knownWeight * proteinMin, knownWeight * proteinMax),
    planningGramsPerDay: knownWeight * proteinPlanning,
  );
  final target = gated ? null : ordinaryTarget;
  final ids = <String>[
    ...bmiIds,
    'RMR_MIFFLIN_ST_JEOR_V1',
    'TDEE_ACTIVITY_FACTOR_V1',
    calorieFormula,
    if (gated) 'LOW_ENERGY_SAFETY_GATE_1200_V1',
    'PROTEIN_ADULT_REFERENCE_MINIMUM_V1',
    'PROTEIN_GOAL_ACTIVITY_RANGE_V1',
    if (!gated) 'CARBOHYDRATE_AMDR_RANGE_V1',
    if (!gated) 'FAT_AMDR_RANGE_V1',
    'APPROXIMATE_FLUID_33MLKG_V1',
    'ROUNDING_V1',
  ];
  return CanonicalNutritionState(
    status: gated
        ? CanonicalNutritionStatus.requiresSpecialistGuidance
        : CanonicalNutritionStatus.ready,
    bmi: bmi,
    bmiClassificationCode: bmiClassCode,
    bmiClassification: bmiClassLabel,
    estimatedRmrKcalPerDay: rmr,
    estimatedTdeeKcalPerDay: tdee,
    activityCategory: activity,
    activityFactor: activityFactor,
    calorieTargetKcalPerDay: target,
    energyAdjustmentKcalPerDay: adjustment,
    protein: protein,
    carbohydrateRangeGramsPerDay: target == null
        ? null
        : NutritionRange(target * 0.45 / 4, target * 0.65 / 4),
    fatRangeGramsPerDay: target == null
        ? null
        : NutritionRange(target * 0.20 / 9, target * 0.35 / 9),
    approximateFluidGoalMlPerDay: knownWeight * 33.0,
    warnings: [
      ...safetyWarnings,
      'RMR_IS_ESTIMATED_NOT_MEASURED',
      'TDEE_ACTIVITY_FACTOR_IS_HEURISTIC',
      if (gated) 'LOW_ENERGY_TARGET_REQUIRES_SPECIALIST_GUIDANCE',
      'FLUID_GOAL_IS_APPROXIMATE_HEURISTIC',
    ],
    formulaIds: List.unmodifiable(ids),
    safetyProfile: input.safetyProfile,
  );
}

class ConsumedMealNutrition {
  final double energyKcal;
  final double proteinGrams;
  final double carbohydrateGrams;
  final double fatGrams;
  final String recordStatus;

  const ConsumedMealNutrition({
    required this.energyKcal,
    required this.proteinGrams,
    required this.carbohydrateGrams,
    required this.fatGrams,
    this.recordStatus = 'CONSUMED',
  });
}

class DailyNutritionSummary {
  final NutritionInputStatus status;
  final double? energyConsumedKcal;
  final double? proteinConsumedGrams;
  final double? carbohydrateConsumedGrams;
  final double? fatConsumedGrams;
  final double? energyRemainingKcal;
  final bool? overTarget;
  final NutritionRangeStatus energyStatus;
  final NutritionRangeStatus proteinStatus;
  final NutritionRangeStatus carbohydrateStatus;
  final NutritionRangeStatus fatStatus;
  final String policyVersion;
  final List<String> formulaIds;

  const DailyNutritionSummary({
    required this.status,
    this.energyConsumedKcal,
    this.proteinConsumedGrams,
    this.carbohydrateConsumedGrams,
    this.fatConsumedGrams,
    this.energyRemainingKcal,
    this.overTarget,
    this.energyStatus = NutritionRangeStatus.unavailable,
    this.proteinStatus = NutritionRangeStatus.unavailable,
    this.carbohydrateStatus = NutritionRangeStatus.unavailable,
    this.fatStatus = NutritionRangeStatus.unavailable,
    this.policyVersion = NutritionPolicyV1.policyVersion,
    this.formulaIds = const ['DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1'],
  });

  Map<String, Object?> toJson() => {
        'status': _wireEnum(status.name),
        'energy_consumed_kcal': _roundTo(energyConsumedKcal, 1),
        'protein_consumed_g': _roundTo(proteinConsumedGrams, 1),
        'carbohydrate_consumed_g': _roundTo(carbohydrateConsumedGrams, 1),
        'fat_consumed_g': _roundTo(fatConsumedGrams, 1),
        'energy_remaining_kcal': _roundTo(energyRemainingKcal, 1),
        'over_target': overTarget,
        'energy_status': _wireEnum(energyStatus.name),
        'protein_status': _wireEnum(proteinStatus.name),
        'carbohydrate_status': _wireEnum(carbohydrateStatus.name),
        'fat_status': _wireEnum(fatStatus.name),
        'policy_version': policyVersion,
        'formula_ids': formulaIds,
        'formula_provenance': formulaIds
            .map((id) => {
                  'formula_id': id,
                  'policy_version': policyVersion,
                })
            .toList(growable: false),
      };
}

NutritionRangeStatus _rangeStatus(double value, NutritionRange? range) {
  if (range == null) return NutritionRangeStatus.unavailable;
  if (value < range.minimum) return NutritionRangeStatus.belowRange;
  if (value > range.maximum) return NutritionRangeStatus.aboveRange;
  return NutritionRangeStatus.withinRange;
}

DailyNutritionSummary summarizeDailyNutrition(
  CanonicalNutritionValue<List<ConsumedMealNutrition>> meals,
  CanonicalNutritionState canonical,
) {
  if (meals.status != NutritionInputStatus.known || meals.value == null) {
    return DailyNutritionSummary(status: meals.status);
  }
  final consumed = meals.value!
      .where((meal) => meal.recordStatus == 'CONSUMED')
      .toList(growable: false);
  final energy = consumed.fold(0.0, (sum, meal) => sum + meal.energyKcal);
  final protein = consumed.fold(0.0, (sum, meal) => sum + meal.proteinGrams);
  final carbohydrate =
      consumed.fold(0.0, (sum, meal) => sum + meal.carbohydrateGrams);
  final fat = consumed.fold(0.0, (sum, meal) => sum + meal.fatGrams);
  final target = canonical.calorieTargetKcalPerDay;
  final proteinRange = canonical.protein?.recommendedGramsPerDay;
  return DailyNutritionSummary(
    status: NutritionInputStatus.known,
    energyConsumedKcal: energy,
    proteinConsumedGrams: protein,
    carbohydrateConsumedGrams: carbohydrate,
    fatConsumedGrams: fat,
    energyRemainingKcal: target == null ? null : target - energy,
    overTarget: target == null ? null : energy > target,
    energyStatus: _rangeStatus(
        energy, target == null ? null : NutritionRange(target, target)),
    proteinStatus: _rangeStatus(protein, proteinRange),
    carbohydrateStatus:
        _rangeStatus(carbohydrate, canonical.carbohydrateRangeGramsPerDay),
    fatStatus: _rangeStatus(fat, canonical.fatRangeGramsPerDay),
    formulaIds: List.unmodifiable({
      'DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1',
      ...canonical.formulaIds,
    }),
  );
}
