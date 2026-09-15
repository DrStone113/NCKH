import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../models/exercise_model.dart';
import '../../../models/wger_models.dart';
import '../../../models/workout_routine_model.dart';
import '../../../theme/app_theme.dart';
import '../../../utils/exercise_utils.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/animated_counter.dart';
import '../../../widgets/smart_exercise_picker.dart';
import '../../../widgets/workout_simulation_painter.dart';
import 'exercise_browser_screen.dart';
import 'exercise_history_screen.dart';
import 'workout_simulation_screen.dart';
import '../../chat/screens/chatbot_screen.dart';
import '../../plans/widgets/planned_day_plan_section.dart';

class ExerciseScreen extends StatefulWidget {
  const ExerciseScreen({super.key});

  @override
  State<ExerciseScreen> createState() => _ExerciseScreenState();
}

class _ExerciseScreenState extends State<ExerciseScreen> {
  final _categories = [
    {
      'icon': Icons.directions_run_rounded,
      'label': 'Cardio',
      'type': 'cardio',
      'color': AppColors.cardio,
      'desc': 'Đốt mỡ & Sức bền'
    },
    {
      'icon': Icons.fitness_center_rounded,
      'label': 'Sức mạnh',
      'type': 'strength',
      'color': AppColors.strength,
      'desc': 'Tăng cơ & Săn chắc'
    },
    {
      'icon': Icons.self_improvement_rounded,
      'label': 'Linh hoạt',
      'type': 'flexibility',
      'color': AppColors.flexibility,
      'desc': 'Dẻo dai & Thăng bằng'
    },
    {
      'icon': Icons.sports_soccer_rounded,
      'label': 'Thể thao',
      'type': 'sports',
      'color': AppColors.sports,
      'desc': 'Năng động & Phản xạ'
    },
  ];

