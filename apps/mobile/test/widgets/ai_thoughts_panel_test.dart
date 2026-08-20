import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/screens/chatbot_screen.dart';

void main() {
  testWidgets('history thoughts use the same expanded panel', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AIThoughtsPanel(
            thoughts: 'Đối chiếu dữ liệu lịch sử.',
            isThinking: false,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Xem quá trình suy nghĩ'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is RichText &&
            widget.text.toPlainText() == 'Đối chiếu dữ liệu lịch sử.',
      ),
      findsOneWidget,
    );
  });
}
