import 'package:flutter/material.dart';

import '../features/plans/plan_display.dart';
import '../theme/app_theme.dart';

/// Renderer for the structured P1 Plan V2 response.  No value in this card is
/// parsed from model prose: the backend supplies an immutable revision and its
/// canonical references.
class VersionedPlanCard extends StatelessWidget {
  final Map<String, dynamic> plan;
  final bool showHeader;
  final VoidCallback? onView;
  final VoidCallback? onSave;
  final VoidCallback? onActivate;
  final VoidCallback? onEdit;
  final VoidCallback? onPause;
  final VoidCallback? onResume;
  final VoidCallback? onCancel;

  const VersionedPlanCard({
    super.key,
    required this.plan,
    this.showHeader = true,
    this.onView,
    this.onSave,
    this.onActivate,
    this.onEdit,
    this.onPause,
    this.onResume,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final days = PlanDisplay.days(plan);
    final isNutrition = PlanDisplay.isNutrition(plan);
    final lifecycle = plan['lifecycle_status']?.toString() ?? 'DRAFT';
    final isConflict = plan['status']?.toString() == 'PLAN_REVISION_CONFLICT';
    final itemCount = PlanDisplay.itemCount(plan);

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: AppColors.surfaceLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.045),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showHeader)
            _PlanCardHeader(
              plan: plan,
              lifecycle: lifecycle,
              itemCount: itemCount,
            ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.md,
              showHeader ? AppSpacing.md : AppSpacing.sm,
              AppSpacing.md,
              AppSpacing.md,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!showHeader)
                  _InlinePlanMeta(
                    plan: plan,
                    lifecycle: lifecycle,
                    itemCount: itemCount,
                  ),
                if (days.isEmpty)
                  _EmptyPlanItems(domain: plan['domain']?.toString() ?? 'PLAN')
                else ...[
                  Text(
                    isNutrition
                        ? 'Thực đơn đã lên lịch'
                        : 'Lịch đã lên kế hoạch',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  ...days.map(
                    (day) => _DayCard(day: day, nutrition: isNutrition),
                  ),
                ],
                if (isConflict) ...[
                  const SizedBox(height: AppSpacing.sm),
                  const _PlanConflictNotice(),
                ],
                if (onView != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: TextButton.icon(
                      onPressed: onView,
                      icon: const Icon(Icons.open_in_new_outlined, size: 16),
                      label: const Text('Xem kế hoạch đầy đủ'),
                    ),
                  ),
                _PlanActions(
                  lifecycle: lifecycle,
                  onSave: onSave,
                  onActivate: onActivate,
                  onEdit: onEdit,
                  onPause: onPause,
                  onResume: onResume,
                  onCancel: onCancel,
                ),
                const SizedBox(height: AppSpacing.sm),
                const _PlannedBoundaryNote(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanCardHeader extends StatelessWidget {
  final Map<String, dynamic> plan;
  final String lifecycle;
  final int itemCount;

  const _PlanCardHeader({
    required this.plan,
    required this.lifecycle,
    required this.itemCount,
  });

  @override
  Widget build(BuildContext context) {
    final gradient = PlanDisplay.isNutrition(plan)
        ? AppColors.calorieGradient
        : PlanDisplay.isWorkout(plan)
            ? AppColors.exerciseGradient
            : AppColors.primaryGradient;
    final revision = plan['revision_number']?.toString() ?? '—';
    final titleStyle = Theme.of(context).textTheme.titleMedium?.copyWith(
          color: Colors.white,
          fontWeight: FontWeight.w800,
        );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(gradient: gradient),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .2),
              borderRadius: BorderRadius.circular(AppRadius.md),
            ),
            child: Icon(PlanDisplay.domainIcon(plan), color: Colors.white),
          ),
          const SizedBox(width: AppSpacing.sm + 2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(PlanDisplay.domainTitle(plan), style: titleStyle),
                const SizedBox(height: 3),
                Text(
                  PlanDisplay.shortDateRange(plan),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Colors.white.withValues(alpha: .9),
                      ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: [
                    _HeaderPill(label: _statusLabel(lifecycle)),
                    _HeaderPill(label: 'Bản $revision'),
                    _HeaderPill(label: '$itemCount mục dự kiến'),
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

class _InlinePlanMeta extends StatelessWidget {
  final Map<String, dynamic> plan;
  final String lifecycle;
  final int itemCount;

  const _InlinePlanMeta({
    required this.plan,
    required this.lifecycle,
    required this.itemCount,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm + 4),
      child: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.xs,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          _MetaText(
            icon: Icons.calendar_today_outlined,
            text: PlanDisplay.shortDateRange(plan),
          ),
          _MetaText(
            icon: Icons.event_note_outlined,
            text: '$itemCount mục dự kiến',
          ),
          _Pill(
            label: _statusLabel(lifecycle),
            color: _statusColor(lifecycle),
          ),
        ],
      ),
    );
  }
}

class _DayCard extends StatelessWidget {
  final Map<String, dynamic> day;
  final bool nutrition;

  const _DayCard({required this.day, required this.nutrition});

  @override
  Widget build(BuildContext context) {
    final items = PlanDisplay.items(day);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: AppSpacing.sm + 2),
      padding: const EdgeInsets.all(AppSpacing.sm + 4),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(
          color: Colors.black.withValues(alpha: 0.04),
          width: 1,
        ),
        boxShadow: AppShadows.subtle,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: (nutrition ? AppColors.calories : AppColors.success)
                      .withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(AppRadius.sm),
                ),
                child: Icon(
                  Icons.calendar_today_rounded,
                  size: 14,
                  color: nutrition ? AppColors.calories : AppColors.success,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  _dayLabel(day['date']?.toString()),
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                        fontSize: 14,
                        letterSpacing: -0.2,
                      ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(AppRadius.pill),
                ),
                child: Text(
                  '${items.length} ${nutrition ? 'bữa' : 'buổi'}',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm + 2),
          if (items.isEmpty)
            const _EmptyDayItems()
          else
            ...items.map(
              (item) => _PlanItemTile(item: item, nutrition: nutrition),
            ),
        ],
      ),
    );
  }
}

