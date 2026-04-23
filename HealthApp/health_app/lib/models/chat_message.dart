import 'wger_models.dart';

/// Trạng thái của bot message
enum MessageStatus {
  thinking,   // Đang xử lý — hiện animated indicator, ẩn text
  streaming,  // Đang nhận token — vẫn ẩn text, giữ indicator
  done,       // Hoàn tất — hiện kết quả
  error,      // Lỗi
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
  })  : status = status ?? (isStreaming ? MessageStatus.thinking : MessageStatus.done),
        timestamp = timestamp ?? DateTime.now();

  bool get isThinking =>
      !isUser && (status == MessageStatus.thinking || status == MessageStatus.streaming);

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
    );
  }
}
