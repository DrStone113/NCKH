import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/user_model.dart';

void main() {
  test('capture immediately stores a pending typed workout intake revision',
      () {
    final captured = WorkoutProfile.applyChatUpdate(
      null,
      const {
        'training_experience': 'NOVICE',
        'training_experience_detail': 'Mới bắt đầu',
        'available_days_per_week': 3,
        'current_pain_status': 'NO',
        'exercise_safety_profile': {
          'health_state': 'HEALTHY_GENERAL',
          'acute_injury': false,
          'warning_symptoms': <String>[],
        },
      },
      mode: 'CAPTURE',
      now: DateTime.utc(2026, 8, 31, 9),
    );

    expect(captured.trainingExperience, 'NOVICE');
    expect(captured.trainingExperienceDetail, 'Mới bắt đầu');
    expect(captured.availableDaysPerWeek, 3);
    expect(captured.currentPainStatus, 'NO');
    expect(captured.intakeConfirmationStatus, 'PENDING_CONFIRMATION');
    expect(captured.intakeRevision, 1);
    expect(captured.safetyCheckedAt, DateTime.utc(2026, 8, 31, 9));
  });

  test('confirmation preserves captured values and records the revision', () {
    final captured = WorkoutProfile.applyChatUpdate(
      null,
      const {'available_days_per_week': 4},
      mode: 'CAPTURE',
      now: DateTime.utc(2026, 8, 31, 9),
    );

    final confirmed = WorkoutProfile.applyChatUpdate(
      captured,
      const {},
      mode: 'CONFIRM',
      now: DateTime.utc(2026, 8, 31, 10),
    );

    expect(confirmed.availableDaysPerWeek, 4);
    expect(confirmed.intakeRevision, 1);
    expect(confirmed.intakeConfirmationStatus, 'CONFIRMED');
    expect(confirmed.intakeConfirmedAt, DateTime.utc(2026, 8, 31, 10));
  });

  test('does not infer experienced status or accept an invalid frequency', () {
    expect(
      () => WorkoutProfile.applyChatUpdate(
        null,
        const {
          'training_experience': 'ADVANCED',
          'training_experience_detail': 'Tập hơn 6 tháng',
        },
        mode: 'CAPTURE',
      ),
      throwsArgumentError,
    );
    expect(
      () => WorkoutProfile.applyChatUpdate(
        null,
        const {'available_days_per_week': 8},
        mode: 'CAPTURE',
      ),
      throwsArgumentError,
    );
  });

  test('account intake is confirmed, versioned, and complete', () {
    final completed = WorkoutProfile.completeAccountIntake(
      null,
      {
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
      now: DateTime.utc(2026, 8, 31, 8),
    );

    expect(completed.intakeConfirmationStatus, 'CONFIRMED');
    expect(completed.accountIntakeVersion,
        WorkoutProfile.currentAccountIntakeVersion);
    expect(completed.safetyCheckedAt, DateTime.utc(2026, 8, 31, 8));
    expect(completed.hasCompletedCurrentAccountIntake, isTrue);
  });

  test('a later chat revision does not reopen account onboarding', () {
    final completed = WorkoutProfile.completeAccountIntake(
      null,
      {
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
      now: DateTime.utc(2026, 8, 31, 8),
    );
    final pendingChatRevision = WorkoutProfile.applyChatUpdate(
      completed,
      const {'available_days_per_week': 4},
      mode: 'CAPTURE',
      now: DateTime.utc(2026, 8, 31, 9),
    );

    expect(
        pendingChatRevision.intakeConfirmationStatus, 'PENDING_CONFIRMATION');
    expect(pendingChatRevision.hasCompletedCurrentAccountIntake, isTrue);
  });

  test('nutrition account notes preserve explicit free text without tags', () {
    final nutrition = NutritionProfile.completeAccountIntake(
      null,
      allergyAndAvoidanceNote: 'Dị ứng tôm; không uống sữa',
      foodPreferenceNote: 'Thích món Việt, ăn ít cay',
      nutritionGoalNote: 'Muốn ăn đủ đạm và giảm đồ ngọt',
      now: DateTime.utc(2026, 8, 31, 8),
    );

    expect(nutrition.hasCompletedCurrentAccountIntake, isTrue);
    expect(nutrition.allergyAndAvoidanceNote, 'Dị ứng tôm; không uống sữa');
    expect(nutrition.foodPreferenceNote, 'Thích món Việt, ăn ít cay');
    expect(nutrition.nutritionGoalNote, 'Muốn ăn đủ đạm và giảm đồ ngọt');
    expect(nutrition.toJson()['account_intake_version'], 2);
  });
}
