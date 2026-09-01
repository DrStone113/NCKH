import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/user_model.dart';

WorkoutProfile _completeWorkout() => WorkoutProfile.completeAccountIntake(
      null,
      const {
        'training_experience': 'NOVICE',
        'available_days_per_week': 3,
        'default_session_duration_minutes': 30,
        'training_location': 'home',
        'available_equipment': ['none'],
        'current_pain_status': 'NO',
        'exercise_safety_profile': {
          'health_state': 'HEALTHY_GENERAL',
          'pregnancy_status': 'NOT_APPLICABLE',
          'warning_symptoms': <String>[],
          'acute_injury': false,
          'recent_surgery': false,
          'technique_screen_confirmed': true,
        },
      },
      now: DateTime.utc(2026, 8, 31),
    );

NutritionProfile _nutrition({
  List<String>? allergies,
  List<String>? restrictions,
  String? notes,
}) =>
    NutritionProfile.completeAccountIntake(
      null,
      allergyAndAvoidanceNote: null,
      foodPreferenceNote: 'Thích món Việt',
      nutritionGoalNote: 'Ăn đủ đạm',
      foodAllergies: allergies,
      dietaryRestrictions: restrictions,
      foodDislikesText: 'Không thích rau mùi',
      nutritionNotes: notes,
      now: DateTime.utc(2026, 8, 31),
    );

