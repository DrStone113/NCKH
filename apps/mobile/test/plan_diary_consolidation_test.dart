import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/meal_model.dart';
import 'package:health_app/models/exercise_model.dart';
import 'package:health_app/providers/nutrition_provider.dart';
import 'package:health_app/providers/exercise_provider.dart';
import 'package:health_app/services/meal_diary_store.dart';
import 'package:health_app/models/planned_projection.dart';

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

      // An uncompleted actual observation does not count as consumed yet.
      final observedMeal = _sampleMeal(
        id: 'actual-1',
        name: 'Phở bò tái',
        calories: 450,
        isCompleted: false,
      );
      await provider.addMeal(observedMeal);

      expect(provider.todayMeals.length, 1);
      expect(provider.todayMeals.first.isCompleted, isFalse);
      expect(provider.completedMealsCount, 0);
      expect(provider.pendingMealsCount, 1);
      expect(provider.consumedCalories, 0.0);
      expect(provider.plannedCalories, 450.0);
    });

    test(
        'toggle meal completion immediately updates consumedCalories and store',
        () async {
      final store = _MemoryMealStore();
      final provider = NutritionProvider(mealStore: store);

      final observedMeal = _sampleMeal(
        id: 'actual-2',
        name: 'Cơm tấm sườn',
        calories: 600,
        isCompleted: false,
      );
      await provider.addMeal(observedMeal);

      expect(provider.consumedCalories, 0.0);

      // User taps 'Ghi nhận đã ăn'
      await provider.toggleMealCompleted('actual-2');

      expect(provider.todayMeals.first.isCompleted, isTrue);
      expect(provider.completedMealsCount, 1);
      expect(provider.pendingMealsCount, 0);
      expect(provider.consumedCalories, 600.0);

      // User untoggles
      await provider.toggleMealCompleted('actual-2');
      expect(provider.todayMeals.first.isCompleted, isFalse);
      expect(provider.consumedCalories, 0.0);
    });
  });

  group('Plan Diary Consolidation - Exercise', () {
    test(
        'uncompleted exercises do not count towards totalCaloriesBurned or totalDuration',
        () {
      final provider = ExerciseProvider();

      final observedExercise = _sampleExercise(
        id: 'actual-ex-1',
        name: 'Chạy bộ nhẹ nhàng',
        duration: 30,
        caloriesBurned: 240,
        isCompleted: false,
      );

      provider.setTodayExercisesForTesting([observedExercise]);

      expect(provider.todayExercises.length, 1);
      expect(provider.todayExercises.first.isCompleted, isFalse);
      expect(provider.completedCount, 0);
      expect(provider.pendingCount, 1);
      expect(provider.totalCaloriesBurned, 0.0);
      expect(provider.totalDuration, 0);
      expect(provider.plannedCaloriesBurned, 240.0);
      expect(provider.plannedDuration, 30);

      // When completed
      final completedEx = observedExercise.copyWith(isCompleted: true);
      provider.setTodayExercisesForTesting([completedEx]);

      expect(provider.todayExercises.first.isCompleted, isTrue);
      expect(provider.completedCount, 1);
      expect(provider.pendingCount, 0);
      expect(provider.totalCaloriesBurned, 240.0);
      expect(provider.totalDuration, 30);
    });
  });

  test('planned projections are read-only and never enter the meal diary store',
      () {
    final planned = PlannedMealProjection(
      planItemId: 'plan-item-1',
      planId: 'plan-1',
      revisionId: 'revision-1',
      userId: 'user-test-123',
      name: 'Bữa trưa dự kiến',
      mealType: 'trua',
      date: DateTime(2026, 9, 21),
      calories: 500,
      protein: 30,
      carbs: 50,
      fat: 15,
    );
    final store = _MemoryMealStore();

    expect(planned.planItemId, 'plan-item-1');
    expect(store.values, isEmpty);
  });

  test(
      'logging a planned meal creates a separate actual observation with source references',
      () async {
    final store = _MemoryMealStore();
    final provider = NutritionProvider(mealStore: store);
    final planned = PlannedMealProjection(
      planItemId: 'planned-source-item',
      planId: 'plan-source',
      revisionId: 'revision-source',
      userId: 'user-test-123',
      name: 'Bữa tối dự kiến',
      mealType: 'toi',
      date: DateTime(2026, 9, 21),
      calories: 600,
      protein: 35,
      carbs: 60,
      fat: 18,
    );

    final result = await provider.logPlannedMealObservation(planned);

    expect(result.isPersisted, isTrue);
    expect(store.values, hasLength(1));
    final actual = store.values.values.single;
    expect(actual.id, isNot(planned.planItemId));
    expect(actual.sourcePlanId, planned.planId);
    expect(actual.sourceRevisionId, planned.revisionId);
    expect(actual.sourcePlanItemId, planned.planItemId);
  });
}
