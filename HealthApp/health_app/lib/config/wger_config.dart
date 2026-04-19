/// Cấu hình cho wger API Integration
class WgerConfig {
  // Base URL của backend proxy (thay vì gọi trực tiếp wger.de)
  static const String baseUrl = 'http://localhost:8080/wger';
  
  // Timeout cho các request HTTP
  static const Duration requestTimeout = Duration(seconds: 15);
  
  // Độ dài tối thiểu của query để bắt đầu tìm kiếm
  static const int minSearchLength = 2;
  
  // Thời gian debounce cho search input
  static const Duration searchDebounce = Duration(milliseconds: 500);
}
