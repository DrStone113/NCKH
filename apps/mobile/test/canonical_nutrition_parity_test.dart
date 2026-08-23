import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/canonical_nutrition.dart';

void main() {
  test('Flutter calculator matches shared backend golden cases', () {
    final cases = (jsonDecode(
            File('../../contracts/nutrition_policy_v1_0_1_golden.json')
                .readAsStringSync()) as List)
        .cast<Map<String, dynamic>>();

    for (final testCase in cases) {
      final raw = testCase['input'] as Map<String, dynamic>;
      final expected = testCase['expected'] as Map<String, dynamic>;
      final state = calculateCanonicalNutrition(CanonicalNutritionInput(
        age: CanonicalNutritionValue.known(raw['age'] as int),
        equationSex:
            CanonicalNutritionValue.known(raw['equation_sex'] as String),
        heightCm:
            CanonicalNutritionValue.known((raw['height_cm'] as num).toDouble()),
        weightKg:
            CanonicalNutritionValue.known((raw['weight_kg'] as num).toDouble()),
        activityLevel:
            CanonicalNutritionValue.known(raw['activity_level'] as String),
        healthGoal: CanonicalNutritionValue.known(raw['health_goal'] as String),
      ));

      expect(
          state.status.name
              .replaceAllMapped(
                  RegExp(r'[A-Z]'), (match) => '_${match.group(0)}')
              .toUpperCase(),
          expected['status'],
          reason: testCase['name'] as String);
      expect(state.bmi, closeTo((expected['bmi'] as num).toDouble(), 1e-9));
      expect(state.bmiClassification, expected['bmi_classification']);
      expect(state.estimatedRmrKcalPerDay,
          closeTo((expected['rmr'] as num).toDouble(), 1e-9));
      expect(state.estimatedTdeeKcalPerDay,
          closeTo((expected['tdee'] as num).toDouble(), 1e-9));
      if (expected['target'] == null) {
        expect(state.calorieTargetKcalPerDay, isNull);
      } else {
        expect(state.calorieTargetKcalPerDay,
            closeTo((expected['target'] as num).toDouble(), 1e-9));
      }
      if (expected['adjustment'] == null) {
        expect(state.energyAdjustmentKcalPerDay, isNull);
      } else {
        expect(state.energyAdjustmentKcalPerDay,
            closeTo((expected['adjustment'] as num).toDouble(), 1e-9));
      }
      if (expected['protein_planning'] == null) {
        expect(state.protein, isNull);
      } else {
        expect(state.protein!.planningGramsPerDay,
            closeTo((expected['protein_planning'] as num).toDouble(), 1e-9));
      }
      expect(state.approximateFluidGoalMlPerDay,
          closeTo((expected['fluid_ml'] as num).toDouble(), 1e-9));
    }
  });

  test('unknown equation sex has no fallback', () {
    final state = calculateCanonicalNutrition(const CanonicalNutritionInput(
      age: CanonicalNutritionValue.known(30),
      equationSex: CanonicalNutritionValue.known('unknown'),
      heightCm: CanonicalNutritionValue.known(170),
      weightKg: CanonicalNutritionValue.known(70),
      activityLevel: CanonicalNutritionValue.known('moderate'),
      healthGoal: CanonicalNutritionValue.known('maintain'),
    ));
    expect(state.status, CanonicalNutritionStatus.inputUnavailable);
    expect(state.estimatedRmrKcalPerDay, isNull);
  });

  test('known zero and over-target summaries are not clamped', () {
    final canonical = calculateCanonicalNutrition(const CanonicalNutritionInput(
      age: CanonicalNutritionValue.known(30),
      equationSex: CanonicalNutritionValue.known('male'),
      heightCm: CanonicalNutritionValue.known(175),
      weightKg: CanonicalNutritionValue.known(70),
      activityLevel: CanonicalNutritionValue.known('moderate'),
      healthGoal: CanonicalNutritionValue.known('maintain'),
    ));
    final zero = summarizeDailyNutrition(
        const CanonicalNutritionValue.known(<ConsumedMealNutrition>[]),
        canonical);
    expect(zero.energyConsumedKcal, 0);
    expect(zero.overTarget, isFalse);

    final over = summarizeDailyNutrition(
      CanonicalNutritionValue.known([
        ConsumedMealNutrition(
          energyKcal: canonical.calorieTargetKcalPerDay! + 100,
          proteinGrams: 100,
          carbohydrateGrams: 300,
          fatGrams: 80,
        ),
        const ConsumedMealNutrition(
          energyKcal: 999,
          proteinGrams: 999,
          carbohydrateGrams: 999,
          fatGrams: 999,
          recordStatus: 'PLANNED',
        ),
      ]),
      canonical,
    );
    expect(over.energyRemainingKcal, closeTo(-100, 1e-9));
    expect(over.overTarget, isTrue);
  });

  test('macro display uses 4/4/9 energy shares, not gram shares', () {
    final result = calculateMacroEnergyPercentages(
      proteinGrams: 100,
      carbohydrateGrams: 100,
      fatGrams: 100,
    );
    expect(result.protein, closeTo(400 / 1700 * 100, 1e-9));
    expect(result.carbohydrate, closeTo(400 / 1700 * 100, 1e-9));
    expect(result.fat, closeTo(900 / 1700 * 100, 1e-9));
  });
}
