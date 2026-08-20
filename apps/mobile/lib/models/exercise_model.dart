import 'package:flutter/material.dart';
import '../utils/exercise_utils.dart';

DateTime _parseExerciseDate(Object? value) {
  if (value is DateTime) return value;
  if (value is String) return DateTime.tryParse(value) ?? DateTime.now();
  try {
    final converted = (value as dynamic).toDate();
    if (converted is DateTime) return converted;
  } catch (_) {
    // Dữ liệu cũ hoặc hỏng sẽ dùng thời điểm hiện tại thay vì làm vỡ màn hình.
  }
  return DateTime.now();
}

int _parseExerciseInt(Object? value, [int fallback = 0]) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double _parseExerciseDouble(Object? value, [double fallback = 0]) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? fallback;
}

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

  int get wgerId => ExerciseUtils.parseWgerId(id);

  // Tính calo tiêu thụ: MET * weight(kg) * time(hours)
  double calculateCalories(double weightKg, int durationMinutes) {
    return ExerciseUtils.calculateCalories(
      met: metValue,
      weightKg: weightKg,
      durationMinutes: durationMinutes,
    );
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
      metValue: _parseExerciseDouble(map['metValue']),
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
  final String timeOfDay; // morning, afternoon, evening, night

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
    this.timeOfDay = 'morning',
  });

  int get wgerId => ExerciseUtils.parseWgerId(exerciseTemplateId);

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
      'timeOfDay': timeOfDay,
    };
  }

  factory ExerciseModel.fromMap(Map<String, dynamic> map) {
    return ExerciseModel(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      name: map['name'] ?? '',
      exerciseTemplateId: map['exerciseTemplateId'],
      date: _parseExerciseDate(map['date']),
      duration: _parseExerciseInt(map['duration'])
          .clamp(0, ExerciseUtils.maxDurationMinutes),
      caloriesBurned: _parseExerciseDouble(map['caloriesBurned'])
          .clamp(0, double.maxFinite),
      type: map['type'] ?? 'cardio',
      intensity: map['intensity'] ?? 'medium',
      isCompleted: map['isCompleted'] ?? false,
      timeOfDay: map['timeOfDay'] ?? 'morning',
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
    String? timeOfDay,
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
      timeOfDay: timeOfDay ?? this.timeOfDay,
    );
  }

  String get typeText {
    switch (type) {
      case 'cardio':
        return 'Cardio';
      case 'strength':
        return 'Sức mạnh';
      case 'flexibility':
        return 'Linh hoạt';
      case 'sports':
        return 'Thể thao';
      default:
        return 'Khác';
    }
  }

  String get intensityText {
    switch (intensity) {
      case 'low':
        return 'Nhẹ';
      case 'medium':
        return 'Vừa';
      case 'high':
        return 'Cao';
      default:
        return 'Vừa';
    }
  }

  String get timeOfDayText {
    switch (timeOfDay) {
      case 'morning':
        return 'Buổi sáng';
      case 'afternoon':
        return 'Buổi chiều';
      case 'evening':
        return 'Buổi tối';
      case 'night':
        return 'Ban đêm';
      default:
        return 'Buổi sáng';
    }
  }

  IconData get timeOfDayIcon {
    switch (timeOfDay) {
      case 'morning':
        return Icons.wb_sunny_outlined;
      case 'afternoon':
        return Icons.wb_cloudy_outlined;
      case 'evening':
        return Icons.nights_stay_outlined;
      case 'night':
        return Icons.bedtime_outlined;
      default:
        return Icons.wb_sunny_outlined;
    }
  }
}
