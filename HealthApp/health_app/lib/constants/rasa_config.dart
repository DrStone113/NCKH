class RasaConfig {
  // Thay đổi URL này khi deploy lên server thực tế
  static const String baseUrl = 'http://10.0.2.2:5005'; // Android emulator
  // static const String baseUrl = 'http://localhost:5005'; // Web/Desktop
  // static const String baseUrl = 'http://YOUR_SERVER_IP:5005'; // Production

  static const String webhookEndpoint = '/webhooks/rest/webhook';
  static const String webhookUrl = '$baseUrl$webhookEndpoint';

  static const Duration requestTimeout = Duration(seconds: 5);
}
