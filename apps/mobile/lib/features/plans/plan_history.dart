import '../../services/backend_api_service.dart';
import 'plan_display.dart';
import 'plan_snapshot.dart';

typedef PlanSnapshotLoader = Future<List<PlanSnapshot>> Function(String userId);

/// Reads persisted Plan V2 revisions from the authoritative repository API.
/// Chat messages remain historical presentation/recovery material only; they
/// must never decide current lifecycle or active-plan state.
class PlanHistoryRepository {
  final BackendApiService _backendApi;

  PlanHistoryRepository({BackendApiService? backendApi})
      : _backendApi = backendApi ?? BackendApiService();

  Future<List<PlanSnapshot>> loadForUser(String userId) async {
    if (userId.trim().isEmpty) return const [];
    final plans = await _backendApi.listAuthoritativePlanV2();
    return plans
        .map(
          (plan) => PlanSnapshot(
            plan: plan,
            sessionId: 'plan-v2-authoritative',
            createdAt:
                DateTime.tryParse(plan['created_at']?.toString() ?? '') ??
                    DateTime.fromMillisecondsSinceEpoch(0),
          ),
        )
        .toList(growable: false);
  }
}

/// The immutable snapshot and exact day that can be displayed as planned.
class PlannedPlanDay {
  final PlanSnapshot snapshot;
  final Map<String, dynamic> day;

  const PlannedPlanDay({required this.snapshot, required this.day});
}

/// Deterministically selects the newest non-terminal plan day for a domain.
/// This is display-only: it never records a meal or workout as completed.
class PlanHistoryResolver {
  static PlannedPlanDay? forDomainAndDate({
    required Iterable<PlanSnapshot> snapshots,
    required String domain,
    required DateTime date,
  }) {
    final dayKey = _dateKey(date);
    final candidates = snapshots
        .where((snapshot) {
          final planDomain = snapshot.plan['domain']?.toString();
          return planDomain == domain || planDomain == 'COMBINED_HEALTH';
        })
        .where((snapshot) => _isOpen(snapshot.lifecycle))
        .where((snapshot) => _containsDate(snapshot.plan, dayKey))
        .toList()
      ..sort(_compareNewestFirst);

    for (final snapshot in candidates) {
      for (final day in PlanDisplay.days(snapshot.plan)) {
        if (day['date']?.toString() == dayKey) {
          if (snapshot.plan['domain']?.toString() == 'COMBINED_HEALTH') {
            final itemType = domain == 'NUTRITION' ? 'MEAL' : 'WORKOUT_SESSION';
            final items = PlanDisplay.items(day)
                .where((item) => item['item_type']?.toString() == itemType)
                .toList(growable: false);
            if (items.isEmpty) continue;
            return PlannedPlanDay(
              snapshot: snapshot,
              day: Map<String, dynamic>.from(day)..['items'] = items,
            );
          }
          return PlannedPlanDay(snapshot: snapshot, day: day);
        }
      }
    }
    return null;
  }

  static bool _isOpen(String lifecycle) =>
      !const {'CANCELLED', 'COMPLETED', 'SUPERSEDED'}.contains(lifecycle);

  static bool _containsDate(Map<String, dynamic> plan, String dayKey) {
    final start = _dateOnly(plan['period_start']);
    final end = _dateOnly(plan['period_end']);
    if (start != null && dayKey.compareTo(start) < 0) return false;
    if (end != null && dayKey.compareTo(end) > 0) return false;
    return true;
  }

  static int _compareNewestFirst(PlanSnapshot a, PlanSnapshot b) {
    final lifecycle =
        _lifecycleRank(b.lifecycle).compareTo(_lifecycleRank(a.lifecycle));
    if (lifecycle != 0) return lifecycle;

    final revision = _revisionNumber(b).compareTo(_revisionNumber(a));
    if (revision != 0) return revision;
    return b.createdAt.compareTo(a.createdAt);
  }

  static int _lifecycleRank(String lifecycle) => switch (lifecycle) {
        'ACTIVE' => 4,
        'SAVED' => 3,
        'PENDING_CONFIRMATION' => 2,
        'DRAFT' => 1,
        _ => 0,
      };

  static int _revisionNumber(PlanSnapshot snapshot) =>
      int.tryParse(snapshot.plan['revision_number']?.toString() ?? '') ?? 0;

  static String _dateKey(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

  static String? _dateOnly(Object? value) {
    final raw = value?.toString().trim() ?? '';
    if (raw.length < 10) return null;
    final candidate = raw.substring(0, 10);
    return DateTime.tryParse(candidate) == null ? null : candidate;
  }
}
