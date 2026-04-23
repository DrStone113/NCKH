/// Models cho wger API Integration

/// Model cho nhóm cơ từ wger API
class WgerMuscle {
  final int id;
  final String nameEn;
  final bool isFront;

  WgerMuscle({
    required this.id,
    required this.nameEn,
    required this.isFront,
  });

  factory WgerMuscle.fromJson(Map<String, dynamic> json) {
    return WgerMuscle(
      id: json['id'] ?? 0,
      nameEn: json['name_en'] ?? json['name'] ?? '',
      isFront: json['is_front'] ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name_en': nameEn,
      'is_front': isFront,
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
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
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
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
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

  factory WgerExercise.fromJson(Map<String, dynamic> json) {
    // Extract name
    String name = json['name']?.toString().trim() ?? '';
    
    // Extract description
    String description = json['description']?.toString() ?? '';
    
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
    } else if (json['images'] != null && json['images'] is List && (json['images'] as List).isNotEmpty) {
      final firstImage = (json['images'] as List).first;
      if (firstImage is Map && firstImage['image'] != null) {
        imageUrl = firstImage['image'].toString();
      }
    }
    
    return WgerExercise(
      id: json['id'] ?? 0,
      name: name,
      description: description,
      categoryName: categoryName,
      muscles: (json['muscles'] as List<dynamic>?)
              ?.map((m) {
                try {
                  return WgerMuscle.fromJson(m as Map<String, dynamic>);
                } catch (e) {
                  return null;
                }
              })
              .whereType<WgerMuscle>()
              .toList() ??
          [],
      musclesSecondary: (json['muscles_secondary'] as List<dynamic>?)
              ?.map((m) {
                try {
                  return WgerMuscle.fromJson(m as Map<String, dynamic>);
                } catch (e) {
                  return null;
                }
              })
              .whereType<WgerMuscle>()
              .toList() ??
          [],
      equipment: (json['equipment'] as List<dynamic>?)
              ?.map((e) {
                try {
                  return WgerEquipment.fromJson(e as Map<String, dynamic>);
                } catch (e) {
                  return null;
                }
              })
              .whereType<WgerEquipment>()
              .toList() ??
          [],
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
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      energy: json['energy'] != null ? (json['energy'] as num).toDouble() : null,
      protein: json['protein'] != null ? (json['protein'] as num).toDouble() : null,
      carbohydrates: json['carbohydrates'] != null
          ? (json['carbohydrates'] as num).toDouble()
          : null,
      fat: json['fat'] != null ? (json['fat'] as num).toDouble() : null,
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
    return (energy ?? 0) * grams / 100;
  }

  // Tính protein cho lượng gram cụ thể
  double proteinForGrams(double grams) {
    return (protein ?? 0) * grams / 100;
  }

  // Tính carbs cho lượng gram cụ thể
  double carbsForGrams(double grams) {
    return (carbohydrates ?? 0) * grams / 100;
  }

  // Tính fat cho lượng gram cụ thể
  double fatForGrams(double grams) {
    return (fat ?? 0) * grams / 100;
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
    final results = (json['results'] as List<dynamic>?)
            ?.map((e) => WgerExercise.fromJson(e as Map<String, dynamic>))
            .where((e) => e.name.isNotEmpty) // lọc bài tập không có tên
            .toList() ??
        [];
    return WgerExerciseListResponse(
      count: json['count'] ?? 0,
      next: json['next'] as String?,
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
      count: json['count'] ?? 0,
      next: json['next'],
      results: (json['results'] as List<dynamic>?)
              ?.map((i) => WgerIngredient.fromJson(i as Map<String, dynamic>))
              .toList() ??
          [],
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
    return ActionItem(
      kind: json['kind'] ?? '',
      wgerId: json['wger_id'] ?? 0,
      name: json['name'] ?? '',
      details: Map<String, dynamic>.from(json['details'] ?? {}),
    );
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

  StructuredResponse({
    required this.type,
    required this.text,
    this.mealName,
    required this.actions,
  });

  factory StructuredResponse.fromJson(Map<String, dynamic> json) {
    return StructuredResponse(
      type: json['type'] ?? 'structured',
      text: json['text'] ?? '',
      mealName: json['meal_name'] as String?,
      actions: (json['actions'] as List<dynamic>?)
              ?.map((a) => ActionItem.fromJson(a as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'text': text,
      if (mealName != null) 'meal_name': mealName,
      'actions': actions.map((a) => a.toJson()).toList(),
    };
  }

  /// Lấy tất cả food actions
  List<ActionItem> get foodActions => actions.where((a) => a.kind == 'food').toList();

  /// Lấy tất cả exercise actions
  List<ActionItem> get exerciseActions => actions.where((a) => a.kind == 'exercise').toList();

  /// Tổng calo ước tính của tất cả food actions
  double get totalFoodCalories => foodActions.fold(0, (sum, a) {
    final cal = a.details['calories'] as num? ?? 0;
    final grams = a.details['serving_grams'] as num? ?? 100;
    return sum + cal * grams / 100;
  });
}
