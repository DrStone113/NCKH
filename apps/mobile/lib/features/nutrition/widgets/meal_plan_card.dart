import 'package:flutter/material.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/health_surface.dart';
import '../../../widgets/meal_summary_card.dart';
import '../../plans/plan_display.dart';

class DishArtwork extends StatelessWidget {
  const DishArtwork({
    super.key,
    required this.name,
    this.imageUrl,
    this.large = false,
  });
  final String name;
  final String? imageUrl;
  final bool large;

  Widget _placeholder() {
    final visual = MealPresentation.dishVisual(name);
    return Container(
      color: visual.background,
      child: Center(
        child: Container(
          padding: EdgeInsets.all(large ? 24 : 12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .65),
            shape: BoxShape.circle,
          ),
          child: Icon(
            MealPresentation.dishIcon(name),
            size: large ? 68 : 32,
            color: AppColors.primary,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final candidate = imageUrl?.trim() ?? '';
    final parsed = Uri.tryParse(candidate);
    if (parsed != null && parsed.scheme == 'https') {
      return Semantics(
        label: 'Dish reference image',
        image: true,
        child: SizedBox(
          width: large ? double.infinity : 76,
          height: large ? 210 : 76,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Image.network(
              candidate,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _placeholder(),
              loadingBuilder: (_, child, progress) =>
                  progress == null ? child : _placeholder(),
            ),
          ),
        ),
      );
    }
    final visual = MealPresentation.dishVisual(name);
    return Semantics(
        label: 'Minh họa món ăn',
        image: true,
        child: Container(
          width: large ? double.infinity : 76,
          height: large ? 210 : 76,
          decoration: BoxDecoration(
              color: visual.background,
              borderRadius: BorderRadius.circular(20)),
          child: Center(
              child: Container(
            padding: EdgeInsets.all(large ? 24 : 12),
            decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .65),
                shape: BoxShape.circle),
            child: Icon(MealPresentation.dishIcon(name),
                size: large ? 68 : 32, color: AppColors.primary),
          )),
        ));
  }
}

class CatalogDishCard extends StatelessWidget {
  const CatalogDishCard(
      {super.key, required this.dish, required this.onSelect});
  final Map<String, dynamic> dish;
  final ValueChanged<Map<String, dynamic>> onSelect;
  @override
  Widget build(BuildContext context) {
    final name = dish['name']?.toString() ?? 'Món ăn';
    final provenance = dish['provenance'];
    final imageUrl = dish['image_url']?.toString() ??
        (provenance is Map ? provenance['source_image_url']?.toString() : null);
    final nutrition = <String, dynamic>{
      for (final key in ['calories', 'protein', 'carbs', 'fat'])
        if (dish['estimated_$key'] is num) 'total_$key': dish['estimated_$key']
    };
    return Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: HealthSurface(
            padding: const EdgeInsets.all(16),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(children: [
                    DishArtwork(name: name, imageUrl: imageUrl),
                    const SizedBox(width: 14),
                    Expanded(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                          Text(name,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w800, fontSize: 17)),
                          const SizedBox(height: 8),
                          Text(
                              nutrition['total_calories'] is num
                                  ? '~${(nutrition['total_calories'] as num).round()} kcal'
                                  : 'Chưa có thông tin năng lượng',
                              style: const TextStyle(
                                  color: AppColors.textSecondary)),
                        ]))
                  ]),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                        child: OutlinedButton(
                            onPressed: () => showModalBottomSheet<void>(
                                context: context,
                                isScrollControlled: true,
                                useSafeArea: true,
                                showDragHandle: true,
                                builder: (_) => FractionallySizedBox(
                                    heightFactor: .9,
                                    child: MealDetailContent(
                                        name: name,
                                        nutrition: nutrition,
                                        content: dish,
                                        imageUrl: imageUrl,
                                        status:
                                            'Món trong danh mục · chưa ghi nhận'))),
                            child: const Text('Xem'))),
                    const SizedBox(width: 10),
                    Expanded(
                        child: FilledButton(
                            onPressed: () => onSelect(dish),
                            child: const Text('Chọn')))
                  ]),
                ])));
  }
}

