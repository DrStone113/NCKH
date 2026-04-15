import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/nutrition_provider.dart';
import '../providers/user_provider.dart';
import '../models/meal_model.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';
import '../widgets/animated_counter.dart';
import 'dart:math' as math;

class NutritionScreen extends StatefulWidget {
  const NutritionScreen({super.key});

  @override
  State<NutritionScreen> createState() => _NutritionScreenState();
}

class _NutritionScreenState extends State<NutritionScreen> {
  void _showDatePicker(BuildContext context, NutritionProvider provider, String userId) {
    DateTime _viewMonth = DateTime(provider.selectedDate.year, provider.selectedDate.month);

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final now = DateTime.now();
          final daysInMonth = DateUtils.getDaysInMonth(_viewMonth.year, _viewMonth.month);
          final firstWeekday = DateTime(_viewMonth.year, _viewMonth.month, 1).weekday % 7; // 0=Sun

          return Container(
            decoration: const BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Handle
                Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
                const SizedBox(height: 16),

                // Month navigator
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.chevron_left),
                      onPressed: () => setModalState(() {
                        _viewMonth = DateTime(_viewMonth.year, _viewMonth.month - 1);
                      }),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                    Text(
                      '${_monthLabel(_viewMonth.month)} ${_viewMonth.year}',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    IconButton(
                      icon: Icon(Icons.chevron_right,
                          color: (_viewMonth.year == now.year && _viewMonth.month == now.month)
                              ? AppColors.textHint : null),
                      onPressed: (_viewMonth.year == now.year && _viewMonth.month == now.month)
                          ? null
                          : () => setModalState(() {
                              _viewMonth = DateTime(_viewMonth.year, _viewMonth.month + 1);
                            }),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                  ],
                ),
                const SizedBox(height: 8),

                // Weekday headers
                Row(
                  children: ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'].map((d) =>
                    Expanded(child: Center(child: Text(d,
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textHint))))
                  ).toList(),
                ),
                const SizedBox(height: 8),

                // Calendar grid
                GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 7,
                    mainAxisSpacing: 4,
                    crossAxisSpacing: 4,
                    childAspectRatio: 1,
                  ),
                  itemCount: firstWeekday + daysInMonth,
                  itemBuilder: (_, index) {
                    if (index < firstWeekday) return const SizedBox();
                    final day = index - firstWeekday + 1;
                    final date = DateTime(_viewMonth.year, _viewMonth.month, day);
                    final isFuture = date.isAfter(now);
                    final isSelected = date.year == provider.selectedDate.year &&
                        date.month == provider.selectedDate.month &&
                        date.day == provider.selectedDate.day;
                    final isToday = date.year == now.year && date.month == now.month && date.day == now.day;

                    return GestureDetector(
                      onTap: isFuture ? null : () {
                        provider.loadMealsForDate(userId, date);
                        Navigator.pop(ctx);
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: isSelected
                              ? AppColors.primary
                              : isToday
                                  ? AppColors.primary.withOpacity(0.08)
                                  : Colors.transparent,
                          shape: BoxShape.circle,
                          border: isToday && !isSelected
                              ? Border.all(color: AppColors.primary, width: 1.5)
                              : null,
                        ),
                        child: Center(
                          child: Text(
                            '$day',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: isSelected || isToday ? FontWeight.bold : FontWeight.normal,
                              color: isSelected
                                  ? Colors.white
                                  : isFuture
                                      ? AppColors.textHint
                                      : AppColors.textPrimary,
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }

  String _monthLabel(int month) {
    const months = ['', 'Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4', 'Tháng 5', 'Tháng 6',
        'Tháng 7', 'Tháng 8', 'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12'];
    return months[month];
  }

  void _changeDate(BuildContext context, int days) {
    final provider = Provider.of<NutritionProvider>(context, listen: false);
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;
    final newDate = provider.selectedDate.add(Duration(days: days));
    if (newDate.isAfter(DateTime.now())) return;
    provider.loadMealsForDate(userId, newDate);
  }

  @override
  Widget build(BuildContext context) {
    final nutritionProvider = Provider.of<NutritionProvider>(context);
    final user = Provider.of<UserProvider>(context).currentUser;
    final targetCal = user?.recommendedCalories ?? 2000;
    final selectedDate = nutritionProvider.selectedDate;
    final isToday = nutritionProvider.isToday;

    // Format ngày hiển thị
    final now = DateTime.now();
    final yesterday = DateTime(now.year, now.month, now.day - 1);
    String dateLabel;
    if (isToday) {
      dateLabel = 'Hôm nay';
    } else if (selectedDate.year == yesterday.year && selectedDate.month == yesterday.month && selectedDate.day == yesterday.day) {
      dateLabel = 'Hôm qua';
    } else {
      dateLabel = '${selectedDate.day}/${selectedDate.month}/${selectedDate.year}';
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Dinh dưỡng'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.lightbulb_outline),
            onPressed: () => _showMealSuggestions(context, targetCal),
            tooltip: 'Gợi ý thực đơn',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddMealDialog(context, selectedDate),
        child: const Icon(Icons.add),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Date navigator
            AnimatedCard(
              delay: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.cardDark,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.chevron_left, size: 20),
                      onPressed: () => _changeDate(context, -1),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                    GestureDetector(
                      onTap: () {
                        final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
                        if (userId == null) return;
                        _showDatePicker(context, nutritionProvider, userId);
                      },
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.calendar_today, size: 13, color: AppColors.textSecondary),
                          const SizedBox(width: 6),
                          Text(dateLabel, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                          const SizedBox(width: 4),
                          const Icon(Icons.keyboard_arrow_down, size: 16, color: AppColors.textSecondary),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.chevron_right, size: 20,
                          color: isToday ? AppColors.textHint : null),
                      onPressed: isToday ? null : () => _changeDate(context, 1),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Calorie summary
            AnimatedCard(
              delay: 100,
              child: _buildCalorieSummary(nutritionProvider, targetCal),
            ),
            const SizedBox(height: 20),

            // Macro breakdown
            AnimatedCard(
              delay: 200,
              child: _buildMacroBreakdown(nutritionProvider),
            ),
            const SizedBox(height: 24),

            // Meals header
            AnimatedCard(
              delay: 300,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Bữa ăn $dateLabel', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  Text('${nutritionProvider.todayMeals.length} món', style: TextStyle(color: AppColors.textSecondary)),
                ],
              ),
            ),
            const SizedBox(height: 12),

            if (nutritionProvider.todayMeals.isEmpty)
              AnimatedCard(
                delay: 300,
                child: Container(
                  padding: const EdgeInsets.all(40),
                  decoration: BoxDecoration(
                    color: AppColors.cardDark,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Center(
                    child: Column(
                      children: [
                        Icon(Icons.restaurant_menu, size: 48, color: AppColors.textHint),
                        SizedBox(height: 12),
                        Text('Chưa có bữa ăn nào', style: TextStyle(color: AppColors.textSecondary)),
                        SizedBox(height: 4),
                        Text('Nhấn + để thêm bữa ăn', style: TextStyle(fontSize: 12, color: AppColors.textHint)),
                      ],
                    ),
                  ),
                ),
              )
            else
              ...nutritionProvider.todayMeals.asMap().entries.map((entry) {
                final index = entry.key;
                final meal = entry.value;
                return AnimatedCard(
                  delay: 300 + (index * 50),
                  child: _buildMealCard(context, meal),
                );
              }),
          ],
        ),
      ),
    );
  }

  Widget _buildCalorieSummary(NutritionProvider provider, double target) {
    final consumed = provider.totalCalories;
    final progress = target > 0 ? (consumed / target).clamp(0.0, 1.5) : 0.0;
    final remaining = (target - consumed).clamp(0.0, target);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AppColors.cardGradient,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          // Circular progress
          SizedBox(
            width: 100,
            height: 100,
            child: CustomPaint(
              painter: _CalorieRingPainter(
                progress: progress.toDouble(),
                consumed: consumed > target,
              ),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AnimatedCounter(
                      value: consumed,
                      decimals: 0,
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                    ),
                    const Text('kcal', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),

          // Stats
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _calorieStat('Mục tiêu', target, AppColors.primary),
                const SizedBox(height: 8),
                _calorieStat('Đã ăn', consumed, AppColors.calories),
                const SizedBox(height: 8),
                _calorieStat('Còn lại', remaining,
                    consumed > target ? AppColors.error : AppColors.success),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _calorieStat(String label, double value, Color color) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
        AnimatedCounter(
          value: value,
          decimals: 0,
          suffix: ' kcal',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color),
        ),
      ],
    );
  }

  Widget _buildMacroBreakdown(NutritionProvider provider) {
    final total = provider.totalProtein + provider.totalCarbs + provider.totalFat;
    final proteinPct = total > 0 ? (provider.totalProtein / total * 100) : 0;
    final carbsPct = total > 0 ? (provider.totalCarbs / total * 100) : 0;
    final fatPct = total > 0 ? (provider.totalFat / total * 100) : 0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Thành phần dinh dưỡng', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          _macroBar('Protein', provider.totalProtein, proteinPct.toDouble(), AppColors.protein),
          const SizedBox(height: 12),
          _macroBar('Carbs', provider.totalCarbs, carbsPct.toDouble(), AppColors.carbs),
          const SizedBox(height: 12),
          _macroBar('Chất béo', provider.totalFat, fatPct.toDouble(), AppColors.fat),
        ],
      ),
    );
  }

  Widget _macroBar(String name, double grams, double pct, Color color) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(name, style: const TextStyle(fontSize: 13)),
            Row(
              children: [
                AnimatedCounter(
                  value: grams,
                  decimals: 1,
                  suffix: 'g',
                  style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600),
                ),
                Text(' (', style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
                AnimatedCounter(
                  value: pct,
                  decimals: 0,
                  suffix: '%)',
                  style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 6),
        AnimatedProgressBar(
          value: (pct / 100).clamp(0.0, 1.0),
          height: 6,
          color: color,
          backgroundColor: AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(4),
        ),
      ],
    );
  }

  Widget _buildMealCard(BuildContext context, MealModel meal) {
    return Dismissible(
      key: Key(meal.id),
      direction: DismissDirection.endToStart,
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: AppColors.error,
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline, color: Colors.white, size: 24),
            SizedBox(width: 8),
            Text(
              'Xoá',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
      confirmDismiss: (direction) async {
        return await showDialog(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: AppColors.surface,
            title: const Text('Xác nhận xoá'),
            content: Text('Bạn có chắc muốn xoá "${meal.name}"?'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Huỷ'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(context, true),
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
                child: const Text('Xoá'),
              ),
            ],
          ),
        );
      },
      onDismissed: (direction) {
        _deleteMeal(context, meal.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã xoá "${meal.name}"'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 2),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: _getMealColor(meal.mealType).withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(_getMealIcon(meal.mealType), color: _getMealColor(meal.mealType), size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    meal.name,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'P: ${meal.protein.toStringAsFixed(0)}g  C: ${meal.carbs.toStringAsFixed(0)}g  F: ${meal.fat.toStringAsFixed(0)}g',
                    style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Column(
              children: [
                Text('${meal.calories.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.calories)),
                const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _getMealColor(String type) {
    switch (type) {
      case 'breakfast': case 'sang': return const Color(0xFFFF9800);
      case 'lunch': case 'trua': return const Color(0xFF4CAF50);
      case 'dinner': case 'toi': return const Color(0xFF3F51B5);
      default: return const Color(0xFF9C27B0);
    }
  }

  IconData _getMealIcon(String type) {
    switch (type) {
      case 'breakfast': case 'sang': return Icons.wb_sunny;
      case 'lunch': case 'trua': return Icons.lunch_dining;
      case 'dinner': case 'toi': return Icons.dinner_dining;
      default: return Icons.fastfood;
    }
  }

  void _showAddMealDialog(BuildContext context, DateTime date) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: _AddMealSheet(date: date),
      ),
    );
  }

  void _showMealSuggestions(BuildContext context, double targetCal) {
    final suggestions = Provider.of<NutritionProvider>(context, listen: false)
        .getMealSuggestions(targetCal);

    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('💡 Gợi ý thực đơn', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text('Dựa trên mục tiêu ${targetCal.toStringAsFixed(0)} kcal/ngày',
                style: const TextStyle(color: AppColors.textSecondary)),
            const SizedBox(height: 16),
            ...suggestions.map((s) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(s['title'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  ...(s['items'] as List<String>).map((item) => Padding(
                    padding: const EdgeInsets.only(left: 8, bottom: 2),
                    child: Text('• $item', style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                  )),
                ],
              ),
            )),
          ],
        ),
      ),
    );
  }

  void _deleteMeal(BuildContext context, String mealId) {
    Provider.of<NutritionProvider>(context, listen: false).deleteMeal(mealId);
  }
}

