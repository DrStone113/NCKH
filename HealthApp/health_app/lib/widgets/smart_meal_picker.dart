import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/nutrition_provider.dart';
import '../providers/user_provider.dart';
import '../models/meal_model.dart';
import '../theme/app_theme.dart';
import '../services/backend_api_service.dart';
/// - Tab 1: Món ăn Việt Nam từ backend API
/// - Tab 2: Món ăn đã lưu (favorites)
/// - Tab 3: Tìm kiếm nguyên liệu local
class SmartMealPicker extends StatefulWidget {
  final DateTime date;
  final String initialMealType;

  const SmartMealPicker({
    super.key,
    required this.date,
    this.initialMealType = 'sang',
  });

  @override
  State<SmartMealPicker> createState() => _SmartMealPickerState();
}

class _SmartMealPickerState extends State<SmartMealPicker>
    with SingleTickerProviderStateMixin {
  final _mealNameController = TextEditingController();
  late String _mealType;
  final List<MealItem> _items = [];
  late TabController _tabController;

  // Backend API service
  final BackendApiService _apiService = BackendApiService();
  
  // Vietnamese dishes from backend
  List<Map<String, dynamic>> _vietnameseDishes = [];
  bool _loadingDishes = false;
  String _dishSearchQuery = '';

  @override
  void initState() {
    super.initState();
    _mealType = widget.initialMealType;
    _tabController = TabController(length: 3, vsync: this);
    _loadVietnameseDishes();
  }

  @override
  void dispose() {
    _mealNameController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  /// Load Vietnamese dishes from backend API
  Future<void> _loadVietnameseDishes() async {
    setState(() => _loadingDishes = true);
    try {
      final dishes = await _apiService.getVietnameseDishes();
      if (mounted) {
        setState(() {
          _vietnameseDishes = dishes;
          _loadingDishes = false;
        });
      }
    } catch (e) {
      debugPrint('❌ Error loading Vietnamese dishes: $e');
      if (mounted) {
        setState(() => _loadingDishes = false);
      }
    }
  }

  double get _totalCal => _items.fold(0, (s, i) => s + i.calories);
  double get _totalProtein => _items.fold(0, (s, i) => s + i.protein);
  double get _totalCarbs => _items.fold(0, (s, i) => s + i.carbs);
  double get _totalFat => _items.fold(0, (s, i) => s + i.fat);

  void _addItem(MealItem item) => setState(() => _items.add(item));
  void _removeItem(int index) => setState(() => _items.removeAt(index));

  /// Add a Vietnamese dish from backend
  void _addDish(Map<String, dynamic> dish) {
    final ingredients = dish['ingredients'] as List<dynamic>? ?? [];
    
    for (final ingredient in ingredients) {
      final item = MealItem(
        id: '${ingredient['name']}_${DateTime.now().millisecondsSinceEpoch}',
        foodId: ingredient['name'] ?? '',
        name: ingredient['name'] ?? '',
        weightGrams: (ingredient['amount'] as num?)?.toDouble() ?? 100.0,
        calories: (ingredient['calories'] as num?)?.toDouble() ?? 0.0,
        protein: (ingredient['protein'] as num?)?.toDouble() ?? 0.0,
        carbs: (ingredient['carbs'] as num?)?.toDouble() ?? 0.0,
        fat: (ingredient['fat'] as num?)?.toDouble() ?? 0.0,
      );
      _addItem(item);
    }

    // Set meal name if empty
    if (_mealNameController.text.isEmpty) {
      _mealNameController.text = dish['name'] ?? '';
    }

    // Switch to summary tab
    _tabController.animateTo(2);
  }

  void _save() {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null || _items.isEmpty) return;

    final mealName = _mealNameController.text.trim().isNotEmpty
        ? _mealNameController.text.trim()
        : _items.length == 1
            ? _items.first.name
            : '${_items.first.name} + ${_items.length - 1} món khác';

    final meal = MealModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: userId,
      name: mealName,
      date: DateTime(widget.date.year, widget.date.month, widget.date.day,
          DateTime.now().hour, DateTime.now().minute),
      mealType: _mealType,
      items: List.from(_items),
    );

    Provider.of<NutritionProvider>(context, listen: false).addMeal(meal);
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.9,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      builder: (ctx, scrollCtrl) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              // Header
              _buildHeader(),
              
              // Items summary
              if (_items.isNotEmpty) _buildItemsSummary(),
              
              // Tab content
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildVietnameseDishesTab(),
                    _buildSavedMealsTab(),
                    _buildIngredientSearchTab(),
                  ],
                ),
              ),
              
              // Bottom bar
              _buildBottomBar(),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
      child: Column(
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.textHint,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Text(
                'Thêm món ăn',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              _buildMealTypeDropdown(),
            ],
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _mealNameController,
            decoration: const InputDecoration(
              hintText: 'Tên món ăn (vd: Cơm heo quay)',
              hintStyle: TextStyle(fontSize: 13),
              prefixIcon: Icon(Icons.restaurant, size: 18),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
          ),
          const SizedBox(height: 8),
          TabBar(
            controller: _tabController,
            labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            unselectedLabelStyle: const TextStyle(fontSize: 12),
            indicatorSize: TabBarIndicatorSize.tab,
            tabs: const [
              Tab(text: '🍜 Món Việt'),
              Tab(text: '❤️ Đã lưu'),
              Tab(text: '🔍 Nguyên liệu'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMealTypeDropdown() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: _getMealTypeColor(_mealType).withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: DropdownButton<String>(
        value: _mealType,
        underline: const SizedBox(),
        isDense: true,
        dropdownColor: AppColors.surface,
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: _getMealTypeColor(_mealType),
        ),
        items: const [
          DropdownMenuItem(value: 'sang', child: Text('🌅 Sáng')),
          DropdownMenuItem(value: 'trua', child: Text('☀️ Trưa')),
          DropdownMenuItem(value: 'toi', child: Text('🌙 Tối')),
          DropdownMenuItem(value: 'phu', child: Text('🍎 Phụ')),
        ],
        onChanged: (v) => setState(() => _mealType = v!),
      ),
    );
  }

  Widget _buildItemsSummary() {
    return Container(
      margin: const EdgeInsets.fromLTRB(20, 8, 20, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.primary.withOpacity(0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.receipt_long, size: 14, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text(
                '${_items.length} thành phần',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              Text(
                '${_totalCal.toStringAsFixed(0)} kcal',
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.calories,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: _items.asMap().entries.map((e) {
              return GestureDetector(
                onTap: () => _removeItem(e.key),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppColors.surfaceLight),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        e.value.name,
                        style: const TextStyle(fontSize: 11),
                      ),
                      const SizedBox(width: 4),
                      const Icon(Icons.close, size: 12, color: AppColors.textHint),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildVietnameseDishesTab() {
    if (_loadingDishes) {
      return const Center(child: CircularProgressIndicator());
    }

    final filtered = _vietnameseDishes.where((dish) {
      if (_dishSearchQuery.isEmpty) return true;
      final name = (dish['name'] ?? '').toString().toLowerCase();
      return name.contains(_dishSearchQuery.toLowerCase());
    }).toList();

    return Column(
      children: [
        // Search bar
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            decoration: const InputDecoration(
              hintText: 'Tìm món ăn...',
              prefixIcon: Icon(Icons.search, size: 20),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (val) => setState(() => _dishSearchQuery = val),
          ),
        ),
        
        // Dishes list
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: filtered.length,
            itemBuilder: (context, index) {
              final dish = filtered[index];
              return _buildDishCard(dish);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildDishCard(Map<String, dynamic> dish) {
    final name = dish['name'] ?? '';
    final calories = (dish['total_calories'] as num?)?.toDouble() ?? 0.0;
    final ingredients = dish['ingredients'] as List<dynamic>? ?? [];

    return GestureDetector(
      onTap: () => _addDish(dish),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.surfaceLight),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.restaurant, color: AppColors.primary, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${ingredients.length} nguyên liệu',
                    style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  calories.toStringAsFixed(0),
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: AppColors.calories,
                  ),
                ),
                const Text(
                  'kcal',
                  style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
                ),
              ],
            ),
            const SizedBox(width: 8),
            const Icon(Icons.add_circle, color: AppColors.primary, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildSavedMealsTab() {
    // TODO: Implement saved meals tab
    return const Center(
      child: Text('Saved meals coming soon...'),
    );
  }

  Widget _buildIngredientSearchTab() {
    // TODO: Implement ingredient search tab
    return const Center(
      child: Text('Ingredient search coming soon...'),
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.surfaceLight)),
      ),
      child: Row(
        children: [
          // Nutrition summary
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '${_totalCal.toStringAsFixed(0)} kcal',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                Text(
                  'P:${_totalProtein.toStringAsFixed(0)}g  C:${_totalCarbs.toStringAsFixed(0)}g  F:${_totalFat.toStringAsFixed(0)}g',
                  style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          // Save button
          ElevatedButton(
            onPressed: _items.isEmpty ? null : _save,
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            ),
            child: const Text('Thêm món'),
          ),
        ],
      ),
    );
  }

  Color _getMealTypeColor(String type) {
    switch (type) {
      case 'sang':
        return const Color(0xFFFF9800);
      case 'trua':
        return const Color(0xFF4CAF50);
      case 'toi':
        return const Color(0xFF3F51B5);
      default:
        return const Color(0xFF9C27B0);
    }
  }
}
