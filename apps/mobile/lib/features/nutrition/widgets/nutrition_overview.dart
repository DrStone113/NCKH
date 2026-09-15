import 'package:flutter/material.dart';
import '../../../models/canonical_nutrition.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/health_surface.dart';

class DailyDateStrip extends StatelessWidget {
  const DailyDateStrip(
      {super.key,
      required this.selected,
      required this.onSelected,
      this.dates});
  final DateTime selected;
  final ValueChanged<DateTime> onSelected;
  final List<DateTime>? dates;
  @override
  Widget build(BuildContext context) {
    final monday = DateTime(
        selected.year, selected.month, selected.day - selected.weekday + 1);
    final days =
        dates ?? List.generate(7, (i) => monday.add(Duration(days: i)));
    return SizedBox(
        height: 96,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: days.length,
          separatorBuilder: (_, index) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final date = days[i];
            final active = DateUtils.isSameDay(date, selected);
            return Semantics(
                selected: active,
                button: true,
                label: 'Ngày ${date.day} tháng ${date.month}',
                child: Material(
                  color: active ? AppColors.primary : AppColors.surface,
                  borderRadius: BorderRadius.circular(18),
                  child: InkWell(
                      borderRadius: BorderRadius.circular(18),
                      onTap: () => onSelected(date),
                      child: Container(
                        constraints: const BoxConstraints(minWidth: 48),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
                        child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                  date.weekday == 7
                                      ? 'CN'
                                      : 'T${date.weekday + 1}',
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: active
                                          ? Colors.white70
                                          : AppColors.textSecondary)),
                              const SizedBox(height: 8),
                              Text('${date.day}',
                                  style: TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w800,
                                      color: active
                                          ? Colors.white
                                          : AppColors.primary)),
                              if (active)
                                const Icon(Icons.check,
                                    size: 12, color: Colors.white),
                            ]),
                      )),
                ));
          },
        ));
  }
}

class NutritionHeroCard extends StatelessWidget {
  const NutritionHeroCard(
      {super.key, required this.canonical, required this.summary});
  final CanonicalNutritionState? canonical;
  final DailyNutritionSummary? summary;
  @override
  Widget build(BuildContext context) {
    final target = canonical?.calorieTargetKcalPerDay;
    final consumed = summary?.energyConsumedKcal;
    // A remainder is meaningful only beside the same authoritative target.
    // Keep consumed diary data visible when profile-derived targets are absent.
    final remaining = target == null ? null : summary?.energyRemainingKcal;
    final over = target != null && summary?.overTarget == true;
    final available = target != null && remaining != null && consumed != null;
    String value(double? n) =>
        n == null ? '—' : roundNutritionEnergyForDisplay(n).toStringAsFixed(0);
    return HealthSurface(
        child: Column(children: [
      const Row(children: [
        Icon(Icons.local_fire_department_outlined,
            color: AppColors.calories, size: 22),
        SizedBox(width: 8),
        Text('Năng lượng trong ngày',
            style: TextStyle(fontWeight: FontWeight.w700))
      ]),
      const SizedBox(height: 24),
      if (available)
        Semantics(
            label:
                '${value(remaining.abs())} kcal ${over ? 'vượt mục tiêu' : 'còn lại'}',
            child: SizedBox.square(
                dimension: 190,
                child: Stack(alignment: Alignment.center, children: [
                  SizedBox.square(
                      dimension: 182,
                      child: CircularProgressIndicator(
                          value:
                              target > 0 ? (consumed / target).clamp(0, 1) : 0,
                          strokeWidth: 12,
                          strokeCap: StrokeCap.round,
                          backgroundColor: AppColors.surfaceLight,
                          color:
                              over ? AppColors.warning : AppColors.calories)),
                  Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(value(remaining.abs()),
                        style: const TextStyle(
                            fontSize: 40,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -1.5)),
                    Text(over ? 'kcal vượt mục tiêu' : 'kcal còn lại',
                        style: const TextStyle(
                            color: AppColors.textSecondary, fontSize: 13))
                  ]),
                ])))
      else
        Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
                target == null
                    ? canonical?.status ==
                            CanonicalNutritionStatus.requiresSpecialistGuidance
                        ? 'Cần hướng dẫn chuyên gia để xác định mục tiêu phù hợp.'
                        : canonical?.status ==
                                CanonicalNutritionStatus.unsupported
                            ? 'Ứng dụng chưa hỗ trợ mục tiêu năng lượng cho hồ sơ này.'
                            : 'Hoàn thiện hồ sơ để hiển thị mục tiêu năng lượng phù hợp.'
                    : 'Chưa có dữ liệu nhật ký đã xác nhận cho ngày này.',
                style: const TextStyle(
                    fontSize: 17, height: 1.5, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center)),
      const SizedBox(height: 24),
      Row(children: [
        _stat('Đã ăn', value(consumed)),
        _stat('Mục tiêu', value(target)),
        _stat(over ? 'Vượt' : 'Còn lại', value(remaining?.abs())),
      ]),
    ]));
  }

  Widget _stat(String label, String value) => Expanded(
          child: Column(children: [
        Text(label,
            style:
                const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        const SizedBox(height: 6),
        Text(value,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        const Text('kcal',
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary))
      ]));
}

