import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

import '../config/backend_endpoint_config.dart';
import '../models/app_state_value.dart';

@visibleForTesting
Future<T> retryOnceAfterUnauthorized<T>({
  required Future<T> Function(bool forceRefresh) operation,
  required bool Function(T value) isUnauthorized,
}) async {
  final first = await operation(false);
  if (!isUnauthorized(first)) return first;
  return operation(true);
}

class PlanCreationException implements Exception {
  const PlanCreationException({required this.message, this.code});

  final String message;
  final String? code;

  @override
  String toString() => message;
}

class PlanV2ApiException implements Exception {
  const PlanV2ApiException({required this.operation, required this.code});

  final String operation;
  final String code;

  @override
  String toString() => '$operation failed: $code';
}

/// Service để gọi backend API
/// Hỗ trợ cả local development và production
class BackendApiService {
  static final BackendApiService _instance = BackendApiService._internal();
  factory BackendApiService() => _instance;
  BackendApiService._internal();

  String get baseUrl => BackendEndpointConfig.baseUrl;

  final http.Client _client = http.Client();

  // The browser acceptance build may supply a short-lived test JWT via
  // --dart-define. Normal signed-in builds forward their identity token. A
  // Plan V2 route never treats a caller-supplied user id as authentication.
  static const String _planV2TestToken =
      String.fromEnvironment('PLAN_V2_TEST_TOKEN');
  // N3.2.1 development/shadow E2E uses the same owner-bound API surface as a
  // signed-in user. It is empty in normal builds and never persisted.
  static const String _n3FeedbackTestToken =
      String.fromEnvironment('N3_2_1_TEST_TOKEN');

  static bool get _usesInjectedTestToken =>
      _n3FeedbackTestToken.isNotEmpty || _planV2TestToken.isNotEmpty;

  Future<Map<String, String>> _planV2Headers(
      {bool forceRefresh = false}) async {
    final token = _n3FeedbackTestToken.isNotEmpty
        ? _n3FeedbackTestToken
        : _planV2TestToken.isNotEmpty
            ? _planV2TestToken
            : await FirebaseAuth.instance.currentUser?.getIdToken(forceRefresh);
    if (token == null || token.trim().isEmpty) {
      throw StateError('PLAN_V2_AUTHENTICATION_REQUIRED');
    }
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, String>> _authenticatedHeaders(
          {bool forceRefresh = false}) =>
      _planV2Headers(forceRefresh: forceRefresh);

  Future<http.Response> _authenticatedRequest(
    Future<http.Response> Function(Map<String, String> headers) request, {
    required Duration timeout,
  }) {
    return retryOnceAfterUnauthorized(
      operation: (forceRefresh) async => request(
        await _authenticatedHeaders(forceRefresh: forceRefresh),
      ).timeout(timeout),
      isUnauthorized: (response) =>
          response.statusCode == 401 && !_usesInjectedTestToken,
    );
  }

  Map<String, dynamic> _planV2Body(http.Response response,
      {required String operation}) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    String code = 'HTTP_${response.statusCode}';
    try {
      final decoded = json.decode(utf8.decode(response.bodyBytes));
      if (decoded is Map) {
        final detail = decoded['detail'];
        if (detail is String && detail.isNotEmpty) code = detail;
        if (detail is Map && detail['code'] != null) {
          code = detail['code'].toString();
        }
      }
    } catch (_) {
      // Keep the HTTP status as the stable fallback for malformed proxies.
    }
    throw PlanV2ApiException(operation: operation, code: code);
  }

  Future<List<Map<String, dynamic>>> listAuthoritativePlanV2(
      {String? artifactKind}) async {
    final uri = Uri.parse('$baseUrl/api/plan-v2/plans').replace(
      queryParameters:
          artifactKind == null ? null : {'artifact_kind': artifactKind},
    );
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        uri,
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    final body = _planV2Body(response, operation: 'PLAN_V2_LIST');
    final plans = body['plans'];
    if (plans is! List) return const [];
    return plans
        .whereType<Map>()
        .map((plan) => Map<String, dynamic>.from(plan))
        .toList(growable: false);
  }

