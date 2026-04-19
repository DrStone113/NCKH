class AIChatbotConfig {
  // Web local test: Flutter web và FastAPI cùng chạy trên localhost
  static const String wsBaseUrl = 'ws://localhost:8080';

  // Android emulator
  // static const String wsBaseUrl = 'ws://10.0.2.2:8000';

  // Thiết bị thật (cùng WiFi, thay IP máy tính)
  // static const String wsBaseUrl = 'ws://192.168.1.x:8000';

  // Production: Cloudflare Tunnel
  // static const String wsBaseUrl = 'wss://your-tunnel.trycloudflare.com';

  static const String wsEndpoint = '/chat/stream';
  static const String wsUrl = '$wsBaseUrl$wsEndpoint';

  static const Duration connectTimeout = Duration(seconds: 3);
  static const Duration streamTimeout = Duration(seconds: 120);
}
