import 'package:flutter/material.dart';
import '../models/wger_models.dart';
import '../services/wger_detail_service.dart';

/// Hiển thị bottom sheet chi tiết exercise hoặc food từ wger
Future<void> showDetailBottomSheet(
  BuildContext context,
  ActionItem action, {
  VoidCallback? onSave,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _DetailSheet(action: action, onSave: onSave),
  );
}

class _DetailSheet extends StatefulWidget {
  final ActionItem action;
  final VoidCallback? onSave;
  const _DetailSheet({required this.action, this.onSave});

  @override
  State<_DetailSheet> createState() => _DetailSheetState();
}

class _DetailSheetState extends State<_DetailSheet> {
  bool _loading = true;
  ExerciseDetail? _exercise;
  IngredientDetail? _ingredient;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final svc = WgerDetailService();
    try {
      if (widget.action.kind == 'exercise') {
        _exercise = await svc.fetchExercise(widget.action.wgerId);
      } else {
        _ingredient = await svc.fetchIngredient(widget.action.wgerId);
      }
    } catch (e) {
      _error = e.toString();
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final isExercise = widget.action.kind == 'exercise';
    final color = isExercise ? const Color(0xFF2196F3) : const Color(0xFF4CAF50);

    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            // Handle
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Center(
                child: Container(
                  width: 40, height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey[300],
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: Row(
                children: [
                  Container(
                    width: 44, height: 44,
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      isExercise ? Icons.fitness_center : Icons.restaurant_menu,
                      color: color, size: 24,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.action.name,
                          style: const TextStyle(
                              fontSize: 17, fontWeight: FontWeight.w700),
                        ),
                        Text(
                          isExercise ? 'Hướng dẫn bài tập' : 'Thông tin dinh dưỡng',
                          style: TextStyle(fontSize: 12, color: color),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            const Divider(height: 16),

            // Content
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? _buildError(color)
                      : ListView(
                          controller: controller,
                          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                          children: isExercise
                              ? _buildExerciseContent(color)
                              : _buildIngredientContent(color),
                        ),
            ),

            // Save button
            Padding(
              padding: EdgeInsets.fromLTRB(
                  20, 8, 20, MediaQuery.of(context).padding.bottom + 12),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () {
                    Navigator.pop(context);
                    widget.onSave?.call();
                  },
                  icon: const Icon(Icons.bookmark_add_outlined, size: 20),
                  label: const Text('Lưu vào nhật ký',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: color,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                    elevation: 0,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError(Color color) {
    // Nếu wger_id = 0, hiển thị thông tin từ details thay vì lỗi
    return ListView(
      padding: const EdgeInsets.all(20),
      children: widget.action.kind == 'exercise'
          ? _buildExerciseFallback(color)
          : _buildIngredientFallback(color),
    );
  }

  // ─── EXERCISE ───────────────────────────────────────────────────────────────

  List<Widget> _buildExerciseContent(Color color) {
    final ex = _exercise;
    if (ex == null) return _buildExerciseFallback(color);

    return [
      // Image nếu có
      if (ex.imageUrl != null) ...[
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.network(
            ex.imageUrl!,
            height: 200,
            width: double.infinity,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => const SizedBox.shrink(),
          ),
        ),
        const SizedBox(height: 16),
      ],

      // Category + Equipment chips
      Wrap(
        spacing: 8, runSpacing: 8,
        children: [
          if (ex.category.isNotEmpty)
            _chip(ex.category, Icons.category_outlined, color),
          ...ex.equipment.map((e) => _chip(e, Icons.sports_gymnastics, Colors.grey)),
        ],
      ),

      // Aliases
      if (ex.aliases.isNotEmpty) ...[
        const SizedBox(height: 8),
        Wrap(
          spacing: 6, runSpacing: 6,
          children: ex.aliases.map((a) =>
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey[300]!),
              ),
              child: Text(a, style: const TextStyle(fontSize: 11, color: Color(0xFF666666))),
            )
          ).toList(),
        ),
      ],
      const SizedBox(height: 20),

      // Hướng dẫn
      if (ex.description.isNotEmpty) ...[
        _sectionTitle('📋 Hướng dẫn thực hiện', color),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: color.withOpacity(0.04),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.15)),
          ),
          child: Text(
            ex.description,
            style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF333333)),
          ),
        ),
        const SizedBox(height: 20),
      ],

      // Cơ chính + cơ phụ
      if (ex.muscles.isNotEmpty || ex.musclesSecondary.isNotEmpty) ...[
        _sectionTitle('💪 Nhóm cơ', color),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (ex.muscles.isNotEmpty)
              Expanded(child: _muscleGroup('Cơ chính', ex.muscles, color)),
            if (ex.muscles.isNotEmpty && ex.musclesSecondary.isNotEmpty)
              const SizedBox(width: 12),
            if (ex.musclesSecondary.isNotEmpty)
              Expanded(child: _muscleGroup('Cơ phụ', ex.musclesSecondary, Colors.orange)),
          ],
        ),
        const SizedBox(height: 20),
      ],

      // Thông tin AI
      _sectionTitle('⏱ Thông tin từ AI', Colors.grey),
      const SizedBox(height: 8),
      _infoCard(_buildAiExerciseRows(), Colors.grey),
    ];
  }

  Widget _muscleGroup(String title, List<MuscleDetail> muscles, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
          const SizedBox(height: 8),
          ...muscles.map((m) {
            final name = m.nameEn.isNotEmpty ? m.nameEn : m.name;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  if (m.imageUrlMain != null)
                    Image.network(m.imageUrlMain!, width: 28, height: 28,
                        errorBuilder: (_, __, ___) => Icon(Icons.circle, size: 8, color: color))
                  else
                    Icon(Icons.circle, size: 8, color: color),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(name,
                        style: const TextStyle(fontSize: 13, color: Color(0xFF333333))),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  List<Widget> _buildExerciseFallback(Color color) {
    final d = widget.action.details;
    return [
      _sectionTitle('⏱ Thông tin bài tập', color),
      const SizedBox(height: 8),
      _infoCard([
        if (d['duration'] != null) _infoRow('Thời gian', '${d['duration']} phút'),
        if (d['calories_burned'] != null) _infoRow('Calo đốt', '${d['calories_burned']} kcal'),
        if (d['type'] != null) _infoRow('Loại', _translateType(d['type'].toString())),
      ], color),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.amber.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.amber.withOpacity(0.3)),
        ),
        child: const Row(
          children: [
            Icon(Icons.info_outline, color: Colors.amber, size: 18),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Bài tập này chưa có trong cơ sở dữ liệu wger. Thông tin được cung cấp bởi AI.',
                style: TextStyle(fontSize: 13, color: Color(0xFF666666)),
              ),
            ),
          ],
        ),
      ),
    ];
  }

  List<Widget> _buildAiExerciseRows() {
    final d = widget.action.details;
    return [
      if (d['duration'] != null) _infoRow('Thời gian', '${d['duration']} phút'),
      if (d['calories_burned'] != null) _infoRow('Calo đốt', '${d['calories_burned']} kcal'),
      if (d['type'] != null) _infoRow('Loại', _translateType(d['type'].toString())),
    ];
  }

  // ─── INGREDIENT ─────────────────────────────────────────────────────────────

  List<Widget> _buildIngredientContent(Color color) {
    final ing = _ingredient;
    if (ing == null) return _buildIngredientFallback(color);

    return [
      // Image nếu có
      if (ing.imageUrl != null) ...[
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.network(ing.imageUrl!, height: 160, width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const SizedBox.shrink()),
        ),
        const SizedBox(height: 16),
      ],

      // Brand / common name
      if (ing.brand != null || ing.commonName != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Wrap(spacing: 8, children: [
            if (ing.brand != null)
              _chip(ing.brand!, Icons.store_outlined, Colors.blueGrey),
            if (ing.commonName != null)
              _chip(ing.commonName!, Icons.label_outline, Colors.teal),
          ]),
        ),

      // Vegan / Vegetarian badges
      if (ing.isVegan == true || ing.isVegetarian == true)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Wrap(spacing: 8, children: [
            if (ing.isVegan == true)
              _chip('Vegan 🌱', Icons.eco_outlined, Colors.green),
            if (ing.isVegetarian == true)
              _chip('Vegetarian 🥗', Icons.grass_outlined, Colors.lightGreen),
          ]),
        ),

      // Nutriscore
      if (ing.nutriscore != null) ...[
        _sectionTitle('🏷 Nutri-Score', color),
        const SizedBox(height: 8),
        _nutriscoreWidget(ing.nutriscore!),
        const SizedBox(height: 16),
      ],

      // Macro cards
      _sectionTitle('🔥 Dinh dưỡng / 100g', color),
      const SizedBox(height: 12),
      Row(children: [
        _macroCard('Calo', '${ing.energy?.toStringAsFixed(0) ?? '-'}', 'kcal', const Color(0xFFFF7043)),
        const SizedBox(width: 8),
        _macroCard('Protein', '${ing.protein?.toStringAsFixed(1) ?? '-'}', 'g', const Color(0xFFE53935)),
        const SizedBox(width: 8),
        _macroCard('Carbs', '${ing.carbohydrates?.toStringAsFixed(1) ?? '-'}', 'g', const Color(0xFFFFA000)),
        const SizedBox(width: 8),
        _macroCard('Fat', '${ing.fat?.toStringAsFixed(1) ?? '-'}', 'g', const Color(0xFF00ACC1)),
      ]),
      const SizedBox(height: 20),

      // Chi tiết đầy đủ
      _sectionTitle('📊 Chi tiết dinh dưỡng', color),
      const SizedBox(height: 8),
      _infoCard([
        if (ing.energy != null) _infoRow('Năng lượng', '${ing.energy!.toStringAsFixed(0)} kcal'),
        if (ing.protein != null) _infoRow('Protein', '${ing.protein!.toStringAsFixed(1)} g'),
        if (ing.carbohydrates != null) _infoRow('Carbohydrates', '${ing.carbohydrates!.toStringAsFixed(1)} g'),
        if (ing.carbohydratesSugar != null) _infoRow('  └ Đường', '${ing.carbohydratesSugar!.toStringAsFixed(1)} g'),
        if (ing.fat != null) _infoRow('Chất béo', '${ing.fat!.toStringAsFixed(1)} g'),
        if (ing.fatSaturated != null) _infoRow('  └ Bão hòa', '${ing.fatSaturated!.toStringAsFixed(1)} g'),
        if (ing.fiber != null) _infoRow('Chất xơ', '${ing.fiber!.toStringAsFixed(1)} g'),
        if (ing.sodium != null) _infoRow('Natri', '${(ing.sodium! * 1000).toStringAsFixed(0)} mg'),
      ], color),

      // Weight units
      if (ing.weightUnits.isNotEmpty) ...[
        const SizedBox(height: 20),
        _sectionTitle('⚖️ Đơn vị đo lường', color),
        const SizedBox(height: 8),
        _infoCard(
          ing.weightUnits.map((wu) =>
            _infoRow(wu.name, '${wu.gram.toStringAsFixed(0)} g')
          ).toList(),
          color,
        ),
      ],
    ];
  }

  Widget _nutriscoreWidget(String score) {
    final colors = {
      'a': Colors.green[700]!,
      'b': Colors.lightGreen,
      'c': Colors.yellow[700]!,
      'd': Colors.orange,
      'e': Colors.red,
    };
    final c = colors[score.toLowerCase()] ?? Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: c.withOpacity(0.15),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: c.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 32, height: 32,
            decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(8)),
            child: Center(
              child: Text(score.toUpperCase(),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 16)),
            ),
          ),
          const SizedBox(width: 10),
          Text('Nutri-Score $score', style: TextStyle(color: c, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  List<Widget> _buildIngredientFallback(Color color) {
    final d = widget.action.details;
    return [
      _sectionTitle('🔥 Dinh dưỡng / 100g', color),
      const SizedBox(height: 12),
      Row(
        children: [
          if (d['calories'] != null)
            _macroCard('Calo', '${d['calories']}', 'kcal', const Color(0xFFFF7043)),
          if (d['protein'] != null) ...[
            const SizedBox(width: 8),
            _macroCard('Protein', '${d['protein']}', 'g', const Color(0xFFE53935)),
          ],
          if (d['carbs'] != null) ...[
            const SizedBox(width: 8),
            _macroCard('Carbs', '${d['carbs']}', 'g', const Color(0xFFFFA000)),
          ],
          if (d['fat'] != null) ...[
            const SizedBox(width: 8),
            _macroCard('Fat', '${d['fat']}', 'g', const Color(0xFF00ACC1)),
          ],
        ],
      ),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.amber.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.amber.withOpacity(0.3)),
        ),
        child: const Row(
          children: [
            Icon(Icons.info_outline, color: Colors.amber, size: 18),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Thông tin dinh dưỡng được cung cấp bởi AI. Giá trị thực tế có thể khác nhau.',
                style: TextStyle(fontSize: 13, color: Color(0xFF666666)),
              ),
            ),
          ],
        ),
      ),
    ];
  }

  // ─── HELPERS ────────────────────────────────────────────────────────────────

  Widget _sectionTitle(String title, Color color) => Text(
        title,
        style: TextStyle(
            fontSize: 15, fontWeight: FontWeight.w700, color: color),
      );

  Widget _chip(String label, IconData icon, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
            Text(label,
                style: TextStyle(
                    fontSize: 12, color: color, fontWeight: FontWeight.w600)),
          ],
        ),
      );

  Widget _muscleRow(MuscleDetail m, Color color, {required bool isPrimary}) {
    final name = m.nameEn.isNotEmpty ? m.nameEn : m.name;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          if (m.imageUrlMain != null)
            Image.network(m.imageUrlMain!, width: 32, height: 32,
                errorBuilder: (_, __, ___) => Icon(Icons.circle, size: 10, color: color))
          else
            Icon(Icons.circle, size: 10, color: color),
          const SizedBox(width: 10),
          Text(name,
              style: TextStyle(
                  fontSize: 14,
                  color: const Color(0xFF333333),
                  fontWeight: isPrimary ? FontWeight.w600 : FontWeight.normal)),
        ],
      ),
    );
  }

  Widget _infoCard(List<Widget> rows, Color color) => Container(
        decoration: BoxDecoration(
          color: Colors.grey[50],
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.grey[200]!),
        ),
        child: Column(
          children: rows.asMap().entries.map((e) {
            final isLast = e.key == rows.length - 1;
            return Column(
              children: [
                e.value,
                if (!isLast)
                  Divider(height: 1, color: Colors.grey[200], indent: 16, endIndent: 16),
              ],
            );
          }).toList(),
        ),
      );

  Widget _infoRow(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(fontSize: 14, color: Color(0xFF666666))),
            Text(value,
                style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF1A1A1A))),
          ],
        ),
      );

  Widget _macroCard(String label, String value, String unit, Color color) =>
      Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: color.withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.2)),
          ),
          child: Column(
            children: [
              Text(value,
                  style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: color)),
              Text(unit,
                  style: TextStyle(fontSize: 11, color: color.withOpacity(0.8))),
              const SizedBox(height: 2),
              Text(label,
                  style: const TextStyle(
                      fontSize: 11,
                      color: Color(0xFF666666),
                      fontWeight: FontWeight.w500)),
            ],
          ),
        ),
      );

  String _translateType(String type) {
    const map = {
      'cardio': 'Cardio',
      'strength': 'Sức mạnh',
      'flexibility': 'Linh hoạt',
      'sports': 'Thể thao',
      'cool-down': 'Hồi phục',
      'breakfast': 'Bữa sáng',
      'lunch': 'Bữa trưa',
      'dinner': 'Bữa tối',
      'snack': 'Bữa phụ',
    };
    return map[type.toLowerCase()] ?? type;
  }
}
