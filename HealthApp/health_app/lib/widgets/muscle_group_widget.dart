import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../models/wger_models.dart';
import '../theme/app_theme.dart';
import '../config/svg_proxy.dart';

// ─── MuscleGroupWidget (chip list) ──────────────────────────────────────────
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
          const Text('Nhóm cơ được tác động',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
        ],
        if (primaryMuscles.isNotEmpty) ...[
          _buildSection('Nhóm cơ chính', primaryMuscles, AppColors.primary, compact),
          if (secondaryMuscles.isNotEmpty) const SizedBox(height: 12),
        ],
        if (secondaryMuscles.isNotEmpty)
          _buildSection('Nhóm cơ phụ', secondaryMuscles, AppColors.textSecondary, compact),
      ],
    );
  }

  Widget _buildSection(String title, List<WgerMuscle> muscles, Color color, bool compact) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!compact) ...[
          Row(children: [
            Container(width: 12, height: 12,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(title, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: color)),
          ]),
          const SizedBox(height: 8),
        ],
        Wrap(
          spacing: 6, runSpacing: 6,
          children: muscles.map((m) => Container(
            padding: EdgeInsets.symmetric(
                horizontal: compact ? 8 : 12, vertical: compact ? 4 : 6),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: color.withValues(alpha: 0.3)),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(m.isFront ? Icons.accessibility_new : Icons.accessibility,
                  size: compact ? 12 : 14, color: color),
              const SizedBox(width: 4),
              Text(_translate(m.nameEn),
                  style: TextStyle(
                      fontSize: compact ? 11 : 12,
                      color: color,
                      fontWeight: FontWeight.w500)),
            ]),
          )).toList(),
        ),
      ],
    );
  }

  String _translate(String nameEn) {
    const t = {
      'Biceps': 'Tay trước', 'Triceps': 'Tay sau', 'Shoulders': 'Vai',
      'Chest': 'Ngực', 'Back': 'Lưng', 'Lats': 'Lưng xô', 'Traps': 'Cơ thang',
      'Abs': 'Bụng', 'Obliques': 'Cơ chéo', 'Quads': 'Đùi trước',
      'Hamstrings': 'Đùi sau', 'Glutes': 'Mông', 'Calves': 'Bắp chân',
      'Adductors': 'Cơ khép', 'Abductors': 'Cơ dạng', 'Lower Back': 'Lưng dưới',
      'Core': 'Core', 'Forearms': 'Cẳng tay', 'Wrists': 'Cổ tay',
    };
    return t[nameEn] ?? nameEn;
  }
}

// ─── MuscleBodyDiagram — Wger SVG body + muscle overlay ─────────────────────
class MuscleBodyDiagram extends StatefulWidget {
  final List<WgerMuscle> primaryMuscles;
  final List<WgerMuscle> secondaryMuscles;

  const MuscleBodyDiagram({
    super.key,
    required this.primaryMuscles,
    required this.secondaryMuscles,
  });

  @override
  State<MuscleBodyDiagram> createState() => _MuscleBodyDiagramState();
}

class _MuscleBodyDiagramState extends State<MuscleBodyDiagram> {
  @override
  Widget build(BuildContext context) {
    final hasFront = widget.primaryMuscles.any((m) => m.isFront) ||
        widget.secondaryMuscles.any((m) => m.isFront);
    final hasBack = widget.primaryMuscles.any((m) => !m.isFront) ||
        widget.secondaryMuscles.any((m) => !m.isFront);

    // Nếu không có muscle nào → hiện cả 2 mặt mờ
    final showFront = hasFront || (!hasFront && !hasBack);
    final showBack  = hasBack  || (!hasFront && !hasBack);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(children: [
        const Text('Sơ đồ nhóm cơ',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            if (showFront)
              _BodySideSvg(
                label: 'Mặt trước',
                isFront: true,
                primaryMuscles: widget.primaryMuscles.where((m) => m.isFront).toList(),
                secondaryMuscles: widget.secondaryMuscles.where((m) => m.isFront).toList(),
              ),
            if (showFront && showBack) const SizedBox(width: 12),
            if (showBack)
              _BodySideSvg(
                label: 'Mặt sau',
                isFront: false,
                primaryMuscles: widget.primaryMuscles.where((m) => !m.isFront).toList(),
                secondaryMuscles: widget.secondaryMuscles.where((m) => !m.isFront).toList(),
              ),
          ],
        ),
        const SizedBox(height: 14),
        const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          _Legend(color: Color(0xFFFF4444), label: 'Cơ chính'),
          SizedBox(width: 20),
          _Legend(color: Color(0xFFFF9800), label: 'Cơ phụ'),
        ]),
      ]),
    );
  }
}

// ─── 1 mặt body (trước / sau) với Wger SVG ────────────────────────────────────
class _BodySideSvg extends StatelessWidget {
  final String label;
  final bool isFront;
  final List<WgerMuscle> primaryMuscles;
  final List<WgerMuscle> secondaryMuscles;

  const _BodySideSvg({
    required this.label,
    required this.isFront,
    required this.primaryMuscles,
    required this.secondaryMuscles,
  });

  @override
  Widget build(BuildContext context) {
    final bodyUrl = isFront 
        ? 'https://wger.de/static/images/muscles/muscular_system_front.svg'
        : 'https://wger.de/static/images/muscles/muscular_system_back.svg';

    return Column(children: [
      Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
      const SizedBox(height: 6),
      SizedBox(
        width: 110,
        height: 200,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Body diagram nền (màu xám)
            SvgPicture.network(
              SvgProxy.resolve(bodyUrl),
              fit: BoxFit.contain,
              colorFilter: ColorFilter.mode(
                Colors.grey.withValues(alpha: 0.3),
                BlendMode.srcIn,
              ),
              placeholderBuilder: (_) => const Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
            // Secondary muscles (dưới) - màu cam
            ...secondaryMuscles.map((m) => SvgPicture.network(
              SvgProxy.resolve(m.imageUrlMain ?? 
                'https://wger.de/static/images/muscles/main/muscle-${m.id}.svg'),
              fit: BoxFit.contain,
              colorFilter: ColorFilter.mode(
                const Color(0xFFFF9800).withValues(alpha: 0.6),
                BlendMode.srcIn,
              ),
              placeholderBuilder: (_) => const SizedBox.shrink(),
            )),
            // Primary muscles (trên) - màu đỏ
            ...primaryMuscles.map((m) => SvgPicture.network(
              SvgProxy.resolve(m.imageUrlMain ?? 
                'https://wger.de/static/images/muscles/main/muscle-${m.id}.svg'),
              fit: BoxFit.contain,
              colorFilter: ColorFilter.mode(
                const Color(0xFFFF4444).withValues(alpha: 0.8),
                BlendMode.srcIn,
              ),
              placeholderBuilder: (_) => const SizedBox.shrink(),
            )),
          ],
        ),
      ),
    ]);
  }
}

// ─── Legend dot ──────────────────────────────────────────────────────────────
class _Legend extends StatelessWidget {
  final Color color;
  final String label;
  const _Legend({required this.color, required this.label});

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 12, height: 12,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle,
          boxShadow: [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 4)]),
      ),
      const SizedBox(width: 6),
      Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
    ],
  );
}
