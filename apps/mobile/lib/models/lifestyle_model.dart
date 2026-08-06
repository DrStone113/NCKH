import 'package:flutter/foundation.dart';

/// Model cho nhật ký Sức khỏe Tinh thần & Lifestyle (Module 3)
@immutable
class LifestyleLog {
  final String id;
  final String userId;
  final DateTime date;
  final int moodScore; // 1 (Rất tệ) đến 5 (Rất tốt)
  final String moodLabel; // E.g., "Hào hứng", "Thư thái", "Bình thường", "Mệt mỏi", "Stress"
  final double sleepHours; // Số giờ ngủ
  final int stressScore; // 1 (Rất thấp) đến 5 (Cực kỳ cao)
  final double waterIntakeMl; // Lượng nước uống (ml)
  final String notes;

  const LifestyleLog({
    required this.id,
    required this.userId,
    required this.date,
    this.moodScore = 3,
    this.moodLabel = 'Bình thường',
    this.sleepHours = 7.0,
    this.stressScore = 2,
    this.waterIntakeMl = 0.0,
    this.notes = '',
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'date': date.toIso8601String(),
      'moodScore': moodScore,
      'moodLabel': moodLabel,
      'sleepHours': sleepHours,
      'stressScore': stressScore,
      'waterIntakeMl': waterIntakeMl,
      'notes': notes,
    };
  }

  factory LifestyleLog.fromMap(Map<String, dynamic> map) {
    return LifestyleLog(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      date: map['date'] != null ? DateTime.parse(map['date']) : DateTime.now(),
      moodScore: (map['moodScore'] as num? ?? 3).toInt(),
      moodLabel: map['moodLabel'] as String? ?? 'Bình thường',
      sleepHours: (map['sleepHours'] as num? ?? 7.0).toDouble(),
      stressScore: (map['stressScore'] as num? ?? 2).toInt(),
      waterIntakeMl: (map['waterIntakeMl'] as num? ?? 0.0).toDouble(),
      notes: map['notes'] as String? ?? '',
    );
  }

  LifestyleLog copyWith({
    String? id,
    String? userId,
    DateTime? date,
    int? moodScore,
    String? moodLabel,
    double? sleepHours,
    int? stressScore,
    double? waterIntakeMl,
    String? notes,
  }) {
    return LifestyleLog(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      date: date ?? this.date,
      moodScore: moodScore ?? this.moodScore,
      moodLabel: moodLabel ?? this.moodLabel,
      sleepHours: sleepHours ?? this.sleepHours,
      stressScore: stressScore ?? this.stressScore,
      waterIntakeMl: waterIntakeMl ?? this.waterIntakeMl,
      notes: notes ?? this.notes,
    );
  }
}

/// Model cho Nhắc nhở sinh hoạt / Lifestyle Reminders
@immutable
class LifestyleReminder {
  final String id;
  final String userId;
  final String title;
  final String type; // "water", "sleep", "exercise", "meditation", "mood_checkin"
  final String time; // "08:00"
  final bool isActive;
  final String note;

  const LifestyleReminder({
    required this.id,
    required this.userId,
    required this.title,
    required this.type,
    required this.time,
    this.isActive = true,
    this.note = '',
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'title': title,
      'type': type,
      'time': time,
      'isActive': isActive,
      'note': note,
    };
  }

  factory LifestyleReminder.fromMap(Map<String, dynamic> map) {
    return LifestyleReminder(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      title: map['title'] as String? ?? 'Nhắc nhở',
      type: map['type'] as String? ?? 'water',
      time: map['time'] as String? ?? '08:00',
      isActive: map['isActive'] as bool? ?? true,
      note: map['note'] as String? ?? '',
    );
  }
}
