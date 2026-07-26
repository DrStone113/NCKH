class UserModel {
  final String id;
  final String email;
  final String name;
  final int age;
  final String gender; // 'male' or 'female'
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
    required this.gender,
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
      gender: map['gender'] ?? 'male',
      height: (map['height'] ?? 0).toDouble(),
      weight: (map['weight'] ?? 0).toDouble(),
      targetWeight: map['targetWeight']?.toDouble(),
      activityLevel: map['activityLevel'] ?? 'sedentary',
      healthGoal: map['healthGoal'] ?? 'maintain',
      createdAt: map['createdAt'] != null ? DateTime.tryParse(map['createdAt']) : null,
    );
  }

  UserModel copyWith({
    String? id, String? email, String? name, int? age,
    String? gender, double? height, double? weight,
    double? targetWeight, String? activityLevel, String? healthGoal,
  }) {
    return UserModel(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
      age: age ?? this.age,
      gender: gender ?? this.gender,
      height: height ?? this.height,
      weight: weight ?? this.weight,
      targetWeight: targetWeight ?? this.targetWeight,
      activityLevel: activityLevel ?? this.activityLevel,
      healthGoal: healthGoal ?? this.healthGoal,
      createdAt: createdAt,
    );
  }

  // === CHỈ SỐ CƠ THỂ ===

  // BMI
  double get bmi => weight / ((height / 100) * (height / 100));

  String get bmiCategory {
    // Tiêu chuẩn BMI cho người Việt Nam (người châu Á)
    if (bmi < 16) return 'Gầy độ III';
    if (bmi < 17) return 'Gầy độ II';
    if (bmi < 18.5) return 'Gầy độ I';
    if (bmi < 25) return 'Bình thường';
    if (bmi < 30) return 'Thừa cân';
    if (bmi < 35) return 'Béo phì độ I';
    if (bmi < 40) return 'Béo phì độ II';
    return 'Béo phì độ III';
  }

  String get bmiAdvice {
    if (bmi < 16) return 'Bạn bị gầy nghiêm trọng. Cần gặp bác sĩ để được tư vấn dinh dưỡng ngay.';
    if (bmi < 17) return 'Bạn bị gầy mức độ II. Nên bổ sung dinh dưỡng và tham khảo ý kiến bác sĩ.';
    if (bmi < 18.5) return 'Bạn hơi gầy. Nên tăng cân bằng cách bổ sung dinh dưỡng đầy đủ.';
    if (bmi < 25) return 'Chỉ số BMI bình thường. Hãy duy trì lối sống lành mạnh!';
    if (bmi < 30) return 'Bạn thừa cân. Nên tăng vận động và kiểm soát khẩu phần ăn.';
    if (bmi < 35) return 'Bạn béo phì độ I. Nên tham khảo ý kiến bác sĩ để có kế hoạch giảm cân.';
    if (bmi < 40) return 'Bạn béo phì độ II. Cần gặp bác sĩ để được tư vấn giảm cân an toàn.';
    return 'Bạn béo phì độ III. Cần gặp bác sĩ chuyên khoa ngay để được điều trị.';
  }

  // BMR - Mifflin-St Jeor
  double get bmr {
    if (gender == 'male') {
      return 10 * weight + 6.25 * height - 5 * age + 5;
    } else {
      return 10 * weight + 6.25 * height - 5 * age - 161;
    }
  }

  // TDEE
  double get tdee {
    double multiplier;
    switch (activityLevel) {
      case 'sedentary':
        multiplier = 1.2;
        break;
      case 'light':
        multiplier = 1.375;
        break;
      case 'moderate':
        multiplier = 1.55;
        break;
      case 'active':
        multiplier = 1.725;
        break;
      case 'very_active':
        multiplier = 1.9;
        break;
      default:
        multiplier = 1.2;
    }
    return bmr * multiplier;
  }

  // Recommended daily calories based on goal
  double get recommendedCalories {
    switch (healthGoal) {
      case 'lose_weight':
        return tdee - 500;
      case 'gain_muscle':
        return tdee + 300;
      default:
        return tdee;
    }
  }

  // Body fat estimation (US Navy method approximation)
  double get estimatedBodyFat {
    if (gender == 'male') {
      return 1.20 * bmi + 0.23 * age - 16.2;
    } else {
      return 1.20 * bmi + 0.23 * age - 5.4;
    }
  }

  // Daily water goal in liters
  double get dailyWaterGoal => weight * 0.033;

  // Activity level in Vietnamese
  String get activityLevelText {
    switch (activityLevel) {
      case 'sedentary': return 'Ít vận động';
      case 'light': return 'Vận động nhẹ';
      case 'moderate': return 'Vận động vừa';
      case 'active': return 'Vận động nhiều';
      case 'very_active': return 'Vận động rất nhiều';
      default: return 'Không rõ';
    }
  }

  String get healthGoalText {
    switch (healthGoal) {
      case 'lose_weight': return 'Giảm cân';
      case 'gain_muscle': return 'Tăng cơ';
      default: return 'Duy trì';
    }
  }
}
