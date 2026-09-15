import 'dart:convert';

import '../../models/chat_message.dart';

/// Builds the development-only transcript copied from a completed assistant
/// reply. It deliberately uses only the allowlisted public trace and the
/// already-redacted developer telemetry held by the client.
String buildChatDebugTranscript({
  required String? userText,
  required String assistantText,
  required AIChatMessage assistantMessage,
}) {
  final transcript = StringBuffer()
    ..writeln('User')
    ..writeln(_copyableText(userText))
    ..writeln()
    ..writeln('Thinking (safe public trace)');

  final publicTrace = assistantMessage.publicTrace;
  if (publicTrace == null || !publicTrace.hasSteps) {
    transcript.writeln('(No public trace was emitted.)');
  } else {
    for (final step in publicTrace.steps) {
      transcript
        ..writeln('- ${step.title}')
        ..writeln('  ${step.summary}');
    }
  }

  if (assistantMessage.developerTrace.isNotEmpty) {
    transcript
      ..writeln()
      ..writeln('Debug execution trace (redacted)');
    for (final event in assistantMessage.developerTrace) {
      transcript
        ..writeln('[${event.timestamp}] ${event.operation}')
        ..writeln(_encodeSanitizedPayload(event.sanitizedPayload));
    }
  }

  transcript
    ..writeln()
    ..writeln('Assistant')
    ..writeln(_copyableText(assistantText));
  return transcript.toString().trimRight();
}

String _copyableText(String? value) {
  final trimmed = value?.trim() ?? '';
  return trimmed.isEmpty ? '(No content.)' : trimmed;
}

String _encodeSanitizedPayload(Map<String, dynamic> payload) {
  try {
    return jsonEncode(payload);
  } on JsonUnsupportedObjectError {
    return payload.toString();
  }
}
