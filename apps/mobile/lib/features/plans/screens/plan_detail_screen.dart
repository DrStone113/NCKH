import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/plan_provider.dart';
import '../../../widgets/health_surface.dart';
import '../../nutrition/widgets/nutrition_overview.dart';
import '../../nutrition/widgets/meal_plan_card.dart';

import '../plan_display.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/versioned_plan_card.dart';
import '../../../services/backend_api_service.dart';

/// Read-only detail for the exact immutable Plan V2 revision referenced by a
/// structured chat card or the plan library.
class PlanDetailScreen extends StatefulWidget {
  final Map<String, dynamic> plan;
  final DateTime? initialDate;

  const PlanDetailScreen({super.key, required this.plan, this.initialDate});

  @override
  State<PlanDetailScreen> createState() => _PlanDetailScreenState();
}

class _PlanDetailScreenState extends State<PlanDetailScreen> {
  int _selectedDayIndex = -1; // -1 means "Tất cả"
  final BackendApiService _api = BackendApiService();
  late Map<String, dynamic> _plan;
  bool _mutating = false;
  List<Map<String, dynamic>> _history = const [];

  @override
  void initState() {
    super.initState();
    _plan = Map<String, dynamic>.from(widget.plan);
    if (PlanDisplay.isNutrition(_plan)) {
      final days = PlanDisplay.days(_plan);
      final match = days.indexWhere((day) => DateUtils.isSameDay(
          DateTime.tryParse(day['date']?.toString() ?? ''),
          widget.initialDate ?? DateTime.now()));
      _selectedDayIndex = match < 0 ? 0 : match;
    }
    _refreshExactRevision();
    _loadHistory();
  }

  Future<void> _refreshExactRevision() async {
    final planId = _plan['plan_id']?.toString() ?? '';
    final revisionId = _plan['revision_id']?.toString() ?? '';
    if (planId.isEmpty || revisionId.isEmpty) return;
    try {
      final read = await _api.readAuthoritativePlanV2(
        planId: planId,
        revisionId: revisionId,
      );
      if (read != null && mounted) {
        setState(() => _plan = read);
        _updateSharedPlan(read);
      }
    } catch (_) {
      // A DRAFT/PENDING chat card may not yet be persisted. It still renders
      // read-only and never falls back to a different "latest" revision.
    }
  }

  Future<void> _loadHistory() async {
    final planId = _plan['plan_id']?.toString() ?? '';
    if (planId.isEmpty) return;
    try {
      final history = await _api.listAuthoritativePlanHistory(planId);
      if (mounted) setState(() => _history = history);
    } catch (_) {
      // History is supplemental; the exact revision remains the authority.
    }
  }

  List<String> _availableActions(String lifecycle) {
    final targets = _plan['valid_lifecycle_targets'];
    if (targets is List) {
      return targets.whereType<String>().toList(growable: false);
    }
    return switch (lifecycle) {
      'DRAFT' || 'PENDING_CONFIRMATION' => const ['SAVE'],
      'SAVED' => const ['ACTIVE', 'CANCELLED'],
      'ACTIVE' => const ['PAUSED', 'CANCELLED'],
      'PAUSED' => const ['ACTIVE', 'CANCELLED'],
      _ => const [],
    };
  }

