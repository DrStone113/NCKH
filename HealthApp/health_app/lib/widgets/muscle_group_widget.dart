import 'package:flutter/material.dart';
import '../models/wger_models.dart';
import '../theme/app_theme.dart';

/// Widget hiển thị nhóm cơ được tác động bởi bài tập
class MuscleGroupWidget extends StatelessWidget {
  final List<WgerMuscle> primaryMuscles;
  final List<WgerMuscle> secondaryMuscles;
  final bool compact;

  const MuscleGroupWidget({
    super.key,
    required this.primaryMuscles,
    required this.secondaryMuscles,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    if (primaryMuscles.isEmpty && secondaryMuscles.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!compact) ...[
          const Text(
            'Nhóm cơ được tác động',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
        ],
        
        // Primary muscles
        if (primaryMuscles.isNotEmpty) ...[
          _buildMuscleSection(
            'Nhóm cơ chính',
            primaryMuscles,
            AppColors.primary,
            compact,
          ),
          if (secondaryMuscles.isNotEmpty) const SizedBox(height: 12),
        ],
        
        // Secondary muscles
        if (secondaryMuscles.isNotEmpty)
          _buildMuscleSection(
            'Nhóm cơ phụ',
            secondaryMuscles,
            AppColors.textSecondary,
            compact,
          ),
      ],
    );
  }

  Widget _buildMuscleSection(
    String title,
    List<WgerMuscle> muscles,
    Color color,
    bool compact,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!compact) ...[
          Row(
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: color,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                title,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
        ],
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: muscles.map((muscle) {
            return Container(
              padding: EdgeInsets.symmetric(
                horizontal: compact ? 8 : 12,
                vertical: compact ? 4 : 6,
              ),
              decoration: BoxDecoration(
                color: color.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: color.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    muscle.isFront
                        ? Icons.accessibility_new
                        : Icons.accessibility,
                    size: compact ? 12 : 14,
                    color: color,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _translateMuscleName(muscle.nameEn),
                    style: TextStyle(
                      fontSize: compact ? 11 : 12,
                      color: color,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  /// Dịch tên nhóm cơ từ tiếng Anh sang tiếng Việt
  String _translateMuscleName(String nameEn) {
    final translations = {
      // Upper body
      'Biceps': 'Cơ nhị đầu',
      'Triceps': 'Cơ tam đầu',
      'Shoulders': 'Vai',
      'Chest': 'Ngực',
      'Back': 'Lưng',
      'Lats': 'Cơ lưng xô',
      'Traps': 'Cơ thang',
      'Abs': 'Bụng',
      'Obliques': 'Cơ chéo bụng',
      
      // Lower body
      'Quads': 'Cơ tứ đầu',
      'Hamstrings': 'Gân kheo',
      'Glutes': 'Mông',
      'Calves': 'Bắp chân',
      'Adductors': 'Cơ khép',
      'Abductors': 'Cơ dạng',
      
      // Core
      'Lower Back': 'Lưng dưới',
      'Core': 'Cơ core',
      
      // Arms
      'Forearms': 'Cẳng tay',
      'Wrists': 'Cổ tay',
    };

    return translations[nameEn] ?? nameEn;
  }
}

/// Widget hiển thị biểu đồ cơ thể với nhóm cơ được highlight
class MuscleBodyDiagram extends StatelessWidget {
  final List<WgerMuscle> primaryMuscles;
  final List<WgerMuscle> secondaryMuscles;

  const MuscleBodyDiagram({
    super.key,
    required this.primaryMuscles,
    required this.secondaryMuscles,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          const Text(
            'Sơ đồ nhóm cơ',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildBodySide('Mặt trước', true),
              _buildBodySide('Mặt sau', false),
            ],
          ),
          const SizedBox(height: 12),
          _buildLegend(),
        ],
      ),
    );
  }

  Widget _buildBodySide(String label, bool isFront) {
    final muscles = [
      ...primaryMuscles.where((m) => m.isFront == isFront),
      ...secondaryMuscles.where((m) => m.isFront == isFront),
    ];

    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          width: 100,
          height: 200,
          decoration: BoxDecoration(
            color: AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(50),
            border: Border.all(
              color: AppColors.textHint.withOpacity(0.3),
            ),
          ),
          child: Stack(
            children: [
              // Placeholder body icon
              Center(
                child: Icon(
                  isFront
                      ? Icons.accessibility_new
                      : Icons.accessibility,
                  size: 80,
                  color: AppColors.textHint.withOpacity(0.3),
                ),
              ),
              // Muscle highlights (simplified)
              if (muscles.isNotEmpty)
                Center(
                  child: Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.3),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLegend() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildLegendItem('Nhóm cơ chính', AppColors.primary),
        const SizedBox(width: 16),
        _buildLegendItem('Nhóm cơ phụ', AppColors.textSecondary),
      ],
    );
  }

  Widget _buildLegendItem(String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: const TextStyle(
            fontSize: 11,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}
