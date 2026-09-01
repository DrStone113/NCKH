import 'package:flutter/material.dart';

/// Renderer for the structured P1 Plan V2 response.  No value in this card is
/// parsed from model prose: the backend supplies an immutable revision and its
/// canonical references.
class VersionedPlanCard extends StatelessWidget {
  final Map<String, dynamic> plan;
  final VoidCallback? onSave;
  final VoidCallback? onActivate;
  final VoidCallback? onEdit;
  final VoidCallback? onPause;
  final VoidCallback? onResume;
  final VoidCallback? onCancel;

  const VersionedPlanCard({
    super.key,
    required this.plan,
    this.onSave,
    this.onActivate,
    this.onEdit,
    this.onPause,
    this.onResume,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final days = (plan['days'] as List<dynamic>? ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    final domain = plan['domain']?.toString() ?? 'PLAN';
    final revision = plan['revision_number']?.toString() ?? '—';
    final isNutrition = domain == 'NUTRITION';
    final lifecycle = plan['lifecycle_status']?.toString() ?? 'DRAFT';
    final isConflict = plan['status']?.toString() == 'PLAN_REVISION_CONFLICT';

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(isNutrition ? Icons.restaurant_menu : Icons.fitness_center,
                    color: colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    isNutrition ? 'Kế hoạch dinh dưỡng' : 'Kế hoạch tập luyện',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    _Pill(label: _statusLabel(lifecycle)),
                    const SizedBox(height: 4),
                    Text('Bản $revision',
                        style: Theme.of(context).textTheme.labelSmall),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${plan['period_start'] ?? ''} → ${plan['period_end'] ?? ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 10),
            if (days.isEmpty)
              const Text(
                  'Kế hoạch này cần thêm thông tin trước khi có mục để hiển thị.')
            else
              ...days.map((day) => _DayCard(day: day, nutrition: isNutrition)),
            if (isConflict) ...[
              const SizedBox(height: 8),
              Text(
                'Kế hoạch đã có bản mới hơn. Hãy làm mới rồi thử lại; thay đổi của bạn chưa ghi đè lên bản mới.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colorScheme.error,
                    ),
              ),
            ],
            _PlanActions(
              lifecycle: lifecycle,
              onSave: onSave,
              onActivate: onActivate,
              onEdit: onEdit,
              onPause: onPause,
              onResume: onResume,
              onCancel: onCancel,
            ),
            const SizedBox(height: 8),
            Text(
              'Đây là lịch dự kiến; chỉ nhật ký xác nhận mới được tính là đã ăn hoặc đã tập.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
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
    final items = (day['items'] as List<dynamic>? ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Theme.of(context)
            .colorScheme
            .surfaceContainerHighest
            .withValues(alpha: .45),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(day['date']?.toString() ?? '',
              style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          ...items.map((item) {
            final dish = item['dish_name']?.toString();
            final duration = item['planned_duration_minutes'];
            final label = dish?.isNotEmpty == true
                ? dish!
                : nutrition
                    ? item['slot']?.toString() ?? 'Bữa ăn'
                    : duration is num
                        ? 'Buổi tập • ${duration.round()} phút'
                        : 'Buổi tập theo lịch E4';
            return Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text('• Dự kiến: $label',
                  style: Theme.of(context).textTheme.bodyMedium),
            );
          }),
        ],
      ),
    );
  }
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
    void add(String label, VoidCallback? callback) {
      if (callback != null) {
        actions.add(TextButton(onPressed: callback, child: Text(label)));
      }
    }

    switch (lifecycle) {
      case 'DRAFT':
      case 'PENDING_CONFIRMATION':
        add('Lưu', onSave);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel);
        break;
      case 'SAVED':
        add('Kích hoạt', onActivate);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel);
        break;
      case 'ACTIVE':
        add('Chỉnh sửa', onEdit);
        add('Tạm dừng', onPause);
        add('Hủy', onCancel);
        break;
      case 'PAUSED':
        add('Tiếp tục', onResume);
        add('Chỉnh sửa', onEdit);
        add('Hủy', onCancel);
        break;
    }
    if (actions.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Wrap(spacing: 2, runSpacing: 0, children: actions),
    );
  }
}

class _Pill extends StatelessWidget {
  final String label;
  const _Pill({required this.label});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(99),
        ),
        child: Text(label, style: Theme.of(context).textTheme.labelSmall),
      );
}
