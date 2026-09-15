import 'package:flutter/foundation.dart';

import '../features/plans/plan_history.dart';
import '../features/plans/plan_snapshot.dart';

typedef AuthoritativePlanLoader = Future<List<PlanSnapshot>> Function(
  String userId,
);

/// Shared, read-only projection of authoritative Plan V2 state.
///
/// Chat cards, the plan library, Home and Nutrition all consume the same
/// immutable snapshots. Updating lifecycle state replaces an exact revision;
/// it never creates a meal diary observation.
class PlanProvider with ChangeNotifier {
  final AuthoritativePlanLoader _loader;

  PlanProvider({AuthoritativePlanLoader? loader})
      : _loader = loader ?? PlanHistoryRepository().loadForUser;

  List<PlanSnapshot> _plans = const [];
  String? _loadedUserId;
  Object? _error;
  bool _isLoading = false;
  Future<List<PlanSnapshot>>? _inFlight;

  List<PlanSnapshot> get plans => _plans;
  bool get isLoading => _isLoading;
  Object? get error => _error;
  bool get hasLoaded => _loadedUserId != null && !_isLoading;

  Future<List<PlanSnapshot>> loadForUser(
    String userId, {
    bool force = false,
  }) {
    final owner = userId.trim();
    if (owner.isEmpty) {
      clear();
      return Future.value(const []);
    }
    if (!force && _loadedUserId == owner && _error == null) {
      return Future.value(plans);
    }
    if (!force && _inFlight != null && _loadedUserId == owner) {
      return _inFlight!;
    }

    if (_loadedUserId != null && _loadedUserId != owner) {
      // Owner-scoped state must never remain visible while the next account's
      // authoritative plans are loading.
      _plans = const [];
    }
    _loadedUserId = owner;
    _isLoading = true;
    _error = null;
    notifyListeners();
    final request = _load(owner);
    _inFlight = request;
    return request;
  }

  Future<List<PlanSnapshot>> refresh() {
    final owner = _loadedUserId;
    if (owner == null || owner.isEmpty) return Future.value(const []);
    return loadForUser(owner, force: true);
  }

  Future<List<PlanSnapshot>> _load(String owner) async {
    try {
      final loaded = PlanSnapshot.deduplicate(await _loader(owner));
      if (_loadedUserId == owner) {
        _plans = List.unmodifiable(loaded);
        _error = null;
      }
      return plans;
    } catch (error) {
      if (_loadedUserId == owner) _error = error;
      rethrow;
    } finally {
      if (_loadedUserId == owner) {
        _isLoading = false;
        _inFlight = null;
        notifyListeners();
      }
    }
  }

  PlannedPlanDay? dayFor({
    required String domain,
    required DateTime date,
  }) =>
      PlanHistoryResolver.forDomainAndDate(
        snapshots: _plans,
        domain: domain,
        date: date,
      );

  void upsertAuthoritativePlan(Map<String, dynamic> plan) {
    final planId = plan['plan_id']?.toString().trim() ?? '';
    final revisionId = plan['revision_id']?.toString().trim() ?? '';
    if (planId.isEmpty || revisionId.isEmpty) return;
    final updated = PlanSnapshot(
      plan: Map<String, dynamic>.from(plan),
      sessionId: 'plan-v2-authoritative',
      createdAt: DateTime.tryParse(plan['created_at']?.toString() ?? '') ??
          DateTime.now().toUtc(),
    );
    _plans = List.unmodifiable(
      PlanSnapshot.deduplicate([
        updated,
        ..._plans.where((snapshot) => snapshot.identity != updated.identity),
      ]),
    );
    notifyListeners();
  }

  void clear() {
    if (_plans.isEmpty && _loadedUserId == null && _error == null) return;
    _plans = const [];
    _loadedUserId = null;
    _error = null;
    _isLoading = false;
    _inFlight = null;
    notifyListeners();
  }
}
