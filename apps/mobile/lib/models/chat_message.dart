import 'wger_models.dart';

class PublicTraceStep {
  final String publicEventType;
  final String title;
  final String summary;
  final int order;
  final DateTime? timestamp;

  const PublicTraceStep({
    required this.publicEventType,
    required this.title,
    required this.summary,
    required this.order,
    this.timestamp,
  });
}

/// Allowlist-only representation for normal users. Server text is discarded
/// deliberately so a compromised payload cannot become a reasoning surface.
class PublicReasoningTrace {
  static const Set<String> _allowedEventTypes = {
    'PROFILE_CONTEXT_USED',
    'TODAY_NUTRITION_CHECKED',
    'DIETARY_CONSTRAINTS_CHECKED',
    'TRAINING_HISTORY_CHECKED',
    'FOOD_CATALOG_SEARCHED',
    'WORKOUT_CATALOG_SEARCHED',
    'RECOMMENDATION_SELECTED',
    'RECOMMENDATION_NUTRITION_FIT',
    'RECOMMENDATION_PREFERENCE_FIT',
    'RECOMMENDATION_DIVERSITY_APPLIED',
    'RECOMMENDATION_PORTION_ADAPTED',
    'RECOMMENDATION_STAGING_SOURCE',
    'CALCULATION_COMPLETED',
    'CONFIRMATION_RECEIVED',
    'PERSISTENCE_IN_PROGRESS',
    'PERSISTENCE_CONFIRMED',
    'CLARIFICATION_REQUIRED',
    'SAFETY_CHECK_APPLIED',
    'ACTIVE_PLAN_READ',
    'PLAN_VALIDATED',
    'PLAN_REVISION_CREATED',
    'WEEKLY_SCHEDULE_CHECKED',
    'WEEKLY_SESSIONS_SCHEDULED',
    'PLAN_VERSION_CONFIRMED',
  };

