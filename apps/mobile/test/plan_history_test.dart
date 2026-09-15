import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_history.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';

PlanSnapshot _snapshot({
  required String planId,
  required String domain,
  required String lifecycle,
  required int revision,
  required DateTime createdAt,
  required String date,
  required String itemName,
}) {
  return PlanSnapshot(
    plan: {
      'plan_id': planId,
      'revision_id': 'revision-$revision',
      'revision_number': revision,
      'domain': domain,
      'lifecycle_status': lifecycle,
      'period_start': date,
      'period_end': date,
      'days': [
        {
          'date': date,
          'items': [
            {'slot': 'breakfast', 'dish_name': itemName},
          ],
        },
      ],
    },
    sessionId: 'session-1',
    createdAt: createdAt,
  );
}

void main() {
  test('selects the newest usable revision for the requested plan day', () {
    final selected = PlanHistoryResolver.forDomainAndDate(
      snapshots: [
        _snapshot(
          planId: 'old',
          domain: 'NUTRITION',
          lifecycle: 'SAVED',
          revision: 1,
          createdAt: DateTime.utc(2026, 9, 1),
          date: '2026-09-02',
          itemName: 'Older meal',
        ),
        _snapshot(
          planId: 'new',
          domain: 'NUTRITION',
          lifecycle: 'SAVED',
          revision: 2,
          createdAt: DateTime.utc(2026, 9, 2),
          date: '2026-09-02',
          itemName: 'Planned meal',
        ),
        _snapshot(
          planId: 'cancelled',
          domain: 'NUTRITION',
          lifecycle: 'CANCELLED',
          revision: 3,
          createdAt: DateTime.utc(2026, 9, 3),
          date: '2026-09-02',
          itemName: 'Cancelled meal',
        ),
      ],
      domain: 'NUTRITION',
      date: DateTime(2026, 9, 2),
    );

    expect(selected?.snapshot.planId, 'new');
    expect(selected?.day['items'], isNotEmpty);
  });

  test('does not display a plan from the wrong domain or day', () {
    final selected = PlanHistoryResolver.forDomainAndDate(
      snapshots: [
        _snapshot(
          planId: 'workout',
          domain: 'WORKOUT',
          lifecycle: 'ACTIVE',
          revision: 1,
          createdAt: DateTime.utc(2026, 9, 2),
          date: '2026-09-02',
          itemName: 'Workout item',
        ),
        _snapshot(
          planId: 'other-day',
          domain: 'NUTRITION',
          lifecycle: 'ACTIVE',
          revision: 1,
          createdAt: DateTime.utc(2026, 9, 2),
          date: '2026-09-03',
          itemName: 'Tomorrow meal',
        ),
      ],
      domain: 'NUTRITION',
      date: DateTime(2026, 9, 2),
    );

    expect(selected, isNull);
  });
}
