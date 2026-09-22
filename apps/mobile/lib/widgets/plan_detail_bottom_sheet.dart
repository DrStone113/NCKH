import 'package:flutter/material.dart';
import '../services/backend_api_service.dart';
import '../theme/app_theme.dart';

({int fullWeeks, int remainingDays, int totalWeeks}) planWeekBreakdown(
  int durationDays,
) {
  final safeDays = durationDays.clamp(1, 365);
  return (
    fullWeeks: safeDays ~/ 7,
    remainingDays: safeDays % 7,
    totalWeeks: (safeDays / 7).ceil(),
  );
}

int planPhaseIndexForWeek(int weekIndex, int totalWeeks) {
  final safeTotal = totalWeeks.clamp(1, 52);
  final safeWeek = weekIndex.clamp(1, safeTotal);
  if (safeTotal == 1) return 1;
  if (safeTotal == 2) return safeWeek == 1 ? 1 : 4;
  if (safeTotal == 3) return const [1, 2, 4][safeWeek - 1];
  return ((safeWeek * 4 + safeTotal - 1) ~/ safeTotal).clamp(1, 4);
}

String formatPlanDurationByWeeks(int durationDays) {
  final breakdown = planWeekBreakdown(durationDays);
  if (breakdown.fullWeeks == 0) return '$durationDays ngày';
  if (breakdown.remainingDays == 0) {
    return '$durationDays ngày • ${breakdown.fullWeeks} tuần';
  }
  return '$durationDays ngày • ${breakdown.fullWeeks} tuần + '
      '${breakdown.remainingDays} ngày';
}

String formatPlanDayCalendarLabel({
  required String startDate,
  required int dayIndex,
  String? weekdayName,
}) {
  DateTime? planDate;
  try {
    planDate = DateTime.parse(startDate).add(Duration(days: dayIndex - 1));
  } catch (_) {
    planDate = null;
  }

  const weekdayNames = [
    'Thứ Hai',
    'Thứ Ba',
    'Thứ Tư',
    'Thứ Năm',
    'Thứ Sáu',
    'Thứ Bảy',
    'Chủ Nhật',
  ];
  final normalizedWeekday = weekdayName?.trim();
  final label = normalizedWeekday != null && normalizedWeekday.isNotEmpty
      ? normalizedWeekday
      : planDate != null
          ? weekdayNames[planDate.weekday - 1]
          : '';
  if (planDate == null) return label;
  final day = planDate.day.toString().padLeft(2, '0');
  final month = planDate.month.toString().padLeft(2, '0');
  return label.isEmpty ? '$day/$month' : '$label • $day/$month';
}

Map<String, dynamic>? planScheduleFromItems(Iterable<dynamic> items) {
  for (final raw in items) {
    if (raw is! Map) continue;
    final payload = raw['payload'];
    if (payload is! Map) continue;
    final schedule = payload['schedule'];
    if (schedule is Map) return Map<String, dynamic>.from(schedule);
  }
  return null;
}

String? planWeeklyTrainingSummary(Map<String, dynamic>? schedule) {
  final value = schedule?['weekly_training_summary']?.toString().trim();
  return value == null || value.isEmpty ? null : value;
}

/// Nhóm item theo toàn bộ khoảng ngày cần hiển thị.
///
/// Map luôn chứa cả ngày chưa có dữ liệu để UI không làm biến mất các ngày
/// còn thiếu trong một kế hoạch nhiều ngày.
Map<int, List<Map<String, dynamic>>> groupPlanItemsByDay({
  required List<dynamic> rawItems,
  required int startDayIndex,
  required int endDayIndex,
}) {
  final grouped = <int, List<Map<String, dynamic>>>{
    for (var day = startDayIndex; day <= endDayIndex; day++) day: [],
  };

  for (var i = 0; i < rawItems.length; i++) {
    final raw = rawItems[i];
    if (raw is! Map) continue;
    final item = Map<String, dynamic>.from(raw);
    final dayIndex = (item['day_index'] as num?)?.toInt();
    if (dayIndex == null || !grouped.containsKey(dayIndex)) continue;
    grouped[dayIndex]!.add({...item, '_originalIndex': i});
  }

  return grouped;
}

