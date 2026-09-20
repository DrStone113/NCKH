import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/meal_model.dart';
import 'package:health_app/models/exercise_model.dart';
import 'package:health_app/providers/nutrition_provider.dart';
import 'package:health_app/providers/exercise_provider.dart';
import 'package:health_app/services/meal_diary_store.dart';

class _MemoryMealStore implements MealDiaryStore {
  final Map<String, MealModel> values = {};

  @override
  Future<void> save(MealModel meal) async {
    values[meal.id] = meal;
  }

  @override
  Future<MealModel?> read(String mealId) async => values[mealId];

  @override
  Future<List<MealModel>> readForUser(String userId) async =>
      values.values.where((meal) => meal.userId == userId).toList();

  @override
  Future<void> delete(String mealId) async {
    values.remove(mealId);
  }
}

MealModel _sampleMeal({
  required String id,
  required String name,
  required double calories,
  required bool isCompleted,
}) {
  return MealModel(
    id: id,
    userId: 'user-test-123',
    name: name,
    date: DateTime.now(),
    mealType: 'sang',
    isCompleted: isCompleted,
    items: [
      MealItem(
        id: '$id-item',
        foodId: 'food-1',
        name: name,
        weightGrams: 100,
        calories: calories,
        protein: 10,
        carbs: 20,
        fat: 5,
      ),
    ],
  );
}

ExerciseModel _sampleExercise({
  required String id,
  required String name,
  required int duration,
  required double caloriesBurned,
  required bool isCompleted,
}) {
  return ExerciseModel(
    id: id,
    userId: 'user-test-123',
    name: name,
    date: DateTime.now(),
    duration: duration,
    caloriesBurned: caloriesBurned,
    type: 'cardio',
    isCompleted: isCompleted,
  );
}

void main() {
  group('Plan Diary Consolidation - Nutrition', () {
    test('uncompleted meals do not count towards consumedCalories', () async {
      final store = _MemoryMealStore();
      final provider = NutritionProvider(mealStore: store);

      // Add a planned (uncompleted) meal
      final plannedMeal = _sampleMeal(
        id: 'planned-1',
        name: 'Phở bò tái',
        calories: 450,
        isCompleted: false,
      );
      await provider.addMeal(plannedMeal);

      expect(provider.todayMeals.length, 1);
      expect(provider.todayMeals.first.isCompleted, isFalse);
      expect(provider.completedMealsCount, 0);
      expect(provider.pendingMealsCount, 1);
      expect(provider.consumedCalories, 0.0);
      expect(provider.plannedCalories, 450.0);
    });

    test('toggle meal completion immediately updates consumedCalories and store', () async {
      final store = _MemoryMealStore();
      final provider = NutritionProvider(mealStore: store);

      final plannedMeal = _sampleMeal(
        id: 'planned-2',
        name: 'Cơm tấm sườn',
        calories: 600,
        isCompleted: false,
      );
      await provider.addMeal(plannedMeal);

      expect(provider.consumedCalories, 0.0);

      // User taps 'Ghi nhận đã ăn'
      await provider.toggleMealCompleted('planned-2');

      expect(provider.todayMeals.first.isCompleted, isTrue);
      expect(provider.completedMealsCount, 1);
      expect(provider.pendingMealsCount, 0);
      expect(provider.consumedCalories, 600.0);

      // User untoggles
      await provider.toggleMealCompleted('planned-2');
      expect(provider.todayMeals.first.isCompleted, isFalse);
      expect(provider.consumedCalories, 0.0);
    });
  });

  group('Plan Diary Consolidation - Exercise', () {
    test('uncompleted exercises do not count towards totalCaloriesBurned or totalDuration', () {
      final provider = ExerciseProvider();

      final plannedEx = _sampleExercise(
        id: 'plan-ex-1',
        name: 'Chạy bộ nhẹ nhàng',
        duration: 30,
        caloriesBurned: 240,
        isCompleted: false,
      );

      provider.setTodayExercisesForTesting([plannedEx]);

      expect(provider.todayExercises.length, 1);
      expect(provider.todayExercises.first.isCompleted, isFalse);
      expect(provider.completedCount, 0);
      expect(provider.pendingCount, 1);
      expect(provider.totalCaloriesBurned, 0.0);
      expect(provider.totalDuration, 0);
      expect(provider.plannedCaloriesBurned, 240.0);
      expect(provider.plannedDuration, 30);

      // When completed
      final completedEx = plannedEx.copyWith(isCompleted: true);
      provider.setTodayExercisesForTesting([completedEx]);

      expect(provider.todayExercises.first.isCompleted, isTrue);
      expect(provider.completedCount, 1);
      expect(provider.pendingCount, 0);
      expect(provider.totalCaloriesBurned, 240.0);
      expect(provider.totalDuration, 30);
    });
  });
}
