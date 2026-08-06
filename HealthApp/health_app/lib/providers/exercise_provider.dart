import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/exercise_model.dart';
import '../constants/firestore_collections.dart';
import '../services/exercise_cache_service.dart';
import '../services/local_exercise_service.dart';

class ExerciseProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;
  final ExerciseCacheService _cacheService = ExerciseCacheService();
  final LocalExerciseService _localService = LocalExerciseService();
  
  List<ExerciseModel> _todayExercises = [];
  bool _isLoading = false;
  bool _wgerLoaded = false;

  List<ExerciseModel> get todayExercises => _todayExercises;
  bool get isLoading => _isLoading;
  double get totalCaloriesBurned => _todayExercises.fold(0, (acc, ex) => acc + ex.caloriesBurned);
  int get totalDuration => _todayExercises.fold(0, (acc, ex) => acc + ex.duration);

  /// Load wger exercises khi khởi động app
  Future<void> initWgerExercises() async {
    if (_wgerLoaded) return;
    await _localService.loadExercises();
    _wgerLoaded = true;
    notifyListeners();
  }

  Future<void> addExercise(ExerciseModel exercise) async {
    // Optimistic update - add to cache immediately
    _todayExercises.add(exercise);
    _cacheService.addExerciseToCache(exercise.userId, exercise.date, exercise);
    notifyListeners();
    
    // Save to Firestore in background
    try {
      await _firestore.collection(FirestoreCollections.exerciseDiary).doc(exercise.id).set(exercise.toMap());
      debugPrint('✅ Exercise saved to Firestore: ${exercise.name}');
    } catch (e) {
      debugPrint('❌ Error saving exercise to Firestore: $e');
      // Rollback on error
      _todayExercises.removeWhere((ex) => ex.id == exercise.id);
      _cacheService.removeExerciseFromCache(exercise.userId, exercise.date, exercise.id);
      notifyListeners();
      rethrow;
    }
  }

  Future<void> loadTodayExercises(String userId) async {
    DateTime today = DateTime.now();
    DateTime startOfDay = DateTime(today.year, today.month, today.day);
    
    // Check cache first
    final cached = _cacheService.getCachedExercises(userId, today);
    if (cached != null) {
      debugPrint('📦 Using cached exercises for today');
      _todayExercises = cached;
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
      _todayExercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .where((exercise) {
            return exercise.date.isAfter(startOfDay) && exercise.date.isBefore(endOfDay);
          })
          .toList();
      
      // Cache the result
      _cacheService.cacheExercises(userId, today, _todayExercises);
      
      // Cache all exercises for history
      final allExercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .toList();
      _cacheService.cacheAllExercises(userId, allExercises);
      
      debugPrint('✅ Loaded ${_todayExercises.length} exercises from Firestore');
      
      // Pre-fetch nearby dates in background
      _preFetchNearbyDates(userId, today);
    } catch (e) {
      debugPrint('❌ Error loading exercises from Firestore: $e');
      _todayExercises = [];
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

  Future<void> deleteExercise(String exerciseId) async {
    // Find the exercise to get its date
    final exercise = _todayExercises.firstWhere((ex) => ex.id == exerciseId);
    
    // Optimistic update - remove from cache immediately
    _todayExercises.removeWhere((ex) => ex.id == exerciseId);
    _cacheService.removeExerciseFromCache(exercise.userId, exercise.date, exerciseId);
    notifyListeners();
    
    // Delete from Firestore in background
    try {
      await _firestore.collection(FirestoreCollections.exerciseDiary).doc(exerciseId).delete();
      debugPrint('✅ Exercise deleted from Firestore: $exerciseId');
    } catch (e) {
      debugPrint('❌ Error deleting exercise: $e');
      // Rollback on error
      _todayExercises.add(exercise);
      _cacheService.addExerciseToCache(exercise.userId, exercise.date, exercise);
      notifyListeners();
      rethrow;
    }
  }

  // === CƠ SỞ DỮ LIỆU BÀI TẬP TỪ WGER ===
  
  /// Map wger category sang app type
  String _mapCategoryToType(String categoryName) {
    final cat = categoryName.toLowerCase();
    if (cat.contains('cardio') || cat.contains('running') || cat.contains('cycling')) {
      return 'cardio';
    }
    if (cat.contains('strength') || cat.contains('barbell') || cat.contains('dumbbell') || 
        cat.contains('arms') || cat.contains('legs') || cat.contains('chest') || 
        cat.contains('back') || cat.contains('shoulders')) {
      return 'strength';
    }
    if (cat.contains('stretch') || cat.contains('flexibility') || cat.contains('yoga')) {
      return 'flexibility';
    }
    return 'sports'; // default
  }

  /// Estimate MET value dựa trên category và muscles
  double _estimateMET(String categoryName, int muscleCount) {
    final cat = categoryName.toLowerCase();
    // Cardio: MET cao
    if (cat.contains('cardio') || cat.contains('running')) return 8.0;
    if (cat.contains('cycling')) return 6.0;
    // Strength: MET trung bình, tăng theo số nhóm cơ
    if (cat.contains('strength') || cat.contains('barbell') || cat.contains('dumbbell')) {
      return 5.0 + (muscleCount * 0.5).clamp(0, 3.0);
    }
    // Flexibility: MET thấp
    if (cat.contains('stretch') || cat.contains('flexibility')) return 2.5;
    // Default
    return 4.0;
  }

  List<ExerciseTemplate> get exerciseDatabase {
    if (!_wgerLoaded || _localService.allExercises.isEmpty) {
      // Fallback: trả về hardcode database nếu wger chưa load
      return _fallbackDatabase;
    }

    // Convert wger exercises sang ExerciseTemplate
    return _localService.allExercises.map((wger) {
      final type = _mapCategoryToType(wger.categoryName);
      final met = _estimateMET(wger.categoryName, wger.muscles.length);
      
      return ExerciseTemplate(
        id: 'wger_${wger.id}',
        name: wger.name,
        metValue: met,
        type: type,
        description: wger.description.isNotEmpty 
            ? wger.description.substring(0, wger.description.length > 100 ? 100 : wger.description.length)
            : wger.categoryName,
      );
    }).toList();
  }

  /// Fallback database khi wger chưa load
  static final List<ExerciseTemplate> _fallbackDatabase = [
    // Cardio
    ExerciseTemplate(id: 'e1', name: 'Đi bộ', metValue: 3.5, type: 'cardio', description: 'Đi bộ nhẹ nhàng 4-5 km/h'),
    ExerciseTemplate(id: 'e2', name: 'Đi bộ nhanh', metValue: 5.0, type: 'cardio', description: 'Đi bộ nhanh 6-7 km/h'),
    ExerciseTemplate(id: 'e3', name: 'Chạy bộ', metValue: 8.0, type: 'cardio', description: 'Chạy bộ vừa phải 8 km/h'),
    ExerciseTemplate(id: 'e4', name: 'Chạy nhanh', metValue: 11.5, type: 'cardio', description: 'Chạy nhanh 12 km/h'),
    ExerciseTemplate(id: 'e5', name: 'Đạp xe', metValue: 6.0, type: 'cardio', description: 'Đạp xe tốc độ vừa phải'),
    ExerciseTemplate(id: 'e6', name: 'Bơi lội', metValue: 7.0, type: 'cardio', description: 'Bơi tự do tốc độ vừa'),
    ExerciseTemplate(id: 'e7', name: 'Nhảy dây', metValue: 10.0, type: 'cardio', description: 'Nhảy dây cường độ vừa'),
    ExerciseTemplate(id: 'e8', name: 'Đi cầu thang', metValue: 8.0, type: 'cardio', description: 'Leo cầu thang'),

    // Strength
    ExerciseTemplate(id: 'e9', name: 'Tập tạ nhẹ', metValue: 3.5, type: 'strength', description: 'Tập tạ cường độ nhẹ'),
    ExerciseTemplate(id: 'e10', name: 'Tập tạ nặng', metValue: 6.0, type: 'strength', description: 'Tập tạ cường độ cao'),
    ExerciseTemplate(id: 'e11', name: 'Hít đất', metValue: 8.0, type: 'strength', description: 'Push-ups cường độ vừa'),
    ExerciseTemplate(id: 'e12', name: 'Squats', metValue: 5.0, type: 'strength', description: 'Squat không tạ'),
    ExerciseTemplate(id: 'e13', name: 'Plank', metValue: 3.5, type: 'strength', description: 'Giữ plank'),

    // Flexibility
    ExerciseTemplate(id: 'e14', name: 'Yoga', metValue: 3.0, type: 'flexibility', description: 'Yoga cơ bản'),
    ExerciseTemplate(id: 'e15', name: 'Stretching', metValue: 2.5, type: 'flexibility', description: 'Giãn cơ toàn thân'),
    ExerciseTemplate(id: 'e16', name: 'Pilates', metValue: 4.0, type: 'flexibility', description: 'Pilates cường độ vừa'),

    // Sports
    ExerciseTemplate(id: 'e17', name: 'Cầu lông', metValue: 5.5, type: 'sports', description: 'Chơi cầu lông'),
    ExerciseTemplate(id: 'e18', name: 'Bóng đá', metValue: 7.0, type: 'sports', description: 'Đá bóng'),
    ExerciseTemplate(id: 'e19', name: 'Bóng rổ', metValue: 6.5, type: 'sports', description: 'Chơi bóng rổ'),
    ExerciseTemplate(id: 'e20', name: 'Bóng bàn', metValue: 4.0, type: 'sports', description: 'Chơi bóng bàn'),
  ];

  List<ExerciseTemplate> getExercisesByType(String type) {
    return exerciseDatabase.where((e) => e.type == type).toList();
  }

  List<ExerciseTemplate> searchExercises(String query) {
    if (query.isEmpty) return exerciseDatabase;
    return exerciseDatabase
        .where((e) => e.name.toLowerCase().contains(query.toLowerCase()))
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
        _cacheService.updateExerciseInCache(exercise.userId, exercise.date, updated);
        notifyListeners();
        
        // Update Firestore in background
        await _firestore
            .collection(FirestoreCollections.exerciseDiary)
            .doc(exerciseId)
            .update({'isCompleted': updated.isCompleted});
        
        debugPrint('✅ Exercise completed status updated: ${updated.isCompleted}');
      }
    } catch (e) {
      debugPrint('❌ Error toggling exercise completed: $e');
      // Rollback on error
      final index = _todayExercises.indexWhere((ex) => ex.id == exerciseId);
      if (index != -1) {
        final exercise = _todayExercises[index];
        final reverted = exercise.copyWith(isCompleted: !exercise.isCompleted);
        _todayExercises[index] = reverted;
        _cacheService.updateExerciseInCache(exercise.userId, exercise.date, reverted);
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
      final filtered = allCached
          .where((exercise) {
            return exercise.date.isAfter(startDate) && exercise.date.isBefore(endDate);
          })
          .toList();
      filtered.sort((a, b) => b.date.compareTo(a.date)); // Newest first
      return filtered;
    }

    try {
      QuerySnapshot snapshot = await _firestore
          .collection(FirestoreCollections.exerciseDiary)
          .where('userId', isEqualTo: userId)
          .get();

      final exercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .where((exercise) {
            return exercise.date.isAfter(startDate) && exercise.date.isBefore(endDate);
          })
          .toList();
      
      exercises.sort((a, b) => b.date.compareTo(a.date)); // Newest first
      
      // Cache all exercises for future use
      final allExercises = snapshot.docs
          .map((doc) => ExerciseModel.fromMap(doc.data() as Map<String, dynamic>))
          .toList();
      _cacheService.cacheAllExercises(userId, allExercises);
      
      return exercises;
    } catch (e) {
      debugPrint('❌ Error loading exercises for date range: $e');
      return [];
    }
  }

  // Get exercises for a specific date
  Future<List<ExerciseModel>> loadExercisesForDate(String userId, DateTime date) async {
    // Check cache first
    final cached = _cacheService.getCachedExercises(userId, date);
    if (cached != null) {
      debugPrint('📦 Using cached exercises for ${date.day}/${date.month}');
      return cached;
    }

    final startOfDay = DateTime(date.year, date.month, date.day);
    final endOfDay = startOfDay.add(const Duration(days: 1));
    final exercises = await loadExercisesForDateRange(userId, startOfDay, endOfDay);
    
    // Cache the result
    _cacheService.cacheExercises(userId, date, exercises);
    
    return exercises;
  }

  // Get completion stats
  int get completedCount => _todayExercises.where((ex) => ex.isCompleted).length;
  int get pendingCount => _todayExercises.where((ex) => !ex.isCompleted).length;
  double get completionRate => _todayExercises.isEmpty 
      ? 0.0 
      : completedCount / _todayExercises.length;
}
