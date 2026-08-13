import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../models/exercise_model.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/animated_counter.dart';
import '../../../widgets/smart_exercise_picker.dart';
import 'exercise_browser_screen.dart';
import 'exercise_history_screen.dart';
import '../../chat/screens/chatbot_screen.dart';
import '../../../services/local_exercise_service.dart';

class ExerciseScreen extends StatefulWidget {
  const ExerciseScreen({super.key});

  @override
  State<ExerciseScreen> createState() => _ExerciseScreenState();
}

class _ExerciseScreenState extends State<ExerciseScreen> {
  final _categories = [
    {'icon': Icons.directions_run, 'label': 'Cardio', 'type': 'cardio', 'color': AppColors.cardio, 'desc': 'Tăng sức bền tim mạch'},
    {'icon': Icons.fitness_center, 'label': 'Sức mạnh', 'type': 'strength', 'color': AppColors.strength, 'desc': 'Xây dựng cơ bắp'},
    {'icon': Icons.self_improvement, 'label': 'Linh hoạt', 'type': 'flexibility', 'color': AppColors.flexibility, 'desc': 'Tăng độ dẻo dai'},
    {'icon': Icons.sports_soccer, 'label': 'Thể thao', 'type': 'sports', 'color': AppColors.sports, 'desc': 'Vui vẻ và năng động'},
  ];

