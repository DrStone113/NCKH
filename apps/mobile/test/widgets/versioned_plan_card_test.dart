import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/wger_models.dart';
import 'package:health_app/widgets/versioned_plan_card.dart';

void _noOp() {}

void main() {
  testWidgets('renders a planned nutrition item from the current snapshot',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: VersionedPlanCard(
          onSave: _noOp,
          plan: {
            'domain': 'NUTRITION',
            'revision_number': 2,
            'period_start': '2026-09-01',
            'period_end': '2026-09-01',
            'days': [
              {
                'date': '2026-09-01',
                'items': [
                  {
                    'slot': 'breakfast',
                    'dish_name': 'Grilled chicken',
                    'status': 'PLANNED',
                    'canonical_refs': {'dish_id': '101'},
                  },
                ],
              },
            ],
          },
        ),
      ),
    ));

    expect(find.text('Grilled chicken'), findsOneWidget);
    expect(find.byIcon(Icons.restaurant_outlined), findsOneWidget);
    expect(find.byIcon(Icons.visibility_outlined), findsOneWidget);
    expect(find.byType(TextButton), findsWidgets);
  });

  testWidgets('keeps dishes visible for older nested item snapshots',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: VersionedPlanCard(
          showHeader: false,
          plan: {
            'domain': 'NUTRITION',
            'days': [
              {
                'date': '2026-09-01',
                'items': [
                  {
                    'slot': 'lunch',
                    'content': {
                      'dish_name': 'Bun cha',
                      'nutrition': {'total_calories': 510},
                    },
                  },
                ],
              },
            ],
          },
        ),
      ),
    ));

    expect(find.text('Bun cha'), findsOneWidget);
    expect(find.textContaining('510 kcal'), findsOneWidget);
  });

  test('preserves a versioned plan card through structured history', () {
    final original = StructuredResponse.fromJson({
      'type': 'versioned_plan',
      'text': 'Plan',
      'days': [
        {'date': '2026-09-01', 'items': []},
      ],
    });
    final restored = StructuredResponse.fromJson(original.toJson());
    expect(restored.versionedPlan?['days'], isA<List<dynamic>>());
  });

  testWidgets('offers a direct view action when the host provides one',
      (tester) async {
    var opened = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: VersionedPlanCard(
          plan: const {
            'plan_id': 'plan-1',
            'revision_id': 'revision-1',
            'domain': 'WORKOUT',
            'lifecycle_status': 'SAVED',
            'days': [],
          },
          onView: () => opened = true,
        ),
      ),
    ));

    await tester.tap(find.textContaining('Xem'));

    expect(opened, isTrue);
  });
}
