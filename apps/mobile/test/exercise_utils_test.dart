import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/exercise_model.dart';
import 'package:health_app/utils/exercise_utils.dart';

void main() {
  group('ExerciseUtils', () {
    test('search normalization ignores Vietnamese accents and punctuation', () {
      expect(
        ExerciseUtils.normalizeSearchText('  Chạy-bộ, NHANH!  '),
        'chay bo nhanh',
      );
    });

    test('maps wger muscle categories to strength instead of cardio', () {
      expect(ExerciseUtils.mapToAppType('Biceps curl', 'Arms'), 'strength');
      expect(ExerciseUtils.mapToAppType('Leg extension', 'Legs'), 'strength');
      expect(ExerciseUtils.mapToAppType('Hatha yoga', 'Yoga'), 'flexibility');
      expect(ExerciseUtils.mapToAppType('Zone 2 Running', 'Cardio'), 'cardio');
    });

    test('MET and calories differ by exercise intensity', () {
      final sprint =
          ExerciseUtils.estimateMet('Swimming 50m sprints', 'Cardio', 4);
      final elliptical = ExerciseUtils.estimateMet('Elliptical', 'Cardio', 2);
      final yoga = ExerciseUtils.estimateMet('Hatha yoga', 'Yoga', 1);

      expect(sprint, greaterThan(elliptical));
      expect(elliptical, greaterThan(yoga));
      expect(
        ExerciseUtils.calculateCalories(
          met: sprint,
          weightKg: 70,
          durationMinutes: 30,
        ),
        closeTo(sprint * 35, 0.001),
      );
    });

    test('unknown exercise MET is deterministic', () {
      final first = ExerciseUtils.estimateMet('Unlisted movement', 'Arms', 1);
      final second = ExerciseUtils.estimateMet('Unlisted movement', 'Arms', 1);
      expect(second, first);
    });

    test('duration and wger IDs are normalized safely', () {
      expect(ExerciseUtils.parseDuration('-10'), 1);
      expect(ExerciseUtils.parseDuration('99999'), 1440);
      expect(ExerciseUtils.parseDuration('invalid'), 30);

      final template = ExerciseTemplate(
        id: 'wger_192',
        name: 'Bench press',
        metValue: 5.8,
        type: 'strength',
      );
      final journalEntry = ExerciseModel(
        id: 'entry',
        userId: 'user',
        name: 'Bench press',
        exerciseTemplateId: template.id,
        date: DateTime(2026, 8, 13),
        duration: 30,
        caloriesBurned: 203,
        type: 'strength',
      );

      expect(template.wgerId, 192);
      expect(journalEntry.wgerId, 192);
      expect(ExerciseUtils.parseWgerId('local_template'), 0);
    });
  });
}
