import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/wger_models.dart';
import 'wger_service.dart';

/// Service để cache và pre-fetch dữ liệu từ wger API
/// Giúp cải thiện UX bằng cách load data sớm và cache lại
class WgerCacheService {
  static final WgerCacheService _instance = WgerCacheService._internal();
  factory WgerCacheService() => _instance;
  WgerCacheService._internal();

  final WgerService _wgerService = WgerService();

  // Cache data
  List<WgerExercise>? _cachedExercises;
  List<WgerExerciseCategory>? _cachedCategories;
  List<WgerMuscle>? _cachedMuscles;
  List<WgerEquipment>? _cachedEquipment;
  
  // Cache metadata
  DateTime? _lastFetchTime;
  bool _isFetching = false;
  bool _isAvailable = false;
  
  // Cache duration (30 minutes)
  static const Duration _cacheDuration = Duration(minutes: 30);
  
  // Getters
  bool get isAvailable => _isAvailable;
  bool get isFetching => _isFetching;
  bool get hasCachedData => _cachedExercises != null && _cachedExercises!.isNotEmpty;
  
  List<WgerExercise> get cachedExercises => _cachedExercises ?? [];
  List<WgerExerciseCategory> get cachedCategories => _cachedCategories ?? [];
  List<WgerMuscle> get cachedMuscles => _cachedMuscles ?? [];
  List<WgerEquipment> get cachedEquipment => _cachedEquipment ?? [];

  /// Pre-fetch data từ wger API
  /// Nên gọi khi app khởi động
  Future<void> preFetchData() async {
    if (_isFetching) {
      debugPrint('⏳ WgerCache: Already fetching, skipping...');
      return;
    }

    // Check if cache is still valid
    if (_isCacheValid()) {
      debugPrint('✅ WgerCache: Cache is still valid, skipping fetch');
      return;
    }

    _isFetching = true;
    debugPrint('🚀 WgerCache: Starting pre-fetch...');

    try {
      // Fetch metadata first (categories, muscles, equipment)
      final metadataResults = await Future.wait([
        _wgerService.fetchExerciseCategories(),
        _wgerService.fetchMuscles(),
        _wgerService.fetchEquipment(),
      ]).timeout(const Duration(seconds: 10));

      _cachedCategories = metadataResults[0] as List<WgerExerciseCategory>;
      _cachedMuscles = metadataResults[1] as List<WgerMuscle>;
      _cachedEquipment = metadataResults[2] as List<WgerEquipment>;

      debugPrint('✅ WgerCache: Metadata fetched');
      debugPrint('   Categories: ${_cachedCategories!.length}');
      debugPrint('   Muscles: ${_cachedMuscles!.length}');
      debugPrint('   Equipment: ${_cachedEquipment!.length}');

      // Fetch first 3 pages of exercises (about 60 exercises)
      final exercises = <WgerExercise>[];
      for (int page = 1; page <= 3; page++) {
        try {
          final response = await _wgerService.fetchExercises(page: page)
              .timeout(const Duration(seconds: 8));
          exercises.addAll(response.results);
          debugPrint('✅ WgerCache: Page $page fetched (${response.results.length} exercises)');
          
          // Stop if no more data
          if (response.results.isEmpty || response.next == null) {
            break;
          }
        } catch (e) {
          debugPrint('⚠️ WgerCache: Failed to fetch page $page: $e');
          break;
        }
      }

      _cachedExercises = exercises;
      _lastFetchTime = DateTime.now();
      _isAvailable = true;

      debugPrint('✅ WgerCache: Pre-fetch completed!');
      debugPrint('   Total exercises cached: ${_cachedExercises!.length}');
    } catch (e) {
      debugPrint('❌ WgerCache: Pre-fetch failed: $e');
      _isAvailable = false;
    } finally {
      _isFetching = false;
    }
  }

  /// Lấy exercises với filter (từ cache hoặc API)
  Future<List<WgerExercise>> getExercises({
    int? categoryId,
    int? muscleId,
  }) async {
    // If no filter and have cache, return cache
    if (categoryId == null && muscleId == null && hasCachedData) {
      debugPrint('📦 WgerCache: Returning cached exercises');
      return _cachedExercises!;
    }

    // If have filter, apply filter on cache first
    if (hasCachedData) {
      final filtered = _cachedExercises!.where((exercise) {
        // Note: WgerExercise doesn't have categoryId, only categoryName
        // So we can't filter by categoryId from cache
        // We'll need to fetch from API for category filtering
        
        if (muscleId != null) {
          final muscleIds = [
            ...exercise.muscles.map((m) => m.id),
            ...exercise.musclesSecondary.map((m) => m.id),
          ];
          if (!muscleIds.contains(muscleId)) {
            return false;
          }
        }
        return true;
      }).toList();

      // If filtering by muscle only and found results, return from cache
      if (categoryId == null && filtered.isNotEmpty) {
        debugPrint('📦 WgerCache: Returning ${filtered.length} filtered exercises from cache');
        return filtered;
      }
    }

    // If filtering by category or no cache, fetch from API
    debugPrint('🌐 WgerCache: Fetching from API with filters');
    final response = await _wgerService.fetchExercises(
      categoryId: categoryId,
      muscleId: muscleId,
    );
    return response.results;
  }

  /// Load more exercises (for pagination)
  Future<WgerExerciseListResponse> loadMoreExercises({
    required int page,
    int? categoryId,
    int? muscleId,
  }) async {
    return await _wgerService.fetchExercises(
      page: page,
      categoryId: categoryId,
      muscleId: muscleId,
    );
  }

  /// Check if cache is still valid
  bool _isCacheValid() {
    if (_lastFetchTime == null || _cachedExercises == null) {
      return false;
    }
    final elapsed = DateTime.now().difference(_lastFetchTime!);
    return elapsed < _cacheDuration;
  }

  /// Clear cache
  void clearCache() {
    debugPrint('🗑️ WgerCache: Clearing cache');
    _cachedExercises = null;
    _cachedCategories = null;
    _cachedMuscles = null;
    _cachedEquipment = null;
    _lastFetchTime = null;
    _isAvailable = false;
  }

  /// Refresh cache (force re-fetch)
  Future<void> refreshCache() async {
    clearCache();
    await preFetchData();
  }

  /// Dispose
  void dispose() {
    _wgerService.dispose();
  }
}
