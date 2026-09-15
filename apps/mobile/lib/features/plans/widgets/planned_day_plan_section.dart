import 'package:flutter/material.dart';

import '../../../theme/app_theme.dart';
import '../../../widgets/health_surface.dart';
import '../../nutrition/widgets/meal_plan_card.dart';
import '../plan_display.dart';
import '../screens/plan_list_screen.dart';
import '../../../widgets/versioned_plan_card.dart';
import '../plan_history.dart';
import '../plan_snapshot.dart';
import '../screens/plan_detail_screen.dart';

/// Read-only daily Plan V2 preview for the actual Nutrition and Exercise tabs.
///
/// It intentionally lives beside the diary, not inside it: planned entries are
/// never written as consumed meals or completed workouts by rendering this UI.
class PlannedDayPlanSection extends StatefulWidget {
  final String userId;
  final DateTime date;
  final String domain;
  final PlanSnapshotLoader? loader;
  final List<PlanSnapshot>? snapshots;
  final bool compact;

  const PlannedDayPlanSection({
    super.key,
    required this.userId,
    required this.date,
    required this.domain,
    this.loader,
    this.snapshots,
    this.compact = false,
  });

  @override
  State<PlannedDayPlanSection> createState() => _PlannedDayPlanSectionState();
}

class _PlannedDayPlanSectionState extends State<PlannedDayPlanSection> {
  late Future<PlannedPlanDay?> _plannedDay;

  @override
  void initState() {
    super.initState();
    _plannedDay = _load();
  }

