import 'package:flutter/foundation.dart';

class AIChatbotConfig {
  // Reuse same base as REST API so WS always follows current environment.
  static const String _envBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String _defaultHttpBaseUrl = 'http://localhost:8080';

  // Android emulator
  // static const String wsBaseUrl = 'ws://10.0.2.2:8000';

  // Thiết bị thật (cùng WiFi, thay IP máy tính)
  // static const String wsBaseUrl = 'ws://192.168.1.x:8000';

  // Production: Cloudflare Tunnel
  // static const String wsBaseUrl = 'wss://your-tunnel.trycloudflare.com';

  static const String wsEndpoint = '/chat/stream';

  static String get wsUrl {
    var httpBase = _envBaseUrl.isNotEmpty ? _envBaseUrl : _defaultHttpBaseUrl;
    if (httpBase == 'http://localhost:8080' && !kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      httpBase = 'http://10.0.2.2:8080';
    }
    if (httpBase.startsWith('https://')) {
      return httpBase.replaceFirst('https://', 'wss://') + wsEndpoint;
    }
    if (httpBase.startsWith('http://')) {
      return httpBase.replaceFirst('http://', 'ws://') + wsEndpoint;
    }
    return httpBase + wsEndpoint;
  }

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration streamTimeout = Duration(seconds: 180);
}
