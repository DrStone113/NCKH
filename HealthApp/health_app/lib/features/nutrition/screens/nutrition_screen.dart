import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../models/meal_model.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/animated_counter.dart';
import 'dart:math' as math;
class NutritionScreen extends StatefulWidget {
  const NutritionScreen({super.key});

  @override
  State<NutritionScreen> createState() => _NutritionScreenState();
}

class _NutritionScreenState extends State<NutritionScreen> {
  void _showDatePicker(BuildContext context, NutritionProvider provider, String userId) {
    DateTime viewMonth = DateTime(provider.selectedDate.year, provider.selectedDate.month);

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final now = DateTime.now();
          final daysInMonth = DateUtils.getDaysInMonth(viewMonth.year, viewMonth.month);
          final firstWeekday = DateTime(viewMonth.year, viewMonth.month, 1).weekday % 7; // 0=Sun

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
                        viewMonth = DateTime(viewMonth.year, viewMonth.month - 1);
                      }),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                    Text(
                      '${_monthLabel(viewMonth.month)} ${viewMonth.year}',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    IconButton(
                      icon: const Icon(Icons.chevron_right),
                      onPressed: () => setModalState(() {
                        viewMonth = DateTime(viewMonth.year, viewMonth.month + 1);
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
                    final date = DateTime(viewMonth.year, viewMonth.month, day);
                    final isFuture = date.isAfter(now);
                    final isSelected = date.year == provider.selectedDate.year &&
                        date.month == provider.selectedDate.month &&
                        date.day == provider.selectedDate.day;
                    final isToday = date.year == now.year && date.month == now.month && date.day == now.day;

                    return GestureDetector(
                      onTap: () {
                        provider.loadMealsForDate(userId, date);
                        Navigator.pop(ctx);
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: isSelected
                              ? AppColors.primary
                              : isToday
                                  ? AppColors.primary.withValues(alpha: 0.08)
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
                                      ? AppColors.textSecondary
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
    // Cho phép xem các ngày tương lai để lập kế hoạch
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
                      icon: const Icon(Icons.chevron_right, size: 20),
                      onPressed: () => _changeDate(context, 1),
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
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Text('Bữa ăn $dateLabel',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                        overflow: TextOverflow.ellipsis),
                  ),
                  const SizedBox(width: 8),
                  Wrap(
                    spacing: 6,
                    children: [
                      if (nutritionProvider.completedMealsCount > 0)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: AppColors.success.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.check_circle, size: 12, color: AppColors.success),
                              const SizedBox(width: 4),
                              Text(
                                '${nutritionProvider.completedMealsCount} đã ăn',
                                style: const TextStyle(fontSize: 11, color: AppColors.success, fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      if (nutritionProvider.pendingMealsCount > 0)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: AppColors.warning.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.schedule, size: 12, color: AppColors.warning),
                              const SizedBox(width: 4),
                              Text(
                                '${nutritionProvider.pendingMealsCount} sắp ăn',
                                style: const TextStyle(fontSize: 11, color: AppColors.warning, fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
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
              ..._buildMealsByType(context, nutritionProvider),
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
        Flexible(
          child: AnimatedCounter(
            value: value,
            decimals: 0,
            suffix: ' kcal',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color),
          ),
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
            Flexible(
              child: Text(
                '${grams.toStringAsFixed(1)}g (${pct.toStringAsFixed(0)}%)',
                style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600),
                overflow: TextOverflow.ellipsis,
              ),
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
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: AppColors.error,
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline, color: Colors.white, size: 22),
            SizedBox(width: 6),
            Text('Xoá', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
      confirmDismiss: (_) async => await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text('Xác nhận xoá'),
          content: Text('Xoá "${meal.name}"?'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Huỷ')),
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
              child: const Text('Xoá'),
            ),
          ],
        ),
      ),
      onDismissed: (_) {
        _deleteMeal(context, meal.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Đã xoá "${meal.name}"'), backgroundColor: AppColors.success),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: meal.isCompleted ? AppColors.success.withValues(alpha: 0.05) : AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: meal.isCompleted ? AppColors.success.withValues(alpha: 0.3) : AppColors.surfaceLight,
            width: 1.5,
          ),
        ),
        child: Column(
          children: [
            // Header: tên món + toggle + calo tổng
            GestureDetector(
              onTap: () => Provider.of<NutritionProvider>(context, listen: false).toggleMealCompleted(meal.id),
              onLongPress: () => _showAddItemToMeal(context, meal),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
                child: Row(
                  children: [
                    Container(
                      width: 34, height: 34,
                      decoration: BoxDecoration(
                        color: meal.isCompleted
                            ? AppColors.success.withValues(alpha: 0.15)
                            : _getMealColor(meal.mealType).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        meal.isCompleted ? Icons.check_circle : _getMealIcon(meal.mealType),
                        color: meal.isCompleted ? AppColors.success : _getMealColor(meal.mealType),
                        size: 18,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            meal.name,
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                              decoration: meal.isCompleted ? TextDecoration.lineThrough : null,
                              color: meal.isCompleted ? AppColors.textSecondary : AppColors.textPrimary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            'P:${meal.protein.toStringAsFixed(0)}g  C:${meal.carbs.toStringAsFixed(0)}g  F:${meal.fat.toStringAsFixed(0)}g',
                            style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          meal.calories.toStringAsFixed(0),
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                            color: meal.isCompleted ? AppColors.textSecondary : AppColors.calories,
                          ),
                        ),
                        const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
                      ],
                    ),
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: meal.isCompleted
                            ? AppColors.success.withValues(alpha: 0.12)
                            : AppColors.warning.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        meal.isCompleted ? '✓' : '⏳',
                        style: TextStyle(
                          fontSize: 11,
                          color: meal.isCompleted ? AppColors.success : AppColors.warning,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Danh sách thành phần
            if (meal.items.isNotEmpty) ...[
              const Divider(height: 1, indent: 12, endIndent: 12),
              ...meal.items.map((item) => Padding(
                padding: const EdgeInsets.fromLTRB(56, 4, 12, 4),
                child: Row(
                  children: [
                    const Icon(Icons.fiber_manual_record, size: 6, color: AppColors.textHint),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${item.name}  ${item.weightGrams.toStringAsFixed(0)}g',
                        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      '${item.calories.toStringAsFixed(0)} kcal',
                      style: const TextStyle(fontSize: 11, color: AppColors.textHint),
                    ),
                  ],
                ),
              )),
              // Nút thêm thành phần
              GestureDetector(
                onTap: () => _showAddItemToMeal(context, meal),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(56, 4, 12, 8),
                  child: Row(
                    children: [
                      Icon(Icons.add, size: 14, color: _getMealColor(meal.mealType).withValues(alpha: 0.7)),
                      const SizedBox(width: 4),
                      Text(
                        'Thêm thành phần',
                        style: TextStyle(fontSize: 11, color: _getMealColor(meal.mealType).withValues(alpha: 0.7)),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _showAddItemToMeal(BuildContext context, MealModel meal) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: _AddItemSheet(meal: meal),
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
        child: _AddMealSheet(date: date, initialMealType: _getDefaultMealType()),
      ),
    );
  }

  /// Gợi ý loại bữa ăn dựa trên giờ hiện tại
  String _getDefaultMealType() {
    final hour = DateTime.now().hour;
    if (hour >= 5 && hour < 10) return 'sang';
    if (hour >= 10 && hour < 14) return 'trua';
    if (hour >= 17 && hour < 21) return 'toi';
    return 'phu';
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

  /// Nhóm bữa ăn theo loại và hiển thị có header
  List<Widget> _buildMealsByType(BuildContext context, NutritionProvider provider) {
    final mealGroups = <String, List<MealModel>>{
      'sang': [],
      'trua': [],
      'toi': [],
      'phu': [],
    };

    for (final meal in provider.todayMeals) {
      final type = meal.mealType;
      if (mealGroups.containsKey(type)) {
        mealGroups[type]!.add(meal);
      } else {
        mealGroups['phu']!.add(meal);
      }
    }

    final groupOrder = ['sang', 'trua', 'toi', 'phu'];
    final groupLabels = {
      'sang': '🌅 Bữa sáng',
      'trua': '☀️ Bữa trưa',
      'toi': '🌙 Bữa tối',
      'phu': '🍎 Ăn phụ',
    };

    final widgets = <Widget>[];
    int delay = 300;

    for (final type in groupOrder) {
      final meals = mealGroups[type]!;
      if (meals.isEmpty) continue;

      final groupCal = meals.fold(0.0, (s, m) => s + m.calories);
      final completedCount = meals.where((m) => m.isCompleted).length;

      widgets.add(AnimatedCard(
        delay: delay,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 8, top: 4),
          child: Row(
            children: [
              Text(
                groupLabels[type]!,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              Text(
                '${groupCal.toStringAsFixed(0)} kcal',
                style: const TextStyle(fontSize: 12, color: AppColors.calories, fontWeight: FontWeight.w600),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: completedCount == meals.length
                      ? AppColors.success.withValues(alpha: 0.12)
                      : AppColors.warning.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '$completedCount/${meals.length}',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: completedCount == meals.length ? AppColors.success : AppColors.warning,
                  ),
                ),
              ),
            ],
          ),
        ),
      ));
      delay += 30;

      for (final meal in meals) {
        widgets.add(AnimatedCard(
          delay: delay,
          child: _buildMealCard(context, meal),
        ));
        delay += 40;
      }

      // Add meal to this group button
      widgets.add(AnimatedCard(
        delay: delay,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: GestureDetector(
            onTap: () => _showAddMealDialogForType(context, provider.selectedDate, type),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: _getMealColor(type).withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: _getMealColor(type).withValues(alpha: 0.2),
                  style: BorderStyle.solid,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.add, size: 16, color: _getMealColor(type)),
                  const SizedBox(width: 6),
                  Text(
                    'Thêm vào ${groupLabels[type]!.split(' ').skip(1).join(' ')}',
                    style: TextStyle(fontSize: 12, color: _getMealColor(type), fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
          ),
        ),
      ));
      delay += 20;
    }

    // Show empty meal types as placeholders
    for (final type in groupOrder) {
      if (mealGroups[type]!.isNotEmpty) continue;
      widgets.add(AnimatedCard(
        delay: delay,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: GestureDetector(
            onTap: () => _showAddMealDialogForType(context, provider.selectedDate, type),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
              decoration: BoxDecoration(
                color: AppColors.cardDark,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.surfaceLight),
              ),
              child: Row(
                children: [
                  Icon(_getMealIcon(type), size: 20, color: _getMealColor(type).withValues(alpha: 0.5)),
                  const SizedBox(width: 12),
                  Text(
                    groupLabels[type]!,
                    style: const TextStyle(fontSize: 13, color: AppColors.textHint),
                  ),
                  const Spacer(),
                  Icon(Icons.add_circle_outline, size: 18, color: _getMealColor(type).withValues(alpha: 0.5)),
                ],
              ),
            ),
          ),
        ),
      ));
      delay += 20;
    }

    return widgets;
  }

  void _showAddMealDialogForType(BuildContext context, DateTime date, String mealType) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: _AddMealSheet(date: date, initialMealType: mealType),
      ),
    );
  }
}

// Sheet tạo món ăn mới (có tên món + thêm nhiều thành phần)
// ═══════════════════════════════════════════════════════════════
class _AddMealSheet extends StatefulWidget {
  final DateTime date;
  final String initialMealType;
  const _AddMealSheet({required this.date, this.initialMealType = 'sang'});

  @override
  State<_AddMealSheet> createState() => _AddMealSheetState();
}

class _AddMealSheetState extends State<_AddMealSheet> with SingleTickerProviderStateMixin {
  final _mealNameController = TextEditingController();
  late String _mealType;
  final List<MealItem> _items = [];
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _mealType = widget.initialMealType;
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _mealNameController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  double get _totalCal => _items.fold(0, (s, i) => s + i.calories);
  double get _totalProtein => _items.fold(0, (s, i) => s + i.protein);
  double get _totalCarbs => _items.fold(0, (s, i) => s + i.carbs);
  double get _totalFat => _items.fold(0, (s, i) => s + i.fat);

  void _addItem(MealItem item) => setState(() => _items.add(item));
  void _removeItem(int index) => setState(() => _items.removeAt(index));

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

  void _saveAsTemplate() {
    if (_items.isEmpty) return;
    final mealName = _mealNameController.text.trim().isNotEmpty
        ? _mealNameController.text.trim()
        : _items.length == 1 ? _items.first.name : '${_items.first.name} + ${_items.length - 1} món';

    final template = SavedMealTemplate(
      id: 'user_${DateTime.now().millisecondsSinceEpoch}',
      name: mealName,
      emoji: '⭐',
      items: _items.map((i) => SavedMealItemTemplate(
        foodId: i.foodId,
        name: i.name,
        defaultGrams: i.weightGrams,
      )).toList(),
    );
    Provider.of<NutritionProvider>(context, listen: false).saveMealTemplate(template);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Đã lưu "$mealName" vào danh sách yêu thích'), backgroundColor: AppColors.success),
    );
  }

  void _loadFromTemplate(SavedMealTemplate template) {
    final db = NutritionProvider.vietnameseFoodDatabase;
    final newItems = <MealItem>[];
    for (final t in template.items) {
      final food = db.where((f) => f.id == t.foodId).firstOrNull;
      if (food != null) {
        newItems.add(food.toMealItem(
          itemId: '${t.foodId}_${DateTime.now().millisecondsSinceEpoch}',
          grams: t.defaultGrams,
        ));
      } else {
        // Fallback nếu không tìm thấy trong db
        newItems.add(MealItem(
          id: '${t.foodId}_${DateTime.now().millisecondsSinceEpoch}',
          foodId: t.foodId,
          name: t.name,
          weightGrams: t.defaultGrams,
          calories: 0, protein: 0, carbs: 0, fat: 0,
        ));
      }
    }
    setState(() {
      _items.clear();
      _items.addAll(newItems);
      if (_mealNameController.text.isEmpty) {
        _mealNameController.text = template.name;
      }
    });
    // Switch to ingredient tab to review/edit
    _tabController.animateTo(2);
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
              // ── Header ──
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
                child: Column(
                  children: [
                    Center(child: Container(width: 40, height: 4,
                        decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2)))),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Text('Thêm món ăn', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                        const Spacer(),
                        // Meal type pill
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: _getMealTypeColor(_mealType).withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: DropdownButton<String>(
                            value: _mealType,
                            underline: const SizedBox(),
                            isDense: true,
                            dropdownColor: AppColors.surface,
                            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: _getMealTypeColor(_mealType)),
                            items: const [
                              DropdownMenuItem(value: 'sang', child: Text('🌅 Sáng')),
                              DropdownMenuItem(value: 'trua', child: Text('☀️ Trưa')),
                              DropdownMenuItem(value: 'toi', child: Text('🌙 Tối')),
                              DropdownMenuItem(value: 'phu', child: Text('🍎 Phụ')),
                            ],
                            onChanged: (v) => setState(() => _mealType = v!),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    // Tên món
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
                    // Tab bar
                    TabBar(
                      controller: _tabController,
                      labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                      unselectedLabelStyle: const TextStyle(fontSize: 12),
                      indicatorSize: TabBarIndicatorSize.tab,
                      tabs: const [
                        Tab(text: '⭐ Gợi ý'),
                        Tab(text: '❤️ Đã lưu'),
                        Tab(text: '🔍 Tìm kiếm'),
                      ],
                    ),
                  ],
                ),
              ),

              // ── Thành phần đã thêm (hiện khi có items) ──
              if (_items.isNotEmpty)
                _buildItemsSummary(),

              // ── Tab content ──
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    // Tab 0: Gợi ý mẫu
                    _SampleMealsTab(onLoad: _loadFromTemplate),
                    // Tab 1: Đã lưu
                    _SavedMealsTab(onLoad: _loadFromTemplate),
                    // Tab 2: Tìm kiếm nguyên liệu
                    _FoodPickerList(mealType: _mealType, onItemAdded: _addItem),
                  ],
                ),
              ),

              // ── Bottom buttons ──
              _buildBottomBar(),
            ],
          ),
        );
      },
    );
  }

  Widget _buildItemsSummary() {
    return Container(
      margin: const EdgeInsets.fromLTRB(20, 8, 20, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.receipt_long, size: 14, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text('${_items.length} thành phần',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('${_totalCal.toStringAsFixed(0)} kcal',
                  style: const TextStyle(fontSize: 13, color: AppColors.calories, fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: _items.asMap().entries.map((e) => GestureDetector(
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
                    Text('${e.value.name} ${e.value.weightGrams.toStringAsFixed(0)}g',
                        style: const TextStyle(fontSize: 11)),
                    const SizedBox(width: 4),
                    const Icon(Icons.close, size: 12, color: AppColors.error),
                  ],
                ),
              ),
            )).toList(),
          ),
          const SizedBox(height: 4),
          Text('P:${_totalProtein.toStringAsFixed(0)}g  C:${_totalCarbs.toStringAsFixed(0)}g  F:${_totalFat.toStringAsFixed(0)}g',
              style: const TextStyle(fontSize: 10, color: AppColors.textSecondary)),
        ],
      ),
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: EdgeInsets.fromLTRB(20, 8, 20, 16 + MediaQuery.of(context).viewInsets.bottom),
      decoration: BoxDecoration(
        color: AppColors.surface,
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 8, offset: const Offset(0, -2))],
      ),
      child: Row(
        children: [
          // Nút lưu template (chỉ hiện khi có items)
          if (_items.isNotEmpty) ...[
            IconButton(
              onPressed: _saveAsTemplate,
              icon: const Icon(Icons.bookmark_add_outlined),
              tooltip: 'Lưu vào yêu thích',
              style: IconButton.styleFrom(
                backgroundColor: AppColors.surfaceLight,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: OutlinedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Huỷ'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            flex: 2,
            child: ElevatedButton.icon(
              onPressed: _items.isEmpty ? null : _save,
              icon: const Icon(Icons.check, size: 16),
              label: Text(_items.isEmpty ? 'Chọn thành phần' : 'Lưu món ăn (${_items.length})'),
            ),
          ),
        ],
      ),
    );
  }

  Color _getMealTypeColor(String type) {
    switch (type) {
      case 'sang': return const Color(0xFFFF9800);
      case 'trua': return const Color(0xFF4CAF50);
      case 'toi': return const Color(0xFF3F51B5);
      default: return const Color(0xFF9C27B0);
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Tab Gợi ý — món mẫu phổ biến
// ═══════════════════════════════════════════════════════════════
class _SampleMealsTab extends StatelessWidget {
  final void Function(SavedMealTemplate) onLoad;
  const _SampleMealsTab({required this.onLoad});

  @override
  Widget build(BuildContext context) {
    final db = NutritionProvider.vietnameseFoodDatabase;
    final samples = NutritionProvider.sampleMeals;
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      itemCount: samples.length,
      itemBuilder: (ctx, i) => _TemplateCard(
        template: samples[i],
        db: db,
        onTap: () => onLoad(samples[i]),
        canDelete: false,
        onDelete: null,
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Tab Đã lưu — món người dùng tự lưu
// ═══════════════════════════════════════════════════════════════
class _SavedMealsTab extends StatelessWidget {
  final void Function(SavedMealTemplate) onLoad;
  const _SavedMealsTab({required this.onLoad});

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<NutritionProvider>(context);
    final saved = provider.savedMeals;
    final db = NutritionProvider.vietnameseFoodDatabase;

    if (saved.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.bookmark_border, size: 48, color: AppColors.textHint),
            SizedBox(height: 12),
            Text('Chưa có món nào được lưu', style: TextStyle(color: AppColors.textSecondary)),
            SizedBox(height: 4),
            Text('Tạo món ăn rồi nhấn 🔖 để lưu lại', style: TextStyle(fontSize: 12, color: AppColors.textHint)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      itemCount: saved.length,
      itemBuilder: (ctx, i) => _TemplateCard(
        template: saved[i],
        db: db,
        onTap: () => onLoad(saved[i]),
        canDelete: true,
        onDelete: () => provider.deleteSavedMeal(saved[i].id),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Card hiển thị 1 template món ăn
// ═══════════════════════════════════════════════════════════════
class _TemplateCard extends StatelessWidget {
  final SavedMealTemplate template;
  final List<FoodItem> db;
  final VoidCallback onTap;
  final bool canDelete;
  final VoidCallback? onDelete;

  const _TemplateCard({
    required this.template,
    required this.db,
    required this.onTap,
    required this.canDelete,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final cal = template.estimatedCalories(db);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.surfaceLight),
        ),
        child: Row(
          children: [
            // Emoji
            Container(
              width: 44, height: 44,
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(child: Text(template.emoji, style: const TextStyle(fontSize: 22))),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(template.name,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                  const SizedBox(height: 3),
                  Text(
                    template.items.map((i) => '${i.name} ${i.defaultGrams.toStringAsFixed(0)}g').join(' · '),
                    style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('~${cal.toStringAsFixed(0)}',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.calories)),
                const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
              ],
            ),
            if (canDelete) ...[
              const SizedBox(width: 8),
              GestureDetector(
                onTap: onDelete,
                child: const Icon(Icons.delete_outline, size: 18, color: AppColors.error),
              ),
            ] else ...[
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward_ios, size: 14, color: AppColors.textHint),
            ],
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Sheet thêm thành phần vào món ăn đã có
// ═══════════════════════════════════════════════════════════════
class _AddItemSheet extends StatelessWidget {
  final MealModel meal;
  const _AddItemSheet({required this.meal});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.8,
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
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 8),
                child: Column(
                  children: [
                    Center(child: Container(width: 40, height: 4,
                        decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2)))),
                    const SizedBox(height: 12),
                    Text('Thêm vào "${meal.name}"',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 4),
                  ],
                ),
              ),
              Expanded(
                child: _FoodPickerList(
                  mealType: meal.mealType,
                  onItemAdded: (item) {
                    final updated = meal.copyWith(items: [...meal.items, item]);
                    Provider.of<NutritionProvider>(ctx, listen: false).updateMeal(updated);
                    Navigator.pop(ctx);
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(
                        content: Text('Đã thêm "${item.name}" vào "${meal.name}"'),
                        backgroundColor: AppColors.success,
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Widget chọn thực phẩm từ database (dùng chung cho cả 2 sheet)
// ═══════════════════════════════════════════════════════════════
class _FoodPickerList extends StatefulWidget {
  final String mealType;
  final void Function(MealItem item) onItemAdded;
  const _FoodPickerList({required this.mealType, required this.onItemAdded});

  @override
  State<_FoodPickerList> createState() => _FoodPickerListState();
}

class _FoodPickerListState extends State<_FoodPickerList> {
  final _searchCtrl = TextEditingController();
  final _gramsCtrl = TextEditingController(text: '100');
  FoodItem? _selected;
  List<FoodItem> _results = [];

  @override
  void initState() {
    super.initState();
    _results = _sorted('');
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _gramsCtrl.dispose();
    super.dispose();
  }

  List<FoodItem> _sorted(String q) {
    final all = q.isEmpty
        ? List<FoodItem>.from(NutritionProvider.vietnameseFoodDatabase)
        : NutritionProvider.vietnameseFoodDatabase
            .where((f) => f.name.toLowerCase().contains(q.toLowerCase()))
            .toList();
    // Ưu tiên theo bữa ăn
    final mealKeywords = {
      'sang': ['bánh', 'trứng', 'sữa', 'phở', 'bún', 'cháo'],
      'trua': ['cơm', 'thịt', 'cá', 'gà', 'rau'],
      'toi':  ['cơm', 'cá', 'gà', 'rau', 'đậu'],
      'phu':  ['sữa', 'trái', 'chuối', 'táo', 'cam', 'bánh'],
    };
    final keys = mealKeywords[widget.mealType] ?? [];
    all.sort((a, b) {
      final sa = keys.any((k) => a.name.toLowerCase().contains(k)) ? 1 : 0;
      final sb = keys.any((k) => b.name.toLowerCase().contains(k)) ? 1 : 0;
      return sb - sa;
    });
    return all;
  }

  void _confirm() {
    if (_selected == null) return;
    final grams = double.tryParse(_gramsCtrl.text) ?? 0;
    if (grams <= 0) return;
    final item = _selected!.toMealItem(
      itemId: '${_selected!.id}_${DateTime.now().millisecondsSinceEpoch}',
      grams: grams,
    );
    widget.onItemAdded(item);
    setState(() {
      _selected = null;
      _gramsCtrl.text = '100';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Search
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
          child: TextField(
            controller: _searchCtrl,
            decoration: const InputDecoration(
              hintText: 'Tìm nguyên liệu...',
              hintStyle: TextStyle(fontSize: 13),
              prefixIcon: Icon(Icons.search, size: 18),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (v) => setState(() {
              _results = _sorted(v);
              _selected = null;
            }),
          ),
        ),

        // Selected food gram input
        if (_selected != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(_selected!.name,
                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                      ),
                      GestureDetector(
                        onTap: () => setState(() => _selected = null),
                        child: const Icon(Icons.close, size: 16, color: AppColors.textHint),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _gramsCtrl,
                          keyboardType: TextInputType.number,
                          autofocus: true,
                          decoration: const InputDecoration(
                            labelText: 'Khối lượng',
                            suffixText: 'g',
                            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          ),
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: 10),
                      // Preview calo
                      Builder(builder: (_) {
                        final g = double.tryParse(_gramsCtrl.text) ?? 0;
                        return Column(
                          children: [
                            Text(
                              _selected!.caloriesForGrams(g).toStringAsFixed(0),
                              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.calories),
                            ),
                            const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
                          ],
                        );
                      }),
                    ],
                  ),
                  const SizedBox(height: 6),
                  // Quick gram options
                  Wrap(
                    spacing: 6,
                    children: [50, 100, 150, 200].map((g) => GestureDetector(
                      onTap: () => setState(() => _gramsCtrl.text = g.toString()),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: _gramsCtrl.text == g.toString()
                              ? AppColors.primary : AppColors.primary.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text('${g}g',
                            style: TextStyle(
                              fontSize: 11,
                              color: _gramsCtrl.text == g.toString() ? Colors.white : AppColors.primary,
                            )),
                      ),
                    )).toList(),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _confirm,
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('Thêm thành phần này'),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

        // Food list
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            itemCount: _results.length,
            itemBuilder: (ctx, i) {
              final food = _results[i];
              final isSelected = _selected?.id == food.id;
              return GestureDetector(
                onTap: () => setState(() {
                  _selected = food;
                  _gramsCtrl.text = '100';
                }),
                child: Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: isSelected ? AppColors.primary.withValues(alpha: 0.1) : AppColors.cardDark,
                    borderRadius: BorderRadius.circular(10),
                    border: isSelected ? Border.all(color: AppColors.primary, width: 1.5) : null,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(food.name,
                                style: TextStyle(
                                  fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                                  fontSize: 13,
                                )),
                            Text(
                              '${food.caloriesPer100g.toStringAsFixed(0)} kcal  P:${food.proteinPer100g.toStringAsFixed(0)}g  C:${food.carbsPer100g.toStringAsFixed(0)}g  F:${food.fatPer100g.toStringAsFixed(0)}g  /100g',
                              style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
                            ),
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
            },
          ),
        ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Calorie Ring Painter
// ═══════════════════════════════════════════════════════════════
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
          ? const LinearGradient(colors: [Color(0xFFE53935), Color(0xFFFF5722)])
              .createShader(Rect.fromCircle(center: center, radius: radius))
          : AppColors.calorieGradient
              .createShader(Rect.fromCircle(center: center, radius: radius));

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
