import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:health_app/models/wger_models.dart';
import 'package:health_app/widgets/recommendation_feedback_bar.dart';

void main() {
  test('preserves exact server-issued recommendation feedback identity', () {
    final action = ActionItem.fromJson({
      'kind': 'food',
      'name': 'Shadow chicken rice',
      'details': {
        'feedback_eligible': true,
        'recommendation_event_id': 'event-42',
        'recommendation_candidate_id': 'candidate-17',
        'recommendation_policy_version':
            'RECOMMENDATION_RANKER_V2_WEIGHT_POLICY_V1',
      },
    });

    expect(action.details['feedback_eligible'], isTrue);
    expect(action.details['recommendation_event_id'], 'event-42');
    expect(action.details['recommendation_candidate_id'], 'candidate-17');
    expect(
      action.details['recommendation_policy_version'],
      'RECOMMENDATION_RANKER_V2_WEIGHT_POLICY_V1',
    );
  });

  testWidgets(
      'renders lightweight shadow feedback and records explicit actions',
      (tester) async {
    final events = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RecommendationFeedbackBar(
            publicReasonCodes: const [
              'NUTRITION_REMAINING_FIT',
              'DIVERSITY_PROTEIN_ROTATION',
            ],
            onChangeDish: () {},
            onFeedback: (eventType, reasonCode) async {
              events.add('$eventType:${reasonCode ?? ''}');
            },
          ),
        ),
      ),
    );

    expect(find.text('Thích'), findsOneWidget);
    expect(find.text('Không hợp'), findsOneWidget);
    expect(find.text('Đổi món'), findsOneWidget);
    expect(find.text('Đã ăn'), findsNothing);
    expect(find.text('Lưu lại'), findsOneWidget);
    expect(find.text('Vì sao?'), findsOneWidget);

    await tester.tap(find.byKey(const Key('recommendation-like')));
    await tester.pump();
    expect(events, ['LIKED:']);
    expect(find.bySemanticsLabel('n3-feedback-like'), findsOneWidget);
    expect(find.bySemanticsLabel('n3-feedback-reject'), findsOneWidget);

    await tester.tap(find.byKey(const Key('recommendation-why')));
    await tester.pumpAndSettle();
    expect(find.text('Vì sao món này?'), findsOneWidget);
    expect(find.textContaining('dinh dưỡng còn lại'), findsOneWidget);
    expect(find.textContaining('nguồn đạm'), findsOneWidget);
  });
  testWidgets('does not render a false accepted state when feedback fails',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RecommendationFeedbackBar(
            onFeedback: (_, __) async {
              throw StateError('synthetic feedback API failure');
            },
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('recommendation-like')));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Đã thích'), findsNothing);
    expect(find.bySemanticsLabel('n3-feedback-like'), findsOneWidget);
    expect(
      find.byKey(const Key('recommendation-feedback-error')),
      findsOneWidget,
    );
  });
}
