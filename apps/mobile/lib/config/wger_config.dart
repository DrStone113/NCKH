import 'package:flutter/foundation.dart';

/// Cấu hình cho wger API Integration
class WgerConfig {
  static const String _envBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String _defaultBackendBaseUrl = 'http://localhost:8080';

  // Base URL của backend proxy (thay vì gọi trực tiếp wger.de)
  static String get backendBaseUrl {
    if (_envBaseUrl.isNotEmpty) return _envBaseUrl;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8080';
    }
    return _defaultBackendBaseUrl;
  }

  static String get baseUrl => '$backendBaseUrl/wger';

  // Timeout cho các request HTTP
  static const Duration requestTimeout = Duration(seconds: 15);

  // Độ dài tối thiểu của query để bắt đầu tìm kiếm
  static const int minSearchLength = 2;

  // Thời gian debounce cho search input
  static const Duration searchDebounce = Duration(milliseconds: 500);
}
