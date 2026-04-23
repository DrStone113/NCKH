import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../models/exercise_model.dart';
import '../theme/app_theme.dart';
import '../services/wger_cache_service.dart';
import '../models/wger_models.dart';

/// Smart exercise picker với tích hợp wger API
/// - Tab 1: Bài tập từ wger API (cached)
/// - Tab 2: Bài tập local database
/// - Tự động tính calories dựa trên MET value và cân nặng
class SmartExercisePicker extends StatefulWidget {
  const SmartExercisePicker({super.key});

  @override
  State<SmartExercisePicker> createState() => _SmartExercisePickerState();
}

class _SmartExercisePickerState extends State<SmartExercisePicker>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final WgerCacheService _cacheService = WgerCacheService();
  
  String _searchQuery = '';
  String _selectedType = 'all';

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

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.9,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      builder: (ctx, scrollCtrl) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              _buildHeader(),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildWgerExercisesTab(),
                    _buildLocalExercisesTab(),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
      child: Column(
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.textHint,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Row(
            children: [
              Text(
                'Thêm bài tập',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 10),
          TextField(
            decoration: const InputDecoration(
              hintText: 'Tìm bài tập...',
              prefixIcon: Icon(Icons.search, size: 20),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (val) => setState(() => _searchQuery = val),
          ),
          const SizedBox(height: 8),
          TabBar(
            controller: _tabController,
            labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            unselectedLabelStyle: const TextStyle(fontSize: 12),
            indicatorSize: TabBarIndicatorSize.tab,
            tabs: [
              Tab(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('🌐 Wger'),
                    if (_cacheService.hasCachedData) ...[
                      const SizedBox(width: 4),
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: AppColors.success,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const Tab(text: '📚 Local'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildWgerExercisesTab() {
    if (!_cacheService.hasCachedData) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            const Text(
              'Đang tải bài tập từ wger...',
              style: TextStyle(color: AppColors.textSecondary),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => _tabController.animateTo(1),
              child: const Text('Dùng bài tập local'),
            ),
          ],
        ),
      );
    }

    final exercises = _cacheService.cachedExercises.where((exercise) {
      if (_searchQuery.isEmpty) return true;
      return exercise.name.toLowerCase().contains(_searchQuery.toLowerCase());
    }).toList();

    if (exercises.isEmpty) {
      return const Center(
        child: Text(
          'Không tìm thấy bài tập',
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: exercises.length,
      itemBuilder: (context, index) {
        return _buildWgerExerciseCard(exercises[index]);
      },
    );
  }

  Widget _buildWgerExerciseCard(WgerExercise exercise) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    
    return GestureDetector(
      onTap: () => _showWgerExerciseDialog(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.surfaceLight),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.primary, AppColors.primary.withOpacity(0.7)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.fitness_center, color: Colors.white, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          exercise.categoryName,
                          style: const TextStyle(
                            fontSize: 10,
                            color: AppColors.primary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (exercise.muscles.isNotEmpty) ...[
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            exercise.muscles.map((m) => m.nameEn).take(2).join(', '),
                            style: const TextStyle(
                              fontSize: 10,
                              color: AppColors.textSecondary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            const Icon(Icons.add_circle, color: AppColors.primary, size: 20),
          ],
        ),
      ),
    );
  }

  void _showWgerExerciseDialog(WgerExercise exercise) {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    
    // Estimate MET value based on category (rough estimation)
    double estimatedMET = 5.0; // Default moderate intensity
    final category = exercise.categoryName.toLowerCase();
    if (category.contains('cardio')) {
      estimatedMET = 7.0;
    } else if (category.contains('strength')) {
      estimatedMET = 6.0;
    } else if (category.contains('stretch') || category.contains('flexibility')) {
      estimatedMET = 3.0;
    }

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          final duration = int.tryParse(durationController.text) ?? 30;
          final calories = user != null 
              ? estimatedMET * user.weight * (duration / 60.0)
              : 0.0;

          return AlertDialog(
            backgroundColor: AppColors.surface,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Text(exercise.name),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Category
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    exercise.categoryName,
                    style: const TextStyle(
                      color: AppColors.primary,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                
                // Duration input
                TextField(
                  controller: durationController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Thời gian (phút)',
                    suffixText: 'phút',
                  ),
                  onChanged: (_) => setState(() {}),
                  autofocus: true,
                ),
                const SizedBox(height: 16),
                
                // Calories estimate
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    gradient: AppColors.calorieGradient,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.local_fire_department,
                        color: Colors.white,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '~${calories.toStringAsFixed(0)} kcal',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Ước tính dựa trên cân nặng và cường độ',
                  style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Hủy'),
              ),
              ElevatedButton(
                onPressed: () {
                  _addWgerExercise(exercise, duration, calories, estimatedMET);
                  Navigator.pop(context);
                  Navigator.pop(context); // Close picker
                },
                child: const Text('Thêm'),
              ),
            ],
          );
        },
      ),
    );
  }

  void _addWgerExercise(WgerExercise exercise, int duration, double calories, double metValue) {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;

    // Map category to type
    String type = 'cardio';
    final category = exercise.categoryName.toLowerCase();
    if (category.contains('strength') || category.contains('arms') || category.contains('legs')) {
      type = 'strength';
    } else if (category.contains('stretch') || category.contains('flexibility')) {
      type = 'flexibility';
    } else if (category.contains('sport')) {
      type = 'sports';
    }

    // Determine intensity based on MET
    String intensity = 'medium';
    if (metValue >= 7) {
      intensity = 'high';
    } else if (metValue < 5) {
      intensity = 'low';
    }

    final exerciseModel = ExerciseModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: userId,
      name: exercise.name,
      date: DateTime.now(),
      duration: duration,
      caloriesBurned: calories,
      type: type,
      intensity: intensity,
    );

    Provider.of<ExerciseProvider>(context, listen: false).addExercise(exerciseModel);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã thêm "${exercise.name}" (${calories.toStringAsFixed(0)} kcal)'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Widget _buildLocalExercisesTab() {
    final allExercises = ExerciseProvider.exerciseDatabase;
    
    final filtered = allExercises.where((exercise) {
      final matchesSearch = _searchQuery.isEmpty ||
          exercise.name.toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesType = _selectedType == 'all' || exercise.type == _selectedType;
      return matchesSearch && matchesType;
    }).toList();

    return Column(
      children: [
        // Type filter
        Padding(
          padding: const EdgeInsets.all(16),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _buildTypeChip('all', 'Tất cả', Icons.fitness_center),
                const SizedBox(width: 8),
                _buildTypeChip('cardio', 'Cardio', Icons.directions_run),
                const SizedBox(width: 8),
                _buildTypeChip('strength', 'Sức mạnh', Icons.fitness_center),
                const SizedBox(width: 8),
                _buildTypeChip('flexibility', 'Linh hoạt', Icons.self_improvement),
                const SizedBox(width: 8),
                _buildTypeChip('sports', 'Thể thao', Icons.sports_soccer),
              ],
            ),
          ),
        ),
        
        // Exercises list
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: filtered.length,
            itemBuilder: (context, index) {
              return _buildLocalExerciseCard(filtered[index]);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildTypeChip(String type, String label, IconData icon) {
    final isSelected = _selectedType == type;
    final color = _getTypeColor(type);

    return GestureDetector(
      onTap: () => setState(() => _selectedType = type),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? color.withOpacity(0.15) : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? color : AppColors.surfaceLight,
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: isSelected ? color : AppColors.textSecondary),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                color: isSelected ? color : AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLocalExerciseCard(ExerciseTemplate exercise) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    final calories30 = user != null ? exercise.calculateCalories(user.weight, 30) : 0.0;
    final color = _getTypeColor(exercise.type);

    return GestureDetector(
      onTap: () => _showLocalExerciseDialog(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [color, color.withOpacity(0.7)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(_getTypeIcon(exercise.type), color: Colors.white, size: 20),
                  Text(
                    exercise.metValue.toStringAsFixed(1),
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    exercise.description,
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
                Text(
                  '~${calories30.toStringAsFixed(0)}',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                    color: AppColors.calories,
                  ),
                ),
                const Text(
                  'kcal/30p',
                  style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
                ),
              ],
            ),
            const SizedBox(width: 8),
            Icon(Icons.add_circle, color: color, size: 20),
          ],
        ),
      ),
    );
  }

  void _showLocalExerciseDialog(ExerciseTemplate exercise) {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          final duration = int.tryParse(durationController.text) ?? 30;
          final calories = user != null 
              ? exercise.calculateCalories(user.weight, duration)
              : 0.0;

          return AlertDialog(
            backgroundColor: AppColors.surface,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Text(exercise.name),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: durationController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Thời gian (phút)',
                    suffixText: 'phút',
                  ),
                  onChanged: (_) => setState(() {}),
                  autofocus: true,
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    gradient: AppColors.calorieGradient,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.local_fire_department,
                        color: Colors.white,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '~${calories.toStringAsFixed(0)} kcal',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Hủy'),
              ),
              ElevatedButton(
                onPressed: () {
                  _addLocalExercise(exercise, duration, calories);
                  Navigator.pop(context);
                  Navigator.pop(context); // Close picker
                },
                child: const Text('Thêm'),
              ),
            ],
          );
        },
      ),
    );
  }

  void _addLocalExercise(ExerciseTemplate exercise, int duration, double calories) {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;

    final exerciseModel = ExerciseModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: userId,
      name: exercise.name,
      exerciseTemplateId: exercise.id,
      date: DateTime.now(),
      duration: duration,
      caloriesBurned: calories,
      type: exercise.type,
      intensity: exercise.metValue >= 7 ? 'high' : exercise.metValue >= 5 ? 'medium' : 'low',
    );

    Provider.of<ExerciseProvider>(context, listen: false).addExercise(exerciseModel);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã thêm "${exercise.name}" (${calories.toStringAsFixed(0)} kcal)'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ),
    );
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
        return AppColors.primary;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type) {
      case 'cardio':
        return Icons.directions_run;
      case 'strength':
        return Icons.fitness_center;
      case 'flexibility':
        return Icons.self_improvement;
      case 'sports':
        return Icons.sports_soccer;
      default:
        return Icons.fitness_center;
    }
  }
}
