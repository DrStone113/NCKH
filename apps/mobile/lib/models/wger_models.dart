/// Models cho wger API Integration
library;

import '../utils/exercise_utils.dart';

int _jsonInt(Object? value, [int fallback = 0]) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double? _jsonDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

String _jsonString(Object? value, [String fallback = '']) =>
    value?.toString().trim() ?? fallback;

List<Map<String, dynamic>> _jsonMapList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList(growable: false);
}

/// Model cho nhóm cơ từ wger API
class WgerMuscle {
  final int id;
  final String nameEn;
  final bool isFront;
  final String? imageUrlMain;
  final String? imageUrlSecondary;

  WgerMuscle({
    required this.id,
    required this.nameEn,
    required this.isFront,
    this.imageUrlMain,
    this.imageUrlSecondary,
  });

  factory WgerMuscle.fromJson(Map<String, dynamic> json) {
    return WgerMuscle(
      id: _jsonInt(json['id']),
      nameEn: _jsonString(json['name_en'] ?? json['name']),
      isFront: json['is_front'] is bool ? json['is_front'] as bool : true,
      imageUrlMain: json['image_url_main']?.toString(),
      imageUrlSecondary: json['image_url_secondary']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name_en': nameEn,
      'is_front': isFront,
      if (imageUrlMain != null) 'image_url_main': imageUrlMain,
      if (imageUrlSecondary != null) 'image_url_secondary': imageUrlSecondary,
    };
  }
}

/// Model cho thiết bị từ wger API
class WgerEquipment {
  final int id;
  final String name;

  WgerEquipment({
    required this.id,
    required this.name,
  });

  factory WgerEquipment.fromJson(Map<String, dynamic> json) {
    return WgerEquipment(
      id: _jsonInt(json['id']),
      name: _jsonString(json['name']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
    };
  }
}

/// Model cho danh mục bài tập từ wger API
class WgerExerciseCategory {
  final int id;
  final String name;

  WgerExerciseCategory({
    required this.id,
    required this.name,
  });

  factory WgerExerciseCategory.fromJson(Map<String, dynamic> json) {
    return WgerExerciseCategory(
      id: _jsonInt(json['id']),
      name: _jsonString(json['name']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
    };
  }
}

/// Model cho bài tập từ wger API
class WgerExercise {
  final int id;
  final String name;
  final String description;
  final String categoryName;
  final List<WgerMuscle> muscles;
  final List<WgerMuscle> musclesSecondary;
  final List<WgerEquipment> equipment;
  final String? imageUrl;

  WgerExercise({
    required this.id,
    required this.name,
    required this.description,
    required this.categoryName,
    required this.muscles,
    required this.musclesSecondary,
    required this.equipment,
    this.imageUrl,
  });

  List<WgerMuscle> get allMuscles {
    final byId = <int, WgerMuscle>{};
    for (final muscle in [...muscles, ...musclesSecondary]) {
      byId[muscle.id] = muscle;
    }
    return List.unmodifiable(byId.values);
  }

  int get muscleCount => allMuscles.length;

