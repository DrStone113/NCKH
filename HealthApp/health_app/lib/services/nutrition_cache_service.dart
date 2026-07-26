import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/meal_model.dart';

/// Service để cache và optimize nutrition data
/// Cải thiện UX bằng cách:
/// - Cache meals data để load nhanh hơn
/// - Optimistic updates cho thao tác CRUD
/// - Pre-fetch data cho các ngày gần đây
class NutritionCacheService {
  static final NutritionCacheService _instance = NutritionCacheService._internal();
  factory NutritionCacheService() => _instance;
  NutritionCacheService._internal();

  // Cache meals by date (key: "userId_yyyy-MM-dd")
  final Map<String, List<MealModel>> _mealsByDate = {};
  
  // Cache metadata
  final Map<String, DateTime> _lastFetchTime = {};
  static const Duration _cacheDuration = Duration(minutes: 15);

  /// Get cache key for a specific date
  String _getCacheKey(String userId, DateTime date) {
    return '${userId}_${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }

  /// Check if cache is valid for a date
  bool isCacheValid(String userId, DateTime date) {
    final key = _getCacheKey(userId, date);
    final lastFetch = _lastFetchTime[key];
    if (lastFetch == null) return false;
    
    final elapsed = DateTime.now().difference(lastFetch);
    return elapsed < _cacheDuration;
  }

  /// Get cached meals for a date
  List<MealModel>? getCachedMeals(String userId, DateTime date) {
    final key = _getCacheKey(userId, date);
    if (!isCacheValid(userId, date)) {
      return null;
    }
    return _mealsByDate[key];
  }

  /// Cache meals for a date
  void cacheMeals(String userId, DateTime date, List<MealModel> meals) {
    final key = _getCacheKey(userId, date);
    _mealsByDate[key] = List.from(meals); // Create a copy
    _lastFetchTime[key] = DateTime.now();
    debugPrint('📦 NutritionCache: Cached ${meals.length} meals for $key');
  }

  /// Update a single meal in cache (optimistic update)
  void updateMealInCache(String userId, DateTime date, MealModel meal) {
    final key = _getCacheKey(userId, date);
    final cached = _mealsByDate[key];
    if (cached != null) {
      final index = cached.indexWhere((m) => m.id == meal.id);
      if (index != -1) {
        cached[index] = meal;
        debugPrint('✏️ NutritionCache: Updated meal ${meal.id} in cache');
      }
    }
  }

  /// Add a meal to cache (optimistic update)
  void addMealToCache(String userId, DateTime date, MealModel meal) {
    final key = _getCacheKey(userId, date);
    final cached = _mealsByDate[key];
    if (cached != null) {
      cached.add(meal);
      debugPrint('➕ NutritionCache: Added meal ${meal.id} to cache');
    } else {
      _mealsByDate[key] = [meal];
      _lastFetchTime[key] = DateTime.now();
      debugPrint('➕ NutritionCache: Created new cache with meal ${meal.id}');
    }
  }

  /// Remove a meal from cache (optimistic update)
  void removeMealFromCache(String userId, DateTime date, String mealId) {
    final key = _getCacheKey(userId, date);
    final cached = _mealsByDate[key];
    if (cached != null) {
      cached.removeWhere((m) => m.id == mealId);
      debugPrint('🗑️ NutritionCache: Removed meal $mealId from cache');
    }
  }

  /// Pre-fetch meals for nearby dates (yesterday, today, tomorrow)
  Future<void> preFetchNearbyDates(
    String userId,
    DateTime centerDate,
    Future<List<MealModel>> Function(DateTime) fetchFunction,
  ) async {
    final dates = [
      centerDate.subtract(const Duration(days: 1)), // Yesterday
      centerDate, // Today
      centerDate.add(const Duration(days: 1)), // Tomorrow
    ];

    for (final date in dates) {
      // Skip if already cached
      if (isCacheValid(userId, date)) {
        debugPrint('✅ NutritionCache: Date ${date.day}/${date.month} already cached');
        continue;
      }

      try {
        final meals = await fetchFunction(date);
        cacheMeals(userId, date, meals);
      } catch (e) {
        debugPrint('⚠️ NutritionCache: Failed to pre-fetch ${date.day}/${date.month}: $e');
      }
    }
  }

  /// Clear cache for a specific date
  void clearDateCache(String userId, DateTime date) {
    final key = _getCacheKey(userId, date);
    _mealsByDate.remove(key);
    _lastFetchTime.remove(key);
    debugPrint('🗑️ NutritionCache: Cleared cache for $key');
  }

  /// Clear all cache
  void clearAllCache() {
    _mealsByDate.clear();
    _lastFetchTime.clear();
    debugPrint('🗑️ NutritionCache: Cleared all cache');
  }

  /// Get cache statistics
  Map<String, dynamic> getCacheStats() {
    return {
      'totalCachedDates': _mealsByDate.length,
      'totalMeals': _mealsByDate.values.fold<int>(0, (sum, meals) => sum + meals.length),
      'oldestCache': _lastFetchTime.values.isEmpty 
          ? null 
          : _lastFetchTime.values.reduce((a, b) => a.isBefore(b) ? a : b),
      'newestCache': _lastFetchTime.values.isEmpty 
          ? null 
          : _lastFetchTime.values.reduce((a, b) => a.isAfter(b) ? a : b),
    };
  }
}
