import 'package:flutter/material.dart';

@immutable
class PlanDayNutritionTotals {
  final int mealCount;
  final double? calories;
  final double? protein;
  final double? carbs;
  final double? fat;

  const PlanDayNutritionTotals({
    required this.mealCount,
    this.calories,
    this.protein,
    this.carbs,
    this.fat,
  });
}

/// Read-only display helpers for an immutable Plan V2 presentation.
///
/// The preferred fields are the published presentation fields. The nested
/// fallbacks only support older persisted structured snapshots; no text is
/// inferred and no Plan state is changed here.
class PlanDisplay {
  static List<Map<String, dynamic>> days(Map<String, dynamic> plan) {
    final rawDays = plan['days'];
    if (rawDays is! List) return const [];
    return rawDays
        .whereType<Map>()
        .map((day) => Map<String, dynamic>.from(day))
        .toList(growable: false);
  }

  static List<Map<String, dynamic>> items(Map<String, dynamic> day) {
    final rawItems = day['items'];
    if (rawItems is! List) return const [];
    return rawItems
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  static Map<String, dynamic>? dayForDate(
    Map<String, dynamic> plan,
    DateTime date,
  ) {
    final key = _dateKey(date);
    for (final day in days(plan)) {
      if (_dateOnly(day['date']) == key) return day;
    }
    return null;
  }

  /// Totals are derived from the exact items rendered for this day. This
  /// prevents a stale summary field from disagreeing with the visible menu.
  static PlanDayNutritionTotals nutritionTotalsForDay(
    Map<String, dynamic> day,
  ) {
    final meals = items(day);
    double? total(String key) {
      if (meals.isEmpty) return null;
      final values = meals.map((item) => nutrition(item)[key]).toList();
      if (values.any((value) => value is! num)) return null;
      return values.cast<num>().fold<double>(
            0,
            (sum, value) => sum + value.toDouble(),
          );
    }

    return PlanDayNutritionTotals(
      mealCount: meals.length,
      calories: total('total_calories'),
      protein: total('total_protein'),
      carbs: total('total_carbs'),
      fat: total('total_fat'),
    );
  }

  static double? dailyTarget(Map<String, dynamic> plan, String nutrient) {
    final targets = plan['daily_targets'];
    if (targets is! Map) return null;
    final value = targets[nutrient];
    return value is num ? value.toDouble() : null;
  }

  static int itemCount(Map<String, dynamic> plan) {
    return days(plan).fold<int>(
      0,
      (total, day) => total + items(day).length,
    );
  }

  static List<String> itemNames(Map<String, dynamic> plan, {int limit = 3}) {
    final names = <String>[];
    for (final day in days(plan)) {
      for (final item in items(day)) {
        final name = itemTitle(item, nutrition: isNutrition(plan));
        if (name.isEmpty || names.contains(name)) continue;
        names.add(name);
        if (names.length == limit) return names;
      }
    }
    return names;
  }

  static bool isNutrition(Map<String, dynamic> plan) =>
      plan['domain']?.toString() == 'NUTRITION';

  static bool isWorkout(Map<String, dynamic> plan) =>
      plan['domain']?.toString() == 'WORKOUT';

  static String itemTitle(
    Map<String, dynamic> item, {
    required bool nutrition,
  }) {
    final content = item['content'];
    final nestedContent = content is Map ? content : const <dynamic, dynamic>{};
    final direct = _nonBlank(item['dish_name']) ??
        _nonBlank(nestedContent['dish_name']) ??
        _nonBlank(item['name']) ??
        _nonBlank(nestedContent['name']);
    if (direct != null) return direct;

    if (nutrition) return 'Món đã lên lịch';
    final duration = plannedDuration(item);
    return duration == null
        ? 'Buổi tập theo lịch E4'
        : 'Buổi tập • ${duration.round()} phút';
  }

  static String itemId(Map<String, dynamic> item) =>
      _nonBlank(item['plan_item_id']) ??
      _nonBlank(item['item_id']) ??
      _nonBlank(item['canonical_refs'] is Map
          ? (item['canonical_refs'] as Map)['dish_id']
          : null) ??
      '';

  static Map<String, dynamic> itemContent(Map<String, dynamic> item) {
    final nested = item['content'];
    return {
      ...item,
      if (nested is Map) ...Map<String, dynamic>.from(nested),
    };
  }

  static String slotLabel(String? slot, {required bool nutrition}) {
    final normalized = slot?.trim().toLowerCase();
    if (nutrition) {
      return switch (normalized) {
        'breakfast' => 'Bữa sáng',
        'lunch' => 'Bữa trưa',
        'dinner' => 'Bữa tối',
        'snack' => 'Bữa phụ',
        _ => 'Bữa ăn',
      };
    }
    return normalized == 'workout' ? 'Buổi tập' : 'Vận động';
  }

  static num? plannedDuration(Map<String, dynamic> item) {
    final direct = item['planned_duration_minutes'];
    if (direct is num) return direct;
    final content = item['content'];
    final nested = content is Map ? content['planned_duration_minutes'] : null;
    return nested is num ? nested : null;
  }

  static Map<String, dynamic> nutrition(Map<String, dynamic> item) {
    final direct = item['nutrition'];
    if (direct is Map) return Map<String, dynamic>.from(direct);
    final content = item['content'];
    if (content is! Map) return const {};
    final nestedNutrition = content['nutrition'];
    if (nestedNutrition is Map) {
      return Map<String, dynamic>.from(nestedNutrition);
    }
    return {
      for (final key in const [
        'total_calories',
        'total_protein',
        'total_carbs',
        'total_fat',
      ])
        if (content[key] is num) key: content[key],
    };
  }

  static String domainTitle(Map<String, dynamic> plan) =>
      switch (plan['domain']?.toString()) {
        'NUTRITION' => 'Kế hoạch dinh dưỡng',
        'WORKOUT' => 'Kế hoạch tập luyện',
        'COMBINED_HEALTH' => 'Kế hoạch sức khỏe',
        _ => 'Kế hoạch',
      };

  static IconData domainIcon(Map<String, dynamic> plan) =>
      switch (plan['domain']?.toString()) {
        'NUTRITION' => Icons.restaurant_menu_outlined,
        'WORKOUT' => Icons.fitness_center_outlined,
        _ => Icons.favorite_outline,
      };

  static String shortDateRange(Map<String, dynamic> plan) {
    final start = _nonBlank(plan['period_start']);
    final end = _nonBlank(plan['period_end']);
    if (start == null && end == null) return 'Chưa xác định thời gian';
    if (end == null) return start!;
    if (start == null) return end;
    if (start == end) return start;
    return '$start – $end';
  }

  static String? _nonBlank(Object? value) {
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? null : text;
  }

  static String _dateKey(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

  static String? _dateOnly(Object? value) {
    final raw = value?.toString().trim() ?? '';
    if (raw.length < 10) return null;
    final candidate = raw.substring(0, 10);
    return DateTime.tryParse(candidate) == null ? null : candidate;
  }
}
