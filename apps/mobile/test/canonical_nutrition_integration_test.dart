import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/canonical_nutrition.dart';
import 'package:health_app/models/user_model.dart';

UserModel _user({
  String? gender,
  String? equationSex,
  NutritionSafetyProfile safety = const NutritionSafetyProfile(
    pregnancy: NutritionSafetyAnswer.no,
    lactation: NutritionSafetyAnswer.no,
    eatingDisorderRiskOrHistory: NutritionSafetyAnswer.no,
    seriousRenalCondition: NutritionSafetyAnswer.no,
    fluidRestrictedCardiacCondition: NutritionSafetyAnswer.no,
    clinicallyComplexMetabolicCondition: NutritionSafetyAnswer.no,
  ),
}) =>
    UserModel(
      id: 'u1',
      email: 'u@example.test',
      name: 'User',
      age: 30,
      gender: gender,
      equationSex: equationSex,
      nutritionSafetyProfile: safety,
      height: 175,
      weight: 70,
      activityLevel: 'moderate',
    );

void main() {
  group('equation-sex migration and explicit input', () {
    test(
        'historical profile with missing gender preserves missing equation sex',
        () {
      final user = UserModel.fromMap({
        'id': 'old-1',
        'age': 30,
        'height': 175,
        'weight': 70,
        'activityLevel': 'moderate',
      });
      expect(user.gender, isNull);
      expect(user.equationSex, isNull);
      expect(user.canonicalNutrition.status,
          CanonicalNutritionStatus.inputUnavailable);
      expect(user.tdee, isNull);
    });

    test('historically defaulted gender is never backfilled into equation sex',
        () {
      final user = UserModel.fromMap({
        'id': 'old-2',
        'gender': 'male',
        'age': 30,
        'height': 175,
        'weight': 70,
        'activityLevel': 'moderate',
      });
      expect(user.gender, 'male');
      expect(user.equationSex, isNull);
      expect(user.canonicalNutrition.estimatedRmrKcalPerDay, isNull);
    });

    test('new profile and declined equation sex do not fabricate a coefficient',
        () {
      final newUser = _user();
      final declined = _user(equationSex: null);
      for (final user in [newUser, declined]) {
        expect(user.toMap()['equation_sex'], isNull);
        expect(user.canonicalNutrition.status,
            CanonicalNutritionStatus.inputUnavailable);
      }
    });

    test('explicit male and female equation sex choose their own coefficients',
        () {
      final male = _user(gender: 'nonbinary', equationSex: 'male');
      final female = _user(gender: 'male', equationSex: 'female');
      expect(male.canonicalNutrition.estimatedRmrKcalPerDay, 1648.75);
      expect(female.canonicalNutrition.estimatedRmrKcalPerDay, 1482.75);
      expect(male.gender, 'nonbinary');
      expect(female.gender, 'male');
    });
  });

  group('structured safety and applicability', () {
    for (final entry in <String, NutritionSafetyProfile>{
      'pregnancy':
          const NutritionSafetyProfile(pregnancy: NutritionSafetyAnswer.yes),
      'lactation':
          const NutritionSafetyProfile(lactation: NutritionSafetyAnswer.yes),
      'eating disorder': const NutritionSafetyProfile(
          eatingDisorderRiskOrHistory: NutritionSafetyAnswer.yes),
      'renal': const NutritionSafetyProfile(
          seriousRenalCondition: NutritionSafetyAnswer.yes),
      'cardiac fluid restriction': const NutritionSafetyProfile(
          fluidRestrictedCardiacCondition: NutritionSafetyAnswer.yes),
      'complex metabolic': const NutritionSafetyProfile(
          clinicallyComplexMetabolicCondition: NutritionSafetyAnswer.yes),
    }.entries) {
      test('${entry.key} YES is specialist-gated', () {
        final state =
            _user(equationSex: 'male', safety: entry.value).canonicalNutrition;
        expect(state.status, CanonicalNutritionStatus.unsupported);
        expect(state.calorieTargetKcalPerDay, isNull);
        expect(state.protein, isNull);
      });
    }

    test('UNKNOWN remains unknown and ordinary target carries warning', () {
      const safety = NutritionSafetyProfile(
        pregnancy: NutritionSafetyAnswer.unknown,
        lactation: NutritionSafetyAnswer.no,
        eatingDisorderRiskOrHistory: NutritionSafetyAnswer.no,
        seriousRenalCondition: NutritionSafetyAnswer.no,
        fluidRestrictedCardiacCondition: NutritionSafetyAnswer.no,
        clinicallyComplexMetabolicCondition: NutritionSafetyAnswer.no,
      );
      final state =
          _user(equationSex: 'male', safety: safety).canonicalNutrition;
      expect(state.safetyProfile.pregnancy, NutritionSafetyAnswer.unknown);
      expect(state.status, CanonicalNutritionStatus.ready);
      expect(state.calorieTargetKcalPerDay, isNotNull);
      expect(state.warnings, contains('SAFETY_SCREENING_INCOMPLETE'));
    });
  });

  test('BMI 18.49 is specialist-gated while 18.50 is ordinary', () {
    CanonicalNutritionState calculate(double bmi) =>
        calculateCanonicalNutrition(CanonicalNutritionInput(
          age: const CanonicalNutritionValue.known(30),
          equationSex: const CanonicalNutritionValue.known('male'),
          heightCm: const CanonicalNutritionValue.known(200),
          weightKg: CanonicalNutritionValue.known(bmi * 4),
          activityLevel: const CanonicalNutritionValue.known('moderate'),
          healthGoal: const CanonicalNutritionValue.known('maintain'),
        ));

    final below = calculate(18.49);
    expect(below.bmiClassificationCode, 'UNDERWEIGHT');
    expect(below.status, CanonicalNutritionStatus.requiresSpecialistGuidance);
    expect(below.estimatedRmrKcalPerDay, isNotNull);
    expect(below.estimatedTdeeKcalPerDay, isNotNull);
    expect(below.calorieTargetKcalPerDay, isNull);
    expect(below.protein, isNull);

    final boundary = calculate(18.50);
    expect(boundary.bmiClassificationCode, 'NORMAL');
    expect(boundary.status, CanonicalNutritionStatus.ready);
    expect(boundary.calorieTargetKcalPerDay, isNotNull);
  });

  test('daily summary always carries policy and formula provenance', () {
    final canonical = _user(equationSex: 'male').canonicalNutrition;
    final summary = summarizeDailyNutrition(
      const CanonicalNutritionValue.known(<ConsumedMealNutrition>[]),
      canonical,
    );
    final json = summary.toJson();
    expect(json['policy_version'], 'nutrition-policy-v1.0.1');
    expect(summary.formulaIds,
        contains('DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1'));
    expect(json['formula_provenance'], isNotEmpty);
  });
}
