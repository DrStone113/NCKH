import 'wger_models.dart';

/// Trạng thái của bot message
enum MessageStatus {
  thinking, // Đang xử lý — chỉ hiện reasoning khi có thought thật
  streaming, // Đang nhận token câu trả lời
  done, // Hoàn tất — hiện kết quả
  error, // Lỗi
}

/// Model cho AI Chat
class AIChatMessage {
  final String id;
  final String text;
  final String thoughts;
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
    this.thoughts = '',
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
    String? thoughts,
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
      thoughts: thoughts ?? this.thoughts,
    );
  }
}
