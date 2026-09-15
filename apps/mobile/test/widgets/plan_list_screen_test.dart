import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';
import 'package:health_app/features/plans/screens/plan_list_screen.dart';

PlanSnapshot _plan({
  required String planId,
  required String revisionId,
  required String lifecycle,
  String dishName = 'Pho ga',
  String domain = 'NUTRITION',
}) {
  return PlanSnapshot(
    plan: {
      'plan_id': planId,
      'revision_id': revisionId,
      'revision_number': 1,
      'domain': domain,
      'lifecycle_status': lifecycle,
      'period_start': '2026-09-01',
      'period_end': '2026-09-07',
      'days': [
        {
          'date': '2026-09-01',
          'items': [
            {'slot': 'breakfast', 'dish_name': dishName},
          ],
        },
      ],
    },
    sessionId: 'session-1',
    createdAt: DateTime.utc(2026, 9, 2),
  );
}

void main() {
  testWidgets('shows planned dishes in the library and exact detail snapshot',
      (tester) async {
    final completer = Completer<List<PlanSnapshot>>();
    await tester.pumpWidget(
      MaterialApp(home: PlanListScreen(loader: () => completer.future)),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    completer.complete([
      _plan(planId: 'plan-1', revisionId: 'revision-1', lifecycle: 'ACTIVE'),
    ]);
    await tester.pumpAndSettle();

    expect(find.text('Pho ga'), findsOneWidget);
    await tester.tap(find.textContaining('Xem'));
    await tester.pumpAndSettle();

    expect(find.text('Pho ga'), findsOneWidget);
    expect(find.text('Dự kiến · chưa ghi nhận'), findsOneWidget);
  });

  testWidgets('keeps active, pending, and terminal plans discoverable',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PlanListScreen(
          loader: () async => [
            _plan(
              planId: 'active',
              revisionId: '1',
              lifecycle: 'ACTIVE',
              dishName: 'Active meal',
            ),
            _plan(
              planId: 'draft',
              revisionId: '1',
              lifecycle: 'DRAFT',
              dishName: 'Draft meal',
            ),
            _plan(
              planId: 'cancelled',
              revisionId: '1',
              lifecycle: 'CANCELLED',
              dishName: 'History meal',
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Active meal'), findsOneWidget);
    expect(find.text('Draft meal'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('History meal'),
      200,
      scrollable: find.byType(Scrollable),
    );
    expect(find.text('History meal'), findsOneWidget);
  });

  testWidgets('shows empty and recoverable error states', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: PlanListScreen(loader: () async => const [])),
    );
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.event_note_outlined), findsOneWidget);

    await tester.pumpWidget(
      MaterialApp(
        home: PlanListScreen(
          key: const ValueKey('error-state'),
          loader: () => Future<List<PlanSnapshot>>.error(StateError('offline')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.cloud_off_outlined), findsOneWidget);
    expect(find.byIcon(Icons.refresh_rounded), findsWidgets);
  });
}
