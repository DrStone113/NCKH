import 'package:flutter/material.dart';

import '../models/meal_model.dart';
import '../theme/app_theme.dart';

class MealCardIngredientView {
  final String name;
  final double grams;
  final double calories;

  const MealCardIngredientView({
    required this.name,
    required this.grams,
    required this.calories,
  });

  factory MealCardIngredientView.fromMealItem(MealItem item) =>
      MealCardIngredientView(
        name: item.name,
        grams: item.weightGrams,
        calories: item.calories,
      );
}

class MealDishVisual {
  final String emoji;
  final Color background;
  final Color border;

  const MealDishVisual(this.emoji, this.background, this.border);
}

abstract final class MealPresentation {
  static IconData dishIcon(String name) => switch (dishVisual(name).emoji) {
        '🍕' => Icons.local_pizza_outlined,
        '🍔' => Icons.lunch_dining_outlined,
        '🍣' => Icons.set_meal_outlined,
        '🍝' => Icons.ramen_dining_outlined,
        '🍜' => Icons.ramen_dining_outlined,
        '🍚' => Icons.rice_bowl_outlined,
        '🥣' => Icons.soup_kitchen_outlined,
        '🥖' => Icons.bakery_dining_outlined,
        '🍗' => Icons.fastfood_outlined,
        '🦐' => Icons.set_meal_outlined,
        '🐟' => Icons.set_meal_outlined,
        '🥩' => Icons.outdoor_grill_outlined,
        '🥗' => Icons.eco_outlined,
        '🥤' => Icons.local_drink_outlined,
        '☕' => Icons.coffee_outlined,
        '🍎' => Icons.spa_outlined,
        '🍳' => Icons.egg_outlined,
        '🍰' => Icons.cake_outlined,
        _ => Icons.restaurant_outlined,
      };
  static Color accent(String? mealType) {
    switch (MealTypeUtils.normalize(mealType)) {
      case 'sang':
        return const Color(0xFFFF9800);
      case 'trua':
        return const Color(0xFF39A96B);
      case 'toi':
        return const Color(0xFF5C6BC0);
      default:
        return const Color(0xFFAB47BC);
    }
  }

  static IconData mealIcon(String? mealType) {
    switch (MealTypeUtils.normalize(mealType)) {
      case 'sang':
        return Icons.wb_sunny_outlined;
      case 'trua':
        return Icons.lunch_dining_outlined;
      case 'toi':
        return Icons.dinner_dining_outlined;
      default:
        return Icons.local_dining_outlined;
    }
  }

