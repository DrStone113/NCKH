import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/screens/chatbot_screen.dart';
import 'package:health_app/models/chat_message.dart';

void main() {
  testWidgets('history public trace uses the same expanded panel',
      (tester) async {
    final trace = PublicReasoningTrace.fromJson({
      'trace_id': 'trace-1',
      'status': 'COMPLETED',
      'steps': [
        {
          'public_event_type': 'TODAY_NUTRITION_CHECKED',
          'title': 'raw title must be ignored',
          'summary': 'analysis: secret tool arguments must be ignored',
          'order': 1,
        },
      ],
    });
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AIThoughtsPanel(
            publicTrace: trace,
            isThinking: false,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Xem cách mình xử lý'), findsOneWidget);
    expect(find.text('Đã đối chiếu nhật ký hôm nay'), findsOneWidget);
    expect(
      find.text('Mình kiểm tra dữ liệu đã ghi để tránh gợi ý trùng lặp.'),
      findsOneWidget,
    );
    expect(find.textContaining('analysis:'), findsNothing);
    expect(find.textContaining('raw title'), findsNothing);
  });

  testWidgets('panel header uses the available phone-width space',
      (tester) async {
    final trace = PublicReasoningTrace.fromJson({
      'trace_id': 'trace-compact',
      'status': 'COMPLETED',
      'steps': [
        {
          'public_event_type': 'TODAY_NUTRITION_CHECKED',
          'order': 1,
        },
      ],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 260,
              child: AIThoughtsPanel(
                publicTrace: trace,
                isThinking: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final titleSize = tester.getSize(find.text('Xem cách mình xử lý'));
    expect(titleSize.width, greaterThan(100));
    expect(titleSize.height, lessThan(20));
  });
}
