import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/plan_provider.dart';
import '../../../models/meal_model.dart';
import '../../../theme/app_theme.dart';
import '../../../utils/meal_nutrition_utils.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/health_surface.dart';
import '../../../models/app_state_value.dart';
import '../widgets/nutrition_overview.dart';
import '../widgets/meal_plan_card.dart';
import '../../plans/screens/plan_list_screen.dart';
import '../../plans/plan_history.dart';
import '../../plans/plan_snapshot.dart';
import '../../../widgets/meal_summary_card.dart';

class NutritionScreen extends StatefulWidget {
  const NutritionScreen({super.key, this.planLoader});
  final PlanSnapshotLoader? planLoader;

  @override
  State<NutritionScreen> createState() => _NutritionScreenState();
}

class _NutritionScreenState extends State<NutritionScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final user =
          Provider.of<UserProvider>(context, listen: false).currentUser;
      if (user != null) {
        Provider.of<NutritionProvider>(context, listen: false)
            .loadTodayMeals(user.id);
        if (widget.planLoader == null) {
          Provider.of<PlanProvider>(context, listen: false)
              .loadForUser(user.id)
              .catchError((_) => <PlanSnapshot>[]);
        }
      }
    });
  }

  void _showDatePicker(
      BuildContext context, NutritionProvider provider, String userId) {
    DateTime viewMonth =
        DateTime(provider.selectedDate.year, provider.selectedDate.month);

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final now = DateTime.now();
          final daysInMonth =
              DateUtils.getDaysInMonth(viewMonth.year, viewMonth.month);
          final firstWeekday =
              DateTime(viewMonth.year, viewMonth.month, 1).weekday % 7; // 0=Sun

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
                Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                        color: AppColors.textHint,
                        borderRadius: BorderRadius.circular(2))),
                const SizedBox(height: 16),

                // Month navigator
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.chevron_left),
                      onPressed: () => setModalState(() {
                        viewMonth =
                            DateTime(viewMonth.year, viewMonth.month - 1);
                      }),
                      padding: EdgeInsets.zero,
                      constraints:
                          const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                    Text(
                      '${_monthLabel(viewMonth.month)} ${viewMonth.year}',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    IconButton(
                      icon: const Icon(Icons.chevron_right),
                      onPressed: () => setModalState(() {
                        viewMonth =
                            DateTime(viewMonth.year, viewMonth.month + 1);
                      }),
                      padding: EdgeInsets.zero,
                      constraints:
                          const BoxConstraints(minWidth: 36, minHeight: 36),
                    ),
                  ],
                ),
                const SizedBox(height: 8),

                // Weekday headers
                Row(
                  children: ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
                      .map((d) => Expanded(
                          child: Center(
                              child: Text(d,
                                  style: const TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                      color: AppColors.textHint)))))
                      .toList(),
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
                    final isSelected =
                        date.year == provider.selectedDate.year &&
                            date.month == provider.selectedDate.month &&
                            date.day == provider.selectedDate.day;
                    final isToday = date.year == now.year &&
                        date.month == now.month &&
                        date.day == now.day;

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
                              fontWeight: isSelected || isToday
                                  ? FontWeight.bold
                                  : FontWeight.normal,
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
    const months = [
      '',
      'Tháng 1',
      'Tháng 2',
      'Tháng 3',
      'Tháng 4',
      'Tháng 5',
      'Tháng 6',
      'Tháng 7',
      'Tháng 8',
      'Tháng 9',
      'Tháng 10',
      'Tháng 11',
      'Tháng 12'
    ];
    return months[month];
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<NutritionProvider>();
    final user = context.watch<UserProvider>().currentUser;
    final sharedPlans =
        widget.planLoader == null ? context.watch<PlanProvider>() : null;
    final selected = provider.selectedDate;
    final canonical = user?.canonicalNutrition;
    final summary =
        canonical == null ? null : provider.canonicalDailySummary(canonical);
    final dateLabel =
        '${provider.isToday ? 'Hôm nay, ' : ''}${selected.day} tháng ${selected.month}';
    final retry = user == null
        ? null
        : () => provider.loadMealsForDate(user.id, selected);
    return Scaffold(
      appBar: AppBar(
          title: const Text('Dinh dưỡng'),
          automaticallyImplyLeading: false,
          actions: [
            IconButton(
                tooltip: 'Gợi ý thực đơn',
                onPressed: user?.recommendedCalories == null
                    ? null
                    : () => _showMealSuggestions(
                        context, user!.recommendedCalories!),
                icon: const Icon(Icons.auto_awesome_outlined)),
            IconButton(
                tooltip: 'Mở kế hoạch',
                onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                        builder: (_) => const PlanListScreen())),
                icon: const Icon(Icons.calendar_month_outlined)),
            IconButton(
                tooltip: 'Chọn ngày',
                onPressed: user == null
                    ? null
                    : () => _showDatePicker(context, provider, user.id),
                icon: const Icon(Icons.date_range_outlined)),
          ]),
      body: SafeArea(
          child: RefreshIndicator(
              onRefresh: () async {
                if (user != null) {
                  await Future.wait([
                    provider.loadMealsForDate(user.id, selected),
                    if (sharedPlans != null)
                      sharedPlans.loadForUser(user.id, force: true),
                  ]);
                }
              },
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 96),
                child: Center(
                    child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 720),
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                  provider.isToday
                                      ? 'Dinh dưỡng hôm nay'
                                      : 'Dinh dưỡng theo ngày',
                                  style: const TextStyle(
                                      fontSize: 30,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: -.9)),
                              const SizedBox(height: 8),
                              Text(dateLabel,
                                  style: const TextStyle(
                                      color: AppColors.textSecondary)),
                              const SizedBox(height: 20),
                              DailyDateStrip(
                                  selected: selected,
                                  onSelected: (date) {
                                    if (user != null) {
                                      provider.loadMealsForDate(user.id, date);
                                    }
                                  }),
                              const SizedBox(height: 20),
                              if (provider.isLoading)
                                const NutritionSkeleton()
                              else ...[
                                if (provider
                                        .todayMealsStatus ==
                                    DataStatus.error)
                                  Padding(
                                      padding: const EdgeInsets.only(
                                          bottom: 12),
                                      child: NutritionEmptyState(
                                          title:
                                              'Không thể tải nhật ký lúc này.',
                                          message:
                                              'Dữ liệu bên dưới chưa được xác nhận lại.',
                                          icon: Icons.cloud_off_outlined,
                                          actionLabel: 'Thử lại',
                                          onAction: retry)),
                                NutritionHeroCard(
                                    canonical: canonical, summary: summary),
                                const HealthSectionTitle('Dưỡng chất',
                                    subtitle: 'Từ các bữa ăn đã ghi nhận'),
                                NutritionMacroSummary(
                                    canonical: canonical, summary: summary),
                              ],
                              const HealthSectionTitle('Nhật ký đã ăn',
                                  subtitle:
                                      'Chỉ các bữa đã xác nhận ăn mới được tính vào tổng ngày.'),
                              if (provider.isLoading)
                                const NutritionSkeleton(lines: 2)
                              else if (provider.completedMealsCount == 0)
                                NutritionEmptyState(
                                    title: provider.isToday
                                        ? 'Bạn chưa ghi nhận bữa ăn nào hôm nay.'
                                        : 'Bạn chưa ghi nhận bữa ăn nào cho ngày này.',
                                    actionLabel: 'Thêm bữa ăn',
                                    onAction: () =>
                                        _showAddMealDialog(context, selected))
                              else
                                ..._buildMealsByType(context, provider,
                                    completed: true),
                              if (provider.pendingMealsCount > 0) ...[
                                const HealthSectionTitle(
                                    'Thực đơn dự kiến · chưa ăn',
                                    subtitle:
                                        'Món theo kế hoạch hoặc đã thêm, nhấn "Ghi nhận đã ăn" khi đã dùng.'),
                                ..._buildMealsByType(context, provider,
                                    completed: false),
                              ],
                              const SizedBox(height: 16),
                              FilledButton.icon(
                                  onPressed: () =>
                                      _showAddMealDialog(context, selected),
                                  icon: const Icon(Icons.add),
                                  label: const Text('Thêm bữa ăn')),
                            ]))),
              ))),
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
            Text('Xoá',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
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
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Huỷ')),
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
          SnackBar(
              content: Text('Đã xoá "${meal.name}"'),
              backgroundColor: AppColors.success),
        );
      },
      child: MealSummaryCard(
        name: meal.name,
        mealType: meal.mealType,
        ingredients: meal.items
            .map(MealCardIngredientView.fromMealItem)
            .toList(growable: false),
        calories: meal.calories,
        protein: meal.protein,
        carbs: meal.carbs,
        fat: meal.fat,
        completed: meal.isCompleted,
        margin: const EdgeInsets.only(bottom: 10),
        onTap: () => _showMealDetail(context, meal),
        onLongPress: () => _showAddItemToMeal(context, meal),
        actionLabel: meal.isCompleted ? 'Bỏ ghi nhận đã ăn' : 'Ghi nhận đã ăn',
        actionIcon: meal.isCompleted ? Icons.undo : Icons.check_circle_outline,
        onAction: () =>
            context.read<NutritionProvider>().toggleMealCompleted(meal.id),
      ),
    );
  }

  void _showMealDetail(BuildContext context, MealModel meal) {
    showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        showDragHandle: true,
        builder: (_) => FractionallySizedBox(
            heightFactor: .9,
            child: MealDetailContent(
              name: meal.name,
              status: meal.isCompleted
                  ? 'Đã ăn · đã ghi nhận'
                  : 'Dự kiến · chưa ghi nhận',
              nutrition: {
                'total_calories': meal.calories,
                'total_protein': meal.protein,
                'total_carbs': meal.carbs,
                'total_fat': meal.fat
              },
              content: {
                'ingredients': meal.items
                    .map((item) =>
                        {'name': item.name, 'grams': item.weightGrams})
                    .toList()
              },
              footer: OutlinedButton(
                  onPressed: () => _showAddItemToMeal(context, meal),
                  child: const Text('Thêm thành phần')),
            )));
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
    return MealPresentation.accent(type);
  }

  IconData _getMealIcon(String type) {
    return MealPresentation.mealIcon(type);
  }

  void _showAddMealDialog(BuildContext context, DateTime date) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => Padding(
        padding:
            EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child:
            _AddMealSheet(date: date, initialMealType: _getDefaultMealType()),
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
            const Text('💡 Gợi ý thực đơn',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text('Dựa trên mục tiêu ${targetCal.toStringAsFixed(0)} kcal/ngày',
                style: const TextStyle(color: AppColors.textSecondary)),
            const SizedBox(height: 16),
            ...suggestions.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(s['title'] as String,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      ...(s['items'] as List<String>).map((item) => Padding(
                            padding: const EdgeInsets.only(left: 8, bottom: 2),
                            child: Text('• $item',
                                style: const TextStyle(
                                    fontSize: 13,
                                    color: AppColors.textSecondary)),
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
  List<Widget> _buildMealsByType(
      BuildContext context, NutritionProvider provider,
      {required bool completed}) {
    final mealGroups = <String, List<MealModel>>{
      'sang': [],
      'trua': [],
      'toi': [],
      'phu': [],
    };

    for (final meal
        in provider.todayMeals.where((meal) => meal.isCompleted == completed)) {
      final type = MealTypeUtils.normalize(meal.mealType);
      mealGroups[type]!.add(meal);
    }

    final groupOrder = ['sang', 'trua', 'toi', 'phu'];
    final groupLabels = {
      'sang': 'Bữa sáng',
      'trua': 'Bữa trưa',
      'toi': 'Bữa tối',
      'phu': 'Bữa phụ',
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
                style:
                    const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              Text(
                '${groupCal.toStringAsFixed(0)} kcal',
                style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.calories,
                    fontWeight: FontWeight.w600),
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
                    color: completedCount == meals.length
                        ? AppColors.success
                        : AppColors.warning,
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
            onTap: () =>
                _showAddMealDialogForType(context, provider.selectedDate, type),
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
                    style: TextStyle(
                        fontSize: 12,
                        color: _getMealColor(type),
                        fontWeight: FontWeight.w600),
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
            onTap: () =>
                _showAddMealDialogForType(context, provider.selectedDate, type),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
              decoration: BoxDecoration(
                color: AppColors.cardDark,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.surfaceLight),
              ),
              child: Row(
                children: [
                  Icon(_getMealIcon(type),
                      size: 20,
                      color: _getMealColor(type).withValues(alpha: 0.5)),
                  const SizedBox(width: 12),
                  Text(
                    groupLabels[type]!,
                    style: const TextStyle(
                        fontSize: 13, color: AppColors.textHint),
                  ),
                  const Spacer(),
                  Icon(Icons.add_circle_outline,
                      size: 18,
                      color: _getMealColor(type).withValues(alpha: 0.5)),
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

  void _showAddMealDialogForType(
      BuildContext context, DateTime date, String mealType) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => Padding(
        padding:
            EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
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

class _AddMealSheetState extends State<_AddMealSheet>
    with SingleTickerProviderStateMixin {
  final _mealNameController = TextEditingController();
  late String _mealType;
  final List<MealItem> _items = [];
  late TabController _tabController;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _mealType = widget.initialMealType;
    _tabController = TabController(length: 3, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<NutritionProvider>(context, listen: false)
          .loadVietnameseDatabase();
    });
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

  Future<void> _save() async {
    final userId =
        Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null || _items.isEmpty || _isSaving) return;

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

    final provider = Provider.of<NutritionProvider>(context, listen: false);
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _isSaving = true);
    try {
      await provider.addMeal(meal);
      if (mounted) Navigator.pop(context);
    } catch (_) {
      if (!mounted) return;
      setState(() => _isSaving = false);
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Không thể lưu món ăn. Vui lòng thử lại.'),
          backgroundColor: AppColors.error,
        ),
      );
    }
  }

  void _saveAsTemplate() {
    if (_items.isEmpty) return;
    final mealName = _mealNameController.text.trim().isNotEmpty
        ? _mealNameController.text.trim()
        : _items.length == 1
            ? _items.first.name
            : '${_items.first.name} + ${_items.length - 1} món';

    final template = SavedMealTemplate(
      id: 'user_${DateTime.now().millisecondsSinceEpoch}',
      name: mealName,
      emoji: '⭐',
      items: _items
          .map((i) => SavedMealItemTemplate(
                foodId: i.foodId,
                name: i.name,
                defaultGrams: i.weightGrams,
              ))
          .toList(),
    );
    Provider.of<NutritionProvider>(context, listen: false)
        .saveMealTemplate(template);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text('Đã lưu "$mealName" vào danh sách yêu thích'),
          backgroundColor: AppColors.success),
    );
  }

  void _loadFromDish(Map<String, dynamic> dish) {
    final dishName = dish['name']?.toString() ?? 'Món ăn';
    final foodsDb =
        Provider.of<NutritionProvider>(context, listen: false).vietnameseFoods;
    final nutrition = MealNutritionUtils.resolveDish(dish, foodsDb);
    final newItems = nutrition.items;

    setState(() {
      _items.clear();
      _items.addAll(newItems);
      _mealNameController.text = dishName;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content:
            Text('Đã chọn món "$dishName" (${newItems.length} thành phần)'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 1),
      ),
    );
  }

  void _loadFromTemplate(SavedMealTemplate template) {
    final db =
        Provider.of<NutritionProvider>(context, listen: false).vietnameseFoods;
    final newItems = <MealItem>[];
    for (final t in template.items) {
      final food = db
          .where((f) =>
              f.id == t.foodId || f.name.toLowerCase() == t.name.toLowerCase())
          .firstOrNull;
      if (food != null) {
        newItems.add(food.toMealItem(
          itemId: '${t.foodId}_${DateTime.now().millisecondsSinceEpoch}',
          grams: t.defaultGrams,
        ));
      } else {
        newItems.add(MealItem(
          id: '${t.foodId}_${DateTime.now().millisecondsSinceEpoch}',
          foodId: t.foodId,
          name: t.name,
          weightGrams: t.defaultGrams,
          calories: (t.defaultGrams * 1.5),
          protein: (t.defaultGrams * 0.1),
          carbs: (t.defaultGrams * 0.2),
          fat: (t.defaultGrams * 0.05),
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
                    Center(
                        child: Container(
                            width: 40,
                            height: 4,
                            decoration: BoxDecoration(
                                color: AppColors.textHint,
                                borderRadius: BorderRadius.circular(2)))),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Text('Chọn món',
                            style: TextStyle(
                                fontSize: 26, fontWeight: FontWeight.w800)),
                        const Spacer(),
                        // Meal type pill
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: _getMealTypeColor(_mealType)
                                .withValues(alpha: 0.12),
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
                                color: _getMealTypeColor(_mealType)),
                            items: const [
                              DropdownMenuItem(
                                  value: 'sang', child: Text('🌅 Sáng')),
                              DropdownMenuItem(
                                  value: 'trua', child: Text('☀️ Trưa')),
                              DropdownMenuItem(
                                  value: 'toi', child: Text('🌙 Tối')),
                              DropdownMenuItem(
                                  value: 'phu', child: Text('🍎 Phụ')),
                            ],
                            onChanged: (v) => setState(() => _mealType = v!),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    // Tên món
                    if (_items.isNotEmpty)
                      TextField(
                        controller: _mealNameController,
                        decoration: const InputDecoration(
                          hintText: 'Tên món ăn (vd: Phở bò, Cơm tấm...)',
                          hintStyle: TextStyle(fontSize: 13),
                          prefixIcon: Icon(Icons.restaurant, size: 18),
                          contentPadding: EdgeInsets.symmetric(vertical: 10),
                        ),
                      ),
                    const SizedBox(height: 8),
                    // Tab bar
                    TabBar(
                      controller: _tabController,
                      labelColor: AppColors.primary,
                      unselectedLabelColor: AppColors.textSecondary,
                      indicatorColor: AppColors.primary,
                      indicatorWeight: 3,
                      labelStyle: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.bold),
                      unselectedLabelStyle: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.normal),
                      tabs: const [
                        Tab(
                            icon: Icon(Icons.restaurant_menu_rounded, size: 18),
                            text: 'Món Việt'),
                        Tab(
                            icon: Icon(Icons.favorite_rounded, size: 18),
                            text: 'Đã lưu'),
                        Tab(
                            icon: Icon(Icons.tune_rounded, size: 18),
                            text: 'Nguyên liệu'),
                      ],
                    ),
                  ],
                ),
              ),

              // ── Thành phần đã thêm (hiện khi có items) ──
              if (_items.isNotEmpty) _buildItemsSummary(),

              // ── Tab content ──
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    // Tab 0: Danh sách món Việt chuẩn từ database
                    _SampleMealsTab(
                      mealType: _mealType,
                      onSelectDish: _loadFromDish,
                    ),
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
              const Icon(Icons.receipt_long,
                  size: 14, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text('${_items.length} thành phần',
                  style: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('${_totalCal.toStringAsFixed(0)} kcal',
                  style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.calories,
                      fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: _items
                .asMap()
                .entries
                .map((e) => GestureDetector(
                      onTap: () => _removeItem(e.key),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: AppColors.surfaceLight),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                                '${e.value.name} ${e.value.weightGrams.toStringAsFixed(0)}g',
                                style: const TextStyle(fontSize: 11)),
                            const SizedBox(width: 4),
                            const Icon(Icons.close,
                                size: 12, color: AppColors.error),
                          ],
                        ),
                      ),
                    ))
                .toList(),
          ),
          const SizedBox(height: 4),
          Text(
              'P: ${_totalProtein.toStringAsFixed(1)}g   C: ${_totalCarbs.toStringAsFixed(1)}g   F: ${_totalFat.toStringAsFixed(1)}g',
              style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: AppColors.textSecondary)),
        ],
      ),
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: EdgeInsets.fromLTRB(
          20, 8, 20, 16 + MediaQuery.of(context).viewInsets.bottom),
      decoration: BoxDecoration(
        color: AppColors.surface,
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 8,
              offset: const Offset(0, -2))
        ],
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
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
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
              onPressed: _items.isEmpty || _isSaving ? null : _save,
              icon: _isSaving
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.check, size: 16),
              label: Text(
                _isSaving
                    ? 'Đang lưu...'
                    : _items.isEmpty
                        ? 'Chọn thành phần'
                        : 'Lưu món ăn (${_items.length})',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _getMealTypeColor(String type) {
    return MealPresentation.accent(type);
  }
}