void main() {
  test('nutrition-only V2 profile is complete without fabricated workout data',
      () {
    final nutrition = _nutrition();
    final health = HealthProfile.completeAccountIntake(
      primarySupport: 'NUTRITION',
      nutritionProfile: nutrition,
      safetyProfile: const SafetyProfile(),
      now: DateTime.utc(2026, 8, 31),
    );

    expect(health.hasCompletedCurrentAccountIntake, isTrue);
    expect(health.workoutProfile, isNull);
    expect(health.schemaVersion, HealthProfile.currentSchemaVersion);
  });

  test('both-domain V2 profile requires a completed workout profile', () {
    final nutrition = _nutrition();
    expect(
      () => HealthProfile.completeAccountIntake(
        primarySupport: 'BOTH',
        nutritionProfile: nutrition,
      ),
      throwsArgumentError,
    );

    final health = HealthProfile.completeAccountIntake(
      primarySupport: 'BOTH',
      nutritionProfile: nutrition,
      workoutProfile: _completeWorkout(),
    );
    expect(health.hasCompletedCurrentAccountIntake, isTrue);
  });

  test('explicit allergen selection maps to deterministic dish restrictions',
      () {
    final nutrition = _nutrition(
      allergies: const ['PEANUT', 'MILK'],
      restrictions: const ['no_pork'],
    );

    expect(
      nutrition.canonicalDietaryRestrictions,
      const ['no_milk', 'no_peanut', 'no_pork'],
    );
    expect(nutrition.provenance?['food_allergies'], 'EXPLICIT_UI_SELECTION');
    expect(nutrition.fieldStates?['food_allergies']?.status, 'CONFIRMED');
    expect(nutrition.fieldStates?['food_allergies']?.source,
        'EXPLICIT_UI_SELECTION');
    expect(nutrition.fieldStates?['food_allergies']?.confirmedAt,
        DateTime.utc(2026, 8, 31));
    expect(nutrition.requiresRelevantConfirmation, isFalse);
  });

  test('confirmed explicit food exclusions are deterministic hard constraints',
      () {
    final nutrition = NutritionProfile.completeAccountIntake(
      null,
      allergyAndAvoidanceNote: null,
      foodPreferenceNote: null,
      nutritionGoalNote: null,
      foodAllergies: const ['FISH'],
      dietaryRestrictions: const ['vegetarian'],
      foodExclusions: const ['thịt heo', 'beef'],
      now: DateTime.utc(2026, 8, 31),
    );

    expect(nutrition.canonicalDietaryRestrictions,
        const ['no_beef', 'no_fish', 'no_pork', 'vegetarian']);
    expect(nutrition.fieldStates?['food_exclusions']?.freshness,
        'STABLE_UNTIL_CHANGED');
  });

  test('candidate profile facts never become deterministic meal constraints',
      () {
    const candidate = ProfileFieldState(
      value: ['PEANUT'],
      status: 'CANDIDATE_FACT',
      source: 'CANDIDATE_FACT',
      freshness: 'STABLE_UNTIL_CHANGED',
    );
    const nutrition = NutritionProfile(
      foodAllergies: ['PEANUT'],
      dietaryRestrictions: ['no_pork'],
      foodExclusions: ['beef'],
      fieldStates: {
        'food_allergies': candidate,
        'dietary_restrictions': candidate,
        'food_exclusions': candidate,
      },
      candidateFacts: [
        ProfileCandidateFact(
          field: 'food_exclusions',
          rawText: 'Không ăn thịt bò',
        ),
      ],
    );

    expect(nutrition.canonicalDietaryRestrictions, isNull);
    expect(nutrition.requiresRelevantConfirmation, isTrue);
    expect(
        nutrition.toJson()['candidate_facts'][0]['source'], 'CANDIDATE_FACT');
  });

  test('free text remains raw and never becomes a diagnosis or allergen tag',
      () {
    final nutrition = _nutrition(notes: 'Tôi khó chịu sau khi uống sữa.');

    expect(nutrition.nutritionNotes, 'Tôi khó chịu sau khi uống sữa.');
    expect(nutrition.foodAllergies, isNull);
    expect(nutrition.canonicalDietaryRestrictions, isNull);
    expect(nutrition.candidateFacts, isNull);
  });

  test('partial nutrition questionnaire keeps optional fields missing', () {
    final nutrition = NutritionProfile.completeAccountIntake(
      null,
      allergyAndAvoidanceNote: null,
      foodPreferenceNote: null,
      nutritionGoalNote: null,
      nutritionGoal: 'UNKNOWN',
    );

    expect(nutrition.nutritionGoal, 'UNKNOWN');
    expect(nutrition.dislikedFoods, isNull);
    expect(nutrition.foodAllergies, isNull);
    expect(nutrition.mealPreferences, isNull);
  });

  test('single-field correction preserves the rest of the nutrition profile',
      () {
    final before = _nutrition(
      restrictions: const ['no_pork', 'no_beef'],
      notes: 'Ăn tối muộn.',
    );
    final after = NutritionProfile.applyExplicitUpdate(
      before,
      const {
        'dietary_restrictions': ['no_beef']
      },
      now: DateTime.utc(2026, 8, 31, 10),
    );

    expect(after.dietaryRestrictions, const ['no_beef']);
    expect(after.nutritionNotes, 'Ăn tối muộn.');
    expect(after.foodDislikesText, 'Không thích rau mùi');
    expect(
        after.fieldStates?['dietary_restrictions']?.source, 'USER_CONFIRMED');
    expect(after.fieldStates?['dietary_restrictions']?.updatedAt,
        DateTime.utc(2026, 8, 31, 10));
    expect(after.fieldStates?['nutrition_notes']?.updatedAt,
        DateTime.utc(2026, 8, 31));
  });

  test('existing V1 workout account is upgraded through HealthProfile V2 only',
      () {
    final legacyUser = UserModel(
      id: 'legacy',
      email: 'legacy@example.com',
      name: 'Legacy',
      age: 25,
      height: 170,
      weight: 65,
      activityLevel: 'moderate',
      workoutProfile: _completeWorkout(),
    );
    expect(legacyUser.needsAccountHealthIntake, isTrue);

    final upgraded = legacyUser.copyWith(
      healthProfile: HealthProfile.completeAccountIntake(
        primarySupport: 'EXERCISE',
        nutritionProfile: _nutrition(),
        workoutProfile: legacyUser.workoutProfile,
      ),
    );
    expect(upgraded.needsAccountHealthIntake, isFalse);
    expect(upgraded.workoutProfile?.trainingExperience, 'NOVICE');
    expect(upgraded.generalProfile.toJson(), {
      'age': 25,
      'height_cm': 170.0,
      'weight_kg': 65.0,
      'equation_sex': null,
      'activity_level': 'moderate',
      'health_goal': 'maintain',
    });
  });

  test('field freshness distinguishes durable preferences from current safety',
      () {
    expect(NutritionProfile.freshnessForField('preferred_cuisines'),
        'PERIODIC_CONFIRMATION');
    expect(WorkoutProfile.freshnessForField('training_experience'),
        'STABLE_UNTIL_CHANGED');
    expect(WorkoutProfile.freshnessForField('current_pain_status'),
        'CURRENT_OBSERVATION');
    expect(WorkoutProfile.freshnessForField('exercise_safety_profile'),
        'TIME_SENSITIVE');
  });

  test('V1 nutrition values remain readable and conversion is idempotent', () {
    final legacy = UserModel.fromMap({
      'id': 'v1',
      'email': 'v1@example.com',
      'name': 'V1',
      'age': 35,
      'height': 168,
      'weight': 70,
      'activityLevel': 'light',
      'nutrition_profile': {
        'food_preference_note': 'Thích món Việt',
      },
    });
    final reread = UserModel.fromMap(legacy.toMap());

    expect(reread.nutritionProfile?.foodPreferenceNote, 'Thích món Việt');
    expect(reread.needsAccountHealthIntake, isTrue);
    expect(reread.generalProfile.weightKg, 70.0);
  });

  test('legacy notes request only a relevant confirmation, not repeated UI',
      () {
    final legacy = NutritionProfile.fromJson(
      const {'food_preference_note': 'Thích món Việt'},
    )!;
    expect(legacy.requiresRelevantConfirmation, isTrue);

    final current = _nutrition();
    expect(current.requiresRelevantConfirmation, isFalse);
  });
}
