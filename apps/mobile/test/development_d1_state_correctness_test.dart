import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/app_state_value.dart';
import 'package:health_app/models/canonical_weight.dart';
import 'package:health_app/models/health_models.dart';
import 'package:health_app/models/lifestyle_model.dart';
import 'package:health_app/models/meal_model.dart';
import 'package:health_app/providers/nutrition_provider.dart';
import 'package:health_app/services/meal_diary_store.dart';

class _MemoryMealStore implements MealDiaryStore {
  final Map<String, MealModel> values = {};
  final bool failWrites;

  _MemoryMealStore({this.failWrites = false});

  @override
  Future<void> save(MealModel meal) async {
    if (failWrites) throw StateError('synthetic persistence failure');
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

MealModel _consumedMeal(String id, double calories) => MealModel(
      id: id,
      userId: 'synthetic-d1-user',
      name: 'Synthetic meal',
      date: DateTime.now(),
      mealType: 'phu',
      isCompleted: true,
      items: [
        MealItem(
          id: '$id-item',
          foodId: 'synthetic',
          name: 'Synthetic component',
          weightGrams: 100,
          calories: calories,
          protein: 10,
          carbs: 20,
          fat: 5,
        ),
      ],
    );

void main() {
  group('D1 meal persistence', () {
    test('consumed log is persisted and immediately changes remaining calories',
        () async {
      final store = _MemoryMealStore();
      final provider = NutritionProvider(mealStore: store);
      const target = 2000.0;
      final before = target - provider.consumedCalories;

      final result = await provider.addMeal(_consumedMeal('meal-1', 450));
      final subsequentReader = NutritionProvider(mealStore: store);
      final readOk = await subsequentReader.refreshTodayMealsAuthoritatively(
        'synthetic-d1-user',
        includeActivePlan: false,
      );

      expect(result.status, WriteStatus.persisted);
      expect(provider.todayMeals.single.isCompleted, isTrue);
      expect(provider.consumedCalories, 450);
      expect(target - provider.consumedCalories, lessThan(before));
      expect(readOk, isTrue);
      expect(subsequentReader.consumedCalories, 450);
    });

    test('failed meal write rolls back and cannot report persisted', () async {
      final provider = NutritionProvider(
        mealStore: _MemoryMealStore(failWrites: true),
      );

      final result = await provider.addMeal(_consumedMeal('meal-2', 300));

      expect(result.status, WriteStatus.error);
      expect(result.isPersisted, isFalse);
      expect(provider.todayMeals, isEmpty);
      expect(provider.consumedCalories, 0);
    });
  });

  group('D1 source and freshness semantics', () {
    test('numeric zero is KNOWN rather than implicitly missing', () {
      final value = AppStateValue<double>(
        value: 0,
        source: 'synthetic.authoritative_source',
        observedAt: DateTime.utc(2026, 8, 23),
        status: DataStatus.known,
      );
      expect(value.toJson()['value'], 0);
      expect(value.toJson()['status'], 'KNOWN');
    });

    test('unloaded lifestyle defaults are not observations', () {
      final log = LifestyleLog(
        id: 'synthetic',
        userId: 'synthetic-d1-user',
        date: DateTime.utc(2026, 8, 23),
      );
      expect(log.hasMoodObservation, isFalse);
      expect(log.hasSleepObservation, isFalse);
      expect(log.hasStressObservation, isFalse);
      expect(log.hasLifestyleWaterObservation, isFalse);
      expect(log.toMap().containsKey('moodScore'), isFalse);
      expect(log.toMap().containsKey('sleepHours'), isFalse);
      expect(log.toMap().containsKey('waterIntakeMl'), isFalse);
    });

    test('latest measurement wins and records a profile conflict', () {
      final latest = BodyMetrics(
        id: 'weight-1',
        userId: 'synthetic-d1-user',
        weight: 68,
        bmi: 23.5,
        recordedAt: DateTime.utc(2026, 8, 23, 7),
      );
      final canonical = CanonicalWeightResolver.resolve(
        profileWeight: 70,
        latestMeasurement: latest,
      );

      expect(canonical.value, 68);
      expect(canonical.source, 'weight_history.latest_measurement');
      expect(canonical.status, DataStatus.conflict);
      expect(canonical.conflict, isNotNull);
    });

    test('a newly synchronized profile agrees with canonical current weight', () {
      final latest = BodyMetrics(
        id: 'weight-2',
        userId: 'synthetic-d1-user',
        weight: 67.5,
        bmi: 23.4,
        recordedAt: DateTime.utc(2026, 8, 23, 8),
      );
      final canonical = CanonicalWeightResolver.resolve(
        profileWeight: 67.5,
        latestMeasurement: latest,
      );
      expect(canonical.value, 67.5);
      expect(canonical.status, DataStatus.known);
    });

    test('missing water is distinct from an authoritative known zero', () {
      const consumed = AppStateValue<double>(
        value: null,
        source: 'health.water_intake',
        observedAt: null,
        status: DataStatus.notLoaded,
      );
      final measuredZero = AppStateValue<double>(
        value: 0,
        source: 'health.water_intake',
        observedAt: DateTime.utc(2026, 8, 23),
        status: DataStatus.known,
      );
      expect(consumed.value, isNull);
      expect(consumed.status, DataStatus.notLoaded);
      expect(measuredZero.value, 0);
      expect(measuredZero.status, DataStatus.known);
      expect(measuredZero.source, consumed.source);
    });
  });
}
