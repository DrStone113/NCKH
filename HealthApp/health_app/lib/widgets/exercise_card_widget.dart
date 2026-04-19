import 'package:flutter/material.dart';
import '../models/exercise_model.dart';
import '../models/wger_models.dart';
import '../theme/app_theme.dart';
import 'muscle_group_widget.dart';

/// Widget card bài tập tái sử dụng
class ExerciseCardWidget extends StatelessWidget {
  final String name;
  final String? categoryName;
  final String? imageUrl;
  final List<WgerMuscle>? primaryMuscles;
  final List<WgerEquipment>? equipment;
  final VoidCallback? onTap;
  final VoidCallback? onAddTap;
  final Color? accentColor;

  const ExerciseCardWidget({
    super.key,
    required this.name,
    this.categoryName,
    this.imageUrl,
    this.primaryMuscles,
    this.equipment,
    this.onTap,
    this.onAddTap,
    this.accentColor,
  });

  /// Constructor từ WgerExercise
  factory ExerciseCardWidget.fromWger({
    required WgerExercise exercise,
    VoidCallback? onTap,
    VoidCallback? onAddTap,
  }) {
    return ExerciseCardWidget(
      name: exercise.name,
      categoryName: exercise.categoryName,
      imageUrl: exercise.imageUrl,
      primaryMuscles: exercise.muscles,
      equipment: exercise.equipment,
      onTap: onTap,
      onAddTap: onAddTap,
      accentColor: AppColors.primary,
    );
  }

  /// Constructor từ ExerciseTemplate
  factory ExerciseCardWidget.fromTemplate({
    required ExerciseTemplate template,
    VoidCallback? onTap,
    VoidCallback? onAddTap,
  }) {
    return ExerciseCardWidget(
      name: template.name,
      categoryName: template.type,
      onTap: onTap,
      onAddTap: onAddTap,
      accentColor: _getTypeColor(template.type),
    );
  }

  static Color _getTypeColor(String type) {
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

  @override
  Widget build(BuildContext context) {
    final color = accentColor ?? AppColors.primary;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.surfaceLight),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.04),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Image or placeholder
            if (imageUrl != null)
              ClipRRect(
                borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
                child: Image.network(
                  imageUrl!,
                  height: 140,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) {
                    return _buildPlaceholder(color);
                  },
                ),
              )
            else
              _buildPlaceholder(color),

            // Content
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Category badge
                  if (categoryName != null)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: color.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        categoryName!,
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: color,
                        ),
                      ),
                    ),
                  const SizedBox(height: 8),

                  // Name
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),

                  // Muscles (compact)
                  if (primaryMuscles != null && primaryMuscles!.isNotEmpty) ...[
                    MuscleGroupWidget(
                      primaryMuscles: primaryMuscles!,
                      secondaryMuscles: const [],
                      compact: true,
                    ),
                    const SizedBox(height: 8),
                  ],

                  // Equipment
                  if (equipment != null && equipment!.isNotEmpty) ...[
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: equipment!.take(3).map((eq) {
                        return Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppColors.surfaceLight,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            eq.name,
                            style: const TextStyle(
                              fontSize: 9,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 8),
                  ],

                  // Actions
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: onTap,
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            side: BorderSide(color: color),
                          ),
                          child: const Text('Chi tiết', style: TextStyle(fontSize: 13)),
                        ),
                      ),
                      if (onAddTap != null) ...[
                        const SizedBox(width: 8),
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: onAddTap,
                            style: ElevatedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              backgroundColor: color,
                            ),
                            icon: const Icon(Icons.add, size: 16),
                            label: const Text('Thêm', style: TextStyle(fontSize: 13)),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlaceholder(Color color) {
    return Container(
      height: 140,
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Center(
        child: Icon(
          Icons.fitness_center,
          size: 48,
          color: color.withOpacity(0.3),
        ),
      ),
    );
  }
}
