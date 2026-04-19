import 'package:flutter/material.dart';
import '../models/wger_models.dart';

class ActionCardWidget extends StatelessWidget {
  final ActionItem action;
  final VoidCallback? onSaveToJournal;
  final VoidCallback? onViewDetail;

  const ActionCardWidget({
    super.key,
    required this.action,
    this.onSaveToJournal,
    this.onViewDetail,
  });

  @override
  Widget build(BuildContext context) {
    final isExercise = action.kind == 'exercise';
    final primaryColor = isExercise
        ? const Color(0xFF2196F3)
        : const Color(0xFF4CAF50);

    return Container(
      margin: const EdgeInsets.only(top: 8, bottom: 4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: primaryColor.withOpacity(0.2), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: primaryColor.withOpacity(0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: primaryColor.withOpacity(0.06),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(14),
                topRight: Radius.circular(14),
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: primaryColor.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    isExercise ? Icons.fitness_center : Icons.restaurant_menu,
                    color: primaryColor,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        action.name,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF1A1A1A),
                        ),
                      ),
                      Text(
                        isExercise ? 'Bài tập' : 'Món ăn',
                        style: TextStyle(
                          fontSize: 12,
                          color: primaryColor,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Stats row
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: isExercise
                ? _buildExerciseStats(primaryColor)
                : _buildFoodStats(primaryColor),
          ),

          // Divider
          Divider(height: 1, color: primaryColor.withOpacity(0.1)),

          // Buttons
          Padding(
            padding: const EdgeInsets.all(10),
            child: Row(
              children: [
                Expanded(
                  child: _buildSaveButton(context, primaryColor),
                ),
                const SizedBox(width: 8),
                _buildDetailButton(context, primaryColor),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildExerciseStats(Color color) {
    final duration = action.details['duration'];
    final calories = action.details['calories_burned'];
    final type = action.details['type'];

    return Row(
      children: [
        if (duration != null) ...[
          _buildStat(Icons.timer_outlined, '$duration phút', const Color(0xFF2196F3)),
          const SizedBox(width: 10),
        ],
        if (calories != null) ...[
          _buildStat(Icons.local_fire_department_outlined, '$calories kcal', const Color(0xFFFF7043)),
          const SizedBox(width: 10),
        ],
        if (type != null)
          _buildStat(Icons.sports, _translateType(type.toString()), const Color(0xFF9C27B0)),
      ],
    );
  }

  Widget _buildFoodStats(Color color) {
    final calories = action.details['calories'];
    final protein = action.details['protein'];
    final carbs = action.details['carbs'];
    final fat = action.details['fat'];
    final servingGrams = action.details['serving_grams'];
    final mealType = action.details['meal_type'];

    // Tính giá trị thực tế theo serving_grams nếu có
    // (calories/protein/carbs/fat là per 100g, serving_grams là khẩu phần)
    final double multiplier = servingGrams != null ? (servingGrams as num).toDouble() / 100.0 : 1.0;
    final bool hasServing = servingGrams != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Serving size badge
        if (hasServing) ...[
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: color.withOpacity(0.3)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.scale_outlined, size: 13, color: color),
                    const SizedBox(width: 4),
                    Text(
                      '${_fmt(servingGrams)}g / khẩu phần',
                      style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w700),
                    ),
                  ],
                ),
              ),
              if (mealType != null) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF9C27B0).withOpacity(0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _translateType(mealType.toString()),
                    style: const TextStyle(fontSize: 11, color: Color(0xFF9C27B0), fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
        ],
        // Macro stats — hiển thị giá trị thực tế theo khẩu phần
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            if (calories != null)
              _buildStat(
                Icons.local_fire_department_outlined,
                hasServing
                    ? '${_fmt((calories as num) * multiplier)} kcal'
                    : '${_fmt(calories)} kcal/100g',
                const Color(0xFFFF7043),
              ),
            if (protein != null)
              _buildStat(
                Icons.egg_outlined,
                hasServing
                    ? 'P: ${_fmt((protein as num) * multiplier)}g'
                    : 'P: ${_fmt(protein)}g',
                const Color(0xFFE53935),
              ),
            if (carbs != null)
              _buildStat(
                Icons.grain,
                hasServing
                    ? 'C: ${_fmt((carbs as num) * multiplier)}g'
                    : 'C: ${_fmt(carbs)}g',
                const Color(0xFFFFA000),
              ),
            if (fat != null)
              _buildStat(
                Icons.water_drop_outlined,
                hasServing
                    ? 'F: ${_fmt((fat as num) * multiplier)}g'
                    : 'F: ${_fmt(fat)}g',
                const Color(0xFF00ACC1),
              ),
          ],
        ),
        // Per 100g note nếu có serving
        if (hasServing) ...[
          const SizedBox(height: 4),
          Text(
            '(${_fmt(calories ?? 0)} kcal/100g)',
            style: const TextStyle(fontSize: 10, color: Color(0xFFADB5BD)),
          ),
        ],
      ],
    );
  }

  Widget _buildStat(IconData icon, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: color,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSaveButton(BuildContext context, Color color) {
    return GestureDetector(
      onTap: onSaveToJournal,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.bookmark_add_outlined, color: Colors.white, size: 16),
            SizedBox(width: 6),
            Text(
              'Lưu vào nhật ký',
              style: TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailButton(BuildContext context, Color color) {
    return GestureDetector(
      onTap: onViewDetail,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Icon(Icons.open_in_new_rounded, color: color, size: 18),
      ),
    );
  }

  String _translateType(String type) {
    const map = {
      'cardio': 'Cardio',
      'strength': 'Sức mạnh',
      'flexibility': 'Linh hoạt',
      'sports': 'Thể thao',
      'cool-down': 'Hồi phục',
      'breakfast': 'Sáng',
      'lunch': 'Trưa',
      'dinner': 'Tối',
      'snack': 'Phụ',
    };
    return map[type.toLowerCase()] ?? type;
  }

  String _fmt(dynamic value) {
    if (value is int) return value.toString();
    if (value is double) {
      return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 1);
    }
    return value.toString();
  }
}