  static MealDishVisual dishVisual(String name) {
    final lower = name.toLowerCase().trim();
    if (_containsAny(lower, const ['pizza'])) {
      return const MealDishVisual(
        '🍕',
        Color(0xFFFFF3E0),
        Color(0xFFFFB74D),
      );
    }
    if (_containsAny(lower, const ['burger', 'hamburger'])) {
      return const MealDishVisual(
        '🍔',
        Color(0xFFFFF8E1),
        Color(0xFFFFD54F),
      );
    }
    if (_containsAny(lower, const ['sushi', 'sashimi'])) {
      return const MealDishVisual(
        '🍣',
        Color(0xFFFCE4EC),
        Color(0xFFF48FB1),
      );
    }
    if (_containsAny(lower, const ['pasta', 'spaghetti', 'macaroni'])) {
      return const MealDishVisual(
        '🍝',
        Color(0xFFFFECE7),
        Color(0xFFFFAB91),
      );
    }
    if (_containsAny(lower, const ['steak', 'beefsteak', 'bít tết'])) {
      return const MealDishVisual(
        '🥩',
        Color(0xFFFCE4EC),
        Color(0xFFF48FB1),
      );
    }
    if (_containsAny(lower, const [
      'phở',
      'bún',
      'mì',
      'miến',
      'hủ tiếu',
      'bánh canh',
    ])) {
      return const MealDishVisual(
        '🍜',
        Color(0xFFFFECE7),
        Color(0xFFFFB39D),
      );
    }
    if (_containsAny(lower, const ['cơm', 'xôi', 'gạo'])) {
      return const MealDishVisual(
        '🍚',
        Color(0xFFFFF3E0),
        Color(0xFFFFCC80),
      );
    }
    if (_containsAny(lower, const ['cháo', 'súp', 'canh'])) {
      return const MealDishVisual(
        '🥣',
        Color(0xFFE0F2F1),
        Color(0xFF80CBC4),
      );
    }
    if (_containsAny(lower, const ['bánh mì', 'sandwich'])) {
      return const MealDishVisual(
        '🥖',
        Color(0xFFEFEBE9),
        Color(0xFFBCAAA4),
      );
    }
    if (_containsAny(lower, const ['gà', 'vịt', 'chim'])) {
      return const MealDishVisual(
        '🍗',
        Color(0xFFFBE9E7),
        Color(0xFFFFAB91),
      );
    }
    if (_containsAny(lower, const ['tôm', 'cua', 'mực', 'hải sản'])) {
      return const MealDishVisual(
        '🦐',
        Color(0xFFE0F7FA),
        Color(0xFF80DEEA),
      );
    }
    if (_containsAny(lower, const ['cá', 'lươn'])) {
      return const MealDishVisual(
        '🐟',
        Color(0xFFE1F5FE),
        Color(0xFF81D4FA),
      );
    }
    if (_containsAny(lower, const ['bò', 'heo', 'thịt', 'sườn', 'chả'])) {
      return const MealDishVisual(
        '🥩',
        Color(0xFFFCE4EC),
        Color(0xFFF48FB1),
      );
    }
    if (_containsAny(lower, const ['trứng', 'ốp la'])) {
      return const MealDishVisual(
        '🍳',
        Color(0xFFFFF8E1),
        Color(0xFFFFD54F),
      );
    }
    if (_containsAny(lower, const ['salad', 'rau', 'gỏi', 'nộm', 'cuốn'])) {
      return const MealDishVisual(
        '🥗',
        Color(0xFFE8F5E9),
        Color(0xFFA5D6A7),
      );
    }
    if (_containsAny(lower, const ['sữa', 'sinh tố', 'nước ép', 'trà'])) {
      return const MealDishVisual(
        '🥤',
        Color(0xFFF3E5F5),
        Color(0xFFCE93D8),
      );
    }
    if (_containsAny(lower, const ['cà phê', 'coffee'])) {
      return const MealDishVisual(
        '☕',
        Color(0xFFEFEBE9),
        Color(0xFFBCAAA4),
      );
    }
    if (_containsAny(lower, const ['bánh ngọt', 'cupcake', 'cheesecake'])) {
      return const MealDishVisual(
        '🍰',
        Color(0xFFFCE4EC),
        Color(0xFFF48FB1),
      );
    }
    if (_containsAny(lower, const ['chuối', 'táo', 'cam', 'trái cây'])) {
      return const MealDishVisual(
        '🍎',
        Color(0xFFFCE4EC),
        Color(0xFFF48FB1),
      );
    }
    return const MealDishVisual(
      '🍽️',
      Color(0xFFFFF3E0),
      Color(0xFFFFCC80),
    );
  }

  static bool _containsAny(String value, List<String> candidates) =>
      candidates.any(value.contains);
}

class MealSummaryCard extends StatelessWidget {
  final String name;
  final String mealType;
  final List<MealCardIngredientView> ingredients;
  final double calories;
  final double protein;
  final double carbs;
  final double fat;
  final bool completed;
  final bool estimated;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final String? actionLabel;
  final IconData actionIcon;
  final VoidCallback? onAction;
  final bool primaryAction;
  final EdgeInsetsGeometry margin;

  const MealSummaryCard({
    super.key,
    required this.name,
    required this.mealType,
    required this.ingredients,
    required this.calories,
    required this.protein,
    required this.carbs,
    required this.fat,
    this.completed = false,
    this.estimated = true,
    this.onTap,
    this.onLongPress,
    this.actionLabel,
    this.actionIcon = Icons.add_rounded,
    this.onAction,
    this.primaryAction = false,
    this.margin = EdgeInsets.zero,
  });