  Future<void> _runAction(String action, {bool replaceConflicts = false}) async {
    final planId = _plan['plan_id']?.toString() ?? '';
    final revisionId = _plan['revision_id']?.toString() ?? '';
    final revisionNumber =
        int.tryParse(_plan['revision_number']?.toString() ?? '');
    if (planId.isEmpty || revisionId.isEmpty || revisionNumber == null) return;
    setState(() => _mutating = true);
    try {
      final result = action == 'SAVE'
          ? await _api.saveAuthoritativePlanV2(
              planId: planId,
              revisionId: revisionId,
              revisionContentHash:
                  _plan['revision_content_hash']?.toString() ?? '',
              actionId: 'plan-ui-save-$revisionId',
            )
          : await _api.changeAuthoritativePlanV2Lifecycle(
              planId: planId,
              revisionId: revisionId,
              expectedRevisionNumber: revisionNumber,
              operation: switch (action) {
                'ACTIVE' =>
                  _plan['lifecycle_status'] == 'PAUSED' ? 'resume' : 'activate',
                'PAUSED' => 'pause',
                'CANCELLED' => 'cancel',
                _ => throw StateError('INVALID_PLAN_UI_ACTION'),
              },
              actionId: 'plan-ui-${action.toLowerCase()}-$revisionId',
              replaceConflicts: replaceConflicts,
            );
      final readBack = result['plan'];
      if (readBack is! Map) throw StateError('PLAN_READBACK_MISSING');
      if (!mounted) return;
      final updated = Map<String, dynamic>.from(readBack);
      setState(() => _plan = updated);
      _updateSharedPlan(updated, refreshAll: true);
      unawaited(_loadHistory());
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã cập nhật kế hoạch từ máy chủ.')),
      );
    } on PlanV2ApiException catch (error) {
      if (!mounted) return;
      if (error.code == 'ACTIVE_SCHEDULE_CONFLICT' && !replaceConflicts) {
        final resolution = await showDialog<String>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Lịch đang bị trùng'),
            content: const Text(
              'Có kế hoạch đang hoạt động trong cùng thời gian. Bạn có thể tải lại hoặc thay thế kế hoạch cũ một cách rõ ràng.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, 'refresh'),
                child: const Text('Tải lại'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, 'replace'),
                child: const Text('Thay thế'),
              ),
            ],
          ),
        );
        if (resolution == 'refresh') {
          await _refreshExactRevision();
          await _loadHistory();
        } else if (resolution == 'replace') {
          await _runAction(action, replaceConflicts: true);
        }
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không thể cập nhật kế hoạch: ${error.code}')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không thể cập nhật kế hoạch: $error')),
      );
    } finally {
      if (mounted) setState(() => _mutating = false);
    }
  }

  void _updateSharedPlan(
    Map<String, dynamic> plan, {
    bool refreshAll = false,
  }) {
    try {
      final shared = context.read<PlanProvider>();
      shared.upsertAuthoritativePlan(plan);
      if (refreshAll) {
        unawaited(shared.refresh().catchError((_) => shared.plans));
      }
    } on ProviderNotFoundException {
      // Isolated widget tests and embedded previews may not own app providers.
    }
  }

  @override
  Widget build(BuildContext context) {
    final lifecycle = _plan['lifecycle_status']?.toString() ?? 'DRAFT';
    final waitingForConfirmation = lifecycle == 'PENDING_CONFIRMATION';
    final allDays = PlanDisplay.days(_plan);

    // Filter days if a specific day is selected
    final displayedPlan =
        _selectedDayIndex == -1 || _selectedDayIndex >= allDays.length
            ? _plan
            : (Map<String, dynamic>.from(_plan)
              ..['days'] = [allDays[_selectedDayIndex]]);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(PlanDisplay.isNutrition(_plan)
            ? 'Kế hoạch ăn theo ngày'
            : 'Chi tiết kế hoạch'),
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          key: const ValueKey('plan-detail-scroll'),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!PlanDisplay.isNutrition(_plan))
                    _PlanDetailHero(plan: _plan),
                  const SizedBox(height: 8),
                  if (!PlanDisplay.isNutrition(_plan))
                    _ExactRevisionReference(plan: _plan),
                  if (!PlanDisplay.isNutrition(_plan) &&
                      allDays.length > 1) ...[
                    const SizedBox(height: 14),
                    _buildDayTabs(allDays),
                  ],
                  const SizedBox(height: 14),
                  if (PlanDisplay.isNutrition(_plan))
                    _nutritionDays(allDays)
                  else
                    VersionedPlanCard(plan: displayedPlan, showHeader: false),
                  if (_availableActions(lifecycle).isNotEmpty) ...[
                    const SizedBox(height: 12),
                    _LifecycleActions(
                      actions: _availableActions(lifecycle),
                      lifecycle: lifecycle,
                      busy: _mutating,
                      onAction: _runAction,
                    ),
                  ],
                  if (waitingForConfirmation) ...[
                    const SizedBox(height: 12),
                    const _ConfirmationNotice(),
                  ],
                  const SizedBox(height: 16),
                  _PlanHistory(history: _history),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _nutritionDays(List<Map<String, dynamic>> days) {
    if (days.isEmpty) {
      return const NutritionEmptyState(
          title: 'Bạn chưa có kế hoạch ăn cho ngày này.');
    }
    final index = _selectedDayIndex.clamp(0, days.length - 1);
    final day = days[index];
    final date = DateTime.tryParse(day['date']?.toString() ?? '');
    final diary = context.watch<NutritionProvider?>();
    final consumedCalories =
        diary != null && DateUtils.isSameDay(diary.selectedDate, date)
            ? diary.consumedCalories
            : null;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(
          date == null
              ? 'Kế hoạch ăn theo ngày'
              : '${date.day} tháng ${date.month}',
          style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800)),
      const SizedBox(height: 8),
      const Text('Các món bên dưới là dự kiến, chưa ghi nhận đã ăn.',
          style: TextStyle(color: AppColors.textSecondary)),
      const SizedBox(height: 20),
      if (date != null)
        DailyDateStrip(
            selected: date,
            dates: days
                .map((day) => DateTime.tryParse(day['date']?.toString() ?? ''))
                .whereType<DateTime>()
                .toList(),
            onSelected: (selected) => setState(() => _selectedDayIndex =
                days.indexWhere((day) => DateUtils.isSameDay(
                    DateTime.tryParse(day['date']?.toString() ?? ''),
                    selected)))),
      const SizedBox(height: 20),
      PlanDayNutritionSummary(plan: _plan, day: day),
      if (consumedCalories != null) ...[
        const SizedBox(height: 12),
        HealthSurface(
          child: Row(children: [
            const Icon(Icons.fact_check_outlined, color: AppColors.success),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Nhật ký ứng dụng: ${consumedCalories.round()} kcal đã ăn trong ngày này. Con số này tách biệt với thực đơn dự kiến.',
                style: const TextStyle(height: 1.35),
              ),
            ),
          ]),
        ),
      ],
      const SizedBox(height: 8),
      MealSlotSection(
          items: PlanDisplay.items(day),
          onView: (item) => showPlannedMealDetail(context, item)),
      // Keep the plan overview available even for a one-day menu so the
      // planned schedule has a stable, read-only summary surface.
      ...[
        const HealthSectionTitle('Tổng quan các ngày',
            subtitle: 'Chạm một ngày để xem thực đơn dự kiến.'),
        HealthSurface(
            child: Column(
                children: days.asMap().entries.map((entry) {
          final items = PlanDisplay.items(entry.value);
          final calories = items
              .map((item) => PlanDisplay.nutrition(item)['total_calories'])
              .toList();
          final known =
              calories.isNotEmpty && calories.every((value) => value is num);
          final total =
              known ? calories.cast<num>().fold<num>(0, (a, b) => a + b) : null;
          return ListTile(
              selected: entry.key == index,
              contentPadding: EdgeInsets.zero,
              leading: Icon(entry.key == index
                  ? Icons.check_circle
                  : Icons.calendar_today_outlined),
              title: Text(entry.value['date']?.toString() ?? 'Chưa có ngày'),
              subtitle: Text('${items.length} bữa · Dự kiến'),
              trailing: total == null
                  ? null
                  : Text('${total.round()} kcal',
                      style: const TextStyle(fontWeight: FontWeight.w700)),
              onTap: () => setState(() => _selectedDayIndex = entry.key));
        }).toList())),
      ],
      ExpansionTile(
          title: const Text('Thông tin kế hoạch'),
          children: [_ExactRevisionReference(plan: _plan)]),
    ]);
  }

  Widget _buildDayTabs(List<Map<String, dynamic>> days) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _dayTabItem(
          label: 'Tất cả (${days.length} ngày)',
          isSelected: _selectedDayIndex == -1,
          onTap: () => setState(() => _selectedDayIndex = -1),
        ),
        ...days.asMap().entries.map((entry) {
          final idx = entry.key;
          final day = entry.value;
          final dateStr = day['date']?.toString() ?? '';
          final parsed = DateTime.tryParse(dateStr);
          final dayLabel = parsed != null
              ? 'Ngày ${idx + 1} (${parsed.day}/${parsed.month})'
              : 'Ngày ${idx + 1}';

          return _dayTabItem(
            label: dayLabel,
            isSelected: _selectedDayIndex == idx,
            onTap: () => setState(() => _selectedDayIndex = idx),
          );
        }),
      ],
    );
  }

  Widget _dayTabItem({
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: isSelected ? AppColors.primary : AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.pill),
            border: Border.all(
              color: isSelected
                  ? Colors.transparent
                  : Colors.black.withValues(alpha: 0.06),
              width: 1,
            ),
            boxShadow: isSelected ? AppShadows.subtle : null,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
              color: isSelected ? Colors.white : AppColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

/// Deliberately exposes the immutable identity that the route is rendering.
/// This is not a "latest plan" label: an operator and the browser acceptance
/// flow can compare it directly with the server's exact read-back.
class _ExactRevisionReference extends StatelessWidget {
  final Map<String, dynamic> plan;

  const _ExactRevisionReference({required this.plan});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Bản kế hoạch chính thức',
      child: Container(
        key: const ValueKey('plan-v2-authoritative-reference'),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: const Text('Nội dung này được đồng bộ từ kế hoạch chính thức.'),
      ),
    );
  }
}