  @override
  void didUpdateWidget(covariant PlannedDayPlanSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.userId != widget.userId ||
        oldWidget.domain != widget.domain ||
        !_isSameDate(oldWidget.date, widget.date) ||
        oldWidget.loader != widget.loader) {
      _plannedDay = _load();
    }
    if (!identical(oldWidget.snapshots, widget.snapshots)) {
      _plannedDay = _load();
    }
  }

  Future<PlannedPlanDay?> _load() async {
    if (widget.userId.trim().isEmpty) return null;
    final snapshots = widget.snapshots ??
        await (widget.loader ?? PlanHistoryRepository().loadForUser)(
          widget.userId,
        );
    return PlanHistoryResolver.forDomainAndDate(
      snapshots: snapshots,
      domain: widget.domain,
      date: widget.date,
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PlannedPlanDay?>(
      future: _plannedDay,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done ||
            snapshot.hasError ||
            snapshot.data == null) {
          if (widget.domain != 'NUTRITION' || widget.compact) {
            return const SizedBox.shrink();
          }
          return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const HealthSectionTitle('Kế hoạch ăn hôm nay',
                    subtitle: 'Dự kiến · tách biệt với nhật ký đã ăn'),
                if (snapshot.connectionState != ConnectionState.done)
                  const NutritionSkeleton(lines: 2)
                else if (snapshot.hasError)
                  NutritionEmptyState(
                      title: 'Không thể tải kế hoạch lúc này.',
                      icon: Icons.cloud_off_outlined,
                      actionLabel: 'Thử lại',
                      onAction: () => setState(() {
                            _plannedDay = _load();
                          }))
                else
                  NutritionEmptyState(
                      title: 'Bạn chưa có kế hoạch ăn cho ngày này.',
                      actionLabel: 'Xem kế hoạch',
                      onAction: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                              builder: (_) => const PlanListScreen()))),
              ]);
        }

        final plannedDay = snapshot.data!;
        final plan = Map<String, dynamic>.from(plannedDay.snapshot.plan)
          ..['days'] = [plannedDay.day];
        if (widget.domain == 'NUTRITION') {
          if (widget.compact) {
            return _CompactNutritionPlanDay(
              plannedDay: plannedDay,
              date: widget.date,
            );
          }
          return Column(
              key: const ValueKey('planned-day-section-NUTRITION'),
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                HealthSectionTitle(
                    DateUtils.isSameDay(widget.date, DateTime.now())
                        ? 'Kế hoạch ăn hôm nay'
                        : 'Kế hoạch ăn theo ngày',
                    subtitle: 'Dự kiến · chưa tính vào năng lượng đã ăn',
                    action: IconButton(
                        tooltip: 'Xem chi tiết',
                        icon: const Icon(Icons.arrow_forward_rounded),
                        onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                                builder: (_) => PlanDetailScreen(
                                    plan: plannedDay.snapshot.plan,
                                    initialDate: widget.date))))),
                PlanDayNutritionSummary(
                  plan: plannedDay.snapshot.plan,
                  day: plannedDay.day,
                ),
                const SizedBox(height: 12),
                MealSlotSection(
                    items: PlanDisplay.items(plannedDay.day),
                    onView: (item) => showPlannedMealDetail(context, item)),
              ]);
        }
        return Semantics(
          container: true,
          label: widget.domain == 'NUTRITION'
              ? 'Authoritative planned nutrition section '
                  '${plannedDay.snapshot.planId} ${plannedDay.snapshot.revisionId}'
              : 'Authoritative planned workout section '
                  '${plannedDay.snapshot.planId} ${plannedDay.snapshot.revisionId}',
          child: Padding(
            padding: const EdgeInsets.only(bottom: 24),
            child: Column(
              key: ValueKey('planned-day-section-${widget.domain}'),
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(
                              widget.domain == 'NUTRITION'
                                  ? 'Thực đơn theo kế hoạch'
                                  : 'Buổi tập theo kế hoạch',
                              style: const TextStyle(
                                fontSize: 17,
                                fontWeight: FontWeight.w800,
                                letterSpacing: -0.3,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: AppColors.info.withValues(alpha: .1),
                              borderRadius:
                                  BorderRadius.circular(AppRadius.pill),
                            ),
                            child: const Text(
                              'Dự kiến',
                              style: TextStyle(
                                fontSize: 11,
                                color: AppColors.info,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    InkWell(
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              PlanDetailScreen(plan: plannedDay.snapshot.plan),
                        ),
                      ),
                      borderRadius: BorderRadius.circular(AppRadius.pill),
                      child: const Padding(
                        padding:
                            EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              'Xem chi tiết',
                              style: TextStyle(
                                fontSize: 12,
                                color: AppColors.primary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            SizedBox(width: 2),
                            Icon(Icons.chevron_right_rounded,
                                size: 16, color: AppColors.primary),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                VersionedPlanCard(plan: plan, showHeader: false),
              ],
            ),
          ),
        );
      },
    );
  }

  bool _isSameDate(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}

class _CompactNutritionPlanDay extends StatelessWidget {
  final PlannedPlanDay plannedDay;
  final DateTime date;

  const _CompactNutritionPlanDay({
    required this.plannedDay,
    required this.date,
  });

  @override
  Widget build(BuildContext context) {
    final items = PlanDisplay.items(plannedDay.day);
    final totals = PlanDisplay.nutritionTotalsForDay(plannedDay.day);
    final names = items
        .map((item) => PlanDisplay.itemTitle(item, nutrition: true))
        .take(3)
        .join(' · ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: HealthSurface(
        child: InkWell(
          key: const ValueKey('home-planned-nutrition-day'),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => PlanDetailScreen(
                plan: plannedDay.snapshot.plan,
                initialDate: date,
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Icon(Icons.restaurant_menu_rounded,
                    color: AppColors.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Thực đơn theo kế hoạch hôm nay',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      Text(
                        names,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: AppColors.textSecondary),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        totals.calories == null
                            ? '${totals.mealCount} bữa dự kiến'
                            : '${totals.mealCount} bữa · ${totals.calories!.round()} kcal dự kiến',
                        style: const TextStyle(
                          color: AppColors.primary,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right_rounded),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