class _PlanItemTile extends StatelessWidget {
  final Map<String, dynamic> item;
  final bool nutrition;

  const _PlanItemTile({required this.item, required this.nutrition});

  @override
  Widget build(BuildContext context) {
    final isMeal = item['item_type']?.toString() == 'MEAL';
    final itemIsNutrition = nutrition || isMeal;
    final nutritionValues = PlanDisplay.nutrition(item);
    final calories = nutritionValues['total_calories'];
    final protein = nutritionValues['total_protein'];
    final carbs = nutritionValues['total_carbs'];
    final fat = nutritionValues['total_fat'];
    final duration = PlanDisplay.plannedDuration(item);
    final slot = PlanDisplay.slotLabel(item['slot']?.toString(),
        nutrition: itemIsNutrition);
    final title = PlanDisplay.itemTitle(item, nutrition: itemIsNutrition);

    final color = itemIsNutrition ? AppColors.calories : AppColors.success;
    final icon = itemIsNutrition
        ? Icons.restaurant_outlined
        : Icons.fitness_center_outlined;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: AppSpacing.xs + 2),
      padding: const EdgeInsets.all(AppSpacing.sm + 2),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(
          color: Colors.black.withValues(alpha: 0.03),
          width: 1,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .12),
              borderRadius: BorderRadius.circular(AppRadius.md),
            ),
            child: Icon(
              icon,
              size: 18,
              color: color,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        slot.toUpperCase(),
                        style: TextStyle(
                          color: color,
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: .3,
                        ),
                      ),
                    ),
                    const Spacer(),
                    if (calories is num)
                      Text(
                        '${calories.round()} kcal',
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.calories,
                        ),
                      )
                    else if (duration != null)
                      Text(
                        '${duration.round()} phút',
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.success,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  title,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        fontSize: 13.5,
                      ),
                ),
                if (protein is num || carbs is num || fat is num) ...[
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      if (protein is num)
                        _MacroBadge(
                          label: 'P',
                          value: '${protein.toStringAsFixed(0)}g',
                          color: AppColors.protein,
                        ),
                      if (carbs is num)
                        _MacroBadge(
                          label: 'C',
                          value: '${carbs.toStringAsFixed(0)}g',
                          color: AppColors.carbs,
                        ),
                      if (fat is num)
                        _MacroBadge(
                          label: 'F',
                          value: '${fat.toStringAsFixed(0)}g',
                          color: AppColors.fat,
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MacroBadge extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _MacroBadge({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        '$label: $value',
        style: TextStyle(
          fontSize: 10.5,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}

class _EmptyPlanItems extends StatelessWidget {
  final String domain;

  const _EmptyPlanItems({required this.domain});

  @override
  Widget build(BuildContext context) {
    final combined = domain == 'COMBINED_HEALTH';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(AppRadius.lg),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, color: AppColors.textSecondary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              combined
                  ? 'Bản tổng hợp này không chứa món hoặc buổi tập trực tiếp. Hãy mở các kế hoạch con đã được tạo riêng.'
                  : 'Revision này chưa có món hoặc buổi tập để hiển thị. Không có dữ liệu nào bị tự suy diễn.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: AppColors.textSecondary,
                    height: 1.4,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyDayItems extends StatelessWidget {
  const _EmptyDayItems();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Text(
          'Chưa có mục nào được lên lịch cho ngày này.',
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
}

class _PlanConflictNotice extends StatelessWidget {
  const _PlanConflictNotice();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(AppSpacing.sm + 2),
        decoration: BoxDecoration(
          color: AppColors.error.withValues(alpha: .08),
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: const Text(
          'Kế hoạch đã có bản mới hơn. Hãy làm mới trước khi tiếp tục.',
          style: TextStyle(color: AppColors.error),
        ),
      );
}

class _PlannedBoundaryNote extends StatelessWidget {
  const _PlannedBoundaryNote();

  @override
  Widget build(BuildContext context) => const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.visibility_outlined,
              size: 16, color: AppColors.textSecondary),
          SizedBox(width: AppSpacing.xs + 2),
          Expanded(
            child: Text(
              'Đây là lịch dự kiến; chỉ nhật ký xác nhận mới được tính là đã ăn hoặc đã tập.',
              style: TextStyle(color: AppColors.textSecondary, height: 1.35),
            ),
          ),
        ],
      );
}

class _HeaderPill extends StatelessWidget {
  final String label;

  const _HeaderPill({required this.label});

  @override
  Widget build(BuildContext context) => Container(
        padding:
            const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 3),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: .18),
          borderRadius: BorderRadius.circular(AppRadius.pill),
        ),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
        ),
      );
}