class _PlanHistory extends StatelessWidget {
  final List<Map<String, dynamic>> history;

  const _PlanHistory({required this.history});

  @override
  Widget build(BuildContext context) {
    if (history.isEmpty) return const SizedBox.shrink();
    return HealthSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Lịch sử chỉnh sửa',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  )),
          const SizedBox(height: 8),
          for (final revision in history) ...[
            Text(
              'Bản ${revision['revision_number'] ?? ''} · ${revision['lifecycle_status'] ?? ''}',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            if ((revision['created_at']?.toString() ?? '').isNotEmpty)
              Text(
                revision['created_at'].toString().replaceFirst('T', ' ').split('.').first,
                style: const TextStyle(color: AppColors.textSecondary),
              ),
            const SizedBox(height: 8),
          ],
        ],
      ),
    );
  }
}

class _LifecycleActions extends StatelessWidget {
  final List<String> actions;
  final String lifecycle;
  final bool busy;
  final ValueChanged<String> onAction;

  const _LifecycleActions({
    required this.actions,
    required this.lifecycle,
    required this.busy,
    required this.onAction,
  });

  static const _labels = {
    'SAVE': 'Lưu',
    'ACTIVE': 'Kích hoạt',
    'PAUSED': 'Tạm dừng',
    'CANCELLED': 'Hủy kế hoạch',
  };

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: actions
          .map(
            (action) => Semantics(
              button: true,
              label: 'Plan lifecycle action $action',
              child: OutlinedButton(
                key: ValueKey('plan-lifecycle-${action.toLowerCase()}'),
                onPressed: busy ? null : () => onAction(action),
                child: Text(action == 'ACTIVE' && lifecycle == 'PAUSED'
                    ? 'Tiếp tục'
                    : (_labels[action] ?? action)),
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}

class _PlanDetailHero extends StatelessWidget {
  final Map<String, dynamic> plan;

  const _PlanDetailHero({required this.plan});

  @override
  Widget build(BuildContext context) {
    final isNutrition = PlanDisplay.isNutrition(plan);
    final gradient = isNutrition
        ? AppColors.calorieGradient
        : PlanDisplay.isWorkout(plan)
            ? AppColors.exerciseGradient
            : AppColors.primaryGradient;
    final itemCount = PlanDisplay.itemCount(plan);
    final dayCount = PlanDisplay.days(plan).length;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(AppRadius.xxl),
        boxShadow: [
          BoxShadow(
            color: (isNutrition ? AppColors.calories : AppColors.primary)
                .withValues(alpha: 0.25),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .22),
              borderRadius: BorderRadius.circular(AppRadius.lg),
            ),
            child: Icon(PlanDisplay.domainIcon(plan),
                color: Colors.white, size: 26),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  PlanDisplay.domainTitle(plan),
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 18,
                        letterSpacing: -0.3,
                      ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(Icons.calendar_today_rounded,
                        size: 13, color: Colors.white70),
                    const SizedBox(width: 5),
                    Text(
                      PlanDisplay.shortDateRange(plan),
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.white.withValues(alpha: .9),
                            fontWeight: FontWeight.w500,
                          ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    _HeroPill(label: '$dayCount ngày'),
                    _HeroPill(label: '$itemCount mục dự kiến'),
                    const _HeroPill(label: 'Chưa ghi nhận thực tế'),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroPill extends StatelessWidget {
  final String label;

  const _HeroPill({required this.label});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: .2),
          borderRadius: BorderRadius.circular(AppRadius.pill),
        ),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 11,
              ),
        ),
      );
}

class _ConfirmationNotice extends StatelessWidget {
  const _ConfirmationNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(
          color: AppColors.warning.withValues(alpha: 0.25),
          width: 1,
        ),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline_rounded, color: AppColors.warning, size: 20),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Bản này đang chờ xác nhận trong cuộc trò chuyện đã tạo nó. Hãy xác nhận tại đó để hệ thống lưu đúng phiên bản.',
              style: TextStyle(
                color: AppColors.textSecondary,
                height: 1.4,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
