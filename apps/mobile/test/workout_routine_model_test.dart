import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/wger_models.dart';
import 'package:health_app/models/workout_routine_model.dart';
import 'package:health_app/providers/exercise_provider.dart';

void main() {
  group('WorkoutRoutineParser Tests', () {
    test(
        'Phân tích đúng chuỗi mô tả bài tập có dấu gạch đầu dòng và số hiệp/lần',
        () {
      const rawText = '''
- 10-12 lần
- Seated Hip Adduction: 3 hiệp x 10-12 lần
- Arnold Shoulder Press: 3 hiệp x 10-12 lần
- Axe Hold: 3 hiệp x 10-12 lần
- Abdominal Stabilization: 3 hiệp x 10-12 lần
- Bear Walk 2: 3 hiệp x 10-12 lần
- Single Leg Extension: 3 hiệp x 10-12 lần
- Bent High Pulls: 3 hiệp x 10-12 lần
''';

      final action = ActionItem(
        kind: 'exercise',
        wgerId: 0,
        name: 'Full Body workout (intermediate)',
        details: {
          'duration': 35,
          'calories_burned': 240.0,
          'description': rawText,
        },
      );

      final routine = WorkoutRoutineParser.parseFromAction(action);

      expect(routine.title, 'Full Body workout (intermediate)');
      expect(routine.level, contains('Intermediate'));
      expect(routine.totalDurationMinutes, 35);
      expect(routine.totalCalories, 240.0);

      // Phải có đủ 3 giai đoạn: Warm-up, Main, Cool-down
      expect(routine.phases.length, 3);
      expect(routine.warmupPhase, isNotNull);
      expect(routine.mainPhase, isNotNull);
      expect(routine.cooldownPhase, isNotNull);

      // Thân bài chính phải trích xuất đúng 7 bài tập con
      final mainExercises = routine.mainPhase!.exercises;
      expect(mainExercises.length, 7);

      expect(mainExercises[0].name, contains('Seated Hip Adduction'));
      expect(mainExercises[0].sets, 3);
      expect(mainExercises[0].reps, '10-12 lần');
      expect(mainExercises[0].targetMuscles, isNotEmpty);
      expect(mainExercises[0].instructions, isNotEmpty);

      expect(mainExercises[1].name, contains('Arnold Shoulder Press'));
      expect(mainExercises[1].sets, 3);
      expect(mainExercises[1].animationType, WorkoutAnimationType.press);

      expect(mainExercises[4].name, contains('Bear Walk 2'));
      expect(
          mainExercises[4].animationType, WorkoutAnimationType.dynamicMovement);

      expect(mainExercises[5].name, contains('Single Leg Extension'));
      expect(mainExercises[5].animationType, WorkoutAnimationType.legExtension);
    });

    test('Tính toán tiến độ tổng thể chính xác khi hoàn thành các bài tập', () {
      final action = ActionItem(
        kind: 'exercise',
        wgerId: 0,
        name: 'Core & Cardio Blast',
        details: {
          'duration': 20,
          'calories_burned': 150.0,
          'description': '- Plank: 3 hiệp x 45s\n- Jumping Jacks: 3 hiệp x 30s',
        },
      );

      final routine = WorkoutRoutineParser.parseFromAction(action);
      final all = routine.allExercises;

      expect(routine.overallProgress, 0.0);
      expect(routine.isFullyCompleted, false);

      // Đánh dấu hoàn thành một nửa số bài
      for (int i = 0; i < all.length ~/ 2; i++) {
        all[i].isCompleted = true;
        all[i].completedSets = all[i].sets;
      }

      expect(routine.completedExercisesCount, all.length ~/ 2);
      expect(routine.overallProgress, greaterThan(0.0));

      // Đánh dấu hoàn thành 100%
      for (final ex in all) {
        ex.isCompleted = true;
        ex.completedSets = ex.sets;
      }

      expect(routine.overallProgress, 1.0);
      expect(routine.isFullyCompleted, true);
    });

    test('JSON serialization & deserialization cho WorkoutExerciseStep', () {
      final step = WorkoutExerciseStep(
        id: 'test_1',
        name: 'Push Up',
        vietnameseName: 'Chống đẩy',
        sets: 4,
        reps: '15 lần',
        durationSeconds: null,
        restSeconds: 60,
        targetMuscles: ['Cơ ngực', 'Tay sau'],
        category: 'Sức mạnh',
        equipment: 'Bodyweight',
        instructions: 'Hạ ngực chạm sàn và đẩy lên.',
        tips: 'Gồng chặt bụng.',
        breathingCue: 'Hít khi hạ, thở khi đẩy.',
        animationType: WorkoutAnimationType.press,
        isCompleted: true,
        completedSets: 4,
      );

      final json = step.toJson();
      final restored = WorkoutExerciseStep.fromJson(json);

      expect(restored.id, 'test_1');
      expect(restored.name, 'Push Up');
      expect(restored.vietnameseName, 'Chống đẩy');
      expect(restored.sets, 4);
      expect(restored.reps, '15 lần');
      expect(restored.restSeconds, 60);
      expect(restored.targetMuscles, ['Cơ ngực', 'Tay sau']);
      expect(restored.animationType, WorkoutAnimationType.press);
      expect(restored.isCompleted, true);
      expect(restored.completedSets, 4);
    });

    test(
        'ExerciseProvider.cleanHtml loại bỏ sạch các tag HTML <p>, </p>, &nbsp;',
        () {
      const html1 = '<p>Zone two Cardio for endurance</p>';
      expect(
          ExerciseProvider.cleanHtml(html1), 'Zone two Cardio for endurance');

      const html2 = '<p>Starting position:&nbsp;<b>Stand tall</b><br/></p>';
      expect(
          ExerciseProvider.cleanHtml(html2), 'Starting position: Stand tall');
    });

    test(
        'ExerciseProvider.estimateMETForExercise tính toán MET chính xác theo từng bài tập',
        () {
      final sprint = ExerciseProvider.estimateMETForExercise(
          'Swimming 50m sprints', 'Cardio', 4);
      final zone2 = ExerciseProvider.estimateMETForExercise(
          'Zone 2 Running', 'Cardio', 2);
      final jumpRope = ExerciseProvider.estimateMETForExercise(
          'Jump rope: basic jumps', 'Cardio', 2);
      final suspended = ExerciseProvider.estimateMETForExercise(
          'Suspended crossess', 'Cardio', 2);
      final yoga = ExerciseProvider.estimateMETForExercise(
          'Hatha Yoga', 'Flexibility', 1);

      // Các bài tập khác nhau phải có lượng calo tiêu thụ / MET khác nhau, không bị trùng lặp
      expect(sprint, greaterThan(zone2));
      expect(jumpRope, greaterThan(suspended));
      expect(zone2, greaterThan(suspended));
      expect(suspended, greaterThan(yoga));
    });

    test('wger prose is not mistaken for a list of exercises', () {
      final action = ActionItem(
        kind: 'exercise',
        wgerId: 123,
        name: 'Biceps curl',
        details: {
          'duration': 30,
          'description':
              'Stand upright and keep your elbows close to your torso. Raise the weight slowly.',
        },
      );

      final routine = WorkoutRoutineParser.parseFromAction(action);
      final main = routine.mainPhase!.exercises;

      expect(main, hasLength(1));
      expect(main.single.name, 'Biceps curl');
      expect(main.single.durationSeconds, isNull);
      expect(main.single.animationType, WorkoutAnimationType.pull);
    });

    test('hyphenated names are preserved and phase time matches total time',
        () {
      final action = ActionItem(
        kind: 'exercise',
        wgerId: 0,
        name: 'Short workout',
        details: {
          'duration': 8,
          'description': '- Push-up - 10 reps',
        },
      );

      final routine = WorkoutRoutineParser.parseFromAction(action);
      final phaseMinutes = routine.phases
          .fold<int>(0, (total, phase) => total + phase.durationMinutes);

      expect(routine.mainPhase!.exercises.single.name, 'Push-up');
      expect(routine.mainPhase!.exercises.single.reps, '10 reps');
      expect(phaseMinutes, routine.totalDurationMinutes);
    });

    test('animation inference distinguishes curls, extensions and unknowns',
        () {
      expect(
        WorkoutRoutineParser.inferAnimationType('Dumbbell biceps curl'),
        WorkoutAnimationType.pull,
      );
      expect(
        WorkoutRoutineParser.inferAnimationType('Single leg extension'),
        WorkoutAnimationType.legExtension,
      );
      expect(
        WorkoutRoutineParser.inferAnimationType('Unlisted exercise'),
        WorkoutAnimationType.generic,
      );
    });

    test('routine normalizes loose duration and estimates invalid calories',
        () {
      final routine = WorkoutRoutineParser.parseFromAction(ActionItem(
        kind: 'exercise',
        wgerId: 9,
        name: 'Jump rope',
        details: {
          'duration': '-20',
          'calories_burned': '-1',
          'category': 'Cardio',
        },
      ));

      expect(routine.totalDurationMinutes, 3);
      expect(routine.totalCalories, greaterThan(0));
      expect(
        routine.mainPhase!.exercises.single.animationType,
        WorkoutAnimationType.cardio,
      );
    });
  });
}
