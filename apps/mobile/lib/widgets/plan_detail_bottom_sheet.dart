import 'package:flutter/material.dart';
import '../services/backend_api_service.dart';
import '../theme/app_theme.dart';

/// Hiển thị bottom sheet chi tiết kế hoạch sức khỏe
Future<void> showPlanDetailBottomSheet(
  BuildContext context, {
  required String userId,
  required Map<String, dynamic> initialPlan,
  required BackendApiService backendApi,
  void Function(String prompt)? onAskAI,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _PlanDetailSheet(
      userId: userId,
      initialPlan: initialPlan,
      backendApi: backendApi,
      onAskAI: onAskAI,
    ),
  );
}

class _PlanDetailSheet extends StatefulWidget {
  final String userId;
  final Map<String, dynamic> initialPlan;
  final BackendApiService backendApi;
  final void Function(String prompt)? onAskAI;

  const _PlanDetailSheet({
    required this.userId,
    required this.initialPlan,
    required this.backendApi,
    this.onAskAI,
  });

  @override
  State<_PlanDetailSheet> createState() => _PlanDetailSheetState();
}

class _PlanDetailSheetState extends State<_PlanDetailSheet> {
  bool _loading = true;
  Map<String, dynamic>? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadDetail();
  }

  Future<void> _loadDetail() async {
    setState(() => _loading = true);
    try {
      final detail = await widget.backendApi.getActivePlanDetail(widget.userId);
      if (!mounted) return;
      setState(() {
        _detail = detail ?? widget.initialPlan;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _detail = widget.initialPlan;
        _error = e.toString();
        _loading = false;
      });
    }
  }

  String _formatGoal(String? goal) {
    switch (goal) {
      case 'lose_weight':
        return 'Giảm cân & Giảm mỡ';
      case 'gain_muscle':
        return 'Tăng cơ & Sức mạnh';
      case 'maintain':
        return 'Duy trì vóc dáng & Sức khỏe';
      default:
        return goal ?? 'Sức khỏe tổng thể';
    }
  }

  IconData _getGoalIcon(String? goal) {
    switch (goal) {
      case 'lose_weight':
        return Icons.local_fire_department_rounded;
      case 'gain_muscle':
        return Icons.fitness_center_rounded;
      case 'maintain':
        return Icons.favorite_rounded;
      default:
        return Icons.track_changes_rounded;
    }
  }

  Color _getGoalColor(String? goal) {
    switch (goal) {
      case 'lose_weight':
        return Colors.orange;
      case 'gain_muscle':
        return Colors.deepPurple;
      case 'maintain':
        return Colors.teal;
      default:
        return AppColors.primary;
    }
  }

  Future<void> _toggleItemCompleted(int index, String itemId, bool current) async {
    final newCompleted = !current;
    final items = List<Map<String, dynamic>>.from(_detail?['items'] ?? []);
    if (index < items.length) {
      setState(() {
        items[index] = {...items[index], 'completed': newCompleted};
        _detail = {...?_detail, 'items': items};
      });
    }

    try {
      await widget.backendApi.updatePlanItemCompletion(
        itemId: itemId,
        completed: newCompleted,
      );
    } catch (e) {
      // Revert on error
      if (mounted && index < items.length) {
        setState(() {
          items[index] = {...items[index], 'completed': current};
          _detail = {...?_detail, 'items': items};
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không thể cập nhật mục: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final plan = _detail ?? widget.initialPlan;
    final goal = plan['goal'] as String?;
    final goalColor = _getGoalColor(goal);
    final durationDays = plan['duration_days'] ?? 0;
    final dailyKcal = plan['daily_kcal_target'] ?? 0;
    final dailyProtein = plan['daily_protein_target'] ?? 0;
    final startDate = plan['start_date'] ?? '';
    final endDate = plan['end_date'] ?? '';
    final items = (plan['items'] as List<dynamic>?) ?? [];

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            children: [
              // Handle bar
              Center(
                child: Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey[300],
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              // App bar header
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: goalColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(_getGoalIcon(goal), color: goalColor, size: 24),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Chi tiết Kế hoạch Sức khỏe',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              color: Colors.black87,
                            ),
                          ),
                          Text(
                            _formatGoal(goal),
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: goalColor,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, color: Colors.grey),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
              ),

              const Divider(height: 1),

              // Content
              Expanded(
                child: _loading
                    ? const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircularProgressIndicator(),
                            SizedBox(height: 12),
                            Text('Đang tải chi tiết kế hoạch...'),
                          ],
                        ),
                      )
                    : ListView(
                        controller: scrollController,
                        padding: const EdgeInsets.all(20),
                        children: [
                          // Status & Timeline Card
                          Container(
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  goalColor.withValues(alpha: 0.08),
                                  goalColor.withValues(alpha: 0.02),
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: goalColor.withValues(alpha: 0.25),
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 10, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: Colors.green.withValues(alpha: 0.15),
                                        borderRadius: BorderRadius.circular(20),
                                      ),
                                      child: const Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(Icons.check_circle_rounded,
                                              size: 14, color: Colors.green),
                                          SizedBox(width: 4),
                                          Text(
                                            'Đang hoạt động',
                                            style: TextStyle(
                                              fontSize: 12,
                                              fontWeight: FontWeight.bold,
                                              color: Colors.green,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    Text(
                                      'Lộ trình $durationDays ngày',
                                      style: const TextStyle(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w600,
                                        color: Colors.black87,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  children: [
                                    const Icon(Icons.date_range_rounded,
                                        size: 16, color: Colors.grey),
                                    const SizedBox(width: 6),
                                    Text(
                                      'Từ $startDate đến $endDate',
                                      style: const TextStyle(
                                        fontSize: 13,
                                        color: Colors.black54,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(height: 16),

                          // Target metrics grid (Calo & Protein)
                          Row(
                            children: [
                              Expanded(
                                child: Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: Colors.orange.withValues(alpha: 0.08),
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(
                                      color:
                                          Colors.orange.withValues(alpha: 0.2),
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Row(
                                        children: [
                                          Icon(Icons.local_fire_department,
                                              color: Colors.orange, size: 20),
                                          SizedBox(width: 6),
                                          Text(
                                            'Mục tiêu Calo',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: Colors.black54,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        '$dailyKcal',
                                        style: const TextStyle(
                                          fontSize: 20,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.orange,
                                        ),
                                      ),
                                      const Text(
                                        'kcal / ngày',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.black45,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: Colors.blue.withValues(alpha: 0.08),
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(
                                      color: Colors.blue.withValues(alpha: 0.2),
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Row(
                                        children: [
                                          Icon(Icons.egg_alt_rounded,
                                              color: Colors.blue, size: 20),
                                          SizedBox(width: 6),
                                          Text(
                                            'Mục tiêu Đạm',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: Colors.black54,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        '${dailyProtein}g',
                                        style: const TextStyle(
                                          fontSize: 20,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.blue,
                                        ),
                                      ),
                                      const Text(
                                        'protein / ngày',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.black45,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 24),

                          // Items List or Macro Overview Card
                          if (items.isNotEmpty) ...[
                            const Text(
                              'Lộ trình từng ngày',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 12),
                            ListView.separated(
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              itemCount: items.length,
                              separatorBuilder: (_, __) =>
                                  const SizedBox(height: 8),
                              itemBuilder: (context, idx) {
                                final it =
                                    items[idx] as Map<String, dynamic>;
                                final itemId = it['id']?.toString() ?? '';
                                final isCompleted =
                                    it['completed'] == true;
                                final title = it['title'] ?? 'Mục kế hoạch';
                                final targetItemKcal = it['target_kcal'];
                                final targetItemProtein =
                                    it['target_protein'];
                                final dayIdx = it['day_index'] ?? 1;

                                return Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 8),
                                  decoration: BoxDecoration(
                                    color: isCompleted
                                        ? Colors.grey.withValues(alpha: 0.05)
                                        : Colors.white,
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: isCompleted
                                          ? Colors.grey.shade300
                                          : AppColors.primary
                                              .withValues(alpha: 0.2),
                                    ),
                                  ),
                                  child: Row(
                                    children: [
                                      Checkbox(
                                        value: isCompleted,
                                        activeColor: AppColors.primary,
                                        onChanged: (val) {
                                          if (itemId.isNotEmpty) {
                                            _toggleItemCompleted(
                                                idx, itemId, isCompleted);
                                          }
                                        },
                                      ),
                                      const SizedBox(width: 6),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              'Ngày $dayIdx: $title',
                                              style: TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.w600,
                                                decoration: isCompleted
                                                    ? TextDecoration
                                                        .lineThrough
                                                    : null,
                                                color: isCompleted
                                                    ? Colors.grey
                                                    : Colors.black87,
                                              ),
                                            ),
                                            if (targetItemKcal != null ||
                                                targetItemProtein != null)
                                              Text(
                                                '${targetItemKcal != null ? "$targetItemKcal kcal" : ""} ${targetItemProtein != null ? "• ${targetItemProtein}g đạm" : ""}',
                                                style: const TextStyle(
                                                  fontSize: 12,
                                                  color: Colors.black54,
                                                ),
                                              ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                );
                              },
                            ),
                          ] else ...[
                            Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: AppColors.surfaceLight,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: AppColors.primary
                                      .withValues(alpha: 0.15),
                                ),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      const Icon(Icons.auto_awesome,
                                          color: Colors.amber, size: 20),
                                      const SizedBox(width: 8),
                                      const Text(
                                        'Mục tiêu tổng thể đã kích hoạt',
                                        style: TextStyle(
                                          fontSize: 15,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.black87,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  const Text(
                                    'Mục tiêu Calo và Đạm hàng ngày của bạn đã được lưu tự động vào hệ thống. Mọi gợi ý bữa ăn và bài tập từ AI Chatbot sẽ tuân thủ nghiêm ngặt mục tiêu này.',
                                    style: TextStyle(
                                      fontSize: 13,
                                      color: Colors.black54,
                                      height: 1.4,
                                    ),
                                  ),
                                  const SizedBox(height: 16),
                                  const Text(
                                    'Bạn muốn làm gì tiếp theo?',
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                      color: Colors.black87,
                                    ),
                                  ),
                                  const SizedBox(height: 10),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    children: [
                                      ActionChip(
                                        avatar: const Icon(
                                            Icons.restaurant_menu,
                                            size: 16,
                                            color: Colors.black87),
                                        label: const Text('Gợi ý bữa ăn hôm nay'),
                                        onPressed: () {
                                          Navigator.of(context).pop();
                                          widget.onAskAI?.call(
                                              'Gợi ý bữa ăn hôm nay phù hợp với mục tiêu $dailyKcal kcal của tôi');
                                        },
                                      ),
                                      ActionChip(
                                        avatar: const Icon(
                                            Icons.directions_run,
                                            size: 16,
                                            color: Colors.black87),
                                        label: const Text('Gợi ý bài tập hôm nay'),
                                        onPressed: () {
                                          Navigator.of(context).pop();
                                          widget.onAskAI?.call(
                                              'Gợi ý bài tập hôm nay phù hợp với lộ trình $durationDays ngày của tôi');
                                        },
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ],
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}