class _MetaText extends StatelessWidget {
  final IconData icon;
  final String text;

  const _MetaText({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.textSecondary),
          const SizedBox(width: 4),
          Text(text, style: Theme.of(context).textTheme.labelSmall),
        ],
      );
}

String _dayLabel(String? value) {
  final parsed = DateTime.tryParse(value ?? '');
  if (parsed == null) {
    return value?.trim().isNotEmpty == true ? value! : 'Ngày chưa xác định';
  }
  const weekdays = [
    'Thứ Hai',
    'Thứ Ba',
    'Thứ Tư',
    'Thứ Năm',
    'Thứ Sáu',
    'Thứ Bảy',
    'Chủ Nhật',
  ];
  final weekday = weekdays[(parsed.weekday - 1) % 7];
  final day = parsed.day.toString().padLeft(2, '0');
  final month = parsed.month.toString().padLeft(2, '0');
  return '$weekday • Ngày $day/$month';
}

String _statusLabel(String lifecycle) {
  switch (lifecycle) {
    case 'PENDING_CONFIRMATION':
      return 'Chờ xác nhận';
    case 'SAVED':
      return 'Đã lưu';
    case 'ACTIVE':
      return 'Đang áp dụng';
    case 'PAUSED':
      return 'Tạm dừng';
    case 'COMPLETED':
      return 'Hoàn tất';
    case 'CANCELLED':
      return 'Đã hủy';
    case 'SUPERSEDED':
      return 'Đã có bản mới';
    default:
      return 'Bản nháp';
  }
}

