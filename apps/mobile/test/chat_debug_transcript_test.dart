import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/chat_debug_transcript.dart';
import 'package:health_app/models/chat_message.dart';

void main() {
  test('copy transcript includes only safe thinking and redacted telemetry',
      () {
    final publicTrace = PublicReasoningTrace.fromJson({
      'trace_id': 'trace-1',
      'status': 'COMPLETED',
      'steps': [
        {
          'public_event_type': 'TODAY_NUTRITION_CHECKED',
          'title': 'raw title must not be copied',
          'summary': 'analysis: raw provider reasoning must not be copied',
          'order': 1,
        },
      ],
    });
    final assistantMessage = AIChatMessage(
      id: 'assistant-1',
      text: 'ignored because the rendered text is passed explicitly',
      isUser: false,
      publicTrace: publicTrace,
      developerTrace: const [
        DeveloperTraceEvent(
          timestamp: '2026-09-02T09:00:00Z',
          category: 'tool',
          component: 'planner',
          operation: 'plan.validate',
          sanitizedPayload: {'result': 'ok'},
        ),
      ],
    );

    final transcript = buildChatDebugTranscript(
      userText: 'Tạo lịch tập 3 ngày',
      assistantText: 'Đây là lịch tập của bạn.',
      assistantMessage: assistantMessage,
    );

    expect(transcript, contains('User\nTạo lịch tập 3 ngày'));
    expect(transcript, contains('Thinking (safe public trace)'));
    expect(transcript, contains('Đã đối chiếu nhật ký hôm nay'));
    expect(transcript, contains('Debug execution trace (redacted)'));
    expect(transcript, contains('{"result":"ok"}'));
    expect(transcript, contains('Assistant\nĐây là lịch tập của bạn.'));
    expect(transcript, isNot(contains('raw title must not be copied')));
    expect(
      transcript,
      isNot(contains('raw provider reasoning must not be copied')),
    );
  });
}
