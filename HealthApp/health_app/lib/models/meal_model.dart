/// Model cho bảng mon_an - Thực phẩm
class FoodItem {
  final String id;
  final String? userId; // null = món hệ thống
  final String name;
  final double caloriesPer100g;
  final double proteinPer100g;
  final double fatPer100g;
  final double carbsPer100g;
  final Map<String, double>? micronutrients; // vi_chat_dinh_duong
  final String category; // danh_muc
  final bool isSystemFood;

  FoodItem({
    required this.id,
    this.userId,
    required this.name,
    required this.caloriesPer100g,
    required this.proteinPer100g,
    required this.fatPer100g,
    required this.carbsPer100g,
    this.micronutrients,
    required this.category,
    this.isSystemFood = true,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'name': name,
      'caloriesPer100g': caloriesPer100g,
      'proteinPer100g': proteinPer100g,
      'fatPer100g': fatPer100g,
      'carbsPer100g': carbsPer100g,
      'micronutrients': micronutrients,
      'category': category,
      'isSystemFood': isSystemFood,
    };
  }

  factory FoodItem.fromMap(Map<String, dynamic> map) {
    return FoodItem(
      id: map['id'] ?? '',
      userId: map['userId'],
      name: map['name'] ?? '',
      caloriesPer100g: (map['caloriesPer100g'] ?? 0).toDouble(),
      proteinPer100g: (map['proteinPer100g'] ?? 0).toDouble(),
      fatPer100g: (map['fatPer100g'] ?? 0).toDouble(),
      carbsPer100g: (map['carbsPer100g'] ?? 0).toDouble(),
      micronutrients: map['micronutrients'] != null
          ? Map<String, double>.from(map['micronutrients'])
          : null,
      category: map['category'] ?? '',
      isSystemFood: map['isSystemFood'] ?? true,
    );
  }

  // Calculated values based on weight
  double caloriesForGrams(double grams) => caloriesPer100g * grams / 100;
  double proteinForGrams(double grams) => proteinPer100g * grams / 100;
  double fatForGrams(double grams) => fatPer100g * grams / 100;
  double carbsForGrams(double grams) => carbsPer100g * grams / 100;
}

/// Model cho bảng nhat_ky_an_uong - Nhật ký ăn uống
class MealModel {
  final String id;
  final String userId;
  final String name; // tên món ăn
  final String? foodId; // tham chiếu tới mon_an
  final DateTime date;
  final String mealType; // sang, trua, toi, phu
  final double weightGrams; // khoi_luong_an
  final double calories;
  final double protein;
  final double carbs;
  final double fat;

  MealModel({
    required this.id,
    required this.userId,
    required this.name,
    this.foodId,
    required this.date,
    required this.mealType,
    this.weightGrams = 0,
    required this.calories,
    required this.protein,
    required this.carbs,
    required this.fat,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'name': name,
      'foodId': foodId,
      'date': date.toIso8601String(),
      'mealType': mealType,
      'weightGrams': weightGrams,
      'calories': calories,
      'protein': protein,
      'carbs': carbs,
      'fat': fat,
    };
  }

  factory MealModel.fromMap(Map<String, dynamic> map) {
    return MealModel(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      name: map['name'] ?? '',
      foodId: map['foodId'],
      date: DateTime.parse(map['date']),
      mealType: map['mealType'] ?? 'sang',
      weightGrams: (map['weightGrams'] ?? 0).toDouble(),
      calories: (map['calories'] ?? 0).toDouble(),
      protein: (map['protein'] ?? 0).toDouble(),
      carbs: (map['carbs'] ?? 0).toDouble(),
      fat: (map['fat'] ?? 0).toDouble(),
    );
  }

  String get mealTypeText {
    switch (mealType) {
      case 'breakfast':
      case 'sang':
        return 'Bữa sáng';
      case 'lunch':
      case 'trua':
        return 'Bữa trưa';
      case 'dinner':
      case 'toi':
        return 'Bữa tối';
      case 'snack':
      case 'phu':
        return 'Ăn phụ';
      default:
        return 'Khác';
    }
  }
}
