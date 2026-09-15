import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/constants/ai_chatbot_config.dart';

void main() {
  test('WebSocket URL never carries an authentication token', () {
    final uri = Uri.parse(AIChatbotConfig.wsUrl);
    expect(uri.path, '/chat/stream');
    expect(uri.queryParameters['token'], isNull);
  });

  test('N3 E2E runtime marker is non-secret and opt-in', () {
    const marker = String.fromEnvironment('N3_2_1_E2E_CONFIGURATION_MARKER');
    expect(
      AIChatbotConfig.n3E2ERuntimeConfigurationActive,
      marker == 'N3_2_1_E2E_CONFIGURED_V1',
    );
  });

  test('normal WebSocket URL carries exact session but no Firebase token', () {
    final uri = Uri.parse(AIChatbotConfig.wsUrlFor(
      sessionId: 'session-123',
      firebaseToken: 'firebase-token',
    ));
    expect(uri.queryParameters['session_id'], 'session-123');
    expect(uri.queryParameters['token'], isNull);
  });

  test('WebSocket subprotocol carries the Firebase token', () {
    final protocols = AIChatbotConfig.wsProtocolsFor(
      firebaseToken: 'firebase-token',
    );
    const e2eToken = String.fromEnvironment('N3_2_1_TEST_TOKEN');
    expect(protocols.first, 'health-auth-v1');
    expect(protocols.last,
        'auth.${e2eToken.isEmpty ? 'firebase-token' : e2eToken}');
  });
}