  Future<Map<String, dynamic>?> readAuthoritativePlanV2({
    required String planId,
    required String revisionId,
  }) async {
    final uri = Uri.parse('$baseUrl/api/plan-v2/plans/$planId')
        .replace(queryParameters: {'revision_id': revisionId});
    final response = await _authenticatedRequest(
      (headers) => _client.get(uri, headers: headers),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode == 404) return null;
    final body = _planV2Body(response, operation: 'PLAN_V2_READ');
    final plan = body['plan'];
    return plan is Map ? Map<String, dynamic>.from(plan) : null;
  }

  Future<ActivePlanReadResult> readAuthoritativeActivePlanV2(
      String domain) async {
    try {
      final response = await _authenticatedRequest(
        (headers) => _client.get(
          Uri.parse('$baseUrl/api/plan-v2/plans/active/$domain'),
          headers: headers,
        ),
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 404) return const ActivePlanReadResult.none();
      final body = _planV2Body(response, operation: 'PLAN_V2_ACTIVE_READ');
      final plan = body['plan'];
      return plan is Map
          ? ActivePlanReadResult.found(Map<String, dynamic>.from(plan))
          : const ActivePlanReadResult.error('PLAN_V2_INVALID_RESPONSE');
    } catch (e) {
      debugPrint('Plan V2 active read failed: $e');
      return const ActivePlanReadResult.error('PLAN_V2_ACTIVE_READ_ERROR');
    }
  }

