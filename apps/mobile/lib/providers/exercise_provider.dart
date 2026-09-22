import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/exercise_model.dart';
import '../constants/firestore_collections.dart';
import '../services/exercise_cache_service.dart';
import '../services/local_exercise_service.dart';
import '../services/backend_api_service.dart';
import '../features/plans/plan_display.dart';
import '../utils/exercise_utils.dart';
import '../models/app_state_value.dart';
import '../models/planned_projection.dart';

class ExerciseProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;
  final ExerciseCacheService _cacheService = ExerciseCacheService();
  final LocalExerciseService _localService = LocalExerciseService();

  List<ExerciseModel> _todayExercises = [];
  // Planned Plan V2 projections are kept outside actual exercise observations.
  List<PlannedWorkoutProjection> _plannedExercises = [];
  bool _isLoading = false;
  bool _wgerLoaded = false;
  List<ExerciseTemplate>? _exerciseDatabaseCache;
  DataStatus _todayExercisesStatus = DataStatus.notLoaded;
  DateTime? _todayExercisesObservedAt;

  List<ExerciseModel> get todayExercises => _todayExercises;
  List<PlannedWorkoutProjection> get plannedExercises =>
      List.unmodifiable(_plannedExercises);
  bool get isLoading => _isLoading;
  DataStatus get todayExercisesStatus => _todayExercisesStatus;
  DateTime? get todayExercisesObservedAt => _todayExercisesObservedAt;

  @visibleForTesting
  void setTodayExercisesForTesting(List<ExerciseModel> exercises) {
    _todayExercises = List.from(exercises);
    notifyListeners();
  }

  double get totalCaloriesBurned => _todayExercises
      .where((ex) => ex.isCompleted)
      .fold(0.0, (acc, ex) => acc + ex.caloriesBurned);
  int get totalDuration => _todayExercises
      .where((ex) => ex.isCompleted)
      .fold(0, (acc, ex) => acc + ex.duration);
  double get plannedCaloriesBurned => _plannedExercises.isNotEmpty
      ? _plannedExercises.fold(0.0, (acc, ex) => acc + ex.caloriesBurned)
      : _todayExercises.fold(0.0, (acc, ex) => acc + ex.caloriesBurned);
  int get plannedDuration => _plannedExercises.isNotEmpty
      ? _plannedExercises.fold(0, (acc, ex) => acc + ex.duration)
      : _todayExercises.fold(0, (acc, ex) => acc + ex.duration);

  static bool _isSameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  /// Load wger exercises khi khởi động app
  Future<void> initWgerExercises() async {
    if (_wgerLoaded) return;
    await _localService.loadExercises();
    _wgerLoaded = _localService.isLoaded;
    _exerciseDatabaseCache = _wgerLoaded ? _buildExerciseDatabase() : null;
    notifyListeners();
  }

  Future<void> addExercise(ExerciseModel exercise) async {
    // Optimistic update - add to cache immediately
    if (_isSameDay(exercise.date, DateTime.now())) {
      final index =
          _todayExercises.indexWhere((item) => item.id == exercise.id);
      if (index == -1) {
        _todayExercises.add(exercise);
      } else {
        _todayExercises[index] = exercise;
      }
    }
    _cacheService.addExerciseToCache(exercise.userId, exercise.date, exercise);
    notifyListeners();

    // Save to Firestore in background
    try {
      await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .doc(exercise.id)
          .set(exercise.toMap());
      debugPrint('✅ Exercise saved to Firestore: ${exercise.name}');
    } catch (e) {
      debugPrint('❌ Error saving exercise to Firestore: $e');
      // Rollback on error
      _todayExercises.removeWhere((ex) => ex.id == exercise.id);
      _cacheService.removeExerciseFromCache(
          exercise.userId, exercise.date, exercise.id);
      notifyListeners();
      rethrow;
    }
  }

  /// Log a new actual workout observation without changing the Plan revision.
  Future<void> logPlannedWorkoutObservation(PlannedWorkoutProjection planned) {
    final now = DateTime.now();
    return addExercise(
      ExerciseModel(
        id: 'workout_observation_${now.microsecondsSinceEpoch}',
        userId: planned.userId,
        name: planned.name,
        date: now,
        duration: planned.duration,
        caloriesBurned: planned.caloriesBurned,
        type: planned.type,
        timeOfDay: planned.timeOfDay,
        isCompleted: true,
        sourcePlanId: planned.planId,
        sourceRevisionId: planned.revisionId,
        sourcePlanItemId: planned.planItemId,
      ),
    );
  }

  Future<void> loadTodayExercises(String userId) async {
    DateTime today = DateTime.now();
    DateTime startOfDay = DateTime(today.year, today.month, today.day);

    // Check cache first
    final cached = _cacheService.getCachedExercises(userId, today);
    if (cached != null) {
      debugPrint('📦 Using cached exercises for today');
      _todayExercises = List.of(cached);
      _todayExercisesStatus = DataStatus.stale;
      await _syncExercisesFromBackendPlan(userId, today);
      notifyListeners();

      // Pre-fetch nearby dates in background
      _preFetchNearbyDates(userId, today);
      return;
    }

    _isLoading = true;
    notifyListeners();

    try {
      debugPrint('🔄 Loading exercises for user: $userId');
      DateTime endOfDay = startOfDay.add(const Duration(days: 1));

      QuerySnapshot snapshot = await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .where('userId', isEqualTo: userId)
          .get();

      // Filter by date in memory instead of Firestore query
      final allExercises = snapshot.docs
          .map((doc) =>
              ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .toList(growable: false);
      _todayExercises = allExercises.where((exercise) {
        return !exercise.date.isBefore(startOfDay) &&
            exercise.date.isBefore(endOfDay);
      }).toList();
      await _syncExercisesFromBackendPlan(userId, today);
      _todayExercisesStatus = DataStatus.known;
      _todayExercisesObservedAt = DateTime.now();

      // Cache the result
      _cacheService.cacheExercises(userId, today, _todayExercises);

      // Cache all exercises for history
      _cacheService.cacheAllExercises(userId, allExercises);

      debugPrint('✅ Loaded ${_todayExercises.length} exercises from Firestore');

      // Pre-fetch nearby dates in background
      _preFetchNearbyDates(userId, today);
    } catch (e) {
      debugPrint('❌ Error loading exercises from Firestore: $e');
      _todayExercisesStatus = DataStatus.error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> refreshTodayExercisesAuthoritatively(String userId) async {
    final today = DateTime.now();
    final startOfDay = DateTime(today.year, today.month, today.day);
    final endOfDay = startOfDay.add(const Duration(days: 1));
    _isLoading = true;
    try {
      final snapshot = await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .where('userId', isEqualTo: userId)
          .get(const GetOptions(source: Source.server));
      final allExercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data()))
          .toList(growable: false);
      _todayExercises = allExercises.where((exercise) {
        return !exercise.date.isBefore(startOfDay) &&
            exercise.date.isBefore(endOfDay);
      }).toList();
      await _syncExercisesFromBackendPlan(userId, today);
      _cacheService.cacheExercises(userId, today, _todayExercises);
      _cacheService.cacheAllExercises(userId, allExercises);
      _todayExercisesStatus = DataStatus.known;
      _todayExercisesObservedAt = DateTime.now();
      return true;
    } catch (e) {
      _todayExercisesStatus = DataStatus.error;
      debugPrint('❌ Authoritative exercise read failed: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Pre-fetch exercises for nearby dates in background
  Future<void> _preFetchNearbyDates(String userId, DateTime centerDate) async {
    await _cacheService.preFetchNearbyDates(
      userId,
      centerDate,
      (date) async {
        return await loadExercisesForDate(userId, date);
      },
    );
  }

  String _slotToTimeOfDay(dynamic slot) {
    final s = slot?.toString().toLowerCase().trim() ?? '';
    if (s.contains('afternoon') || s.contains('chieu') || s.contains('trua')) {
      return 'afternoon';
    }
    if (s.contains('evening') || s.contains('toi')) return 'evening';
    if (s.contains('night') || s.contains('dem')) return 'night';
    return 'morning';
  }

  Future<void> _syncExercisesFromBackendPlan(
      String userId, DateTime date) async {
    _plannedExercises = [];
    try {
      final read =
          await BackendApiService().readAuthoritativeActivePlanV2('WORKOUT');
      if (read.status != ActivePlanStatus.activePlanFound ||
          read.plan == null) {
        return;
      }

      final plan = read.plan!;
      final day = PlanDisplay.dayForDate(plan, date);
      if (day == null) return;

      final items = PlanDisplay.items(day);
      final dateKey =
          '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
      bool changed = false;

      for (int idx = 0; idx < items.length; idx++) {
        final item = items[idx];
        final itemId = PlanDisplay.itemId(item).isNotEmpty
            ? PlanDisplay.itemId(item)
            : 'plan_ex_${dateKey}_$idx';

        final name = PlanDisplay.itemTitle(item, nutrition: false);
        final duration = (PlanDisplay.plannedDuration(item) ?? 30).round();
        final content = item['content'];
        final num? burnedCalNum = (item['calories_burned'] as num?) ??
            (content is Map ? content['calories_burned'] as num? : null) ??
            (item['estimated_calories'] as num?) ??
            (content is Map ? content['estimated_calories'] as num? : null);
        final double burned = burnedCalNum?.toDouble() ?? (duration * 6.0);
        final String exType = (item['type'] ??
                (content is Map ? content['type'] : null) ??
                'cardio')
            .toString()
            .toLowerCase();

        final timeOfDay = _slotToTimeOfDay(item['slot']);

        final plannedExercise = PlannedWorkoutProjection(
          planItemId: itemId,
          planId: plan['plan_id']?.toString() ?? '',
          revisionId: plan['revision_id']?.toString() ?? '',
          userId: userId,
          name: name,
          date: date,
          duration: duration,
          caloriesBurned: burned,
          type: exType,
          timeOfDay: timeOfDay,
        );
        _plannedExercises.add(plannedExercise);
        changed = true;
      }
      if (changed) {
        // Planned projections are deliberately not written to the actual
        // observation cache. PlanProvider/Plan screens read them from SQL.
      }
    } catch (e) {
      debugPrint('Plan V2 workout status read failed: $e');
    }
  }

  Future<void> deleteExercise(String exerciseId) async {
    // Find the exercise to get its date
    final index = _todayExercises.indexWhere((ex) => ex.id == exerciseId);
    if (index == -1) return;
    final exercise = _todayExercises[index];

    // Optimistic update - remove from cache immediately
    _todayExercises.removeWhere((ex) => ex.id == exerciseId);
    _cacheService.removeExerciseFromCache(
        exercise.userId, exercise.date, exerciseId);
    notifyListeners();

    // Delete from Firestore in background
    try {
      await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .doc(exerciseId)
          .delete();
      debugPrint('✅ Exercise deleted from Firestore: $exerciseId');
    } catch (e) {
      debugPrint('❌ Error deleting exercise: $e');
      // Rollback on error
      _todayExercises.add(exercise);
      _cacheService.addExerciseToCache(
          exercise.userId, exercise.date, exercise);
      notifyListeners();
      rethrow;
    }
  }

  // === CƠ SỞ DỮ LIỆU BÀI TẬP TỪ WGER ===

  /// Map wger category sang app type
  static String mapCategoryToType(String name, String categoryName) =>
      ExerciseUtils.mapToAppType(name, categoryName);

  /// Loại bỏ sạch các tag HTML thừa và khoảng trắng
  static String cleanHtml(String html) => ExerciseUtils.cleanHtml(html);

  /// Estimate MET value chính xác theo Compendium of Physical Activities chuẩn thể thao
  static double estimateMETForExercise(
          String name, String categoryName, int muscleCount) =>
      ExerciseUtils.estimateMet(name, categoryName, muscleCount);

  static double estimateCaloriesForExercise({
    required String name,
    required String categoryName,
    required int muscleCount,
    required double weightKg,
    required int durationMinutes,
  }) =>
      ExerciseUtils.calculateCalories(
        met: estimateMETForExercise(name, categoryName, muscleCount),
        weightKg: weightKg,
        durationMinutes: durationMinutes,
      );

  List<ExerciseTemplate> get exerciseDatabase {
    if (!_wgerLoaded || _localService.allExercises.isEmpty) {
      // Fallback: trả về hardcode database nếu wger chưa load
      return _fallbackDatabase;
    }

    return _exerciseDatabaseCache ??= _buildExerciseDatabase();
  }

  List<ExerciseTemplate> _buildExerciseDatabase() {
    return List.unmodifiable(_localService.allExercises.map((wger) {
      final type = mapCategoryToType(wger.name, wger.categoryName);
      final met = estimateMETForExercise(
          wger.name, wger.categoryName, wger.muscleCount);
      final rawDesc = cleanHtml(wger.description);
      final displayDesc = rawDesc.isNotEmpty
          ? (rawDesc.length > 100 ? '${rawDesc.substring(0, 100)}...' : rawDesc)
          : wger.categoryName;

      return ExerciseTemplate(
        id: 'wger_${wger.id}',
        name: wger.name,
        metValue: met,
        type: type,
        description: displayDesc,
      );
    }));
  }

  /// Fallback database khi wger chưa load
  static final List<ExerciseTemplate> _fallbackDatabase = [
    // Cardio
    ExerciseTemplate(
        id: 'e1',
        name: 'Đi bộ',
        metValue: 3.5,
        type: 'cardio',
        description: 'Đi bộ nhẹ nhàng 4-5 km/h'),
    ExerciseTemplate(
        id: 'e2',
        name: 'Đi bộ nhanh',
        metValue: 5.0,
        type: 'cardio',
        description: 'Đi bộ nhanh 6-7 km/h'),
    ExerciseTemplate(
        id: 'e3',
        name: 'Chạy bộ',
        metValue: 8.0,
        type: 'cardio',
        description: 'Chạy bộ vừa phải 8 km/h'),
    ExerciseTemplate(
        id: 'e4',
        name: 'Chạy nhanh',
        metValue: 11.5,
        type: 'cardio',
        description: 'Chạy nhanh 12 km/h'),
    ExerciseTemplate(
        id: 'e5',
        name: 'Đạp xe',
        metValue: 6.0,
        type: 'cardio',
        description: 'Đạp xe tốc độ vừa phải'),
    ExerciseTemplate(
        id: 'e6',
        name: 'Bơi lội',
        metValue: 7.0,
        type: 'cardio',
        description: 'Bơi tự do tốc độ vừa'),
    ExerciseTemplate(
        id: 'e7',
        name: 'Nhảy dây',
        metValue: 10.0,
        type: 'cardio',
        description: 'Nhảy dây cường độ vừa'),
    ExerciseTemplate(
        id: 'e8',
        name: 'Đi cầu thang',
        metValue: 8.0,
        type: 'cardio',
        description: 'Leo cầu thang'),

    // Strength
    ExerciseTemplate(
        id: 'e9',
        name: 'Tập tạ nhẹ',
        metValue: 3.5,
        type: 'strength',
        description: 'Tập tạ cường độ nhẹ'),
    ExerciseTemplate(
        id: 'e10',
        name: 'Tập tạ nặng',
        metValue: 6.0,
        type: 'strength',
        description: 'Tập tạ cường độ cao'),
    ExerciseTemplate(
        id: 'e11',
        name: 'Hít đất',
        metValue: 8.0,
        type: 'strength',
        description: 'Push-ups cường độ vừa'),
    ExerciseTemplate(
        id: 'e12',
        name: 'Squats',
        metValue: 5.0,
        type: 'strength',
        description: 'Squat không tạ'),
    ExerciseTemplate(
        id: 'e13',
        name: 'Plank',
        metValue: 3.5,
        type: 'strength',
        description: 'Giữ plank'),

    // Flexibility
    ExerciseTemplate(
        id: 'e14',
        name: 'Yoga',
        metValue: 3.0,
        type: 'flexibility',
        description: 'Yoga cơ bản'),
    ExerciseTemplate(
        id: 'e15',
        name: 'Stretching',
        metValue: 2.5,
        type: 'flexibility',
        description: 'Giãn cơ toàn thân'),
    ExerciseTemplate(
        id: 'e16',
        name: 'Pilates',
        metValue: 4.0,
        type: 'flexibility',
        description: 'Pilates cường độ vừa'),

    // Sports
    ExerciseTemplate(
        id: 'e17',
        name: 'Cầu lông',
        metValue: 5.5,
        type: 'sports',
        description: 'Chơi cầu lông'),
    ExerciseTemplate(
        id: 'e18',
        name: 'Bóng đá',
        metValue: 7.0,
        type: 'sports',
        description: 'Đá bóng'),
    ExerciseTemplate(
        id: 'e19',
        name: 'Bóng rổ',
        metValue: 6.5,
        type: 'sports',
        description: 'Chơi bóng rổ'),
    ExerciseTemplate(
        id: 'e20',
        name: 'Bóng bàn',
        metValue: 4.0,
        type: 'sports',
        description: 'Chơi bóng bàn'),
  ];

  List<ExerciseTemplate> getExercisesByType(String type) {
    return exerciseDatabase.where((e) => e.type == type).toList();
  }

  List<ExerciseTemplate> searchExercises(String query) {
    if (query.isEmpty) return exerciseDatabase;
    final normalizedQuery = ExerciseUtils.normalizeSearchText(query);
    return exerciseDatabase
        .where((e) =>
            ExerciseUtils.normalizeSearchText('${e.name} ${e.description}')
                .contains(normalizedQuery))
        .toList();
  }

  // Gợi ý bài tập dựa trên mục tiêu
  List<ExerciseTemplate> getSuggestedExercises(String healthGoal) {
    switch (healthGoal) {
      case 'lose_weight':
        return exerciseDatabase.where((e) => e.metValue >= 5.0).toList();
      case 'gain_muscle':
        return exerciseDatabase.where((e) => e.type == 'strength').toList();
      default:
        return exerciseDatabase.take(8).toList();
    }
  }

  // Toggle exercise completed status
  Future<void> toggleExerciseCompleted(String exerciseId) async {
    try {
      final index = _todayExercises.indexWhere((ex) => ex.id == exerciseId);
      if (index != -1) {
        final exercise = _todayExercises[index];
        final updated = exercise.copyWith(isCompleted: !exercise.isCompleted);

        // Optimistic update
        _todayExercises[index] = updated;
        _cacheService.updateExerciseInCache(
            exercise.userId, exercise.date, updated);
        notifyListeners();

        // Update Firestore in background
        await _firestore
            .collection(FirestoreCollections.exerciseDiary)
            .doc(exerciseId)
            .set(updated.toMap(), SetOptions(merge: true));

        // A plan item is immutable planned state. The diary write above is
        // the actual observation; it must never mutate the Plan revision.

        debugPrint(
            '✅ Exercise completed status updated: ${updated.isCompleted}');
      }
    } catch (e) {
      debugPrint('❌ Error toggling exercise completed: $e');
      // Rollback on error
      final index = _todayExercises.indexWhere((ex) => ex.id == exerciseId);
      if (index != -1) {
        final exercise = _todayExercises[index];
        final reverted = exercise.copyWith(isCompleted: !exercise.isCompleted);
        _todayExercises[index] = reverted;
        _cacheService.updateExerciseInCache(
            exercise.userId, exercise.date, reverted);
        notifyListeners();
      }
      rethrow;
    }
  }

  // Load exercises for a specific date range
  Future<List<ExerciseModel>> loadExercisesForDateRange(
    String userId,
    DateTime startDate,
    DateTime endDate,
  ) async {
    // Check if we have all exercises cached
    final allCached = _cacheService.getAllCachedExercises(userId);
    if (allCached != null) {
      debugPrint('📦 Using cached exercises for date range');
      final filtered = allCached.where((exercise) {
        return !exercise.date.isBefore(startDate) &&
            exercise.date.isBefore(endDate);
      }).toList();
      filtered.sort((a, b) => b.date.compareTo(a.date)); // Newest first
      return filtered;
    }

    try {
      QuerySnapshot snapshot = await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .where('userId', isEqualTo: userId)
          .get();

      final exercises = snapshot.docs
          .map((doc) =>
              ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .where((exercise) {
        return !exercise.date.isBefore(startDate) &&
            exercise.date.isBefore(endDate);
      }).toList();

      exercises.sort((a, b) => b.date.compareTo(a.date)); // Newest first

      // Cache all exercises for future use
      final allExercises = snapshot.docs
          .map((doc) =>
              ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .toList();
      _cacheService.cacheAllExercises(userId, allExercises);

      return exercises;
    } catch (e) {
      debugPrint('❌ Error loading exercises for date range: $e');
      return [];
    }
  }

  /// Read a range from Firestore's server source for an E4 recommendation.
  /// A cache result must never be presented to the backend as current history.
  Future<AuthoritativeExerciseHistory> loadExercisesForDateRangeAuthoritatively(
    String userId,
    DateTime startDate,
    DateTime endDate,
  ) async {
    try {
      final snapshot = await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .where('userId', isEqualTo: userId)
          .get(const GetOptions(source: Source.server));
      final exercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data()))
          .where((exercise) =>
              !exercise.date.isBefore(startDate) &&
              exercise.date.isBefore(endDate))
          .toList()
        ..sort((a, b) => b.date.compareTo(a.date));
      return AuthoritativeExerciseHistory.known(exercises, DateTime.now());
    } catch (error) {
      debugPrint('❌ E4 authoritative exercise-history read failed: $error');
      return const AuthoritativeExerciseHistory.error();
    }
  }

  // Get exercises for a specific date
  Future<List<ExerciseModel>> loadExercisesForDate(
      String userId, DateTime date) async {
    // Check cache first
    final cached = _cacheService.getCachedExercises(userId, date);
    if (cached != null) {
      debugPrint('📦 Using cached exercises for ${date.day}/${date.month}');
      return cached;
    }

    final startOfDay = DateTime(date.year, date.month, date.day);
    final endOfDay = startOfDay.add(const Duration(days: 1));
    final exercises =
        await loadExercisesForDateRange(userId, startOfDay, endOfDay);

    // Cache the result
    _cacheService.cacheExercises(userId, date, exercises);

    return exercises;
  }

  // Get completion stats
  int get completedCount =>
      _todayExercises.where((ex) => ex.isCompleted).length;
  int get pendingCount => _todayExercises.where((ex) => !ex.isCompleted).length;
  double get completionRate =>
      _todayExercises.isEmpty ? 0.0 : completedCount / _todayExercises.length;
}

class AuthoritativeExerciseHistory {
  final List<ExerciseModel> exercises;
  final DataStatus status;
  final DateTime? observedAt;

  const AuthoritativeExerciseHistory._(
      this.exercises, this.status, this.observedAt);

  factory AuthoritativeExerciseHistory.known(
          List<ExerciseModel> exercises, DateTime observedAt) =>
      AuthoritativeExerciseHistory._(exercises, DataStatus.known, observedAt);

  const AuthoritativeExerciseHistory.error()
      : exercises = const [],
        status = DataStatus.error,
        observedAt = null;
}
