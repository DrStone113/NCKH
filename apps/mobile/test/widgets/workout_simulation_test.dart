import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:health_app/models/wger_models.dart';
import 'package:health_app/models/workout_routine_model.dart';
import 'package:health_app/providers/exercise_provider.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:health_app/widgets/workout_simulation_painter.dart';
import 'package:health_app/widgets/detail_bottom_sheet.dart';
import 'package:health_app/features/exercise/screens/workout_simulation_screen.dart';

void main() {
  test('resolves exercise names to biomechanically distinct movements', () {
    expect(
      resolveWorkoutMovementVariant(
        WorkoutAnimationType.stretch,
        'Joint Rotations & Dynamic Stretch',
      ),
      WorkoutMovementVariant.jointRotation,
    );
    expect(
      resolveWorkoutMovementVariant(
        WorkoutAnimationType.dynamicMovement,
        'Jumping Jacks / Arm Circles',
      ),
      WorkoutMovementVariant.jumpingJack,
    );
    expect(
      resolveWorkoutMovementVariant(
        WorkoutAnimationType.cardio,
        'High Knees',
      ),
      WorkoutMovementVariant.highKnees,
    );
    expect(
      resolveWorkoutMovementVariant(
        WorkoutAnimationType.press,
        'Push-up',
      ),
      WorkoutMovementVariant.pushUp,
    );
    expect(
      resolveWorkoutMovementVariant(
        WorkoutAnimationType.dynamicMovement,
        'Bear Walk',
      ),
      WorkoutMovementVariant.bearWalk,
    );
    final preciseMovements = {
      'Bench press': WorkoutMovementVariant.benchPress,
      'Dumbbell biceps curl': WorkoutMovementVariant.bicepsCurl,
      'Walking lunges': WorkoutMovementVariant.lunge,
      'Jump rope: basic jumps': WorkoutMovementVariant.jumpRope,
      'Swimming 50m sprints': WorkoutMovementVariant.swimming,
      'Elliptical': WorkoutMovementVariant.elliptical,
      'Suspended crossess': WorkoutMovementVariant.suspensionCross,
    };
    for (final entry in preciseMovements.entries) {
      expect(
        resolveWorkoutMovementVariant(
          WorkoutAnimationType.generic,
          entry.key,
        ),
        entry.value,
        reason: entry.key,
      );
    }
  });

  testWidgets('WorkoutSimulationWidget renders correctly', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: WorkoutSimulationWidget(
            animationType: WorkoutAnimationType.press,
            exerciseName: 'Arnold Shoulder Press',
            isResting: false,
          ),
        ),
      ),
    );

    expect(find.text('MÔ PHỎNG ĐỘNG TÁC'), findsOneWidget);
    expect(find.text('Đẩy qua đầu'), findsOneWidget);
    expect(find.byType(WorkoutSimulationWidget), findsOneWidget);
  });

  testWidgets('DetailBottomSheet displays 3 phases and workout breakdown',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final action = ActionItem(
      kind: 'exercise',
      wgerId: 0,
      name: 'Full Body workout (intermediate)',
      details: {
        'duration': 30,
        'calories_burned': 200.0,
        'description':
            '- Seated Hip Adduction: 3 hiệp x 10-12 lần\n- Arnold Shoulder Press: 3 hiệp x 10-12 lần',
      },
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => showDetailBottomSheet(context, action),
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    );

    // Open sheet
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    // Verify elements
    expect(find.text('Full Body workout (intermediate)'), findsOneWidget);
    expect(find.text('Lộ trình & Giai đoạn'), findsOneWidget);
    expect(find.text('Kỹ thuật & An toàn'), findsOneWidget);
    expect(find.text('Bắt đầu luyện tập'), findsOneWidget);
    expect(find.text('Lưu nhật ký'), findsOneWidget);

    // Verify phases
    expect(find.textContaining('Giai đoạn 1: Khởi động'), findsOneWidget);
    expect(find.textContaining('Giai đoạn 2: Thân bài'), findsOneWidget);
    expect(find.textContaining('Giai đoạn 3: Giãn cơ'), findsOneWidget);

    // Verify sub-exercises
    expect(find.text('Seated Hip Adduction'), findsOneWidget);
    expect(find.text('Arnold Shoulder Press'), findsOneWidget);
  });

  testWidgets('WorkoutSimulationScreen renders active exercise and controls',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final action = ActionItem(
      kind: 'exercise',
      wgerId: 0,
      name: 'Full Body workout',
      details: {
        'duration': 30,
        'calories_burned': 200.0,
        'description': '- Arnold Shoulder Press: 3 hiệp x 10-12 lần',
      },
    );
    final routine = WorkoutRoutineParser.parseFromAction(action);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => UserProvider()..setDemoUser()),
          ChangeNotifierProvider(create: (_) => ExerciseProvider()),
        ],
        child: MaterialApp(
          home: WorkoutSimulationScreen(routine: routine),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 100));

    // Verify header and simulation
    expect(find.text('Full Body workout'), findsOneWidget);
    expect(find.byType(WorkoutSimulationWidget), findsOneWidget);
    expect(find.textContaining('HIỆP 1'), findsOneWidget);

    // The first exercise is warmup (timed exercise) with 'Xong hiệp'
    expect(find.text('Xong hiệp'), findsOneWidget);

    // Tap complete set -> Should trigger rest timer
    await tester.tap(find.text('Xong hiệp'));
    await tester.pump(const Duration(milliseconds: 100));

    // Rest interval banner should appear
    expect(find.text('NGHỈ NGƠI & HỒI SỨC'), findsOneWidget);
    expect(find.text('Bỏ qua nghỉ & Tập tiếp'), findsOneWidget);

    // Skip rest
    await tester.tap(find.text('Bỏ qua nghỉ & Tập tiếp'));
    await tester.pump(const Duration(milliseconds: 100));
  });
}
