import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Service để gọi backend API
/// Hỗ trợ cả local development và production
class BackendApiService {
  static final BackendApiService _instance = BackendApiService._internal();
  factory BackendApiService() => _instance;
  BackendApiService._internal();

  // Backend URL - ưu tiên lấy từ --dart-define API_BASE_URL.
  static const String _defaultBaseUrl = 'http://localhost:8080';
  static const String _envBaseUrl = String.fromEnvironment('API_BASE_URL');

  String get baseUrl {
    if (_envBaseUrl.isNotEmpty) return _envBaseUrl;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8080';
    }
    return _defaultBaseUrl;
  }

  final http.Client _client = http.Client();

  // Cache
  List<Map<String, dynamic>>? _cachedDishes;
  List<Map<String, dynamic>>? _cachedFoods;
  DateTime? _lastDishFetch;
  DateTime? _lastFoodFetch;
  static const Duration _cacheDuration = Duration(hours: 1);

  /// Get Vietnamese dishes from backend
  Future<List<Map<String, dynamic>>> getVietnameseDishes() async {
    // Check cache first
    if (_cachedDishes != null && _lastDishFetch != null) {
      final elapsed = DateTime.now().difference(_lastDishFetch!);
      if (elapsed < _cacheDuration) {
        debugPrint('📦 BackendAPI: Returning cached dishes');
        return _cachedDishes!;
      }
    }

    try {
      debugPrint('🌐 BackendAPI: Fetching Vietnamese dishes...');
      final response = await _client
          .get(Uri.parse('$baseUrl/api/nutrition/vietnamese-dishes'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data =
            json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
        _cachedDishes = data.map((e) => e as Map<String, dynamic>).toList();
        _lastDishFetch = DateTime.now();
        debugPrint('✅ BackendAPI: Loaded ${_cachedDishes!.length} dishes');
        return _cachedDishes!;
      } else {
        throw Exception('Failed to load dishes: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ BackendAPI: Error loading dishes: $e');
      // Return cached data if available, even if expired
      if (_cachedDishes != null) {
        debugPrint('⚠️ BackendAPI: Using expired cache');
        return _cachedDishes!;
      }
      rethrow;
    }
  }

  /// Get Vietnamese foods from backend
  Future<List<Map<String, dynamic>>> getVietnameseFoods() async {
    // Check cache first
    if (_cachedFoods != null && _lastFoodFetch != null) {
      final elapsed = DateTime.now().difference(_lastFoodFetch!);
      if (elapsed < _cacheDuration) {
        debugPrint('📦 BackendAPI: Returning cached foods');
        return _cachedFoods!;
      }
    }

    try {
      debugPrint('🌐 BackendAPI: Fetching Vietnamese foods...');
      final response = await _client
          .get(Uri.parse('$baseUrl/api/nutrition/vietnamese-foods'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data =
            json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
        _cachedFoods = data.map((e) => e as Map<String, dynamic>).toList();
        _lastFoodFetch = DateTime.now();
        debugPrint('✅ BackendAPI: Loaded ${_cachedFoods!.length} foods');
        return _cachedFoods!;
      } else {
        throw Exception('Failed to load foods: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ BackendAPI: Error loading foods: $e');
      // Return cached data if available, even if expired
      if (_cachedFoods != null) {
        debugPrint('⚠️ BackendAPI: Using expired cache');
        return _cachedFoods!;
      }
      rethrow;
    }
  }

  /// Search Vietnamese foods
  Future<List<Map<String, dynamic>>> searchFoods(String query) async {
    final foods = await getVietnameseFoods();
    if (query.isEmpty) return foods;

    return foods.where((food) {
      final name = (food['name'] ?? '').toString().toLowerCase();
      return name.contains(query.toLowerCase());
    }).toList();
  }

  /// Search Vietnamese dishes
  Future<List<Map<String, dynamic>>> searchDishes(String query) async {
    final dishes = await getVietnameseDishes();
    if (query.isEmpty) return dishes;

    return dishes.where((dish) {
      final name = (dish['name'] ?? '').toString().toLowerCase();
      return name.contains(query.toLowerCase());
    }).toList();
  }

  /// Get dish by ID
  Future<Map<String, dynamic>?> getDishById(String id) async {
    final dishes = await getVietnameseDishes();
    try {
      return dishes.firstWhere((dish) => dish['id'] == id);
    } catch (e) {
      return null;
    }
  }

  /// Get food by ID
  Future<Map<String, dynamic>?> getFoodById(String id) async {
    final foods = await getVietnameseFoods();
    try {
      return foods.firstWhere((food) => food['id'] == id);
    } catch (e) {
      return null;
    }
  }

  /// Clear cache
  void clearCache() {
    _cachedDishes = null;
    _cachedFoods = null;
    _lastDishFetch = null;
    _lastFoodFetch = null;
    debugPrint('🗑️ BackendAPI: Cache cleared');
  }

  Future<Map<String, dynamic>> createLongTermPlan({
    required String userId,
    required Map<String, dynamic> userContext,
    required int days,
    double? targetWeight,
    String? notes,
  }) async {
    final payload = {
      'user_id': userId,
      'user_context': userContext,
      'duration': {'days': days},
      'target': {
        if (targetWeight != null) 'target_weight': targetWeight,
        if (notes != null && notes.isNotEmpty) 'notes': notes,
      }
    };

    final response = await _client
        .post(
          Uri.parse('$baseUrl/plans'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Create plan failed: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getActivePlan(String userId) async {
    final response = await _client
        .get(Uri.parse('$baseUrl/plans/$userId/active'))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Get active plan failed: ${response.statusCode}');
  }

  Future<void> updatePlanItemCompletion({
    required String itemId,
    required bool completed,
  }) async {
    final response = await _client
        .patch(
          Uri.parse('$baseUrl/plans/items/$itemId'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'completed': completed}),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Update plan item failed: ${response.statusCode}');
    }
  }

  /// Get chat sessions list for a user
  Future<List<Map<String, dynamic>>> getChatSessions({String? userId}) async {
    final uri = Uri.parse('$baseUrl/chat/sessions').replace(queryParameters: {
      if (userId != null && userId.isNotEmpty) 'user_id': userId,
    });
    final response =
        await _client.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final list =
          json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    }
    throw Exception('Get chat sessions failed: ${response.statusCode}');
  }

  /// Get messages for a specific session ID
  Future<List<Map<String, dynamic>>> getSessionMessages(
      String sessionId) async {
    final response = await _client
        .get(Uri.parse('$baseUrl/chat/sessions/$sessionId/messages'))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final list =
          json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    }
    throw Exception('Get session messages failed: ${response.statusCode}');
  }

  /// Delete a chat session
  Future<void> deleteChatSession(String sessionId) async {
    final response = await _client
        .delete(Uri.parse('$baseUrl/chat/sessions/$sessionId'))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Delete chat session failed: ${response.statusCode}');
    }
  }

  /// Get active proactive check-in nudge
  Future<Map<String, dynamic>?> getActiveCheckin({String userId = 'default_user'}) async {
    try {
      final uri = Uri.parse('$baseUrl/checkin/active').replace(queryParameters: {'user_id': userId});
      final response = await _client.get(uri).timeout(const Duration(seconds: 10));
      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty || response.body == 'null') return null;
        return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      debugPrint('❌ BackendAPI: Error getting active checkin: $e');
      return null;
    }
  }

  /// Respond to proactive check-in
  Future<Map<String, dynamic>> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    String userId = 'default_user',
  }) async {
    final payload = {
      'nudge_id': nudgeId,
      'user_id': userId,
      if (selectedOptionId != null) 'selected_option_id': selectedOptionId,
      if (responseText != null) 'response_text': responseText,
    };
    final response = await _client.post(
      Uri.parse('$baseUrl/checkin/respond'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    ).timeout(const Duration(seconds: 10));

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Respond checkin failed: ${response.statusCode}');
  }

  /// Get check-in settings
  Future<Map<String, dynamic>> getCheckinSettings({String userId = 'default_user'}) async {
    final uri = Uri.parse('$baseUrl/checkin/settings').replace(queryParameters: {'user_id': userId});
    final response = await _client.get(uri).timeout(const Duration(seconds: 10));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Get checkin settings failed: ${response.statusCode}');
  }

  /// Update check-in settings
  Future<Map<String, dynamic>> updateCheckinSettings(
    Map<String, dynamic> settings, {
    String userId = 'default_user',
  }) async {
    final uri = Uri.parse('$baseUrl/checkin/settings').replace(queryParameters: {'user_id': userId});
    final response = await _client.put(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(settings),
    ).timeout(const Duration(seconds: 10));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    throw Exception('Update checkin settings failed: ${response.statusCode}');
  }

  /// Dispose
  void dispose() {
    _client.close();
  }
}

