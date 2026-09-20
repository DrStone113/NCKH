import '../config/backend_endpoint_config.dart';

class AIChatbotConfig {
  // Isolated development E2E only. In normal and production builds this is
  // empty, so WebSocket authentication continues to use the normal session.
  // The value is never rendered, logged, or persisted by the app.
  static const String _n3FeedbackTestToken =
      String.fromEnvironment('N3_2_1_TEST_TOKEN');
  // Non-secret build assertion for the isolated Brave harness. The marker is
  // meaningful only together with the test token above; it never includes or
  // exposes that token.
  static const String n3E2ERuntimeConfigurationMarker =
      String.fromEnvironment('N3_2_1_E2E_CONFIGURATION_MARKER');
  static const bool n3E2ERuntimeConfigurationActive =
      n3E2ERuntimeConfigurationMarker == 'N3_2_1_E2E_CONFIGURED_V1';
  // Android emulator
  // static const String wsBaseUrl = 'ws://10.0.2.2:8000';

  // Thiết bị thật (cùng WiFi, thay IP máy tính)
  // static const String wsBaseUrl = 'ws://192.168.1.x:8000';

  // Production: Cloudflare Tunnel
  // static const String wsBaseUrl = 'wss://your-tunnel.trycloudflare.com';

  static const String wsEndpoint = '/chat/stream';

  static String wsUrlFor({required String sessionId, String? firebaseToken}) {
    final httpBase = BackendEndpointConfig.baseUrl;
    final rawUrl = httpBase.startsWith('https://')
        ? httpBase.replaceFirst('https://', 'wss://') + wsEndpoint
        : httpBase.startsWith('http://')
            ? httpBase.replaceFirst('http://', 'ws://') + wsEndpoint
            : httpBase + wsEndpoint;
    return Uri.parse(rawUrl).replace(queryParameters: {
      'session_id': sessionId,
    }).toString();
  }

  /// Carries authentication outside the URL so reverse-proxy/access logs do
  /// not persist a Firebase ID token. The server negotiates only the fixed
  /// protocol name; the credential protocol remains request-only.
  static List<String> wsProtocolsFor({String? firebaseToken}) {
    final token = _n3FeedbackTestToken.isNotEmpty
        ? _n3FeedbackTestToken
        : firebaseToken?.trim() ?? '';
    return [
      'health-auth-v1',
      if (token.isNotEmpty) 'auth.$token',
    ];
  }

  static String get wsUrl => wsUrlFor(sessionId: 'configuration-preview');

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration streamTimeout = Duration(seconds: 180);
}