  @override
  Widget build(BuildContext context) {
    final accent = MealPresentation.accent(mealType);
    final visual = MealPresentation.dishVisual(name);
    final totalGrams =
        ingredients.fold<double>(0, (sum, item) => sum + item.grams);

    return Container(
      margin: margin,
      decoration: BoxDecoration(
        color: completed
            ? AppColors.success.withValues(alpha: 0.045)
            : Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: completed
              ? AppColors.success.withValues(alpha: 0.28)
              : accent.withValues(alpha: 0.2),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.035),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: onTap,
            onLongPress: onLongPress,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 11, 12, 9),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: visual.background,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: visual.border),
                    ),
                    alignment: Alignment.center,
                    child: completed
                        ? const Icon(
                            Icons.check_rounded,
                            color: AppColors.success,
                            size: 22,
                          )
                        : Text(
                            visual.emoji,
                            semanticsLabel: 'Biểu tượng món $name',
                            style: const TextStyle(fontSize: 21),
                          ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: completed
                                ? AppColors.textSecondary
                                : AppColors.textPrimary,
                            decoration:
                                completed ? TextDecoration.lineThrough : null,
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${MealTypeUtils.label(mealType)} · '
                          '${ingredients.length} thành phần'
                          '${totalGrams > 0 ? ' · ${totalGrams.toStringAsFixed(0)}g' : ''}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: accent,
                            fontSize: 10.5,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '${estimated ? '~' : ''}${calories.toStringAsFixed(0)}',
                        style: const TextStyle(
                          color: AppColors.calories,
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const Text(
                        'kcal',
                        style: TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 9.5,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          if (ingredients.isNotEmpty) ...[
            Divider(height: 1, color: accent.withValues(alpha: 0.12)),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 7),
              child: Column(
                children: [
                  ...ingredients.take(4).map(
                        (item) => Padding(
                          padding: const EdgeInsets.only(bottom: 5),
                          child: Row(
                            children: [
                              Container(
                                width: 4,
                                height: 4,
                                decoration: BoxDecoration(
                                  color: accent.withValues(alpha: 0.65),
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  '${item.name}  ${item.grams.toStringAsFixed(0)}g',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: AppColors.textSecondary,
                                    fontSize: 11.5,
                                  ),
                                ),
                              ),
                              Text(
                                '${item.calories.toStringAsFixed(0)} kcal',
                                style: const TextStyle(
                                  color: AppColors.textHint,
                                  fontSize: 10.5,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  if (ingredients.length > 4)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        '+ ${ingredients.length - 4} thành phần khác',
                        style: const TextStyle(
                          color: AppColors.textHint,
                          fontSize: 10.5,
                        ),
                      ),
                    ),
                  const SizedBox(height: 2),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                            child:
                                _MacroValue('P', protein, AppColors.protein)),
                        Expanded(
                            child: _MacroValue('C', carbs, AppColors.carbs)),
                        Expanded(child: _MacroValue('F', fat, AppColors.fat)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (actionLabel != null && onAction != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 1, 10, 9),
              child: SizedBox(
                width: double.infinity,
                child: primaryAction
                    ? FilledButton.icon(
                        onPressed: onAction,
                        icon: Icon(actionIcon, size: 16),
                        label: Text(actionLabel!),
                        style: FilledButton.styleFrom(
                          backgroundColor: accent,
                          padding: const EdgeInsets.symmetric(vertical: 9),
                          textStyle: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      )
                    : TextButton.icon(
                        onPressed: onAction,
                        icon: Icon(actionIcon, size: 15, color: accent),
                        label: Text(actionLabel!),
                        style: TextButton.styleFrom(
                          foregroundColor: accent,
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          textStyle: const TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
              ),
            ),
        ],
      ),
    );
  }
}

class _MacroValue extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _MacroValue(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$label:',
          style: TextStyle(
            color: color,
            fontSize: 10.5,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(width: 2),
        Text(
          '${value.toStringAsFixed(0)}g',
          style: const TextStyle(
            color: AppColors.textSecondary,
            fontSize: 10.5,
          ),
        ),
      ],
    );
  }
}
