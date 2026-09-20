import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/profile_readiness.dart';
import 'package:health_app/models/user_model.dart';
import 'package:health_app/providers/ai_chat_provider.dart';
import 'package:health_app/providers/user_provider.dart';

UserModel completeUser({bool confirmedFood = false}) {
  final nutrition = NutritionProfile.completeAccountIntake(
    null,
    allergyAndAvoidanceNote: null,
    foodPreferenceNote: null,
    nutritionGoalNote: null,
    foodAllergies: confirmedFood ? [] : null,
    dietaryRestrictions: confirmedFood ? [] : null,
  );
  return UserModel.newAccount(
          id: 'owner', email: 'fixture@example.com', name: 'An Nguyen')
      .copyWith(
    age: 29,
    height: 165,
    weight: 60,
    activityLevel: 'light',
    healthGoal: 'maintain',
    basicProfileCompletedAt: DateTime.utc(2026, 9, 8),
    nutritionProfile: nutrition,
    healthProfile: HealthProfile.completeAccountIntake(
      primarySupport: 'NUTRITION',
      nutritionProfile: nutrition,
    ),
  );
}

UserModel completeUserWithGender(String gender, {bool confirmedFood = true}) =>
    completeUser(confirmedFood: confirmedFood).copyWith(gender: gender);

class RefreshingUserProvider extends UserProvider {
  RefreshingUserProvider(this.profile);
  UserModel profile;
  UserModel? refreshed;
  bool succeeds = true;
  int reads = 0;
  @override
  UserModel get currentUser => profile;
  @override
  Future<bool> refreshCurrentUser() async {
    reads++;
    if (refreshed != null) profile = refreshed!;
    return succeeds;
  }
}