  Future<Map<String, dynamic>> saveAuthoritativePlanV2({
    required String planId,
    required String revisionId,
    required String revisionContentHash,
    required String actionId,
  }) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/plan-v2/plans/save'),
        headers: headers,
        body: jsonEncode({
          'plan_id': planId,
          'revision_id': revisionId,
          'revision_content_hash': revisionContentHash,
          'action_id': actionId,
        }),
      ),
      timeout: const Duration(seconds: 15),
    );
    return _planV2Body(response, operation: 'PLAN_V2_SAVE');
  }

  Future<Map<String, dynamic>> createAuthoritativePlanPreview({
    required String domain,
    required DateTime periodStart,
    required DateTime periodEnd,
    required String timezone,
    required Map<String, dynamic> profile,
    String? goalOverride,
    List<String> temporaryPreferences = const [],
    List<String> temporaryExclusions = const [],
    int? durationMinutes,
    int? numberOfSessions,
    String? trainingLocation,
    List<String> equipment = const [],
  }) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/plan-v2/previews'),
        headers: headers,
        body: jsonEncode({
          'domain': domain,
          'period_start': periodStart.toIso8601String().substring(0, 10),
          'period_end': periodEnd.toIso8601String().substring(0, 10),
          'timezone': timezone,
          'profile': profile,
          if (goalOverride != null) 'goal_override': goalOverride,
          'temporary_preferences': temporaryPreferences,
          'temporary_exclusions': temporaryExclusions,
          if (durationMinutes != null) 'duration_minutes': durationMinutes,
          if (numberOfSessions != null) 'number_of_sessions': numberOfSessions,
          if (trainingLocation != null) 'training_location': trainingLocation,
          'equipment': equipment,
        }),
      ),
      timeout: const Duration(seconds: 180),
    );
    return _planV2Body(response, operation: 'PLAN_V2_PREVIEW');
  }

  Future<List<Map<String, dynamic>>> listPlanChangeEvents(String planId) async {
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        Uri.parse('$baseUrl/api/plan-v2/plans/$planId/change-events'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    final body = _planV2Body(response, operation: 'PLAN_V2_CHANGE_EVENTS');
    final events = body['events'];
    if (events is! List) return const [];
    return events
        .whereType<Map>()
        .map((event) => Map<String, dynamic>.from(event))
        .toList(growable: false);
  }

  Future<List<Map<String, dynamic>>> listAuthoritativePlanHistory(
      String planId) async {
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        Uri.parse('$baseUrl/api/plan-v2/plans/$planId/history'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    final body = _planV2Body(response, operation: 'PLAN_V2_HISTORY');
    final history = body['history'];
    if (history is! List) return const [];
    return history
        .whereType<Map>()
        .map((revision) => Map<String, dynamic>.from(revision))
        .toList(growable: false);
  }

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
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/plan-v2/$planId/revisions'),
        headers: headers,
        body: jsonEncode({
          'base_revision_id': baseRevisionId,
          'expected_revision_number': expectedRevisionNumber,
          'operation': operation,
          if (targetItemId != null) 'target_item_id': targetItemId,
          'requested_change': requestedChange,
          'reason': reason,
          'action_id': actionId,
        }),
      ),
      timeout: const Duration(seconds: 15),
    );
    return _planV2Body(response, operation: 'PLAN_V2_PATCH_PREVIEW');
  }

  Future<Map<String, dynamic>> attachStandaloneToCombinedPlan({
    required String combinedPlanId,
    required String baseRevisionId,
    required String combinedContentHash,
    required String sourcePlanId,
    required String sourceRevisionId,
    required String sourceContentHash,
    required String actionId,
    required String sourceSurface,
  }) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/plan-v2/plans/$combinedPlanId/attachments'),
        headers: headers,
        body: jsonEncode({
          'base_revision_id': baseRevisionId,
          'combined_content_hash': combinedContentHash,
          'source_plan_id': sourcePlanId,
          'source_revision_id': sourceRevisionId,
          'source_content_hash': sourceContentHash,
          'action_id': actionId,
          'source_surface': sourceSurface,
        }),
      ),
      timeout: const Duration(seconds: 15),
    );
    return _planV2Body(response, operation: 'PLAN_V2_ATTACH_TRANSFER');
  }

  Future<Map<String, dynamic>> changeAuthoritativePlanV2Lifecycle({
    required String planId,
    required String revisionId,
    required int expectedRevisionNumber,
    required String operation,
    required String actionId,
    bool replaceConflicts = false,
  }) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse(
            '$baseUrl/api/plan-v2/plans/$planId/revisions/$revisionId/$operation'),
        headers: headers,
        body: jsonEncode({
          'expected_revision_number': expectedRevisionNumber,
          'action_id': actionId,
          'replace_conflicts': replaceConflicts,
        }),
      ),
      timeout: const Duration(seconds: 15),
    );
    return _planV2Body(response, operation: 'PLAN_V2_$operation');
  }

  // Cache
  List<Map<String, dynamic>>? _cachedDishes;
  List<Map<String, dynamic>>? _cachedFoods;
  DateTime? _lastDishFetch;
  DateTime? _lastFoodFetch;
  static const Duration _cacheDuration = Duration(hours: 1);

  /// Get Vietnamese dishes from backend
  Future<List<Map<String, dynamic>>> getVietnameseDishes() async {
    // Check cache first
    if (_cachedDishes != null && _lastDishFetch != null) {
      final elapsed = DateTime.now().difference(_lastDishFetch!);
      if (elapsed < _cacheDuration) {
        debugPrint('📦 BackendAPI: Returning cached dishes');
        return _cachedDishes!;
      }
    }

    try {
      debugPrint('🌐 BackendAPI: Fetching Vietnamese dishes...');
      final response = await _client
          .get(Uri.parse('$baseUrl/api/nutrition/vietnamese-dishes?limit=500'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data =
            json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
        _cachedDishes = data.map((e) => e as Map<String, dynamic>).toList();
        _lastDishFetch = DateTime.now();
        debugPrint('✅ BackendAPI: Loaded ${_cachedDishes!.length} dishes');
        return _cachedDishes!;
      } else {
        throw Exception('Failed to load dishes: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ BackendAPI: Error loading dishes: $e');
      // Return cached data if available, even if expired
      if (_cachedDishes != null) {
        debugPrint('⚠️ BackendAPI: Using expired cache');
        return _cachedDishes!;
      }
      rethrow;
    }
  }

  /// Get Vietnamese foods from backend
  Future<List<Map<String, dynamic>>> getVietnameseFoods() async {
    // Check cache first
    if (_cachedFoods != null && _lastFoodFetch != null) {
      final elapsed = DateTime.now().difference(_lastFoodFetch!);
      if (elapsed < _cacheDuration) {
        debugPrint('📦 BackendAPI: Returning cached foods');
        return _cachedFoods!;
      }
    }

    try {
      debugPrint('🌐 BackendAPI: Fetching Vietnamese foods...');
      final response = await _client
          .get(Uri.parse('$baseUrl/api/nutrition/vietnamese-foods?limit=1000'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data =
            json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
        _cachedFoods = data.map((e) => e as Map<String, dynamic>).toList();
        _lastFoodFetch = DateTime.now();
        debugPrint('✅ BackendAPI: Loaded ${_cachedFoods!.length} foods');
        return _cachedFoods!;
      } else {
        throw Exception('Failed to load foods: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ BackendAPI: Error loading foods: $e');
      // Return cached data if available, even if expired
      if (_cachedFoods != null) {
        debugPrint('⚠️ BackendAPI: Using expired cache');
        return _cachedFoods!;
      }
      rethrow;
    }
  }

  /// Search Vietnamese foods
  Future<List<Map<String, dynamic>>> searchFoods(String query) async {
    final foods = await getVietnameseFoods();
    if (query.isEmpty) return foods;

    return foods.where((food) {
      final name = (food['name'] ?? '').toString().toLowerCase();
      return name.contains(query.toLowerCase());
    }).toList();
  }

  /// Search Vietnamese dishes
  Future<List<Map<String, dynamic>>> searchDishes(String query) async {
    final dishes = await getVietnameseDishes();
    if (query.isEmpty) return dishes;

    return dishes.where((dish) {
      final name = (dish['name'] ?? '').toString().toLowerCase();
      return name.contains(query.toLowerCase());
    }).toList();
  }

  /// Get dish by ID
  Future<Map<String, dynamic>?> getDishById(String id) async {
    final dishes = await getVietnameseDishes();
    try {
      return dishes.firstWhere((dish) => dish['id']?.toString() == id);
    } catch (e) {
      return null;
    }
  }

  /// Get food by ID
  Future<Map<String, dynamic>?> getFoodById(String id) async {
    final foods = await getVietnameseFoods();
    try {
      return foods.firstWhere((food) =>
          food['food_id']?.toString() == id ||
          food['ma_so']?.toString() == id ||
          food['stt']?.toString() == id);
    } catch (e) {
      return null;
    }
  }

  /// Explicit E4.1 write. The backend independently rejects it unless
  /// WORKOUT_WRITE_MODE=explicit; this method is never called on plan render.
  Future<Map<String, dynamic>> savePersonalizedWorkoutPlan({
    required String userId,
    required String planId,
    required String requestId,
    bool activate = false,
  }) =>
      _postWorkout(
        '/workouts/plans/$planId/save',
        {
          'user_id': userId,
          'request_id': requestId,
          'activate': activate,
        },
      );

  Future<Map<String, dynamic>> logPersonalizedWorkoutResult({
    required String userId,
    required String planId,
    required String requestId,
    required String sessionCompletionStatus,
    required String painDiscomfortStatus,
    List<Map<String, dynamic>> exerciseResults = const [],
  }) =>
      _postWorkout(
        '/workouts/plans/$planId/results',
        {
          'user_id': userId,
          'request_id': requestId,
          'session_completion_status': sessionCompletionStatus,
          'pain_discomfort_status': painDiscomfortStatus,
          'exercise_results': exerciseResults,
        },
      );

  Future<Map<String, dynamic>> _postWorkout(
      String path, Map<String, dynamic> payload) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl$path'),
        headers: headers,
        body: jsonEncode(payload),
      ),
      timeout: const Duration(seconds: 15),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Workout write failed: ${response.statusCode}');
  }

  /// N3.2 development/shadow feedback only. The server refuses this endpoint
  /// outside shadow mode and it never changes the canonical recipe catalog.
  Future<Map<String, dynamic>> recordAdaptiveRecommendationFeedback({
    required String recommendationEventId,
    required String candidateId,
    required String policyVersion,
    required String idempotencyKey,
    required String eventType,
    String? reasonCode,
    String? recommendationId,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) async {
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/nutrition/adaptive/recommendations/feedback'),
        headers: {
          ...headers,
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'recommendation_event_id': recommendationEventId,
          'candidate_id': candidateId,
          'policy_version': policyVersion,
          'idempotency_key': idempotencyKey,
          'event_type': eventType,
          if (reasonCode != null) 'reason_code': reasonCode,
          if (recommendationId != null) 'recommendation_id': recommendationId,
          if (metadata.isNotEmpty) 'metadata': metadata,
        }),
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception(
        'Adaptive recommendation feedback failed: ${response.statusCode}');
  }

  /// Read only the current user's exact recommendation event after a refresh.
  /// This intentionally has no "latest recommendation" fallback.
  Future<Map<String, dynamic>> getAdaptiveRecommendationFeedbackState(
      String recommendationEventId) async {
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        Uri.parse(
            '$baseUrl/api/nutrition/adaptive/recommendations/$recommendationEventId'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception(
        'Adaptive recommendation feedback state failed: ${response.statusCode}');
  }

  /// Clear cache
  void clearCache() {
    _cachedDishes = null;
    _cachedFoods = null;
    _lastDishFetch = null;
    _lastFoodFetch = null;
    debugPrint('🗑️ BackendAPI: Cache cleared');
  }

  Future<Map<String, dynamic>> createLongTermPlan({
    required String userId,
    required Map<String, dynamic> userContext,
    required int days,
    double? targetWeight,
    String? notes,
    List<String> temporaryPreferences = const [],
    List<String> temporaryExclusions = const [],
  }) async {
    final start = DateTime.now();
    final end = start.add(Duration(days: days - 1));
    final workoutProfile = userContext['workout_profile'];
    final workout = workoutProfile is Map<String, dynamic>
        ? workoutProfile
        : const <String, dynamic>{};
    final payload = {
      'domain': 'COMBINED_HEALTH',
      'period_start': start.toIso8601String().substring(0, 10),
      'period_end': end.toIso8601String().substring(0, 10),
      'timezone': 'Asia/Ho_Chi_Minh',
      if (notes?.trim().isNotEmpty == true) 'goal_override': notes!.trim(),
      'profile': userContext,
      if (workout['available_days_per_week'] is int)
        'number_of_sessions': workout['available_days_per_week'],
      if (workout['default_session_duration_minutes'] is int)
        'duration_minutes': workout['default_session_duration_minutes'],
      if (workout['training_location'] is String)
        'training_location': workout['training_location'],
      if (workout['available_equipment'] is List)
        'equipment': workout['available_equipment'],
      'temporary_preferences': temporaryPreferences,
      'temporary_exclusions': temporaryExclusions,
    };

    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/api/plan-v2/previews'),
        headers: headers,
        body: jsonEncode(payload),
      ),
      timeout: const Duration(seconds: 180),
    );

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    String? code;
    String? message;
    try {
      final decoded = json.decode(utf8.decode(response.bodyBytes));
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is Map<String, dynamic>) {
          code = detail['code']?.toString();
          message = detail['message']?.toString();
        } else if (detail is String) {
          message = detail;
        }
      }
    } catch (_) {
      // A non-JSON proxy response still becomes a safe user-facing failure.
    }
    debugPrint(
        'BackendAPI: plan creation failed (${response.statusCode}, ${code ?? 'UNKNOWN'})');
    throw PlanCreationException(
      code: code,
      message: message?.trim().isNotEmpty == true
          ? message!.trim()
          : 'Chưa thể tạo kế hoạch lúc này. Vui lòng thử lại.',
    );
  }

  Future<Map<String, dynamic>?> getActivePlan(String userId) async {
    final result = await readAuthoritativeActivePlanV2('NUTRITION');
    if (result.status == ActivePlanStatus.activePlanFound) return result.plan;
    if (result.status == ActivePlanStatus.readError) {
      throw Exception(result.errorCode ?? 'PLAN_V2_READ_FAILED');
    }
    return null;
  }

  Future<Map<String, dynamic>?> getActivePlanDetail(String userId) async {
    final result = await readActivePlanDetail(userId);
    if (result.status == ActivePlanStatus.activePlanFound) return result.plan;
    if (result.status == ActivePlanStatus.readError) {
      throw Exception(result.errorCode ?? 'PLAN_V2_READ_FAILED');
    }
    return null;
  }

  // ignore: unused_element
  Future<Map<String, dynamic>?> _readLegacyActivePlan(
    String userId, {
    required bool detail,
  }) async {
    final suffix = detail ? '/detail' : '';
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        Uri.parse('$baseUrl/plans/$userId/active$suffix'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode == 404) return null;
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Legacy active plan read failed: ${response.statusCode}');
  }

  Future<ActivePlanReadResult> readActivePlanDetail(String userId) async {
    // Keep the parameter while callers migrate; it is intentionally never
    // sent to the authoritative API. Ownership comes from the bearer token.
    return readAuthoritativeActivePlanV2('NUTRITION');
  }

  Future<void> updatePlanItemCompletion({
    required String itemId,
    required bool completed,
  }) async {
    throw StateError('PLANNED_STATE_IMMUTABLE_USE_ACTUAL_OBSERVATION_LOG');
  }

  /// Create a plan check-in (log weight and progress)
  Future<Map<String, dynamic>> createPlanCheckin({
    required String userId,
    required String planId,
    double? weight,
    String? note,
  }) async {
    final payload = {
      'user_id': userId,
      'plan_id': planId,
      if (weight != null) 'weight': weight,
      if (note != null && note.isNotEmpty) 'note': note,
    };
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/plans/checkins'),
        headers: headers,
        body: jsonEncode(payload),
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Plan check-in failed: ${response.statusCode}');
  }

  /// Get chat sessions list for a user
  Future<List<Map<String, dynamic>>> getChatSessions({String? userId}) async {
    final uri = Uri.parse('$baseUrl/chat/sessions').replace(queryParameters: {
      if (userId != null && userId.isNotEmpty) 'user_id': userId,
    });
    final response = await _authenticatedRequest(
      (headers) => _client.get(uri, headers: headers),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final list =
          json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    }
    throw Exception('Get chat sessions failed: ${response.statusCode}');
  }

  /// Get messages for a specific session ID
  Future<List<Map<String, dynamic>>> getSessionMessages(
      String sessionId) async {
    final response = await _authenticatedRequest(
      (headers) => _client.get(
        Uri.parse('$baseUrl/chat/sessions/$sessionId/messages'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final list =
          json.decode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    }
    throw Exception('Get session messages failed: ${response.statusCode}');
  }

  /// Delete a chat session
  Future<void> deleteChatSession(String sessionId) async {
    final response = await _authenticatedRequest(
      (headers) => _client.delete(
        Uri.parse('$baseUrl/chat/sessions/$sessionId'),
        headers: headers,
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Delete chat session failed: ${response.statusCode}');
    }
  }

  /// Get active proactive check-in nudge
  Future<Map<String, dynamic>?> getActiveCheckin({
    required String userId,
    Map<String, dynamic>? userContext,
  }) async {
    final uri = Uri.parse('$baseUrl/checkin/active')
        .replace(queryParameters: {'user_id': userId});
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        uri,
        headers: headers,
        body: jsonEncode(userContext),
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty || response.body == 'null') return null;
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Get active checkin failed: ${response.statusCode}');
  }

  /// Respond to proactive check-in
  Future<Map<String, dynamic>> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    String userId = 'default_user',
  }) async {
    final payload = {
      'nudge_id': nudgeId,
      'user_id': userId,
      if (selectedOptionId != null) 'selected_option_id': selectedOptionId,
      if (responseText != null) 'response_text': responseText,
    };
    final response = await _authenticatedRequest(
      (headers) => _client.post(
        Uri.parse('$baseUrl/checkin/respond'),
        headers: headers,
        body: jsonEncode(payload),
      ),
      timeout: const Duration(seconds: 10),
    );

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Respond checkin failed: ${response.statusCode}');
  }

  /// Get check-in settings
  Future<Map<String, dynamic>> getCheckinSettings(
      {String userId = 'default_user'}) async {
    final uri = Uri.parse('$baseUrl/checkin/settings')
        .replace(queryParameters: {'user_id': userId});
    final response = await _authenticatedRequest(
      (headers) => _client.get(uri, headers: headers),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Get checkin settings failed: ${response.statusCode}');
  }

  /// Update check-in settings
  Future<Map<String, dynamic>> updateCheckinSettings(
    Map<String, dynamic> settings, {
    String userId = 'default_user',
  }) async {
    final uri = Uri.parse('$baseUrl/checkin/settings')
        .replace(queryParameters: {'user_id': userId});
    final response = await _authenticatedRequest(
      (headers) => _client.put(
        uri,
        headers: headers,
        body: jsonEncode(settings),
      ),
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return json.decode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
    }
    throw Exception('Update checkin settings failed: ${response.statusCode}');
  }

  /// Dispose
  void dispose() {
    _client.close();
  }
}
