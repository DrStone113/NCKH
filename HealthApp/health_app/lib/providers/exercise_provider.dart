import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/exercise_model.dart';
import '../constants/firestore_collections.dart';

class ExerciseProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;
  List<ExerciseModel> _todayExercises = [];

  List<ExerciseModel> get todayExercises => _todayExercises;
  double get totalCaloriesBurned => _todayExercises.fold(0, (sum, ex) => sum + ex.caloriesBurned);
  int get totalDuration => _todayExercises.fold(0, (sum, ex) => sum + ex.duration);

  Future<void> addExercise(ExerciseModel exercise) async {
    // Add to local list first for immediate UI update
    _todayExercises.add(exercise);
    notifyListeners();
    
    try {
      await _firestore.collection(FirestoreCollections.exerciseDiary).doc(exercise.id).set(exercise.toMap());
      debugPrint('✅ Exercise saved to Firestore: ${exercise.name}');
    } catch (e) {
      debugPrint('❌ Error saving exercise to Firestore: $e');
      // Keep in local list even if Firestore fails (offline support)
    }
  }

  Future<void> loadTodayExercises(String userId) async {
    try {
      debugPrint('🔄 Loading exercises for user: $userId');
      DateTime today = DateTime.now();
      DateTime startOfDay = DateTime(today.year, today.month, today.day);
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
      
      debugPrint('✅ Loaded ${_todayExercises.length} exercises from Firestore');
      notifyListeners();
    } catch (e) {
      debugPrint('❌ Error loading exercises from Firestore: $e');
      _todayExercises = [];
    }
  }

  Future<void> deleteExercise(String exerciseId) async {
    try {
      await _firestore.collection(FirestoreCollections.exerciseDiary).doc(exerciseId).delete();
      _todayExercises.removeWhere((ex) => ex.id == exerciseId);
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  // === CƠ SỞ DỮ LIỆU BÀI TẬP VỚI MET ===
  static final List<ExerciseTemplate> exerciseDatabase = [
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
}
