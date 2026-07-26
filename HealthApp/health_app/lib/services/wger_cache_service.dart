import 'package:flutter/foundation.dart';
import '../models/wger_models.dart';
import 'local_exercise_service.dart';

/// Service cache bài tập — load từ JSON local (offline, không cần API)
class WgerCacheService {
  static final WgerCacheService _instance = WgerCacheService._internal();
  factory WgerCacheService() => _instance;
  WgerCacheService._internal();

  final LocalExerciseService _local = LocalExerciseService();

  bool _isFetching = false;

  bool get isFetching => _isFetching;
  bool get hasCachedData => _local.isLoaded && _local.allExercises.isNotEmpty;

  List<WgerExercise> get cachedExercises => _local.allExercises;
  List<WgerExerciseCategory> get cachedCategories => _local.categories;
  List<WgerMuscle> get cachedMuscles => _local.muscles;
  List<WgerEquipment> get cachedEquipment => const [];

  /// Load data từ JSON local khi app khởi động
  Future<void> preFetchData() async {
    if (_isFetching || _local.isLoaded) return;
    _isFetching = true;
    debugPrint('🚀 WgerCache: Loading from local JSON...');
    try {
      await _local.loadExercises();
      debugPrint('✅ WgerCache: Loaded ${_local.allExercises.length} exercises');
      debugPrint('   Categories: ${_local.categories.length}');
      debugPrint('   Muscles: ${_local.muscles.length}');
    } catch (e) {
      debugPrint('❌ WgerCache: Load failed: $e');
    } finally {
      _isFetching = false;
    }
  }

  /// Lấy exercises với filter tuỳ chọn
  Future<List<WgerExercise>> getExercises({
    int? categoryId,
    int? muscleId,
    String? categoryName,
  }) async {
    if (!_local.isLoaded) await _local.loadExercises();

    var list = _local.allExercises;

    if (categoryName != null && categoryName.isNotEmpty) {
      list = _local.getByCategory(categoryName);
    } else if (muscleId != null) {
      list = _local.getByMuscle(muscleId);
    }

    return list;
  }

  /// Pagination — trả về WgerExerciseListResponse giả để tương thích với code cũ
  Future<WgerExerciseListResponse> loadMoreExercises({
    required int page,
    int? categoryId,
    int? muscleId,
    int pageSize = 20,
  }) async {
    if (!_local.isLoaded) await _local.loadExercises();

    var source = _local.allExercises;
    if (muscleId != null) source = _local.getByMuscle(muscleId);

    final pageItems = _local.getPage(source, page, pageSize: pageSize);
    return WgerExerciseListResponse(
      count: source.length,
      next: pageItems.length == pageSize ? 'has_more' : null,
      results: pageItems,
    );
  }

  /// Tìm kiếm theo tên
  List<WgerExercise> search(String query) => _local.search(query);

  void clearCache() => debugPrint('ℹ️ WgerCache: Local JSON cache không cần clear');
  Future<void> refreshCache() => preFetchData();
  void dispose() {}
}