  factory WgerExercise.fromJson(Map<String, dynamic> json) {
    // Extract name
    String name = _jsonString(json['name']);

    // Extract description
    String description = _jsonString(json['description']);

    // Extract category name — backend trả về "category" hoặc "category_name"
    String categoryName = '';
    if (json['category_name'] != null) {
      categoryName = json['category_name'].toString();
    } else if (json['category'] != null) {
      if (json['category'] is Map) {
        categoryName = json['category']['name']?.toString() ?? '';
      } else if (json['category'] is String) {
        categoryName = json['category'].toString();
      }
    }

    // Extract image URL
    String? imageUrl;
    if (json['image_url'] != null) {
      imageUrl = json['image_url'].toString();
    } else {
      final images = _jsonMapList(json['images']);
      final mainImage =
          images.where((image) => image['is_main'] == true).firstOrNull;
      final selected = mainImage ?? images.firstOrNull;
      imageUrl = selected?['image']?.toString();
    }

    return WgerExercise(
      id: _jsonInt(json['id']),
      name: name,
      description: description,
      categoryName: categoryName,
      muscles: _jsonMapList(json['muscles'])
          .map(WgerMuscle.fromJson)
          .where((muscle) => muscle.id > 0)
          .toList(growable: false),
      musclesSecondary: _jsonMapList(json['muscles_secondary'])
          .map(WgerMuscle.fromJson)
          .where((muscle) => muscle.id > 0)
          .toList(growable: false),
      equipment: _jsonMapList(json['equipment'])
          .map(WgerEquipment.fromJson)
          .where((equipment) => equipment.name.isNotEmpty)
          .toList(growable: false),
      imageUrl: imageUrl,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'description': description,
      'category_name': categoryName,
      'muscles': muscles.map((m) => m.toJson()).toList(),
      'muscles_secondary': musclesSecondary.map((m) => m.toJson()).toList(),
      'equipment': equipment.map((e) => e.toJson()).toList(),
      'image_url': imageUrl,
    };
  }
}

/// Model cho thực phẩm từ wger API
class WgerIngredient {
  final int id;
  final String name;
  final double? energy; // kcal/100g
  final double? protein; // g/100g
  final double? carbohydrates; // g/100g
  final double? fat; // g/100g

  WgerIngredient({
    required this.id,
    required this.name,
    this.energy,
    this.protein,
    this.carbohydrates,
    this.fat,
  });

  factory WgerIngredient.fromJson(Map<String, dynamic> json) {
    return WgerIngredient(
      id: _jsonInt(json['id']),
      name: _jsonString(json['name']),
      energy: _jsonDouble(json['energy']),
      protein: _jsonDouble(json['protein']),
      carbohydrates: _jsonDouble(json['carbohydrates']),
      fat: _jsonDouble(json['fat']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'energy': energy,
      'protein': protein,
      'carbohydrates': carbohydrates,
      'fat': fat,
    };
  }

  // Tính calo cho lượng gram cụ thể
  double caloriesForGrams(double grams) {
    return (energy ?? 0) * grams.clamp(0, double.maxFinite) / 100;
  }

  // Tính protein cho lượng gram cụ thể
  double proteinForGrams(double grams) {
    return (protein ?? 0) * grams.clamp(0, double.maxFinite) / 100;
  }

  // Tính carbs cho lượng gram cụ thể
  double carbsForGrams(double grams) {
    return (carbohydrates ?? 0) * grams.clamp(0, double.maxFinite) / 100;
  }

  // Tính fat cho lượng gram cụ thể
  double fatForGrams(double grams) {
    return (fat ?? 0) * grams.clamp(0, double.maxFinite) / 100;
  }
}

/// Response phân trang cho danh sách bài tập
class WgerExerciseListResponse {
  final int count;
  final String? next;
  final List<WgerExercise> results;

  WgerExerciseListResponse({
    required this.count,
    this.next,
    required this.results,
  });

  factory WgerExerciseListResponse.fromJson(Map<String, dynamic> json) {
    final results = _jsonMapList(json['results'])
        .map(WgerExercise.fromJson)
        .where((exercise) => exercise.name.isNotEmpty)
        .toList(growable: false);
    return WgerExerciseListResponse(
      count: _jsonInt(json['count']),
      next: json['next']?.toString(),
      results: results,
    );
  }
}

/// Response phân trang cho danh sách thực phẩm
class WgerIngredientListResponse {
  final int count;
  final String? next;
  final List<WgerIngredient> results;

  WgerIngredientListResponse({
    required this.count,
    this.next,
    required this.results,
  });

  factory WgerIngredientListResponse.fromJson(Map<String, dynamic> json) {
    return WgerIngredientListResponse(
      count: _jsonInt(json['count']),
      next: json['next']?.toString(),
      results: _jsonMapList(json['results'])
          .map(WgerIngredient.fromJson)
          .where((ingredient) => ingredient.name.isNotEmpty)
          .toList(growable: false),
    );
  }
}

/// Model cho action item từ chatbot structured response
class ActionItem {
  final String kind; // "exercise" | "food"
  final int wgerId;
  final String name;
  final Map<String, dynamic> details;

