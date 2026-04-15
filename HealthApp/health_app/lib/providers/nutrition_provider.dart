import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/meal_model.dart';
import '../constants/firestore_collections.dart';

class NutritionProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;
  List<MealModel> _todayMeals = [];
  List<MealModel> _allMeals = []; // toàn bộ meals đã fetch 1 lần
  DateTime _selectedDate = DateTime.now();
  bool _allMealsLoaded = false;

  List<MealModel> get todayMeals => _todayMeals;
  DateTime get selectedDate => _selectedDate;
  bool get isToday {
    final now = DateTime.now();
    return _selectedDate.year == now.year && _selectedDate.month == now.month && _selectedDate.day == now.day;
  }

  double get totalCalories => _todayMeals.fold(0, (sum, m) => sum + m.calories);
  double get totalProtein => _todayMeals.fold(0, (sum, m) => sum + m.protein);
  double get totalCarbs => _todayMeals.fold(0, (sum, m) => sum + m.carbs);
  double get totalFat => _todayMeals.fold(0, (sum, m) => sum + m.fat);

  void _filterByDate(DateTime date) {
    _selectedDate = date;
    final start = DateTime(date.year, date.month, date.day);
    final end = start.add(const Duration(days: 1));
    _todayMeals = _allMeals.where((m) => m.date.isAfter(start) && m.date.isBefore(end)).toList();
    notifyListeners();
  }

  Future<void> addMeal(MealModel meal) async {
    _allMeals.add(meal);
    _filterByDate(_selectedDate);
    try {
      await _firestore.collection(FirestoreCollections.mealDiary).doc(meal.id).set(meal.toMap());
    } catch (e) {
      debugPrint('❌ Error saving meal: $e');
    }
  }

  // Fetch 1 lần duy nhất, sau đó filter local
  Future<void> loadTodayMeals(String userId) async {
    if (_allMealsLoaded) {
      _filterByDate(DateTime.now());
      return;
    }
    try {
      final snapshot = await _firestore
          .collection(FirestoreCollections.mealDiary)
          .where('userId', isEqualTo: userId)
          .get();
      _allMeals = snapshot.docs
          .map((doc) => MealModel.fromMap(doc.data() as Map<String, dynamic>))
          .toList();
      _allMealsLoaded = true;
      _filterByDate(DateTime.now());
    } catch (e) {
      debugPrint('❌ Error loading meals: $e');
      _todayMeals = [];
      notifyListeners();
    }
  }

  // Chuyển ngày - instant, không cần network
  Future<void> loadMealsForDate(String userId, DateTime date) async {
    if (_allMealsLoaded) {
      _filterByDate(date);
      return;
    }
    // Nếu chưa load thì fetch trước
    await loadTodayMeals(userId);
    _filterByDate(date);
  }

  Future<void> deleteMeal(String mealId) async {
    try {
      await _firestore.collection(FirestoreCollections.mealDiary).doc(mealId).delete();
      _allMeals.removeWhere((meal) => meal.id == mealId);
      _todayMeals.removeWhere((meal) => meal.id == mealId);
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  // === CƠ SỞ DỮ LIỆU THỰC PHẨM VIỆT NAM ===
  static final List<FoodItem> vietnameseFoodDatabase = [
    // Cơm & Tinh bột
    FoodItem(id: 'f1', name: 'Cơm trắng', caloriesPer100g: 130, proteinPer100g: 2.7, fatPer100g: 0.3, carbsPer100g: 28.2, category: 'Cơm & Tinh bột'),
    FoodItem(id: 'f2', name: 'Cơm gạo lứt', caloriesPer100g: 123, proteinPer100g: 2.7, fatPer100g: 1.0, carbsPer100g: 25.6, category: 'Cơm & Tinh bột'),
    FoodItem(id: 'f3', name: 'Phở bò', caloriesPer100g: 46, proteinPer100g: 3.5, fatPer100g: 0.8, carbsPer100g: 6.5, category: 'Cơm & Tinh bột'),
    FoodItem(id: 'f4', name: 'Bún', caloriesPer100g: 110, proteinPer100g: 3.2, fatPer100g: 0.2, carbsPer100g: 23.4, category: 'Cơm & Tinh bột'),
    FoodItem(id: 'f5', name: 'Bánh mì', caloriesPer100g: 265, proteinPer100g: 9.0, fatPer100g: 3.2, carbsPer100g: 49.0, category: 'Cơm & Tinh bột'),

    // Thịt
    FoodItem(id: 'f6', name: 'Thịt gà luộc', caloriesPer100g: 165, proteinPer100g: 31.0, fatPer100g: 3.6, carbsPer100g: 0, category: 'Thịt'),
    FoodItem(id: 'f7', name: 'Thịt bò nạc', caloriesPer100g: 250, proteinPer100g: 26.0, fatPer100g: 15.0, carbsPer100g: 0, category: 'Thịt'),
    FoodItem(id: 'f8', name: 'Thịt heo nạc', caloriesPer100g: 143, proteinPer100g: 26.0, fatPer100g: 3.5, carbsPer100g: 0, category: 'Thịt'),
    FoodItem(id: 'f9', name: 'Thịt vịt', caloriesPer100g: 337, proteinPer100g: 19.0, fatPer100g: 28.4, carbsPer100g: 0, category: 'Thịt'),

    // Hải sản
    FoodItem(id: 'f10', name: 'Cá hồi', caloriesPer100g: 208, proteinPer100g: 20.0, fatPer100g: 13.0, carbsPer100g: 0, category: 'Hải sản'),
    FoodItem(id: 'f11', name: 'Tôm', caloriesPer100g: 99, proteinPer100g: 24.0, fatPer100g: 0.3, carbsPer100g: 0.2, category: 'Hải sản'),
    FoodItem(id: 'f12', name: 'Cá ba sa', caloriesPer100g: 92, proteinPer100g: 15.0, fatPer100g: 3.0, carbsPer100g: 0, category: 'Hải sản'),

    // Rau củ
    FoodItem(id: 'f13', name: 'Rau muống', caloriesPer100g: 19, proteinPer100g: 2.6, fatPer100g: 0.2, carbsPer100g: 3.1, category: 'Rau củ'),
    FoodItem(id: 'f14', name: 'Rau cải', caloriesPer100g: 20, proteinPer100g: 2.0, fatPer100g: 0.3, carbsPer100g: 2.5, category: 'Rau củ'),
    FoodItem(id: 'f15', name: 'Cà rốt', caloriesPer100g: 41, proteinPer100g: 0.9, fatPer100g: 0.2, carbsPer100g: 9.6, category: 'Rau củ'),
    FoodItem(id: 'f16', name: 'Bí đỏ', caloriesPer100g: 26, proteinPer100g: 1.0, fatPer100g: 0.1, carbsPer100g: 6.5, category: 'Rau củ'),

    // Trứng sữa
    FoodItem(id: 'f17', name: 'Trứng gà luộc', caloriesPer100g: 155, proteinPer100g: 13.0, fatPer100g: 11.0, carbsPer100g: 1.1, category: 'Trứng & Sữa'),
    FoodItem(id: 'f18', name: 'Sữa tươi', caloriesPer100g: 61, proteinPer100g: 3.2, fatPer100g: 3.3, carbsPer100g: 4.8, category: 'Trứng & Sữa'),
    FoodItem(id: 'f19', name: 'Sữa chua', caloriesPer100g: 59, proteinPer100g: 3.5, fatPer100g: 0.4, carbsPer100g: 11.4, category: 'Trứng & Sữa'),

    // Đậu & Hạt
    FoodItem(id: 'f20', name: 'Đậu phụ', caloriesPer100g: 76, proteinPer100g: 8.0, fatPer100g: 4.8, carbsPer100g: 1.9, category: 'Đậu & Hạt'),
    FoodItem(id: 'f21', name: 'Đậu đen', caloriesPer100g: 132, proteinPer100g: 8.9, fatPer100g: 0.5, carbsPer100g: 23.7, category: 'Đậu & Hạt'),

    // Trái cây
    FoodItem(id: 'f22', name: 'Chuối', caloriesPer100g: 89, proteinPer100g: 1.1, fatPer100g: 0.3, carbsPer100g: 22.8, category: 'Trái cây'),
    FoodItem(id: 'f23', name: 'Cam', caloriesPer100g: 47, proteinPer100g: 0.9, fatPer100g: 0.1, carbsPer100g: 11.8, category: 'Trái cây'),
    FoodItem(id: 'f24', name: 'Táo', caloriesPer100g: 52, proteinPer100g: 0.3, fatPer100g: 0.2, carbsPer100g: 13.8, category: 'Trái cây'),
    FoodItem(id: 'f25', name: 'Dưa hấu', caloriesPer100g: 30, proteinPer100g: 0.6, fatPer100g: 0.2, carbsPer100g: 7.6, category: 'Trái cây'),

    // Món Việt phổ biến (estimated per serving, per 100g of dish)
    FoodItem(id: 'f26', name: 'Bún chả', caloriesPer100g: 150, proteinPer100g: 12.0, fatPer100g: 7.0, carbsPer100g: 12.0, category: 'Món Việt'),
    FoodItem(id: 'f27', name: 'Bánh cuốn', caloriesPer100g: 110, proteinPer100g: 5.0, fatPer100g: 2.5, carbsPer100g: 18.0, category: 'Món Việt'),
    FoodItem(id: 'f28', name: 'Gỏi cuốn', caloriesPer100g: 70, proteinPer100g: 5.0, fatPer100g: 0.8, carbsPer100g: 12.0, category: 'Món Việt'),
    FoodItem(id: 'f29', name: 'Canh chua', caloriesPer100g: 35, proteinPer100g: 3.0, fatPer100g: 0.5, carbsPer100g: 5.0, category: 'Món Việt'),
    FoodItem(id: 'f30', name: 'Cơm tấm sườn', caloriesPer100g: 180, proteinPer100g: 10.0, fatPer100g: 8.0, carbsPer100g: 18.0, category: 'Món Việt'),
  ];

  List<FoodItem> searchFoods(String query) {
    if (query.isEmpty) return vietnameseFoodDatabase;
    return vietnameseFoodDatabase
        .where((f) => f.name.toLowerCase().contains(query.toLowerCase()))
        .toList();
  }

  // Gợi ý bữa ăn dựa trên mục tiêu calories
  List<Map<String, dynamic>> getMealSuggestions(double targetCalories) {
    final suggestions = <Map<String, dynamic>>[];
    final breakfastCal = targetCalories * 0.3;
    final lunchCal = targetCalories * 0.4;
    final dinnerCal = targetCalories * 0.3;

    suggestions.add({
      'title': '🌅 Bữa sáng (~${breakfastCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Trứng gà luộc (2 quả) + Bánh mì',
        'Phở bò (1 tô)',
        'Cơm gạo lứt + Thịt gà luộc + Rau',
      ],
    });

    suggestions.add({
      'title': '☀️ Bữa trưa (~${lunchCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Cơm + Cá hồi + Rau muống xào',
        'Bún chả + Gỏi cuốn',
        'Cơm tấm sườn + Canh chua',
      ],
    });

    suggestions.add({
      'title': '🌙 Bữa tối (~${dinnerCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Cơm gạo lứt + Tôm + Rau cải',
        'Bánh cuốn + Canh rau',
        'Đậu phụ sốt cà + Rau luộc',
      ],
    });

    return suggestions;
  }
}
