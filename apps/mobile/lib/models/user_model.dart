import 'canonical_nutrition.dart';

class UserModel {
  final String id;
  final String email;
  final String name;
  final int age;
  final String? gender; // General identity field; not an equation input.
  final String?
      equationSex; // Explicit Mifflin input: male, female, or missing.
  final NutritionSafetyProfile nutritionSafetyProfile;
  final double height; // cm
  final double weight; // kg
  final double? targetWeight; // kg - can_nang_muc_tieu
  final String activityLevel; // sedentary, light, moderate, active, very_active
  final String healthGoal; // lose_weight, maintain, gain_muscle
  final DateTime? createdAt;

  UserModel({
    required this.id,
    required this.email,
    required this.name,
    required this.age,
    this.gender,
    this.equationSex,
    this.nutritionSafetyProfile = const NutritionSafetyProfile(),
    required this.height,
    required this.weight,
    this.targetWeight,
    required this.activityLevel,
    this.healthGoal = 'maintain',
    this.createdAt,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'email': email,
      'name': name,
      'age': age,
      'gender': gender,
      'equation_sex': equationSex,
      'nutrition_safety_profile': nutritionSafetyProfile.toJson(),
      'height': height,
      'weight': weight,
      'targetWeight': targetWeight,
      'activityLevel': activityLevel,
      'healthGoal': healthGoal,
      'createdAt': (createdAt ?? DateTime.now()).toIso8601String(),
    };
  }

  factory UserModel.fromMap(Map<String, dynamic> map) {
    return UserModel(
      id: map['id'] ?? '',
      email: map['email'] ?? '',
      name: map['name'] ?? '',
      age: map['age'] ?? 0,
      gender: map['gender']?.toString(),
      equationSex: const {'male', 'female'}.contains(map['equation_sex'])
          ? map['equation_sex'].toString()
          : null,
      nutritionSafetyProfile:
          NutritionSafetyProfile.fromJson(map['nutrition_safety_profile']),
      height: (map['height'] ?? 0).toDouble(),
      weight: (map['weight'] ?? 0).toDouble(),
      targetWeight: map['targetWeight']?.toDouble(),
      activityLevel: map['activityLevel'] ?? 'sedentary',
      healthGoal: map['healthGoal'] ?? 'maintain',
      createdAt:
          map['createdAt'] != null ? DateTime.tryParse(map['createdAt']) : null,
    );
  }

  static const _notSet = Object();

  UserModel copyWith({
    String? id,
    String? email,
    String? name,
    int? age,
    Object? gender = _notSet,
    Object? equationSex = _notSet,
    NutritionSafetyProfile? nutritionSafetyProfile,
    double? height,
    double? weight,
    double? targetWeight,
    String? activityLevel,
    String? healthGoal,
  }) {
    return UserModel(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
      age: age ?? this.age,
      gender: identical(gender, _notSet) ? this.gender : gender as String?,
      equationSex: identical(equationSex, _notSet)
          ? this.equationSex
          : equationSex as String?,
      nutritionSafetyProfile:
          nutritionSafetyProfile ?? this.nutritionSafetyProfile,
      height: height ?? this.height,
      weight: weight ?? this.weight,
      targetWeight: targetWeight ?? this.targetWeight,
      activityLevel: activityLevel ?? this.activityLevel,
      healthGoal: healthGoal ?? this.healthGoal,
      createdAt: createdAt,
    );
  }

  // === CHỈ SỐ CƠ THỂ ===

  CanonicalNutritionState canonicalForGoal(String goal) =>
      calculateCanonicalNutrition(CanonicalNutritionInput(
        age: CanonicalNutritionValue.known(age, source: 'user_profile.age'),
        equationSex: equationSex == null
            ? const CanonicalNutritionValue<String>(
                value: null,
                source: 'user_profile.equation_sex',
                status: NutritionInputStatus.missing,
              )
            : CanonicalNutritionValue.known(equationSex,
                source: 'user_profile.equation_sex'),
        heightCm: CanonicalNutritionValue.known(height,
            source: 'user_profile.height'),
        weightKg: CanonicalNutritionValue.known(weight,
            source: 'user_profile.weight'),
        activityLevel: CanonicalNutritionValue.known(activityLevel,
            source: 'user_profile.activity_level'),
        healthGoal: CanonicalNutritionValue.known(goal,
            source: 'user_profile.health_goal'),
        safetyProfile: nutritionSafetyProfile,
      ));

  CanonicalNutritionState get canonicalNutrition =>
      canonicalForGoal(healthGoal);

  // Compatibility getters delegate to the canonical policy-v1 state.
  double get bmi => canonicalNutrition.bmi ?? double.nan;
  double get displayBmi => canonicalNutrition.displayBmi ?? double.nan;

  String get bmiCategory {
    return canonicalNutrition.bmiClassification ?? 'Không khả dụng';
  }

  String? get bmiCategoryCode => canonicalNutrition.bmiClassificationCode;

  String get bmiAdvice {
    final category = canonicalNutrition.bmiClassification;
    if (category == null) return 'Chưa đủ dữ liệu để hiển thị BMI.';
    return 'Phân loại BMI: $category. Đây là thông tin sàng lọc, không phải chẩn đoán.';
  }

  double? get bmr => canonicalNutrition.estimatedRmrKcalPerDay;
  double? get displayRmr => canonicalNutrition.displayEstimatedRmrKcalPerDay;

  // TDEE
  double? get tdee => canonicalNutrition.estimatedTdeeKcalPerDay;
  double? get displayTdee => canonicalNutrition.displayEstimatedTdeeKcalPerDay;

  // Recommended daily calories based on goal
  double? get recommendedCalories => canonicalNutrition.calorieTargetKcalPerDay;
  double? get displayRecommendedCalories =>
      canonicalNutrition.displayCalorieTargetKcalPerDay;

  // Body fat estimation (US Navy method approximation)
  double? get estimatedBodyFat {
    if (gender == 'male') {
      return 1.20 * bmi + 0.23 * age - 16.2;
    }
    if (gender == 'female') {
      return 1.20 * bmi + 0.23 * age - 5.4;
    }
    return null;
  }

  // Daily water goal in liters
  double? get dailyWaterGoal =>
      canonicalNutrition.approximateFluidGoalMlPerDay == null
          ? null
          : canonicalNutrition.approximateFluidGoalMlPerDay! / 1000.0;
  double? get displayDailyWaterGoal =>
      canonicalNutrition.displayApproximateFluidGoalMlPerDay == null
          ? null
          : canonicalNutrition.displayApproximateFluidGoalMlPerDay! / 1000.0;

  // Activity level in Vietnamese
  String get activityLevelText {
    switch (activityLevel) {
      case 'sedentary':
        return 'Ít vận động';
      case 'light':
        return 'Vận động nhẹ';
      case 'moderate':
        return 'Vận động vừa';
      case 'active':
        return 'Vận động nhiều';
      case 'very_active':
        return 'Vận động rất nhiều';
      default:
        return 'Không rõ';
    }
  }

  String get healthGoalText {
    switch (healthGoal) {
      case 'lose_weight':
        return 'Giảm cân';
      case 'gain_muscle':
        return 'Tăng cơ';
      default:
        return 'Duy trì';
    }
  }
}
