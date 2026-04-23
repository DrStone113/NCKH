import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Service để gọi backend API
/// Hỗ trợ cả local development và production
class BackendApiService {
  static final BackendApiService _instance = BackendApiService._internal();
  factory BackendApiService() => _instance;
  BackendApiService._internal();

  // Backend URL - có thể config từ environment
  static const String _localUrl = 'http://localhost:8000';
  static const String _productionUrl = 'https://your-backend-url.com'; // TODO: Update this
  
  String get baseUrl => kDebugMode ? _localUrl : _productionUrl;
  
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
        final data = json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
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
        final data = json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
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

  /// Dispose
  void dispose() {
    _client.close();
  }
}
