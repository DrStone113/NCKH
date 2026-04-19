import 'package:flutter/material.dart';
import '../models/meal_model.dart';
import '../theme/app_theme.dart';

/// Widget hiển thị nhóm bữa ăn (Sáng/Trưa/Tối/Phụ)
class MealGroupWidget extends StatelessWidget {
  final String mealType;
  final List<MealModel> meals;
  final VoidCallback onAddMeal;
  final Function(String mealId) onDeleteMeal;
  final Function(String mealId)? onToggleCompleted;

  const MealGroupWidget({
    super.key,
    required this.mealType,
    required this.meals,
    required this.onAddMeal,
    required this.onDeleteMeal,
    this.onToggleCompleted,
  });

  @override
  Widget build(BuildContext context) {
    final totalCalories = meals.fold<double>(0, (sum, meal) => sum + meal.calories);
    final color = _getMealColor(mealType);
    final icon = _getMealIcon(mealType);
    final label = _getMealLabel(mealType);

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        children: [
          // Header
          InkWell(
            onTap: meals.isEmpty ? onAddMeal : null,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: color.withOpacity(0.08),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
              ),
              child: Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(icon, color: color, size: 22),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          label,
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: color,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${meals.length} món • ${totalCalories.toStringAsFixed(0)} kcal',
                          style: TextStyle(
                            fontSize: 12,
                            color: color.withOpacity(0.7),
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: onAddMeal,
                    icon: Icon(Icons.add_circle, color: color),
                    tooltip: 'Thêm món',
                  ),
                ],
              ),
            ),
          ),

          // Meals list
          if (meals.isEmpty)
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Icon(
                    Icons.restaurant_menu,
                    size: 32,
                    color: AppColors.textHint,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Chưa có món ăn nào',
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Nhấn + để thêm món',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textHint,
                    ),
                  ),
                ],
              ),
            )
          else
            ...meals.map((meal) => _buildMealItem(context, meal, color)),
        ],
      ),
    );
  }

  Widget _buildMealItem(BuildContext context, MealModel meal, Color color) {
    return Dismissible(
      key: Key(meal.id),
      direction: DismissDirection.endToStart,
      background: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: AppColors.error,
          borderRadius: BorderRadius.circular(12),
        ),
        alignment: Alignment.centerRight,
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(Icons.delete_outline, color: Colors.white, size: 20),
            SizedBox(width: 6),
            Text(
              'Xoá',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 14,
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
            content: Text('Bạn có chắc muốn xoá "${meal.name}"?'),
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
        onDeleteMeal(meal.id);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã xoá "${meal.name}"'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 2),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            // CHECKBOX
            Transform.scale(
              scale: 1.1,
              child: Checkbox(
                value: meal.isCompleted,
                onChanged: onToggleCompleted != null
                    ? (value) => onToggleCompleted!(meal.id)
                    : null,
                activeColor: AppColors.success,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(Icons.restaurant, color: color, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    meal.name,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      decoration: meal.isCompleted ? TextDecoration.lineThrough : null,
                      color: meal.isCompleted ? AppColors.textSecondary : AppColors.textPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'P: ${meal.protein.toStringAsFixed(0)}g  C: ${meal.carbs.toStringAsFixed(0)}g  F: ${meal.fat.toStringAsFixed(0)}g',
                    style: const TextStyle(
                      fontSize: 10,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '${meal.calories.toStringAsFixed(0)}',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: AppColors.calories,
                    fontSize: 16,
                  ),
                ),
                const Text(
                  'kcal',
                  style: TextStyle(
                    fontSize: 9,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _getMealColor(String type) {
    switch (type) {
      case 'breakfast':
      case 'sang':
        return const Color(0xFFFF9800);
      case 'lunch':
      case 'trua':
        return const Color(0xFF4CAF50);
      case 'dinner':
      case 'toi':
        return const Color(0xFF3F51B5);
      default:
        return const Color(0xFF9C27B0);
    }
  }

  IconData _getMealIcon(String type) {
    switch (type) {
      case 'breakfast':
      case 'sang':
        return Icons.wb_sunny;
      case 'lunch':
      case 'trua':
        return Icons.lunch_dining;
      case 'dinner':
      case 'toi':
        return Icons.dinner_dining;
      default:
        return Icons.fastfood;
    }
  }

  String _getMealLabel(String type) {
    switch (type) {
      case 'breakfast':
      case 'sang':
        return 'Bữa sáng';
      case 'lunch':
      case 'trua':
        return 'Bữa trưa';
      case 'dinner':
      case 'toi':
        return 'Bữa tối';
      default:
        return 'Ăn phụ';
    }
  }
}