// === Add Meal Bottom Sheet ===
class _AddMealSheet extends StatefulWidget {
  final DateTime date;
  const _AddMealSheet({required this.date});

  @override
  State<_AddMealSheet> createState() => _AddMealSheetState();
}

class _AddMealSheetState extends State<_AddMealSheet> {
  final _searchController = TextEditingController();
  final _nameController = TextEditingController();
  final _caloriesController = TextEditingController();
  final _proteinController = TextEditingController();
  final _carbsController = TextEditingController();
  final _fatController = TextEditingController();
  final _gramsController = TextEditingController(text: '100');
  String _mealType = 'sang';
  bool _isManual = false;
  FoodItem? _selectedFood;
  List<FoodItem> _searchResults = [];

  @override
  void initState() {
    super.initState();
    _searchResults = _getSortedFoodList(_mealType);
  }

  // Helper để lấy tên bữa ăn
  String _getMealTypeLabel(String mealType) {
    switch (mealType) {
      case 'sang': return 'bữa sáng';
      case 'trua': return 'bữa trưa';
      case 'toi': return 'bữa tối';
      case 'phu': return 'ăn phụ';
      default: return 'bữa ăn';
    }
  }

  // Tính điểm phù hợp của món ăn với bữa ăn
  int _getFoodRelevanceScore(FoodItem food, String mealType) {
    final name = food.name.toLowerCase();
    int score = 0;
    
    if (mealType == 'sang') {
      // Bữa sáng: ưu tiên bánh mì, phở, trứng, sữa, cháo
      if (name.contains('bánh mì')) score += 100;
      if (name.contains('phở')) score += 90;
      if (name.contains('trứng')) score += 85;
      if (name.contains('sữa')) score += 80;
      if (name.contains('cháo')) score += 75;
      if (name.contains('xôi')) score += 70;
      if (name.contains('bún')) score += 60;
      if (name.contains('chuối') || name.contains('táo')) score += 50;
      if (name.contains('cơm')) score += 30;
    } else if (mealType == 'trua') {
      // Bữa trưa: ưu tiên cơm, thịt, cá, rau
      if (name.contains('cơm')) score += 100;
      if (name.contains('thịt') || name.contains('bò') || name.contains('heo')) score += 90;
      if (name.contains('cá')) score += 85;
      if (name.contains('gà')) score += 80;
      if (name.contains('rau') || name.contains('cải') || name.contains('muống')) score += 75;
      if (name.contains('canh')) score += 70;
      if (name.contains('phở') || name.contains('bún')) score += 60;
      if (name.contains('tôm') || name.contains('mực')) score += 55;
    } else if (mealType == 'toi') {
      // Bữa tối: cân bằng, ưu tiên nhẹ hơn
      if (name.contains('cơm')) score += 90;
      if (name.contains('cá')) score += 85;
      if (name.contains('gà')) score += 80;
      if (name.contains('rau') || name.contains('cải') || name.contains('muống')) score += 85;
      if (name.contains('canh')) score += 75;
      if (name.contains('phở') || name.contains('bún')) score += 70;
      if (name.contains('tôm')) score += 65;
      if (name.contains('thịt')) score += 60;
    } else if (mealType == 'phu') {
      // Ăn phụ: ưu tiên trái cây, sữa, bánh nhẹ
      if (name.contains('chuối') || name.contains('táo') || name.contains('cam')) score += 100;
      if (name.contains('dưa') || name.contains('xoài')) score += 95;
      if (name.contains('sữa')) score += 90;
      if (name.contains('bánh') && !name.contains('bánh mì')) score += 80;
      if (name.contains('kẹo') || name.contains('snack')) score += 70;
      if (name.contains('trứng')) score += 60;
      if (name.contains('cơm') || name.contains('phở')) score += 20;
    }
    
    return score;
  }

