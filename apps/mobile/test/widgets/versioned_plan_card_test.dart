import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/widgets/versioned_plan_card.dart';
import 'package:health_app/models/wger_models.dart';

void _noOp() {}

void main() {
  testWidgets('renders deterministic Plan V2 day and planned-state boundary',
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
                    'dish_name': 'Phở gà',
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

    expect(find.text('Kế hoạch dinh dưỡng'), findsOneWidget);
    expect(find.text('• Dự kiến: Phở gà'), findsOneWidget);
    expect(find.textContaining('lịch dự kiến'), findsOneWidget);
    expect(find.text('Lưu'), findsOneWidget);
  });

  test('preserves a versioned plan card through structured history', () {
    final original = StructuredResponse.fromJson({
      'type': 'versioned_plan',
      'text': 'Kế hoạch',
      'days': [
        {'date': '2026-09-01', 'items': []},
      ],
    });
    final restored = StructuredResponse.fromJson(original.toJson());
    expect(restored.versionedPlan?['days'], isA<List<dynamic>>());
  });
}
