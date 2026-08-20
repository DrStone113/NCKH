import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/meal_model.dart';
import 'package:health_app/utils/meal_nutrition_utils.dart';

void main() {
  final foods = [
    FoodItem(
      id: 'bun',
      name: 'Bún',
      caloriesPer100g: 110,
      proteinPer100g: 1.7,
      fatPer100g: 0,
      carbsPer100g: 25.7,
      category: 'Tinh bột',
    ),
    FoodItem(
      id: 'fish',
      name: 'Cá rô phi',
      caloriesPer100g: 100,
      proteinPer100g: 19.7,
      fatPer100g: 2.3,
      carbsPer100g: 0,
      category: 'Hải sản',
    ),
  ];

  test('catalog calories and saved meal calories stay identical', () {
    final result = MealNutritionUtils.resolveDish(
      {
        'name': 'Bún cá',
        'estimated_calories': 500,
        'ingredients': [
          {'name': 'Bún', 'grams': 200, 'category': 'carb'},
          {'name': 'Cá rô phi', 'grams': 120, 'category': 'protein'},
        ],
      },
      foods,
      idSeed: 'test',
    );

    expect(result.usesCatalogEstimate, isTrue);
    expect(result.items, hasLength(2));
    expect(result.calories, closeTo(500, 0.001));
    expect(result.items.first.weightGrams, 200);
  });

  test('structured chatbot components are not rescaled again', () {
    final result = MealNutritionUtils.resolveDish(
      {
        'components': [
          {
            'name': 'Bún',
            'serving_grams': 250,
            'calories': 300,
            'protein': 5,
            'carbs': 60,
            'fat': 2,
          },
        ],
        'estimated_calories': 500,
      },
      foods,
      idSeed: 'test',
    );

    expect(result.usesCatalogEstimate, isFalse);
    expect(result.calories, 300);
  });
}
