import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/screens/plan_detail_screen.dart';
import 'package:health_app/services/backend_api_service.dart';

Map<String, dynamic> meal(String id, String name, String dishId) => {
      'plan_item_id': id,
      'item_type': 'MEAL',
      'status': 'PLANNED',
      'slot': 'lunch',
      'dish_name': name,
      'canonical_refs': {
        'dish_id': dishId,
        'food_ids': ['food-$dishId']
      },
      'ingredients': [
        {'food_id': 'food-$dishId', 'grams': 100}
      ],
      'nutrition': {
        'total_calories': 300,
        'total_protein': 20,
        'total_carbs': 30,
        'total_fat': 10,
      },
    };

Map<String, dynamic> plan(
        String revision, String status, List<Map<String, dynamic>> items) =>
    {
      'plan_id': 'plan-1',
      'revision_id': revision,
      'revision_number': revision == 'base' ? 1 : 2,
      'revision_content_hash': 'hash-$revision',
      'parent_revision_id': revision == 'base' ? null : 'base',
      'domain': 'NUTRITION',
      'lifecycle_status': status,
      'valid_lifecycle_targets': status == 'DRAFT'
          ? ['CANCELLED']
          : status == 'SAVED'
              ? ['ACTIVE', 'CANCELLED']
              : <String>[],
      'validation': {'status': 'READY'},
      'days': [
        {'date': '2026-09-23', 'items': items}
      ],
    };

class FakePlanApi implements BackendApiService {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  final original = plan('base', 'SAVED', [
    meal('first', 'Món đầu', 'dish-1'),
    meal('second', 'Món thay', 'dish-2'),
  ]);
  late final preview = plan('preview', 'DRAFT', [
    meal('first', 'Món thay', 'dish-2'),
    meal('second', 'Món thay', 'dish-2'),
  ]);
  Map<String, dynamic>? patch;
  String? savedRevision;
  String? savedHash;
  bool failPreview = false;

  @override
  Future<Map<String, dynamic>?> readAuthoritativePlanV2(
          {required String planId, required String revisionId}) async =>
      original;

  @override
  Future<List<Map<String, dynamic>>> listAuthoritativePlanHistory(
          String planId) async =>
      [
        original,
        if (savedRevision != null) preview,
      ];

  @override
  Future<List<Map<String, dynamic>>> listPlanChangeEvents(String planId) async =>
      savedRevision == null
          ? const []
          : [
              {
                'id': 'event-1',
                'event_type': 'REPLACE_ITEM',
                'created_at': '2026-09-23T10:00:00Z',
              }
            ];

  @override
  Future<Map<String, dynamic>> createAuthoritativePlanRevisionPreview({
    required String planId,
    required String baseRevisionId,
    required int expectedRevisionNumber,
    required String operation,
    required String actionId,
    String? targetItemId,
    Map<String, dynamic> requestedChange = const {},
    String reason = 'USER_REQUEST',
  }) async {
    patch = {
      'plan_id': planId,
      'base_revision_id': baseRevisionId,
      'expected_revision_number': expectedRevisionNumber,
      'operation': operation,
      'target_item_id': targetItemId,
      'requested_change': requestedChange,
    };
    if (failPreview)
      throw const PlanV2ApiException(
          operation: 'PATCH', code: 'PLAN_REVISION_CONFLICT');
    return {'status': 'PREVIEW_READY', 'plan': preview};
  }

  @override
  Future<Map<String, dynamic>> saveAuthoritativePlanV2({
    required String planId,
    required String revisionId,
    required String revisionContentHash,
    required String actionId,
  }) async {
    savedRevision = revisionId;
    savedHash = revisionContentHash;
    return {
      'plan': {...preview, 'lifecycle_status': 'SAVED'}
    };
  }
}

void main() {
  testWidgets(
      'typed meal replacement previews exact revision before saving and history',
      (tester) async {
    final api = FakePlanApi();
    await tester.pumpWidget(
        MaterialApp(home: PlanDetailScreen(plan: api.original, api: api)));
    await tester.pump();
    final edit = find.byKey(const ValueKey('plan-edit-replace-meal'));
    await tester.ensureVisible(edit);
    await tester.tap(edit);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('plan-edit-target')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('plan-edit-source-first')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Món thay').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('plan-edit-preview')));
    await tester.pumpAndSettle();

    expect(api.patch?['operation'], 'REPLACE_ITEM');
    expect(api.patch?['base_revision_id'], 'base');
    expect(api.patch?['expected_revision_number'], 1);
    expect(api.patch?['target_item_id'], 'first');
    final item = (api.patch?['requested_change'] as Map)['item'] as Map;
    expect(item['plan_item_id'], 'first');
    expect(item['scheduled_date'], '2026-09-23');
    expect(item['canonical_refs'], {
      'dish_id': 'dish-2',
      'food_ids': ['food-dish-2']
    });
    expect((item['content'] as Map)['dish_name'], 'Món thay');
    expect(api.savedRevision, isNull);
    expect((api.original['days'] as List).single['items'][0]['dish_name'], 'Món đầu');
    expect((api.preview['days'] as List).single['items'][1]['dish_name'], 'Món thay');

    final save = find.byKey(const ValueKey('plan-lifecycle-save'));
    expect(save, findsOneWidget);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(api.savedRevision, 'preview');
    expect(api.savedHash, 'hash-preview');
    expect(find.text('Lịch sử chỉnh sửa'), findsOneWidget);
    expect(find.textContaining('Bản 2'), findsOneWidget);
    expect(find.text('Thay đổi gần đây'), findsOneWidget);
    expect(find.textContaining('REPLACE_ITEM'), findsOneWidget);
  });

  testWidgets('failed preview keeps saved revision and does not offer save',
      (tester) async {
    final api = FakePlanApi()..failPreview = true;
    await tester.pumpWidget(
        MaterialApp(home: PlanDetailScreen(plan: api.original, api: api)));
    await tester.pump();
    await tester
        .ensureVisible(find.byKey(const ValueKey('plan-edit-replace-meal')));
    await tester.tap(find.byKey(const ValueKey('plan-edit-replace-meal')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('plan-edit-source-first')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Món thay').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('plan-edit-preview')));
    await tester.pumpAndSettle();
    expect(api.savedRevision, isNull);
    expect(find.byKey(const ValueKey('plan-lifecycle-save')), findsNothing);
    expect(find.textContaining('PLAN_REVISION_CONFLICT'), findsOneWidget);
  });

  testWidgets('combined saved Plan offers typed meal replacement',
      (tester) async {
    final api = FakePlanApi();
    final combined = {...api.original, 'domain': 'COMBINED_HEALTH'};
    await tester.pumpWidget(
      MaterialApp(home: PlanDetailScreen(plan: combined, api: api)),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('plan-edit-replace-meal')));
    expect(find.text('Thay món'), findsOneWidget);
  });
}