  @override
  Widget build(BuildContext context) {
    final exerciseProvider = Provider.of<ExerciseProvider>(context);
    final user = Provider.of<UserProvider>(context).currentUser;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Vận động & Luyện tập'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.history_rounded),
            tooltip: 'Lịch sử tập luyện',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ExerciseHistoryScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.smart_toy_outlined),
            tooltip: 'Hỏi AI gợi ý bài tập',
            onPressed: () => _openAIChat(context),
          ),
          IconButton(
            icon: const Icon(Icons.explore_outlined),
            tooltip: 'Khám phá bài tập wger',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ExerciseBrowserScreen()),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 80),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Stats Overview
            AnimatedCard(delay: 0, child: _buildStatsRow(exerciseProvider)),
            const SizedBox(height: 18),

            // AI Coach Banner
            AnimatedCard(delay: 50, child: _buildAIBanner(context)),
            const SizedBox(height: 20),

            // Danh mục bài tập
            AnimatedCard(
              delay: 100,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Danh mục bài tập',
                      style:
                          TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                  TextButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const ExerciseBrowserScreen()),
                    ),
                    icon: const Icon(Icons.grid_view_rounded, size: 16),
                    label: const Text('Tất cả bài',
                        style: TextStyle(fontSize: 12.5)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            AnimatedCard(
                delay: 150,
                child: _buildCategoryGrid(context, exerciseProvider, user)),
            const SizedBox(height: 22),

            if (user != null)
              PlannedDayPlanSection(
                userId: user.id,
                date: DateTime.now(),
                domain: 'WORKOUT',
              ),

            // Actual workout diary. Planned items are shown separately above.
            AnimatedCard(
              delay: 200,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Hoạt động đã ghi nhận hôm nay',
                      style:
                          TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                  Row(
                    children: [
                      if (exerciseProvider.todayExercises.isNotEmpty) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: AppColors.success.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.check_circle_rounded,
                                  size: 13, color: AppColors.success),
                              const SizedBox(width: 4),
                              Text(
                                '${exerciseProvider.completedCount}/${exerciseProvider.todayExercises.length}',
                                style: const TextStyle(
                                    fontSize: 12,
                                    color: AppColors.success,
                                    fontWeight: FontWeight.w700),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 6),
                      ],
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          '${exerciseProvider.todayExercises.length} bài tập',
                          style: const TextStyle(
                              fontSize: 12,
                              color: AppColors.primary,
                              fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            if (exerciseProvider.todayExercises.isEmpty)
              AnimatedCard(delay: 250, child: _buildEmptyExercise(context))
            else
              ..._buildGroupedExercises(
                  context, exerciseProvider.todayExercises),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STATS & BANNERS
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildStatsRow(ExerciseProvider provider) {
    return Row(
      children: [
        Expanded(
          child: _statCard(
            icon: Icons.timer_outlined,
            value: provider.totalDuration.toDouble(),
            unit: 'phút',
            label: 'Thời gian tập',
            gradient: const LinearGradient(
              colors: [Color(0xFF2979FF), Color(0xFF1565C0)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            textColor: Colors.white,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _statCard(
            icon: Icons.local_fire_department_rounded,
            value: provider.totalCaloriesBurned,
            unit: 'kcal',
            label: 'Calo tiêu hao',
            gradient: const LinearGradient(
              colors: [Color(0xFFFF6D00), Color(0xFFE65100)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            textColor: Colors.white,
          ),
        ),
      ],
    );
  }

  Widget _statCard({
    required IconData icon,
    required double value,
    required String unit,
    required String label,
    required LinearGradient gradient,
    required Color textColor,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: gradient.colors.first.withValues(alpha: 0.3),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: textColor.withValues(alpha: 0.85))),
              Icon(icon, color: textColor, size: 20),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              AnimatedCounter(
                value: value,
                decimals: 0,
                style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    color: textColor),
              ),
              const SizedBox(width: 4),
              Text(unit,
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: textColor.withValues(alpha: 0.85))),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAIBanner(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.15),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF38BDF8), Color(0xFF0284C7)],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.smart_toy_rounded,
                      color: Colors.white, size: 24),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'AI Huấn luyện viên thể thao',
                        style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w800,
                            color: Colors.white),
                      ),
                      SizedBox(height: 2),
                      Text(
                        'Nhận giáo án 3 giai đoạn & mô phỏng động tác',
                        style: TextStyle(fontSize: 11.5, color: Colors.white70),
                      ),
                    ],
                  ),
                ),
                ElevatedButton(
                  onPressed: () => _openAIChat(context),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF38BDF8),
                    foregroundColor: const Color(0xFF0F172A),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                    elevation: 0,
                  ),
                  child: const Text('Hỏi AI',
                      style:
                          TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
                ),
              ],
            ),
            const SizedBox(height: 12),
            // Quick prompt chips
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                _quickPromptChip(context, '⚡ Full body đốt mỡ'),
                _quickPromptChip(context, '💪 Tăng cơ ngực & tay sau'),
                _quickPromptChip(context, '🧘 Giãn cơ phục hồi'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _quickPromptChip(BuildContext context, String prompt) {
    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => const ChatbotScreen(showBackButton: true),
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white12),
        ),
        child: Text(
          prompt,
          style: const TextStyle(fontSize: 11, color: Colors.white70),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORIES
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildCategoryGrid(
      BuildContext context, ExerciseProvider provider, user) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 10,
        crossAxisSpacing: 10,
        childAspectRatio: 2.1,
      ),
      itemCount: _categories.length,
      itemBuilder: (context, index) {
        final cat = _categories[index];
        final color = cat['color'] as Color;
        final type = cat['type'] as String;
        final label = cat['label'] as String;
        final icon = cat['icon'] as IconData;
        final desc = cat['desc'] as String;

        return InteractiveCard(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          borderRadius: BorderRadius.circular(AppRadius.lg),
          border: Border.all(
            color: color.withValues(alpha: 0.18),
            width: 1,
          ),
          onTap: () =>
              _showCategorySheet(context, type, label, color, provider, user),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: Icon(icon, color: color, size: 22),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: AppColors.textPrimary),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      desc,
                      style: const TextStyle(
                          fontSize: 11, color: AppColors.textSecondary),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TODAY EXERCISES LIST & CARDS
  // ═══════════════════════════════════════════════════════════════════════════

  List<Widget> _buildGroupedExercises(
      BuildContext context, List<ExerciseModel> exercises) {
    final order = ['morning', 'afternoon', 'evening', 'night'];
    final labels = {
      'morning': ('Buổi sáng', Icons.wb_sunny_rounded, const Color(0xFFFF9800)),
      'afternoon': (
        'Buổi chiều',
        Icons.wb_cloudy_rounded,
        const Color(0xFF2196F3)
      ),
      'evening': (
        'Buổi tối',
        Icons.nights_stay_rounded,
        const Color(0xFF9C27B0)
      ),
      'night': ('Ban đêm', Icons.bedtime_rounded, const Color(0xFF3F51B5)),
    };

    final grouped = <String, List<ExerciseModel>>{};
    for (final ex in exercises) {
      grouped.putIfAbsent(ex.timeOfDay, () => []).add(ex);
    }

    final widgets = <Widget>[];
    int delay = 250;
    for (final key in order) {
      final group = grouped[key];
      if (group == null || group.isEmpty) continue;
      final meta = labels[key]!;
      widgets.add(AnimatedCard(
        delay: delay,
        child: Padding(
          padding: const EdgeInsets.only(top: 10, bottom: 6),
          child: Row(children: [
            Icon(meta.$2, size: 16, color: meta.$3),
            const SizedBox(width: 6),
            Text(meta.$1,
                style: TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w800, color: meta.$3)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                  color: meta.$3.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8)),
              child: Text('${group.length} bài',
                  style: TextStyle(
                      fontSize: 10.5,
                      color: meta.$3,
                      fontWeight: FontWeight.w700)),
            ),
          ]),
        ),
      ));
      delay += 30;
      for (final ex in group) {
        widgets.add(AnimatedCard(
            delay: delay, child: _buildExerciseLogCard(context, ex)));
        delay += 40;
      }
    }
    return widgets;
  }

  Widget _buildExerciseLogCard(BuildContext context, ExerciseModel exercise) {
    final color = _getTypeColor(exercise.type);

    return Dismissible(
      key: Key(exercise.id),
      direction: DismissDirection.endToStart,
      background: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
            color: AppColors.error, borderRadius: BorderRadius.circular(16)),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline_rounded, color: Colors.white),
            SizedBox(width: 8),
            Text('Xoá',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
      confirmDismiss: (_) async => await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Xác nhận xoá'),
          content: Text('Xoá bài tập "${exercise.name}" khỏi lịch hôm nay?'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Huỷ')),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
              child: const Text('Xoá'),
            ),
          ],
        ),
      ),
      onDismissed: (_) {
        Provider.of<ExerciseProvider>(context, listen: false)
            .deleteExercise(exercise.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Đã xoá "${exercise.name}"')),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: exercise.isCompleted
                ? Colors.green.withValues(alpha: 0.3)
                : Colors.grey.withValues(alpha: 0.2),
            width: exercise.isCompleted ? 1.5 : 1.0,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(16),
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: () => _showExerciseDetail(context, exercise),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  // Checkbox Hoàn thành
                  Checkbox(
                    value: exercise.isCompleted,
                    onChanged: (value) {
                      Provider.of<ExerciseProvider>(context, listen: false)
                          .toggleExerciseCompleted(exercise.id);
                    },
                    activeColor: AppColors.success,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(5)),
                  ),
                  const SizedBox(width: 4),

                  // Icon bài tập
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(_getExerciseIcon(exercise.name, exercise.type),
                        color: color, size: 24),
                  ),
                  const SizedBox(width: 12),

                  // Tên & Thông số
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          exercise.name,
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 14.5,
                            decoration: exercise.isCompleted
                                ? TextDecoration.lineThrough
                                : null,
                            color: exercise.isCompleted
                                ? AppColors.textSecondary
                                : const Color(0xFF1A1A1A),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            _infoChip(
                                Icons.timer_outlined,
                                '${exercise.duration} phút',
                                AppColors.textSecondary),
                            const SizedBox(width: 8),
                            _infoChip(
                                Icons.local_fire_department_outlined,
                                '${exercise.caloriesBurned.toStringAsFixed(0)} kcal',
                                const Color(0xFFFF7043)),
                          ],
                        ),
                      ],
                    ),
                  ),

                  // Nút ▶ Tập ngay (Quick Play into Simulation)
                  IconButton(
                    tooltip: 'Bắt đầu luyện tập ngay',
                    icon: Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [color, color.withValues(alpha: 0.8)],
                        ),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: color.withValues(alpha: 0.3),
                            blurRadius: 6,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.play_arrow_rounded,
                          color: Colors.white, size: 18),
                    ),
                    onPressed: () =>
                        _startSimulationForExercise(context, exercise),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // COMPREHENSIVE EXERCISE DETAIL MODAL WITH 3 PHASES & SIMULATION PREVIEW
  // ═══════════════════════════════════════════════════════════════════════════

  void _showExerciseDetail(BuildContext context, ExerciseModel exercise) {
    final color = _getTypeColor(exercise.type);

    // Xây dựng WorkoutRoutinePlan từ ExerciseModel
    final action = ActionItem(
      kind: 'exercise',
      wgerId: exercise.wgerId,
      name: exercise.name,
      details: {
        'duration': exercise.duration,
        'calories_burned': exercise.caloriesBurned,
        'type': exercise.type,
        'intensity': exercise.intensity,
        'description': '',
      },
    );

    final routinePlan = WorkoutRoutineParser.parseFromAction(action);

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => _ExerciseLiveDetailModal(
        exercise: exercise,
        routinePlan: routinePlan,
        color: color,
        onStartSimulation: () {
          Navigator.pop(ctx);
          _startSimulationForExercise(context, exercise, plan: routinePlan);
        },
      ),
    );
  }

  void _startSimulationForExercise(BuildContext context, ExerciseModel exercise,
      {WorkoutRoutinePlan? plan}) {
    final routine = plan ??
        WorkoutRoutineParser.parseFromAction(
          ActionItem(
            kind: 'exercise',
            wgerId: exercise.wgerId,
            name: exercise.name,
            details: {
              'duration': exercise.duration,
              'calories_burned': exercise.caloriesBurned,
              'type': exercise.type,
              'intensity': exercise.intensity,
              'description': '',
            },
          ),
        );

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WorkoutSimulationScreen(
          routine: routine,
          onSaveToJournal: () async {
            // Tự động đánh dấu hoàn thành nếu chưa
            if (!exercise.isCompleted) {
              await Provider.of<ExerciseProvider>(context, listen: false)
                  .toggleExerciseCompleted(exercise.id);
            }
          },
        ),
      ),
    );
  }

  Widget _buildEmptyExercise(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.grey[200]!),
      ),
      child: Column(
        children: [
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.fitness_center_rounded,
                color: AppColors.primary, size: 28),
          ),
          const SizedBox(height: 14),
          const Text('Chưa có hoạt động hôm nay',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text(
            'Thêm bài tập từ danh mục, chọn giáo án gợi ý hoặc hỏi AI để lên lịch tập.',
            style: TextStyle(fontSize: 12.5, color: Color(0xFF777777)),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () => _showAddExerciseSheet(context),
            icon: const Icon(Icons.add_rounded, size: 18),
            label: const Text('Thêm bài tập ngay'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _infoChip(IconData icon, String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 4),
        Text(label,
            style: TextStyle(
                fontSize: 11.5, color: color, fontWeight: FontWeight.w600)),
      ],
    );
  }

  String _defaultTimeOfDay() {
    final hour = DateTime.now().hour;
    if (hour >= 5 && hour < 12) return 'morning';
    if (hour >= 12 && hour < 17) return 'afternoon';
    if (hour >= 17 && hour < 21) return 'evening';
    return 'night';
  }

  Color _getTypeColor(String type) {
    switch (type) {
      case 'cardio':
        return AppColors.cardio;
      case 'strength':
        return AppColors.strength;
      case 'flexibility':
        return AppColors.flexibility;
      case 'sports':
        return AppColors.sports;
      default:
        return AppColors.success;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type) {
      case 'cardio':
        return Icons.directions_run_rounded;
      case 'strength':
        return Icons.fitness_center_rounded;
      case 'flexibility':
        return Icons.self_improvement_rounded;
      case 'sports':
        return Icons.sports_soccer_rounded;
      default:
        return Icons.directions_walk_rounded;
    }
  }

  IconData _getExerciseIcon(String name, String type) {
    final n = name.toLowerCase();
    if (n.contains('pull') || n.contains('chin') || n.contains('xà')) {
      return Icons.airline_seat_flat;
    }
    if (n.contains('push') ||
        n.contains('press') ||
        n.contains('hít đất') ||
        n.contains('bench')) {
      return Icons.arrow_upward;
    }
    if (n.contains('squat') ||
        n.contains('lunge') ||
        n.contains('leg') ||
        n.contains('chân') ||
        n.contains('knee')) {
      return Icons.accessibility_new;
    }
    if (n.contains('deadlift') ||
        n.contains('hip') ||
        n.contains('romanian') ||
        n.contains('hinge')) {
      return Icons.vertical_align_bottom;
    }
    if (n.contains('curl') || n.contains('bicep')) {
      return Icons.sports_handball;
    }
    if (n.contains('tricep') || n.contains('dip')) {
      return Icons.back_hand;
    }
    if (n.contains('plank') ||
        n.contains('crunch') ||
        n.contains('ab') ||
        n.contains('core') ||
        n.contains('bụng')) {
      return Icons.crop_square;
    }
    if (n.contains('run') ||
        n.contains('chạy') ||
        n.contains('jog') ||
        n.contains('sprint')) {
      return Icons.directions_run_rounded;
    }
    if (n.contains('bike') || n.contains('cycle') || n.contains('cycling')) {
      return Icons.directions_bike;
    }
    if (n.contains('swim') || n.contains('bơi')) {
      return Icons.pool;
    }
    if (n.contains('jump') || n.contains('nhảy')) {
      return Icons.keyboard_double_arrow_up;
    }
    if (n.contains('yoga') ||
        n.contains('stretch') ||
        n.contains('flex') ||
        n.contains('giãn')) {
      return Icons.self_improvement_rounded;
    }
    return _getTypeIcon(type);
  }

  void _openAIChat(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => const ChatbotScreen(showBackButton: true),
      ),
    );
  }

  void _showCategorySheet(BuildContext context, String type, String label,
      Color color, ExerciseProvider provider, user) {
    final exercises = provider.getExercisesByType(type);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.75,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        builder: (context, scrollController) => Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 10),
                child: Column(
                  children: [
                    Center(
                      child: Container(
                          width: 40,
                          height: 4,
                          decoration: BoxDecoration(
                              color: Colors.grey[300],
                              borderRadius: BorderRadius.circular(2))),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(12)),
                          child:
                              Icon(_getTypeIcon(type), color: color, size: 24),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(label,
                                style: const TextStyle(
                                    fontSize: 18, fontWeight: FontWeight.w800)),
                            Text('${exercises.length} bài tập mẫu',
                                style: const TextStyle(
                                    fontSize: 12, color: Color(0xFF777777))),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: ListView.builder(
                  controller: scrollController,
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
                  itemCount: exercises.length,
                  itemBuilder: (context, index) {
                    final template = exercises[index];
                    final cal30 = user != null
                        ? template.calculateCalories(user.weight, 30)
                        : 0.0;
                    return Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: Colors.grey[200]!),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.03),
                            blurRadius: 6,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                                color: color.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(12)),
                            child: Icon(_getTypeIcon(type),
                                color: color, size: 22),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(template.name,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 14)),
                                const SizedBox(height: 2),
                                Text(
                                    ExerciseProvider.cleanHtml(
                                        template.description),
                                    style: const TextStyle(
                                        fontSize: 11.5,
                                        color: Color(0xFF777777)),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis),
                              ],
                            ),
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text('~${cal30.toStringAsFixed(0)}',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800,
                                      color: Color(0xFFFF7043),
                                      fontSize: 14)),
                              const Text('kcal/30p',
                                  style: TextStyle(
                                      fontSize: 10, color: Color(0xFF888888))),
                            ],
                          ),
                          const SizedBox(width: 6),
                          IconButton(
                            tooltip: 'Luyện tập ngay',
                            icon: Container(
                              padding: const EdgeInsets.all(6),
                              decoration: BoxDecoration(
                                color: color.withValues(alpha: 0.12),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(Icons.play_arrow_rounded,
                                  color: color, size: 18),
                            ),
                            onPressed: () {
                              Navigator.pop(ctx);
                              final action = ActionItem(
                                kind: 'exercise',
                                wgerId: template.wgerId,
                                name: template.name,
                                details: {
                                  'duration': 30,
                                  'calories_burned': cal30,
                                  'description': template.description,
                                },
                              );
                              final routine =
                                  WorkoutRoutineParser.parseFromAction(action);
                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) =>
                                      WorkoutSimulationScreen(routine: routine),
                                ),
                              );
                            },
                          ),
                          IconButton(
                            tooltip: 'Thêm vào lịch',
                            icon: Container(
                              padding: const EdgeInsets.all(6),
                              decoration: BoxDecoration(
                                color: color.withValues(alpha: 0.12),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(Icons.add_rounded,
                                  color: color, size: 18),
                            ),
                            onPressed: () {
                              Navigator.pop(ctx);
                              _showQuickAddDialog(context, template);
                            },
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showQuickAddDialog(
      BuildContext context, ExerciseTemplate template) async {
    final pageContext = context;
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    String selectedTimeOfDay = _defaultTimeOfDay();

    final timeSlots = [
      {
        'value': 'morning',
        'label': 'Sáng',
        'icon': Icons.wb_sunny_rounded,
        'color': const Color(0xFFFF9800)
      },
      {
        'value': 'afternoon',
        'label': 'Chiều',
        'icon': Icons.wb_cloudy_rounded,
        'color': const Color(0xFF2196F3)
      },
      {
        'value': 'evening',
        'label': 'Tối',
        'icon': Icons.nights_stay_rounded,
        'color': const Color(0xFF9C27B0)
      },
      {
        'value': 'night',
        'label': 'Đêm',
        'icon': Icons.bedtime_rounded,
        'color': const Color(0xFF3F51B5)
      },
    ];

    try {
      await showDialog(
        context: pageContext,
        builder: (context) => StatefulBuilder(
          builder: (context, setState) => AlertDialog(
            backgroundColor: Colors.white,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: _getTypeColor(template.type).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(_getTypeIcon(template.type),
                      color: _getTypeColor(template.type), size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    template.name,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (template.description.isNotEmpty) ...[
                  Text(
                    ExerciseProvider.cleanHtml(template.description),
                    style: const TextStyle(
                        fontSize: 12.5, color: Color(0xFF666666)),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 12),
                ],
                const Text(
                  'Thời gian tập (phút)',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF555555)),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: durationController,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                    hintText: '30',
                    suffixText: 'phút',
                    filled: true,
                    fillColor: Colors.grey[100],
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide.none,
                    ),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
                const SizedBox(height: 14),
                const Text(
                  'Buổi tập',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF555555)),
                ),
                const SizedBox(height: 8),
                Row(
                  children: timeSlots.map((slot) {
                    final isSelected = selectedTimeOfDay == slot['value'];
                    final color = slot['color'] as Color;
                    return Expanded(
                      child: GestureDetector(
                        onTap: () => setState(
                            () => selectedTimeOfDay = slot['value'] as String),
                        child: Container(
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? color.withValues(alpha: 0.15)
                                : Colors.grey[100],
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isSelected ? color : Colors.transparent,
                              width: 1.5,
                            ),
                          ),
                          child: Column(
                            children: [
                              Icon(slot['icon'] as IconData,
                                  size: 18,
                                  color: isSelected
                                      ? color
                                      : const Color(0xFF888888)),
                              const SizedBox(height: 3),
                              Text(
                                slot['label'] as String,
                                style: TextStyle(
                                  fontSize: 10,
                                  color: isSelected
                                      ? color
                                      : const Color(0xFF888888),
                                  fontWeight: isSelected
                                      ? FontWeight.bold
                                      : FontWeight.normal,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                if (user != null) ...[
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFF7043).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.local_fire_department_rounded,
                            color: Color(0xFFFF7043), size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '~${template.calculateCalories(user.weight, ExerciseUtils.parseDuration(durationController.text)).toStringAsFixed(0)} kcal',
                          style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFFFF7043)),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Hủy')),
              OutlinedButton.icon(
                onPressed: () {
                  final duration =
                      ExerciseUtils.parseDuration(durationController.text);
                  final cal = user != null
                      ? template.calculateCalories(user.weight, duration)
                      : template.calculateCalories(70, duration);
                  final action = ActionItem(
                    kind: 'exercise',
                    wgerId: template.wgerId,
                    name: template.name,
                    details: {
                      'duration': duration,
                      'calories_burned': cal,
                      'description': template.description,
                    },
                  );
                  final routine = WorkoutRoutineParser.parseFromAction(action);
                  Navigator.pop(context);
                  Navigator.push(
                    pageContext,
                    MaterialPageRoute(
                      builder: (_) => WorkoutSimulationScreen(
                        routine: routine,
                        onSaveToJournal: user == null
                            ? null
                            : () async {
                                final exercise = ExerciseModel(
                                  id: DateTime.now()
                                      .millisecondsSinceEpoch
                                      .toString(),
                                  userId: user.id,
                                  name: template.name,
                                  exerciseTemplateId: template.id,
                                  date: DateTime.now(),
                                  duration: duration,
                                  caloriesBurned: cal,
                                  type: template.type,
                                  timeOfDay: selectedTimeOfDay,
                                  isCompleted: true,
                                );
                                await Provider.of<ExerciseProvider>(pageContext,
                                        listen: false)
                                    .addExercise(exercise);
                              },
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.play_circle_filled_rounded, size: 16),
                label: const Text('Luyện tập ngay'),
              ),
              ElevatedButton(
                onPressed: () async {
                  final userId = user?.id;
                  final duration =
                      ExerciseUtils.parseDuration(durationController.text);
                  if (userId != null && user != null) {
                    final exercise = ExerciseModel(
                      id: DateTime.now().millisecondsSinceEpoch.toString(),
                      userId: userId,
                      name: template.name,
                      exerciseTemplateId: template.id,
                      date: DateTime.now(),
                      duration: duration,
                      caloriesBurned:
                          template.calculateCalories(user.weight, duration),
                      type: template.type,
                      timeOfDay: selectedTimeOfDay,
                    );
                    await Provider.of<ExerciseProvider>(pageContext,
                            listen: false)
                        .addExercise(exercise);
                    if (!context.mounted) return;
                    Navigator.pop(context);
                  }
                },
                child: const Text('Thêm vào lịch'),
              ),
            ],
          ),
        ),
      );
    } finally {
      durationController.dispose();
    }
  }

  void _showAddExerciseSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const SmartExercisePicker(),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// STATEFUL MODAL FOR EXERCISE DETAILS WITH LIVE MOVEMENT SIMULATION & 3 PHASES
// ═══════════════════════════════════════════════════════════════════════════

class _ExerciseLiveDetailModal extends StatefulWidget {
  final ExerciseModel exercise;
  final WorkoutRoutinePlan routinePlan;
  final Color color;
  final VoidCallback onStartSimulation;

  const _ExerciseLiveDetailModal({
    required this.exercise,
    required this.routinePlan,
    required this.color,
    required this.onStartSimulation,
  });

  @override
  State<_ExerciseLiveDetailModal> createState() =>
      _ExerciseLiveDetailModalState();
}

class _ExerciseLiveDetailModalState extends State<_ExerciseLiveDetailModal>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  WorkoutAnimationType _getAnimationType(String name, String type) {
    return WorkoutRoutineParser.inferAnimationType('$name $type');
  }

  @override
  Widget build(BuildContext context) {
    final ex = widget.exercise;
    final plan = widget.routinePlan;
    final color = widget.color;
    final animType = _getAnimationType(ex.name, ex.type);

    return DraggableScrollableSheet(
      initialChildSize: 0.90,
      minChildSize: 0.5,
      maxChildSize: 0.96,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
          boxShadow: [
            BoxShadow(
                color: Colors.black26, blurRadius: 20, offset: Offset(0, -6)),
          ],
        ),
        child: Column(
          children: [
            // Handle
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 6),
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
              padding: const EdgeInsets.fromLTRB(20, 6, 20, 6),
              child: Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [color, color.withValues(alpha: 0.8)],
                      ),
                      borderRadius: BorderRadius.circular(14),
                      boxShadow: [
                        BoxShadow(
                            color: color.withValues(alpha: 0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 3)),
                      ],
                    ),
                    child: const Icon(Icons.fitness_center_rounded,
                        color: Colors.white, size: 22),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          ex.name,
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
                                '${ex.typeText} · ${ex.intensityText}',
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

            // Tabs Header
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
                  labelStyle: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w700),
                  unselectedLabelStyle: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w500),
                  tabs: const [
                    Tab(text: 'Mô phỏng & 3 Giai đoạn'),
                    Tab(text: 'Kỹ thuật & An toàn'),
                  ],
                ),
              ),
            ),

            const Divider(height: 8),

            // Tab Views
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  // Tab 1: Live Simulation & 3 Phases
                  ListView(
                    controller: controller,
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
                    children: [
                      // LIVE SIMULATION CANVAS PREVIEW
                      ClipRRect(
                        borderRadius: BorderRadius.circular(18),
                        child: Container(
                          height: 220,
                          decoration: BoxDecoration(
                            color: const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(18),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.1),
                                blurRadius: 10,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: WorkoutSimulationWidget(
                            animationType: animType,
                            exerciseName: ex.name,
                            isResting: false,
                          ),
                        ),
                      ),

                      const SizedBox(height: 14),

                      // Quick Stats Grid
                      Row(
                        children: [
                          Expanded(
                              child: _statChip(Icons.timer_outlined,
                                  '${ex.duration} phút', 'Thời gian', color)),
                          const SizedBox(width: 8),
                          Expanded(
                              child: _statChip(
                                  Icons.local_fire_department_rounded,
                                  '~${ex.caloriesBurned.toStringAsFixed(0)} kcal',
                                  'Calo đốt',
                                  const Color(0xFFFF7043))),
                          const SizedBox(width: 8),
                          Expanded(
                              child: _statChip(
                                  Icons.format_list_bulleted_rounded,
                                  '${plan.totalExercisesCount} bài',
                                  'Giai đoạn',
                                  const Color(0xFF9C27B0))),
                        ],
                      ),

                      const SizedBox(height: 18),

                      // 3 PHASES LIST
                      const Text(
                        'Lộ trình 3 giai đoạn chuẩn thể thao',
                        style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1A1A1A)),
                      ),
                      const SizedBox(height: 10),

                      ...plan.phases
                          .map((phase) => _buildPhaseSection(phase, color)),
                    ],
                  ),

                  // Tab 2: Guidance
                  ListView(
                    controller: controller,
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                    children: [
                      _guidanceCard(
                        icon: Icons.lightbulb_outline_rounded,
                        iconColor: Colors.amber,
                        title: 'Kỹ thuật thực hiện an toàn',
                        items: [
                          'Khởi động kỹ 3-5 phút trước khi bước vào động tác chính.',
                          'Giữ thẳng cột sống, siết chặt cơ bụng (brace core) khi phát lực.',
                          'Không khóa cứng khớp khuỷu tay và đầu gối ở điểm cuối hành trình.',
                          'Dừng ngay lập tức nếu xuất hiện cơn đau nhói bất thường.',
                        ],
                      ),
                      const SizedBox(height: 14),
                      _guidanceCard(
                        icon: Icons.air_rounded,
                        iconColor: Colors.teal,
                        title: 'Kỹ thuật Hít thở chuẩn Thể hình',
                        items: [
                          'Hít sâu bằng mũi trong pha hạ tạ hoặc mở rộng cơ thể.',
                          'Thở dứt khoát bằng miệng trong pha phát lực ép/đẩy/kéo.',
                          'Duy trì nhịp thở đều đặn, tuyệt đối không nín thở nén ép tim mạch.',
                        ],
                      ),
                      const SizedBox(height: 14),
                      _guidanceCard(
                        icon: Icons.water_drop_outlined,
                        iconColor: Colors.blue,
                        title: 'Bù nước & Phục hồi sau tập',
                        items: [
                          'Uống 100-150ml nước lọc từng ngụm nhỏ sau mỗi 15-20 phút.',
                          'Giãn cơ tĩnh 3-5 phút để đào thải acid lactic.',
                          'Bổ sung 20-30g Protein trong vòng 45 phút sau buổi tập.',
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Bottom Action Bar
            _buildBottomActionBar(context, ex, color),
          ],
        ),
      ),
    );
  }

  Widget _statChip(IconData icon, String value, String label, Color chipColor) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: chipColor.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          Icon(icon, color: chipColor, size: 18),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w800,
                color: Color(0xFF1A1A1A)),
          ),
          Text(
            label,
            style: const TextStyle(fontSize: 10.5, color: Color(0xFF777777)),
          ),
        ],
      ),
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
      margin: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Phase header
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
                child: Text(
                  phase.title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: phaseColor,
                  ),
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
          const SizedBox(height: 8),

          // Exercise steps
          ...phase.exercises.map((step) => Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.grey[200]!),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 26,
                          height: 26,
                          decoration: BoxDecoration(
                            color: phaseColor.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Center(
                            child: Icon(Icons.fitness_center,
                                color: phaseColor, size: 14),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            step.name,
                            style: const TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1A1A1A),
                            ),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: phaseColor.withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            '${step.sets} hiệp × ${step.reps}',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: phaseColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (step.instructions.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(
                        step.instructions,
                        style: const TextStyle(
                            fontSize: 12,
                            height: 1.45,
                            color: Color(0xFF555555)),
                      ),
                    ],
                    if (step.breathingCue.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          const Icon(Icons.air, size: 14, color: Colors.teal),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              step.breathingCue,
                              style: const TextStyle(
                                  fontSize: 11.5,
                                  color: Colors.teal,
                                  fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              )),
        ],
      ),
    );
  }

  Widget _guidanceCard({
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
                    color: Color(0xFF1A1A1A)),
              ),
            ],
          ),
          const SizedBox(height: 10),
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
                            fontSize: 12.5,
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

  Widget _buildBottomActionBar(
      BuildContext context, ExerciseModel ex, Color color) {
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
      child: Row(
        children: [
          // Nút Bắt đầu Luyện tập & Mô phỏng (Primary Gradient)
          Expanded(
            flex: 3,
            child: ElevatedButton.icon(
              onPressed: widget.onStartSimulation,
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
          // Nút Toggle Hoàn thành
          Expanded(
            flex: 2,
            child: OutlinedButton.icon(
              onPressed: () {
                Provider.of<ExerciseProvider>(context, listen: false)
                    .toggleExerciseCompleted(ex.id);
                Navigator.pop(context);
              },
              icon: Icon(
                ex.isCompleted
                    ? Icons.undo_rounded
                    : Icons.check_circle_outline_rounded,
                size: 18,
                color: ex.isCompleted ? Colors.grey : AppColors.success,
              ),
              label: Text(
                ex.isCompleted ? 'Bỏ hoàn thành' : 'Đã tập xong',
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: ex.isCompleted ? Colors.grey : AppColors.success,
                ),
              ),
              style: OutlinedButton.styleFrom(
                side: BorderSide(
                  color: ex.isCompleted ? Colors.grey[400]! : AppColors.success,
                  width: 1.5,
                ),
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
