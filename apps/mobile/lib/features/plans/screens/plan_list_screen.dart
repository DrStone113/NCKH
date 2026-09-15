import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../providers/user_provider.dart';
import '../../../providers/plan_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/bento_card.dart';
import '../plan_display.dart';
import '../plan_snapshot.dart';
import 'plan_detail_screen.dart';

typedef PlanHistoryLoader = Future<List<PlanSnapshot>> Function();

/// The discoverable Plan V2 library.
///
/// It reads the authoritative structured payload that the chat backend already
/// persists, rather than reconstructing a plan from LLM text or legacy plans.
class PlanListScreen extends StatefulWidget {
  final VoidCallback? onOpenChat;
  final PlanHistoryLoader? loader;

  const PlanListScreen({
    super.key,
    this.onOpenChat,
    this.loader,
  });

  @override
  State<PlanListScreen> createState() => _PlanListScreenState();
}

class _PlanListScreenState extends State<PlanListScreen> {
  late Future<List<PlanSnapshot>> _plansFuture;

  @override
  void initState() {
    super.initState();
    _plansFuture = widget.loader?.call() ?? _loadPlansFromChatHistory();
  }

  Future<List<PlanSnapshot>> _loadPlansFromChatHistory() async {
    final userId =
        Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null || userId.isEmpty) return const [];
    return Provider.of<PlanProvider>(context, listen: false)
        .loadForUser(userId);
  }

  Future<void> _refresh() async {
    setState(() {
      _plansFuture = widget.loader?.call() ?? _reloadSharedPlans();
    });
    await _plansFuture;
  }

  Future<List<PlanSnapshot>> _reloadSharedPlans() async {
    final userId =
        Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null || userId.isEmpty) return const [];
    return Provider.of<PlanProvider>(context, listen: false)
        .loadForUser(userId, force: true);
  }

  @override
  Widget build(BuildContext context) {
    final sharedPlans =
        widget.loader == null ? context.watch<PlanProvider>() : null;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Kế hoạch'),
        actions: [
          IconButton(
            tooltip: 'Làm mới kế hoạch',
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: FutureBuilder<List<PlanSnapshot>>(
        future: _plansFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const _PlanLoadingState();
          }
          if (snapshot.hasError) {
            return _PlanErrorState(onRetry: _refresh);
          }
          final plans =
              sharedPlans?.plans ?? snapshot.data ?? const <PlanSnapshot>[];
          if (plans.isEmpty) {
            return _PlanEmptyState(onOpenChat: widget.onOpenChat);
          }
          return _PlanList(plans: plans, onRefresh: _refresh);
        },
      ),
    );
  }
}

class _PlanLoadingState extends StatelessWidget {
  const _PlanLoadingState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 12),
          Text('Đang tải kế hoạch...'),
        ],
      ),
    );
  }
}

class _PlanErrorState extends StatelessWidget {
  final Future<void> Function() onRetry;