class GuardedChatProvider extends AIChatProvider {
  int connections = 0;
  @override
  Future<void> connect(String sessionId) async {
    connections++;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('missing actual values reopen profiles despite completion stamps', () {
    final user = completeUser().copyWith(age: 0, height: double.nan, name: ' ');
    final readiness = ProfileReadiness.assess(user);
    expect(readiness.canSend, isFalse);
    expect(readiness.requiredFields.keys,
        unorderedEquals(['name', 'age', 'height']));
  });

  test('missing domain payload is not hidden by a health completion marker',
      () {
    final user = completeUser().copyWith(
        healthProfile: HealthProfile(
      schemaVersion: HealthProfile.currentSchemaVersion,
      primarySupport: 'NUTRITION',
      completedAt: DateTime.utc(2026),
    ));
    expect(ProfileReadiness.assess(user).requiredFields,
        contains('health_profile'));
  });

  test(
      'explicit none differs from unanswered and does not invent optional data',
      () {
    final missing = ProfileReadiness.assess(completeUser(),
        scope: ProfileContextScope.nutrition);
    expect(missing.personalizationFields,
        contains('nutrition_profile.food_allergies'));
    final confirmed = ProfileReadiness.assess(
        completeUserWithGender('female', confirmedFood: true),
        scope: ProfileContextScope.nutrition);
    expect(confirmed.canSend, isTrue);
    expect(confirmed.personalizationFields,
        isNot(contains('nutrition_profile.food_allergies')));
    expect(confirmed.personalizationFields,
        isNot(contains('nutrition_profile.dietary_restrictions')));
    expect(confirmed.personalizationFields, contains('equation_sex'));
    expect(confirmed.personalizationFields,
        contains('nutrition_safety_profile.pregnancy'));
    expect(
        confirmed.personalizationFields.keys
            .any((key) => key.contains('preferred')),
        isFalse);
    expect(completeUser().gender, isNull);
    final restored =
        UserModel.fromMap(completeUser(confirmedFood: true).toMap());
    expect(restored.nutritionProfile!.foodAllergies, isEmpty);
    expect(
        ProfileReadiness.assess(restored, scope: ProfileContextScope.nutrition)
            .personalizationFields,
        isNot(contains('nutrition_profile.food_allergies')));
  });

  test('general and workout requests do not demand unrelated nutrition answers',
      () {
    expect(ProfileReadiness.assess(completeUser()).hasMissingFields, isFalse);
    final workout = ProfileReadiness.assess(completeUser(),
        scope: ProfileContextScope.workout);
    expect(workout.personalizationFields.keys, ['workout_profile']);
    expect(ProfileReadiness.scopeForMessage('Gợi ý món ăn tối'),
        ProfileContextScope.nutrition);
    expect(ProfileReadiness.scopeForMessage('Lên lịch tập gym'),
        ProfileContextScope.workout);
  });

  test('male nutrition profile does not request maternal safety answers', () {
    final readiness = ProfileReadiness.assess(
      completeUserWithGender('male'),
      scope: ProfileContextScope.nutrition,
    );

    expect(readiness.personalizationFields,
        isNot(contains('nutrition_safety_profile.pregnancy')));
    expect(readiness.personalizationFields,
        isNot(contains('nutrition_safety_profile.lactation')));
    expect(readiness.personalizationFields,
        contains('nutrition_safety_profile.eating_disorder_risk_or_history'));
  });

  test('plan creation requires explicit equation input and never infers gender',
      () {
    final maleWithoutEquation = completeUserWithGender('male');
    expect(
      ProfileReadiness.planCreationMissingFields(maleWithoutEquation),
      contains('equation_sex'),
    );

    final ready = maleWithoutEquation.copyWith(equationSex: 'male');
    expect(ProfileReadiness.planCreationMissingFields(ready), isEmpty);
  });

  test('plan creation validates body measurements against backend bounds', () {
    final invalid = completeUserWithGender('male').copyWith(
      equationSex: 'male',
      weight: 25,
    );
    expect(
      ProfileReadiness.planCreationMissingFields(invalid),
      contains('weight'),
    );
  });

  test('female nutrition profile still requests maternal safety answers', () {
    final readiness = ProfileReadiness.assess(
      completeUserWithGender('female'),
      scope: ProfileContextScope.nutrition,
    );

    expect(readiness.personalizationFields,
        contains('nutrition_safety_profile.pregnancy'));
    expect(readiness.personalizationFields,
        contains('nutrition_safety_profile.lactation'));
  });

  test('legacy empty allergies still require confirmation', () {
    final user = completeUser().copyWith(
        nutritionProfile: NutritionProfile.fromJson({
      'food_allergies': <String>[],
      'dietary_restrictions': <String>[],
      'provenance': {'food_allergies': 'LEGACY'},
    }));
    expect(
        ProfileReadiness.assess(user, scope: ProfileContextScope.nutrition)
            .personalizationFields,
        contains('nutrition_profile.food_allergies'));
  });

  test('send checks refreshed profile before connecting and preserves messages',
      () async {
    final users = RefreshingUserProvider(completeUser());
    final chat = GuardedChatProvider()..setProviders(userProvider: users);
    addTearDown(chat.dispose);
    addTearDown(users.dispose);
    users.refreshed = completeUser().copyWith(weight: 0);
    expect(await chat.sendMessage('Gợi ý món ăn', completeUser()), isFalse);
    expect(users.reads, 1);
    expect(chat.connections, 0);
    expect(chat.messages, isEmpty);
    expect(chat.pendingDraftFor('owner'), 'Gợi ý món ăn');
    expect(chat.pendingDraftFor('another-owner'), isNull);
    expect(chat.profileReadiness!.requiredFields, contains('weight'));
    users.refreshed = completeUser().copyWith(weight: 63);
    final checked =
        await chat.checkProfileBeforeSend('Gợi ý món ăn', completeUser());
    expect(checked!.weight, 63);
    expect(chat.profileIssue, isNull);
  });

  test('read failure never falls back to a complete cached profile', () async {
    final users = RefreshingUserProvider(completeUser())..succeeds = false;
    final chat = GuardedChatProvider()..setProviders(userProvider: users);
    addTearDown(chat.dispose);
    addTearDown(users.dispose);
    expect(await chat.sendMessage('Xin chào', completeUser()), isFalse);
    expect(chat.connections, 0);
    expect(chat.profileIssue, contains('hồ sơ mới nhất'));
    expect(chat.isCheckingProfile, isFalse);
  });

  test('account switch during refresh rejects the old account request',
      () async {
    final users = RefreshingUserProvider(completeUser())
      ..refreshed = completeUser().copyWith(id: 'other');
    final chat = GuardedChatProvider()..setProviders(userProvider: users);
    addTearDown(chat.dispose);
    expect(await chat.sendMessage('Xin chào', completeUser()), isFalse);
    expect(chat.connections, 0);
    expect(chat.messages, isEmpty);
  });

  test('daily safety check preserves confirmed intake status', () {
    const base = WorkoutProfile(
      trainingExperience: 'NOVICE',
      availableEquipment: ['thảm'],
      intakeConfirmationStatus: 'CONFIRMED',
      intakeRevision: 2,
    );
    final updated = WorkoutProfile.applyChatUpdate(
      base,
      {'current_pain_status': 'NO'},
      mode: 'CAPTURE',
    );
    expect(updated.intakeConfirmationStatus, 'CONFIRMED');
    expect(updated.intakeRevision, 2);
    expect(updated.currentPainStatus, 'NO');
    expect(updated.safetyCheckedAt, isNotNull);
  });
}