class MealPlanCard extends StatelessWidget {
  const MealPlanCard({super.key, required this.item, required this.onView});
  final Map<String, dynamic> item;
  final ValueChanged<Map<String, dynamic>> onView;
  @override
  Widget build(BuildContext context) {
    final values = PlanDisplay.nutrition(item);
    final name = PlanDisplay.itemTitle(item, nutrition: true);
    final content = PlanDisplay.itemContent(item);
    final imageUrl = item['image_url']?.toString();
    final grams = content['serving_grams'];
    return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: HealthSurface(
            padding: const EdgeInsets.all(16),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                DishArtwork(name: name, imageUrl: imageUrl),
                const SizedBox(width: 14),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(name,
                          style: const TextStyle(
                              fontSize: 17,
                              height: 1.3,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(height: 6),
                      if (grams is num)
                        Text('${grams.toStringAsFixed(0)} g',
                            style: const TextStyle(
                                color: AppColors.textSecondary)),
                      Text(
                          values['total_calories'] is num
                              ? '${(values['total_calories'] as num).round()} kcal'
                              : 'Chưa có thông tin năng lượng',
                          style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              color: AppColors.primary)),
                    ]))
              ]),
              const SizedBox(height: 14),
              Wrap(spacing: 14, runSpacing: 6, children: [
                for (final entry in {
                  'Protein': 'total_protein',
                  'Carb': 'total_carbs',
                  'Fat': 'total_fat'
                }.entries)
                  if (values[entry.value] is num)
                    Text(
                        '${entry.key} ${(values[entry.value] as num).toStringAsFixed(1)} g',
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.textSecondary))
              ]),
              const SizedBox(height: 6),
              Row(children: [
                const Icon(Icons.schedule_rounded,
                    size: 16, color: AppColors.textSecondary),
                const SizedBox(width: 6),
                const Expanded(
                    child: Text('Dự kiến · chưa ghi nhận',
                        style: TextStyle(
                            fontSize: 12, fontWeight: FontWeight.w600))),
                TextButton(
                    key: ValueKey('view-meal-${PlanDisplay.itemId(item)}'),
                    onPressed: () => onView(item),
                    child: const Text('Xem'))
              ]),
            ])));
  }
}

class PlanDayNutritionSummary extends StatelessWidget {
  const PlanDayNutritionSummary({
    super.key,
    required this.plan,
    required this.day,
  });

  final Map<String, dynamic> plan;
  final Map<String, dynamic> day;

  @override
  Widget build(BuildContext context) {
    final totals = PlanDisplay.nutritionTotalsForDay(day);
    final target = PlanDisplay.dailyTarget(plan, 'calories');
    String value(double? number, String unit) =>
        number == null ? '—' : '${number.toStringAsFixed(0)} $unit';

    return HealthSurface(
      key: const ValueKey('plan-day-nutrition-summary'),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text('Tổng thực đơn trong ngày',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
              Text('${totals.mealCount} bữa',
                  style: const TextStyle(color: AppColors.textSecondary)),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 18,
            runSpacing: 12,
            children: [
              _PlanTotalMetric(
                label: 'Năng lượng dự kiến',
                value: value(totals.calories, 'kcal'),
                color: AppColors.calories,
              ),
              _PlanTotalMetric(
                label: 'Protein',
                value: value(totals.protein, 'g'),
                color: AppColors.protein,
              ),
              _PlanTotalMetric(
                label: 'Carb',
                value: value(totals.carbs, 'g'),
                color: AppColors.carbs,
              ),
              _PlanTotalMetric(
                label: 'Fat',
                value: value(totals.fat, 'g'),
                color: AppColors.fat,
              ),
            ],
          ),
          if (target != null) ...[
            const SizedBox(height: 12),
            Text(
              'Mục tiêu khi tạo kế hoạch: ${target.round()} kcal/ngày',
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
              ),
            ),
          ],
          const SizedBox(height: 8),
          const Text(
            'Các số trên được cộng trực tiếp từ đúng những món hiển thị bên dưới và chưa tính là đã ăn.',
            style: TextStyle(
              fontSize: 12,
              height: 1.35,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanTotalMetric extends StatelessWidget {
  const _PlanTotalMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 128,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 11, color: AppColors.textSecondary)),
            const SizedBox(height: 3),
            Text(value,
                style: TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w800, color: color)),
          ],
        ),
      );
}

