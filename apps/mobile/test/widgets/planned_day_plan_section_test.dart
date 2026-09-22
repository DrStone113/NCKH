import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_history.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';
import 'package:health_app/features/plans/widgets/planned_day_plan_section.dart';

void main() {
  test('combined plan is visible in both daily domain projections', () {
    final snapshot = PlanSnapshot(
      plan: const {
        'plan_id': 'combined-1',
        'revision_id': 'revision-1',
        'revision_number': 1,
        'domain': 'COMBINED_HEALTH',
        'lifecycle_status': 'SAVED',
        'period_start': '2026-09-02',
        'period_end': '2026-09-02',
        'days': [
          {
            'date': '2026-09-02',
            'items': [
              {'item_type': 'MEAL', 'dish_name': 'Planned lunch'},
              {
                'item_type': 'WORKOUT_SESSION',
                'name': 'Planned workout',
              },
            ],
          },
        ],
      },
      sessionId: 'session-1',
      createdAt: DateTime.utc(2026, 9, 2),
    );

    final nutrition = PlanHistoryResolver.forDomainAndDate(
      snapshots: [snapshot],
      domain: 'NUTRITION',
      date: DateTime(2026, 9, 2),
    );
    final workout = PlanHistoryResolver.forDomainAndDate(
      snapshots: [snapshot],
      domain: 'WORKOUT',
      date: DateTime(2026, 9, 2),
    );

    expect(nutrition, isNotNull);
    expect(workout, isNotNull);
    expect(nutrition!.day['items'], hasLength(1));
    expect(workout!.day['items'], hasLength(1));
    expect(nutrition.day['items'][0]['item_type'], 'MEAL');
    expect(workout.day['items'][0]['item_type'], 'WORKOUT_SESSION');
  });

  testWidgets('shows a planned meal without turning it into a diary record',
      (tester) async {
    final snapshot = PlanSnapshot(
      plan: const {
        'plan_id': 'plan-1',
        'revision_id': 'revision-1',
        'revision_number': 1,
        'domain': 'NUTRITION',
        'lifecycle_status': 'SAVED',
        'period_start': '2026-09-02',
        'period_end': '2026-09-02',
        'days': [
          {
            'date': '2026-09-02',
            'items': [
              {
                'slot': 'lunch',
                'plan_item_id': 'planned-lunch-1',
                'dish_name': 'Planned lunch',
                'image_url': 'https://example.test/planned-lunch.jpg',
                'nutrition': {
                  'total_calories': 520,
                  'total_protein': 36,
                  'total_carbs': 58,
                  'total_fat': 16,
                },
              },
            ],
          },
        ],
      },
      sessionId: 'session-1',
      createdAt: DateTime.utc(2026, 9, 2),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PlannedDayPlanSection(
            userId: 'user-1',
            date: DateTime(2026, 9, 2),
            domain: 'NUTRITION',
            loader: (_) async => [snapshot],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('planned-day-section-NUTRITION')),
      findsOneWidget,
    );
    expect(find.text('Planned lunch'), findsOneWidget);
    // One value in the exact daily total and one on the matching meal card.
    expect(find.textContaining('520 kcal'), findsNWidgets(2));
    expect(find.byKey(const ValueKey('plan-day-nutrition-summary')),
        findsOneWidget);
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('Tổng thực đơn trong ngày'), findsOneWidget);
    expect(find.text('36 g'), findsOneWidget);
    expect(find.text('Dự kiến · chưa ghi nhận'), findsOneWidget);
  });
}
