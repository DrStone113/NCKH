import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/user_model.dart';

void main() {
  test('Plan context retains confirmed structured workout intake', () {
    final user = UserModel(
      id: 'test-user',
      email: 'test@example.invalid',
      name: 'Test User',
      age: 30,
      equationSex: 'male',
      height: 170,
      weight: 70,
      activityLevel: 'moderate',
      healthGoal: 'maintain',
      workoutProfile: const WorkoutProfile(
        availableDaysPerWeek: 4,
        defaultSessionDurationMinutes: 60,
        trainingLocation: 'home',
        availableEquipment: ['none'],
        exerciseSafetyProfile: {'acute_injury': false},
      ),
    );

    final context = user.toPlanRequestContext();
    expect(context['workout_profile']['available_days_per_week'], 4);
    expect(context['workout_profile']['exercise_safety_profile'], isNotNull);
    expect(context['age'], 30);
  });
}
