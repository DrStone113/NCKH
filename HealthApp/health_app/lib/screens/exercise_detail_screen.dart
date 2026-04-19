import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/wger_models.dart';
import '../models/exercise_model.dart';
import '../models/user_model.dart';
import '../theme/app_theme.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../widgets/muscle_group_widget.dart';


/// Màn hình chi tiết bài tập từ wger
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

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          // App bar với ảnh
          SliverAppBar(
            expandedHeight: 250,
            pinned: true,
            flexibleSpace: FlexibleSpaceBar(
              title: Text(
                widget.exercise.name,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  shadows: [
                    Shadow(
                      color: Colors.black54,
                      blurRadius: 8,
                    ),
                  ],
                ),
              ),
              background: Stack(
                fit: StackFit.expand,
                children: [
                  // Ảnh bài tập
                  if (widget.exercise.imageUrl != null)
                    Image.network(
                      widget.exercise.imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) {
                        return _buildPlaceholderImage();
                      },
                    )
                  else
                    _buildPlaceholderImage(),
                  
                  // Gradient overlay
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withOpacity(0.7),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Nội dung
          SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Category badge
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: AppColors.primary.withOpacity(0.3),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.category,
                          size: 14,
                          color: AppColors.primary,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          widget.exercise.categoryName,
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppColors.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                // Equipment
                if (widget.exercise.equipment.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                    child: _buildEquipmentSection(),
                  ),

                const SizedBox(height: 20),

                // Tabs
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: TabBar(
                      controller: _tabController,
                      indicator: BoxDecoration(
                        color: AppColors.primary,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      labelColor: Colors.white,
                      unselectedLabelColor: AppColors.textSecondary,
                      labelStyle: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                      tabs: const [
                        Tab(text: 'Hướng dẫn'),
                        Tab(text: 'Nhóm cơ'),
                        Tab(text: 'Thêm vào'),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 20),

                // Tab content
                SizedBox(
                  height: 400,
                  child: TabBarView(
                    controller: _tabController,
                    children: [
                      // Tab 1: Hướng dẫn
                      _buildInstructionsTab(),
                      
                      // Tab 2: Nhóm cơ
                      _buildMusclesTab(),
                      
                      // Tab 3: Thêm vào diary
                      _buildAddToDiaryTab(user),
                    ],
                  ),
                ),

                const SizedBox(height: 20),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPlaceholderImage() {
    return Container(
      color: AppColors.cardDark,
      child: const Center(
        child: Icon(
          Icons.fitness_center,
          size: 80,
          color: AppColors.textHint,
        ),
      ),
    );
  }

  Widget _buildEquipmentSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(
              Icons.fitness_center,
              size: 16,
              color: AppColors.textSecondary,
            ),
            SizedBox(width: 6),
            Text(
              'Thiết bị cần thiết',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: widget.exercise.equipment.map((eq) {
            return Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 10,
                vertical: 5,
              ),
              decoration: BoxDecoration(
                color: AppColors.cardDark,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                eq.name,
                style: const TextStyle(
                  fontSize: 12,
                  color: AppColors.textPrimary,
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildInstructionsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Cách thực hiện',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          if (widget.exercise.description.isNotEmpty)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.cardDark,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                _stripHtml(widget.exercise.description),
                style: const TextStyle(
                  fontSize: 14,
                  color: AppColors.textPrimary,
                  height: 1.6,
                ),
              ),
            )
          else
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.cardDark,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Center(
                child: Text(
                  'Chưa có hướng dẫn chi tiết',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            ),
          const SizedBox(height: 16),
          _buildTipsSection(),
        ],
      ),
    );
  }

  Widget _buildTipsSection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.primary.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.lightbulb_outline,
                size: 18,
                color: AppColors.primary,
              ),
              SizedBox(width: 8),
              Text(
                'Lưu ý khi tập',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: AppColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _buildTipItem('Khởi động kỹ trước khi tập'),
          _buildTipItem('Thực hiện động tác đúng kỹ thuật'),
          _buildTipItem('Thở đều trong quá trình tập'),
          _buildTipItem('Dừng lại nếu cảm thấy đau'),
        ],
      ),
    );
  }

  Widget _buildTipItem(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '• ',
            style: TextStyle(
              fontSize: 14,
              color: AppColors.primary,
              fontWeight: FontWeight.bold,
            ),
          ),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMusclesTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        children: [
          // Muscle groups list
          MuscleGroupWidget(
            primaryMuscles: widget.exercise.muscles,
            secondaryMuscles: widget.exercise.musclesSecondary,
          ),
          
          const SizedBox(height: 20),
          
          // Body diagram
          MuscleBodyDiagram(
            primaryMuscles: widget.exercise.muscles,
            secondaryMuscles: widget.exercise.musclesSecondary,
          ),
        ],
      ),
    );
  }

  Widget _buildAddToDiaryTab(UserModel? user) {
    if (user == null) {
      return const Center(
        child: Text(
          'Vui lòng đăng nhập để thêm bài tập',
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
    }

    final duration = int.tryParse(_durationController.text) ?? 30;
    final estimatedCalories = _estimateCalories(duration, user.weight);

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Thêm vào nhật ký tập luyện',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 20),
          
          // Duration input
          TextField(
            controller: _durationController,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Thời gian tập (phút)',
              prefixIcon: Icon(Icons.timer),
              suffixText: 'phút',
            ),
            onChanged: (value) {
              setState(() {}); // Rebuild to update calories
            },
          ),
          
          const SizedBox(height: 20),
          
          // Quick duration options
          const Text(
            'Chọn nhanh',
            style: TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [15, 30, 45, 60].map((min) {
              final isSelected = _durationController.text == min.toString();
              return GestureDetector(
                onTap: () {
                  setState(() {
                    _durationController.text = min.toString();
                  });
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? AppColors.primary
                        : AppColors.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: AppColors.primary.withOpacity(isSelected ? 1 : 0.3),
                      width: isSelected ? 2 : 1,
                    ),
                  ),
                  child: Text(
                    '$min phút',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                      color: isSelected ? Colors.white : AppColors.primary,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          
          const SizedBox(height: 24),
          
          // Estimated calories
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: AppColors.calorieGradient,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.local_fire_department,
                  color: Colors.white,
                  size: 32,
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Ước tính calo đốt',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.white70,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '~${estimatedCalories.toStringAsFixed(0)} kcal',
                      style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          
          const SizedBox(height: 24),
          
          // Add button
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton.icon(
              onPressed: () => _addExerciseToDiary(user),
              icon: const Icon(Icons.add),
              label: const Text(
                'Thêm vào nhật ký',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _stripHtml(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]*>'), '')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .trim();
  }

  double _estimateCalories(int durationMinutes, double weightKg) {
    // Ước tính MET dựa trên category
    double met = 5.0; // Default moderate intensity
    
    final category = widget.exercise.categoryName.toLowerCase();
    if (category.contains('cardio') || category.contains('running')) {
      met = 8.0;
    } else if (category.contains('strength') || category.contains('weight')) {
      met = 6.0;
    } else if (category.contains('yoga') || category.contains('stretch')) {
      met = 3.0;
    }
    
    // Calories = MET * weight(kg) * time(hours)
    return met * weightKg * (durationMinutes / 60.0);
  }

  void _addExerciseToDiary(UserModel user) {
    final duration = int.tryParse(_durationController.text) ?? 30;
    final calories = _estimateCalories(duration, user.weight);
    
    final exercise = ExerciseModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: user.id,
      name: widget.exercise.name,
      exerciseTemplateId: null, // wger exercise
      date: DateTime.now(),
      duration: duration,
      caloriesBurned: calories,
      type: _mapCategoryToType(widget.exercise.categoryName),
      intensity: 'medium',
    );
    
    Provider.of<ExerciseProvider>(context, listen: false).addExercise(exercise);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã thêm "${widget.exercise.name}" vào nhật ký'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ),
    );
    
    Navigator.pop(context);
  }

  String _mapCategoryToType(String category) {
    final cat = category.toLowerCase();
    if (cat.contains('cardio') || cat.contains('running')) {
      return 'cardio';
    } else if (cat.contains('strength') || cat.contains('weight')) {
      return 'strength';
    } else if (cat.contains('yoga') || cat.contains('stretch')) {
      return 'flexibility';
    }
    return 'cardio';
  }
}
