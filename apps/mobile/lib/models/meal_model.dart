/// Thành phần của một món ăn (ví dụ: Cơm trắng 200g, Heo quay 100g)
class MealItem {
  final String id;
  final String foodId;   // tham chiếu FoodItem trong database
  final String name;     // tên nguyên liệu
  final double weightGrams;
  final double calories;
  final double protein;
  final double carbs;
  final double fat;

  MealItem({
    required this.id,
    required this.foodId,
    required this.name,
    required this.weightGrams,
    required this.calories,
    required this.protein,
    required this.carbs,
    required this.fat,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'foodId': foodId,
    'name': name,
    'weightGrams': weightGrams,
    'calories': calories,
    'protein': protein,
    'carbs': carbs,
    'fat': fat,
  };

  factory MealItem.fromMap(Map<String, dynamic> map) => MealItem(
    id: map['id'] ?? '',
    foodId: map['foodId'] ?? '',
    name: map['name'] ?? '',
    weightGrams: (map['weightGrams'] ?? 0).toDouble(),
    calories: (map['calories'] ?? 0).toDouble(),
    protein: (map['protein'] ?? 0).toDouble(),
    carbs: (map['carbs'] ?? 0).toDouble(),
    fat: (map['fat'] ?? 0).toDouble(),
  );

  MealItem copyWith({double? weightGrams, double? calories, double? protein, double? carbs, double? fat}) =>
    MealItem(
      id: id, foodId: foodId, name: name,
      weightGrams: weightGrams ?? this.weightGrams,
      calories: calories ?? this.calories,
      protein: protein ?? this.protein,
      carbs: carbs ?? this.carbs,
      fat: fat ?? this.fat,
    );
}

/// Một món ăn gồm nhiều thành phần (ví dụ: "Cơm heo quay" = cơm + heo quay)
class MealModel {
  final String id;
  final String userId;
  final String name;       // tên món ăn (ví dụ: "Cơm heo quay")
  final DateTime date;
  final String mealType;   // sang, trua, toi, phu
  final List<MealItem> items; // danh sách thành phần
  final bool isCompleted;

  MealModel({
    required this.id,
    required this.userId,
    required this.name,
    required this.date,
    required this.mealType,
    this.items = const [],
    this.isCompleted = false,
  });

  // Tổng macro tính từ items
  double get calories => items.fold(0, (s, i) => s + i.calories);
  double get protein  => items.fold(0, (s, i) => s + i.protein);
  double get carbs    => items.fold(0, (s, i) => s + i.carbs);
  double get fat      => items.fold(0, (s, i) => s + i.fat);
  double get totalGrams => items.fold(0, (s, i) => s + i.weightGrams);

  Map<String, dynamic> toMap() => {
    'id': id,
    'userId': userId,
    'name': name,
    'date': date.toIso8601String(),
    'mealType': mealType,
    'items': items.map((i) => i.toMap()).toList(),
    'isCompleted': isCompleted,
  };

  factory MealModel.fromMap(Map<String, dynamic> map) {
    // Backward compat: nếu data cũ không có items, tạo 1 item từ chính nó
    List<MealItem> items = [];
    if (map['items'] != null && (map['items'] as List).isNotEmpty) {
      items = (map['items'] as List)
          .map((i) => MealItem.fromMap(i as Map<String, dynamic>))
          .toList();
    } else if (map['calories'] != null) {
      // Data cũ: wrap thành 1 item
      items = [
        MealItem(
          id: '${map['id']}_item',
          foodId: map['foodId'] ?? '',
          name: map['name'] ?? '',
          weightGrams: (map['weightGrams'] ?? 0).toDouble(),
          calories: (map['calories'] ?? 0).toDouble(),
          protein: (map['protein'] ?? 0).toDouble(),
          carbs: (map['carbs'] ?? 0).toDouble(),
          fat: (map['fat'] ?? 0).toDouble(),
        ),
      ];
    }

    return MealModel(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      name: map['name'] ?? '',
      date: DateTime.parse(map['date']),
      mealType: map['mealType'] ?? 'sang',
      items: items,
      isCompleted: map['isCompleted'] ?? false,
    );
  }

  MealModel copyWith({
    String? name,
    List<MealItem>? items,
    bool? isCompleted,
  }) => MealModel(
    id: id,
    userId: userId,
    name: name ?? this.name,
    date: date,
    mealType: mealType,
    items: items ?? this.items,
    isCompleted: isCompleted ?? this.isCompleted,
  );