  const _PlanErrorState({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: BentoCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_outlined,
                  size: 42, color: AppColors.textSecondary),
              const SizedBox(height: 12),
              const Text('Kế hoạch chưa thể tải',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              const Text(
                'Kiểm tra kết nối rồi thử lại.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Thử lại'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanEmptyState extends StatelessWidget {
  final VoidCallback? onOpenChat;

  const _PlanEmptyState({this.onOpenChat});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: BentoCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.event_note_outlined,
                  size: 48, color: AppColors.primary),
              const SizedBox(height: 14),
              const Text('Chưa có kế hoạch',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              const Text(
                'Bạn có thể tạo kế hoạch ăn uống hoặc tập luyện cùng Trợ lý.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary, height: 1.4),
              ),
              if (onOpenChat != null) ...[
                const SizedBox(height: 18),
                ElevatedButton.icon(
                  onPressed: onOpenChat,
                  icon: const Icon(Icons.smart_toy_outlined),
                  label: const Text('Tạo kế hoạch với Trợ lý'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanList extends StatefulWidget {
  final List<PlanSnapshot> plans;
  final Future<void> Function() onRefresh;

  const _PlanList({required this.plans, required this.onRefresh});

  @override
  State<_PlanList> createState() => _PlanListState();
}

class _PlanListState extends State<_PlanList> {
  String _selectedFilter = 'ALL';

  @override
  Widget build(BuildContext context) {
    final filteredPlans = widget.plans.where((snapshot) {
      if (_selectedFilter == 'ALL') return true;
      final domain = snapshot.plan['domain']?.toString() ?? '';
      return domain == _selectedFilter;
    }).toList();

    final current = filteredPlans
        .where((plan) => {'ACTIVE', 'PAUSED'}.contains(plan.lifecycle))
        .toList();
    final pending = filteredPlans
        .where((plan) =>
            {'DRAFT', 'PENDING_CONFIRMATION', 'SAVED'}.contains(plan.lifecycle))
        .toList();
    final history = filteredPlans
        .where((plan) => !{
              'ACTIVE',
              'PAUSED',
              'DRAFT',
              'PENDING_CONFIRMATION',
              'SAVED'
            }.contains(plan.lifecycle))
        .toList();

    return RefreshIndicator(
      onRefresh: widget.onRefresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          _PlanLibraryHero(plans: widget.plans),
          const SizedBox(height: 14),
          _buildFilterBar(),
          const SizedBox(height: 12),
          const _PlannedOnlyBanner(),
          const SizedBox(height: 18),
          if (current.isNotEmpty)
            _PlanSection(title: 'Kế hoạch hiện tại', plans: current),
          if (pending.isNotEmpty)
            _PlanSection(title: 'Đang chuẩn bị', plans: pending),
          if (history.isNotEmpty)
            _PlanSection(title: 'Lịch sử', plans: history),
          if (current.isEmpty && pending.isEmpty && history.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 32),
              child: Center(
                child: Text(
                  'Không tìm thấy kế hoạch phù hợp với bộ lọc.',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    final filters = [
      ('ALL', 'Tất cả'),
      ('NUTRITION', 'Dinh dưỡng 🥗'),
      ('WORKOUT', 'Vận động 🏋️'),
      ('COMBINED_HEALTH', 'Sức khỏe 🩺'),
    ];

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: filters.map((f) {
        final isSelected = _selectedFilter == f.$1;
        return GestureDetector(
          onTap: () => setState(() => _selectedFilter = f.$1),
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
              f.$2,
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected ? Colors.white : AppColors.textSecondary,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _PlanLibraryHero extends StatelessWidget {
  final List<PlanSnapshot> plans;

  const _PlanLibraryHero({required this.plans});

  @override
  Widget build(BuildContext context) {
    final activeCount = plans
        .where((plan) => {'ACTIVE', 'PAUSED'}.contains(plan.lifecycle))
        .length;
    final itemCount = plans.fold<int>(
      0,
      (total, snapshot) => total + PlanDisplay.itemCount(snapshot.plan),
    );

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppRadius.xxl),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.2),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF6366F1), Color(0xFF4F46E5)],
                  ),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: const Icon(Icons.event_note_rounded,
                    color: Colors.white, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Thư viện Kế hoạch',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.3,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Theo dõi các lộ trình dinh dưỡng & tập luyện cá nhân hóa',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.7),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _HeroStatTile(
                  icon: Icons.play_circle_fill_rounded,
                  label: 'Đang áp dụng',
                  value: '$activeCount',
                  accentColor: AppColors.accent,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _HeroStatTile(
                  icon: Icons.checklist_rounded,
                  label: 'Mục dự kiến',
                  value: '$itemCount',
                  accentColor: const Color(0xFF38BDF8),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroStatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color accentColor;

  const _HeroStatTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.accentColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.1),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Icon(icon, color: accentColor, size: 18),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.65),
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PlannedOnlyBanner extends StatelessWidget {
  const _PlannedOnlyBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.info.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(
          color: AppColors.info.withValues(alpha: 0.15),
          width: 1,
        ),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline_rounded, color: AppColors.info, size: 18),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Kế hoạch là lịch dự kiến. Màn này không tự ghi nhận ăn uống hay tập luyện.',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanSection extends StatelessWidget {
  final String title;
  final List<PlanSnapshot> plans;

  const _PlanSection({required this.title, required this.plans});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.2,
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(AppRadius.pill),
              ),
              child: Text(
                '${plans.length}',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        ...plans.map(
          (snapshot) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _PlanOverviewCard(snapshot: snapshot),
          ),
        ),
      ],
    );
  }
}

class _PlanOverviewCard extends StatelessWidget {
  final PlanSnapshot snapshot;

  const _PlanOverviewCard({required this.snapshot});

  @override
  Widget build(BuildContext context) {
    final plan = snapshot.plan;
    final domain = plan['domain']?.toString() ?? '';
    final title = switch (domain) {
      'NUTRITION' => 'Kế hoạch dinh dưỡng',
      'WORKOUT' => 'Kế hoạch tập luyện',
      'COMBINED_HEALTH' => 'Kế hoạch sức khỏe',
      _ => 'Kế hoạch',
    };
    final icon = switch (domain) {
      'NUTRITION' => Icons.restaurant_rounded,
      'WORKOUT' => Icons.fitness_center_rounded,
      _ => Icons.event_note_rounded,
    };
    final domainColor = switch (domain) {
      'NUTRITION' => AppColors.calories,
      'WORKOUT' => AppColors.success,
      _ => AppColors.primary,
    };

    final lifecycle = _lifecycleLabel(snapshot.lifecycle);
    final statusColor = _lifecycleColor(snapshot.lifecycle);
    final itemCount = PlanDisplay.itemCount(plan);
    final previewNames = PlanDisplay.itemNames(plan, limit: 3);
    final openRevisionLabel =
        'Open authoritative plan revision ${snapshot.planId} ${snapshot.revisionId}';

    return InteractiveCard(
      borderRadius: BorderRadius.circular(AppRadius.xl),
      padding: const EdgeInsets.all(16),
      onTap: () => _openDetail(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: domainColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: Icon(icon, color: domainColor, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            title,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.2,
                            ),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: statusColor.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(AppRadius.pill),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: statusColor,
                                ),
                              ),
                              const SizedBox(width: 5),
                              Text(
                                lifecycle,
                                style: TextStyle(
                                  color: statusColor,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        const Icon(Icons.calendar_today_rounded,
                            size: 13, color: AppColors.textSecondary),
                        const SizedBox(width: 5),
                        Text(
                          '${plan['period_start'] ?? '—'} – ${plan['period_end'] ?? '—'}',
                          style: const TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12.5,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        if (itemCount > 0) ...[
                          const SizedBox(width: 10),
                          Container(
                            width: 3,
                            height: 3,
                            decoration: const BoxDecoration(
                              shape: BoxShape.circle,
                              color: AppColors.textHint,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            '$itemCount mục dự kiến',
                            style: const TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 12.5,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (previewNames.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: previewNames
                  .map(
                    (name) => Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: domainColor.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(AppRadius.pill),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            domain == 'NUTRITION'
                                ? Icons.restaurant_menu_rounded
                                : Icons.fitness_center_rounded,
                            size: 12,
                            color: domainColor,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            name,
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                  .toList(growable: false),
            ),
          ] else if (itemCount == 0) ...[
            const SizedBox(height: 8),
            const Text(
              'Chưa có món hoặc buổi tập trong revision này.',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 12,
              ),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Semantics(
                label: openRevisionLabel,
                button: true,
                onTap: () => _openDetail(context),
                excludeSemantics: true,
                child: TextButton.icon(
                  onPressed: () => _openDetail(context),
                  icon: const Icon(Icons.arrow_forward_rounded, size: 16),
                  label: const Text('Xem chi tiết'),
                  style: TextButton.styleFrom(
                    foregroundColor: AppColors.primary,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _openDetail(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => PlanDetailScreen(plan: snapshot.plan)),
    );
  }
}

String _lifecycleLabel(String lifecycle) => switch (lifecycle) {
      'PENDING_CONFIRMATION' => 'Chờ xác nhận',
      'SAVED' => 'Đã lưu',
      'ACTIVE' => 'Đang áp dụng',
      'PAUSED' => 'Tạm dừng',
      'COMPLETED' => 'Hoàn tất',
      'CANCELLED' => 'Đã hủy',
      'SUPERSEDED' => 'Đã có bản mới',
      _ => 'Bản nháp',
    };

Color _lifecycleColor(String lifecycle) => switch (lifecycle) {
      'ACTIVE' => AppColors.accent,
      'PENDING_CONFIRMATION' => AppColors.warning,
      'SAVED' => AppColors.info,
      'COMPLETED' => const Color(0xFF8B5CF6),
      'PAUSED' => const Color(0xFFF59E0B),
      'CANCELLED' => AppColors.error,
      _ => AppColors.textSecondary,
    };