class MealSlotSection extends StatelessWidget {
  const MealSlotSection({super.key, required this.items, required this.onView});
  final List<Map<String, dynamic>> items;
  final ValueChanged<Map<String, dynamic>> onView;
  @override
  Widget build(BuildContext context) {
    final slots = <String>[
      'breakfast',
      'lunch',
      'dinner',
      'snack',
      ...items
          .map((item) => item['slot']?.toString() ?? '')
          .where((slot) =>
              !['breakfast', 'lunch', 'dinner', 'snack'].contains(slot))
          .toSet()
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (final slot in slots)
        if (items.any((item) => (item['slot']?.toString() ?? '') == slot)) ...[
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Row(children: [
                Icon(MealPresentation.mealIcon(slot), size: 20),
                const SizedBox(width: 8),
                Text(PlanDisplay.slotLabel(slot, nutrition: true),
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 16))
              ])),
          for (final item in items
              .where((item) => (item['slot']?.toString() ?? '') == slot))
            MealPlanCard(item: item, onView: onView),
        ]
    ]);
  }
}

Future<void> showPlannedMealDetail(
        BuildContext context, Map<String, dynamic> item) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      useSafeArea: true,
      builder: (_) => FractionallySizedBox(
          heightFactor: .9,
          child: MealDetailContent(
            name: PlanDisplay.itemTitle(item, nutrition: true),
            nutrition: PlanDisplay.nutrition(item),
            content: PlanDisplay.itemContent(item),
            imageUrl: item['image_url']?.toString(),
          )),
    );

class MealDetailContent extends StatelessWidget {
  const MealDetailContent(
      {super.key,
      required this.name,
      required this.nutrition,
      required this.content,
      this.imageUrl,
      this.status = 'Dự kiến · chưa ghi nhận',
      this.footer});
  final String name, status;
  final Map<String, dynamic> nutrition, content;
  final String? imageUrl;
  final Widget? footer;
  @override
  Widget build(BuildContext context) {
    final ingredients = content['ingredients'];
    return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          DishArtwork(name: name, imageUrl: imageUrl, large: true),
          const SizedBox(height: 24),
          Text(name,
              style: const TextStyle(
                  fontSize: 28,
                  height: 1.2,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -.7)),
          const SizedBox(height: 10),
          Text(status, style: const TextStyle(color: AppColors.textSecondary)),
          if (content['serving_grams'] is num)
            Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text('Khẩu phần: ${content['serving_grams']} g')),
          const SizedBox(height: 16),
          Text(
              nutrition['total_calories'] is num
                  ? '${(nutrition['total_calories'] as num).round()} kcal'
                  : 'Chưa có thông tin năng lượng',
              style:
                  const TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
          const SizedBox(height: 20),
          Wrap(spacing: 10, runSpacing: 10, children: [
            for (final entry in {
              'Carb': 'total_carbs',
              'Protein': 'total_protein',
              'Fat': 'total_fat'
            }.entries)
              HealthSurface(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(entry.key,
                            style: const TextStyle(
                                color: AppColors.textSecondary)),
                        const SizedBox(height: 8),
                        Text(
                            nutrition[entry.value] is num
                                ? '${(nutrition[entry.value] as num).toStringAsFixed(1)} g'
                                : 'Chưa có',
                            style: const TextStyle(fontWeight: FontWeight.w800))
                      ]))
          ]),
          if (content['recipe_origin'] == 'ADAPTED_RECIPE_VARIANT')
            const Padding(
                padding: EdgeInsets.only(top: 20),
                child: Text('Khẩu phần được điều chỉnh cho mục tiêu của bạn')),
          const HealthSectionTitle('Thành phần'),
          if (ingredients is List && ingredients.isNotEmpty)
            HealthSurface(
                child: Column(children: [
              for (final ingredient in ingredients)
                if (ingredient is Map)
                  ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text((ingredient['food_name'] ??
                              ingredient['name'] ??
                              'Thành phần')
                          .toString()),
                      subtitle: ingredient['grams'] is num ||
                              ingredient['weight_grams'] is num
                          ? Text(
                              '${ingredient['grams'] ?? ingredient['weight_grams']} g')
                          : null),
            ]))
          else
            const Text('Món này chưa có danh sách thành phần chi tiết.',
                style: TextStyle(color: AppColors.textSecondary)),
          if (footer != null) ...[const SizedBox(height: 24), footer!],
        ]));
  }
}