class MacroProgressCard extends StatelessWidget {
  const MacroProgressCard(
      {super.key,
      required this.label,
      required this.color,
      this.consumed,
      this.target,
      this.range});
  final String label;
  final Color color;
  final double? consumed, target;
  final NutritionRange? range;
  @override
  Widget build(BuildContext context) {
    final max = target ?? range?.maximum;
    final targetLabel = target != null
        ? '${target!.round()} g'
        : range != null
            ? '${range!.minimum.round()}–${range!.maximum.round()} g'
            : 'Chưa có mục tiêu';
    return Semantics(
        label:
            '$label: ${consumed == null ? 'chưa có dữ liệu' : '${consumed!.round()} g đã ăn'}, $targetLabel',
        child: Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: HealthSurface(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                              color: color, shape: BoxShape.circle)),
                      const SizedBox(width: 8),
                      Text(label,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      const Spacer(),
                      Text(
                          consumed == null
                              ? 'Chưa ghi nhận'
                              : '${consumed!.toStringAsFixed(1)} g đã ăn',
                          style: const TextStyle(fontWeight: FontWeight.w600))
                    ]),
                    const SizedBox(height: 10),
                    if (consumed != null && max != null && max > 0)
                      ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: LinearProgressIndicator(
                              value: (consumed! / max).clamp(0, 1),
                              minHeight: 6,
                              color: color,
                              backgroundColor: AppColors.surfaceLight)),
                    const SizedBox(height: 8),
                    Text('Mục tiêu: $targetLabel',
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.textSecondary)),
                  ])),
        ));
  }
}

class NutritionMacroSummary extends StatelessWidget {
  const NutritionMacroSummary(
      {super.key, required this.canonical, required this.summary});
  final CanonicalNutritionState? canonical;
  final DailyNutritionSummary? summary;
  @override
  Widget build(BuildContext context) => Column(children: [
        MacroProgressCard(
            label: 'Protein',
            color: AppColors.protein,
            consumed: summary?.proteinConsumedGrams,
            target: canonical?.protein?.planningGramsPerDay),
        MacroProgressCard(
            label: 'Carb',
            color: AppColors.carbs,
            consumed: summary?.carbohydrateConsumedGrams,
            range: canonical?.carbohydrateRangeGramsPerDay),
        MacroProgressCard(
            label: 'Fat',
            color: AppColors.fat,
            consumed: summary?.fatConsumedGrams,
            range: canonical?.fatRangeGramsPerDay),
      ]);
}
