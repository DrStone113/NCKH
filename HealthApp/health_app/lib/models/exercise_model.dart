/// Model cho bảng bai_tap - Bài tập (template)
class ExerciseTemplate {
  final String id;
  final String name;
  final double metValue; // chi_so_met
  final String description;
  final String type; // cardio, strength, flexibility, sports

  ExerciseTemplate({
    required this.id,
    required this.name,
    required this.metValue,
    this.description = '',
    required this.type,
  });

  // Tính calo tiêu thụ: MET * weight(kg) * time(hours)
  double calculateCalories(double weightKg, int durationMinutes) {
    return metValue * weightKg * (durationMinutes / 60.0);
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'name': name,
      'metValue': metValue,
      'description': description,
      'type': type,
    };
  }

  factory ExerciseTemplate.fromMap(Map<String, dynamic> map) {
    return ExerciseTemplate(
      id: map['id'] ?? '',
      name: map['name'] ?? '',
      metValue: (map['metValue'] ?? 0).toDouble(),
      description: map['description'] ?? '',
      type: map['type'] ?? 'cardio',
    );
  }
}

/// Model cho bảng nhat_ky_tap_luyen - Nhật ký tập luyện
class ExerciseModel {
  final String id;
  final String userId;
  final String name;
  final String? exerciseTemplateId; // bai_tap_id
  final DateTime date;
  final int duration; // phút
  final double caloriesBurned;
  final String type; // cardio, strength, flexibility, sports
  final String intensity; // low, medium, high
  final bool isCompleted; // Đã hoàn thành chưa

  ExerciseModel({
    required this.id,
    required this.userId,
    required this.name,
    this.exerciseTemplateId,
    required this.date,
    required this.duration,
    required this.caloriesBurned,
    required this.type,
    this.intensity = 'medium',
    this.isCompleted = false,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'name': name,
      'exerciseTemplateId': exerciseTemplateId,
      'date': date.toIso8601String(),
      'duration': duration,
      'caloriesBurned': caloriesBurned,
      'type': type,
      'intensity': intensity,
      'isCompleted': isCompleted,
    };
  }

  factory ExerciseModel.fromMap(Map<String, dynamic> map) {
    return ExerciseModel(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      name: map['name'] ?? '',
      exerciseTemplateId: map['exerciseTemplateId'],
      date: DateTime.parse(map['date']),
      duration: map['duration'] ?? 0,
      caloriesBurned: (map['caloriesBurned'] ?? 0).toDouble(),
      type: map['type'] ?? 'cardio',
      intensity: map['intensity'] ?? 'medium',
      isCompleted: map['isCompleted'] ?? false,
    );
  }

  ExerciseModel copyWith({
    String? id,
    String? userId,
    String? name,
    String? exerciseTemplateId,
    DateTime? date,
    int? duration,
    double? caloriesBurned,
    String? type,
    String? intensity,
    bool? isCompleted,
  }) {
    return ExerciseModel(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      name: name ?? this.name,
      exerciseTemplateId: exerciseTemplateId ?? this.exerciseTemplateId,
      date: date ?? this.date,
      duration: duration ?? this.duration,
      caloriesBurned: caloriesBurned ?? this.caloriesBurned,
      type: type ?? this.type,
      intensity: intensity ?? this.intensity,
      isCompleted: isCompleted ?? this.isCompleted,
    );
  }

  String get typeText {
    switch (type) {
      case 'cardio': return 'Cardio';
      case 'strength': return 'Sức mạnh';
      case 'flexibility': return 'Linh hoạt';
      case 'sports': return 'Thể thao';
      default: return 'Khác';
    }
  }

  String get intensityText {
    switch (intensity) {
      case 'low': return 'Nhẹ';
      case 'medium': return 'Vừa';
      case 'high': return 'Cao';
      default: return 'Vừa';
    }
  }
}
