// ignore_for_file: prefer_const_literals_to_create_immutables

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/widgets/personalized_workout_card.dart';

void main() {
  testWidgets('renders E4 dosage and logs only entered actual observations',
      (tester) async {
    String? status;
    String? pain;
    List<Map<String, dynamic>>? actual;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PersonalizedWorkoutCard(
          workout: {
            'estimated_duration_minutes': 30,
            'energy_estimate': {
              'estimated_energy_expenditure': 140.0,
            },
            'exercises': [
              {
                'canonical_exercise_id': 'e4_test',
                'display_name': 'Source exercise name',
                'sets': 2,
                'rep_range': [8, 12],
                'rest_range_seconds': [60, 90],
                'effort_target_rir': [2, 3],
                'progression_status': 'MAINTAIN',
              },
            ],
          },
          onLog: (nextStatus, nextPain, nextActual) async {
            status = nextStatus;
            pain = nextPain;
            actual = nextActual;
          },
        ),
      ),
    ));

    expect(find.text('Source exercise name'), findsOneWidget);
    expect(find.textContaining('140 kcal'), findsOneWidget);
    await tester.tap(find.text('Hoàn thành'));
    await tester.pump();

    expect(status, 'COMPLETED');
    expect(pain, 'UNKNOWN');
    expect(actual, isEmpty);
  });
}
