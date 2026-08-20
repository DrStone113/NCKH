import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../models/wger_models.dart';
import '../../../models/exercise_model.dart';
import '../../../models/workout_routine_model.dart';
import '../../../theme/app_theme.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../widgets/wger_image.dart';
import '../../../widgets/workout_simulation_painter.dart';
import '../../../utils/exercise_utils.dart';
import 'workout_simulation_screen.dart';

/// Màn hình chi tiết bài tập từ wger kết hợp Mô phỏng Động tác & Trình phát luyện tập
class ExerciseDetailScreen extends StatefulWidget {
  final WgerExercise exercise;

  const ExerciseDetailScreen({
    super.key,
    required this.exercise,
  });

  @override
  State<ExerciseDetailScreen> createState() => _ExerciseDetailScreenState();
}

class _ExerciseDetailScreenState extends State<ExerciseDetailScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final _durationController = TextEditingController(text: '30');

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _durationController.dispose();
    super.dispose();
  }

  WorkoutAnimationType _getAnimationType() {
    return WorkoutRoutineParser.inferAnimationType(widget.exercise.name);
  }

  void _startWorkoutSimulation(BuildContext context) {
    final duration = ExerciseUtils.parseDuration(_durationController.text);
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    final estimatedCalories = ExerciseProvider.estimateCaloriesForExercise(
      name: widget.exercise.name,
      categoryName: widget.exercise.categoryName,
      muscleCount: widget.exercise.muscleCount,
      weightKg: user?.weight ?? 70,
      durationMinutes: duration,
    );
    final action = ActionItem(
      kind: 'exercise',
      wgerId: widget.exercise.id,
      name: widget.exercise.name,
      details: {
        'duration': duration,
        'calories_burned': estimatedCalories,
        'description': widget.exercise.description,
      },
    );

    final routine = WorkoutRoutineParser.parseFromAction(action);

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WorkoutSimulationScreen(
          routine: routine,
          onSaveToJournal: user == null
              ? null
              : () async {
                  final calories = _estimateCalories(duration, user.weight);
                  final exercise = ExerciseModel(
                    id: DateTime.now().millisecondsSinceEpoch.toString(),
                    userId: user.id,
                    name: widget.exercise.name,
                    exerciseTemplateId: 'wger_${widget.exercise.id}',
                    date: DateTime.now(),
                    duration: duration,
                    caloriesBurned: calories,
                    type: ExerciseProvider.mapCategoryToType(
                        widget.exercise.name, widget.exercise.categoryName),
                    intensity: 'medium',
                    isCompleted: true,
                  );
                  await Provider.of<ExerciseProvider>(context, listen: false)
                      .addExercise(exercise);
                },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;
    final animType = _getAnimationType();

    return Scaffold(
      backgroundColor: Colors.white,
      body: CustomScrollView(
        slivers: [
          // App bar với ảnh & overlay
          SliverAppBar(
            expandedHeight: 220,
            pinned: true,
            flexibleSpace: FlexibleSpaceBar(
              title: Text(
                widget.exercise.name,
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 16,
                  shadows: [
                    Shadow(color: Colors.black87, blurRadius: 8),
                  ],
                ),
              ),
              background: Stack(
                fit: StackFit.expand,
                children: [
                  if (widget.exercise.imageUrl != null)
                    WgerImage(
                      widget.exercise.imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) =>
                          _buildPlaceholderImage(),
                    )
                  else
                    _buildPlaceholderImage(),
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.75),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Nội dung chính
          SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Live Movement Simulation Box
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(18),
                    child: Container(
                      height: 200,
                      decoration: const BoxDecoration(
                        color: Color(0xFF0F172A),
                      ),
                      child: WorkoutSimulationWidget(
                        animationType: animType,
                        exerciseName: widget.exercise.name,
                        isResting: false,
                      ),
                    ),
                  ),
                ),

                // Category & Equipment badges
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                              color: AppColors.primary.withValues(alpha: 0.3)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.category_rounded,
                                size: 14, color: AppColors.primary),
                            const SizedBox(width: 6),
                            Text(
                              widget.exercise.categoryName,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: AppColors.primary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (widget.exercise.equipment.isNotEmpty)
                        ...widget.exercise.equipment.map((eq) => Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 5),
                              decoration: BoxDecoration(
                                color: Colors.blueGrey.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(
                                    color:
                                        Colors.blueGrey.withValues(alpha: 0.3)),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.fitness_center_rounded,
                                      size: 13, color: Colors.blueGrey),
                                  const SizedBox(width: 4),
                                  Text(
                                    eq.name,
                                    style: const TextStyle(
                                      fontSize: 11.5,
                                      fontWeight: FontWeight.w600,
                                      color: Colors.blueGrey,
                                    ),
                                  ),
                                ],
                              ),
                            )),
                    ],
                  ),
                ),

                const SizedBox(height: 16),

                // Tabs
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.grey[100],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: TabBar(
                      controller: _tabController,
                      indicator: BoxDecoration(
                        color: AppColors.primary,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      indicatorSize: TabBarIndicatorSize.tab,
                      labelColor: Colors.white,
                      unselectedLabelColor: const Color(0xFF666666),
                      labelStyle: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w700),
                      unselectedLabelStyle: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w500),
                      tabs: const [
                        Tab(text: 'Hướng dẫn kỹ thuật'),
                        Tab(text: 'Nhóm cơ tác động'),
                        Tab(text: 'Cài đặt thời gian'),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 14),

                // Tab content
                SizedBox(
                  height: 340,
                  child: TabBarView(
                    controller: _tabController,
                    children: [
                      _buildInstructionsTab(),
                      _buildMusclesTab(),
                      _buildAddToDiaryTab(user),
                    ],
                  ),
                ),
                const SizedBox(height: 100),
              ],
            ),
          ),
        ],
      ),
      bottomSheet: Container(
        padding: EdgeInsets.fromLTRB(
            16, 10, 16, MediaQuery.of(context).padding.bottom + 10),
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.08),
              blurRadius: 10,
              offset: const Offset(0, -4),
            ),
          ],
        ),
        child: Row(
          children: [
            // Nút Bắt đầu Luyện tập & Mô phỏng
            Expanded(
              flex: 3,
              child: ElevatedButton.icon(
                onPressed: () => _startWorkoutSimulation(context),
                icon: const Icon(Icons.play_circle_filled_rounded,
                    size: 22, color: Colors.white),
                label: const Text(
                  'Bắt đầu luyện tập',
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w800,
                      color: Colors.white),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                  elevation: 2,
                ),
              ),
            ),
            const SizedBox(width: 10),
            // Nút Thêm vào nhật ký
            Expanded(
              flex: 2,
              child: OutlinedButton.icon(
                onPressed:
                    user != null ? () => _addExerciseToDiary(user) : null,
                icon: const Icon(Icons.add_rounded, size: 20),
                label: const Text(
                  'Thêm vào lịch',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primary,
                  side: const BorderSide(color: AppColors.primary, width: 1.5),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlaceholderImage() {
    return Container(
      color: const Color(0xFF1E293B),
      child: const Center(
        child: Icon(
          Icons.fitness_center_rounded,
          size: 70,
          color: Colors.white30,
        ),
      ),
    );
  }

  Widget _buildInstructionsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '📋 Hướng dẫn thực hiện chuẩn',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          if (widget.exercise.description.isNotEmpty)
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.grey[50],
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.grey[200]!),
              ),
              child: Text(
                _stripHtml(widget.exercise.description),
                style: const TextStyle(
                    fontSize: 13.5, color: Color(0xFF333333), height: 1.55),
              ),
            )
          else
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.grey[50],
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.grey[200]!),
              ),
              child: const Text(
                'Thực hiện động tác theo đúng kỹ thuật, kiểm soát nhịp thở và giữ thăng bằng thân người.',
                style: TextStyle(fontSize: 13, color: Color(0xFF666666)),
              ),
            ),
          const SizedBox(height: 14),
          _buildTipsSection(),
        ],
      ),
    );
  }

  Widget _buildTipsSection() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.amber.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.amber.withValues(alpha: 0.25)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.lightbulb_outline_rounded,
                  size: 18, color: Colors.amber),
              SizedBox(width: 8),
              Text(
                'Lưu ý an toàn & Hiệu quả',
                style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1A1A1A)),
              ),
            ],
          ),
          SizedBox(height: 8),
          Text(
            '• Khởi động kỹ khớp trước khi tập.\n• Thở ra khi phát lực, hít sâu khi hạ tạ.\n• Dừng lại ngay nếu xuất hiện cơn đau khớp bất thường.',
            style: TextStyle(
                fontSize: 12.5, height: 1.5, color: Color(0xFF555555)),
          ),
        ],
      ),
    );
  }

  Widget _buildMusclesTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.exercise.muscles.isNotEmpty) ...[
            const Text('🎯 Nhóm cơ chính tác động',
                style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: widget.exercise.muscles.map((m) {
                return Chip(
                  avatar: const Icon(Icons.check_circle_rounded,
                      size: 16, color: Colors.white),
                  label: Text(m.nameEn,
                      style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          fontSize: 12)),
                  backgroundColor: AppColors.primary,
                );
              }).toList(),
            ),
            const SizedBox(height: 14),
          ],
          if (widget.exercise.musclesSecondary.isNotEmpty) ...[
            const Text('⚡ Nhóm cơ phụ hỗ trợ',
                style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: widget.exercise.musclesSecondary.map((m) {
                return Chip(
                  label: Text(m.nameEn,
                      style: const TextStyle(
                          color: Colors.blueGrey,
                          fontWeight: FontWeight.w600,
                          fontSize: 12)),
                  backgroundColor: Colors.blueGrey.withValues(alpha: 0.12),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAddToDiaryTab(user) {
    final duration = ExerciseUtils.parseDuration(_durationController.text);
    final estimatedCalories =
        user != null ? _estimateCalories(duration, user.weight) : 0.0;

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('⏱️ Thời gian tập luyện',
              style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          TextField(
            controller: _durationController,
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
          // Estimated calories
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFFFF6D00), Color(0xFFE65100)],
              ),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                const Icon(Icons.local_fire_department_rounded,
                    color: Colors.white, size: 28),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Ước tính calo tiêu hao',
                        style:
                            TextStyle(fontSize: 11.5, color: Colors.white70)),
                    Text(
                      '~${estimatedCalories.toStringAsFixed(0)} kcal',
                      style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w900,
                          color: Colors.white),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _stripHtml(String html) {
    return ExerciseUtils.cleanHtml(html);
  }

  double _estimateCalories(int durationMinutes, double weightKg) {
    return ExerciseProvider.estimateCaloriesForExercise(
      name: widget.exercise.name,
      categoryName: widget.exercise.categoryName,
      muscleCount: widget.exercise.muscleCount,
      weightKg: weightKg,
      durationMinutes: durationMinutes,
    );
  }

  Future<void> _addExerciseToDiary(user) async {
    final duration = ExerciseUtils.parseDuration(_durationController.text);
    final calories = _estimateCalories(duration, user.weight);

    final exercise = ExerciseModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: user.id,
      name: widget.exercise.name,
      exerciseTemplateId: 'wger_${widget.exercise.id}',
      date: DateTime.now(),
      duration: duration,
      caloriesBurned: calories,
      type: ExerciseProvider.mapCategoryToType(
          widget.exercise.name, widget.exercise.categoryName),
      intensity: 'medium',
    );

    try {
      await Provider.of<ExerciseProvider>(context, listen: false)
          .addExercise(exercise);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Không thể lưu bài tập. Vui lòng thử lại.'),
        backgroundColor: AppColors.error,
      ));
      return;
    }

    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã thêm "${widget.exercise.name}" vào lịch hôm nay'),
        backgroundColor: AppColors.success,
      ),
    );

    Navigator.pop(context);
  }
}