// ═══════════════════════════════════════════════════════════════
// Tab Món Việt Chuẩn — nạp từ 90 món ăn database backend
// ═══════════════════════════════════════════════════════════════
class _SampleMealsTab extends StatefulWidget {
  final String mealType;
  final void Function(Map<String, dynamic>) onSelectDish;
  const _SampleMealsTab({required this.mealType, required this.onSelectDish});

  @override
  State<_SampleMealsTab> createState() => _SampleMealsTabState();
}

class _SampleMealsTabState extends State<_SampleMealsTab> {
  final _searchCtrl = TextEditingController();
  String _query = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _loadCatalog();
    });
  }

  Future<void> _loadCatalog() async {
    setState(() => _loading = true);
    try {
      await context.read<NutritionProvider>().loadVietnameseDatabase();
    } catch (_) {
      // The provider retains any previously loaded catalog on failure.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<NutritionProvider>(context);
    final dishes = provider.vietnameseDishes;

    final mealTypeMap = {
      'sang': 'breakfast',
      'trua': 'lunch',
      'toi': 'dinner',
      'phu': 'snack',
    };
    final targetType = mealTypeMap[widget.mealType] ?? 'lunch';

    final filtered = dishes.where((d) {
      final name = (d['name'] ?? '').toString().toLowerCase();
      final types = (d['meal_types'] as List<dynamic>? ?? [])
          .map((e) => e.toString().toLowerCase())
          .toList();
      final matchType = types.isEmpty ||
          types.contains(targetType) ||
          widget.mealType == 'phu';
      final matchQuery = _query.isEmpty || name.contains(_query.toLowerCase());
      return matchType && matchQuery;
    }).toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 8),
          child: TextField(
            controller: _searchCtrl,
            decoration: const InputDecoration(
              hintText: 'Tìm món Việt (Phở, Cơm, Bún, Cháo, Cá...)...',
              hintStyle: TextStyle(fontSize: 13),
              prefixIcon: Icon(Icons.search, size: 18),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (v) => setState(() => _query = v),
          ),
        ),
        Expanded(
          child: filtered.isEmpty
              ? SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: dishes.isEmpty && _loading
                      ? const NutritionSkeleton()
                      : NutritionEmptyState(
                          icon: Icons.restaurant_menu,
                          title: dishes.isEmpty
                              ? 'Danh mục món ăn chưa khả dụng.'
                              : 'Không tìm thấy món phù hợp.',
                          message: dishes.isEmpty
                              ? 'Thử tải lại để chọn món cho bữa ăn.'
                              : 'Thử tìm bằng tên món khác.',
                          actionLabel: dishes.isEmpty ? 'Thử lại' : null,
                          onAction: dishes.isEmpty ? _loadCatalog : null,
                        ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
                  itemCount: filtered.length,
                  itemBuilder: (ctx, i) {
                    return CatalogDishCard(
                        dish: filtered[i], onSelect: widget.onSelectDish);
                  },
                ),
        ),
      ],
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
            Text('Chưa có món nào được lưu',
                style: TextStyle(color: AppColors.textSecondary)),
            SizedBox(height: 4),
            Text('Tạo món ăn rồi nhấn 🔖 để lưu lại',
                style: TextStyle(fontSize: 12, color: AppColors.textHint)),
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
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                  child: Text(template.emoji,
                      style: const TextStyle(fontSize: 22))),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(template.name,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 14)),
                  const SizedBox(height: 3),
                  Text(
                    template.items
                        .map((i) =>
                            '${i.name} ${i.defaultGrams.toStringAsFixed(0)}g')
                        .join(' · '),
                    style: const TextStyle(
                        fontSize: 11, color: AppColors.textSecondary),
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
                    style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: AppColors.calories)),
                const Text('kcal',
                    style: TextStyle(
                        fontSize: 10, color: AppColors.textSecondary)),
              ],
            ),
            if (canDelete) ...[
              const SizedBox(width: 8),
              GestureDetector(
                onTap: onDelete,
                child: const Icon(Icons.delete_outline,
                    size: 18, color: AppColors.error),
              ),
            ] else ...[
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward_ios,
                  size: 14, color: AppColors.textHint),
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
                    Center(
                        child: Container(
                            width: 40,
                            height: 4,
                            decoration: BoxDecoration(
                                color: AppColors.textHint,
                                borderRadius: BorderRadius.circular(2)))),
                    const SizedBox(height: 12),
                    Text('Thêm vào "${meal.name}"',
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 4),
                  ],
                ),
              ),
              Expanded(
                child: _FoodPickerList(
                  mealType: meal.mealType,
                  onItemAdded: (item) {
                    final updated = meal.copyWith(items: [...meal.items, item]);
                    Provider.of<NutritionProvider>(ctx, listen: false)
                        .updateMeal(updated);
                    Navigator.pop(ctx);
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(
                        content:
                            Text('Đã thêm "${item.name}" vào "${meal.name}"'),
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
    final foodsDb =
        Provider.of<NutritionProvider>(context, listen: false).vietnameseFoods;
    final all = q.isEmpty
        ? List<FoodItem>.from(foodsDb)
        : foodsDb
            .where((f) => f.name.toLowerCase().contains(q.toLowerCase()))
            .toList();
    // Ưu tiên theo bữa ăn
    final mealKeywords = {
      'sang': ['bánh', 'trứng', 'sữa', 'phở', 'bún', 'cháo'],
      'trua': ['cơm', 'thịt', 'cá', 'gà', 'rau', 'tôm'],
      'toi': ['cơm', 'cá', 'gà', 'rau', 'đậu', 'mì', 'cháo'],
      'phu': ['sữa', 'trái', 'chuối', 'táo', 'cam', 'bánh', 'sữa chua'],
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

  static (String emoji, Color bg) _getFoodVisuals(
      String name, String category) {
    final lower = name.toLowerCase().trim();
    final cat = category.toLowerCase().trim();
    if (cat.contains('ngũ cốc') ||
        cat.contains('tinh bột') ||
        lower.contains('gạo') ||
        lower.contains('bún') ||
        lower.contains('phở') ||
        lower.contains('bánh') ||
        lower.contains('mì')) {
      return ('🌾', const Color(0xFFFF9800).withValues(alpha: 0.12));
    }
    if (cat.contains('thịt') ||
        lower.contains('bò') ||
        lower.contains('heo') ||
        lower.contains('gà') ||
        lower.contains('vịt') ||
        lower.contains('sườn') ||
        lower.contains('chả')) {
      return ('🥩', const Color(0xFFE91E63).withValues(alpha: 0.12));
    }
    if (cat.contains('hải sản') ||
        cat.contains('thủy sản') ||
        lower.contains('cá') ||
        lower.contains('tôm') ||
        lower.contains('mực') ||
        lower.contains('cua') ||
        lower.contains('nghêu') ||
        lower.contains('sò')) {
      return ('🐟', const Color(0xFF03A9F4).withValues(alpha: 0.12));
    }
    if (cat.contains('rau') ||
        lower.contains('rau') ||
        lower.contains('cải') ||
        lower.contains('muống') ||
        lower.contains('xà lách') ||
        lower.contains('cà rốt') ||
        lower.contains('cà chua')) {
      return ('🥬', const Color(0xFF4CAF50).withValues(alpha: 0.12));
    }
    if (cat.contains('khoai') ||
        lower.contains('khoai') ||
        lower.contains('sắn') ||
        lower.contains('ngô') ||
        lower.contains('bắp')) {
      return ('🥔', const Color(0xFF8D6E63).withValues(alpha: 0.12));
    }
    if (cat.contains('hạt') ||
        cat.contains('đậu') ||
        lower.contains('đậu') ||
        lower.contains('hạt') ||
        lower.contains('lạc')) {
      return ('🥜', const Color(0xFF795548).withValues(alpha: 0.12));
    }
    if (cat.contains('trái') ||
        cat.contains('quả') ||
        lower.contains('chuối') ||
        lower.contains('táo') ||
        lower.contains('cam') ||
        lower.contains('dưa') ||
        lower.contains('bơ')) {
      return ('🍎', const Color(0xFFFF4081).withValues(alpha: 0.12));
    }
    if (cat.contains('sữa') ||
        lower.contains('sữa') ||
        lower.contains('trứng') ||
        lower.contains('bơ sữa')) {
      return ('🥚', const Color(0xFFFFC107).withValues(alpha: 0.15));
    }
    return ('🥗', const Color(0xFF4CAF50).withValues(alpha: 0.12));
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
                border:
                    Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(_selected!.name,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 14)),
                      ),
                      GestureDetector(
                        onTap: () => setState(() => _selected = null),
                        child: const Icon(Icons.close,
                            size: 16, color: AppColors.textHint),
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
                            contentPadding: EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
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
                              style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.calories),
                            ),
                            const Text('kcal',
                                style: TextStyle(
                                    fontSize: 10,
                                    color: AppColors.textSecondary)),
                          ],
                        );
                      }),
                    ],
                  ),
                  const SizedBox(height: 6),
                  // Quick gram options
                  Wrap(
                    spacing: 6,
                    children: [50, 100, 150, 200]
                        .map((g) => GestureDetector(
                              onTap: () => setState(
                                  () => _gramsCtrl.text = g.toString()),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: _gramsCtrl.text == g.toString()
                                      ? AppColors.primary
                                      : AppColors.primary
                                          .withValues(alpha: 0.08),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text('${g}g',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: _gramsCtrl.text == g.toString()
                                          ? Colors.white
                                          : AppColors.primary,
                                    )),
                              ),
                            ))
                        .toList(),
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
              final visual = _getFoodVisuals(food.name, food.category);
              return GestureDetector(
                onTap: () => setState(() {
                  _selected = food;
                  _gramsCtrl.text = '100';
                }),
                child: Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? AppColors.primary.withValues(alpha: 0.1)
                        : AppColors.cardDark,
                    borderRadius: BorderRadius.circular(12),
                    border: isSelected
                        ? Border.all(color: AppColors.primary, width: 1.5)
                        : Border.all(color: AppColors.surfaceLight),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: visual.$2,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Center(
                            child: Text(visual.$1,
                                style: const TextStyle(fontSize: 18))),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(food.name,
                                style: TextStyle(
                                  fontWeight: isSelected
                                      ? FontWeight.bold
                                      : FontWeight.w600,
                                  fontSize: 13,
                                )),
                            const SizedBox(height: 2),
                            Text(
                              '${food.caloriesPer100g.toStringAsFixed(0)} kcal  P:${food.proteinPer100g.toStringAsFixed(0)}g  C:${food.carbsPer100g.toStringAsFixed(0)}g  F:${food.fatPer100g.toStringAsFixed(0)}g /100g',
                              style: const TextStyle(
                                  fontSize: 10, color: AppColors.textSecondary),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(food.category,
                            style: const TextStyle(
                                fontSize: 9, color: AppColors.textHint)),
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
