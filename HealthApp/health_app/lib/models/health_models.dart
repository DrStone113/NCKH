/// Model cho bảng chi_so_co_the - Lịch sử chỉ số cơ thể
class BodyMetrics {
  final String id;
  final String userId;
  final double weight;
  final double bmi;
  final DateTime recordedAt;

  BodyMetrics({
    required this.id,
    required this.userId,
    required this.weight,
    required this.bmi,
    required this.recordedAt,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'userId': userId,
      'weight': weight,
      'bmi': bmi,
      'recordedAt': recordedAt.toIso8601String(),
    };
  }

  factory BodyMetrics.fromMap(Map<String, dynamic> map) {
    return BodyMetrics(
      id: map['id'] ?? '',
      userId: map['userId'] ?? '',
      weight: (map['weight'] ?? 0).toDouble(),
      bmi: (map['bmi'] ?? 0).toDouble(),
      recordedAt: DateTime.parse(map['recordedAt']),
    );
  }
}

/// Model cho chatbot - Triệu chứng
class Symptom {
  final String id;
  final String name;
  final String description;

  Symptom({required this.id, required this.name, required this.description});
}

/// Model cho chatbot - Thiếu hụt vi chất
class NutrientDeficiency {
  final String id;
  final String nutrientName; // Sắt, Vitamin B12, etc.
  final String advice;
  final List<String> symptomIds;
  final List<String> foodSuggestions;
  final String absorptionTip; // meo_hap_thu

  NutrientDeficiency({
    required this.id,
    required this.nutrientName,
    required this.advice,
    required this.symptomIds,
    required this.foodSuggestions,
    this.absorptionTip = '',
  });
}

/// Chat message model
class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;
  final List<String>? quickReplies;

  ChatMessage({
    required this.text,
    required this.isUser,
    DateTime? timestamp,
    this.quickReplies,
  }) : timestamp = timestamp ?? DateTime.now();
}
