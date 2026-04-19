import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../models/exercise_model.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';
import '../widgets/animated_counter.dart';
import 'exercise_detail_screen.dart';
import 'exercise_browser_screen.dart';
import 'exercise_history_screen.dart';
import 'chatbot_screen.dart';

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
            AnimatedCard(
              delay: 100,
              child: const Text('Danh mục bài tập', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
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
                            color: AppColors.success.withOpacity(0.1),
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
                          color: AppColors.primary.withOpacity(0.1),
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
              ...exerciseProvider.todayExercises.asMap().entries.map((e) =>
                AnimatedCard(delay: 250 + e.key * 50, child: _buildExerciseLogCard(context, e.value))
              ),
          ],
        ),
      ),
    );
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
          Icon(icon, color: textColor.withOpacity(0.8), size: 22),
          const SizedBox(height: 10),
          Text(label, style: TextStyle(fontSize: 12, color: textColor.withOpacity(0.7))),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              AnimatedCounter(value: value, decimals: 0, style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: textColor)),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(unit, style: TextStyle(fontSize: 13, color: textColor.withOpacity(0.7))),
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
                color: Colors.white.withOpacity(0.1),
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
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 1.6,
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
              color: color.withOpacity(0.08),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: color.withOpacity(0.2)),
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
                      decoration: BoxDecoration(color: color.withOpacity(0.15), borderRadius: BorderRadius.circular(10)),
                      child: Icon(cat['icon'] as IconData, color: color, size: 20),
                    ),
                    Text('$count bài', style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
                  ],
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cat['label'] as String, style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color)),
                    Text(cat['desc'] as String, style: TextStyle(fontSize: 10, color: color.withOpacity(0.7))),
                  ],
                ),
              ],
            ),
          ),
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
              color: AppColors.success.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.fitness_center, size: 36, color: AppColors.success),
          ),
          const SizedBox(height: 16),
          const Text('Chưa có hoạt động nào', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text('Bắt đầu tập luyện để theo dõi tiến trình', style: TextStyle(fontSize: 13, color: AppColors.textSecondary), textAlign: TextAlign.center),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: () => _openAIChat(context),
                icon: const Icon(Icons.smart_toy_outlined, size: 16),
                label: const Text('Hỏi AI'),
              ),
              const SizedBox(width: 12),
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
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.surfaceLight),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 8, offset: const Offset(0, 2))],
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
              decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(14)),
              child: Icon(_getTypeIcon(exercise.type), color: color, size: 24),
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
                Text('${exercise.caloriesBurned.toStringAsFixed(0)}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppColors.calories)),
                const Text('kcal', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
              ],
            ),
          ],
        ),
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

  void _openAIChat(BuildContext context) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const ChatbotScreen()));
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
                        decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(12)),
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
                            decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(12)),
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
                            decoration: BoxDecoration(color: color.withOpacity(0.12), shape: BoxShape.circle),
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
              if (user != null) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.calorieGradient.colors.first.withOpacity(0.1),
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
    final nameController = TextEditingController();
    final durationController = TextEditingController();
    final caloriesController = TextEditingController();
    String selectedType = 'cardio';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Text('Thêm hoạt động', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Tên hoạt động', prefixIcon: Icon(Icons.edit_outlined)),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: selectedType,
              decoration: const InputDecoration(labelText: 'Loại', prefixIcon: Icon(Icons.category_outlined)),
              dropdownColor: AppColors.surface,
              items: const [
                DropdownMenuItem(value: 'cardio', child: Text('🏃 Cardio')),
                DropdownMenuItem(value: 'strength', child: Text('💪 Sức mạnh')),
                DropdownMenuItem(value: 'flexibility', child: Text('🧘 Linh hoạt')),
                DropdownMenuItem(value: 'sports', child: Text('⚽ Thể thao')),
              ],
              onChanged: (val) => selectedType = val!,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: durationController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Thời gian (phút)'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: caloriesController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Calo đốt (kcal)'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: () {
                  final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
                  if (userId != null && nameController.text.isNotEmpty) {
                    final exercise = ExerciseModel(
                      id: DateTime.now().millisecondsSinceEpoch.toString(),
                      userId: userId,
                      name: nameController.text,
                      date: DateTime.now(),
                      duration: int.tryParse(durationController.text) ?? 0,
                      caloriesBurned: double.tryParse(caloriesController.text) ?? 0,
                      type: selectedType,
                    );
                    Provider.of<ExerciseProvider>(context, listen: false).addExercise(exercise);
                    Navigator.pop(context);
                  }
                },
                child: const Text('Thêm hoạt động', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
