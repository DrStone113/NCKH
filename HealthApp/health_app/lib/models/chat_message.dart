import 'wger_models.dart';

/// Model cho AI Chat — thay thế ChatMessage trong health_models.dart (chỉ dùng cho AI chat)
class AIChatMessage {
  final String id;
  final String text;
  final bool isUser;
  final bool isStreaming;
  final DateTime timestamp;
  final StructuredResponse? structuredResponse;
  final List<String> suggestions;
  final bool isFlowQuestion; // true khi đang trong conversation flow

  AIChatMessage({
    required this.id,
    required this.text,
    required this.isUser,
    this.isStreaming = false,
    DateTime? timestamp,
    this.structuredResponse,
    this.suggestions = const [],
    this.isFlowQuestion = false,
  }) : timestamp = timestamp ?? DateTime.now();

  AIChatMessage copyWith({
    String? id,
    String? text,
    bool? isUser,
    bool? isStreaming,
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
      timestamp: timestamp ?? this.timestamp,
      structuredResponse: structuredResponse ?? this.structuredResponse,
      suggestions: suggestions ?? this.suggestions,
      isFlowQuestion: isFlowQuestion ?? this.isFlowQuestion,
    );
  }
}
