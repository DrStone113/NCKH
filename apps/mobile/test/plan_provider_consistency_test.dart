import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_display.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';
import 'package:health_app/providers/plan_provider.dart';

Map<String, dynamic> _plan({String lifecycle = 'SAVED'}) => {
      'plan_id': 'plan-1',
      'revision_id': 'revision-1',
      'revision_number': 1,
      'domain': 'NUTRITION',
      'lifecycle_status': lifecycle,
      'period_start': '2026-09-13',
      'period_end': '2026-09-14',
      'days': [
        {
          'date': '2026-09-13',
          'items': [
            {
              'plan_item_id': 'breakfast-1',
              'slot': 'breakfast',
              'dish_name': 'Phở gà',
              'nutrition': {
                'total_calories': 420,
                'total_protein': 30,
                'total_carbs': 52,
                'total_fat': 10,
              },
            },
            {
              'plan_item_id': 'lunch-1',
              'slot': 'lunch',
              'dish_name': 'Cơm cá',
              'nutrition': {
                'total_calories': 580,
                'total_protein': 40,
                'total_carbs': 68,
                'total_fat': 16,
              },
            },
          ],
        },
        {
          'date': '2026-09-14',
          'items': [
            {
              'plan_item_id': 'breakfast-2',
              'slot': 'breakfast',
              'dish_name': 'Cháo cá',
              'nutrition': {
                'total_calories': 360,
                'total_protein': 24,
                'total_carbs': 48,
                'total_fat': 8,
              },
            },
          ],
        },
      ],
    };

void main() {
  test('daily totals are calculated from the meals of that exact date', () {
    final plan = _plan();
    final first = PlanDisplay.dayForDate(plan, DateTime(2026, 9, 13));
    final second = PlanDisplay.dayForDate(plan, DateTime(2026, 9, 14));

    final firstTotals = PlanDisplay.nutritionTotalsForDay(first!);
    final secondTotals = PlanDisplay.nutritionTotalsForDay(second!);

    expect(firstTotals.mealCount, 2);
    expect(firstTotals.calories, 1000);
    expect(firstTotals.protein, 70);
    expect(secondTotals.mealCount, 1);
    expect(secondTotals.calories, 360);
    expect(PlanDisplay.itemId(PlanDisplay.items(first).first), 'breakfast-1');
  });

  test('shared provider updates lifecycle without duplicating the revision',
      () async {
    var loads = 0;
    final provider = PlanProvider(loader: (userId) async {
      loads++;
      return [
        PlanSnapshot(
          plan: _plan(),
          sessionId: 'authoritative',
          createdAt: DateTime.utc(2026, 9, 13),
        ),
      ];
    });

    await provider.loadForUser('user-1');
    await provider.loadForUser('user-1');
    provider.upsertAuthoritativePlan(_plan(lifecycle: 'ACTIVE'));

    expect(loads, 1);
    expect(provider.plans, hasLength(1));
    expect(provider.plans.single.lifecycle, 'ACTIVE');
    expect(
      provider
          .dayFor(domain: 'NUTRITION', date: DateTime(2026, 9, 14))
          ?.day['date'],
      '2026-09-14',
    );
  });

  test('switching owners clears the previous owner before loading', () async {
    final pending = <String, Completer<List<PlanSnapshot>>>{};
    final provider = PlanProvider(loader: (userId) {
      return (pending[userId] ??= Completer<List<PlanSnapshot>>()).future;
    });

    final firstLoad = provider.loadForUser('user-1');
    pending['user-1']!.complete([
      PlanSnapshot(
        plan: _plan(),
        sessionId: 'authoritative',
        createdAt: DateTime.utc(2026, 9, 13),
      ),
    ]);
    await firstLoad;
    expect(provider.plans, hasLength(1));

    final secondLoad = provider.loadForUser('user-2');
    expect(provider.plans, isEmpty);
    pending['user-2']!.complete(const []);
    await secondLoad;
  });
}