  static const Map<String, List<String>> _safeCopy = {
    'PROFILE_CONTEXT_USED': [
      'Đã kiểm tra thông tin liên quan',
      'Mình dùng các thông tin hồ sơ đã xác nhận để trả lời phù hợp hơn.'
    ],
    'TODAY_NUTRITION_CHECKED': [
      'Đã đối chiếu nhật ký hôm nay',
      'Mình kiểm tra dữ liệu đã ghi để tránh gợi ý trùng lặp.'
    ],
    'DIETARY_CONSTRAINTS_CHECKED': [
      'Đã kiểm tra giới hạn ăn uống',
      'Các hạn chế đã xác nhận được đưa vào khi chọn gợi ý.'
    ],
    'TRAINING_HISTORY_CHECKED': [
      'Đã kiểm tra lịch sử tập luyện',
      'Mình đối chiếu mức độ và lịch tập đã có trước khi đề xuất.'
    ],
    'FOOD_CATALOG_SEARCHED': [
      'Đã tìm trong danh mục món ăn',
      'Mình chỉ dùng các lựa chọn có trong dữ liệu ứng dụng.'
    ],
    'WORKOUT_CATALOG_SEARCHED': [
      'Đã tìm trong thư viện bài tập',
      'Mình chỉ dùng các bài tập có trong dữ liệu ứng dụng.'
    ],
    'RECOMMENDATION_SELECTED': [
      'Đã chọn gợi ý phù hợp',
      'Gợi ý được chọn dựa trên các dữ liệu đã kiểm tra ở trên.'
    ],
    'RECOMMENDATION_NUTRITION_FIT': [
      'Phù hợp mục tiêu dinh dưỡng còn lại',
      'Gợi ý này được đối chiếu với phần dinh dưỡng còn lại trong ngày.'
    ],
    'RECOMMENDATION_PREFERENCE_FIT': [
      'Phù hợp khẩu vị đã xác nhận',
      'Mình dùng phản hồi hoặc sở thích bạn đã xác nhận, sau các kiểm tra an toàn.'
    ],
    'RECOMMENDATION_DIVERSITY_APPLIED': [
      'Đã cân nhắc sự đa dạng',
      'Mình tránh lặp lại món hoặc nguồn đạm vừa xuất hiện khi có lựa chọn phù hợp.'
    ],
    'RECOMMENDATION_PORTION_ADAPTED': [
      'Có thể điều chỉnh khẩu phần',
      'Khẩu phần được tính lại từ nguyên liệu chuẩn trong giới hạn công thức phù hợp.'
    ],
    'RECOMMENDATION_STAGING_SOURCE': [
      'Nguồn công thức đang được đánh giá',
      'Công thức này là dữ liệu thử nghiệm; dinh dưỡng vẫn được tính từ dữ liệu chuẩn.'
    ],
    'CALCULATION_COMPLETED': [
      'Đã hoàn tất tính toán',
      'Kết quả được tính từ các thông tin đã xác nhận.'
    ],
    'CONFIRMATION_RECEIVED': [
      'Đã nhận xác nhận của bạn',
      'Mình tiếp tục với đúng lựa chọn bạn vừa xác nhận.'
    ],
    'PERSISTENCE_IN_PROGRESS': [
      'Đang lưu thay đổi',
      'Mình đang ghi nhận thông tin vào hồ sơ hoặc nhật ký của bạn.'
    ],
    'PERSISTENCE_CONFIRMED': [
      'Đã lưu thay đổi',
      'Thông tin đã được hệ thống xác nhận là đã lưu.'
    ],
    'CLARIFICATION_REQUIRED': [
      'Cần làm rõ thêm',
      'Mình cần thêm một thông tin để đưa ra gợi ý an toàn và phù hợp.'
    ],
    'SAFETY_CHECK_APPLIED': [
      'Đã áp dụng kiểm tra an toàn',
      'Mình đã cân nhắc các giới hạn sức khỏe đã được xác nhận.'
    ],
    'ACTIVE_PLAN_READ': [
      'Đã đọc kế hoạch hiện tại',
      'Mình dùng đúng phiên bản đang áp dụng.'
    ],
    'PLAN_VALIDATED': [
      'Đã kiểm tra toàn bộ kế hoạch',
      'Các giới hạn và tham chiếu có cấu trúc đã được kiểm tra.'
    ],
    'PLAN_REVISION_CREATED': [
      'Đã tạo bản chỉnh sửa',
      'Thay đổi được tạo thành một phiên bản mới để giữ lại lịch sử.'
    ],
    'WEEKLY_SCHEDULE_CHECKED': [
      'Đã kiểm tra lịch tuần',
      'Ngày rảnh và thời lượng được kiểm tra trước khi lên lịch.'
    ],
    'WEEKLY_SESSIONS_SCHEDULED': [
      'Đã lập lịch các buổi tập',
      'Lịch dự kiến chưa phải lịch sử đã tập.'
    ],
    'PLAN_VERSION_CONFIRMED': [
      'Đã xác nhận phiên bản kế hoạch',
      'Phiên bản hiển thị được giữ nguyên khi lưu hoặc kích hoạt.'
    ],
  };

  final String traceId;
  final String status;
  final List<PublicTraceStep> steps;

  const PublicReasoningTrace({
    required this.traceId,
    required this.status,
    required this.steps,
  });

  bool get hasSteps => steps.isNotEmpty;

  factory PublicReasoningTrace.fromJson(Map<String, dynamic> json) {
    final steps = <PublicTraceStep>[];
    final rawSteps = json['steps'];
    if (rawSteps is List) {
      for (final rawStep in rawSteps) {
        if (rawStep is! Map) continue;
        final type = rawStep['public_event_type']?.toString() ?? '';
        if (!_allowedEventTypes.contains(type)) continue;
        final copy = _safeCopy[type];
        if (copy == null) continue;
        steps.add(PublicTraceStep(
          publicEventType: type,
          title: copy[0],
          summary: copy[1],
          order: (rawStep['order'] as num?)?.toInt() ?? steps.length + 1,
          timestamp: DateTime.tryParse(rawStep['timestamp']?.toString() ?? ''),
        ));
      }
    }
    steps.sort((a, b) => a.order.compareTo(b.order));
    return PublicReasoningTrace(
      traceId: json['trace_id']?.toString() ?? '',
      status: json['status']?.toString() ?? 'IN_PROGRESS',
      steps: List.unmodifiable(steps.take(6)),
    );
  }
}