class _PlanActions extends StatelessWidget {
  final String lifecycle;
  final VoidCallback? onSave;
  final VoidCallback? onActivate;
  final VoidCallback? onEdit;
  final VoidCallback? onPause;
  final VoidCallback? onResume;
  final VoidCallback? onCancel;

  const _PlanActions({
    required this.lifecycle,
    this.onSave,
    this.onActivate,
    this.onEdit,
    this.onPause,
    this.onResume,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final actions = <Widget>[];
    void add(
      String label,
      VoidCallback? callback, {
      bool isPrimary = false,
      bool isDestructive = false,
    }) {
      if (callback != null) {
        actions.add(
          Padding(
            padding: const EdgeInsets.only(right: 8, bottom: 6),
            child: TextButton(
              onPressed: callback,
              style: TextButton.styleFrom(
                backgroundColor: isPrimary
                    ? AppColors.primary
                    : isDestructive
                        ? AppColors.error.withValues(alpha: 0.08)
                        : AppColors.surfaceLight,
                foregroundColor: isPrimary
                    ? Colors.white
                    : isDestructive
                        ? AppColors.error
                        : AppColors.textPrimary,
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  side: BorderSide(
                    color: isPrimary
                        ? Colors.transparent
                        : isDestructive
                            ? AppColors.error.withValues(alpha: 0.2)
                            : Colors.black.withValues(alpha: 0.06),
                    width: 1,
                  ),
                ),
                textStyle: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              child: Text(label),
            ),
          ),
        );
      }
    }

    switch (lifecycle) {
      case 'DRAFT':
      case 'PENDING_CONFIRMATION':
        add('Lưu kế hoạch', onSave, isPrimary: true);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel, isDestructive: true);
        break;
      case 'SAVED':
        add('Kích hoạt ngay', onActivate, isPrimary: true);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel, isDestructive: true);
        break;
      case 'ACTIVE':
        add('Chỉnh sửa', onEdit);
        add('Tạm dừng', onPause);
        add('Hủy', onCancel, isDestructive: true);
        break;
      case 'PAUSED':
        add('Tiếp tục', onResume, isPrimary: true);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel, isDestructive: true);
        break;
    }
    if (actions.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Wrap(spacing: 0, runSpacing: 0, children: actions),
    );
  }
}

class _Pill extends StatelessWidget {
  final String label;
  final Color? color;
  const _Pill({required this.label, this.color});

  @override
  Widget build(BuildContext context) {
    final effectiveColor = color ?? AppColors.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: effectiveColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppRadius.pill),
        border: Border.all(
          color: effectiveColor.withValues(alpha: 0.25),
          width: 1,
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: effectiveColor,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

Color _statusColor(String lifecycle) {
  switch (lifecycle) {
    case 'ACTIVE':
      return AppColors.accent;
    case 'PENDING_CONFIRMATION':
      return AppColors.warning;
    case 'SAVED':
      return AppColors.info;
    case 'COMPLETED':
      return const Color(0xFF8B5CF6);
    case 'PAUSED':
      return const Color(0xFFF59E0B);
    case 'CANCELLED':
      return AppColors.error;
    default:
      return AppColors.textSecondary;
  }
}
