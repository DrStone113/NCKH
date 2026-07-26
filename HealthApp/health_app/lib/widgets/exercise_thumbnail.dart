import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../config/svg_proxy.dart';
import '../models/wger_models.dart';
import '../services/local_exercise_service.dart';
import '../theme/app_theme.dart';

/// Thumbnail thông minh cho bài tập trong nhật ký.
/// Ưu tiên:
///   1. Ảnh thực tế từ wger (imageUrl)
///   2. SVG nhóm cơ overlay lên body diagram
///   3. Icon theo type (fallback)
class ExerciseThumbnail extends StatelessWidget {
  final String exerciseName;
  final String exerciseType; // cardio, strength, flexibility, sports
  final Color typeColor;
  final double size;

  const ExerciseThumbnail({
    super.key,
    required this.exerciseName,
    required this.exerciseType,
    required this.typeColor,
    this.size = 48,
  });

  @override
  Widget build(BuildContext context) {
    final local = LocalExerciseService();

    // Lookup bài tập theo tên (case-insensitive)
    WgerExercise? wgerEx;
    if (local.isLoaded) {
      final nameLower = exerciseName.toLowerCase();
      try {
        wgerEx = local.allExercises.firstWhere(
          (e) => e.name.toLowerCase() == nameLower,
        );
      } catch (_) {
        // Thử partial match
        try {
          wgerEx = local.allExercises.firstWhere(
            (e) => e.name.toLowerCase().contains(nameLower) ||
                nameLower.contains(e.name.toLowerCase()),
          );
        } catch (_) {
          wgerEx = null;
        }
      }
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: size,
        height: size,
        child: _buildContent(wgerEx),
      ),
    );
  }

  Widget _buildContent(WgerExercise? wgerEx) {
    // 1. Ảnh thực tế từ wger
    if (wgerEx?.imageUrl != null) {
      return _WgerExerciseImage(
        imageUrl: wgerEx!.imageUrl!,
        fallback: _buildMuscleSvg(wgerEx) ?? _buildIconFallback(),
      );
    }

    // 2. SVG nhóm cơ
    if (wgerEx != null) {
      final muscleSvg = _buildMuscleSvg(wgerEx);
      if (muscleSvg != null) return muscleSvg;
    }

    // 3. Icon fallback
    return _buildIconFallback();
  }

  /// SVG body diagram + muscle highlight
  Widget? _buildMuscleSvg(WgerExercise wgerEx) {
    final allMuscles = [...wgerEx.muscles, ...wgerEx.musclesSecondary];
    if (allMuscles.isEmpty) return null;

    // Lấy nhóm cơ chính đầu tiên có SVG
    final primary = wgerEx.muscles.isNotEmpty ? wgerEx.muscles.first : allMuscles.first;
    final isFront = primary.isFront;

    final bodyUrl = isFront
        ? 'https://wger.de/static/images/muscles/muscular_system_front.svg'
        : 'https://wger.de/static/images/muscles/muscular_system_back.svg';

    // Lấy SVG URL của nhóm cơ chính
    final muscleUrl = primary.imageUrlMain ??
        'https://wger.de/static/images/muscles/main/muscle-${primary.id}.svg';

    return Container(
      color: typeColor.withOpacity(0.08),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Body base
          Padding(
            padding: const EdgeInsets.all(4),
            child: SvgPicture.network(
              SvgProxy.resolve(bodyUrl),
              fit: BoxFit.contain,
              placeholderBuilder: (_) => const SizedBox.shrink(),
            ),
          ),
          // Muscle highlight (primary — màu đậm)
          Padding(
            padding: const EdgeInsets.all(4),
            child: SvgPicture.network(
              SvgProxy.resolve(muscleUrl),
              fit: BoxFit.contain,
              colorFilter: ColorFilter.mode(typeColor, BlendMode.srcIn),
              placeholderBuilder: (_) => const SizedBox.shrink(),
            ),
          ),
          // Secondary muscles (màu nhạt hơn)
          ...wgerEx.musclesSecondary.take(2).map((m) {
            final secUrl = m.imageUrlMain ??
                'https://wger.de/static/images/muscles/main/muscle-${m.id}.svg';
            return Padding(
              padding: const EdgeInsets.all(4),
              child: SvgPicture.network(
                SvgProxy.resolve(secUrl),
                fit: BoxFit.contain,
                colorFilter: ColorFilter.mode(
                  typeColor.withOpacity(0.45),
                  BlendMode.srcIn,
                ),
                placeholderBuilder: (_) => const SizedBox.shrink(),
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildIconFallback() {
    return Container(
      color: typeColor.withOpacity(0.12),
      child: Icon(_typeIcon, color: typeColor, size: size * 0.5),
    );
  }

  IconData get _typeIcon {
    switch (exerciseType) {
      case 'cardio':      return Icons.directions_run;
      case 'strength':    return Icons.fitness_center;
      case 'flexibility': return Icons.self_improvement;
      case 'sports':      return Icons.sports_soccer;
      default:            return Icons.directions_walk;
    }
  }
}

/// Load ảnh wger với fallback
class _WgerExerciseImage extends StatelessWidget {
  final String imageUrl;
  final Widget fallback;

  const _WgerExerciseImage({required this.imageUrl, required this.fallback});

  @override
  Widget build(BuildContext context) {
    return Image.network(
      SvgProxy.auto(imageUrl),
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => fallback,
      loadingBuilder: (_, child, progress) {
        if (progress == null) return child;
        return fallback; // Hiện fallback trong khi load
      },
    );
  }
}
