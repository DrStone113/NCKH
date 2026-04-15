import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../models/exercise_model.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';
import '../widgets/animated_counter.dart';

class ExerciseScreen extends StatefulWidget {
  const ExerciseScreen({super.key});

  @override
  State<ExerciseScreen> createState() => _ExerciseScreenState();
}

class _ExerciseScreenState extends State<ExerciseScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final exerciseProvider = Provider.of<ExerciseProvider>(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Vận động'),
        automaticallyImplyLeading: false,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Stats cards
            AnimatedCard(
              delay: 0,
              child: _buildStatsRow(exerciseProvider),
            ),
            const SizedBox(height: 20),

            // Exercise categories
            AnimatedCard(
              delay: 100,
              child: const Text('Danh mục bài tập', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(height: 12),
            AnimatedCard(
              delay: 150,
              child: _buildCategoryTabs(),
            ),
            const SizedBox(height: 20),

            // Today's exercises
            AnimatedCard(
              delay: 200,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Hoạt động hôm nay', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  Text('${exerciseProvider.todayExercises.length} hoạt động', style: const TextStyle(color: AppColors.textSecondary)),
                ],
              ),
            ),
            const SizedBox(height: 12),

            if (exerciseProvider.todayExercises.isEmpty)
              AnimatedCard(
                delay: 300,
                child: Container(
                  padding: const EdgeInsets.all(40),
                  decoration: BoxDecoration(
                    color: AppColors.cardDark,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Center(
                    child: Column(
                      children: [
                        Icon(Icons.fitness_center, size: 48, color: AppColors.textHint),
                        SizedBox(height: 12),
                        Text('Chưa có hoạt động nào', style: TextStyle(color: AppColors.textSecondary)),
                        SizedBox(height: 4),
                        Text('Nhấn + để ghi nhận hoạt động', style: TextStyle(fontSize: 12, color: AppColors.textHint)),
                      ],
                    ),
                  ),
                ),
              )
            else
              ...exerciseProvider.todayExercises.asMap().entries.map((entry) {
                final index = entry.key;
                final ex = entry.value;
                return AnimatedCard(
                  delay: 300 + (index * 50),
                  child: _buildExerciseCard(context, ex),
                );
              }),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsRow(ExerciseProvider provider) {
    return Row(
      children: [
        Expanded(
          child: _statCard(
            icon: Icons.timer_outlined,
            value: provider.totalDuration.toDouble(),
            unit: 'phút',
            label: 'Thời gian',
            gradient: AppColors.exerciseGradient,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _statCard(
            icon: Icons.local_fire_department,
            value: provider.totalCaloriesBurned,
            unit: 'kcal',
            label: 'Calo đốt',
            gradient: AppColors.calorieGradient,
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
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Colors.white.withOpacity(0.8), size: 20),
          const SizedBox(height: 8),
          Text(label, style: TextStyle(fontSize: 12, color: Colors.white.withOpacity(0.7))),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              AnimatedCounter(
                value: value,
                decimals: 0,
                style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
              ),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(unit, style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.7))),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryTabs() {
    final categories = [
      {'icon': Icons.directions_run, 'label': 'Cardio', 'type': 'cardio', 'color': AppColors.cardio},
      {'icon': Icons.fitness_center, 'label': 'Sức mạnh', 'type': 'strength', 'color': AppColors.strength},
      {'icon': Icons.self_improvement, 'label': 'Linh hoạt', 'type': 'flexibility', 'color': AppColors.flexibility},
      {'icon': Icons.sports_soccer, 'label': 'Thể thao', 'type': 'sports', 'color': AppColors.sports},
    ];

    return Row(
      children: categories.map((cat) {
        return Expanded(
          child: GestureDetector(
            onTap: () => _showCategoryExercises(context, cat['type'] as String, cat['label'] as String),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 4),
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                color: (cat['color'] as Color).withOpacity(0.12),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: (cat['color'] as Color).withOpacity(0.25)),
              ),
              child: Column(
                children: [
                  Icon(cat['icon'] as IconData, color: cat['color'] as Color, size: 24),
                  const SizedBox(height: 6),
                  Text(cat['label'] as String,
                      style: TextStyle(fontSize: 11, color: cat['color'] as Color, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildExerciseCard(BuildContext context, ExerciseModel exercise) {
    return Dismissible(
      key: Key(exercise.id),
      direction: DismissDirection.endToStart,
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: AppColors.error,
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline, color: Colors.white, size: 24),
            SizedBox(width: 8),
            Text(
              'Xoá',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
      confirmDismiss: (direction) async {
        return await showDialog(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: AppColors.surface,
            title: const Text('Xác nhận xoá'),
            content: Text('Bạn có chắc muốn xoá "${exercise.name}"?'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Huỷ'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(context, true),
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
                child: const Text('Xoá'),
              ),
            ],
          ),
        );
      },
      onDismissed: (direction) {
        Provider.of<ExerciseProvider>(context, listen: false).deleteExercise(exercise.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã xoá "${exercise.name}"'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 2),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: _getTypeColor(exercise.type).withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(_getTypeIcon(exercise.type), color: _getTypeColor(exercise.type), size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${exercise.duration} phút • ${exercise.intensityText}',
                    style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('${exercise.caloriesBurned.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.calories)),
                const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
              ],
            ),
          ],
        ),
      ),
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

  void _showCategoryExercises(BuildContext context, String type, String label) {
    final exercises = Provider.of<ExerciseProvider>(context, listen: false).getExercisesByType(type);
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scrollController) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$label', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text('Chọn bài tập để thêm', style: TextStyle(color: AppColors.textSecondary)),
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
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.cardDark,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        children: [
                          Icon(_getTypeIcon(type), color: _getTypeColor(type), size: 20),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(template.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                                Text(template.description, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                              ],
                            ),
                          ),
                          Text('~${cal30.toStringAsFixed(0)} kcal/30p', style: const TextStyle(fontSize: 11, color: AppColors.calories)),
                          const SizedBox(width: 8),
                          const Icon(Icons.add_circle, color: AppColors.primary, size: 22),
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
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(template.name),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: durationController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Thời gian (phút)', suffixText: 'phút'),
              autofocus: true,
            ),
            if (user != null) ...[
              const SizedBox(height: 12),
              Text(
                'Ước tính: ~${template.calculateCalories(user.weight, int.tryParse(durationController.text) ?? 30).toStringAsFixed(0)} kcal',
                style: const TextStyle(color: AppColors.primary),
              ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
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
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          left: 20, right: 20, top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Thêm hoạt động', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Tên hoạt động', prefixIcon: Icon(Icons.edit)),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: selectedType,
              decoration: const InputDecoration(labelText: 'Loại', prefixIcon: Icon(Icons.category)),
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
              height: 48,
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
                child: const Text('Thêm hoạt động'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
