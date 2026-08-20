import 'package:flutter/material.dart';
import '../models/wger_models.dart';
import '../models/workout_routine_model.dart';
import '../services/wger_detail_service.dart';
import '../features/exercise/screens/workout_simulation_screen.dart';
import 'wger_image.dart';

/// Hiển thị bottom sheet chi tiết exercise hoặc food từ wger hoặc chuỗi bài tập AI
Future<void> showDetailBottomSheet(
  BuildContext context,
  ActionItem action, {
  Future<void> Function()? onSave,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _DetailSheet(action: action, onSave: onSave),
  );
}

class _DetailSheet extends StatefulWidget {
  final ActionItem action;
  final Future<void> Function()? onSave;
  const _DetailSheet({required this.action, this.onSave});

  @override
  State<_DetailSheet> createState() => _DetailSheetState();
}

class _DetailSheetState extends State<_DetailSheet>
    with SingleTickerProviderStateMixin {
  bool _loading = true;
  IngredientDetail? _ingredient;
  String? _error;
  late WorkoutRoutinePlan _routinePlan;
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    if (widget.action.kind == 'exercise') {
      _routinePlan = WorkoutRoutineParser.parseFromAction(widget.action);
    }
    _load();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final svc = WgerDetailService();
    try {
      if (widget.action.kind != 'exercise' && widget.action.wgerId > 0) {
        _ingredient = await svc.fetchIngredient(widget.action.wgerId);
      }
    } catch (e) {
      _error = e.toString();
    }
    if (mounted) setState(() => _loading = false);
  }

  void _startWorkoutSimulation() {
    Navigator.pop(context);
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WorkoutSimulationScreen(
          routine: _routinePlan,
          onSaveToJournal: widget.onSave,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isExercise = widget.action.kind == 'exercise';
    final color =
        isExercise ? const Color(0xFF2196F3) : const Color(0xFF4CAF50);

    return DraggableScrollableSheet(
      initialChildSize: 0.88,
      minChildSize: 0.5,
      maxChildSize: 0.96,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
          boxShadow: [
            BoxShadow(
              color: Colors.black26,
              blurRadius: 20,
              offset: Offset(0, -6),
            ),
          ],
        ),
        child: Column(
          children: [
            // Drag handle
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Center(
                child: Container(
                  width: 44,
                  height: 4.5,
                  decoration: BoxDecoration(
                    color: Colors.grey[300],
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: isExercise
                            ? [const Color(0xFF2196F3), const Color(0xFF1976D2)]
                            : [
                                const Color(0xFF4CAF50),
                                const Color(0xFF388E3C)
                              ],
                      ),
                      borderRadius: BorderRadius.circular(14),
                      boxShadow: [
                        BoxShadow(
                          color: color.withValues(alpha: 0.3),
                          blurRadius: 8,
                          offset: const Offset(0, 3),
                        ),
                      ],
                    ),
                    child: Icon(
                      isExercise ? Icons.fitness_center : Icons.restaurant_menu,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.action.name,
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.2,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: color.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                isExercise
                                    ? _routinePlan.level
                                    : 'Thông tin dinh dưỡng',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: color,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.black54),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            const Divider(height: 12),

            // Content
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : isExercise
                      ? _buildStructuredWorkoutView(controller, color)
                      : (_error != null || _ingredient == null)
                          ? ListView(
                              controller: controller,
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                              children: _buildIngredientFallback(color),
                            )
                          : ListView(
                              controller: controller,
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                              children: _buildIngredientContent(color),
                            ),
            ),

            // Bottom Actions Bar
            _buildBottomActionBar(color, isExercise),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // WORKOUT ROUTINE VIEW (3 PHASES + GUIDANCE + SIMULATION CTA)
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildStructuredWorkoutView(
      ScrollController scrollController, Color color) {
    return Column(
      children: [
        // Tab header
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
          child: Container(
            height: 38,
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(10),
            ),
            child: TabBar(
              controller: _tabController,
              indicator: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.06),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              indicatorSize: TabBarIndicatorSize.tab,
              labelColor: color,
              unselectedLabelColor: Colors.grey[600],
              labelStyle:
                  const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              unselectedLabelStyle:
                  const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
              tabs: const [
                Tab(text: 'Lộ trình & Giai đoạn'),
                Tab(text: 'Kỹ thuật & An toàn'),
              ],
            ),
          ),
        ),

        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              // Tab 1: 3 Giai đoạn tập luyện
              _buildPhasesTab(scrollController, color),

              // Tab 2: Hướng dẫn kỹ thuật & Form
              _buildGuidanceTab(scrollController, color),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildPhasesTab(ScrollController scrollController, Color color) {
    final totalExercises = _routinePlan.totalExercisesCount;
    final completedCount = _routinePlan.completedExercisesCount;
    final progress = _routinePlan.overallProgress;

    return ListView(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
      children: [
        // Summary & Stats Overview Card
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                color.withValues(alpha: 0.08),
                color.withValues(alpha: 0.03),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color.withValues(alpha: 0.15)),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _statChip(
                      Icons.timer_outlined,
                      '${_routinePlan.totalDurationMinutes} phút',
                      'Thời gian',
                      color),
                  _statChip(
                      Icons.local_fire_department_outlined,
                      '~${_routinePlan.totalCalories.toStringAsFixed(0)} kcal',
                      'Calo đốt',
                      const Color(0xFFFF7043)),
                  _statChip(
                      Icons.format_list_bulleted_rounded,
                      '$totalExercises bài tập',
                      'Động tác',
                      const Color(0xFF9C27B0)),
                ],
              ),
              const SizedBox(height: 12),
              // Thanh tiến độ
              Row(
                children: [
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: progress,
                        minHeight: 6,
                        backgroundColor: Colors.grey[200],
                        valueColor: AlwaysStoppedAnimation<Color>(
                            progress >= 1.0 ? Colors.green : color),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    '${(progress * 100).toStringAsFixed(0)}% ($completedCount/$totalExercises)',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: progress >= 1.0 ? Colors.green : color,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 18),

        // Danh sách 3 giai đoạn
        ..._routinePlan.phases.map((phase) => _buildPhaseSection(phase, color)),

        // Amber Disclaimer Box
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.amber.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.amber.withValues(alpha: 0.25)),
          ),
          child: const Row(
            children: [
              Icon(Icons.info_outline, color: Colors.amber, size: 18),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Giáo án được cá nhân hóa bởi AI dựa trên thể trạng và mục tiêu sức khỏe của bạn.',
                  style: TextStyle(fontSize: 12, color: Color(0xFF666666)),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _statChip(IconData icon, String value, String label, Color chipColor) {
    return Column(
      children: [
        Icon(icon, color: chipColor, size: 20),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w800,
            color: Color(0xFF1A1A1A),
          ),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: Color(0xFF888888)),
        ),
      ],
    );
  }

  Widget _buildPhaseSection(WorkoutPhase phase, Color color) {
    Color phaseColor;
    IconData phaseIcon;
    switch (phase.phaseType) {
      case 'warmup':
        phaseColor = Colors.orange;
        phaseIcon = Icons.wb_sunny_outlined;
        break;
      case 'cooldown':
        phaseColor = Colors.teal;
        phaseIcon = Icons.self_improvement_rounded;
        break;
      default:
        phaseColor = color;
        phaseIcon = Icons.fitness_center_rounded;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Phase Header Banner
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: phaseColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(phaseIcon, color: phaseColor, size: 16),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      phase.title,
                      style: TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w800,
                        color: phaseColor,
                      ),
                    ),
                    Text(
                      phase.description,
                      style: const TextStyle(
                          fontSize: 11.5, color: Color(0xFF777777)),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.grey[100],
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '${phase.durationMinutes} phút',
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF666666),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          // Exercise cards within this phase
          ...phase.exercises.asMap().entries.map((entry) {
            final index = entry.key + 1;
            final step = entry.value;
            return _buildExerciseStepCard(step, index, phaseColor);
          }),
        ],
      ),
    );
  }

  Widget _buildExerciseStepCard(
      WorkoutExerciseStep step, int index, Color phaseColor) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: step.isCompleted
              ? Colors.green.withValues(alpha: 0.4)
              : Colors.grey.withValues(alpha: 0.2),
          width: step.isCompleted ? 1.5 : 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(14),
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            leading: Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: step.isCompleted
                    ? Colors.green
                    : phaseColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: step.isCompleted
                    ? const Icon(Icons.check, color: Colors.white, size: 18)
                    : Text(
                        index.toString().padLeft(2, '0'),
                        style: TextStyle(
                          fontSize: 12.5,
                          fontWeight: FontWeight.w800,
                          color: phaseColor,
                        ),
                      ),
              ),
            ),
            title: Text(
              step.name,
              style: TextStyle(
                fontSize: 14.5,
                fontWeight: FontWeight.w700,
                decoration:
                    step.isCompleted ? TextDecoration.lineThrough : null,
                color: step.isCompleted
                    ? Colors.grey[600]
                    : const Color(0xFF1A1A1A),
              ),
            ),
            subtitle: Row(
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 2),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: phaseColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    '${step.sets} hiệp × ${step.reps}',
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700,
                      color: phaseColor,
                    ),
                  ),
                ),
                if (step.vietnameseName.isNotEmpty) ...[
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      step.vietnameseName,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF888888),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ],
            ),
            trailing: Checkbox(
              value: step.isCompleted,
              activeColor: Colors.green,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(4),
              ),
              onChanged: (val) {
                setState(() {
                  step.isCompleted = val ?? false;
                  if (step.isCompleted) {
                    step.completedSets = step.sets;
                  } else {
                    step.completedSets = 0;
                  }
                });
              },
            ),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Divider(height: 1),
                    const SizedBox(height: 10),

                    // Chips: Nhóm cơ & Thiết bị
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _chipSmall(Icons.accessibility_new,
                            step.targetMusclesText, Colors.orange),
                        _chipSmall(Icons.fitness_center, step.equipment,
                            Colors.blueGrey),
                        _chipSmall(Icons.timer_outlined,
                            'Nghỉ ${step.restSeconds}s', Colors.teal),
                      ],
                    ),
                    const SizedBox(height: 10),

                    // Hướng dẫn kỹ thuật
                    if (step.instructions.isNotEmpty) ...[
                      const Text(
                        '📋 Kỹ thuật thực hiện:',
                        style: TextStyle(
                            fontSize: 12.5,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF333333)),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        step.instructions,
                        style: const TextStyle(
                            fontSize: 12.5,
                            height: 1.5,
                            color: Color(0xFF555555)),
                      ),
                      const SizedBox(height: 8),
                    ],

                    // Nhịp thở
                    if (step.breathingCue.isNotEmpty) ...[
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.teal.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                              color: Colors.teal.withValues(alpha: 0.2)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.air, color: Colors.teal, size: 16),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                step.breathingCue,
                                style: const TextStyle(
                                    fontSize: 12,
                                    color: Colors.teal,
                                    fontWeight: FontWeight.w600),
                              ),
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
        ),
      ),
    );
  }

  Widget _chipSmall(IconData icon, String label, Color chipColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: chipColor.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: chipColor),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
                fontSize: 11, color: chipColor, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GUIDANCE TAB (FORM, BREATHING, RECOVERY TIPS)
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildGuidanceTab(ScrollController scrollController, Color color) {
    return ListView(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      children: [
        _guidanceSection(
          icon: Icons.lightbulb_outline,
          iconColor: Colors.amber,
          title: 'Nguyên tắc tập luyện an toàn',
          items: [
            'Luôn khởi động kỹ 3-5 phút trước khi bước vào các bài tập chính.',
            'Không khóa cứng khớp khuỷu tay và khớp gối khi phát lực tối đa.',
            'Nếu cảm thấy đau nhói bất thường ở khớp, hãy dừng lại ngay.',
          ],
        ),
        const SizedBox(height: 14),
        _guidanceSection(
          icon: Icons.air,
          iconColor: Colors.teal,
          title: 'Kỹ thuật Hít thở chuẩn Thể hình',
          items: [
            'Hít sâu bằng mũi trong pha hạ tạ hoặc mở rộng cơ thể (pha nạp năng lượng).',
            'Thở dứt khoát bằng miệng trong pha phát lực, đẩy hoặc kéo tạ.',
            'Tuyệt đối không nín thở (Valsalva quá lâu) để tránh tăng huyết áp đột ngột.',
          ],
        ),
        const SizedBox(height: 14),
        _guidanceSection(
          icon: Icons.water_drop_outlined,
          iconColor: Colors.blue,
          title: 'Bổ sung nước & Dinh dưỡng phục hồi',
          items: [
            'Uống từng ngụm nhỏ 100-150ml sau mỗi 15-20 phút luyện tập.',
            'Nạp bữa ăn giàu Protein (20-30g) kết hợp tinh bột hấp thu vừa trong 45 phút sau tập.',
            'Ngủ đủ 7-8 tiếng để cơ bắp tái tạo và tổng hợp sợi cơ mới.',
          ],
        ),
      ],
    );
  }

  Widget _guidanceSection({
    required IconData icon,
    required Color iconColor,
    required String title,
    required List<String> items,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey[200]!),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: iconColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(icon, color: iconColor, size: 18),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF1A1A1A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...items.map((it) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• ',
                        style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF666666))),
                    Expanded(
                      child: Text(
                        it,
                        style: const TextStyle(
                            fontSize: 13,
                            height: 1.45,
                            color: Color(0xFF444444)),
                      ),
                    ),
                  ],
                ),
              )),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // BOTTOM ACTIONS BAR (SIMULATION PLAYER + SAVE TO JOURNAL)
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildBottomActionBar(Color color, bool isExercise) {
    return Container(
      padding: EdgeInsets.fromLTRB(
          20, 10, 20, MediaQuery.of(context).padding.bottom + 12),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 10,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: isExercise
          ? Row(
              children: [
                // Nút Bắt đầu Luyện tập & Mô phỏng (Primary Button)
                Expanded(
                  flex: 3,
                  child: ElevatedButton.icon(
                    onPressed: _startWorkoutSimulation,
                    icon: const Icon(Icons.play_circle_filled_rounded,
                        size: 22, color: Colors.white),
                    label: const Text(
                      'Bắt đầu luyện tập',
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: Colors.white),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: color,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                      elevation: 2,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Nút Lưu nhật ký
                Expanded(
                  flex: 2,
                  child: OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onSave?.call();
                    },
                    icon: const Icon(Icons.bookmark_add_outlined, size: 18),
                    label: const Text(
                      'Lưu nhật ký',
                      style:
                          TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: color,
                      side: BorderSide(color: color, width: 1.5),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                  ),
                ),
              ],
            )
          : SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {
                  Navigator.pop(context);
                  widget.onSave?.call();
                },
                icon: const Icon(Icons.bookmark_add_outlined, size: 20),
                label: const Text('Lưu vào nhật ký',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: color,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                  elevation: 0,
                ),
              ),
            ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INGREDIENT CONTENT (FOOD)
  // ═══════════════════════════════════════════════════════════════════════════

  List<Widget> _buildIngredientContent(Color color) {
    final ing = _ingredient;
    if (ing == null) return _buildIngredientFallback(color);

    return [
      if (ing.imageUrl != null) ...[
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: WgerImage(ing.imageUrl!,
              height: 160,
              width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const SizedBox.shrink()),
        ),
        const SizedBox(height: 16),
      ],
      if (ing.brand != null || ing.commonName != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Wrap(spacing: 8, children: [
            if (ing.brand != null)
              _chip(ing.brand!, Icons.store_outlined, Colors.blueGrey),
            if (ing.commonName != null)
              _chip(ing.commonName!, Icons.label_outline, Colors.teal),
          ]),
        ),
      _sectionTitle('🔥 Dinh dưỡng / 100g', color),
      const SizedBox(height: 12),
      Row(
        children: [
          _macroCard('Calo', '${ing.energy?.toStringAsFixed(0) ?? 0}', 'kcal',
              const Color(0xFFFF7043)),
          const SizedBox(width: 8),
          _macroCard('Protein', '${ing.protein?.toStringAsFixed(1) ?? 0}', 'g',
              const Color(0xFFE53935)),
          const SizedBox(width: 8),
          _macroCard('Carbs', '${ing.carbohydrates?.toStringAsFixed(1) ?? 0}',
              'g', const Color(0xFFFFA000)),
          const SizedBox(width: 8),
          _macroCard('Fat', '${ing.fat?.toStringAsFixed(1) ?? 0}', 'g',
              const Color(0xFF00ACC1)),
        ],
      ),
      const SizedBox(height: 20),
    ];
  }

  List<Widget> _buildIngredientFallback(Color color) {
    final d = widget.action.details;
    return [
      _sectionTitle('🔥 Dinh dưỡng / 100g', color),
      const SizedBox(height: 12),
      Row(
        children: [
          if (d['calories'] != null)
            _macroCard(
                'Calo', '${d['calories']}', 'kcal', const Color(0xFFFF7043)),
          if (d['protein'] != null) ...[
            const SizedBox(width: 8),
            _macroCard(
                'Protein', '${d['protein']}', 'g', const Color(0xFFE53935)),
          ],
          if (d['carbs'] != null) ...[
            const SizedBox(width: 8),
            _macroCard('Carbs', '${d['carbs']}', 'g', const Color(0xFFFFA000)),
          ],
          if (d['fat'] != null) ...[
            const SizedBox(width: 8),
            _macroCard('Fat', '${d['fat']}', 'g', const Color(0xFF00ACC1)),
          ],
        ],
      ),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.amber.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.amber.withValues(alpha: 0.3)),
        ),
        child: const Row(
          children: [
            Icon(Icons.info_outline, color: Colors.amber, size: 18),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Thông tin dinh dưỡng được cung cấp bởi AI. Giá trị thực tế có thể khác nhau.',
                style: TextStyle(fontSize: 13, color: Color(0xFF666666)),
              ),
            ),
          ],
        ),
      ),
    ];
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _sectionTitle(String title, Color color) => Text(
        title,
        style:
            TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: color),
      );

  Widget _chip(String label, IconData icon, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
            Text(label,
                style: TextStyle(
                    fontSize: 12, color: color, fontWeight: FontWeight.w600)),
          ],
        ),
      );

  Widget _macroCard(String label, String value, String unit, Color color) =>
      Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withValues(alpha: 0.2)),
          ),
          child: Column(
            children: [
              Text(value,
                  style: TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w800, color: color)),
              Text(unit,
                  style: TextStyle(
                      fontSize: 11, color: color.withValues(alpha: 0.8))),
              const SizedBox(height: 2),
              Text(label,
                  style: const TextStyle(
                      fontSize: 11,
                      color: Color(0xFF666666),
                      fontWeight: FontWeight.w500)),
            ],
          ),
        ),
      );
}
