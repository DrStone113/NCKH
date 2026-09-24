import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/providers/ai_chat_provider.dart';

void main() {
  test('turn correlation rejects stale and post-completion events', () {
    expect(AIChatProvider.acceptsTurnEvent('turn-2', 'turn-1'), isFalse);
    expect(AIChatProvider.acceptsTurnEvent(null, 'turn-1'), isFalse);
    expect(AIChatProvider.acceptsTurnEvent('turn-1', 'turn-1'), isTrue);
    expect(AIChatProvider.acceptsTurnEvent('turn-1', null), isTrue);
  });

  test('blank done event is not considered a completed answer', () {
    expect(
      AIChatProvider.hasUsableDonePayload({'full_response': ''}),
      isFalse,
    );
    expect(
      AIChatProvider.hasUsableDonePayload({'full_response': '   '}),
      isFalse,
    );
    expect(
      AIChatProvider.hasUsableDonePayload({'full_response': 'Câu trả lời'}),
      isTrue,
    );
    expect(
      AIChatProvider.hasUsableDonePayload({
        'full_response': '',
        'structured': <String, dynamic>{'type': 'structured'},
      }),
      isTrue,
    );
  });

  test('progress heartbeat is accepted for an active turn only', () {
    expect(AIChatProvider.acceptsTurnEvent('turn-1', 'turn-1'), isTrue);
    expect(AIChatProvider.acceptsTurnEvent('turn-2', 'turn-1'), isFalse);
  });

  test('chat transport begins disconnected', () {
    expect(AIChatProvider().transportState, ChatTransportState.disconnected);
  });

  test('client action state begins empty', () {
    final provider = AIChatProvider();
    expect(provider.lastClientActionName, isNull);
    expect(provider.lastClientActionSucceeded, isNull);
  });
}
