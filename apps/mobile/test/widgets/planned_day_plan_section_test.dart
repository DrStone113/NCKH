import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';
import 'package:health_app/features/plans/widgets/planned_day_plan_section.dart';

void main() {
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
    expect(find.text('Tổng thực đơn trong ngày'), findsOneWidget);
    expect(find.text('36 g'), findsOneWidget);
    expect(find.text('Dự kiến · chưa ghi nhận'), findsOneWidget);
  });
}