  ActionItem({
    required this.kind,
    required this.wgerId,
    required this.name,
    required this.details,
  });

  factory ActionItem.fromJson(Map<String, dynamic> json) {
    final kind = _jsonString(json['kind']);
    final wgerId = _jsonInt(json['wger_id']);

    // Đọc tên món ăn một cách phòng thủ từ nhiều thuộc tính có thể có
    String name = _jsonString(json['name']);
    final rawDetails = json['details'];
    final details = rawDetails is Map
        ? Map<String, dynamic>.from(rawDetails)
        : <String, dynamic>{};
    if (name.isEmpty) {
      name = details['dish_name'] as String? ??
          details['food_name'] as String? ??
          '';
    }

    if (kind == 'food') {
      if (details['calories'] == null || details['calories'] == 0) {
        final lookup = lookupFoodNutrition(name);
        details['calories'] = lookup['calories'];
        details['protein'] = lookup['protein'];
        details['carbs'] = lookup['carbs'];
        details['fat'] = lookup['fat'];
      }
    } else if (kind == 'exercise') {
      final duration = _jsonInt(
        details['duration_min'] ?? details['duration'],
        ExerciseUtils.defaultDurationMinutes,
      ).clamp(
        ExerciseUtils.minDurationMinutes,
        ExerciseUtils.maxDurationMinutes,
      );
      details['duration'] = duration;
      details['duration_min'] = duration;

      final suppliedCalories = _jsonDouble(details['calories_burned']);
      if (suppliedCalories == null ||
          !suppliedCalories.isFinite ||
          suppliedCalories <= 0) {
        final category = _jsonString(details['category'] ?? details['type']);
        final muscleCount = _jsonInt(details['muscle_count']);
        details['calories_burned'] = ExerciseUtils.calculateCalories(
          met: ExerciseUtils.estimateMet(name, category, muscleCount),
          weightKg: 70,
          durationMinutes: duration,
        );
        details['calories_estimated'] = true;
      } else {
        details['calories_burned'] = suppliedCalories;
      }
    }

    return ActionItem(
      kind: kind,
      wgerId: wgerId,
      name: name,
      details: details,
    );
  }

  static final Map<String, Map<String, double>> compoundRecipes = {
    'bún riêu': {
      'Bún': 0.50,
      'Tôm': 0.15,
      'Thịt cua': 0.15,
      'Rau': 0.20,
    },
    'bún bò huế': {
      'Bún': 0.55,
      'Thịt bò': 0.25,
      'Chả cua': 0.10,
      'Rau sống': 0.10,
    },
    'phở bò': {
      'Bánh phở': 0.60,
      'Thịt bò': 0.30,
      'Rau thơm': 0.10,
    },
    'phở gà': {
      'Bánh phở': 0.60,
      'Thịt gà': 0.30,
      'Rau thơm': 0.10,
    },
    'bún chả': {
      'Bún': 0.60,
      'Thịt heo': 0.30,
      'Rau sống': 0.10,
    },
    'bánh mì kẹp': {
      'Bánh mì': 0.50,
      'Thịt heo': 0.30,
      'Rau': 0.20,
    },
    'cơm tấm': {
      'Cơm': 0.60,
      'Thịt heo': 0.30,
      'Trứng': 0.10,
    },
  };