/// Hiển thị bottom sheet chi tiết kế hoạch sức khỏe theo lộ trình tuần
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
  int _selectedWeek = 1;

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
      final plan = detail ?? widget.initialPlan;
      final curWeek = _computeCurrentWeek(plan);
      setState(() {
        _detail = plan;
        _selectedWeek = curWeek;
        _loading = false;
      });
    } catch (e) {
      debugPrint('Error loading plan detail: $e');
      if (!mounted) return;
      final curWeek = _computeCurrentWeek(widget.initialPlan);
      setState(() {
        _detail = widget.initialPlan;
        _selectedWeek = curWeek;
        _loading = false;
      });
    }
  }

  int _computeCurrentWeek(Map<String, dynamic> plan) {
    final durationDays = (plan['duration_days'] as num?)?.toInt() ?? 7;
    final totalWeeks = (durationDays / 7).ceil().clamp(1, 52);
    final startDateStr = plan['start_date'] as String?;
    if (startDateStr == null || startDateStr.isEmpty) return 1;

    try {
      final startDate = DateTime.parse(startDateStr);
      final now = DateTime.now();
      final diff = now.difference(startDate).inDays;
      if (diff < 0) return 1;
      final calculated = (diff ~/ 7) + 1;
      return calculated.clamp(1, totalWeeks);
    } catch (_) {
      return 1;
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

  Map<String, dynamic> _getPhaseInfo(int week, int totalWeeks, String? goal) {
    final phaseIndex = planPhaseIndexForWeek(week, totalWeeks);
    if (goal == 'gain_muscle') {
      if (phaseIndex == 1) {
        return {
          'phaseTitle': 'Giai đoạn 1: Thích nghi & Xây dựng phom tập',
          'phaseBadge': 'Giai đoạn 1',
          'icon': Icons.flag_rounded,
          'color': Colors.blue,
          'target':
              'Thặng dư nhẹ 200 kcal/ngày, tập trung chuẩn form kỹ thuật.',
          'focus':
              'Protein 1.8g/kg, ngủ đủ 8 tiếng, làm quen lịch tập 4 buổi/tuần.',
          'weightTarget': '+0.3 ~ +0.5 kg cơ',
        };
      } else if (phaseIndex == 2) {
        return {
          'phaseTitle': 'Giai đoạn 2: Tăng tiến tải trọng (Overload)',
          'phaseBadge': 'Giai đoạn 2',
          'icon': Icons.fitness_center_rounded,
          'color': Colors.deepPurple,
          'target':
              'Thặng dư 350 kcal/ngày, tăng tạ dần đều (Progressive Overload).',
          'focus': 'Protein 2.0g/kg, bổ sung carb phức trước & sau tập.',
          'weightTarget': '+0.5 ~ +0.8 kg',
        };
      } else if (phaseIndex == 3) {
        return {
          'phaseTitle': 'Giai đoạn 3: Đột phá kích thước & Sức mạnh',
          'phaseBadge': 'Giai đoạn 3',
          'icon': Icons.bolt_rounded,
          'color': Colors.indigo,
          'target': 'Thặng dư 400 kcal/ngày, cường độ tập luyện tối đa.',
          'focus':
              'Đa dạng bài tập đa khớp (Compound), bù nước điện giải đầy đủ.',
          'weightTarget': '+0.5 ~ +0.8 kg',
        };
      } else {
        return {
          'phaseTitle': 'Giai đoạn 4: Củng cố & Tối ưu khối cơ nạc',
          'phaseBadge': 'Giai đoạn 4',
          'icon': Icons.verified_rounded,
          'color': Colors.teal,
          'target':
              'Kiểm soát tỷ lệ mỡ thừa, duy trì khối lượng cơ nạc tối đa.',
          'focus': 'Cân bằng dinh dưỡng, kéo giãn phục hồi cơ sau tập.',
          'weightTarget': 'Ổn định thể hình săn chắc',
        };
      }
    }

    if (goal == 'maintain') {
      const titles = [
        'Giai đoạn 1: Thiết lập nhịp sống cân bằng',
        'Giai đoạn 2: Tăng tính đều đặn',
        'Giai đoạn 3: Nâng thể lực toàn diện',
        'Giai đoạn 4: Củng cố thói quen lâu dài',
      ];
      const focuses = [
        'Ổn định giờ ăn, vận động vừa sức và bảo đảm ngày nghỉ thực sự.',
        'Duy trì lịch tập đa dạng, năng lượng cân bằng và giấc ngủ ổn định.',
        'Tăng nhẹ thử thách trong các buổi chính nhưng không hy sinh phục hồi.',
        'Giữ một lịch sinh hoạt có thể tiếp tục sau khi lộ trình kết thúc.',
      ];
      return {
        'phaseTitle': titles[phaseIndex - 1],
        'phaseBadge': 'Giai đoạn $phaseIndex',
        'icon':
            phaseIndex == 4 ? Icons.verified_rounded : Icons.favorite_rounded,
        'color': phaseIndex == 4 ? Colors.teal : Colors.blue,
        'target': 'Giữ năng lượng quanh mức duy trì và cân bằng tải tập.',
        'focus': focuses[phaseIndex - 1],
        'weightTarget': 'Mục tiêu: Duy trì cân nặng ổn định',
      };
    }

    // Default: lose_weight & general
    if (phaseIndex == 1) {
      return {
        'phaseTitle': 'Giai đoạn 1: Khởi động & Thích nghi cơ thể',
        'phaseBadge': 'Giai đoạn 1',
        'icon': Icons.flag_rounded,
        'color': Colors.blue,
        'target': 'Thâm hụt nhẹ 300 kcal/ngày, tạo thói quen, giảm tích nước.',
        'focus':
            'Cắt giảm đường ngọt & đồ chiên rán, uống 2-2.5L nước/ngày, vận động nhẹ 3 buổi/tuần.',
        'weightTarget': 'Mục tiêu: Giảm ~0.8 - 1.2 kg',
      };
    } else if (phaseIndex == 2) {
      return {
        'phaseTitle': 'Giai đoạn 2: Tăng tốc đốt mỡ thừa',
        'phaseBadge': 'Giai đoạn 2',
        'icon': Icons.local_fire_department_rounded,
        'color': Colors.orange,
        'target':
            'Thâm hụt chuẩn 400 - 500 kcal/ngày, tăng oxy hóa mỡ, bảo toàn cơ bắp.',
        'focus':
            'Tăng protein lên 1.6-1.8g/kg, kết hợp Cardio HIIT/LISS + Kháng lực 4 buổi/tuần.',
        'weightTarget': 'Mục tiêu: Giảm ~1.0 - 1.5 kg mỡ',
      };
    } else if (phaseIndex == 3) {
      return {
        'phaseTitle': 'Giai đoạn 3: Đột phá & Chống chững cân',
        'phaseBadge': 'Giai đoạn 3',
        'icon': Icons.bolt_rounded,
        'color': Colors.deepOrange,
        'target':
            'Thâm hụt 400 kcal/ngày, áp dụng 1 ngày Refeed/tuần để kích thích trao đổi chất.',
        'focus':
            'Tăng tải bài tập kháng lực (Progressive Overload), bổ sung chất xơ và rau củ.',
        'weightTarget': 'Mục tiêu: Giảm ~1.0 - 1.2 kg',
      };
    } else {
      return {
        'phaseTitle': 'Giai đoạn 4: Siết nét & Chuyển giao duy trì bền vững',
        'phaseBadge': 'Giai đoạn 4',
        'icon': Icons.verified_rounded,
        'color': Colors.teal,
        'target':
            'Nâng dần calo về TDEE mới (Reverse Dieting), định hình lối sống lâu dài.',
        'focus':
            'Duy trì lịch tập 3-4 buổi/tuần, giữ vóc dáng ổn định không lo tăng cân lại.',
        'weightTarget': 'Mục tiêu: Ổn định vóc dáng & Duy trì',
      };
    }
  }

  Future<void> _toggleItemCompleted(
      int itemIndex, String itemId, bool current) async {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Plan là nội dung dự kiến; hãy ghi nhận actual trong nhật ký.')),
    );
    return;
    // Kept below only as historical UI code until this legacy sheet is
    // removed; no planned state mutation is reachable.
    // ignore: dead_code
    final newCompleted = !current;
    final items = List<Map<String, dynamic>>.from(_detail?['items'] ?? []);
    if (itemIndex < items.length) {
      setState(() {
        items[itemIndex] = {...items[itemIndex], 'completed': newCompleted};
        _detail = {...?_detail, 'items': items};
      });
    }

    try {
      await widget.backendApi.updatePlanItemCompletion(
        itemId: itemId,
        completed: newCompleted,
      );
    } catch (e) {
      if (mounted && itemIndex < items.length) {
        setState(() {
          items[itemIndex] = {...items[itemIndex], 'completed': current};
          _detail = {...?_detail, 'items': items};
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không thể cập nhật mục: $e')),
        );
      }
    }
  }

  void _showCheckinDialog(BuildContext context, String planId) {
    final weightController = TextEditingController();
    final noteController = TextEditingController();
    bool isSubmitting = false;

    showDialog(
      context: context,
      builder: (dialogCtx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Row(
            children: [
              Icon(Icons.monitor_weight_rounded, color: AppColors.primary),
              SizedBox(width: 8),
              Text(
                'Check-in Cân nặng Tuần',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Ghi nhận cân nặng thực tế để AI theo dõi tiến độ và tối ưu lộ trình cho các tuần tiếp theo.',
                style: TextStyle(fontSize: 13, color: Colors.black54),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: weightController,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: 'Cân nặng hiện tại (kg)',
                  hintText: 'Ví dụ: 68.5',
                  prefixIcon: const Icon(Icons.scale_rounded),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: noteController,
                maxLines: 2,
                decoration: InputDecoration(
                  labelText: 'Ghi chú / Cảm nhận tuần qua',
                  hintText: 'Ví dụ: Ăn đúng bữa, tập đủ 4 buổi...',
                  prefixIcon: const Icon(Icons.note_alt_outlined),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: isSubmitting ? null : () => Navigator.pop(dialogCtx),
              child: const Text('Hủy'),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: isSubmitting
                  ? null
                  : () async {
                      final wStr = weightController.text.trim();
                      final weight = double.tryParse(wStr);
                      if (weight == null || weight <= 0) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                              content: Text('Vui lòng nhập cân nặng hợp lệ')),
                        );
                        return;
                      }

                      setDialogState(() => isSubmitting = true);
                      try {
                        await widget.backendApi.createPlanCheckin(
                          userId: widget.userId,
                          planId: planId,
                          weight: weight,
                          note: noteController.text.trim(),
                        );
                        if (dialogCtx.mounted) {
                          Navigator.pop(dialogCtx);
                        }
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: Colors.green,
                              content: Text(
                                  'Đã check-in tuần thành công: $weight kg!'),
                            ),
                          );
                        }
                      } catch (e) {
                        if (dialogCtx.mounted) {
                          setDialogState(() => isSubmitting = false);
                        }
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Lỗi check-in: $e')),
                          );
                        }
                      }
                    },
              child: isSubmitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Lưu Check-in'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final plan = _detail ?? widget.initialPlan;
    final goal = plan['goal'] as String?;
    final goalColor = _getGoalColor(goal);
    final durationDays = (plan['duration_days'] as num?)?.toInt() ?? 7;
    final weekBreakdown = planWeekBreakdown(durationDays);
    final totalWeeks = weekBreakdown.totalWeeks.clamp(1, 52);
    final currentWeek = _computeCurrentWeek(plan);
    final baseDailyKcal = (plan['daily_kcal_target'] as num?)?.toInt() ?? 0;
    final baseDailyProtein =
        (plan['daily_protein_target'] as num?)?.toInt() ?? 0;
    final startDateStr = plan['start_date'] as String? ?? '';
    final endDateStr = plan['end_date'] as String? ?? '';
    final planId = plan['id']?.toString() ?? '';
    final rawItems = (plan['items'] as List<dynamic>?) ?? [];

    // Filter items for selected week
    final startDayIndex = (_selectedWeek - 1) * 7 + 1;
    final endDayIndex = (_selectedWeek * 7).clamp(1, durationDays);

    final itemsByDay = groupPlanItemsByDay(
      rawItems: rawItems,
      startDayIndex: startDayIndex,
      endDayIndex: endDayIndex,
    );
    final weekItems = itemsByDay.values.expand((items) => items).toList();
    final selectedSchedule = planScheduleFromItems(weekItems);
    final dailyKcal =
        (selectedSchedule?['weekly_daily_kcal_target'] as num?)?.round() ??
            baseDailyKcal;
    final dailyProtein =
        (selectedSchedule?['daily_protein_target'] as num?)?.round() ??
            baseDailyProtein;
    var phaseInfo = _getPhaseInfo(_selectedWeek, totalWeeks, goal);
    final schedulePhaseTitle = selectedSchedule?['phase_title']?.toString();
    final scheduleFocus = selectedSchedule?['weekly_focus']?.toString();
    final trainingSummary = planWeeklyTrainingSummary(selectedSchedule);
    if (schedulePhaseTitle != null && schedulePhaseTitle.isNotEmpty) {
      phaseInfo = {
        ...phaseInfo,
        'phaseTitle':
            'Giai đoạn ${selectedSchedule?['phase_index']}: $schedulePhaseTitle',
        if (scheduleFocus != null && scheduleFocus.isNotEmpty)
          'focus': scheduleFocus,
        'target':
            'Khoảng $dailyKcal kcal và ${dailyProtein}g protein mỗi ngày.',
      };
    }
    final populatedDays =
        itemsByDay.values.where((items) => items.isNotEmpty).length;

    return DraggableScrollableSheet(
      initialChildSize: 0.9,
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

              // Header
              Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: goalColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child:
                          Icon(_getGoalIcon(goal), color: goalColor, size: 24),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Lộ trình Kế hoạch Sức khỏe',
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

              // Body
              Expanded(
                child: _loading
                    ? const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircularProgressIndicator(),
                            SizedBox(height: 12),
                            Text('Đang tải chi tiết lộ trình...'),
                          ],
                        ),
                      )
                    : ListView(
                        controller: scrollController,
                        padding: const EdgeInsets.all(16),
                        children: [
                          // 1. Overall Status & Timeline Card
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
                                        color: Colors.green
                                            .withValues(alpha: 0.15),
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
                                    const SizedBox(width: 8),
                                    Flexible(
                                      child: Text(
                                        formatPlanDurationByWeeks(durationDays),
                                        textAlign: TextAlign.right,
                                        style: const TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w600,
                                          color: Colors.black87,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                Row(
                                  children: [
                                    const Icon(Icons.date_range_rounded,
                                        size: 16, color: Colors.grey),
                                    const SizedBox(width: 6),
                                    Text(
                                      'Từ $startDateStr đến $endDateStr',
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

                          // 2. Week Selector Bar (Horizontally scrollable)
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Chọn Tuần Lộ Trình',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black87,
                                ),
                              ),
                              Text(
                                'Tuần $_selectedWeek / $totalWeeks',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: goalColor,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 10),
                          SizedBox(
                            height: 76,
                            child: ListView.separated(
                              scrollDirection: Axis.horizontal,
                              itemCount: totalWeeks,
                              separatorBuilder: (_, __) =>
                                  const SizedBox(width: 8),
                              itemBuilder: (ctx, idx) {
                                final weekNum = idx + 1;
                                final isSelected = weekNum == _selectedWeek;
                                final isCur = weekNum == currentWeek;
                                final isPast = weekNum < currentWeek;
                                final daysInWeek = weekNum == totalWeeks &&
                                        weekBreakdown.remainingDays > 0
                                    ? weekBreakdown.remainingDays
                                    : 7;
                                final statusLabel = isCur
                                    ? 'Hiện tại'
                                    : isPast
                                        ? 'Đã qua'
                                        : 'Sắp tới';
                                final weekStatus = daysInWeek < 7
                                    ? '$daysInWeek ngày • $statusLabel'
                                    : statusLabel;

                                return InkWell(
                                  borderRadius: BorderRadius.circular(14),
                                  onTap: () {
                                    setState(() => _selectedWeek = weekNum);
                                  },
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    width: daysInWeek < 7 ? 112 : 96,
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 8),
                                    decoration: BoxDecoration(
                                      color: isSelected
                                          ? goalColor
                                          : isCur
                                              ? goalColor.withValues(
                                                  alpha: 0.12)
                                              : Colors.grey.shade100,
                                      borderRadius: BorderRadius.circular(14),
                                      border: Border.all(
                                        color: isSelected
                                            ? goalColor
                                            : isCur
                                                ? goalColor.withValues(
                                                    alpha: 0.5)
                                                : Colors.grey.shade300,
                                        width: isSelected || isCur ? 1.5 : 1,
                                      ),
                                      boxShadow: isSelected
                                          ? [
                                              BoxShadow(
                                                color: goalColor.withValues(
                                                    alpha: 0.3),
                                                blurRadius: 6,
                                                offset: const Offset(0, 3),
                                              )
                                            ]
                                          : null,
                                    ),
                                    child: Column(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Text(
                                          'Tuần $weekNum',
                                          style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.bold,
                                            color: isSelected
                                                ? Colors.white
                                                : Colors.black87,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: isSelected
                                                ? Colors.white
                                                    .withValues(alpha: 0.25)
                                                : isCur
                                                    ? Colors.green
                                                        .withValues(alpha: 0.2)
                                                    : Colors.transparent,
                                            borderRadius:
                                                BorderRadius.circular(8),
                                          ),
                                          child: Text(
                                            weekStatus,
                                            style: TextStyle(
                                              fontSize:
                                                  daysInWeek < 7 ? 9.5 : 10,
                                              fontWeight: FontWeight.w600,
                                              color: isSelected
                                                  ? Colors.white
                                                  : isCur
                                                      ? Colors.green.shade800
                                                      : Colors.black45,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),

                          const SizedBox(height: 16),

                          // 3. Phase Details & Weekly Target Milestone Card
                          Container(
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: (phaseInfo['color'] as Color)
                                  .withValues(alpha: 0.07),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: (phaseInfo['color'] as Color)
                                    .withValues(alpha: 0.3),
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Icon(
                                      phaseInfo['icon'] as IconData,
                                      color: phaseInfo['color'] as Color,
                                      size: 22,
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        phaseInfo['phaseTitle'] as String,
                                        style: TextStyle(
                                          fontSize: 15,
                                          fontWeight: FontWeight.bold,
                                          color: phaseInfo['color'] as Color,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  '🎯 Mục tiêu tuần: ${phaseInfo['target']}',
                                  style: const TextStyle(
                                    fontSize: 13,
                                    color: Colors.black87,
                                    height: 1.3,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '💡 Trọng tâm: ${phaseInfo['focus']}',
                                  style: const TextStyle(
                                    fontSize: 13,
                                    color: Colors.black54,
                                    height: 1.3,
                                  ),
                                ),
                                if (trainingSummary != null) ...[
                                  const SizedBox(height: 6),
                                  Text(
                                    '🏃 Lịch vận động: $trainingSummary',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      color: Colors.black54,
                                      height: 1.3,
                                    ),
                                  ),
                                ],
                                const SizedBox(height: 12),
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 8),
                                  decoration: BoxDecoration(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(10),
                                    border:
                                        Border.all(color: Colors.grey.shade200),
                                  ),
                                  child: Row(
                                    mainAxisAlignment:
                                        MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        phaseInfo['weightTarget'] as String,
                                        style: const TextStyle(
                                          fontSize: 12,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.black87,
                                        ),
                                      ),
                                      InkWell(
                                        onTap: () {
                                          if (planId.isNotEmpty) {
                                            _showCheckinDialog(context, planId);
                                          }
                                        },
                                        child: Row(
                                          children: [
                                            Icon(Icons.edit_calendar_rounded,
                                                size: 15,
                                                color: phaseInfo['color']
                                                    as Color),
                                            const SizedBox(width: 4),
                                            Text(
                                              'Check-in tuần',
                                              style: TextStyle(
                                                fontSize: 12,
                                                fontWeight: FontWeight.bold,
                                                color:
                                                    phaseInfo['color'] as Color,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(height: 16),

                          // 4. Daily Calo & Protein Targets
                          Row(
                            children: [
                              Expanded(
                                child: Container(
                                  padding: const EdgeInsets.all(14),
                                  decoration: BoxDecoration(
                                    color:
                                        Colors.orange.withValues(alpha: 0.08),
                                    borderRadius: BorderRadius.circular(14),
                                    border: Border.all(
                                      color:
                                          Colors.orange.withValues(alpha: 0.2),
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      const Row(
                                        children: [
                                          Icon(Icons.local_fire_department,
                                              color: Colors.orange, size: 18),
                                          SizedBox(width: 4),
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
                                      const SizedBox(height: 6),
                                      Text(
                                        '$dailyKcal',
                                        style: const TextStyle(
                                          fontSize: 18,
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
                                  padding: const EdgeInsets.all(14),
                                  decoration: BoxDecoration(
                                    color: Colors.blue.withValues(alpha: 0.08),
                                    borderRadius: BorderRadius.circular(14),
                                    border: Border.all(
                                      color: Colors.blue.withValues(alpha: 0.2),
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      const Row(
                                        children: [
                                          Icon(Icons.egg_alt_rounded,
                                              color: Colors.blue, size: 18),
                                          SizedBox(width: 4),
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
                                      const SizedBox(height: 6),
                                      Text(
                                        '${dailyProtein}g',
                                        style: const TextStyle(
                                          fontSize: 18,
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

                          const SizedBox(height: 20),

                          // 5. Daily Schedule for Selected Week
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  'Lịch trình Tuần $_selectedWeek (Ngày $startDayIndex - $endDayIndex)',
                                  style: const TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.black87,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                '$populatedDays/${itemsByDay.length} ngày có lịch'
                                '${weekItems.isNotEmpty ? '\n${weekItems.where((item) => item['completed'] == true).length}/${weekItems.length} mục xong' : ''}',
                                textAlign: TextAlign.right,
                                style: TextStyle(
                                  fontSize: 11.5,
                                  fontWeight: FontWeight.w600,
                                  color: populatedDays == itemsByDay.length
                                      ? Colors.green
                                      : Colors.orange.shade700,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),

                          if (itemsByDay.isNotEmpty) ...[
                            ...itemsByDay.entries.map((entry) {
                              final dayNum = entry.key;
                              final dayEntries = entry.value;
                              final daySchedule =
                                  planScheduleFromItems(dayEntries);
                              final calendarLabel = formatPlanDayCalendarLabel(
                                startDate: startDateStr,
                                dayIndex: dayNum,
                                weekdayName:
                                    daySchedule?['weekday_name']?.toString(),
                              );
                              final dayKind =
                                  daySchedule?['day_kind']?.toString();
                              final dayKindLabel = switch (dayKind) {
                                'rest' => 'Nghỉ hoàn toàn',
                                'active_recovery' => 'Phục hồi chủ động',
                                'workout' => 'Buổi tập',
                                _ => null,
                              };
                              final dayKindColor = switch (dayKind) {
                                'rest' => Colors.teal,
                                'active_recovery' => Colors.blue,
                                _ => Colors.deepPurple,
                              };
                              final dayTargetKcal =
                                  (daySchedule?['daily_kcal_target'] as num?)
                                      ?.round();
                              final dayTargetProtein =
                                  (daySchedule?['daily_protein_target'] as num?)
                                      ?.round();
                              final isRefeedDay =
                                  daySchedule?['is_refeed_day'] == true;

                              return Container(
                                margin: const EdgeInsets.only(bottom: 12),
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade50,
                                  borderRadius: BorderRadius.circular(14),
                                  border:
                                      Border.all(color: Colors.grey.shade200),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Padding(
                                      padding: const EdgeInsets.only(
                                          bottom: 8, left: 4, right: 4),
                                      child: Row(
                                        children: [
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment:
                                                  CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  calendarLabel.isEmpty
                                                      ? 'Ngày $dayNum'
                                                      : calendarLabel,
                                                  style: const TextStyle(
                                                    fontSize: 13,
                                                    fontWeight: FontWeight.bold,
                                                    color: Colors.black87,
                                                  ),
                                                ),
                                                Text(
                                                  'Ngày $dayNum trong lộ trình',
                                                  style: const TextStyle(
                                                    fontSize: 11,
                                                    color: Colors.black45,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          if (dayKindLabel != null)
                                            Container(
                                              padding:
                                                  const EdgeInsets.symmetric(
                                                horizontal: 8,
                                                vertical: 4,
                                              ),
                                              decoration: BoxDecoration(
                                                color: dayKindColor.withValues(
                                                    alpha: 0.1),
                                                borderRadius:
                                                    BorderRadius.circular(10),
                                                border: Border.all(
                                                  color: dayKindColor
                                                      .withValues(alpha: 0.25),
                                                ),
                                              ),
                                              child: Text(
                                                dayKindLabel,
                                                style: TextStyle(
                                                  fontSize: 10.5,
                                                  fontWeight: FontWeight.w600,
                                                  color: dayKindColor,
                                                ),
                                              ),
                                            ),
                                        ],
                                      ),
                                    ),
                                    if (daySchedule != null)
                                      Padding(
                                        padding: const EdgeInsets.only(
                                            left: 4, right: 4, bottom: 8),
                                        child: Wrap(
                                          spacing: 6,
                                          runSpacing: 4,
                                          children: [
                                            if (dayTargetKcal != null)
                                              _ScheduleMetricChip(
                                                icon: Icons
                                                    .local_fire_department_rounded,
                                                label: '$dayTargetKcal kcal',
                                                color: Colors.orange,
                                              ),
                                            if (dayTargetProtein != null)
                                              _ScheduleMetricChip(
                                                icon: Icons.egg_alt_rounded,
                                                label:
                                                    '${dayTargetProtein}g đạm',
                                                color: Colors.blue,
                                              ),
                                            if (isRefeedDay)
                                              const _ScheduleMetricChip(
                                                icon: Icons.sync_rounded,
                                                label: 'Nạp lại có kiểm soát',
                                                color: Colors.green,
                                              ),
                                          ],
                                        ),
                                      ),
                                    if (dayEntries.isEmpty)
                                      Container(
                                        width: double.infinity,
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 12,
                                          vertical: 10,
                                        ),
                                        decoration: BoxDecoration(
                                          color: Colors.orange
                                              .withValues(alpha: 0.06),
                                          borderRadius:
                                              BorderRadius.circular(10),
                                          border: Border.all(
                                            color: Colors.orange
                                                .withValues(alpha: 0.18),
                                          ),
                                        ),
                                        child: Row(
                                          children: [
                                            Icon(
                                              Icons.event_busy_outlined,
                                              size: 18,
                                              color: Colors.orange.shade700,
                                            ),
                                            const SizedBox(width: 8),
                                            const Expanded(
                                              child: Text(
                                                'Chưa có thực đơn hoặc bài tập cho ngày này.',
                                                style: TextStyle(
                                                  fontSize: 12.5,
                                                  color: Colors.black54,
                                                ),
                                              ),
                                            ),
                                            if (widget.onAskAI != null)
                                              TextButton(
                                                onPressed: () {
                                                  Navigator.of(context).pop();
                                                  widget.onAskAI?.call(
                                                    'Bổ sung thực đơn và lịch tập chi tiết cho Ngày $dayNum trong kế hoạch sức khỏe hiện tại của tôi.',
                                                  );
                                                },
                                                child: const Text(
                                                  'Bổ sung',
                                                  style:
                                                      TextStyle(fontSize: 12),
                                                ),
                                              ),
                                          ],
                                        ),
                                      ),
                                    ...dayEntries.map((it) {
                                      final origIdx =
                                          it['_originalIndex'] as int;
                                      final itemId = it['id']?.toString() ?? '';
                                      final isCompleted =
                                          it['completed'] == true;
                                      final title =
                                          it['title'] ?? 'Mục kế hoạch';
                                      final targetItemKcal = it['target_kcal'];
                                      final targetItemProtein =
                                          it['target_protein'];
                                      final itemType =
                                          it['item_type'] ?? 'meal';
                                      final isExercise = itemType == 'exercise';

                                      return Container(
                                        margin:
                                            const EdgeInsets.only(bottom: 6),
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 10, vertical: 8),
                                        decoration: BoxDecoration(
                                          color: isCompleted
                                              ? Colors.grey
                                                  .withValues(alpha: 0.06)
                                              : Colors.white,
                                          borderRadius:
                                              BorderRadius.circular(10),
                                          border: Border.all(
                                            color: isCompleted
                                                ? Colors.grey.shade300
                                                : isExercise
                                                    ? Colors.deepPurple
                                                        .withValues(alpha: 0.2)
                                                    : AppColors.primary
                                                        .withValues(alpha: 0.2),
                                          ),
                                        ),
                                        child: Row(
                                          children: [
                                            Checkbox(
                                              value: isCompleted,
                                              activeColor: isExercise
                                                  ? Colors.deepPurple
                                                  : AppColors.primary,
                                              onChanged: (val) {
                                                if (itemId.isNotEmpty) {
                                                  _toggleItemCompleted(origIdx,
                                                      itemId, isCompleted);
                                                }
                                              },
                                            ),
                                            Icon(
                                              isExercise
                                                  ? Icons.fitness_center_rounded
                                                  : Icons
                                                      .restaurant_menu_rounded,
                                              size: 18,
                                              color: isCompleted
                                                  ? Colors.grey
                                                  : isExercise
                                                      ? Colors.deepPurple
                                                      : Colors.orange,
                                            ),
                                            const SizedBox(width: 8),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    title,
                                                    style: TextStyle(
                                                      fontSize: 13.5,
                                                      fontWeight:
                                                          FontWeight.w600,
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
                                                        fontSize: 11.5,
                                                        color: Colors.black54,
                                                      ),
                                                    ),
                                                ],
                                              ),
                                            ),
                                          ],
                                        ),
                                      );
                                    }),
                                  ],
                                ),
                              );
                            }),
                          ] else ...[
                            // Empty state for this week
                            Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: AppColors.surfaceLight,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color:
                                      AppColors.primary.withValues(alpha: 0.15),
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
                                      Text(
                                        'Khung Lộ trình Tuần $_selectedWeek đã sẵn sàng',
                                        style: const TextStyle(
                                          fontSize: 14.5,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.black87,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Mục tiêu và nguyên tắc dinh dưỡng cho Tuần $_selectedWeek đã được lưu vào hệ thống. Bạn có thể yêu cầu AI lập thực đơn và lịch tập chi tiết từng ngày cho tuần này bất kỳ lúc nào.',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      color: Colors.black54,
                                      height: 1.4,
                                    ),
                                  ),
                                  const SizedBox(height: 14),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    children: [
                                      ActionChip(
                                        avatar: const Icon(
                                            Icons.restaurant_menu,
                                            size: 16,
                                            color: Colors.black87),
                                        label: Text(
                                            'Gợi ý thực đơn Tuần $_selectedWeek'),
                                        onPressed: () {
                                          Navigator.of(context).pop();
                                          widget.onAskAI?.call(
                                            'Gợi ý thực đơn chi tiết cho Tuần $_selectedWeek ($dailyKcal kcal/ngày, ${dailyProtein}g đạm) theo lộ trình $durationDays ngày của tôi',
                                          );
                                        },
                                      ),
                                      ActionChip(
                                        avatar: const Icon(Icons.directions_run,
                                            size: 16, color: Colors.black87),
                                        label: Text(
                                            'Lịch tập Tuần $_selectedWeek'),
                                        onPressed: () {
                                          Navigator.of(context).pop();
                                          widget.onAskAI?.call(
                                            'Lập lịch tập luyện chi tiết cho Tuần $_selectedWeek (${phaseInfo['phaseTitle']}) theo lộ trình của tôi',
                                          );
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

class _ScheduleMetricChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _ScheduleMetricChip({
    required this.icon,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