  // Sắp xếp danh sách món ăn theo độ phù hợp với bữa ăn
  List<FoodItem> _getSortedFoodList(String mealType, {String? searchQuery}) {
    List<FoodItem> foods;
    
    if (searchQuery != null && searchQuery.isNotEmpty) {
      foods = Provider.of<NutritionProvider>(context, listen: false).searchFoods(searchQuery);
    } else {
      foods = List.from(NutritionProvider.vietnameseFoodDatabase);
    }
    
    // Sắp xếp theo điểm phù hợp
    foods.sort((a, b) {
      final scoreA = _getFoodRelevanceScore(a, mealType);
      final scoreB = _getFoodRelevanceScore(b, mealType);
      
      if (scoreB != scoreA) {
        return scoreB.compareTo(scoreA); // Điểm cao hơn lên trước
      }
      
      // Nếu điểm bằng nhau, sắp xếp theo tên
      return a.name.compareTo(b.name);
    });
    
    return foods;
  }

  // Hiển thị thông tin dinh dưỡng dự kiến
  Widget _buildNutritionPreview() {
    if (_selectedFood == null) return const SizedBox.shrink();
    
    final grams = double.tryParse(_gramsController.text) ?? 0;
    if (grams <= 0) {
      return const Text(
        'Nhập khối lượng để xem thông tin dinh dưỡng',
        style: TextStyle(fontSize: 11, color: AppColors.textSecondary, fontStyle: FontStyle.italic),
      );
    }
    
    final calories = _selectedFood!.caloriesForGrams(grams);
    final protein = _selectedFood!.proteinForGrams(grams);
    final carbs = _selectedFood!.carbsForGrams(grams);
    final fat = _selectedFood!.fatForGrams(grams);
    
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: [
        _buildNutrientInfo('🔥', calories.toStringAsFixed(0), 'kcal', AppColors.calories),
        _buildNutrientInfo('💪', protein.toStringAsFixed(1), 'g', AppColors.protein),
        _buildNutrientInfo('🌾', carbs.toStringAsFixed(1), 'g', AppColors.carbs),
        _buildNutrientInfo('🥑', fat.toStringAsFixed(1), 'g', AppColors.fat),
      ],
    );
  }

  Widget _buildNutrientInfo(String emoji, String value, String unit, Color color) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 16)),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color),
        ),
        Text(
          unit,
          style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
        ),
      ],
    );
  }

  // Hàm gợi ý khối lượng mặc định dựa trên tên món ăn VÀ bữa ăn
  int _getSuggestedGrams(String foodName, String mealType) {
    final name = foodName.toLowerCase();
    
    // Hệ số điều chỉnh theo bữa ăn
    double mealMultiplier = 1.0;
    if (mealType == 'sang') {
      mealMultiplier = 0.8; // Bữa sáng ăn ít hơn
    } else if (mealType == 'trua') {
      mealMultiplier = 1.2; // Bữa trưa ăn nhiều nhất
    } else if (mealType == 'toi') {
      mealMultiplier = 1.0; // Bữa tối vừa phải
    } else if (mealType == 'phu') {
      mealMultiplier = 0.6; // Ăn phụ ít nhất
    }
    
    int baseGrams = 100;
    
    // Cơm
    if (name.contains('cơm')) {
      baseGrams = 150;
    }
    // Phở, bún, mì
    else if (name.contains('phở') || name.contains('bún') || name.contains('mì')) {
      baseGrams = 350;
    }
    // Bánh mì
    else if (name.contains('bánh mì')) {
      baseGrams = 80;
    }
    // Trứng
    else if (name.contains('trứng')) {
      baseGrams = 50;
    }
    // Thịt, cá
    else if (name.contains('thịt') || name.contains('cá') || name.contains('gà') || 
        name.contains('bò') || name.contains('heo') || name.contains('vịt')) {
      baseGrams = 100;
    }
    // Tôm, hải sản
    else if (name.contains('tôm') || name.contains('mực') || name.contains('cua')) {
      baseGrams = 80;
    }
    // Rau
    else if (name.contains('rau') || name.contains('cải') || name.contains('muống')) {
      baseGrams = 100;
    }
    // Trái cây
    else if (name.contains('chuối') || name.contains('táo') || name.contains('cam') || 
        name.contains('dưa')) {
      baseGrams = 120;
    }
    // Sữa
    else if (name.contains('sữa')) {
      baseGrams = 200;
    }
    // Bánh ngọt, snack
    else if (name.contains('bánh') || name.contains('kẹo') || name.contains('snack')) {
      baseGrams = 50;
    }
    
    // Áp dụng hệ số bữa ăn và làm tròn đến bội số của 10
    return ((baseGrams * mealMultiplier) / 10).round() * 10;
  }

  // Hàm gợi ý các lựa chọn khối lượng nhanh theo món ăn VÀ bữa ăn
  List<int> _getQuickGramOptions(String foodName, String mealType) {
    final name = foodName.toLowerCase();
    List<int> baseOptions = [];
    
    // Cơm
    if (name.contains('cơm')) {
      baseOptions = [100, 150, 200, 250];
    }
    // Phở, bún, mì
    else if (name.contains('phở') || name.contains('bún') || name.contains('mì')) {
      baseOptions = [250, 350, 450, 550];
    }
    // Bánh mì
    else if (name.contains('bánh mì')) {
      baseOptions = [50, 80, 100, 120];
    }
    // Trứng
    else if (name.contains('trứng')) {
      baseOptions = [50, 100, 150, 200];
    }
    // Thịt, cá
    else if (name.contains('thịt') || name.contains('cá') || name.contains('gà') || 
        name.contains('bò') || name.contains('heo') || name.contains('vịt')) {
      baseOptions = [80, 100, 150, 200];
    }
    // Tôm, hải sản
    else if (name.contains('tôm') || name.contains('mực') || name.contains('cua')) {
      baseOptions = [50, 80, 100, 150];
    }
    // Rau
    else if (name.contains('rau') || name.contains('cải') || name.contains('muống')) {
      baseOptions = [80, 100, 150, 200];
    }
    // Trái cây
    else if (name.contains('chuối') || name.contains('táo') || name.contains('cam') || 
        name.contains('dưa')) {
      baseOptions = [100, 120, 150, 200];
    }
    // Sữa
    else if (name.contains('sữa')) {
      baseOptions = [150, 200, 250, 300];
    }
    // Bánh ngọt, snack
    else if (name.contains('bánh') || name.contains('kẹo') || name.contains('snack')) {
      baseOptions = [30, 50, 80, 100];
    }
    // Mặc định
    else {
      baseOptions = [50, 100, 150, 200];
    }
    
    // Điều chỉnh theo bữa ăn
    if (mealType == 'sang') {
      // Bữa sáng: giảm 20%
      return baseOptions.map((g) => ((g * 0.8) / 10).round() * 10).toList();
    } else if (mealType == 'trua') {
      // Bữa trưa: tăng 20%
      return baseOptions.map((g) => ((g * 1.2) / 10).round() * 10).toList();
    } else if (mealType == 'phu') {
      // Ăn phụ: giảm 40%
      return baseOptions.map((g) => ((g * 0.6) / 10).round() * 10).toList();
    }
    
    // Bữa tối: giữ nguyên
    return baseOptions;
  }

  @override
  Widget build(BuildContext context) {
    final keyboardHeight = MediaQuery.of(context).viewInsets.bottom;
    
    return DraggableScrollableSheet(
      initialChildSize: 0.9,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      snap: true,
      snapSizes: const [0.9],
      builder: (context, scrollController) {
        return Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2),
                blurRadius: 20,
                offset: const Offset(0, -5),
              ),
            ],
          ),
          child: Column(
            children: [
              // Header cố định - compact
              Container(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
                decoration: const BoxDecoration(
                  borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                ),
                child: Column(
                  children: [
                    Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Text('Thêm bữa ăn', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                        const Spacer(),
                        // Meal type compact dropdown
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: AppColors.primary.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: AppColors.primary.withOpacity(0.3)),
                          ),
                          child: DropdownButton<String>(
                            value: _mealType,
                            underline: const SizedBox(),
                            isDense: true,
                            dropdownColor: AppColors.surface,
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.primary),
                            items: const [
                              DropdownMenuItem(value: 'sang', child: Text('🌅 Sáng')),
                              DropdownMenuItem(value: 'trua', child: Text('☀️ Trưa')),
                              DropdownMenuItem(value: 'toi', child: Text('🌙 Tối')),
                              DropdownMenuItem(value: 'phu', child: Text('🍎 Phụ')),
                            ],
                            onChanged: (val) {
                              setState(() {
                                _mealType = val!;
                                _searchResults = _getSortedFoodList(_mealType, searchQuery: _searchController.text);
                                if (_selectedFood != null) {
                                  _gramsController.text = _getSuggestedGrams(_selectedFood!.name, _mealType).toString();
                                }
                              });
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Toggle compact
                    Container(
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLight,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: GestureDetector(
                              onTap: () => setState(() {
                                _isManual = false;
                                _selectedFood = null;
                              }),
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                decoration: BoxDecoration(
                                  color: !_isManual ? AppColors.primary : Colors.transparent,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text('📋 Danh sách', textAlign: TextAlign.center,
                                    style: TextStyle(fontWeight: FontWeight.w600, color: !_isManual ? Colors.white : AppColors.textSecondary, fontSize: 12)),
                              ),
                            ),
                          ),
                          Expanded(
                            child: GestureDetector(
                              onTap: () => setState(() => _isManual = true),
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                decoration: BoxDecoration(
                                  color: _isManual ? AppColors.primary : Colors.transparent,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text('✏️ Nhập tay', textAlign: TextAlign.center,
                                    style: TextStyle(fontWeight: FontWeight.w600, color: _isManual ? Colors.white : AppColors.textSecondary, fontSize: 12)),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            
            // Ô tìm kiếm - cố định (chỉ hiện khi chế độ danh sách)
            if (!_isManual)
              Container(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                color: AppColors.surface,
                child: Column(
                  children: [
                    TextField(
                      controller: _searchController,
                      decoration: InputDecoration(
                        hintText: 'Tìm món ăn cho ${_getMealTypeLabel(_mealType)}...',
                        hintStyle: const TextStyle(fontSize: 13),
                        prefixIcon: const Icon(Icons.search, size: 20),
                        contentPadding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                      onChanged: (val) {
                        setState(() {
                          _searchResults = _getSortedFoodList(_mealType, searchQuery: val);
                        });
                      },
                    ),
                    const SizedBox(height: 6),
                    // Indicator compact
                    Row(
                      children: [
                        const Icon(Icons.auto_awesome, size: 12, color: AppColors.primary),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            'Sắp xếp phù hợp với ${_getMealTypeLabel(_mealType)}',
                            style: const TextStyle(fontSize: 10, color: AppColors.textSecondary, fontStyle: FontStyle.italic),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            
            // Nội dung scrollable
            Expanded(
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                children: [

                  if (!_isManual) ...[
                    // Food list - compact
                    ..._searchResults.take(10).map((food) {
                      final isSelected = _selectedFood?.id == food.id;
                      return GestureDetector(
                        onTap: () {
                          setState(() {
                            _selectedFood = food;
                            _gramsController.text = _getSuggestedGrams(food.name, _mealType).toString();
                          });
                        },
                        child: Container(
                          margin: const EdgeInsets.only(bottom: 6),
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: isSelected ? AppColors.primary.withOpacity(0.15) : AppColors.cardDark,
                            borderRadius: BorderRadius.circular(10),
                            border: isSelected ? Border.all(color: AppColors.primary, width: 2) : null,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(food.name, style: TextStyle(fontWeight: isSelected ? FontWeight.bold : FontWeight.w500, fontSize: 13)),
                                    const SizedBox(height: 2),
                                    Text('${food.caloriesPer100g.toStringAsFixed(0)} kcal | P:${food.proteinPer100g.toStringAsFixed(0)}g C:${food.carbsPer100g.toStringAsFixed(0)}g F:${food.fatPer100g.toStringAsFixed(0)}g',
                                        style: const TextStyle(fontSize: 10, color: AppColors.textSecondary)),
                                  ],
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AppColors.surfaceLight,
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(food.category, style: const TextStyle(fontSize: 9, color: AppColors.textHint)),
                              ),
                            ],
                          ),
                        ),
                      );
                    }),

                  ] else ...[
                    // Manual entry - compact
                    TextField(controller: _nameController, decoration: const InputDecoration(labelText: 'Tên món ăn', labelStyle: TextStyle(fontSize: 12), contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12))),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(child: TextField(controller: _caloriesController, decoration: const InputDecoration(labelText: 'Calo', labelStyle: TextStyle(fontSize: 12), suffixText: 'kcal', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)), keyboardType: TextInputType.number)),
                        const SizedBox(width: 8),
                        Expanded(child: TextField(controller: _proteinController, decoration: const InputDecoration(labelText: 'Protein', labelStyle: TextStyle(fontSize: 12), suffixText: 'g', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)), keyboardType: TextInputType.number)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(child: TextField(controller: _carbsController, decoration: const InputDecoration(labelText: 'Carbs', labelStyle: TextStyle(fontSize: 12), suffixText: 'g', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)), keyboardType: TextInputType.number)),
                        const SizedBox(width: 8),
                        Expanded(child: TextField(controller: _fatController, decoration: const InputDecoration(labelText: 'Chất béo', labelStyle: TextStyle(fontSize: 12), suffixText: 'g', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)), keyboardType: TextInputType.number)),
                      ],
                    ),
                  ],
                ],
              ),
            ),

            // Phần nhập khối lượng - cố định (chỉ hiện khi có selectedFood)
            if (!_isManual && _selectedFood != null)
              Container(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                color: AppColors.surface,
                child: Column(
                  children: [
                    // Gram input compact
                    TextField(
                      controller: _gramsController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Khối lượng',
                        labelStyle: TextStyle(fontSize: 12),
                        suffixText: 'g',
                        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                      onChanged: (value) => setState(() {}),
                    ),
                    const SizedBox(height: 6),
                    // Quick options - compact
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: _getQuickGramOptions(_selectedFood!.name, _mealType).map((grams) {
                        final isSelected = _gramsController.text == grams.toString();
                        return GestureDetector(
                          onTap: () => setState(() => _gramsController.text = grams.toString()),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: isSelected ? AppColors.primary : AppColors.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                color: AppColors.primary.withOpacity(isSelected ? 1 : 0.3),
                                width: isSelected ? 2 : 1,
                              ),
                            ),
                            child: Text(
                              '${grams}g',
                              style: TextStyle(
                                fontSize: 12,
                                color: isSelected ? Colors.white : AppColors.primary,
                                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 8),
                  ],
                ),
              ),

            // Nutrition preview - cố định ngay trên button (chỉ hiện khi có selectedFood)
            if (!_isManual && _selectedFood != null)
              Container(
                margin: const EdgeInsets.fromLTRB(20, 0, 20, 0),
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppColors.primary.withOpacity(0.2)),
                ),
                child: Column(
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.info_outline, size: 14, color: AppColors.primary),
                        const SizedBox(width: 4),
                        const Text(
                          'Dinh dưỡng dự kiến:',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.primary),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    _buildNutritionPreview(),
                  ],
                ),
              ),

            // Button cố định ở dưới
            Container(
              padding: EdgeInsets.fromLTRB(20, 8, 20, 8 + keyboardHeight),
              decoration: BoxDecoration(
                color: AppColors.surface,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.1),
                    blurRadius: 8,
                    offset: const Offset(0, -2),
                  ),
                ],
              ),
              child: SizedBox(
                width: double.infinity,
                height: 44,
                child: ElevatedButton(
                  onPressed: _addMeal,
                  child: const Text('Thêm bữa ăn', style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
                ),
              ),
            ),
          ],
        ),
        );
      },
    );
  }

  void _addMeal() {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;
    final date = widget.date;

    MealModel? meal;

    if (!_isManual && _selectedFood != null) {
      final grams = double.tryParse(_gramsController.text) ?? 100;
      final food = _selectedFood!;
      meal = MealModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: userId,
        name: food.name,
        foodId: food.id,
        date: DateTime(date.year, date.month, date.day, DateTime.now().hour, DateTime.now().minute),
        mealType: _mealType,
        weightGrams: grams,
        calories: food.caloriesForGrams(grams),
        protein: food.proteinForGrams(grams),
        carbs: food.carbsForGrams(grams),
        fat: food.fatForGrams(grams),
      );
    } else if (_isManual && _nameController.text.isNotEmpty) {
      meal = MealModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: userId,
        name: _nameController.text,
        date: DateTime(date.year, date.month, date.day, DateTime.now().hour, DateTime.now().minute),
        mealType: _mealType,
        calories: double.tryParse(_caloriesController.text) ?? 0,
        protein: double.tryParse(_proteinController.text) ?? 0,
        carbs: double.tryParse(_carbsController.text) ?? 0,
        fat: double.tryParse(_fatController.text) ?? 0,
      );
    }

    if (meal != null) {
      Provider.of<NutritionProvider>(context, listen: false).addMeal(meal);
      Navigator.pop(context);
    }
  }
}

// === Calorie Ring Painter ===
class _CalorieRingPainter extends CustomPainter {
  final double progress;
  final bool consumed;

  _CalorieRingPainter({required this.progress, required this.consumed});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - 4;

    final bgPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..color = AppColors.surfaceLight;
    canvas.drawCircle(center, radius, bgPaint);

    final progressPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round
      ..shader = consumed
          ? const LinearGradient(colors: [Color(0xFFE53935), Color(0xFFFF5722)]).createShader(Rect.fromCircle(center: center, radius: radius))
          : AppColors.calorieGradient.createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      2 * math.pi * progress.clamp(0.0, 1.0),
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
