import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/exercise_model.dart';

/// Service để cache và optimize exercise data
/// Cải thiện UX bằng cách:
/// - Cache exercises data để load nhanh hơn
/// - Optimistic updates cho thao tác CRUD
/// - Pre-fetch data cho các ngày gần đây
class ExerciseCacheService {
  static final ExerciseCacheService _instance = ExerciseCacheService._internal();
  factory ExerciseCacheService() => _instance;
  ExerciseCacheService._internal();

  // Cache exercises by date (key: "userId_yyyy-MM-dd")
  final Map<String, List<ExerciseModel>> _exercisesByDate = {};
  
  // Cache all exercises for a user (for history/stats)
  final Map<String, List<ExerciseModel>> _allExercisesByUser = {};
  
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

  /// Get cached exercises for a date
  List<ExerciseModel>? getCachedExercises(String userId, DateTime date) {
    final key = _getCacheKey(userId, date);
    if (!isCacheValid(userId, date)) {
      return null;
    }
    return _exercisesByDate[key];
  }

  /// Cache exercises for a date
  void cacheExercises(String userId, DateTime date, List<ExerciseModel> exercises) {
    final key = _getCacheKey(userId, date);
    _exercisesByDate[key] = List.from(exercises); // Create a copy
    _lastFetchTime[key] = DateTime.now();
    debugPrint('📦 ExerciseCache: Cached ${exercises.length} exercises for $key');
  }

  /// Cache all exercises for a user
  void cacheAllExercises(String userId, List<ExerciseModel> exercises) {
    _allExercisesByUser[userId] = List.from(exercises);
    debugPrint('📦 ExerciseCache: Cached ${exercises.length} total exercises for user $userId');
  }

  /// Get all cached exercises for a user
  List<ExerciseModel>? getAllCachedExercises(String userId) {
    return _allExercisesByUser[userId];
  }

  /// Update a single exercise in cache (optimistic update)
  void updateExerciseInCache(String userId, DateTime date, ExerciseModel exercise) {
    final key = _getCacheKey(userId, date);
    final cached = _exercisesByDate[key];
    if (cached != null) {
      final index = cached.indexWhere((e) => e.id == exercise.id);
      if (index != -1) {
        cached[index] = exercise;
        debugPrint('✏️ ExerciseCache: Updated exercise ${exercise.id} in cache');
      }
    }

    // Also update in all exercises cache
    final allCached = _allExercisesByUser[userId];
    if (allCached != null) {
      final index = allCached.indexWhere((e) => e.id == exercise.id);
      if (index != -1) {
        allCached[index] = exercise;
      }
    }
  }

  /// Add an exercise to cache (optimistic update)
  void addExerciseToCache(String userId, DateTime date, ExerciseModel exercise) {
    final key = _getCacheKey(userId, date);
    final cached = _exercisesByDate[key];
    if (cached != null) {
      cached.add(exercise);
      debugPrint('➕ ExerciseCache: Added exercise ${exercise.id} to cache');
    } else {
      _exercisesByDate[key] = [exercise];
      _lastFetchTime[key] = DateTime.now();
      debugPrint('➕ ExerciseCache: Created new cache with exercise ${exercise.id}');
    }

    // Also add to all exercises cache
    final allCached = _allExercisesByUser[userId];
    if (allCached != null) {
      allCached.add(exercise);
    }
  }

  /// Remove an exercise from cache (optimistic update)
  void removeExerciseFromCache(String userId, DateTime date, String exerciseId) {
    final key = _getCacheKey(userId, date);
    final cached = _exercisesByDate[key];
    if (cached != null) {
      cached.removeWhere((e) => e.id == exerciseId);
      debugPrint('🗑️ ExerciseCache: Removed exercise $exerciseId from cache');
    }

    // Also remove from all exercises cache
    final allCached = _allExercisesByUser[userId];
    if (allCached != null) {
      allCached.removeWhere((e) => e.id == exerciseId);
    }
  }

  /// Pre-fetch exercises for nearby dates (yesterday, today, tomorrow)
  Future<void> preFetchNearbyDates(
    String userId,
    DateTime centerDate,
    Future<List<ExerciseModel>> Function(DateTime) fetchFunction,
  ) async {
    final dates = [
      centerDate.subtract(const Duration(days: 1)), // Yesterday
      centerDate, // Today
      centerDate.add(const Duration(days: 1)), // Tomorrow
    ];

    for (final date in dates) {
      // Skip if already cached
      if (isCacheValid(userId, date)) {
        debugPrint('✅ ExerciseCache: Date ${date.day}/${date.month} already cached');
        continue;
      }

      try {
        final exercises = await fetchFunction(date);
        cacheExercises(userId, date, exercises);
      } catch (e) {
        debugPrint('⚠️ ExerciseCache: Failed to pre-fetch ${date.day}/${date.month}: $e');
      }
    }
  }

  /// Clear cache for a specific date
  void clearDateCache(String userId, DateTime date) {
    final key = _getCacheKey(userId, date);
    _exercisesByDate.remove(key);
    _lastFetchTime.remove(key);
    debugPrint('🗑️ ExerciseCache: Cleared cache for $key');
  }

  /// Clear all cache for a user
  void clearUserCache(String userId) {
    _exercisesByDate.removeWhere((key, _) => key.startsWith(userId));
    _lastFetchTime.removeWhere((key, _) => key.startsWith(userId));
    _allExercisesByUser.remove(userId);
    debugPrint('🗑️ ExerciseCache: Cleared all cache for user $userId');
  }

  /// Clear all cache
  void clearAllCache() {
    _exercisesByDate.clear();
    _allExercisesByUser.clear();
    _lastFetchTime.clear();
    debugPrint('🗑️ ExerciseCache: Cleared all cache');
  }

  /// Get cache statistics
  Map<String, dynamic> getCacheStats() {
    return {
      'totalCachedDates': _exercisesByDate.length,
      'totalExercises': _exercisesByDate.values.fold<int>(0, (sum, exercises) => sum + exercises.length),
      'totalUsers': _allExercisesByUser.length,
      'oldestCache': _lastFetchTime.values.isEmpty 
          ? null 
          : _lastFetchTime.values.reduce((a, b) => a.isBefore(b) ? a : b),
      'newestCache': _lastFetchTime.values.isEmpty 
          ? null 
          : _lastFetchTime.values.reduce((a, b) => a.isAfter(b) ? a : b),
    };
  }
}