class DeveloperTraceEvent {
  final String timestamp;
  final String category;
  final String component;
  final String operation;
  final Map<String, dynamic> sanitizedPayload;
  final String? correlationId;
  final num? latencyMs;
  final String? result;

  const DeveloperTraceEvent({
    required this.timestamp,
    required this.category,
    required this.component,
    required this.operation,
    required this.sanitizedPayload,
    this.correlationId,
    this.latencyMs,
    this.result,
  });

  factory DeveloperTraceEvent.fromJson(Map<String, dynamic> json) {
    final rawPayload = json['sanitized_payload'];
    return DeveloperTraceEvent(
      timestamp: json['timestamp']?.toString() ?? '',
      category: json['category']?.toString() ?? 'unknown',
      component: json['component']?.toString() ?? 'unknown',
      operation: json['operation']?.toString() ?? 'unknown',
      sanitizedPayload: rawPayload is Map
          ? Map<String, dynamic>.from(rawPayload)
          : const <String, dynamic>{},
      correlationId: json['correlation_id']?.toString(),
      latencyMs: json['latency_ms'] as num?,
      result: json['result']?.toString(),
    );
  }
}

/// Trạng thái của bot message
enum MessageStatus {
  thinking, // Đang xử lý — chỉ hiện PublicReasoningTrace an toàn
  streaming, // Đang nhận token câu trả lời
  done, // Hoàn tất — hiện kết quả
  error, // Lỗi
}

/// Model cho AI Chat
class AIChatMessage {
  final String id;
  final String text;
  final bool isUser;
  final bool isStreaming;
  final MessageStatus status;
  final DateTime timestamp;
  final StructuredResponse? structuredResponse;
  final List<String> suggestions;
  final bool isFlowQuestion;
  final PublicReasoningTrace? publicTrace;
  final List<DeveloperTraceEvent> developerTrace;

  AIChatMessage({
    required this.id,
    required this.text,
    required this.isUser,
    this.isStreaming = false,
    MessageStatus? status,
    DateTime? timestamp,
    this.structuredResponse,
    this.suggestions = const [],
    this.isFlowQuestion = false,
    this.publicTrace,
    this.developerTrace = const [],
  })  : status = status ??
            (isStreaming ? MessageStatus.thinking : MessageStatus.done),
        timestamp = timestamp ?? DateTime.now();

  bool get isThinking => !isUser && status == MessageStatus.thinking;

  AIChatMessage copyWith({
    String? id,
    String? text,
    bool? isUser,
    bool? isStreaming,
    MessageStatus? status,
    DateTime? timestamp,
    StructuredResponse? structuredResponse,
    List<String>? suggestions,
    bool? isFlowQuestion,
    PublicReasoningTrace? publicTrace,
    List<DeveloperTraceEvent>? developerTrace,
  }) {
    return AIChatMessage(
      id: id ?? this.id,
      text: text ?? this.text,
      isUser: isUser ?? this.isUser,
      isStreaming: isStreaming ?? this.isStreaming,
      status: status ?? this.status,
      timestamp: timestamp ?? this.timestamp,
      structuredResponse: structuredResponse ?? this.structuredResponse,
      suggestions: suggestions ?? this.suggestions,
      isFlowQuestion: isFlowQuestion ?? this.isFlowQuestion,
      publicTrace: publicTrace ?? this.publicTrace,
      developerTrace: developerTrace ?? this.developerTrace,
    );
  }
}
