import '../models/meal_model.dart';

class DishNutritionResult {
  final List<MealItem> items;
  final bool usesCatalogEstimate;

  const DishNutritionResult({
    required this.items,
    required this.usesCatalogEstimate,
  });

  double get calories => items.fold(0, (sum, item) => sum + item.calories);
  double get protein => items.fold(0, (sum, item) => sum + item.protein);
  double get carbs => items.fold(0, (sum, item) => sum + item.carbs);
  double get fat => items.fold(0, (sum, item) => sum + item.fat);
}

/// Chuyển một món trong catalog thành đúng danh sách [MealItem] được lưu.
///
/// Catalog cũ có hai con số khác nhau: `estimated_calories` dùng ở danh sách
/// và tổng kcal tính từ nguyên liệu dùng sau khi chọn. Hàm này lấy con số của
/// catalog làm tổng chuẩn rồi phân bổ lại kcal thành phần theo cùng một tỷ lệ,
/// nhờ vậy card trước và sau khi chọn luôn khớp nhau.
abstract final class MealNutritionUtils {
  static DishNutritionResult resolveDish(
    Map<String, dynamic> dish,
    List<FoodItem> foods, {
    String? idSeed,
  }) {
    final seed = idSeed ?? DateTime.now().microsecondsSinceEpoch.toString();
    final directComponents = _mapList(dish['components']);
    if (directComponents.isNotEmpty) {
      final items = <MealItem>[];
      for (final component in directComponents) {
        final name = component['name']?.toString().trim() ?? '';
        if (name.isEmpty) continue;
        final grams = _positiveDouble(
          component['serving_grams'] ?? component['grams'],
          fallback: 100,
        );
        items.add(
          MealItem(
            id: 'component_${seed}_${items.length}',
            foodId: component['food_id']?.toString() ?? '',
            name: name,
            weightGrams: grams,
            calories: _nonNegativeDouble(component['calories']),
            protein: _nonNegativeDouble(component['protein']),
            carbs: _nonNegativeDouble(component['carbs']),
            fat: _nonNegativeDouble(component['fat']),
          ),
        );
      }
      return DishNutritionResult(
        items: List.unmodifiable(items),
        usesCatalogEstimate: false,
      );
    }

    final rawIngredients = _mapList(dish['ingredients']);
    final items = <MealItem>[];
    for (final ingredient in rawIngredients) {
      final name = ingredient['name']?.toString().trim() ?? '';
      if (name.isEmpty) continue;
      final grams = _positiveDouble(ingredient['grams'], fallback: 100);
      final food = _findFood(name, foods);
      if (food != null) {
        items.add(
          food.toMealItem(
            itemId: '${food.id}_${seed}_${items.length}',
            grams: grams,
          ),
        );
        continue;
      }

      final fallback = _fallbackPer100g(
        ingredient['category']?.toString() ?? '',
      );
      items.add(
        MealItem(
          id: 'ingredient_${seed}_${items.length}',
          foodId: '',
          name: name,
          weightGrams: grams,
          calories: fallback.$1 * grams / 100,
          protein: fallback.$2 * grams / 100,
          carbs: fallback.$3 * grams / 100,
          fat: fallback.$4 * grams / 100,
        ),
      );
    }

    final estimated = _nonNegativeDouble(
      dish['estimated_calories'] ?? dish['total_calories'],
    );
    final calculated = items.fold<double>(
      0,
      (sum, item) => sum + item.calories,
    );
    if (items.isEmpty || estimated <= 0) {
      return DishNutritionResult(
        items: List.unmodifiable(items),
        usesCatalogEstimate: false,
      );
    }

    final adjusted = <MealItem>[];
    if (calculated > 0) {
      final calorieFactor = estimated / calculated;
      for (final item in items) {
        adjusted.add(item.copyWith(calories: item.calories * calorieFactor));
      }
    } else {
      final totalGrams = items.fold<double>(
        0,
        (sum, item) => sum + item.weightGrams,
      );
      for (final item in items) {
        final ratio = totalGrams > 0 ? item.weightGrams / totalGrams : 0;
        adjusted.add(item.copyWith(calories: estimated * ratio));
      }
    }

    return DishNutritionResult(
      items: List.unmodifiable(adjusted),
      usesCatalogEstimate: true,
    );
  }

  static FoodItem? _findFood(String name, List<FoodItem> foods) {
    final normalized = _normalizeName(name);
    for (final food in foods) {
      if (_normalizeName(food.name) == normalized) return food;
    }
    for (final food in foods) {
      final candidate = _normalizeName(food.name);
      if (candidate.length < 3 || normalized.length < 3) continue;
      if (candidate.contains(normalized) || normalized.contains(candidate)) {
        return food;
      }
    }
    return null;
  }

  static String _normalizeName(String value) =>
      value.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

  static List<Map<String, dynamic>> _mapList(dynamic value) {
    if (value is! List) return const [];
    return value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  static double _nonNegativeDouble(dynamic value) {
    final parsed = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '') ?? 0;
    if (!parsed.isFinite || parsed <= 0) return 0;
    return parsed;
  }

  static double _positiveDouble(dynamic value, {required double fallback}) {
    final parsed = _nonNegativeDouble(value);
    return parsed > 0 ? parsed : fallback;
  }

  static (double, double, double, double) _fallbackPer100g(
    String category,
  ) {
    switch (category.trim().toLowerCase()) {
      case 'carb':
        return (130, 2.7, 28, 0.3);
      case 'protein':
        return (165, 24, 0, 6);
      case 'veggie':
        return (30, 1.5, 5, 0.3);
      default:
        return (100, 4, 14, 3);
    }
  }
}
