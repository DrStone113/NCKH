import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/user_model.dart';
import 'package:health_app/providers/user_provider.dart';

UserModel _answered() => UserModel.newAccount(
      id: 'demo',
      email: 'profile@example.com',
      name: 'Nguyễn An',
    ).copyWith(
      age: 29,
      height: 165.5,
      weight: 57.25,
      activityLevel: 'light',
      healthGoal: 'maintain',
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('new email and Google accounts contain no invented measurements', () {
    for (final name in ['', 'Google display name']) {
      final user = UserModel.newAccount(
        id: 'new-account',
        email: 'new@example.com',
        name: name,
      );
      final persisted = user.toMap();
      for (final field in [
        'age',
        'height',
        'weight',
        'targetWeight',
        'gender',
        'equation_sex',
        'activityLevel',
        'healthGoal',
      ]) {
        expect(persisted[field], isNull, reason: field);
      }
      expect(user.needsBasicProfileIntake, isTrue);
      expect(user.recommendedCalories, isNull);
      final restored = UserModel.fromMap(persisted);
      expect(restored.toMap()['activityLevel'], isNull);
      expect(restored.toMap()['healthGoal'], isNull);
      expect(restored.needsBasicProfileIntake, isTrue);
    }
  });

  test('legacy V2 completion cannot skip confirmation of basic details', () {
    final user = _answered().copyWith(
      healthProfile: HealthProfile.completeAccountIntake(
        primarySupport: 'NUTRITION',
        nutritionProfile: NutritionProfile.completeAccountIntake(
          null,
          allergyAndAvoidanceNote: null,
          foodPreferenceNote: null,
          nutritionGoalNote: null,
        ),
      ),
    );
    expect(user.needsAccountHealthIntake, isFalse);
    expect(user.needsBasicProfileIntake, isTrue);
  });

  test('confirmed details survive serialization and later profile updates', () {
    final confirmed = _answered().copyWith(
      gender: 'female',
      basicProfileCompletedAt: DateTime.utc(2026, 9, 8),
    );
    final restored = UserModel.fromMap(confirmed.toMap()).copyWith(weight: 58);
    expect(restored.needsBasicProfileIntake, isFalse);
    expect(restored.basicProfileCompletedAt, DateTime.utc(2026, 9, 8));
    expect(restored.equationSex, isNull);
    expect(restored.needsAccountHealthIntake, isTrue);
  });

  test('invalid required details reopen even a previously confirmed profile',
      () {
    final confirmed = _answered().copyWith(
      basicProfileCompletedAt: DateTime.utc(2026, 9, 8),
    );
    for (final invalid in [
      confirmed.copyWith(name: ' '),
      confirmed.copyWith(age: 0),
      confirmed.copyWith(height: double.nan),
      confirmed.copyWith(weight: double.infinity),
      confirmed.copyWith(activityLevel: ''),
      confirmed.copyWith(healthGoal: ''),
    ]) {
      expect(invalid.needsBasicProfileIntake, isTrue);
    }
  });

  test(
      'provider validates owner and values before completing the basic profile',
      () async {
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    final before = provider.currentUser;
    await expectLater(
      provider.completeBasicProfile(_answered().copyWith(id: 'another-owner')),
      throwsArgumentError,
    );
    await expectLater(
      provider.completeBasicProfile(_answered().copyWith(height: 0)),
      throwsArgumentError,
    );
    expect(provider.currentUser, same(before));
    await provider.completeBasicProfile(_answered());
    expect(provider.needsBasicProfileIntake, isFalse);
    expect(provider.currentUser!.basicProfileCompletedAt, isNotNull);
    expect(provider.currentUser!.gender, isNull);
    expect(provider.currentUser!.equationSex, isNull);
  });
}