  String get mealTypeText {
    switch (mealType) {
      case 'breakfast': case 'sang': return 'Bữa sáng';
      case 'lunch':     case 'trua': return 'Bữa trưa';
      case 'dinner':    case 'toi':  return 'Bữa tối';
      case 'snack':     case 'phu':  return 'Ăn phụ';
      default: return 'Khác';
    }
  }
}

/// Model cho thực phẩm trong database
class FoodItem {
  final String id;
  final String? userId;
  final String name;
  final double caloriesPer100g;
  final double proteinPer100g;
  final double fatPer100g;
  final double carbsPer100g;
  final String category;
  final bool isSystemFood;

  FoodItem({
    required this.id,
    this.userId,
    required this.name,
    required this.caloriesPer100g,
    required this.proteinPer100g,
    required this.fatPer100g,
    required this.carbsPer100g,
    required this.category,
    this.isSystemFood = true,
  });

  double caloriesForGrams(double g) => caloriesPer100g * g / 100;
  double proteinForGrams(double g)  => proteinPer100g  * g / 100;
  double fatForGrams(double g)      => fatPer100g      * g / 100;
  double carbsForGrams(double g)    => carbsPer100g    * g / 100;

  /// Tạo MealItem từ FoodItem với gram cho trước
  MealItem toMealItem({required String itemId, required double grams}) => MealItem(
    id: itemId,
    foodId: id,
    name: name,
    weightGrams: grams,
    calories: caloriesForGrams(grams),
    protein: proteinForGrams(grams),
    carbs: carbsForGrams(grams),
    fat: fatForGrams(grams),
  );

  Map<String, dynamic> toMap() => {
    'id': id, 'userId': userId, 'name': name,
    'caloriesPer100g': caloriesPer100g, 'proteinPer100g': proteinPer100g,
    'fatPer100g': fatPer100g, 'carbsPer100g': carbsPer100g,
    'category': category, 'isSystemFood': isSystemFood,
  };

  factory FoodItem.fromMap(Map<String, dynamic> map) => FoodItem(
    id: map['id'] ?? '',
    userId: map['userId'],
    name: map['name'] ?? '',
    caloriesPer100g: (map['caloriesPer100g'] ?? 0).toDouble(),
    proteinPer100g:  (map['proteinPer100g']  ?? 0).toDouble(),
    fatPer100g:      (map['fatPer100g']      ?? 0).toDouble(),
    carbsPer100g:    (map['carbsPer100g']    ?? 0).toDouble(),
    category: map['category'] ?? '',
    isSystemFood: map['isSystemFood'] ?? true,
  );
}

/// Template thành phần trong món mẫu
class SavedMealItemTemplate {
  final String foodId;
  final String name;
  final double defaultGrams;

  SavedMealItemTemplate({
    required this.foodId,
    required this.name,
    required this.defaultGrams,
  });

  Map<String, dynamic> toJson() => {
    'foodId': foodId,
    'name': name,
    'defaultGrams': defaultGrams,
  };

  factory SavedMealItemTemplate.fromJson(Map<String, dynamic> j) =>
      SavedMealItemTemplate(
        foodId: j['foodId'] ?? '',
        name: j['name'] ?? '',
        defaultGrams: (j['defaultGrams'] ?? 100).toDouble(),
      );
}

/// Món ăn đã lưu / mẫu — dùng để tạo nhanh MealModel
class SavedMealTemplate {
  final String id;
  final String name;
  final String emoji;
  final List<SavedMealItemTemplate> items;

  SavedMealTemplate({
    required this.id,
    required this.name,
    this.emoji = '🍽️',
    required this.items,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'emoji': emoji,
    'items': items.map((i) => i.toJson()).toList(),
  };

  factory SavedMealTemplate.fromJson(Map<String, dynamic> j) =>
      SavedMealTemplate(
        id: j['id'] ?? '',
        name: j['name'] ?? '',
        emoji: j['emoji'] ?? '🍽️',
        items: (j['items'] as List<dynamic>? ?? [])
            .map((i) => SavedMealItemTemplate.fromJson(i as Map<String, dynamic>))
            .toList(),
      );

  /// Tính tổng calo ước tính từ database
  double estimatedCalories(List<FoodItem> db) {
    double total = 0;
    for (final item in items) {
      final food = db.where((f) => f.id == item.foodId).firstOrNull;
      if (food != null) total += food.caloriesForGrams(item.defaultGrams);
    }
    return total;
  }
}
