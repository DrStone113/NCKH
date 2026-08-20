import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/meal_model.dart';

void main() {
  group('MealTypeUtils', () {
    test('normalizes backend and app meal type values', () {
      expect(MealTypeUtils.normalize('breakfast'), 'sang');
      expect(MealTypeUtils.normalize('lunch'), 'trua');
      expect(MealTypeUtils.normalize('dinner'), 'toi');
      expect(MealTypeUtils.normalize('snack'), 'phu');
      expect(MealTypeUtils.normalize('TRUA'), 'trua');
    });

    test('MealModel always stores the normalized type', () {
      final meal = MealModel(
        id: 'meal-1',
        userId: 'user-1',
        name: 'Bún cá',
        date: DateTime(2026, 8, 14),
        mealType: 'lunch',
      );

      expect(meal.mealType, 'trua');
      expect(meal.mealTypeText, 'Bữa trưa');
    });
  });

  test('MealItem safely parses numeric strings and rejects negative values',
      () {
    final item = MealItem.fromMap({
      'id': 12,
      'foodId': 34,
      'name': 'Cá',
      'weightGrams': '120.5',
      'calories': '99.2',
      'protein': '-2',
      'carbs': '0',
      'fat': 1,
    });

    expect(item.id, '12');
    expect(item.foodId, '34');
    expect(item.weightGrams, 120.5);
    expect(item.calories, 99.2);
    expect(item.protein, 0);
  });
}