  static List<ActionItem> parseActions(List<dynamic>? rawActions) {
    if (rawActions == null) return [];
    final List<ActionItem> result = [];

    for (final raw in rawActions) {
      if (raw is! Map<String, dynamic>) continue;

      final action = ActionItem.fromJson(raw);
      if (action.kind == 'food') {
        final isCanonicalDish = action.details['catalog_dish_id'] != null ||
            action.details['recommendation_event_id'] != null ||
            action.details['components'] is List;
        if (isCanonicalDish) {
          result.add(action);
          continue;
        }
        final cleanName = action.name.toLowerCase().trim();
        String? matchedRecipeKey;
        for (final key in compoundRecipes.keys) {
          if (cleanName.contains(key)) {
            matchedRecipeKey = key;
            break;
          }
        }

        if (matchedRecipeKey != null) {
          final recipe = compoundRecipes[matchedRecipeKey]!;
          final totalGrams =
              (action.details['serving_grams'] as num? ?? 100.0).toDouble();

          recipe.forEach((ingredientName, ratio) {
            final ingredientGrams = totalGrams * ratio;
            final ingredientLookup = lookupFoodNutrition(ingredientName);

            final ingredientDetails = {
              'dish_name': ingredientName,
              'meal_type': action.details['meal_type'] ?? 'lunch',
              'serving_grams': ingredientGrams,
              'calories': ingredientLookup['calories'],
              'protein': ingredientLookup['protein'],
              'carbs': ingredientLookup['carbs'],
              'fat': ingredientLookup['fat'],
              'day': action.details['day'] ?? 1,
            };

            result.add(ActionItem(
              kind: 'food',
              wgerId: 0,
              name: ingredientName,
              details: ingredientDetails,
            ));
          });
          continue;
        }
      }

      result.add(action);
    }

    return result;
  }

  static Map<String, double> lookupFoodNutrition(String foodName) {
    final cleanName = foodName.toLowerCase().trim();

    // Dictionary các món ăn Việt Nam phổ biến và lượng calo/macros trên 100g
    final database = {
      'gạo': {'calories': 344.0, 'protein': 7.9, 'fat': 1.0, 'carbs': 76.2},
      'cơm': {'calories': 130.0, 'protein': 2.7, 'fat': 0.3, 'carbs': 28.0},
      'bún': {'calories': 110.0, 'protein': 1.7, 'fat': 0.0, 'carbs': 25.7},
      'phở': {'calories': 141.0, 'protein': 3.2, 'fat': 0.0, 'carbs': 32.1},
      'bánh phở': {
        'calories': 141.0,
        'protein': 3.2,
        'fat': 0.0,
        'carbs': 32.1
      },
      'bánh mì': {'calories': 249.0, 'protein': 7.9, 'fat': 0.8, 'carbs': 52.6},
      'thịt bò': {'calories': 118.0, 'protein': 21.0, 'fat': 3.8, 'carbs': 0.0},
      'thịt heo': {
        'calories': 139.0,
        'protein': 19.0,
        'fat': 7.0,
        'carbs': 0.0
      },
      'thịt heo nạc': {
        'calories': 139.0,
        'protein': 19.0,
        'fat': 7.0,
        'carbs': 0.0
      },
      'thịt gà': {
        'calories': 199.0,
        'protein': 20.3,
        'fat': 13.1,
        'carbs': 0.0
      },
      'ức gà': {'calories': 165.0, 'protein': 31.0, 'fat': 3.6, 'carbs': 0.0},
      'trứng': {'calories': 166.0, 'protein': 14.8, 'fat': 11.6, 'carbs': 0.5},
      'đậu phụ': {'calories': 95.0, 'protein': 10.9, 'fat': 5.4, 'carbs': 0.7},
      'đậu hũ': {'calories': 95.0, 'protein': 10.9, 'fat': 5.4, 'carbs': 0.7},
      'cá': {'calories': 97.0, 'protein': 18.2, 'fat': 2.7, 'carbs': 0.0},
      'tôm': {'calories': 82.0, 'protein': 17.6, 'fat': 0.9, 'carbs': 0.9},
      'thịt cua': {
        'calories': 100.0,
        'protein': 18.0,
        'fat': 1.5,
        'carbs': 0.0
      },
      'chả cua': {'calories': 120.0, 'protein': 12.0, 'fat': 5.0, 'carbs': 4.0},
      'cà chua': {'calories': 18.0, 'protein': 0.9, 'fat': 0.2, 'carbs': 3.9},
      'rau': {'calories': 25.0, 'protein': 1.5, 'fat': 0.2, 'carbs': 4.0},
      'rau sống': {'calories': 20.0, 'protein': 1.2, 'fat': 0.1, 'carbs': 3.5},
      'rau thơm': {'calories': 20.0, 'protein': 1.2, 'fat': 0.1, 'carbs': 3.5},
      'bún riêu': {
        'calories': 150.0,
        'protein': 8.0,
        'fat': 6.0,
        'carbs': 16.0
      },
      'bún bò huế': {
        'calories': 160.0,
        'protein': 9.0,
        'fat': 6.0,
        'carbs': 18.0
      },
      'phở bò': {'calories': 150.0, 'protein': 9.0, 'fat': 5.0, 'carbs': 17.0},
      'phở gà': {'calories': 140.0, 'protein': 10.0, 'fat': 4.0, 'carbs': 16.0},
      'bánh mì kẹp': {
        'calories': 260.0,
        'protein': 9.0,
        'fat': 8.0,
        'carbs': 38.0
      },
      'sữa': {'calories': 74.0, 'protein': 3.9, 'fat': 4.4, 'carbs': 4.8},
    };

    // Tìm kiếm khớp từ khóa trong tên món ăn
    for (final entry in database.entries) {
      if (cleanName.contains(entry.key)) {
        return entry.value;
      }
    }

    // Giá trị mặc định (100g chứa 150 kcal, 5g protein, 3g chất béo, 25g tinh bột)
    return {'calories': 150.0, 'protein': 5.0, 'fat': 3.0, 'carbs': 25.0};
  }

