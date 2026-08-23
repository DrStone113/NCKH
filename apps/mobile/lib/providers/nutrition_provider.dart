import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../models/meal_model.dart';
import '../constants/firestore_collections.dart';
import '../services/nutrition_cache_service.dart';
import '../services/backend_api_service.dart';
import '../models/app_state_value.dart';
import '../models/canonical_nutrition.dart';
import '../services/meal_diary_store.dart';

class NutritionProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;
  final NutritionCacheService _cacheService = NutritionCacheService();
  final MealDiaryStore _mealStore;

  NutritionProvider({MealDiaryStore? mealStore})
      : _mealStore = mealStore ?? FirestoreMealDiaryStore();

  List<MealModel> _todayMeals = [];
  List<MealModel> _allMeals = [];
  DateTime _selectedDate = DateTime.now();
  bool _allMealsLoaded = false;
  bool _isLoading = false;
  DataStatus _todayMealsStatus = DataStatus.notLoaded;
  DateTime? _todayMealsObservedAt;
  ActivePlanStatus _activePlanReadStatus = ActivePlanStatus.readError;

  List<MealModel> get todayMeals => _todayMeals;
  DateTime get selectedDate => _selectedDate;
  bool get isLoading => _isLoading;
  DataStatus get todayMealsStatus => _todayMealsStatus;
  DateTime? get todayMealsObservedAt => _todayMealsObservedAt;
  ActivePlanStatus get activePlanReadStatus => _activePlanReadStatus;
  bool get isToday {
    final now = DateTime.now();
    return _selectedDate.year == now.year &&
        _selectedDate.month == now.month &&
        _selectedDate.day == now.day;
  }

  List<Map<String, dynamic>> _vietnameseDishes = [];
  List<FoodItem> _vietnameseFoods = [];
  Future<void>? _vietnameseDatabaseLoad;

  List<Map<String, dynamic>> get vietnameseDishes => _vietnameseDishes;
  List<FoodItem> get vietnameseFoods =>
      _vietnameseFoods.isNotEmpty ? _vietnameseFoods : vietnameseFoodDatabase;

  Set<String> _deletedPlanItemIds = {};

  Future<void> _loadDeletedPlanItemIds(String userId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final list =
          prefs.getStringList('nutrition_deleted_plan_items_$userId') ?? [];
      _deletedPlanItemIds = list.toSet();
    } catch (_) {}
  }

  Future<void> _saveDeletedPlanItemIds(String userId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList(
        'nutrition_deleted_plan_items_$userId',
        _deletedPlanItemIds.toList(),
      );
    } catch (_) {}
  }

  /// Tổng calo & macro của các bữa ăn ĐÃ ĂN (isCompleted == true)
  double get consumedCalories =>
      _todayMeals.where((m) => m.isCompleted).fold(0.0, (acc, m) => acc + m.calories);
  double get consumedProtein =>
      _todayMeals.where((m) => m.isCompleted).fold(0.0, (acc, m) => acc + m.protein);
  double get consumedCarbs =>
      _todayMeals.where((m) => m.isCompleted).fold(0.0, (acc, m) => acc + m.carbs);
  double get consumedFat =>
      _todayMeals.where((m) => m.isCompleted).fold(0.0, (acc, m) => acc + m.fat);

  DailyNutritionSummary canonicalDailySummary(
      CanonicalNutritionState canonical) {
    final inputStatus = switch (_todayMealsStatus) {
      DataStatus.known => NutritionInputStatus.known,
      DataStatus.missing => NutritionInputStatus.missing,
      DataStatus.notLoaded => NutritionInputStatus.notLoaded,
      DataStatus.stale => NutritionInputStatus.stale,
      DataStatus.error => NutritionInputStatus.error,
      DataStatus.conflict => NutritionInputStatus.conflict,
    };
    final meals = _todayMeals
        .map((meal) => ConsumedMealNutrition(
              energyKcal: meal.calories,
              proteinGrams: meal.protein,
              carbohydrateGrams: meal.carbs,
              fatGrams: meal.fat,
              recordStatus: meal.isCompleted ? 'CONSUMED' : 'PLANNED',
            ))
        .toList(growable: false);
    return summarizeDailyNutrition(
      CanonicalNutritionValue<List<ConsumedMealNutrition>>(
        value: inputStatus == NutritionInputStatus.known ? meals : null,
        source: 'nutrition_provider.today_meals',
        status: inputStatus,
      ),
      canonical,
    );
  }

  /// Tổng calo & macro dự kiến trong kế hoạch / thực đơn cả ngày (bất kể đã ăn hay chưa)
  double get plannedCalories =>
      _todayMeals.fold(0.0, (acc, m) => acc + m.calories);
  double get plannedProtein =>
      _todayMeals.fold(0.0, (acc, m) => acc + m.protein);
  double get plannedCarbs =>
      _todayMeals.fold(0.0, (acc, m) => acc + m.carbs);
  double get plannedFat =>
      _todayMeals.fold(0.0, (acc, m) => acc + m.fat);

  /// Giữ totalCalories làm alias cho plannedCalories
  double get totalCalories => plannedCalories;
  double get totalProtein => plannedProtein;
  double get totalCarbs => plannedCarbs;
  double get totalFat => plannedFat;

  /// Nạp danh mục món ăn & thực phẩm chuẩn từ backend API
  Future<void> loadVietnameseDatabase() {
    if (_vietnameseDishes.isNotEmpty && _vietnameseFoods.isNotEmpty) {
      return Future.value();
    }
    return _vietnameseDatabaseLoad ??= _loadVietnameseDatabase().whenComplete(
      () => _vietnameseDatabaseLoad = null,
    );
  }

  Future<void> _loadVietnameseDatabase() async {
    try {
      final dishes = await BackendApiService().getVietnameseDishes();
      if (dishes.isNotEmpty) {
        _vietnameseDishes = dishes;
      }
    } catch (e) {
      debugPrint('⚠️ Error loading vietnamese dishes: $e');
    }

    try {
      final rawFoods = await BackendApiService().getVietnameseFoods();
      if (rawFoods.isNotEmpty) {
        _vietnameseFoods = rawFoods.map((f) {
          final id = f['ma_so']?.toString() ??
              f['stt']?.toString() ??
              'vn_${f['name']}';
          final name = f['name']?.toString() ?? '';
          final cal = (f['energy_kcal'] as num?)?.toDouble() ?? 0.0;
          final pro = (f['protein'] as num?)?.toDouble() ?? 0.0;
          final fat = (f['fat'] as num?)?.toDouble() ?? 0.0;
          final carbs = (f['carbohydrates'] as num?)?.toDouble() ?? 0.0;
          final cat = f['category']?.toString() ?? 'Thực phẩm';
          return FoodItem(
            id: id,
            name: name,
            caloriesPer100g: cal,
            proteinPer100g: pro,
            fatPer100g: fat,
            carbsPer100g: carbs,
            category: cat,
          );
        }).toList();
      }
    } catch (e) {
      debugPrint('⚠️ Error loading vietnamese foods: $e');
    }
    notifyListeners();
  }

  Map<String, dynamic>? findVietnameseDish(String name) {
    final normalized = name.trim().toLowerCase();
    if (normalized.isEmpty) return null;
    for (final dish in _vietnameseDishes) {
      if (dish['name']?.toString().trim().toLowerCase() == normalized) {
        return dish;
      }
    }
    return null;
  }

  void _filterByDate(DateTime date) {
    _selectedDate = date;
    final start = DateTime(date.year, date.month, date.day);
    final end = start.add(const Duration(days: 1));
    _todayMeals = _allMeals
        .where((m) => !m.date.isBefore(start) && m.date.isBefore(end))
        .toList();
    notifyListeners();
  }

  /// Đọc bữa ăn trong một khoảng ngày mà KHÔNG đụng vào state hiển thị.
  ///
  /// Dùng cho chatbot khi nó gọi tool `get_meal_log_range`. Không thể dùng
  /// `loadMealsForDate` cho việc này: hàm đó đặt lại `_selectedDate` và
  /// `_todayMeals`, nên một câu hỏi kiểu "tuần rồi mình ăn thế nào" sẽ làm
  /// nhảy luôn ngày đang xem trên màn hình Dinh dưỡng.
  Future<List<MealModel>> getMealsInRange(
    String userId,
    DateTime from,
    DateTime to,
  ) async {
    if (!_allMealsLoaded) {
      await loadTodayMeals(userId);
    }
    final start = DateTime(from.year, from.month, from.day);
    final end =
        DateTime(to.year, to.month, to.day).add(const Duration(days: 1));
    final result = _allMeals
        .where((m) => !m.date.isBefore(start) && m.date.isBefore(end))
        .toList();
    result.sort((a, b) => a.date.compareTo(b.date));
    return result;
  }

  Future<WriteResult<MealModel>> addMeal(
    MealModel meal, {
    bool replacePendingSlot = true,
  }) async {
    final normType = MealTypeUtils.normalize(meal.mealType);
    final List<MealModel> pendingToRemove = [];
    if (replacePendingSlot && normType != 'phu') {
      final start = DateTime(meal.date.year, meal.date.month, meal.date.day);
      final end = start.add(const Duration(days: 1));
      pendingToRemove.addAll(_allMeals.where((m) {
        final isSameDate = !m.date.isBefore(start) && m.date.isBefore(end);
        final isSameType = MealTypeUtils.normalize(m.mealType) == normType;
        return isSameDate && isSameType && !m.isCompleted && m.id != meal.id;
      }));

      for (final old in pendingToRemove) {
        _allMeals.removeWhere((m) => m.id == old.id);
        _todayMeals.removeWhere((m) => m.id == old.id);
        _cacheService.removeMealFromCache(old.userId, old.date, old.id);
      }
    }

    final previousAtSameId = _allMeals.where((m) => m.id == meal.id).toList();
    _allMeals.removeWhere((m) => m.id == meal.id);
    _allMeals.add(meal);
    _filterByDate(_selectedDate);
    _cacheService.addMealToCache(meal.userId, meal.date, meal);

    try {
      await _mealStore.save(meal);
      final persisted = await _mealStore.read(meal.id);
      if (persisted == null ||
          persisted.userId != meal.userId ||
          persisted.name != meal.name ||
          persisted.mealType != meal.mealType ||
          persisted.date.toUtc() != meal.date.toUtc() ||
          persisted.items.length != meal.items.length ||
          (persisted.calories - meal.calories).abs() > 0.01 ||
          persisted.isCompleted != meal.isCompleted) {
        throw StateError('MEAL_PERSISTENCE_VERIFICATION_FAILED');
      }
      for (final old in pendingToRemove) {
        await _mealStore.delete(old.id);
      }
      for (final old in pendingToRemove) {
        _deletedPlanItemIds.add(old.id);
        await _saveDeletedPlanItemIds(old.userId);
      }
      _todayMealsStatus = DataStatus.known;
      _todayMealsObservedAt = DateTime.now();
      debugPrint('✅ Meal saved to Firestore: ${meal.id}');
      return WriteResult.persisted(persisted);
    } catch (e) {
      try {
        await _mealStore.delete(meal.id);
      } catch (_) {}
      _allMeals.removeWhere((m) => m.id == meal.id);
      _allMeals.addAll(previousAtSameId);
      _allMeals.addAll(pendingToRemove);
      _filterByDate(_selectedDate);
      _cacheService.removeMealFromCache(meal.userId, meal.date, meal.id);
      for (final previous in [...previousAtSameId, ...pendingToRemove]) {
        _cacheService.addMealToCache(
          previous.userId,
          previous.date,
          previous,
        );
      }
      _todayMealsStatus = DataStatus.error;
      debugPrint('❌ Meal persistence failed: $e');
      return const WriteResult.error('MEAL_PERSISTENCE_ERROR');
    }
  }

  Future<void> replaceMeal(String oldMealId, MealModel newMeal) async {
    await deleteMeal(oldMealId);
    await addMeal(newMeal, replacePendingSlot: false);
  }

  String _mapMealType(String raw) {
    return MealTypeUtils.normalize(raw);
  }

  Future<void> _syncMealsFromBackendPlan(String userId, DateTime date) async {
    try {
      await _loadDeletedPlanItemIds(userId);
      final read = await BackendApiService().readActivePlanDetail(userId);
      _activePlanReadStatus = read.status;
      final detail = read.plan;
      if (read.status != ActivePlanStatus.activePlanFound || detail == null) {
        return;
      }
      final items = detail['items'] as List<dynamic>? ?? [];
      final dateStr =
          '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

      for (final item in items) {
        if (item is! Map<String, dynamic>) continue;
        if (item['item_type'] != 'meal') continue;
        final planDate = item['plan_date']?.toString();
        if (planDate != null && planDate != dateStr) continue;

        final planItemId = item['id']?.toString() ?? '';
        if (planItemId.isEmpty) continue;
        if (_deletedPlanItemIds.contains(planItemId)) continue;

        final payload = item['payload'] as Map<String, dynamic>? ?? {};
        final mealTypeRaw = payload['meal_type']?.toString() ?? 'lunch';
        final mealType = _mapMealType(mealTypeRaw);

        final existingIdx = _allMeals.indexWhere((m) => m.id == planItemId);
        if (existingIdx == -1) {
          final start = DateTime(date.year, date.month, date.day);
          final end = start.add(const Duration(days: 1));
          final hasSlotMeal = _allMeals.any((m) {
            final isSameDate = !m.date.isBefore(start) && m.date.isBefore(end);
            final isSameType = MealTypeUtils.normalize(m.mealType) == mealType;
            return isSameDate && isSameType && m.id != planItemId;
          });
          if (hasSlotMeal) continue;
        }

        final title = item['title']?.toString() ?? 'Món ăn';
        final targetKcal = (item['target_kcal'] as num?)?.toDouble() ?? 0.0;
        final targetProtein =
            (item['target_protein'] as num?)?.toDouble() ?? 0.0;
        final isCompleted = item['completed'] == true;
        final components = (payload['components'] as List<dynamic>?) ?? [];

        List<MealItem> mealItems = [];
        if (components.isNotEmpty) {
          for (final comp in components) {
            if (comp is Map<String, dynamic>) {
              final compName = comp['name']?.toString() ?? 'Thành phần';
              final compGrams =
                  (comp['serving_grams'] as num?)?.toDouble() ?? 100.0;
              final compCal = (comp['calories'] as num?)?.toDouble() ?? 0.0;
              final compPro = (comp['protein'] as num?)?.toDouble() ?? 0.0;
              final compCarbs = (comp['carbs'] as num?)?.toDouble() ?? 0.0;
              final compFat = (comp['fat'] as num?)?.toDouble() ?? 0.0;

              mealItems.add(MealItem(
                id: '${planItemId}_$compName',
                foodId: '',
                name: compName,
                weightGrams: compGrams,
                calories: compCal,
                protein: compPro,
                carbs: compCarbs,
                fat: compFat,
              ));
            }
          }
        } else {
          mealItems.add(MealItem(
            id: '${planItemId}_item',
            foodId: '',
            name: title,
            weightGrams: 100.0,
            calories: targetKcal,
            protein: targetProtein,
            carbs: 0.0,
            fat: 0.0,
          ));
        }

        final planMeal = MealModel(
          id: planItemId,
          userId: userId,
          name: title,
          date: date,
          mealType: mealType,
          items: mealItems,
          isCompleted: isCompleted,
        );

        if (existingIdx != -1) {
          _allMeals[existingIdx] = planMeal;
        } else {
          _allMeals.add(planMeal);
        }
      }
    } catch (e) {
      _activePlanReadStatus = ActivePlanStatus.readError;
      debugPrint('⚠️ Sync meals from backend plan error: $e');
    }
  }

  Future<void> loadTodayMeals(String userId) async {
    _isLoading = true;
    notifyListeners();

    try {
      _allMeals = await _mealStore.readForUser(userId);
      _todayMealsStatus = DataStatus.known;
      _todayMealsObservedAt = DateTime.now();
    } catch (e) {
      debugPrint('⚠️ Firestore load error (offline/web): $e');
      _todayMealsStatus = DataStatus.error;
    }

    await _syncMealsFromBackendPlan(userId, DateTime.now());
    _allMealsLoaded = true;
    _filterByDate(DateTime.now());
    _cacheService.cacheMeals(userId, DateTime.now(), _todayMeals);
    _isLoading = false;
    notifyListeners();
  }

  /// Force a server-backed read for chatbot tools. A cached echo is never
  /// labelled as fresh by this method.
  Future<bool> refreshTodayMealsAuthoritatively(
    String userId, {
    bool includeActivePlan = true,
  }) async {
    _isLoading = true;
    try {
      _allMeals = await _mealStore.readForUser(userId);
      if (includeActivePlan) {
        await _syncMealsFromBackendPlan(userId, DateTime.now());
      } else {
        _activePlanReadStatus = ActivePlanStatus.noActivePlan;
      }
      _allMealsLoaded = true;
      _filterByDate(DateTime.now());
      _cacheService.cacheMeals(userId, DateTime.now(), _todayMeals);
      _todayMealsStatus = DataStatus.known;
      _todayMealsObservedAt = DateTime.now();
      return true;
    } catch (e) {
      _todayMealsStatus = DataStatus.error;
      debugPrint('❌ Authoritative meal read failed: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> loadMealsForDate(String userId, DateTime date) async {
    _selectedDate = date;
    _isLoading = true;
    notifyListeners();

    try {
      final snapshot = await _firestore
          .collection(FirestoreCollections.mealDiary)
          .where('userId', isEqualTo: userId)
          .get();
      _allMeals =
          snapshot.docs.map((doc) => MealModel.fromMap(doc.data())).toList();
    } catch (e) {
      debugPrint('⚠️ Firestore load error: $e');
    }

    await _syncMealsFromBackendPlan(userId, date);
    _allMealsLoaded = true;
    _filterByDate(date);
    _cacheService.cacheMeals(userId, date, _todayMeals);
    _isLoading = false;
    notifyListeners();
  }

  Future<void> deleteMeal(String mealId) async {
    final mealIdx = _allMeals.indexWhere((m) => m.id == mealId);
    if (mealIdx == -1) return;
    final meal = _allMeals[mealIdx];

    // Optimistic update - remove from cache immediately
    _allMeals.removeAt(mealIdx);
    _todayMeals.removeWhere((m) => m.id == mealId);
    _deletedPlanItemIds.add(mealId);
    _saveDeletedPlanItemIds(meal.userId);
    _cacheService.removeMealFromCache(meal.userId, meal.date, mealId);
    notifyListeners();

    // Delete from Firestore in background
    try {
      await _firestore
          .collection(FirestoreCollections.mealDiary)
          .doc(mealId)
          .delete();
      debugPrint('✅ Meal deleted from Firestore: $mealId');
    } catch (e) {
      debugPrint('⚠️ Meal deleted locally/offline: $e');
    }
  }

  /// Cập nhật món ăn (thêm/xoá thành phần)
  Future<void> updateMeal(MealModel meal) async {
    // Optimistic update - update cache immediately
    final allIdx = _allMeals.indexWhere((m) => m.id == meal.id);
    if (allIdx != -1) _allMeals[allIdx] = meal;
    final todayIdx = _todayMeals.indexWhere((m) => m.id == meal.id);
    if (todayIdx != -1) _todayMeals[todayIdx] = meal;
    _cacheService.updateMealInCache(meal.userId, meal.date, meal);
    notifyListeners();

    // Save to Firestore in background
    try {
      await _firestore
          .collection(FirestoreCollections.mealDiary)
          .doc(meal.id)
          .set(meal.toMap());
      debugPrint('✅ Meal updated in Firestore: ${meal.id}');
    } catch (e) {
      debugPrint('❌ Error updating meal: $e');
      // Note: Rollback is complex here, so we just log the error
    }
  }

  // === CƠ SỞ DỮ LIỆU THỰC PHẨM VIỆT NAM (Bảng thành phần thực phẩm VN) ===
  static final List<FoodItem> vietnameseFoodDatabase = [
    // Ngũ cốc & Tinh bột
    FoodItem(
        id: 'vn001',
        name: 'Gạo nếp cái',
        caloriesPer100g: 346.0,
        proteinPer100g: 8.6,
        fatPer100g: 1.5,
        carbsPer100g: 74.9,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn002',
        name: 'Gạo tẻ',
        caloriesPer100g: 344.0,
        proteinPer100g: 7.9,
        fatPer100g: 1.0,
        carbsPer100g: 76.2,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn003',
        name: 'Bắp tươi',
        caloriesPer100g: 196.0,
        proteinPer100g: 4.1,
        fatPer100g: 2.3,
        carbsPer100g: 39.6,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn004',
        name: 'Bánh bao',
        caloriesPer100g: 219.0,
        proteinPer100g: 6.1,
        fatPer100g: 0.5,
        carbsPer100g: 47.5,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn005',
        name: 'Bánh tráng mỏng',
        caloriesPer100g: 333.0,
        proteinPer100g: 4.0,
        fatPer100g: 0.2,
        carbsPer100g: 78.9,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn006',
        name: 'Bánh đúc',
        caloriesPer100g: 52.0,
        proteinPer100g: 0.9,
        fatPer100g: 0.3,
        carbsPer100g: 11.3,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn007',
        name: 'Bánh mì',
        caloriesPer100g: 249.0,
        proteinPer100g: 7.9,
        fatPer100g: 0.8,
        carbsPer100g: 52.6,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn008',
        name: 'Bánh phở',
        caloriesPer100g: 141.0,
        proteinPer100g: 3.2,
        fatPer100g: 0.0,
        carbsPer100g: 32.1,
        category: 'Ngũ cốc & Tinh bột'),
    FoodItem(
        id: 'vn009',
        name: 'Bún',
        caloriesPer100g: 110.0,
        proteinPer100g: 1.7,
        fatPer100g: 0.0,
        carbsPer100g: 25.7,
        category: 'Ngũ cốc & Tinh bột'),
    // Khoai củ
    FoodItem(
        id: 'vn010',
        name: 'Củ sắn',
        caloriesPer100g: 152.0,
        proteinPer100g: 1.1,
        fatPer100g: 0.2,
        carbsPer100g: 36.4,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn011',
        name: 'Củ từ',
        caloriesPer100g: 92.0,
        proteinPer100g: 1.5,
        fatPer100g: 0.0,
        carbsPer100g: 21.5,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn012',
        name: 'Khoai lang',
        caloriesPer100g: 119.0,
        proteinPer100g: 0.8,
        fatPer100g: 0.2,
        carbsPer100g: 28.5,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn013',
        name: 'Khoai lang nghệ',
        caloriesPer100g: 116.0,
        proteinPer100g: 1.2,
        fatPer100g: 0.3,
        carbsPer100g: 27.1,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn014',
        name: 'Khoai môn',
        caloriesPer100g: 109.0,
        proteinPer100g: 1.5,
        fatPer100g: 0.2,
        carbsPer100g: 25.2,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn015',
        name: 'Khoai tây',
        caloriesPer100g: 92.0,
        proteinPer100g: 2.0,
        fatPer100g: 0.0,
        carbsPer100g: 21.0,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn016',
        name: 'Miến dong',
        caloriesPer100g: 332.0,
        proteinPer100g: 0.6,
        fatPer100g: 0.1,
        carbsPer100g: 82.2,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn017',
        name: 'Bột sắn dây',
        caloriesPer100g: 340.0,
        proteinPer100g: 0.7,
        fatPer100g: 0.0,
        carbsPer100g: 84.3,
        category: 'Khoai củ'),
    FoodItem(
        id: 'vn018',
        name: 'Khoai tây chiên',
        caloriesPer100g: 525.0,
        proteinPer100g: 2.2,
        fatPer100g: 35.4,
        carbsPer100g: 49.3,
        category: 'Khoai củ'),
    // Hạt & Đậu
    FoodItem(
        id: 'vn019',
        name: 'Cùi dừa già',
        caloriesPer100g: 368.0,
        proteinPer100g: 4.8,
        fatPer100g: 36.0,
        carbsPer100g: 6.2,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn020',
        name: 'Cùi dừa non',
        caloriesPer100g: 40.0,
        proteinPer100g: 3.5,
        fatPer100g: 1.7,
        carbsPer100g: 2.6,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn021',
        name: 'Đậu đen (hạt)',
        caloriesPer100g: 325.0,
        proteinPer100g: 24.2,
        fatPer100g: 1.7,
        carbsPer100g: 53.3,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn022',
        name: 'Đậu Hà lan (hạt)',
        caloriesPer100g: 342.0,
        proteinPer100g: 22.2,
        fatPer100g: 1.4,
        carbsPer100g: 60.1,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn023',
        name: 'Đậu xanh',
        caloriesPer100g: 328.0,
        proteinPer100g: 23.4,
        fatPer100g: 2.4,
        carbsPer100g: 53.1,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn024',
        name: 'Hạt điều',
        caloriesPer100g: 605.0,
        proteinPer100g: 18.4,
        fatPer100g: 46.3,
        carbsPer100g: 28.7,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn025',
        name: 'Đậu phộng',
        caloriesPer100g: 573.0,
        proteinPer100g: 27.5,
        fatPer100g: 44.5,
        carbsPer100g: 15.5,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn026',
        name: 'Mè',
        caloriesPer100g: 568.0,
        proteinPer100g: 20.1,
        fatPer100g: 46.4,
        carbsPer100g: 17.6,
        category: 'Hạt & Đậu'),
    FoodItem(
        id: 'vn027',
        name: 'Đậu phụ',
        caloriesPer100g: 95.0,
        proteinPer100g: 10.9,
        fatPer100g: 5.4,
        carbsPer100g: 0.7,
        category: 'Hạt & Đậu'),
    // Thịt
    FoodItem(
        id: 'vn028',
        name: 'Thịt bê nạc',
        caloriesPer100g: 85.0,
        proteinPer100g: 20.0,
        fatPer100g: 0.5,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn029',
        name: 'Thịt bò',
        caloriesPer100g: 118.0,
        proteinPer100g: 21.0,
        fatPer100g: 3.8,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn030',
        name: 'Thịt dê nạc',
        caloriesPer100g: 122.0,
        proteinPer100g: 20.7,
        fatPer100g: 4.3,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn031',
        name: 'Thịt gà ta',
        caloriesPer100g: 199.0,
        proteinPer100g: 20.3,
        fatPer100g: 13.1,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn032',
        name: 'Thịt heo mỡ',
        caloriesPer100g: 394.0,
        proteinPer100g: 14.5,
        fatPer100g: 37.3,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn033',
        name: 'Thịt heo nạc',
        caloriesPer100g: 139.0,
        proteinPer100g: 19.0,
        fatPer100g: 7.0,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn034',
        name: 'Thịt heo ba chỉ',
        caloriesPer100g: 260.0,
        proteinPer100g: 16.5,
        fatPer100g: 21.5,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn035',
        name: 'Thịt thỏ',
        caloriesPer100g: 158.0,
        proteinPer100g: 21.5,
        fatPer100g: 8.0,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn036',
        name: 'Thịt vịt',
        caloriesPer100g: 267.0,
        proteinPer100g: 17.8,
        fatPer100g: 21.8,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn037',
        name: 'Cật bò',
        caloriesPer100g: 67.0,
        proteinPer100g: 12.5,
        fatPer100g: 1.8,
        carbsPer100g: 0.3,
        category: 'Thịt'),
    FoodItem(
        id: 'vn038',
        name: 'Cật heo',
        caloriesPer100g: 81.0,
        proteinPer100g: 13.0,
        fatPer100g: 3.1,
        carbsPer100g: 0.3,
        category: 'Thịt'),
    FoodItem(
        id: 'vn039',
        name: 'Gan bò',
        caloriesPer100g: 110.0,
        proteinPer100g: 17.4,
        fatPer100g: 3.1,
        carbsPer100g: 3.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn040',
        name: 'Gan gà',
        caloriesPer100g: 111.0,
        proteinPer100g: 18.2,
        fatPer100g: 3.4,
        carbsPer100g: 2.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn041',
        name: 'Gan heo',
        caloriesPer100g: 116.0,
        proteinPer100g: 18.8,
        fatPer100g: 3.6,
        carbsPer100g: 2.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn042',
        name: 'Chả lụa',
        caloriesPer100g: 136.0,
        proteinPer100g: 21.5,
        fatPer100g: 5.5,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn043',
        name: 'Lạp xưởng',
        caloriesPer100g: 585.0,
        proteinPer100g: 20.8,
        fatPer100g: 55.0,
        carbsPer100g: 1.7,
        category: 'Thịt'),
    FoodItem(
        id: 'vn044',
        name: 'Nem chua',
        caloriesPer100g: 137.0,
        proteinPer100g: 21.7,
        fatPer100g: 3.7,
        carbsPer100g: 4.3,
        category: 'Thịt'),
    FoodItem(
        id: 'vn045',
        name: 'Chà bông',
        caloriesPer100g: 396.0,
        proteinPer100g: 46.6,
        fatPer100g: 20.3,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn046',
        name: 'Thịt bò khô',
        caloriesPer100g: 239.0,
        proteinPer100g: 51.0,
        fatPer100g: 1.6,
        carbsPer100g: 5.2,
        category: 'Thịt'),
    FoodItem(
        id: 'vn047',
        name: 'Xúc xích',
        caloriesPer100g: 535.0,
        proteinPer100g: 27.2,
        fatPer100g: 47.4,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    FoodItem(
        id: 'vn048',
        name: 'Ếch',
        caloriesPer100g: 90.0,
        proteinPer100g: 20.0,
        fatPer100g: 1.1,
        carbsPer100g: 0.0,
        category: 'Thịt'),
    // Hải sản & Thủy sản
    FoodItem(
        id: 'vn049',
        name: 'Cá bống',
        caloriesPer100g: 70.0,
        proteinPer100g: 15.8,
        fatPer100g: 0.8,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn050',
        name: 'Cá chép',
        caloriesPer100g: 96.0,
        proteinPer100g: 16.0,
        fatPer100g: 3.6,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn051',
        name: 'Cá hồi',
        caloriesPer100g: 136.0,
        proteinPer100g: 22.0,
        fatPer100g: 5.3,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn052',
        name: 'Cá khô',
        caloriesPer100g: 208.0,
        proteinPer100g: 43.3,
        fatPer100g: 3.9,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn053',
        name: 'Cá lóc',
        caloriesPer100g: 97.0,
        proteinPer100g: 18.2,
        fatPer100g: 2.7,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn054',
        name: 'Cá ngừ',
        caloriesPer100g: 87.0,
        proteinPer100g: 21.0,
        fatPer100g: 0.3,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn055',
        name: 'Cá nục',
        caloriesPer100g: 111.0,
        proteinPer100g: 20.2,
        fatPer100g: 3.3,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn056',
        name: 'Cá rô phi',
        caloriesPer100g: 100.0,
        proteinPer100g: 19.7,
        fatPer100g: 2.3,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn057',
        name: 'Cá thu',
        caloriesPer100g: 166.0,
        proteinPer100g: 18.2,
        fatPer100g: 10.3,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn058',
        name: 'Cua biển',
        caloriesPer100g: 103.0,
        proteinPer100g: 17.5,
        fatPer100g: 0.6,
        carbsPer100g: 7.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn059',
        name: 'Cua đồng',
        caloriesPer100g: 87.0,
        proteinPer100g: 12.3,
        fatPer100g: 3.3,
        carbsPer100g: 2.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn060',
        name: 'Hến',
        caloriesPer100g: 45.0,
        proteinPer100g: 4.5,
        fatPer100g: 0.7,
        carbsPer100g: 5.1,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn061',
        name: 'Lươn',
        caloriesPer100g: 94.0,
        proteinPer100g: 20.0,
        fatPer100g: 1.5,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn062',
        name: 'Mực khô',
        caloriesPer100g: 291.0,
        proteinPer100g: 60.1,
        fatPer100g: 4.5,
        carbsPer100g: 2.5,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn063',
        name: 'Mực tươi',
        caloriesPer100g: 73.0,
        proteinPer100g: 16.3,
        fatPer100g: 0.9,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn064',
        name: 'Ốc bươu',
        caloriesPer100g: 84.0,
        proteinPer100g: 11.1,
        fatPer100g: 0.7,
        carbsPer100g: 8.3,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn065',
        name: 'Sò',
        caloriesPer100g: 51.0,
        proteinPer100g: 8.8,
        fatPer100g: 0.4,
        carbsPer100g: 3.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn066',
        name: 'Tôm biển',
        caloriesPer100g: 82.0,
        proteinPer100g: 17.6,
        fatPer100g: 0.9,
        carbsPer100g: 0.9,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn067',
        name: 'Tôm đồng',
        caloriesPer100g: 90.0,
        proteinPer100g: 18.4,
        fatPer100g: 1.8,
        carbsPer100g: 0.0,
        category: 'Hải sản & Thủy sản'),
    FoodItem(
        id: 'vn068',
        name: 'Tôm khô',
        caloriesPer100g: 347.0,
        proteinPer100g: 75.6,
        fatPer100g: 3.8,
        carbsPer100g: 2.5,
        category: 'Hải sản & Thủy sản'),
    // Trứng
    FoodItem(
        id: 'vn069',
        name: 'Trứng gà',
        caloriesPer100g: 166.0,
        proteinPer100g: 14.8,
        fatPer100g: 11.6,
        carbsPer100g: 0.5,
        category: 'Trứng'),
    FoodItem(
        id: 'vn070',
        name: 'Trứng vịt',
        caloriesPer100g: 184.0,
        proteinPer100g: 13.0,
        fatPer100g: 14.2,
        carbsPer100g: 1.0,
        category: 'Trứng'),
    FoodItem(
        id: 'vn071',
        name: 'Trứng vịt lộn',
        caloriesPer100g: 182.0,
        proteinPer100g: 13.6,
        fatPer100g: 12.4,
        carbsPer100g: 4.0,
        category: 'Trứng'),
    // Sữa & Chế phẩm
    FoodItem(
        id: 'vn072',
        name: 'Sữa bò tươi',
        caloriesPer100g: 74.0,
        proteinPer100g: 3.9,
        fatPer100g: 4.4,
        carbsPer100g: 4.8,
        category: 'Sữa & Chế phẩm'),
    // Đồ hộp
    FoodItem(
        id: 'vn073',
        name: 'Cá thu hộp',
        caloriesPer100g: 207.0,
        proteinPer100g: 24.8,
        fatPer100g: 12.0,
        carbsPer100g: 0.0,
        category: 'Đồ hộp'),
    FoodItem(
        id: 'vn074',
        name: 'Thịt bò hộp',
        caloriesPer100g: 251.0,
        proteinPer100g: 16.4,
        fatPer100g: 20.6,
        carbsPer100g: 0.0,
        category: 'Đồ hộp'),
    FoodItem(
        id: 'vn075',
        name: 'Thịt heo hộp',
        caloriesPer100g: 344.0,
        proteinPer100g: 17.3,
        fatPer100g: 29.3,
        carbsPer100g: 2.7,
        category: 'Đồ hộp'),
    // Bánh & Kẹo
    FoodItem(
        id: 'vn076',
        name: 'Bánh mì khô',
        caloriesPer100g: 346.0,
        proteinPer100g: 12.3,
        fatPer100g: 1.3,
        carbsPer100g: 71.3,
        category: 'Bánh & Kẹo'),
    FoodItem(
        id: 'vn077',
        name: 'Bánh sôcôla',
        caloriesPer100g: 449.0,
        proteinPer100g: 3.9,
        fatPer100g: 17.6,
        carbsPer100g: 68.8,
        category: 'Bánh & Kẹo'),
    FoodItem(
        id: 'vn078',
        name: 'Đường cát trắng',
        caloriesPer100g: 397.0,
        proteinPer100g: 0.0,
        fatPer100g: 0.0,
        carbsPer100g: 99.3,
        category: 'Bánh & Kẹo'),
    FoodItem(
        id: 'vn079',
        name: 'Kẹo dừa mềm',
        caloriesPer100g: 415.0,
        proteinPer100g: 0.6,
        fatPer100g: 12.2,
        carbsPer100g: 75.6,
        category: 'Bánh & Kẹo'),
    FoodItem(
        id: 'vn080',
        name: 'Mật ong',
        caloriesPer100g: 327.0,
        proteinPer100g: 0.4,
        fatPer100g: 0.0,
        carbsPer100g: 81.3,
        category: 'Bánh & Kẹo'),
    // Gia vị
    FoodItem(
        id: 'vn081',
        name: 'Gừng tươi',
        caloriesPer100g: 25.0,
        proteinPer100g: 0.4,
        fatPer100g: 0.0,
        carbsPer100g: 5.8,
        category: 'Gia vị'),
    FoodItem(
        id: 'vn082',
        name: 'Nước mắm',
        caloriesPer100g: 28.0,
        proteinPer100g: 7.1,
        fatPer100g: 0.0,
        carbsPer100g: 0.0,
        category: 'Gia vị'),
    FoodItem(
        id: 'vn083',
        name: 'Tương ớt',
        caloriesPer100g: 37.0,
        proteinPer100g: 0.5,
        fatPer100g: 0.5,
        carbsPer100g: 7.6,
        category: 'Gia vị'),
    // Đồ uống
    FoodItem(
        id: 'vn084',
        name: 'Bia',
        caloriesPer100g: 43.0,
        proteinPer100g: 0.5,
        fatPer100g: 0.0,
        carbsPer100g: 2.3,
        category: 'Đồ uống'),
    FoodItem(
        id: 'vn085',
        name: 'CocaCola',
        caloriesPer100g: 42.0,
        proteinPer100g: 0.0,
        fatPer100g: 0.0,
        carbsPer100g: 10.4,
        category: 'Đồ uống'),
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
    final breakfastCal =
        targetCalories * NutritionPolicyV1.mealSplit['breakfast']!;
    final lunchCal = targetCalories * NutritionPolicyV1.mealSplit['lunch']!;
    final dinnerCal = targetCalories * NutritionPolicyV1.mealSplit['dinner']!;

    suggestions.add({
      'title': '🌅 Bữa sáng (~${breakfastCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Bánh mì (80g) + Trứng gà (2 quả)',
        'Bánh phở (350g) + Thịt bò (100g)',
        'Bún (200g) + Chả lụa (50g)',
      ],
    });

    suggestions.add({
      'title': '☀️ Bữa trưa (~${lunchCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Gạo tẻ (150g) + Cá lóc (120g) + Rau luộc',
        'Gạo tẻ (150g) + Thịt heo nạc (100g) + Đậu phụ',
        'Gạo tẻ (150g) + Tôm biển (100g) + Rau xào',
      ],
    });

    suggestions.add({
      'title': '🌙 Bữa tối (~${dinnerCal.toStringAsFixed(0)} kcal)',
      'items': [
        'Gạo tẻ (120g) + Cá ngừ (100g) + Rau luộc',
        'Bún (200g) + Thịt gà ta (100g)',
        'Gạo tẻ (120g) + Đậu phụ (150g) + Rau xào',
      ],
    });

    return suggestions;
  }

  // Toggle meal completed status
  Future<void> toggleMealCompleted(String mealId) async {
    try {
      final index = _todayMeals.indexWhere((m) => m.id == mealId);
      if (index != -1) {
        final meal = _todayMeals[index];
        final updated = meal.copyWith(isCompleted: !meal.isCompleted);

        // Optimistic update
        _todayMeals[index] = updated;
        final allIndex = _allMeals.indexWhere((m) => m.id == mealId);
        if (allIndex != -1) {
          _allMeals[allIndex] = updated;
        }
        _cacheService.updateMealInCache(meal.userId, meal.date, updated);
        notifyListeners();

        // Update Firestore in background
        try {
          await _firestore
              .collection(FirestoreCollections.mealDiary)
              .doc(mealId)
              .update({'isCompleted': updated.isCompleted});
        } catch (_) {}

        // Update backend plan item if it belongs to plan
        try {
          await BackendApiService().updatePlanItemCompletion(
            itemId: mealId,
            completed: updated.isCompleted,
          );
        } catch (_) {}

        debugPrint('✅ Meal completed status updated: ${updated.isCompleted}');
      }
    } catch (e) {
      debugPrint('❌ Error toggling meal completed: $e');
      // Rollback on error
      final index = _todayMeals.indexWhere((m) => m.id == mealId);
      if (index != -1) {
        final meal = _todayMeals[index];
        final reverted = meal.copyWith(isCompleted: !meal.isCompleted);
        _todayMeals[index] = reverted;
        final allIndex = _allMeals.indexWhere((m) => m.id == mealId);
        if (allIndex != -1) {
          _allMeals[allIndex] = reverted;
        }
        _cacheService.updateMealInCache(meal.userId, meal.date, reverted);
        notifyListeners();
      }
      rethrow;
    }
  }

  int get completedMealsCount => _todayMeals.where((m) => m.isCompleted).length;
  int get pendingMealsCount => _todayMeals.where((m) => !m.isCompleted).length;
  double get mealCompletionRate =>
      _todayMeals.isEmpty ? 0.0 : completedMealsCount / _todayMeals.length;

  // ═══════════════════════════════════════════════════════════════
  // MÓN ĂN ĐÃ LƯU (saved meals) — lưu local bằng SharedPreferences
  // ═══════════════════════════════════════════════════════════════
  static const _savedMealsKey = 'saved_meal_templates';
  List<SavedMealTemplate> _savedMeals = [];
  List<SavedMealTemplate> get savedMeals => List.unmodifiable(_savedMeals);

  Future<void> loadSavedMeals() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getStringList(_savedMealsKey) ?? [];
      _savedMeals = raw
          .map((s) {
            try {
              return SavedMealTemplate.fromJson(
                  jsonDecode(s) as Map<String, dynamic>);
            } catch (_) {
              return null;
            }
          })
          .whereType<SavedMealTemplate>()
          .toList();
      notifyListeners();
    } catch (e) {
      debugPrint('❌ Error loading saved meals: $e');
    }
  }

  Future<void> saveMealTemplate(SavedMealTemplate template) async {
    _savedMeals.removeWhere((m) => m.id == template.id);
    _savedMeals.insert(0, template);
    notifyListeners();
    await _persistSavedMeals();
  }

  Future<void> deleteSavedMeal(String id) async {
    _savedMeals.removeWhere((m) => m.id == id);
    notifyListeners();
    await _persistSavedMeals();
  }

  Future<void> _persistSavedMeals() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = _savedMeals.map((m) => jsonEncode(m.toJson())).toList();
      await prefs.setStringList(_savedMealsKey, raw);
    } catch (e) {
      debugPrint('❌ Error saving meal templates: $e');
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // MÓN ĂN MẪU — combo phổ biến load sẵn
  // ═══════════════════════════════════════════════════════════════
  static final List<SavedMealTemplate> sampleMeals = [
    SavedMealTemplate(
      id: 'sample_com_heo_quay',
      name: 'Cơm heo quay',
      emoji: '🍖',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn002', name: 'Gạo tẻ', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn034', name: 'Thịt heo ba chỉ', defaultGrams: 100),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_pho_bo',
      name: 'Phở bò',
      emoji: '🍜',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn008', name: 'Bánh phở', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn029', name: 'Thịt bò', defaultGrams: 100),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_bun_cha',
      name: 'Bún chả',
      emoji: '🥢',
      items: [
        SavedMealItemTemplate(foodId: 'vn009', name: 'Bún', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn033', name: 'Thịt heo nạc', defaultGrams: 80),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_com_ga',
      name: 'Cơm gà luộc',
      emoji: '🍗',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn002', name: 'Gạo tẻ', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn031', name: 'Thịt gà ta', defaultGrams: 120),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_banh_mi_trung',
      name: 'Bánh mì trứng',
      emoji: '🥖',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn007', name: 'Bánh mì', defaultGrams: 100),
        SavedMealItemTemplate(
            foodId: 'vn069', name: 'Trứng gà', defaultGrams: 60),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_com_ca',
      name: 'Cơm cá lóc',
      emoji: '🐟',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn002', name: 'Gạo tẻ', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn053', name: 'Cá lóc', defaultGrams: 150),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_sua_chua_trai_cay',
      name: 'Sữa chua trái cây',
      emoji: '🍓',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn072', name: 'Sữa bò tươi', defaultGrams: 150),
      ],
    ),
    SavedMealTemplate(
      id: 'sample_com_tom',
      name: 'Cơm tôm xào',
      emoji: '🦐',
      items: [
        SavedMealItemTemplate(
            foodId: 'vn002', name: 'Gạo tẻ', defaultGrams: 200),
        SavedMealItemTemplate(
            foodId: 'vn066', name: 'Tôm biển', defaultGrams: 100),
      ],
    ),
  ];
}
