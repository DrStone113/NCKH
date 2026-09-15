import '../../models/wger_models.dart';

/// A Plan V2 presentation captured with its originating chat message.
///
/// Plan V2 shadow revisions are intentionally not exposed through a separate
/// REST listing API. Chat history already persists the structured presentation,
/// so this snapshot preserves the exact plan/revision shown to the user without
/// re-parsing assistant prose or accessing Plan Engine internals.
class PlanSnapshot {
  final Map<String, dynamic> plan;
  final String sessionId;
  final DateTime createdAt;

  const PlanSnapshot({
    required this.plan,
    required this.sessionId,
    required this.createdAt,
  });

  String get planId => plan['plan_id']?.toString() ?? '';
  String get revisionId => plan['revision_id']?.toString() ?? '';
  String get lifecycle => plan['lifecycle_status']?.toString() ?? 'DRAFT';

  String get identity => '$planId/$revisionId';

  static PlanSnapshot? fromChatMessage({
    required String sessionId,
    required Map<String, dynamic> message,
  }) {
    if (message['role']?.toString() != 'assistant') return null;
    final rawStructured = message['structured'];
    if (rawStructured is! Map || rawStructured.isEmpty) return null;

    try {
      final structured = StructuredResponse.fromJson(
        Map<String, dynamic>.from(rawStructured),
      );
      final plan = structured.versionedPlan;
      final planId = plan?['plan_id']?.toString().trim() ?? '';
      final revisionId = plan?['revision_id']?.toString().trim() ?? '';
      if (plan == null || planId.isEmpty || revisionId.isEmpty) {
        return null;
      }
      return PlanSnapshot(
        plan: plan,
        sessionId: sessionId,
        createdAt: DateTime.tryParse(message['created_at']?.toString() ?? '') ??
            DateTime.fromMillisecondsSinceEpoch(0),
      );
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  static List<PlanSnapshot> deduplicate(Iterable<PlanSnapshot> snapshots) {
    final newestByIdentity = <String, PlanSnapshot>{};
    for (final snapshot in snapshots) {
      final existing = newestByIdentity[snapshot.identity];
      if (existing == null || snapshot.createdAt.isAfter(existing.createdAt)) {
        newestByIdentity[snapshot.identity] = snapshot;
      }
    }
    final result = newestByIdentity.values.toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return result;
  }
}
