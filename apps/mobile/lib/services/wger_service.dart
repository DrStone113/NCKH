import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config/wger_config.dart';
import '../models/wger_models.dart';

/// Exception cho lỗi từ wger API
class WgerApiException implements Exception {
  final String message;
  final int? statusCode;

  WgerApiException(this.message, {this.statusCode});

  @override
  String toString() => 'WgerApiException: $message${statusCode != null ? ' (Status: $statusCode)' : ''}';
}

/// Service để gọi wger API
class WgerService {
  final http.Client _client;

  WgerService({http.Client? client}) : _client = client ?? http.Client();

  /// Lấy danh sách bài tập với phân trang và filter
  Future<WgerExerciseListResponse> fetchExercises({
    int page = 1,
    int? categoryId,
    int? muscleId,
  }) async {
    try {
      final queryParams = {
        'page': page.toString(),
      };

      if (categoryId != null) {
        queryParams['category'] = categoryId.toString();
      }

      if (muscleId != null) {
        queryParams['muscles'] = muscleId.toString();
      }

      final uri = Uri.parse('${WgerConfig.baseUrl}/exercises')
          .replace(queryParameters: queryParams);

      debugPrint('🌐 Fetching: $uri');

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      debugPrint('📡 Response status: ${response.statusCode}');
      debugPrint('📦 Response length: ${response.body.length} bytes');

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        debugPrint('✅ Parsed JSON successfully');
        debugPrint('   Count: ${data['count']}');
        debugPrint('   Results: ${(data['results'] as List?)?.length ?? 0}');
        
        final result = WgerExerciseListResponse.fromJson(data);
        debugPrint('✅ Created response object with ${result.results.length} exercises');
        return result;
      } else {
        throw WgerApiException(
          'Không thể tải danh sách bài tập từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      debugPrint('⏱️ Request timeout');
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e, stackTrace) {
      debugPrint('❌ Exception in fetchExercises: $e');
      debugPrint('   Stack: $stackTrace');
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tải danh sách bài tập: $e');
    }
  }

  /// Lấy chi tiết một bài tập
  Future<WgerExercise> fetchExerciseDetail(int id) async {
    try {
      final uri = Uri.parse('${WgerConfig.baseUrl}/exercise/$id');

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        return WgerExercise.fromJson(data);
      } else {
        throw WgerApiException(
          'Không thể tải chi tiết bài tập từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e) {
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tải chi tiết bài tập: $e');
    }
  }

  /// Tìm kiếm thực phẩm theo tên
  Future<WgerIngredientListResponse> searchIngredients(
    String query, {
    int page = 1,
  }) async {
    try {
      final uri = Uri.parse('${WgerConfig.baseUrl}/ingredient/').replace(
        queryParameters: {
          'format': 'json',
          'language': '2',
          'name': query,
          'page': page.toString(),
        },
      );

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        return WgerIngredientListResponse.fromJson(data);
      } else {
        throw WgerApiException(
          'Không thể tìm kiếm thực phẩm từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e) {
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tìm kiếm thực phẩm: $e');
    }
  }

  /// Lấy danh sách danh mục bài tập
  Future<List<WgerExerciseCategory>> fetchExerciseCategories() async {
    try {
      final uri = Uri.parse('${WgerConfig.baseUrl}/categories');

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        final results = data['results'] as List<dynamic>? ?? [];
        return results
            .map((item) => WgerExerciseCategory.fromJson(item as Map<String, dynamic>))
            .toList();
      } else {
        throw WgerApiException(
          'Không thể tải danh mục bài tập từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e) {
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tải danh mục bài tập: $e');
    }
  }

  /// Lấy danh sách nhóm cơ
  Future<List<WgerMuscle>> fetchMuscles() async {
    try {
      final uri = Uri.parse('${WgerConfig.baseUrl}/muscles');

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        final results = data['results'] as List<dynamic>? ?? [];
        return results
            .map((item) => WgerMuscle.fromJson(item as Map<String, dynamic>))
            .toList();
      } else {
        throw WgerApiException(
          'Không thể tải danh sách nhóm cơ từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e) {
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tải danh sách nhóm cơ: $e');
    }
  }

  /// Lấy danh sách thiết bị
  Future<List<WgerEquipment>> fetchEquipment() async {
    try {
      final uri = Uri.parse('${WgerConfig.baseUrl}/equipment/')
          .replace(queryParameters: {'format': 'json'});

      final response = await _client
          .get(uri)
          .timeout(WgerConfig.requestTimeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        final results = data['results'] as List<dynamic>? ?? [];
        return results
            .map((item) => WgerEquipment.fromJson(item as Map<String, dynamic>))
            .toList();
      } else {
        throw WgerApiException(
          'Không thể tải danh sách thiết bị từ wger',
          statusCode: response.statusCode,
        );
      }
    } on TimeoutException {
      throw WgerApiException('Kết nối wger quá chậm. Vui lòng thử lại.');
    } catch (e) {
      if (e is WgerApiException) rethrow;
      throw WgerApiException('Lỗi khi tải danh sách thiết bị: $e');
    }
  }

  /// Đóng HTTP client
  void dispose() {
    _client.close();
  }
}