  @override
  Widget build(BuildContext context) {
    final exerciseProvider = Provider.of<ExerciseProvider>(context);
    final user = Provider.of<UserProvider>(context).currentUser;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Vận động'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.history),
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
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showAddExerciseSheet(context),
        icon: const Icon(Icons.add),
        label: const Text('Thêm'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AnimatedCard(delay: 0, child: _buildStatsRow(exerciseProvider)),
            const SizedBox(height: 24),
            AnimatedCard(delay: 50, child: _buildAIBanner(context)),
            const SizedBox(height: 24),
            const AnimatedCard(
              delay: 100,
              child: Text('Danh mục bài tập', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(height: 12),
            AnimatedCard(delay: 150, child: _buildCategoryGrid(context, exerciseProvider, user)),
            const SizedBox(height: 24),
            AnimatedCard(
              delay: 200,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Hoạt động hôm nay', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  Row(
                    children: [
                      if (exerciseProvider.todayExercises.isNotEmpty) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: AppColors.success.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.check_circle, size: 14, color: AppColors.success),
                              const SizedBox(width: 4),
                              Text(
                                '${exerciseProvider.completedCount}',
                                style: const TextStyle(fontSize: 12, color: AppColors.success, fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 6),
                      ],
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '${exerciseProvider.todayExercises.length} hoạt động',
                          style: const TextStyle(fontSize: 12, color: AppColors.primary, fontWeight: FontWeight.w600),
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
              ..._buildGroupedExercises(context, exerciseProvider.todayExercises),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildGroupedExercises(BuildContext context, List<ExerciseModel> exercises) {
    final order = ['morning', 'afternoon', 'evening', 'night'];
    final labels = {
      'morning':   ('Buổi sáng',  Icons.wb_sunny_outlined,    const Color(0xFFFF9800)),
      'afternoon': ('Buổi chiều', Icons.wb_cloudy_outlined,   const Color(0xFF2196F3)),
      'evening':   ('Buổi tối',   Icons.nights_stay_outlined, const Color(0xFF9C27B0)),
      'night':     ('Ban đêm',    Icons.bedtime_outlined,     const Color(0xFF3F51B5)),
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
          padding: const EdgeInsets.only(top: 8, bottom: 6),
          child: Row(children: [
            Icon(meta.$2, size: 16, color: meta.$3),
            const SizedBox(width: 6),
            Text(meta.$1, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: meta.$3)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(color: meta.$3.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
              child: Text('${group.length} bài', style: TextStyle(fontSize: 10, color: meta.$3, fontWeight: FontWeight.w600)),
            ),
          ]),
        ),
      ));
      delay += 30;
      for (final ex in group) {
        widgets.add(AnimatedCard(delay: delay, child: _buildExerciseLogCard(context, ex)));
        delay += 40;
      }
    }
    return widgets;
  }

  Widget _buildStatsRow(ExerciseProvider provider) {
    return Row(
      children: [
        Expanded(child: _statCard(
          icon: Icons.timer_outlined,
          value: provider.totalDuration.toDouble(),
          unit: 'phút',
          label: 'Thời gian',
          gradient: AppColors.exerciseGradient,
          textColor: Colors.black87,
        )),
        const SizedBox(width: 12),
        Expanded(child: _statCard(
          icon: Icons.local_fire_department,
          value: provider.totalCaloriesBurned,
          unit: 'kcal',
          label: 'Calo đốt',
          gradient: AppColors.calorieGradient,
          textColor: Colors.white,
        )),
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
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(gradient: gradient, borderRadius: BorderRadius.circular(20)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: textColor.withValues(alpha: 0.8), size: 22),
          const SizedBox(height: 10),
          Text(label, style: TextStyle(fontSize: 12, color: textColor.withValues(alpha: 0.7))),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              AnimatedCounter(value: value, decimals: 0, style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: textColor)),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(unit, style: TextStyle(fontSize: 13, color: textColor.withValues(alpha: 0.7))),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAIBanner(BuildContext context) {
    return GestureDetector(
      onTap: () => _openAIChat(context),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF1a1a2e), Color(0xFF16213e)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.smart_toy, color: Colors.white, size: 26),
            ),
            const SizedBox(width: 14),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('AI Gợi ý bài tập', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.white)),
                  SizedBox(height: 4),
                  Text('Nhận kế hoạch tập luyện cá nhân hóa', style: TextStyle(fontSize: 12, color: Colors.white70)),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Text('Hỏi AI', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryGrid(BuildContext context, ExerciseProvider provider, user) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        // Trên màn hình rộng: nhiều cột hơn để card không bị quá to
        final crossAxisCount = width > 600 ? 4 : 2;
        // Giới hạn chiều cao card tối đa ~100px bất kể screen size
        final itemWidth = (width - 12 * (crossAxisCount - 1)) / crossAxisCount;
        const itemHeight = 100.0;
        final aspectRatio = itemWidth / itemHeight;

        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: crossAxisCount,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: aspectRatio,
          ),
          itemCount: _categories.length,
          itemBuilder: (context, index) {
            final cat = _categories[index];
            final color = cat['color'] as Color;
            final type = cat['type'] as String;
            final count = provider.getExercisesByType(type).length;
            return GestureDetector(
              onTap: () => _showCategorySheet(context, type, cat['label'] as String, color, provider, user),
              child: Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: color.withValues(alpha: 0.2)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(10)),
                          child: Icon(cat['icon'] as IconData, color: color, size: 20),
                        ),
                        Text('$count bài', style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
                      ],
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(cat['label'] as String, style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color)),
                        Text(cat['desc'] as String, style: TextStyle(fontSize: 10, color: color.withValues(alpha: 0.7))),
                      ],
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildEmptyExercise(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.surfaceLight),
      ),
      child: Column(
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: AppColors.success.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.fitness_center, size: 36, color: AppColors.success),
          ),
          const SizedBox(height: 16),
          const Text('Chưa có hoạt động nào', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text('Bắt đầu tập luyện để theo dõi tiến trình', style: TextStyle(fontSize: 13, color: AppColors.textSecondary), textAlign: TextAlign.center),
          const SizedBox(height: 20),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: () => _openAIChat(context),
                icon: const Icon(Icons.smart_toy_outlined, size: 16),
                label: const Text('Hỏi AI'),
              ),
              ElevatedButton.icon(
                onPressed: () => _showAddExerciseSheet(context),
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Thêm ngay'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildExerciseLogCard(BuildContext context, ExerciseModel exercise) {
    final color = _getTypeColor(exercise.type);
    return Dismissible(
      key: Key(exercise.id),
      direction: DismissDirection.endToStart,
      background: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(color: AppColors.error, borderRadius: BorderRadius.circular(16)),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline, color: Colors.white),
            SizedBox(width: 8),
            Text('Xoá', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
      confirmDismiss: (_) async => await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Xác nhận xoá'),
          content: Text('Xoá "${exercise.name}"?'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Huỷ')),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
              child: const Text('Xoá'),
            ),
          ],
        ),
      ),
      onDismissed: (_) {
        Provider.of<ExerciseProvider>(context, listen: false).deleteExercise(exercise.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Đã xoá "${exercise.name}"')),
        );
      },
      child: GestureDetector(
        onTap: () => _showExerciseDetail(context, exercise),
        child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.surfaceLight),
          boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 8, offset: const Offset(0, 2))],
        ),
        child: Row(
          children: [
            // CHECKBOX
            Transform.scale(
              scale: 1.2,
              child: Checkbox(
                value: exercise.isCompleted,
                onChanged: (value) {
                  Provider.of<ExerciseProvider>(context, listen: false)
                      .toggleExerciseCompleted(exercise.id);
                },
                activeColor: AppColors.success,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
              child: Icon(_getExerciseIcon(exercise.name, exercise.type), color: color, size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 15,
                      decoration: exercise.isCompleted ? TextDecoration.lineThrough : null,
                      color: exercise.isCompleted ? AppColors.textSecondary : AppColors.textPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      _infoChip(Icons.timer_outlined, '${exercise.duration} phút', AppColors.textSecondary),
                      const SizedBox(width: 8),
                      _infoChip(Icons.speed, exercise.intensityText, color),
                    ],
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(exercise.caloriesBurned.toStringAsFixed(0), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppColors.calories)),
                const Text('kcal', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
              ],
            ),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, size: 18, color: AppColors.textHint),
          ],
        ),
      ),
      ),
    );
  }

  void _showExerciseDetail(BuildContext context, ExerciseModel exercise) {
    final color = _getTypeColor(exercise.type);
    // Tìm bài tập trong wger data để lấy hướng dẫn
    final local = LocalExerciseService();

    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.75,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (_, sc) => SingleChildScrollView(
          controller: sc,
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Handle
              Center(
                child: Container(
                  width: 40, height: 4,
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2)),
                ),
              ),
              // Header
              Row(
                children: [
                  Container(
                    width: 60, height: 60,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(colors: [color, color.withValues(alpha: 0.7)]),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Icon(_getExerciseIcon(exercise.name, exercise.type), color: Colors.white, size: 30),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(exercise.name, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                        const SizedBox(height: 4),
                        Text(exercise.typeText, style: TextStyle(fontSize: 13, color: color, fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                  IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const SizedBox(height: 20),

              // Stats row
              Row(
                children: [
                  Expanded(child: _detailStat(Icons.timer_outlined, '${exercise.duration}', 'phút', color)),
                  const SizedBox(width: 12),
                  Expanded(child: _detailStat(Icons.local_fire_department, exercise.caloriesBurned.toStringAsFixed(0), 'kcal', AppColors.calories)),
                  const SizedBox(width: 12),
                  Expanded(child: _detailStat(Icons.speed, exercise.intensityText, 'cường độ', color)),
                ],
              ),
              const SizedBox(height: 20),

              // Hướng dẫn tập — tìm từ wger local data
              _buildInstructions(exercise, local, color),

              const SizedBox(height: 20),

              // Tips chung
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: color.withValues(alpha: 0.2)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(Icons.lightbulb_outline, size: 16, color: color),
                      const SizedBox(width: 6),
                      Text('Lưu ý khi tập', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: color)),
                    ]),
                    const SizedBox(height: 10),
                    ...[
                      'Khởi động kỹ 5-10 phút trước khi tập',
                      'Thực hiện đúng kỹ thuật, không gắng sức quá mức',
                      'Thở đều — thở ra khi gắng sức, hít vào khi thả lỏng',
                      'Dừng ngay nếu cảm thấy đau hoặc chóng mặt',
                      'Giãn cơ 5 phút sau khi tập xong',
                    ].map((tip) => Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('• ', style: TextStyle(color: color, fontWeight: FontWeight.bold)),
                          Expanded(child: Text(tip, style: const TextStyle(fontSize: 13, height: 1.4))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // Nút đánh dấu hoàn thành
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton.icon(
                  onPressed: () {
                    Provider.of<ExerciseProvider>(context, listen: false)
                        .toggleExerciseCompleted(exercise.id);
                    Navigator.pop(ctx);
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: exercise.isCompleted ? AppColors.textSecondary : AppColors.success,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: Icon(exercise.isCompleted ? Icons.undo : Icons.check_circle_outline),
                  label: Text(
                    exercise.isCompleted ? 'Bỏ đánh dấu hoàn thành' : 'Đánh dấu hoàn thành',
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInstructions(ExerciseModel exercise, LocalExerciseService local, Color color) {
    // Tìm bài tập trong wger data theo tên
    final wgerExercise = local.isLoaded
        ? local.allExercises.where((e) =>
            e.name.toLowerCase() == exercise.name.toLowerCase()).firstOrNull
        : null;

    final description = wgerExercise?.description ?? '';
    final cleanDesc = description
        .replaceAll(RegExp(r'<[^>]*>'), '')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();

    // Hướng dẫn mặc định theo loại bài tập
    final defaultInstructions = _getDefaultInstructions(exercise.type, exercise.name);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.menu_book_outlined, size: 16, color: AppColors.textSecondary),
            SizedBox(width: 6),
            Text('Cách thực hiện', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppColors.textSecondary)),
          ]),
          const SizedBox(height: 10),
          if (cleanDesc.isNotEmpty)
            Text(cleanDesc, style: const TextStyle(fontSize: 13, height: 1.6, color: AppColors.textPrimary))
          else
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: defaultInstructions.asMap().entries.map((e) =>
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 22, height: 22,
                        margin: const EdgeInsets.only(right: 10, top: 1),
                        decoration: BoxDecoration(color: color.withValues(alpha: 0.15), shape: BoxShape.circle),
                        child: Center(child: Text('${e.key + 1}', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color))),
                      ),
                      Expanded(child: Text(e.value, style: const TextStyle(fontSize: 13, height: 1.5))),
                    ],
                  ),
                ),
              ).toList(),
            ),
          // Nhóm cơ từ wger
          if (wgerExercise != null && wgerExercise.muscles.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Divider(height: 1),
            const SizedBox(height: 10),
            Wrap(
              spacing: 6, runSpacing: 6,
              children: [
                const Text('Nhóm cơ: ', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                ...wgerExercise.muscles.map((m) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: color.withValues(alpha: 0.25)),
                  ),
                  child: Text(m.nameEn, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
                )),
              ],
            ),
          ],
        ],
      ),
    );
  }

  List<String> _getDefaultInstructions(String type, String name) {
    final nameLower = name.toLowerCase();
    // Hướng dẫn cụ thể theo tên bài
    if (nameLower.contains('squat')) {
      return ['Đứng thẳng, hai chân rộng bằng vai', 'Hạ người xuống như ngồi ghế, giữ lưng thẳng', 'Đùi song song với sàn, gối không vượt quá mũi chân', 'Đẩy người lên về vị trí ban đầu'];
    }
    if (nameLower.contains('push') || nameLower.contains('hít đất')) {
      return ['Nằm sấp, hai tay rộng hơn vai', 'Giữ thân người thẳng từ đầu đến gót chân', 'Hạ ngực xuống gần sàn', 'Đẩy người lên về vị trí ban đầu'];
    }
    if (nameLower.contains('plank')) {
      return ['Nằm sấp, chống tay hoặc khuỷu tay', 'Giữ thân người thẳng như tấm ván', 'Siết cơ bụng và mông', 'Giữ tư thế trong thời gian quy định'];
    }
    if (nameLower.contains('lunge')) {
      return ['Đứng thẳng, bước một chân về phía trước', 'Hạ người xuống đến khi đùi sau gần chạm sàn', 'Giữ lưng thẳng, gối trước không vượt mũi chân', 'Đẩy người lên và đổi chân'];
    }
    if (nameLower.contains('deadlift')) {
      return ['Đứng trước tạ, chân rộng bằng hông', 'Cúi người giữ lưng thẳng, nắm tạ', 'Đẩy hông về phía trước để đứng thẳng', 'Hạ tạ xuống kiểm soát'];
    }
    if (nameLower.contains('curl') || nameLower.contains('bicep')) {
      return ['Đứng thẳng, cầm tạ hai tay', 'Giữ khuỷu tay sát thân, cuộn tạ lên', 'Siết cơ bắp tay ở đỉnh', 'Hạ tạ xuống chậm rãi'];
    }
    if (nameLower.contains('chạy') || nameLower.contains('run')) {
      return ['Khởi động đi bộ 3-5 phút', 'Chạy với tốc độ vừa phải, thở đều', 'Giữ tư thế thẳng, nhìn về phía trước', 'Hạ tốc độ dần khi kết thúc'];
    }
    // Hướng dẫn theo loại
    switch (type) {
      case 'cardio':
        return ['Khởi động nhẹ 5 phút', 'Duy trì nhịp tim ở mức 60-80% tối đa', 'Thở đều và nhịp nhàng', 'Giảm cường độ dần khi kết thúc'];
      case 'strength':
        return ['Chọn mức tạ phù hợp với trình độ', 'Thực hiện động tác chậm và kiểm soát', 'Nghỉ 60-90 giây giữa các set', 'Tập trung vào nhóm cơ đang tập'];
      case 'flexibility':
        return ['Giữ mỗi tư thế 20-30 giây', 'Không ép quá mức, cảm nhận sự căng nhẹ', 'Thở sâu và đều trong khi giữ tư thế', 'Thực hiện cả hai bên cơ thể'];
      default:
        return ['Khởi động kỹ trước khi bắt đầu', 'Thực hiện đúng kỹ thuật', 'Nghỉ ngơi đầy đủ giữa các hiệp', 'Giãn cơ sau khi tập'];
    }
  }

  Widget _detailStat(IconData icon, String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppColors.cardDark, borderRadius: BorderRadius.circular(12)),
      child: Column(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
          Text(label, style: const TextStyle(fontSize: 10, color: AppColors.textSecondary)),
        ],
      ),
    );
  }

  Widget _infoChip(IconData icon, String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: color),
        const SizedBox(width: 3),
        Text(label, style: TextStyle(fontSize: 11, color: color)),
      ],
    );
  }

  /// Trả về buổi tập mặc định dựa theo giờ hiện tại
  String _defaultTimeOfDay() {
    final hour = DateTime.now().hour;
    if (hour >= 5 && hour < 12) return 'morning';
    if (hour >= 12 && hour < 17) return 'afternoon';
    if (hour >= 17 && hour < 21) return 'evening';
    return 'night';
  }

  Color _getTypeColor(String type) {
    switch (type) {
      case 'cardio': return AppColors.cardio;
      case 'strength': return AppColors.strength;
      case 'flexibility': return AppColors.flexibility;
      case 'sports': return AppColors.sports;
      default: return AppColors.success;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type) {
      case 'cardio': return Icons.directions_run;
      case 'strength': return Icons.fitness_center;
      case 'flexibility': return Icons.self_improvement;
      case 'sports': return Icons.sports_soccer;
      default: return Icons.directions_walk;
    }
  }

  /// Chọn icon dựa trên tên bài tập (chi tiết hơn _getTypeIcon)
  IconData _getExerciseIcon(String name, String type) {
    final n = name.toLowerCase();

    // ── Kéo / xà / pull ──────────────────────────────────────────────
    if (n.contains('pull') || n.contains('chin') || n.contains('xà')) {
      return Icons.airline_seat_flat;
    }
    // ── Đẩy / push / press / hít đất ─────────────────────────────────
    if (n.contains('push') || n.contains('press') || n.contains('hít đất') || n.contains('bench')) {
      return Icons.arrow_upward;
    }
    // ── Squat / lunge / chân ──────────────────────────────────────────
    if (n.contains('squat') || n.contains('lunge') || n.contains('leg') || n.contains('chân') || n.contains('knee')) {
      return Icons.accessibility_new;
    }
    // ── Deadlift / hip hinge ──────────────────────────────────────────
    if (n.contains('deadlift') || n.contains('hip') || n.contains('romanian') || n.contains('hinge')) {
      return Icons.vertical_align_bottom;
    }
    // ── Curl / bicep ──────────────────────────────────────────────────
    if (n.contains('curl') || n.contains('bicep')) {
      return Icons.sports_handball;
    }
    // ── Tricep / extension / dip ──────────────────────────────────────
    if (n.contains('tricep') || n.contains('dip')) {
      return Icons.back_hand;
    }
    // ── Wrist / forearm / grip / finger / hang ────────────────────────
    if (n.contains('wrist') || n.contains('forearm') || n.contains('grip') ||
        n.contains('finger') || n.contains('hang') || n.contains('pinch')) {
      return Icons.back_hand;
    }
    // ── Row / lưng / lat ──────────────────────────────────────────────
    if (n.contains('row') || n.contains('lat ') || n.contains('back') || n.contains('lưng')) {
      return Icons.swap_vert;
    }
    // ── Shoulder / vai / raise / lateral ─────────────────────────────
    if (n.contains('shoulder') || n.contains('lateral') || n.contains('raise') || n.contains('vai')) {
      return Icons.expand;
    }
    // ── Plank / core / bụng / ab / crunch / slide ────────────────────
    if (n.contains('plank') || n.contains('crunch') || n.contains('ab') ||
        n.contains('core') || n.contains('bụng') || n.contains('slide') ||
        n.contains('hollow') || n.contains('l-sit')) {
      return Icons.crop_square;
    }
    // ── Climb / leo / pillar / hercules ──────────────────────────────
    if (n.contains('climb') || n.contains('pillar') || n.contains('hercules') ||
        n.contains('rope') || n.contains('leo')) {
      return Icons.terrain;
    }
    // ── Chạy / run / jog / sprint ────────────────────────────────────
    if (n.contains('run') || n.contains('chạy') || n.contains('jog') || n.contains('sprint')) {
      return Icons.directions_run;
    }
    // ── Đạp xe ───────────────────────────────────────────────────────
    if (n.contains('bike') || n.contains('cycle') || n.contains('cycling')) {
      return Icons.directions_bike;
    }
    // ── Bơi ──────────────────────────────────────────────────────────
    if (n.contains('swim') || n.contains('bơi')) {
      return Icons.pool;
    }
    // ── Nhảy / jump / box ────────────────────────────────────────────
    if (n.contains('jump') || n.contains('box jump') || n.contains('nhảy')) {
      return Icons.keyboard_double_arrow_up;
    }
    // ── Yoga / stretch / giãn ────────────────────────────────────────
    if (n.contains('yoga') || n.contains('stretch') || n.contains('flex') || n.contains('giãn')) {
      return Icons.self_improvement;
    }
    // ── Commando / burpee / military ─────────────────────────────────
    if (n.contains('commando') || n.contains('burpee') || n.contains('military')) {
      return Icons.sports_martial_arts;
    }
    // ── Tạ / dumbbell / barbell / db ─────────────────────────────────
    if (n.contains('dumbbell') || n.contains('barbell') || n.startsWith('db ') || n.contains(' db ')) {
      return Icons.fitness_center;
    }
    // ── Extension (chung — sau khi đã lọc tricep/wrist ở trên) ───────
    if (n.contains('extension')) {
      return Icons.fitness_center;
    }

    // ── Fallback theo type ────────────────────────────────────────────
    switch (type) {
      case 'cardio':      return Icons.monitor_heart_outlined;
      case 'strength':    return Icons.fitness_center;
      case 'flexibility': return Icons.self_improvement;
      case 'sports':      return Icons.sports;
      default:            return Icons.directions_walk;
    }
  }

  void _openAIChat(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => const ChatbotScreen(showBackButton: true),
      ),
    );
  }

  void _showCategorySheet(BuildContext context, String type, String label, Color color, ExerciseProvider provider, user) {
    final exercises = provider.getExercisesByType(type);
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.75,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scrollController) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              child: Column(
                children: [
                  Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                        child: Icon(_getTypeIcon(type), color: color, size: 22),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(label, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                          Text('${exercises.length} bài tập', style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                controller: scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                itemCount: exercises.length,
                itemBuilder: (context, index) {
                  final template = exercises[index];
                  final cal30 = user != null ? template.calculateCalories(user.weight, 30) : 0.0;
                  return GestureDetector(
                    onTap: () {
                      Navigator.pop(ctx);
                      _showQuickAddDialog(context, template);
                    },
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLight,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                            child: Icon(_getTypeIcon(type), color: color, size: 22),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(template.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                                const SizedBox(height: 2),
                                Text(template.description, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary), maxLines: 1, overflow: TextOverflow.ellipsis),
                              ],
                            ),
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text('~${cal30.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.calories, fontSize: 15)),
                              const Text('kcal/30p', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
                            ],
                          ),
                          const SizedBox(width: 8),
                          Container(
                            width: 32,
                            height: 32,
                            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), shape: BoxShape.circle),
                            child: Icon(Icons.add, color: color, size: 18),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showQuickAddDialog(BuildContext context, ExerciseTemplate template) {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    String selectedTimeOfDay = _defaultTimeOfDay();

    final timeSlots = [
      {'value': 'morning',   'label': 'Sáng',  'icon': Icons.wb_sunny_outlined,    'color': const Color(0xFFFF9800)},
      {'value': 'afternoon', 'label': 'Chiều', 'icon': Icons.wb_cloudy_outlined,   'color': const Color(0xFF2196F3)},
      {'value': 'evening',   'label': 'Tối',   'icon': Icons.nights_stay_outlined, 'color': const Color(0xFF9C27B0)},
      {'value': 'night',     'label': 'Đêm',   'icon': Icons.bedtime_outlined,     'color': const Color(0xFF3F51B5)},
    ];

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Text(template.name),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: durationController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Thời gian (phút)', suffixText: 'phút'),
                onChanged: (_) => setState(() {}),
                autofocus: true,
              ),
              const SizedBox(height: 16),
              // Chọn buổi tập
              const Align(
                alignment: Alignment.centerLeft,
                child: Text('Buổi tập', style: TextStyle(fontSize: 13, color: AppColors.textSecondary, fontWeight: FontWeight.w500)),
              ),
              const SizedBox(height: 8),
              Row(
                children: timeSlots.map((slot) {
                  final isSelected = selectedTimeOfDay == slot['value'];
                  final color = slot['color'] as Color;
                  return Expanded(
                    child: GestureDetector(
                      onTap: () => setState(() => selectedTimeOfDay = slot['value'] as String),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        decoration: BoxDecoration(
                          color: isSelected ? color.withValues(alpha: 0.15) : AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: isSelected ? color : Colors.transparent,
                            width: 1.5,
                          ),
                        ),
                        child: Column(
                          children: [
                            Icon(slot['icon'] as IconData, size: 18, color: isSelected ? color : AppColors.textHint),
                            const SizedBox(height: 3),
                            Text(slot['label'] as String, style: TextStyle(fontSize: 10, color: isSelected ? color : AppColors.textHint, fontWeight: isSelected ? FontWeight.bold : FontWeight.normal)),
                          ],
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
              if (user != null) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.calorieGradient.colors.first.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.local_fire_department, color: AppColors.calories, size: 20),
                      const SizedBox(width: 8),
                      Text(
                        '~${template.calculateCalories(user.weight, int.tryParse(durationController.text) ?? 30).toStringAsFixed(0)} kcal',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.calories),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Hủy')),
            ElevatedButton(
              onPressed: () {
                final userId = user?.id;
                final duration = int.tryParse(durationController.text) ?? 30;
                if (userId != null) {
                  final exercise = ExerciseModel(
                    id: DateTime.now().millisecondsSinceEpoch.toString(),
                    userId: userId,
                    name: template.name,
                    exerciseTemplateId: template.id,
                    date: DateTime.now(),
                    duration: duration,
                    caloriesBurned: template.calculateCalories(user!.weight, duration),
                    type: template.type,
                    timeOfDay: selectedTimeOfDay,
                  );
                  Provider.of<ExerciseProvider>(context, listen: false).addExercise(exercise);
                  Navigator.pop(context);
                }
              },
              child: const Text('Thêm'),
            ),
          ],
        ),
      ),
    );
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
