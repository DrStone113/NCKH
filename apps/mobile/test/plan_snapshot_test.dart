import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';

void main() {
  test('extracts the exact Plan V2 revision from structured chat history', () {
    final snapshot = PlanSnapshot.fromChatMessage(
      sessionId: 'session-1',
      message: {
        'role': 'assistant',
        'created_at': '2026-09-02T09:00:00Z',
        'structured': {
          'type': 'versioned_plan',
          'plan_id': 'plan-1',
          'revision_id': 'revision-2',
          'revision_number': 2,
          'domain': 'NUTRITION',
          'lifecycle_status': 'SAVED',
          'days': const [],
        },
      },
    );

    expect(snapshot, isNotNull);
    expect(snapshot!.planId, 'plan-1');
    expect(snapshot.revisionId, 'revision-2');
    expect(snapshot.plan['revision_number'], 2);
    expect(snapshot.sessionId, 'session-1');
  });

  test('never infers a plan from assistant prose', () {
    final snapshot = PlanSnapshot.fromChatMessage(
      sessionId: 'session-1',
      message: {
        'role': 'assistant',
        'content': 'Kế hoạch của bạn đã sẵn sàng.',
        'structured': const {},
      },
    );

    expect(snapshot, isNull);
  });

  test('keeps the newest copy of the same immutable plan revision', () {
    final old = PlanSnapshot(
      plan: {'plan_id': 'plan-1', 'revision_id': 'revision-2'},
      sessionId: 'session-1',
      createdAt: DateTime.utc(2026, 9, 1),
    );
    final current = PlanSnapshot(
      plan: {'plan_id': 'plan-1', 'revision_id': 'revision-2'},
      sessionId: 'session-2',
      createdAt: DateTime.utc(2026, 9, 2),
    );

    final plans = PlanSnapshot.deduplicate([old, current]);

    expect(plans, hasLength(1));
    expect(plans.single.sessionId, 'session-2');
  });
}