  Map<String, dynamic> toJson() {
    return {
      'kind': kind,
      'wger_id': wgerId,
      'name': name,
      'details': details,
    };
  }
}

/// Model cho structured response từ chatbot
class StructuredResponse {
  final String type;
  final String text;
  final String? mealName; // tên món ăn khi gợi ý dinh dưỡng
  final List<ActionItem> actions;

  /// Canonical E4 payload kept separate from generic ActionItem calories.
  final Map<String, dynamic>? personalizedWorkout;

  /// Immutable P1 plan revision; it is rendered directly rather than asking
  /// the model to recreate a weekly table in Markdown.
  final Map<String, dynamic>? versionedPlan;

  StructuredResponse({
    required this.type,
    required this.text,
    this.mealName,
    required this.actions,
    this.personalizedWorkout,
    this.versionedPlan,
  });

  factory StructuredResponse.fromJson(Map<String, dynamic> json) {
    return StructuredResponse(
      type: json['type'] ?? 'structured',
      text: json['text'] ?? '',
      mealName: json['meal_name'] as String?,
      actions: ActionItem.parseActions(json['actions'] as List<dynamic>?),
      personalizedWorkout: json['type'] == 'personalized_workout'
          ? Map<String, dynamic>.from(json)
          : json['personalized_workout'] is Map
              ? Map<String, dynamic>.from(json['personalized_workout'] as Map)
              : null,
      versionedPlan: json['versioned_plan'] is Map
          ? Map<String, dynamic>.from(json['versioned_plan'] as Map)
          : json['type'] == 'versioned_plan'
              ? Map<String, dynamic>.from(json)
              : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'text': text,
      if (mealName != null) 'meal_name': mealName,
      'actions': actions.map((a) => a.toJson()).toList(),
      if (personalizedWorkout != null)
        'personalized_workout': personalizedWorkout,
      if (versionedPlan != null) 'versioned_plan': versionedPlan,
    };
  }

  /// Lấy tất cả food actions
  List<ActionItem> get foodActions =>
      actions.where((a) => a.kind == 'food').toList();

  /// Lấy tất cả exercise actions
  List<ActionItem> get exerciseActions =>
      actions.where((a) => a.kind == 'exercise').toList();

  /// Tổng calo ước tính của tất cả food actions
  double get totalFoodCalories => foodActions.fold(0, (sum, a) {
        final cal = a.details['calories'] as num? ?? 0;
        final grams = a.details['serving_grams'] as num? ?? 100;
        return sum + cal * grams / 100;
      });
}
