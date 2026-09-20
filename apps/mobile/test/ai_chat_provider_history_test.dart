import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/providers/ai_chat_provider.dart';

void main() {
  test('restores the exact structured meal card from chat history', () {
    final provider = AIChatProvider();

    provider.loadExistingSession('session-1', [
      {
        'id': 'message-1',
        'role': 'assistant',
        'content': 'Đã ghi nhận Cơm sườn',
        'created_at': '2026-08-14T10:00:00Z',
        'structured': {
          'type': 'structured',
          'text': '',
          'meal_name': 'Cơm sườn',
          'actions': [
            {
              'kind': 'food',
              'wger_id': 0,
              'name': 'Cơm',
              'details': {
                'dish_name': 'Cơm sườn',
                'meal_type': 'lunch',
                'serving_grams': 214.0,
                'calories': 130.0,
                'protein': 2.7,
                'carbs': 28.0,
                'fat': 0.3,
              },
            },
            {
              'kind': 'food',
              'wger_id': 0,
              'name': 'Sườn heo',
              'details': {
                'dish_name': 'Cơm sườn',
                'meal_type': 'lunch',
                'serving_grams': 129.0,
                'calories': 242.0,
                'protein': 27.0,
                'carbs': 0.0,
                'fat': 14.0,
              },
            },
          ],
        },
      },
    ]);

    final response = provider.messages.single.structuredResponse;
    expect(response, isNotNull);
    expect(response!.mealName, 'Cơm sườn');
    expect(response.foodActions, hasLength(2));
    expect(response.foodActions.first.name, 'Cơm');
    expect(response.foodActions.first.details['serving_grams'], 214.0);

    provider.dispose();
  });

  test('restores the newest non-empty server session', () async {
    final provider = AIChatProvider();
    final requestedSessionIds = <String>[];

    final restored = await provider.restoreLatestSession(
      loadSessions: () async => [
        {'id': 'empty-session'},
        {'id': 'latest-real-session'},
        {'id': 'older-session'},
      ],
      loadMessages: (sessionId) async {
        requestedSessionIds.add(sessionId);
        if (sessionId == 'empty-session') return [];
        return [
          {
            'id': 'message-1',
            'role': 'user',
            'content': 'Tôi muốn ăn burger',
            'created_at': '2026-09-20T03:00:00Z',
          },
          {
            'id': 'message-2',
            'role': 'assistant',
            'content': 'Bạn có thể chọn burger gà.',
            'created_at': '2026-09-20T03:00:01Z',
          },
        ];
      },
    );

    expect(restored, isTrue);
    expect(provider.currentSessionId, 'latest-real-session');
    expect(requestedSessionIds, ['empty-session', 'latest-real-session']);
    expect(provider.messages.map((message) => message.text), [
      'Tôi muốn ăn burger',
      'Bạn có thể chọn burger gà.',
    ]);

    provider.dispose();
  });

  test('does not create a session when server history is empty', () async {
    final provider = AIChatProvider();

    final restored = await provider.restoreLatestSession(
      loadSessions: () async => [],
      loadMessages: (_) async => [],
    );

    expect(restored, isFalse);
    expect(provider.currentSessionId, isNull);
    expect(provider.messages, isEmpty);

    provider.dispose();
  });
}
