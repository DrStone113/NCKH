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
  final Set<String> observedFields;

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
    this.observedFields = const {},
  });

  bool get hasMoodObservation => observedFields.contains('mood');
  bool get hasSleepObservation => observedFields.contains('sleep');
  bool get hasStressObservation => observedFields.contains('stress');
  bool get hasLifestyleWaterObservation => observedFields.contains('water');
  bool get hasNotesObservation => observedFields.contains('notes');

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'userId': userId,
      'date': date.toIso8601String(),
      if (hasMoodObservation) 'moodScore': moodScore,
      if (hasMoodObservation) 'moodLabel': moodLabel,
      if (hasSleepObservation) 'sleepHours': sleepHours,
      if (hasStressObservation) 'stressScore': stressScore,
      if (hasLifestyleWaterObservation) 'waterIntakeMl': waterIntakeMl,
      if (hasNotesObservation) 'notes': notes,
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
      observedFields: {
        if (map.containsKey('moodScore') || map.containsKey('moodLabel')) 'mood',
        if (map.containsKey('sleepHours')) 'sleep',
        if (map.containsKey('stressScore')) 'stress',
        if (map.containsKey('waterIntakeMl')) 'water',
        if (map.containsKey('notes')) 'notes',
      },
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
    Set<String>? observedFields,
  }) {
    final fields = Set<String>.from(observedFields ?? this.observedFields);
    if (moodScore != null || moodLabel != null) fields.add('mood');
    if (sleepHours != null) fields.add('sleep');
    if (stressScore != null) fields.add('stress');
    if (waterIntakeMl != null) fields.add('water');
    if (notes != null) fields.add('notes');
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
      observedFields: fields,
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
