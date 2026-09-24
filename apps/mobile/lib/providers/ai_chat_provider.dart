import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';
import '../models/user_model.dart';
import '../models/profile_readiness.dart';
import '../models/chat_message.dart';
import '../models/wger_models.dart';
import '../models/exercise_model.dart';
import '../models/meal_model.dart';
import '../models/lifestyle_model.dart';
import '../models/app_state_value.dart';
import '../models/canonical_weight.dart';
import '../constants/ai_chatbot_config.dart';
import '../services/backend_api_service.dart';
import '../services/semantic_router/semantic_router.dart';
import 'exercise_provider.dart';
import 'nutrition_provider.dart';
import 'lifestyle_provider.dart';
import 'health_provider.dart';
import 'user_provider.dart';
import '../utils/location_helper.dart';
import '../utils/meal_nutrition_utils.dart';
import '../utils/streaming_typewriter.dart';

const bool _developerTraceBuild =
    bool.fromEnvironment('CHAT_DEBUG_TRACE', defaultValue: kDebugMode);

enum ChatTransportState {
  disconnected,
  authenticating,
  connecting,
  connected,
  streaming,
  completed,
  error,
}

String chatMealDocumentId(String? requestId, String fallbackId) {
  final normalized = requestId?.trim();
  if (normalized == null || normalized.isEmpty) return fallbackId;
  return 'chat_${normalized.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_')}';
}

class AIChatProvider extends ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  final List<AIChatMessage> _messages = [];
  bool _isStreaming = false;
  ChatTransportState _transportState = ChatTransportState.disconnected;
  String _lastStreamEvent = 'none';
  String _lastStage = 'disconnected';
  String? _lastClientActionName;
  bool? _lastClientActionSucceeded;
  String? _streamingMessageId;
  String? _errorMessage;
  ProfileReadiness? _profileReadiness;
  String? _profileIssue;
  bool _checkingProfile = false;
  bool _sendingMessage = false;
  bool _pendingActionActive = false;
  String? _unsentDraft;
  String? _draftOwner;

  String? pendingDraftFor(String userId) =>
      _draftOwner == userId ? _unsentDraft : null;
  Timer? _timeoutTimer;
  Timer? _deadlineTimer;
  String? _activeTurnId;
  late final StreamingTypewriter _responseTypewriter;
  String _deferredResponseText = '';
  final _uuid = const Uuid();
  String? _sessionId;
  final BackendApiService _backendApi = BackendApiService();
  late final SemanticRouter _semanticRouter;
  double? _latitude;
  double? _longitude;
  ProfileContextScope _activeProfileScope = ProfileContextScope.general;

  AIChatProvider({
    Duration typewriterInterval = const Duration(milliseconds: 18),
    SemanticRouter? semanticRouter,
  }) {
    _semanticRouter = semanticRouter ?? SemanticRouter();
    _responseTypewriter = StreamingTypewriter(
      interval: typewriterInterval,
      onChunk: _appendTypewriterChunk,
      // Terminal `done` now finalizes immediately; animation idle has no
      // authority over conversation state.
      onIdle: () {},
    );
    initLocation();
  }

  Future<void> initLocation() async {
    try {
      final loc = await LocationHelper.getUserLocation();
      if (loc != null) {
        _latitude = loc['latitude'];
        _longitude = loc['longitude'];
        debugPrint(
            '📍 [AIChatProvider] Location cached: $_latitude, $_longitude');
      }
    } catch (e) {
      debugPrint('📍 [AIChatProvider] Error initializing location: $e');
    }
  }

  // Lưu lại context của lần gửi cuối để retry
  String? _lastMessageText;
  UserModel? _lastUser;
  double _lastTodayCalories = 0;
  int _lastTodayMealsCount = 0;
  double _lastTodayCaloriesBurned = 0;
  int _lastTodayExercisesCount = 0;
  List<Map<String, dynamic>> _lastTodayMeals = const [];
  List<Map<String, dynamic>> _lastTodayExercises = const [];

  // References to other providers for saving actions
  ExerciseProvider? _exerciseProvider;
  NutritionProvider? _nutritionProvider;
  LifestyleProvider? _lifestyleProvider;
  HealthProvider? _healthProvider;
  UserProvider? _userProvider;

  /// Callback to navigate screens in Flutter UI
  void Function(String screen)? onNavigateToScreen;

  List<AIChatMessage> get messages => List.unmodifiable(_messages);
  bool get isStreaming => _isStreaming;
  ChatTransportState get transportState => _transportState;
  String? get lastClientActionName => _lastClientActionName;
  bool? get lastClientActionSucceeded => _lastClientActionSucceeded;
  String get lastStreamEvent => _lastStreamEvent;
  String get lastStage => _lastStage;
  String? get errorMessage => _errorMessage;
  ProfileReadiness? get profileReadiness => _profileReadiness;
  String? get profileIssue {
    final current = _userProvider?.currentUser;
    if (_profileReadiness?.canSend == false &&
        current != null &&
        ProfileReadiness.assess(current).canSend) {
      return null;
    }
    return _profileIssue;
  }

  bool get isCheckingProfile => _checkingProfile;
  bool get canRetry => _lastMessageText != null && _lastUser != null;
  String? get currentSessionId => _sessionId;

  @visibleForTesting
  void setTestingTransportState(ChatTransportState state) {
    _transportState = state;
    notifyListeners();
  }

  @visibleForTesting
  static bool acceptsTurnEvent(String? activeTurnId, String? eventTurnId) {
    return eventTurnId == null || eventTurnId == activeTurnId;
  }

  @visibleForTesting
  static bool hasUsableDonePayload(Map<String, dynamic> data) {
    final fullResponse = data['full_response']?.toString() ?? '';
    return fullResponse.trim().isNotEmpty || data['structured'] is Map;
  }

  /// Set provider references for saving actions
  void setProviders({
    ExerciseProvider? exerciseProvider,
    NutritionProvider? nutritionProvider,
    LifestyleProvider? lifestyleProvider,
    HealthProvider? healthProvider,
    UserProvider? userProvider,
  }) {
    if (exerciseProvider != null) _exerciseProvider = exerciseProvider;
    if (nutritionProvider != null) _nutritionProvider = nutritionProvider;
    if (lifestyleProvider != null) _lifestyleProvider = lifestyleProvider;
    if (healthProvider != null) _healthProvider = healthProvider;
    if (userProvider != null) _userProvider = userProvider;
  }

  /// Khởi tạo với welcome message và tạo session ID mới
  void initialize() {
    _sessionId = _uuid.v4();
    debugPrint('🎬 [AIChatProvider] Initializing with session: $_sessionId');
    if (_messages.isEmpty) {
      _messages.add(AIChatMessage(
        id: _uuid.v4(),
        text:
            'Xin chào! 👋 Tôi là trợ lý sức khỏe AI.\n\nTôi có thể giúp bạn:\n• Tư vấn dinh dưỡng và thực đơn\n• Gợi ý bài tập phù hợp\n• Tính toán calo và macro\n\nHãy đặt câu hỏi!',
        isUser: false,
        isStreaming: false,
        timestamp: DateTime.now(),
      ));
      debugPrint(
          '✅ [AIChatProvider] Welcome message added. Total messages: ${_messages.length}');
      notifyListeners();
    } else {
      debugPrint(
          'ℹ️ [AIChatProvider] Already initialized. Total messages: ${_messages.length}');
    }
  }

  /// Restore the most recent non-empty server session before creating a new
  /// local session. Empty sessions are skipped because a WebSocket may have
  /// created one even though the user never sent a message.
  Future<bool> restoreLatestSession({
    required Future<List<Map<String, dynamic>>> Function() loadSessions,
    required Future<List<Map<String, dynamic>>> Function(String sessionId)
        loadMessages,
    int maxCandidates = 5,
  }) async {
    if (_messages.isNotEmpty) return true;

    final sessions = await loadSessions();
    for (final session in sessions.take(maxCandidates)) {
      if (_messages.isNotEmpty) return true;
      final sessionId = session['id']?.toString().trim() ?? '';
      if (sessionId.isEmpty) continue;

      final messages = await loadMessages(sessionId);
      if (messages.isEmpty) continue;
      if (_messages.isNotEmpty) return true;

      loadExistingSession(sessionId, messages);
      return true;
    }
    return false;
  }

  /// Start a new fresh chat session
  void startNewSession() {
    disconnect();
    _sessionId = _uuid.v4();
    _activeProfileScope = ProfileContextScope.general;
    _messages.clear();
    _errorMessage = null;
    _isStreaming = false;
    _messages.add(AIChatMessage(
      id: _uuid.v4(),
      text:
          'Xin chào! 👋 Tôi là trợ lý sức khỏe AI.\n\nTôi có thể giúp bạn:\n• Tư vấn dinh dưỡng và thực đơn\n• Gợi ý bài tập phù hợp\n• Tính toán calo và macro\n\nHãy đặt câu hỏi!',
      isUser: false,
      isStreaming: false,
      timestamp: DateTime.now(),
    ));
    debugPrint('✨ [AIChatProvider] Started new session: $_sessionId');
    notifyListeners();
  }

  /// Load an existing chat session from history
  void loadExistingSession(
      String sessionId, List<Map<String, dynamic>> rawMessages) {
    disconnect();
    _sessionId = sessionId;
    _activeProfileScope = ProfileContextScope.general;
    _messages.clear();
    _errorMessage = null;
    _isStreaming = false;

    for (final raw in rawMessages) {
      final role = raw['role'] ?? 'user';
      final isUser = role == 'user';
      final text = raw['content'] ?? '';
      PublicReasoningTrace? publicTrace;
      final rawTrace = raw['public_trace'];
      if (!isUser && rawTrace is Map) {
        publicTrace = PublicReasoningTrace.fromJson(
          Map<String, dynamic>.from(rawTrace),
        );
      }
      final timeStr = raw['created_at'];
      DateTime ts = DateTime.now();
      if (timeStr != null) {
        ts = DateTime.tryParse(timeStr.toString()) ?? DateTime.now();
      }

      StructuredResponse? structuredResponse;
      if (!isUser) {
        final rawStructured = raw['structured'];
        if (rawStructured is Map && rawStructured.isNotEmpty) {
          try {
            structuredResponse = StructuredResponse.fromJson(
              Map<String, dynamic>.from(rawStructured),
            );
          } catch (e) {
            debugPrint('❌ Invalid structured history payload: $e');
          }
        }

        // Session cũ chưa có structured_data vẫn dùng fallback để không mất
        // hoàn toàn card, nhưng dữ liệu mới luôn khôi phục payload gốc ở trên.
        structuredResponse ??= _restoreLegacyStructuredResponse(text);
      }

      _messages.add(AIChatMessage(
        id: raw['id'] ?? _uuid.v4(),
        text: text,
        isUser: isUser,
        isStreaming: false,
        timestamp: ts,
        status: MessageStatus.done,
        structuredResponse: structuredResponse,
        publicTrace: publicTrace,
      ));
    }
    debugPrint(
        '📜 [AIChatProvider] Loaded existing session: $sessionId with ${_messages.length} messages');
    notifyListeners();
  }

  StructuredResponse? _restoreLegacyStructuredResponse(String text) {
    final exMatch = RegExp(
      r'(?:lưu bài tập|ghi nhận bài tập|lưu) \*\*?(.*?)\*\*? vào nhật ký vận động',
      caseSensitive: false,
    ).firstMatch(text);
    if (exMatch != null) {
      final exName = exMatch.group(1)!.trim().replaceAll('*', '');
      if (exName.isNotEmpty) {
        final estimatedCalories = ExerciseProvider.estimateCaloriesForExercise(
          name: exName,
          categoryName: '',
          muscleCount: 0,
          weightKg: _lastUser?.weight ?? 70,
          durationMinutes: 30,
        );
        return StructuredResponse(
          type: 'structured',
          text: '',
          actions: [
            ActionItem(
              kind: 'exercise',
              wgerId: 0,
              name: exName,
              details: {
                'duration': 30,
                'duration_min': 30,
                'calories_burned': estimatedCalories,
                'calories_estimated': true,
              },
            ),
          ],
        );
      }
      return null;
    }

    final mealMatch = RegExp(
      r'(?:lưu món ăn|ghi nhận món|lưu món) \*\*?(.*?)\*\*? vào nhật ký',
      caseSensitive: false,
    ).firstMatch(text);
    if (mealMatch == null) return null;

    final dishName = mealMatch.group(1)!.trim().replaceAll('*', '');
    if (dishName.isEmpty) return null;
    final lookup = ActionItem.lookupFoodNutrition(dishName);
    return StructuredResponse(
      type: 'structured',
      text: '',
      mealName: dishName,
      actions: [
        ActionItem(
          kind: 'food',
          wgerId: 0,
          name: dishName,
          details: {
            'dish_name': dishName,
            'meal_type': 'lunch',
            'serving_grams': 100.0,
            'calories': lookup['calories'],
            'protein': lookup['protein'],
            'carbs': lookup['carbs'],
            'fat': lookup['fat'],
          },
        ),
      ],
    );
  }

  /// Kết nối WebSocket với timeout 3 giây
  Future<void> connect(String sessionId) async {
    _sessionId = sessionId;
    disconnect();
    _transportState = ChatTransportState.authenticating;
    _lastStage = 'authenticating';
    notifyListeners();

    try {
      String? firebaseToken;
      try {
        firebaseToken =
            await FirebaseAuth.instance.currentUser?.getIdToken(true);
      } on FirebaseAuthException catch (error) {
        _onError('AUTHENTICATION_REQUIRED', error.code);
        return;
      }
      final wsUrl = AIChatbotConfig.wsUrlFor(
        sessionId: sessionId,
      );
      final protocols =
          AIChatbotConfig.wsProtocolsFor(firebaseToken: firebaseToken);
      if (protocols.length < 2) {
        _onError('AUTHENTICATION_REQUIRED', 'Firebase user is unavailable');
        return;
      }
      _transportState = ChatTransportState.connecting;
      _lastStage = 'connecting';
      notifyListeners();
      debugPrint('🔌 [AIChatProvider] Connecting authenticated chat...');
      final channel = WebSocketChannel.connect(
        Uri.parse(wsUrl),
        protocols: protocols,
      );
      _channel = channel;

      // Chờ kết nối với timeout 3 giây
      await _channel!.ready.timeout(
        AIChatbotConfig.connectTimeout,
        onTimeout: () {
          debugPrint('❌ [AIChatProvider] Connection timeout');
          _onError('TIMEOUT', 'Kết nối quá lâu');
          throw TimeoutException('WebSocket connect timeout');
        },
      );

      debugPrint('✅ [AIChatProvider] Connected successfully');
      _transportState = ChatTransportState.connected;
      _lastStage = 'connected';
      notifyListeners();

      _subscription = _channel!.stream.listen(
        _handleMessage,
        onError: (error) {
          debugPrint('❌ [AIChatProvider] Stream error: $error');
          debugPrint(
              'CLIENT_WS_CLOSE_CODE=NONE CLIENT_WS_CLOSE_REASON=stream_error CLIENT_WS_READY_STATE=unknown CLIENT_LAST_EVENT=$_lastStreamEvent CLIENT_LAST_STAGE=$_lastStage');
          disconnect(); // Clear resources and set _channel = null
          _onError('CONNECTION_ERROR', error.toString());
        },
        onDone: () {
          debugPrint('🔌 [AIChatProvider] Connection closed');
          final wasStreaming = _isStreaming;
          final closeCode = channel.closeCode;
          debugPrint(
              'CLIENT_WS_CLOSE_CODE=$closeCode CLIENT_WS_CLOSE_REASON=stream_done CLIENT_WS_READY_STATE=closed CLIENT_LAST_EVENT=$_lastStreamEvent CLIENT_LAST_STAGE=$_lastStage');
          disconnect(); // Clear resources and set _channel = null
          if (wasStreaming) {
            _onError(
              closeCode == 4401
                  ? 'AUTHENTICATION_REQUIRED'
                  : 'CONNECTION_ERROR',
              closeCode == 4401
                  ? 'Phiên xác thực không hợp lệ'
                  : 'Kết nối bị ngắt',
            );
          } else if (_sessionId != null) {
            // A normal close after a terminal turn must not strand the
            // composer. Reconnect with fresh auth before the next send.
            unawaited(connect(_sessionId!));
          }
        },
      );
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Connection failed: $e');
      _channel = null;
      if (e is! TimeoutException) {
        _onError('CONNECTION_ERROR', e.toString());
      }
    }
  }

  /// Gửi lại tin nhắn cuối cùng khi có lỗi
  Future<void> retryLastMessage() async {
    if (_lastMessageText == null || _lastUser == null) return;

    await sendMessage(
      _lastMessageText!,
      _lastUser!,
      todayCalories: _lastTodayCalories,
      todayMealsCount: _lastTodayMealsCount,
      todayCaloriesBurned: _lastTodayCaloriesBurned,
      todayExercisesCount: _lastTodayExercisesCount,
      todayMeals: _lastTodayMeals,
      todayExercises: _lastTodayExercises,
      replaceLastAttempt: true,
    );
  }

  /// Gửi tin nhắn người dùng và tạo streaming placeholder
  Future<bool> sendMessage(
    String text,
    UserModel user, {
    double todayCalories = 0,
    int todayMealsCount = 0,
    double todayCaloriesBurned = 0,
    int todayExercisesCount = 0,
    List<Map<String, dynamic>> todayMeals = const [],
    List<Map<String, dynamic>> todayExercises = const [],
    List<Map<String, dynamic>> exerciseHistory = const [],
    String exerciseHistoryStatus = 'NOT_LOADED',
    DateTime? exerciseHistoryObservedAt,
    bool replaceLastAttempt = false,
  }) async {
    if (_checkingProfile || _isStreaming || _sendingMessage) return false;
    _sendingMessage = true;
    _unsentDraft = text;
    _draftOwner = user.id;
    try {
      final profileScope = _scopeForMessage(text);
      final currentProfile = await checkProfileBeforeSend(
        text,
        user,
        scope: profileScope,
      );
      if (currentProfile == null) return false;
      user = currentProfile;
      _activeProfileScope = profileScope;

      // Lưu context để có thể retry
      _lastMessageText = text;
      _lastUser = user;
      _lastTodayCalories = todayCalories;
      _lastTodayMealsCount = todayMealsCount;
      _lastTodayCaloriesBurned = todayCaloriesBurned;
      _lastTodayExercisesCount = todayExercisesCount;
      _lastTodayMeals = todayMeals;
      _lastTodayExercises = todayExercises;

      if (_channel == null) {
        debugPrint('🔌 [AIChatProvider] No connection, connecting...');
        await connect(_sessionId ?? _uuid.v4());
        if (_channel == null) return false;
      }

      if (_userProvider?.currentUser?.id != user.id) return false;
      if (replaceLastAttempt) {
        final lastUserIdx =
            _messages.lastIndexWhere((message) => message.isUser);
        if (lastUserIdx != -1) {
          _messages.removeRange(lastUserIdx, _messages.length);
        }
      }

      // 1. Thêm user message vào list
      _messages.add(AIChatMessage(
        id: _uuid.v4(),
        text: text,
        isUser: true,
        isStreaming: false,
        timestamp: DateTime.now(),
      ));

      // 2. Tạo streaming message placeholder — status: thinking
      final semanticTurnId = _uuid.v4();
      _activeTurnId = semanticTurnId;
      _responseTypewriter.clear();
      _deferredResponseText = '';
      final streamingId = _uuid.v4();
      _streamingMessageId = streamingId;
      _isStreaming = true;
      _transportState = ChatTransportState.streaming;
      _errorMessage = null;
      _messages.add(AIChatMessage(
        id: streamingId,
        text: '',
        isUser: false,
        isStreaming: true,
        status: MessageStatus.thinking,
        timestamp: DateTime.now(),
      ));
      notifyListeners();

      // Public trace/status do not satisfy this first-answer deadline.
      _timeoutTimer?.cancel();
      _timeoutTimer = Timer(AIChatbotConfig.firstResponseTimeout, () {
        debugPrint('⏰ [AIChatProvider] Stream timeout');
        _onError('TIMEOUT', 'Phản hồi quá lâu');
      });

      // 3. Gửi ChatRequest JSON qua WebSocket kèm user_context phong phú
      _deadlineTimer?.cancel();
      _deadlineTimer = Timer(AIChatbotConfig.streamTimeout, () {
        _onError('TIMEOUT', 'Phản hồi quá lâu');
      });

      final canonicalNutrition = user.canonicalNutrition;
      final dailyNutritionSummary =
          _nutritionProvider?.canonicalDailySummary(canonicalNutrition);
      final calculationFormulaIds = <String>{
        ...canonicalNutrition.formulaIds,
        ...?dailyNutritionSummary?.formulaIds,
      }.toList(growable: false);
      final Map<String, dynamic> userContext = {
        'user_id': user.id,
        'name': user.name,
        'profile_readiness': _profileReadiness!.toJson(),
        // Shared general values are a compact typed view of the authoritative
        // user root. They are available to both domain flows without injecting
        // the full HealthProfile envelope.
        'general_profile': user.generalProfile.toJson(),
        'age': user.age,
        'gender': user.gender,
        'equation_sex': user.equationSex,
        'nutrition_safety_profile': user.nutritionSafetyProfile.toJson(),
        'nutrition_profile': user.effectiveNutritionProfile?.toJson(),
        'dietary_restrictions':
            user.effectiveNutritionProfile?.canonicalDietaryRestrictions,
        'height': user.height,
        'weight': user.weight,
        'target_weight': user.targetWeight,
        'activity_level': user.activityLevel,
        'health_goal': user.healthGoal,
        'bmi': canonicalNutrition.bmi,
        'bmi_category': user.bmiCategory,
        'bmr': user.bmr,
        'tdee': user.tdee,
        'recommended_calories': user.recommendedCalories,
        'daily_water_goal': user.dailyWaterGoal,
        'daily_nutrition_summary': dailyNutritionSummary?.toJson(),
        'today_calories_consumed': todayCalories,
        'today_meals_count': todayMealsCount,
        'today_calories_burned': todayCaloriesBurned,
        'today_exercises_count': todayExercisesCount,
        'today_meals': todayMeals,
        'today_exercises': todayExercises,
        // E4.1 fields are separate from the frozen nutrition state manifest.
        // A caller supplies legacy history only after a Firestore server read.
        'workout_profile': user.effectiveWorkoutProfile?.toJson(),
        'training_state': {
          'workout_profile_present': user.effectiveWorkoutProfile != null,
          'exercise_history_status': exerciseHistoryStatus,
          'exercise_history_observed_at':
              exerciseHistoryObservedAt?.toUtc().toIso8601String(),
        },
        'exercise_history': exerciseHistory,
        'exercise_history_status': exerciseHistoryStatus,
        'exercise_history_loaded': exerciseHistoryStatus == 'KNOWN',
        'exercise_history_observed_at':
            exerciseHistoryObservedAt?.toUtc().toIso8601String(),
        'state_manifest': _buildSendTimeStateManifest(
          user,
          todayCalories: todayCalories,
          todayMealsCount: todayMealsCount,
          todayCaloriesBurned: todayCaloriesBurned,
          todayExercisesCount: todayExercisesCount,
          todayMeals: todayMeals,
          todayExercises: todayExercises,
        ),
        'calculation_manifest': {
          'policy_version': canonicalNutrition.policyVersion,
          'formula_ids': calculationFormulaIds,
          'formula_provenance': calculationFormulaIds
              .map((id) => {
                    'formula_id': id,
                    'policy_version': canonicalNutrition.policyVersion,
                  })
              .toList(growable: false),
          'inputs': {
            'weight_kg': user.weight,
            'height_cm': user.height,
            'age': user.age,
            'equation_sex': user.equationSex,
            'nutrition_safety_profile': user.nutritionSafetyProfile.toJson(),
            'activity_level': user.activityLevel,
            'health_goal': user.healthGoal,
          },
          'outputs': {
            ...canonicalNutrition.toJson(),
            'daily_nutrition_summary': dailyNutritionSummary?.toJson(),
          },
        },
      };

      // Only attach the profile domain needed by this turn. This prevents an
      // unrelated nutrition request from repeatedly exposing workout/safety
      // details (and vice versa) while retaining the exact safety data needed by
      // each deterministic policy.
      userContext['profile_context_domains'] = switch (profileScope) {
        ProfileContextScope.nutrition => const [
            'general',
            'nutrition',
            'nutrition_safety',
            'canonical_nutrition'
          ],
        ProfileContextScope.workout => const [
            'general',
            'workout',
            'exercise_safety',
            'training_state'
          ],
        ProfileContextScope.both => const [
            'general',
            'nutrition',
            'nutrition_safety',
            'canonical_nutrition',
            'workout',
            'exercise_safety',
            'training_state'
          ],
        ProfileContextScope.general => const ['general'],
      };

      // `state_manifest` is a mixed send-time snapshot. Prune it alongside the
      // top-level payload so a nutrition turn never receives exercise details
      // and a workout turn never receives meal/nutrition details by accident.
      void pruneStateManifest(Iterable<String> keys) {
        final raw = userContext['state_manifest'];
        if (raw is! Map) return;
        final scoped = Map<String, dynamic>.from(raw);
        for (final key in keys) {
          scoped.remove(key);
        }
        userContext['state_manifest'] = scoped;
      }

      switch (profileScope) {
        case ProfileContextScope.nutrition:
          for (final key in const [
            'workout_profile',
            'training_state',
            'exercise_history',
            'exercise_history_status',
            'exercise_history_loaded',
            'exercise_history_observed_at',
            'today_calories_burned',
            'today_exercises_count',
            'today_exercises',
          ]) {
            userContext.remove(key);
          }
          pruneStateManifest(const [
            'today.calories_burned',
            'today.exercise_count',
            'today.exercises',
          ]);
        case ProfileContextScope.workout:
          for (final key in const [
            'nutrition_profile',
            'dietary_restrictions',
            'nutrition_safety_profile',
            'daily_nutrition_summary',
            'today_calories_consumed',
            'today_meals_count',
            'today_meals',
            'calculation_manifest',
            'bmi',
            'bmi_category',
            'bmr',
            'tdee',
            'recommended_calories',
            'daily_water_goal',
          ]) {
            userContext.remove(key);
          }
          pruneStateManifest(const [
            'today.calories_consumed',
            'today.consumed_meal_count',
            'today.meals',
            'water_target',
            'water_consumed_today',
          ]);
        case ProfileContextScope.general:
          for (final key in const [
            'nutrition_profile',
            'dietary_restrictions',
            'nutrition_safety_profile',
            'daily_nutrition_summary',
            'workout_profile',
            'training_state',
            'exercise_history',
            'exercise_history_status',
            'exercise_history_loaded',
            'exercise_history_observed_at',
            'today_calories_consumed',
            'today_meals_count',
            'today_meals',
            'today_calories_burned',
            'today_exercises_count',
            'today_exercises',
            'calculation_manifest',
          ]) {
            userContext.remove(key);
          }
        case ProfileContextScope.both:
          break;
      }

      if (user.id == 'demo') {
        for (final key in const [
          'age',
          'general_profile',
          'gender',
          'equation_sex',
          'nutrition_safety_profile',
          'height',
          'weight',
          'target_weight',
          'activity_level',
          'health_goal',
          'bmi',
          'bmi_category',
          'bmr',
          'tdee',
          'recommended_calories',
          'daily_water_goal',
        ]) {
          userContext.remove(key);
        }
        userContext['calculation_manifest'] = {
          'inputs': <String, Object?>{},
          'outputs': <String, Object?>{},
          'formula_provenance': <Object?>[],
        };
      }

      final Map<String, dynamic> request = {
        'type': 'chat',
        'session_id': _sessionId,
        'user_id': user.id,
        'message': text,
        'user_context': userContext,
      };
      request['turn_id'] = semanticTurnId;
      if (_latitude != null && _longitude != null) {
        request['latitude'] = _latitude;
        request['longitude'] = _longitude;
      }

      try {
        debugPrint('📡 [AIChatProvider] Sending chat request');
        _channel!.sink.add(jsonEncode(request));
        _unsentDraft = null;
        debugPrint('✅ [AIChatProvider] Request sent');
        // Shadow analysis never delays or mutates the authoritative chat turn.
        // Its sanitized result travels in a separate non-routing message.
        unawaited(_runSemanticShadow(
          rawText: text,
          turnId: semanticTurnId,
          pendingActionActive: _pendingActionActive,
        ));
        return true;
      } catch (e) {
        debugPrint('❌ [AIChatProvider] Send error: $e');
        _onError('CONNECTION_ERROR', e.toString());
        return false;
      }
    } finally {
      _sendingMessage = false;
    }
  }

  /// Validate the current owner and authoritative profile before any chat send.
  /// Supplemental gaps travel with the scoped context so the bot can ask only
  /// what it needs. They never become assumed negative safety answers.
  Future<UserModel?> checkProfileBeforeSend(
    String text,
    UserModel supplied, {
    ProfileContextScope? scope,
  }) async {
    _checkingProfile = true;
    _profileIssue = null;
    _profileReadiness = null;
    notifyListeners();
    try {
      final provider = _userProvider;
      if (provider == null || provider.currentUser?.id != supplied.id) {
        _profileIssue =
            'Chưa xác định được hồ sơ hiện tại. Vui lòng đăng nhập lại.';
        return null;
      }
      if (supplied.id != 'demo' && !await provider.refreshCurrentUser()) {
        _profileIssue =
            'Chưa đọc được hồ sơ mới nhất. Kiểm tra kết nối rồi thử lại.';
        return null;
      }
      final current = provider.currentUser;
      if (current == null || current.id != supplied.id) {
        _profileIssue =
            'Tài khoản đã thay đổi. Vui lòng gửi lại từ tài khoản hiện tại.';
        return null;
      }
      _profileReadiness = ProfileReadiness.assess(
        current,
        scope: scope ?? _scopeForMessage(text),
      );
      if (!_profileReadiness!.canSend) {
        _profileIssue =
            'Cần bổ sung: ${_profileReadiness!.requiredFields.values.join(', ')}.';
        return null;
      }
      return current;
    } catch (_) {
      _profileIssue = 'Chưa kiểm tra được hồ sơ. Vui lòng thử lại.';
      return null;
    } finally {
      _checkingProfile = false;
      notifyListeners();
    }
  }

  /// Xử lý message nhận từ WebSocket
  void _handleMessage(dynamic raw) {
    try {
      final data = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = data['type'] as String?;
      final eventTurnId = data['turn_id']?.toString();
      if (!acceptsTurnEvent(_activeTurnId, eventTurnId)) {
        debugPrint(
            'Ignoring stale chat event for turn $eventTurnId; active=$_activeTurnId');
        return;
      }

      debugPrint('📦 [AIChatProvider] Message type: $type');

      switch (type) {
        case 'token':
          _lastStreamEvent = 'token';
          _lastStage = 'streaming';
          _onTokenReceived(data['content'] as String? ?? '');
          break;
        case 'thought':
          // Legacy/raw reasoning is intentionally ignored. It must never be
          // added to a message, history, or developer panel.
          break;
        case 'public_trace':
          _onPublicTraceReceived(data['trace']);
          break;
        case 'debug_trace':
          if (_developerTraceBuild) {
            _onDebugTraceReceived(data['event']);
          }
          break;
        case 'action_state':
          // Human-readable state is already reflected by the final assistant
          // response; keep it as a stream heartbeat, never as raw tool data.
          _onActionStateReceived(data['state']);
          break;
        case 'status':
          _onStatusReceived();
          break;
        case 'done':
          _lastStreamEvent = 'done';
          _lastStage = 'completed';
          debugPrint('✅ [AIChatProvider] Stream done');
          _onStreamDone(data);
          break;
        case 'error':
          _lastStreamEvent = 'error';
          _lastStage = 'error';
          _onError(data['code'] as String? ?? 'ERROR',
              data['message'] as String? ?? 'Lỗi không xác định');
          break;
        case 'tool_call':
          _lastStreamEvent = 'tool_call';
          _lastStage = 'client_action';
          _resetTimeoutTimer();
          _handleToolCall(data);
          break;
        default:
          debugPrint('⚠️ [AIChatProvider] Unknown message type: $type');
      }
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Parse error: $e');
      if (_isStreaming) {
        _onError('BAD_RESPONSE', 'Phản hồi từ server không hợp lệ');
      }
    }
  }

  void _onActionStateReceived(dynamic rawState) {
    if (rawState is Map) {
      final status = rawState['status']?.toString();
      _pendingActionActive = status == 'PENDING_CONFIRMATION' ||
          status == 'IN_PROGRESS' ||
          status == 'CLARIFICATION_REQUIRED';
    }
    _onStatusReceived();
  }

  Future<void> _runSemanticShadow({
    required String rawText,
    required String turnId,
    required bool pendingActionActive,
  }) async {
    final observation = await _semanticRouter.analyze(
      rawText,
      pendingActionActive: pendingActionActive,
      recentReferenceKind: _recentVisibleReferenceKind(),
    );
    if (observation.mode.name == 'off') return;
    debugPrint(
      '🧭 [SemanticRouter] ${observation.reasonCode}; '
      'slm=${observation.slmInvoked}; rawLength=${observation.rawLength}',
    );
    final channel = _channel;
    if (channel == null) return;
    try {
      channel.sink.add(jsonEncode({
        'type': 'semantic_shadow',
        'session_id': _sessionId,
        'turn_id': turnId,
        'observation': observation.toTelemetryJson(),
      }));
    } catch (_) {
      // Telemetry is fail-open and must never fail the user chat path.
    }
  }

  String? _recentVisibleReferenceKind() {
    for (final message in _messages.reversed) {
      if (message.isUser) continue;
      final structured = message.structuredResponse;
      if (structured != null) return structured.type;
    }
    return null;
  }

  /// Xử lý Tool Call từ Backend
  Future<void> _handleToolCall(Map<String, dynamic> data) async {
    _resetTimeoutTimer();
    final correlationId = data['correlation_id'] as String?;
    final name = data['name'] as String?;
    final args = data['arguments'] as Map<String, dynamic>? ?? {};

    if (correlationId == null || name == null) {
      debugPrint('❌ [AIChatProvider] Invalid tool_call format');
      return;
    }

    _lastClientActionName = name;
    _lastClientActionSucceeded = null;
    notifyListeners();

    // Client action RPC is transport-only. Do not log its implementation name
    // or arguments into Flutter diagnostics / user-visible trace surfaces.

    Map<String, dynamic> resultData = {};
    Map<String, dynamic>? uiMessage;
    bool isOk = true;
    String? error;

    switch (name) {
      case 'get_user_profile':
        final profileRead = await _userProvider?.refreshCurrentUser() ?? false;
        final profile = _userProvider?.currentUser ?? _lastUser;
        final historyRead = profile == null
            ? false
            : await _healthProvider?.loadWeightHistory(profile.id) ?? false;
        if (profile?.id == 'demo') {
          resultData = {
            'read_status': 'NOT_LOADED',
            'state': {
              'profile': const AppStateValue<Object?>(
                value: null,
                source: 'demo_ui_defaults',
                observedAt: null,
                status: DataStatus.notLoaded,
              ).toJson(),
              'current_weight': const AppStateValue<double>(
                value: null,
                source: 'demo_ui_defaults',
                observedAt: null,
                status: DataStatus.notLoaded,
              ).toJson(),
            },
          };
          break;
        }
        if (profile != null) {
          _lastUser = profile;
          final latest =
              historyRead && _healthProvider!.weightHistory.isNotEmpty
                  ? _healthProvider!.weightHistory.last
                  : null;
          var canonicalWeight = CanonicalWeightResolver.resolve(
            profileWeight: profile.id != 'demo' &&
                    profile.weight >= 30 &&
                    profile.weight <= 300
                ? profile.weight
                : null,
            latestMeasurement: latest,
          );
          if (!historyRead) {
            final validProfileWeight =
                profile.weight >= 30 && profile.weight <= 300;
            canonicalWeight = AppStateValue<double>(
              value: validProfileWeight ? profile.weight : null,
              source: profileRead
                  ? 'profile.current_weight'
                  : 'send_time_profile_snapshot',
              observedAt: null,
              status: validProfileWeight
                  ? (profileRead ? DataStatus.error : DataStatus.stale)
                  : DataStatus.missing,
            );
          }
          final effectiveProfile = canonicalWeight.value == null
              ? profile
              : profile.copyWith(weight: canonicalWeight.value);
          final canonicalNutrition = effectiveProfile.canonicalNutrition;
          resultData = {
            'read_status': profileRead && historyRead
                ? 'CURRENT'
                : profileRead
                    ? 'PARTIAL'
                    : 'STALE_SNAPSHOT',
            'user_id': profile.id,
            'id': profile.id,
            'name': profile.name,
            'profile_readiness': ProfileReadiness.assess(
              effectiveProfile,
              scope: _activeProfileScope,
            ).toJson(),
            'general_profile': effectiveProfile.generalProfile.toJson(),
            'age': profile.age,
            'gender': profile.gender,
            'equation_sex': profile.equationSex,
            'nutrition_safety_profile': profile.nutritionSafetyProfile.toJson(),
            'nutrition_profile': profile.effectiveNutritionProfile?.toJson(),
            'dietary_restrictions':
                profile.effectiveNutritionProfile?.canonicalDietaryRestrictions,
            'height': profile.height,
            'weight': canonicalWeight.value,
            'profile_weight': profile.weight,
            'target_weight': profile.targetWeight,
            'activity_level': profile.activityLevel,
            'health_goal': profile.healthGoal,
            'workout_profile': profile.effectiveWorkoutProfile?.toJson(),
            'training_state': {
              'workout_profile_present':
                  profile.effectiveWorkoutProfile != null,
              'exercise_history_status': historyRead ? 'KNOWN' : 'NOT_LOADED',
            },
            'bmi': canonicalNutrition.bmi,
            'bmi_category': canonicalNutrition.bmiClassification,
            'bmr': canonicalNutrition.estimatedRmrKcalPerDay,
            'tdee': canonicalNutrition.estimatedTdeeKcalPerDay,
            'recommended_calories': canonicalNutrition.calorieTargetKcalPerDay,
            'daily_water_goal':
                canonicalNutrition.approximateFluidGoalMlPerDay == null
                    ? null
                    : canonicalNutrition.approximateFluidGoalMlPerDay! / 1000,
            'canonical_nutrition': canonicalNutrition.toJson(),
            'state': {
              'current_weight': canonicalWeight.toJson(),
              'profile': AppStateValue<Map<String, Object?>>(
                value: {'age': profile.age, 'height_cm': profile.height},
                source: profileRead
                    ? 'firestore.users'
                    : 'send_time_profile_snapshot',
                observedAt: null,
                status: profileRead ? DataStatus.known : DataStatus.stale,
              ).toJson(),
            },
          };
          switch (_activeProfileScope) {
            case ProfileContextScope.nutrition:
              resultData.remove('workout_profile');
              resultData.remove('training_state');
            case ProfileContextScope.workout:
              for (final key in const [
                'nutrition_safety_profile',
                'nutrition_profile',
                'dietary_restrictions',
                'bmi',
                'bmi_category',
                'bmr',
                'tdee',
                'recommended_calories',
                'daily_water_goal',
                'canonical_nutrition',
              ]) {
                resultData.remove(key);
              }
            case ProfileContextScope.general:
              for (final key in const [
                'nutrition_safety_profile',
                'nutrition_profile',
                'dietary_restrictions',
                'workout_profile',
                'training_state',
                'bmi',
                'bmi_category',
                'bmr',
                'tdee',
                'recommended_calories',
                'daily_water_goal',
                'canonical_nutrition',
              ]) {
                resultData.remove(key);
              }
            case ProfileContextScope.both:
              break;
          }
          resultData['profile_context_domains'] = switch (_activeProfileScope) {
            ProfileContextScope.nutrition => const [
                'general',
                'nutrition',
                'nutrition_safety',
                'canonical_nutrition'
              ],
            ProfileContextScope.workout => const [
                'general',
                'workout',
                'exercise_safety',
                'training_state'
              ],
            ProfileContextScope.both => const [
                'general',
                'nutrition',
                'nutrition_safety',
                'canonical_nutrition',
                'workout',
                'exercise_safety',
                'training_state'
              ],
            ProfileContextScope.general => const ['general'],
          };
        } else {
          isOk = false;
          error = 'READ_ERROR';
          resultData = {
            'read_status': 'READ_ERROR',
            'state': {
              'profile': const AppStateValue<Object?>(
                value: null,
                source: 'firestore.users',
                observedAt: null,
                status: DataStatus.notLoaded,
              ).toJson(),
            },
          };
        }
        break;
      case 'update_nutrition_profile':
        final rawPatch = args['patch'];
        final patch = rawPatch is Map
            ? Map<String, dynamic>.from(rawPatch)
            : <String, dynamic>{};
        if (_userProvider == null) {
          isOk = false;
          error = 'WRITE_REJECTED';
          resultData = const WriteResult<Object?>.rejected(
            'NUTRITION_PROFILE_CONTEXT_UNAVAILABLE',
          ).toJson();
          break;
        }
        final nutritionWrite =
            await _userProvider!.updateNutritionProfileFromChat(patch);
        if (!nutritionWrite.isPersisted || nutritionWrite.value == null) {
          isOk = false;
          error = nutritionWrite.status == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = nutritionWrite.toJson();
          break;
        }
        _lastUser = _userProvider!.currentUser ?? _lastUser;
        resultData = {
          ...nutritionWrite.toJson(),
          'nutrition_profile': nutritionWrite.value!.toJson(),
        };
        break;
      case 'update_workout_profile':
        final mode = args['mode'] as String?;
        final rawPatch = args['patch'];
        final patch = rawPatch is Map
            ? Map<String, dynamic>.from(rawPatch)
            : <String, dynamic>{};
        if (mode == null || _userProvider == null) {
          isOk = false;
          error = 'WRITE_REJECTED';
          resultData = const WriteResult<Object?>.rejected(
            'WORKOUT_PROFILE_CONTEXT_UNAVAILABLE',
          ).toJson();
          break;
        }
        final profileWrite = await _userProvider!.updateWorkoutProfileFromChat(
          patch,
          mode: mode,
        );
        if (!profileWrite.isPersisted || profileWrite.value == null) {
          isOk = false;
          error = profileWrite.status == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = profileWrite.toJson();
          break;
        }
        final stored = profileWrite.value!;
        _lastUser = _userProvider!.currentUser ?? _lastUser;
        resultData = {
          ...profileWrite.toJson(),
          'workout_profile': stored.toJson(),
          'intake_confirmation_status': stored.intakeConfirmationStatus,
          'intake_revision': stored.intakeRevision,
        };
        break;
      case 'get_today_meals':
        final user = _userProvider?.currentUser ?? _lastUser;
        final provider = _nutritionProvider;
        final fresh = user != null && provider != null
            ? await provider.refreshTodayMealsAuthoritatively(user.id)
            : false;
        if (!fresh) {
          isOk = false;
          error = 'READ_ERROR';
          resultData = {
            'read_status': 'READ_ERROR',
            'state': {
              'today_meals': AppStateValue<List<Map<String, dynamic>>>(
                value: _lastTodayMeals,
                source: 'send_time_meal_snapshot',
                observedAt: provider?.todayMealsObservedAt,
                status: DataStatus.stale,
              ).toJson(),
            },
          };
        } else {
          final meals = _serializeTodayMeals(provider.todayMeals);
          _lastTodayMeals = meals;
          _lastTodayCalories = provider.consumedCalories;
          _lastTodayMealsCount = provider.completedMealsCount;
          resultData = _todayMealsResult(provider, meals);
        }
        break;
      case 'get_today_exercises':
        final user = _userProvider?.currentUser ?? _lastUser;
        final provider = _exerciseProvider;
        final fresh = user != null && provider != null
            ? await provider.refreshTodayExercisesAuthoritatively(user.id)
            : false;
        if (!fresh) {
          isOk = false;
          error = 'READ_ERROR';
          resultData = {
            'read_status': 'READ_ERROR',
            'state': {
              'today_exercises': AppStateValue<List<Map<String, dynamic>>>(
                value: _lastTodayExercises,
                source: 'send_time_exercise_snapshot',
                observedAt: provider?.todayExercisesObservedAt,
                status: DataStatus.stale,
              ).toJson(),
            },
          };
        } else {
          final exercises = _serializeTodayExercises(provider.todayExercises);
          _lastTodayExercises = exercises;
          _lastTodayCaloriesBurned = provider.totalCaloriesBurned;
          _lastTodayExercisesCount = provider.todayExercises.length;
          resultData = _todayExercisesResult(provider, exercises);
        }
        break;
      case 'log_meal':
        final dishName = args['dish_name'] as String? ?? 'Món ăn';
        final mealTypeRaw = args['meal_type'] as String? ?? 'lunch';
        final mealType = _mapMealType(mealTypeRaw);
        final catalogDishId = args['catalog_dish_id']?.toString().trim();
        final requestedGrams = _positiveDouble(args['serving_grams']);
        final grams = requestedGrams ?? 100.0;

        final List<ActionItem> actions = [];
        final rawComponents = args['components'];
        if (rawComponents is List) {
          final comps = rawComponents;
          for (final comp in comps) {
            if (comp is Map) {
              final data = Map<String, dynamic>.from(comp);
              final compName = data['name']?.toString().trim();
              if (compName == null || compName.isEmpty) continue;
              final gramsDouble = _positiveDouble(
                    data['serving_grams'] ?? data['grams'],
                  ) ??
                  100;
              final compCal = _nonNegativeDouble(data['calories']);
              final compPro = _nonNegativeDouble(data['protein']);
              final compCarbs = _nonNegativeDouble(data['carbs']);
              final compFat = _nonNegativeDouble(data['fat']);

              final double cal100g =
                  gramsDouble > 0 ? (compCal * 100.0 / gramsDouble) : 0.0;
              final double pro100g =
                  gramsDouble > 0 ? (compPro * 100.0 / gramsDouble) : 0.0;
              final double carb100g =
                  gramsDouble > 0 ? (compCarbs * 100.0 / gramsDouble) : 0.0;
              final double fat100g =
                  gramsDouble > 0 ? (compFat * 100.0 / gramsDouble) : 0.0;

              actions.add(ActionItem(
                kind: 'food',
                wgerId: 0,
                name: compName,
                details: {
                  'dish_name': dishName,
                  'meal_type': mealType,
                  'serving_grams': gramsDouble,
                  'calories': cal100g,
                  'protein': pro100g,
                  'carbs': carb100g,
                  'fat': fat100g,
                },
              ));
            }
          }
        }

        // Nếu model thiếu components, dùng chính catalog của sheet "Thêm món
        // ăn". Fallback cũ chỉ dò từ khoá đầu tiên (ví dụ "cơm") nên kcal và
        // thành phần trong chatbot có thể khác hoàn toàn màn Dinh dưỡng.
        if (actions.isEmpty && _nutritionProvider != null) {
          await _nutritionProvider!.loadVietnameseDatabase();
          final catalogDish = _nutritionProvider!.findVietnameseDish(dishName);
          if (catalogDish != null) {
            final resolved = MealNutritionUtils.resolveDish(
              catalogDish,
              _nutritionProvider!.vietnameseFoods,
            );
            final baseGrams = resolved.items.fold<double>(
              0,
              (sum, item) => sum + item.weightGrams,
            );
            final portionScale = requestedGrams != null && baseGrams > 0
                ? requestedGrams / baseGrams
                : 1.0;
            for (final item in resolved.items) {
              final itemGrams = item.weightGrams * portionScale;
              if (itemGrams <= 0 || item.weightGrams <= 0) continue;
              actions.add(
                ActionItem(
                  kind: 'food',
                  wgerId: 0,
                  name: item.name,
                  details: {
                    'dish_name': dishName,
                    'meal_type': mealType,
                    'serving_grams': itemGrams,
                    'calories': item.calories * 100 / item.weightGrams,
                    'protein': item.protein * 100 / item.weightGrams,
                    'carbs': item.carbs * 100 / item.weightGrams,
                    'fat': item.fat * 100 / item.weightGrams,
                    'nutrition_source': 'vietnamese_catalog',
                  },
                ),
              );
            }
          }
        }

        if (actions.isEmpty) {
          final cleanName = dishName.toLowerCase().trim();
          String? matchedRecipeKey;
          for (final key in ActionItem.compoundRecipes.keys) {
            if (cleanName.contains(key)) {
              matchedRecipeKey = key;
              break;
            }
          }

          if (matchedRecipeKey != null) {
            final recipe = ActionItem.compoundRecipes[matchedRecipeKey]!;
            recipe.forEach((ingredientName, ratio) {
              final ingredientGrams = grams * ratio;
              final lookup = ActionItem.lookupFoodNutrition(ingredientName);

              actions.add(ActionItem(
                  kind: 'food',
                  wgerId: 0,
                  name: ingredientName,
                  details: {
                    'dish_name': dishName,
                    'meal_type': mealType,
                    'serving_grams': ingredientGrams,
                    'calories': lookup['calories'],
                    'protein': lookup['protein'],
                    'carbs': lookup['carbs'],
                    'fat': lookup['fat'],
                  }));
            });
          } else {
            final lookup = ActionItem.lookupFoodNutrition(dishName);
            actions.add(
                ActionItem(kind: 'food', wgerId: 0, name: dishName, details: {
              'dish_name': dishName,
              'meal_type': mealType,
              'serving_grams': grams,
              'calories': lookup['calories'],
              'protein': lookup['protein'],
              'carbs': lookup['carbs'],
              'fat': lookup['fat'],
            }));
          }
        }

        // Keep the trusted catalogue reference with the generated card and
        // return it after a successful write. The backend accepts a pending
        // recommendation as persisted only when this exact reference comes
        // back, preventing a stale or substituted dish from being confirmed.
        if (catalogDishId != null && catalogDishId.isNotEmpty) {
          for (final action in actions) {
            action.details['catalog_dish_id'] = catalogDishId;
          }
        }

        final items = actions.map((action) {
          final details = action.details;
          final cal100g = (details['calories'] as num? ?? 0).toDouble();
          final pro100g = (details['protein'] as num? ?? 0).toDouble();
          final carb100g = (details['carbs'] as num? ?? 0).toDouble();
          final fat100g = (details['fat'] as num? ?? 0).toDouble();
          final itemGrams =
              (details['serving_grams'] as num? ?? 100).toDouble();

          return MealItem(
            id: '${action.name}_${DateTime.now().millisecondsSinceEpoch}',
            foodId: action.wgerId.toString(),
            name: action.name,
            weightGrams: itemGrams,
            calories: cal100g * itemGrams / 100,
            protein: pro100g * itemGrams / 100,
            carbs: carb100g * itemGrams / 100,
            fat: fat100g * itemGrams / 100,
          );
        }).toList();

        final totalCal = items.fold(0.0, (s, i) => s + i.calories);

        WriteResult<MealModel> mealWrite =
            const WriteResult.rejected('MEAL_SERVICE_UNAVAILABLE');
        if (_nutritionProvider != null && _lastUser != null) {
          final stableMealId = chatMealDocumentId(
            args['request_id']?.toString(),
            _uuid.v4(),
          );
          final meal = MealModel(
            id: stableMealId,
            userId: _lastUser!.id,
            name: dishName,
            date: DateTime.now(),
            mealType: mealType,
            items: items,
            isCompleted: true,
          );
          mealWrite = await _nutritionProvider!.addMeal(meal);
        }

        if (!mealWrite.isPersisted) {
          _messages.add(AIChatMessage(
            id: _uuid.v4(),
            text:
                '⚠️ Chưa thể ghi nhận món **$dishName**. Vui lòng thử lại sau.',
            isUser: false,
            isStreaming: false,
            timestamp: DateTime.now(),
          ));
          notifyListeners();
          isOk = false;
          error = mealWrite.status == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = mealWrite.toJson();
          break;
        }

        _lastTodayMeals = _serializeTodayMeals(_nutritionProvider!.todayMeals);
        _lastTodayCalories = _nutritionProvider!.consumedCalories;
        _lastTodayMealsCount = _nutritionProvider!.completedMealsCount;

        final structuredResponse = StructuredResponse(
          type: 'structured',
          text: '',
          mealName: dishName,
          actions: actions,
        );
        final confirmationText =
            '✅ Đã tự động ghi nhận món **$dishName** (~${totalCal.toStringAsFixed(0)} kcal) vào nhật ký ăn uống hôm nay!';

        _messages.add(AIChatMessage(
          id: _uuid.v4(),
          text: confirmationText,
          isUser: false,
          isStreaming: false,
          timestamp: DateTime.now(),
          structuredResponse: structuredResponse,
        ));
        notifyListeners();
        uiMessage = {
          'text': confirmationText,
          'structured': structuredResponse.toJson(),
        };

        resultData = {
          'write_status': 'PERSISTED',
          'meal_record_status': 'CONSUMED',
          if (catalogDishId != null && catalogDishId.isNotEmpty)
            'catalog_dish_id': catalogDishId,
          if (catalogDishId != null && catalogDishId.isNotEmpty)
            'read_back_catalog_dish_id': catalogDishId,
          if (mealWrite.value != null) 'persisted_meal_id': mealWrite.value!.id,
          'logged_meal': dishName,
          'calories': totalCal,
          'today_calories_consumed': _lastTodayCalories,
          'today_consumed_meals_count': _lastTodayMealsCount,
          'state': {
            'today_calories_consumed': AppStateValue<double>(
              value: _lastTodayCalories,
              source: 'firestore.meal_diary.consumed',
              observedAt: _nutritionProvider!.todayMealsObservedAt,
              status: DataStatus.known,
            ).toJson(),
          },
        };
        break;
      case 'log_exercise':
        final exName = args['exercise_name'] as String? ?? 'Bài tập';
        final duration =
            (args['duration_min'] as num? ?? 30).toInt().clamp(1, 24 * 60);
        final description = args['description'] as String? ?? '';
        final wgerId = (args['wger_id'] as num? ?? 0).toInt();
        final category =
            args['category']?.toString() ?? args['type']?.toString() ?? '';
        final calBurned = ExerciseProvider.estimateCaloriesForExercise(
          name: exName,
          categoryName: category,
          muscleCount: 0,
          weightKg: _lastUser?.weight ?? 70,
          durationMinutes: duration,
        );

        var exercisePersisted = false;
        if (_exerciseProvider != null && _lastUser != null) {
          try {
            final exercise = ExerciseModel(
              id: _uuid.v4(),
              userId: _lastUser!.id,
              name: exName,
              exerciseTemplateId: wgerId > 0 ? 'wger_$wgerId' : null,
              date: DateTime.now(),
              duration: duration,
              caloriesBurned: calBurned.toDouble(),
              type: ExerciseProvider.mapCategoryToType(exName, category),
              intensity: 'medium',
            );
            await _exerciseProvider!.addExercise(exercise);
            exercisePersisted = true;
            debugPrint('✅ Auto-logged exercise: $exName ($duration min)');
          } catch (e) {
            debugPrint('❌ Error auto-logging exercise: $e');
          }
        }
        if (!exercisePersisted) {
          isOk = false;
          error = _exerciseProvider == null || _lastUser == null
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = {
            'write_status': _exerciseProvider == null || _lastUser == null
                ? 'REJECTED'
                : 'ERROR',
          };
          break;
        }

        _lastTodayExercises =
            _serializeTodayExercises(_exerciseProvider!.todayExercises);
        _lastTodayCaloriesBurned = _exerciseProvider!.totalCaloriesBurned;
        _lastTodayExercisesCount = _exerciseProvider!.todayExercises.length;

        final structuredResponse = StructuredResponse(
          type: 'structured',
          text: '',
          actions: [
            ActionItem(
                kind: 'exercise',
                wgerId: wgerId,
                name: exName,
                details: {
                  'duration': duration,
                  'duration_min': duration,
                  'calories_burned': calBurned,
                  'description': description,
                  'category': category,
                })
          ],
        );
        final confirmationText =
            '✅ Đã tự động ghi nhận bài tập **$exName** ($duration phút, ~${calBurned.toStringAsFixed(0)} kcal) vào nhật ký vận động!';

        _messages.add(AIChatMessage(
          id: _uuid.v4(),
          text: confirmationText,
          isUser: false,
          isStreaming: false,
          timestamp: DateTime.now(),
          structuredResponse: structuredResponse,
        ));
        notifyListeners();
        uiMessage = {
          'text': confirmationText,
          'structured': structuredResponse.toJson(),
        };

        resultData = {
          'write_status': 'PERSISTED',
          'logged_exercise': exName,
          'calories_burned': calBurned
        };
        break;
      case 'get_lifestyle_logs':
        final user = _userProvider?.currentUser ?? _lastUser;
        final lifestyle = _lifestyleProvider;
        final health = _healthProvider;
        if (user == null || lifestyle == null) {
          resultData = _unloadedLifestyleResult();
          break;
        }
        await lifestyle.loadTodayLogs(user.id);
        if (lifestyle.loadStatus == DataStatus.notLoaded) {
          resultData = _unloadedLifestyleResult();
          break;
        }
        if (lifestyle.loadStatus == DataStatus.error) {
          isOk = false;
          error = 'READ_ERROR';
          resultData = _unloadedLifestyleResult(status: DataStatus.error);
          break;
        }
        if (health != null) await health.loadTodayWaterIntake(user.id);
        resultData = _currentLifestyleResult(user, lifestyle, health);
        break;
      case 'log_lifestyle':
        final logType = args['type'] as String? ?? 'mood';
        final moodScore = args['mood_score'] != null
            ? (args['mood_score'] as num).toInt()
            : null;
        final moodLabel = args['mood_label'] as String? ?? 'Bình thường';
        final sleepHours = args['sleep_hours'] != null
            ? (args['sleep_hours'] as num).toDouble()
            : null;
        final stressScore = args['stress_score'] != null
            ? (args['stress_score'] as num).toInt()
            : null;
        final waterMl = args['water_ml'] != null
            ? (args['water_ml'] as num).toDouble()
            : null;
        final notes = args['notes'] as String? ?? '';

        final user = _userProvider?.currentUser ?? _lastUser;
        WriteStatus writeStatus = WriteStatus.rejected;
        String? writeError = 'INVALID_LIFESTYLE_WRITE';
        if (user != null) {
          if (logType == 'mood' &&
              moodScore != null &&
              _lifestyleProvider != null) {
            final write = await _lifestyleProvider!
                .logMood(user.id, moodScore, moodLabel, notes: notes);
            writeStatus = write.status;
            writeError = write.errorCode;
          } else if (logType == 'sleep_stress' &&
              sleepHours != null &&
              stressScore != null &&
              _lifestyleProvider != null) {
            final write = await _lifestyleProvider!
                .logSleepAndStress(user.id, sleepHours, stressScore);
            writeStatus = write.status;
            writeError = write.errorCode;
          } else if (logType == 'water' &&
              waterMl != null &&
              _healthProvider != null) {
            final write = await _healthProvider!.recordWater(user.id, waterMl);
            writeStatus = write.status;
            writeError = write.errorCode;
          }
        }

        if (writeStatus != WriteStatus.persisted) {
          isOk = false;
          error = writeStatus == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = {
            'write_status': writeStatus.name.toUpperCase(),
            'error_code': writeError,
          };
          break;
        }

        _messages.add(AIChatMessage(
          id: _uuid.v4(),
          text:
              '✅ Đã tự động cập nhật chỉ số Sức khỏe Tinh thần & Lifestyle vào hệ thống!',
          isUser: false,
          isStreaming: false,
          timestamp: DateTime.now(),
        ));
        notifyListeners();

        resultData = {
          'write_status': 'PERSISTED',
          'logged_type': logType,
          if (logType == 'water') 'water_source': 'health.water_intake',
        };
        break;
      case 'set_lifestyle_reminder':
        final title = args['title'] as String? ?? 'Nhắc nhở sinh hoạt';
        final remType = args['rem_type'] as String? ?? 'water';
        final timeStr = args['time'] as String? ?? '08:00';
        final note = args['note'] as String? ?? '';

        WriteResult<LifestyleReminder> reminderWrite =
            const WriteResult.rejected('REMINDER_SERVICE_UNAVAILABLE');
        final reminderUser = _userProvider?.currentUser ?? _lastUser;
        if (_lifestyleProvider != null && reminderUser != null) {
          final reminder = LifestyleReminder(
            id: 'rem_${DateTime.now().millisecondsSinceEpoch}',
            userId: reminderUser.id,
            title: title,
            type: remType,
            time: timeStr,
            isActive: true,
            note: note,
          );
          reminderWrite =
              await _lifestyleProvider!.addReminder(reminderUser.id, reminder);
        }
        if (!reminderWrite.isPersisted) {
          isOk = false;
          error = reminderWrite.status == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = reminderWrite.toJson();
          break;
        }

        _messages.add(AIChatMessage(
          id: _uuid.v4(),
          text:
              '⏰ Đã thiết lập nhắc nhở **$title** vào lúc **$timeStr** thành công!',
          isUser: false,
          isStreaming: false,
          timestamp: DateTime.now(),
        ));
        notifyListeners();

        resultData = {
          'write_status': 'PERSISTED',
          'reminder_title': title,
          'time': timeStr
        };
        break;
      // LƯU Ý QUAN TRỌNG:
      // Trước đây ba tool dưới đây trả về {'history': []} kèm ok=true. Đó là
      // nói dối chứ không phải thiếu tính năng: model nhận "danh sách rỗng"
      // nghĩa là "người dùng không có dữ liệu nào", nên khi người dùng nói
      // "cân mình mãi không giảm" thì bot phân tích trên một lịch sử trống và
      // trả lời rất tự tin. Thà báo lỗi để model biết mà nói thật.
      case 'get_weight_history':
        final days = (args['days'] as num?)?.toInt() ?? 30;
        final weightUser = _userProvider?.currentUser ?? _lastUser;
        if (weightUser?.id == 'demo') {
          resultData = {
            'read_status': 'NOT_LOADED',
            'state': {
              'weight_history': const AppStateValue<List<Map<String, dynamic>>>(
                value: null,
                source: 'demo_ui_defaults',
                observedAt: null,
                status: DataStatus.notLoaded,
              ).toJson(),
              'current_weight': const AppStateValue<double>(
                value: null,
                source: 'demo_ui_defaults',
                observedAt: null,
                status: DataStatus.notLoaded,
              ).toJson(),
            },
          };
          break;
        }
        final history = await _fetchWeightHistory(days);
        if (history == null) {
          isOk = false;
          error = 'READ_ERROR';
          resultData = {
            'read_status': 'READ_ERROR',
            'state': {
              'weight_history': AppStateValue<List<Map<String, dynamic>>>(
                value: null,
                source: 'firestore.body_metrics',
                observedAt: _healthProvider?.weightHistoryObservedAt,
                status: DataStatus.error,
              ).toJson(),
            },
          };
        } else {
          final profile = _userProvider?.currentUser ?? _lastUser;
          final latest = _healthProvider != null &&
                  _healthProvider!.weightHistory.isNotEmpty
              ? _healthProvider!.weightHistory.last
              : null;
          final currentWeight = CanonicalWeightResolver.resolve(
            profileWeight: profile?.id == 'demo' ? null : profile?.weight,
            latestMeasurement: latest,
          );
          resultData = {
            'read_status': 'CURRENT',
            'days': days,
            'count': history.length,
            'history': history,
            'current_weight': currentWeight.value,
            'state': {
              'weight_history': AppStateValue<List<Map<String, dynamic>>>(
                value: history,
                source: 'firestore.body_metrics',
                observedAt: _healthProvider?.weightHistoryObservedAt,
                status: DataStatus.known,
              ).toJson(),
              'current_weight': currentWeight.toJson(),
            },
          };
        }
        break;

      case 'get_meal_log_range':
        final meals = await _fetchMealRange(
          args['from_date'] as String?,
          args['to_date'] as String?,
        );
        if (meals == null) {
          isOk = false;
          error = 'TOOL_INTERNAL_ERROR';
        } else {
          resultData = {'count': meals.length, 'meals': meals};
        }
        break;

      case 'get_exercise_log_range':
        final exercises = await _fetchExerciseRange(
          args['from_date'] as String?,
          args['to_date'] as String?,
        );
        if (exercises == null) {
          isOk = false;
          error = 'TOOL_INTERNAL_ERROR';
        } else {
          resultData = {'count': exercises.length, 'exercises': exercises};
        }
        break;

      case 'log_weight':
        final valueKg = (args['value_kg'] as num?)?.toDouble();
        if (valueKg == null || _lastUser == null) {
          isOk = false;
          error = 'WRITE_REJECTED';
          resultData =
              const WriteResult<Object?>.rejected('INVALID_WEIGHT_WRITE')
                  .toJson();
          break;
        }
        final weightWrite = await _saveWeight(valueKg, args['date'] as String?);
        if (!weightWrite.isPersisted) {
          isOk = false;
          error = weightWrite.status == WriteStatus.rejected
              ? 'WRITE_REJECTED'
              : 'PERSISTENCE_ERROR';
          resultData = weightWrite.toJson();
        } else {
          resultData = {
            'write_status': 'PERSISTED',
            'value_kg': valueKg,
            ...?weightWrite.value,
          };
        }
        break;

      case 'get_active_plan':
        final activePlanUser = _userProvider?.currentUser ?? _lastUser;
        if (activePlanUser != null) {
          final read =
              await _backendApi.readActivePlanDetail(activePlanUser.id);
          switch (read.status) {
            case ActivePlanStatus.activePlanFound:
              resultData = {
                'read_status': 'ACTIVE_PLAN_FOUND',
                'active_plan': read.plan,
              };
              break;
            case ActivePlanStatus.noActivePlan:
              resultData = {
                'read_status': 'NO_ACTIVE_PLAN',
                'active_plan': null,
              };
              break;
            case ActivePlanStatus.readError:
              isOk = false;
              error = 'READ_ERROR';
              resultData = {
                'read_status': 'READ_ERROR',
                'error_code': read.errorCode,
              };
              break;
          }
        } else {
          isOk = false;
          error = 'READ_ERROR';
          resultData = {
            'read_status': 'READ_ERROR',
            'error_code': 'USER_PROFILE_NOT_LOADED',
          };
        }
        break;

      case 'mark_plan_item_complete':
        final itemId = args['item_id'] as String?;
        if (itemId != null && itemId.isNotEmpty) {
          try {
            await _backendApi.updatePlanItemCompletion(
                itemId: itemId, completed: true);
            resultData = {
              'write_status': 'PERSISTED',
              'item_id': itemId,
              'completed': true
            };
          } catch (e) {
            debugPrint('❌ [AIChatProvider] mark_plan_item_complete error: $e');
            isOk = false;
            error = 'PERSISTENCE_ERROR';
            resultData =
                const WriteResult<Object?>.error('PLAN_ITEM_PERSISTENCE_ERROR')
                    .toJson();
          }
        } else {
          isOk = false;
          error = 'WRITE_REJECTED';
          resultData =
              const WriteResult<Object?>.rejected('INVALID_PLAN_ITEM').toJson();
        }
        break;

      case 'navigate_to_screen':
        final screen = args['screen'] as String? ?? 'dashboard';
        debugPrint('📱 [AIChatProvider] Navigating to screen: $screen');
        if (onNavigateToScreen != null) {
          onNavigateToScreen!(screen);
        }
        resultData = {'status': 'success', 'screen': screen};
        break;
      default:
        isOk = false;
        error = 'UNKNOWN_TOOL';
        debugPrint(
            '⚠️ [AIChatProvider] Tool $name is not supported locally yet.');
    }

    final response = {
      'type': 'tool_result',
      'correlation_id': correlationId,
      'ok': isOk,
      'data': resultData,
      if (isOk && uiMessage != null) 'ui_message': uiMessage,
      if (!isOk) 'error': error,
    };

    try {
      debugPrint('📡 [AIChatProvider] Sending tool_result for $name: ok=$isOk');
      _channel?.sink.add(jsonEncode(response));
      _lastClientActionSucceeded = isOk;
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Send tool_result error: $e');
      _lastClientActionSucceeded = false;
    }
    notifyListeners();
  }

  // ------------------------------------------------------------------ //
  // Truy vấn lịch sử cho các tool đọc dữ liệu
  //
  // Mọi hàm dưới đây trả `null` khi KHÔNG lấy được dữ liệu, và trả danh sách
  // rỗng khi thực sự không có bản ghi nào. Phân biệt này rất quan trọng: bản
  // cũ gộp cả hai thành `[]` nên model không thể biết "chưa từng ghi cân" khác
  // với "không đọc được dữ liệu cân", và nó chọn diễn giải đầu tiên.
  // ------------------------------------------------------------------ //

  /// Parse ngày ISO (YYYY-MM-DD); trả null nếu sai định dạng.
  DateTime? _parseDate(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    return DateTime.tryParse(raw);
  }

  Future<List<Map<String, dynamic>>?> _fetchWeightHistory(int days) async {
    final user = _lastUser;
    final health = _healthProvider;
    if (user == null || health == null) return null;

    try {
      final loaded = await health.loadWeightHistory(user.id);
      if (!loaded) return null;
      final cutoff = DateTime.now().subtract(Duration(days: days));
      return health.weightHistory
          .where((m) => m.recordedAt.isAfter(cutoff))
          .map((m) => {
                'date': m.recordedAt.toIso8601String().split('T').first,
                'weight_kg': m.weight,
                'bmi': double.parse(m.bmi.toStringAsFixed(1)),
              })
          .toList();
    } catch (e) {
      debugPrint('❌ [AIChatProvider] _fetchWeightHistory failed: $e');
      return null;
    }
  }

  Future<List<Map<String, dynamic>>?> _fetchMealRange(
    String? fromRaw,
    String? toRaw,
  ) async {
    final user = _lastUser;
    final nutrition = _nutritionProvider;
    if (user == null || nutrition == null) return null;

    final from = _parseDate(fromRaw);
    final to = _parseDate(toRaw);
    if (from == null || to == null) return null;

    try {
      final meals = await nutrition.getMealsInRange(user.id, from, to);
      return meals
          .map((m) => {
                'date': m.date.toIso8601String().split('T').first,
                'meal_type': m.mealType,
                'name': m.name,
                'calories': m.calories.round(),
                'protein': double.parse(m.protein.toStringAsFixed(1)),
                'carbs': double.parse(m.carbs.toStringAsFixed(1)),
                'fat': double.parse(m.fat.toStringAsFixed(1)),
              })
          .toList();
    } catch (e) {
      debugPrint('❌ [AIChatProvider] _fetchMealRange failed: $e');
      return null;
    }
  }

  Future<List<Map<String, dynamic>>?> _fetchExerciseRange(
    String? fromRaw,
    String? toRaw,
  ) async {
    final user = _lastUser;
    final exercise = _exerciseProvider;
    if (user == null || exercise == null) return null;

    final from = _parseDate(fromRaw);
    final to = _parseDate(toRaw);
    if (from == null || to == null) return null;

    try {
      final items = await exercise.loadExercisesForDateRange(
        user.id,
        DateTime(from.year, from.month, from.day),
        DateTime(to.year, to.month, to.day).add(const Duration(days: 1)),
      );
      return items
          .map((e) => {
                'date': e.date.toIso8601String().split('T').first,
                'name': e.name,
                'duration_min': e.duration,
                'calories_burned': e.caloriesBurned.round(),
                'type': e.type,
                'intensity': e.intensity,
              })
          .toList();
    } catch (e) {
      debugPrint('❌ [AIChatProvider] _fetchExerciseRange failed: $e');
      return null;
    }
  }

  Future<WriteResult<Map<String, Object?>>> _saveWeight(
    double valueKg,
    String? dateRaw,
  ) async {
    final user = _lastUser;
    final health = _healthProvider;
    if (user == null || health == null) {
      return const WriteResult.rejected('WEIGHT_SERVICE_UNAVAILABLE');
    }

    try {
      final heightM = user.height / 100.0;
      final bmi = heightM > 0 ? valueKg / (heightM * heightM) : 0.0;
      final recordedAt = _parseDate(dateRaw) ?? DateTime.now();

      final ok = await health.addBodyMetrics(
        userId: user.id,
        weight: valueKg,
        bmi: bmi,
        recordedAt: recordedAt,
      );
      if (!ok) {
        return const WriteResult.error('WEIGHT_PERSISTENCE_ERROR');
      }

      final latest = health.weightHistory.isEmpty
          ? null
          : health.weightHistory
              .reduce((a, b) => a.recordedAt.isAfter(b.recordedAt) ? a : b);
      final shouldSyncProfile = !recordedAt.isAfter(DateTime.now()) &&
          (latest == null ||
              (!latest.recordedAt.isAfter(recordedAt) &&
                  (latest.weight - valueKg).abs() <= 0.05));
      String profileSyncStatus = 'NOT_REQUIRED_BACKDATED_MEASUREMENT';
      if (shouldSyncProfile && _userProvider != null) {
        final profileWrite =
            await _userProvider!.synchronizeWeightFromMeasurement(valueKg);
        profileSyncStatus = profileWrite.status.name.toUpperCase();
        if (profileWrite.isPersisted && _userProvider!.currentUser != null) {
          _lastUser = _userProvider!.currentUser;
        }
      } else if (shouldSyncProfile) {
        profileSyncStatus = 'NOT_LOADED';
      }

      final canonical = CanonicalWeightResolver.resolve(
        profileWeight: (_userProvider?.currentUser ?? _lastUser)?.weight,
        latestMeasurement: latest,
      );
      _messages.add(AIChatMessage(
        id: _uuid.v4(),
        text: '⚖️ Đã ghi cân nặng **${valueKg.toStringAsFixed(1)} kg** '
            '(BMI ${bmi.toStringAsFixed(1)}).',
        isUser: false,
        isStreaming: false,
        timestamp: DateTime.now(),
      ));
      notifyListeners();
      return WriteResult.persisted({
        'profile_sync_status': profileSyncStatus,
        'current_weight': canonical.value,
        'state': {'current_weight': canonical.toJson()},
      });
    } catch (e) {
      debugPrint('❌ [AIChatProvider] _saveWeight failed: $e');
      return const WriteResult.error('WEIGHT_PERSISTENCE_ERROR');
    }
  }

  void _resetTimeoutTimer() {
    _timeoutTimer?.cancel();
    _timeoutTimer = Timer(AIChatbotConfig.streamIdleTimeout, () {
      debugPrint('⏰ [AIChatProvider] Stream timeout');
      _onError('TIMEOUT', 'Phản hồi quá lâu');
    });
  }

  /// Đưa token câu trả lời vào hàng đợi typewriter thích ứng.
  void _onTokenReceived(String token) {
    if (_streamingMessageId == null || token.isEmpty) return;
    _resetTimeoutTimer();

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    if (_deferredResponseText.isNotEmpty) {
      _deferredResponseText += token;
      return;
    }
    _responseTypewriter.add(token);
  }

  void _appendTypewriterChunk(String chunk) {
    if (_streamingMessageId == null || chunk.isEmpty) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    _messages[idx] = _messages[idx].copyWith(
      text: _messages[idx].text + chunk,
      status: MessageStatus.streaming,
    );
    notifyListeners();
  }

  void _onPublicTraceReceived(dynamic rawTrace) {
    if (_streamingMessageId == null || rawTrace is! Map) return;
    _resetTimeoutTimer();
    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;
    final trace = PublicReasoningTrace.fromJson(
      Map<String, dynamic>.from(rawTrace),
    );
    if (!trace.hasSteps) return;
    _messages[idx] = _messages[idx].copyWith(
      publicTrace: trace,
      status: _messages[idx].text.isEmpty
          ? MessageStatus.thinking
          : MessageStatus.streaming,
    );
    notifyListeners();
  }

  void _onDebugTraceReceived(dynamic rawEvent) {
    if (_streamingMessageId == null || rawEvent is! Map) return;
    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;
    final event = DeveloperTraceEvent.fromJson(
      Map<String, dynamic>.from(rawEvent),
    );
    _messages[idx] = _messages[idx].copyWith(
      developerTrace: [..._messages[idx].developerTrace, event],
    );
    notifyListeners();
  }

  /// Authenticated server progress keeps a long tool/model turn interactive
  /// until its bounded total deadline, even before the first visible token.
  void _onStatusReceived() {
    if (_isStreaming) _resetTimeoutTimer();
  }

  /// Lấy text hiển thị khi đang stream — ẩn tất cả data block tags và SUGGESTIONS
  static String getDisplayText(String text, bool isStreaming) {
    if (!isStreaming) return text;
    // Ẩn từ vị trí bắt đầu của bất kỳ tag nào trở đi
    final tagPattern = RegExp(
      r'(\[(ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA|SUGGESTIONS)\]'
      r'|\*\*(ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA|SUGGESTIONS)\*\*'
      r'|(?<!\[)SUGGESTIONS' // "SUGGESTIONS" không có [ ở đầu
      r'|\{\s*"type"\s*:\s*"structured")',
      caseSensitive: false,
    );
    final match = tagPattern.firstMatch(text);
    if (match != null) {
      return text.substring(0, match.start).trimRight();
    }
    return text;
  }

  /// Hoàn tất stream — set isStreaming = false, hủy timeout, parse structured response
  void _onStreamDone(Map<String, dynamic> data) {
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    _activeTurnId = null;

    if (!hasUsableDonePayload(data)) {
      _onError('EMPTY_RESPONSE', 'Server không trả về nội dung');
      return;
    }

    // Server `done` is authoritative terminal state. Cosmetic typewriter
    // backlog must never keep the conversation locked after completion.
    _applyStreamDone(Map<String, dynamic>.from(data));
  }

  void _applyStreamDone(Map<String, dynamic> data) {
    _responseTypewriter.clear();
    _deferredResponseText = '';
    // `done` is terminal for the turn, not for the reusable socket. Keep the
    // connected transport state so the composer can accept the next turn.
    _transportState = ChatTransportState.connected;

    final fullResponse = data['full_response'] as String? ?? '';
    final structuredData = data['structured'] as Map<String, dynamic>?;
    final rawPublicTrace = data['public_trace'];
    final publicTrace = rawPublicTrace is Map
        ? PublicReasoningTrace.fromJson(
            Map<String, dynamic>.from(rawPublicTrace))
        : null;
    final suggestionsRaw = data['suggestions'] as List<dynamic>? ?? [];
    final optionsRaw = data['options'] as List<dynamic>? ?? [];
    final suggestions = suggestionsRaw.map((s) => s.toString()).toList();
    final options = optionsRaw.map((s) => s.toString()).toList();

    StructuredResponse? structuredResponse;
    if (structuredData != null) {
      try {
        structuredResponse = StructuredResponse.fromJson(structuredData);
      } catch (e) {
        debugPrint('❌ Error parsing structured response: $e');
      }
    }

    if (_streamingMessageId != null) {
      final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
      if (idx != -1) {
        _messages[idx] = _messages[idx].copyWith(
          text: fullResponse.isNotEmpty ? fullResponse : _messages[idx].text,
          isStreaming: false,
          status: MessageStatus.done,
          structuredResponse: structuredResponse,
          suggestions: options.isNotEmpty ? options : suggestions,
          isFlowQuestion: options.isNotEmpty,
          publicTrace: publicTrace,
        );
      }
    }

    _isStreaming = false;
    _streamingMessageId = null;
    _activeTurnId = null;
    notifyListeners();
  }

  /// Xử lý lỗi — set error message tiếng Việt dựa trên code
  void _onError(String code, String message) {
    disconnect(); // Ensure channel is completely cleaned up and nullified
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;

    debugPrint('❌ [AIChatProvider] Error: $code - $message');

    // Xóa streaming placeholder nếu còn trống
    if (_streamingMessageId != null) {
      final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
      if (idx != -1 && _messages[idx].text.isEmpty) {
        _messages.removeAt(idx);
      } else if (idx != -1) {
        _messages[idx] = _messages[idx].copyWith(
          isStreaming: false,
          status: MessageStatus.error,
        );
      }
    }

    _isStreaming = false;
    _transportState = ChatTransportState.error;
    _streamingMessageId = null;
    _activeTurnId = null;

    switch (code) {
      case 'LLM_UNAVAILABLE':
        _errorMessage =
            'Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.';
        break;
      case 'LLM_QUOTA_EXHAUSTED':
        _errorMessage =
            'Dịch vụ AI đã hết hạn mức. Vui lòng liên hệ quản trị viên.';
        break;
      case 'TIMEOUT':
      case 'LLM_TIMEOUT':
        _errorMessage = 'Phản hồi quá lâu. Vui lòng thử lại.';
        break;
      case 'EMPTY_RESPONSE':
      case 'BAD_RESPONSE':
        _errorMessage =
            'Chưa nhận được câu trả lời hoàn chỉnh. Nhấn để thử lại.';
        break;
      case 'CONNECTION_ERROR':
        _errorMessage = 'Không thể kết nối đến server. Kiểm tra kết nối mạng.';
        break;
      case 'AUTHENTICATION_REQUIRED':
        _errorMessage = 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.';
        break;
      default:
        _errorMessage = 'Có lỗi xảy ra. Nhấn để thử lại.';
    }

    notifyListeners();
  }

  ProfileContextScope _scopeForMessage(String message) {
    return ProfileReadiness.scopeForConversation(
      message,
      activeScope: _activeProfileScope,
      recentMessages: _messages.reversed.map((message) => message.text),
    );
  }

  /// Ngắt kết nối WebSocket và hủy tất cả subscriptions
  void disconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    _activeTurnId = null;
    _responseTypewriter.clear();
    _deferredResponseText = '';
    if (_transportState != ChatTransportState.error) {
      _transportState = ChatTransportState.disconnected;
    }
  }

  @override
  void dispose() {
    disconnect();
    _responseTypewriter.dispose();
    unawaited(_semanticRouter.dispose());
    super.dispose();
  }

  /// Save exercise from action item to ExerciseProvider
  Future<void> saveExerciseFromAction(ActionItem action, UserModel user) async {
    if (_exerciseProvider == null) {
      debugPrint('❌ ExerciseProvider not set');
      return;
    }

    try {
      final details = action.details;
      final rawDuration = details['duration'] ?? details['duration_min'] ?? 30;
      final duration = (rawDuration is num
              ? rawDuration.toInt()
              : int.tryParse(rawDuration.toString()) ?? 30)
          .clamp(1, 24 * 60);
      final category =
          details['category']?.toString() ?? details['type']?.toString() ?? '';
      final rawCalories = details['calories_burned'];
      final parsedCalories = rawCalories is num
          ? rawCalories.toDouble()
          : double.tryParse(rawCalories?.toString() ?? '');
      final caloriesBurned = parsedCalories != null &&
              parsedCalories.isFinite &&
              parsedCalories > 0
          ? parsedCalories
          : ExerciseProvider.estimateCaloriesForExercise(
              name: action.name,
              categoryName: category,
              muscleCount: 0,
              weightKg: user.weight,
              durationMinutes: duration,
            );

      final exercise = ExerciseModel(
        id: _uuid.v4(),
        userId: user.id,
        name: action.name,
        exerciseTemplateId: action.wgerId > 0 ? 'wger_${action.wgerId}' : null,
        date: DateTime.now(),
        duration: duration,
        caloriesBurned: caloriesBurned,
        type: ExerciseProvider.mapCategoryToType(action.name, category),
        intensity: 'medium',
      );

      await _exerciseProvider!.addExercise(exercise);
      debugPrint('✅ Exercise saved from action: ${action.name}');
    } catch (e) {
      debugPrint('❌ Error saving exercise from action: $e');
      rethrow;
    }
  }

  /// Save food from action item to NutritionProvider
  Future<void> saveFoodFromAction(
    ActionItem action,
    double grams,
    UserModel user,
  ) async {
    if (_nutritionProvider == null) {
      debugPrint('❌ NutritionProvider not set');
      return;
    }

    try {
      final details = action.details;
      final caloriesPer100g = details['calories'] as num? ?? 0;
      final proteinPer100g = details['protein'] as num? ?? 0;
      final carbsPer100g = details['carbs'] as num? ?? 0;
      final fatPer100g = details['fat'] as num? ?? 0;
      final mealType = _mapMealType(details['meal_type'] as String? ?? 'sang');
      final servingGrams = details['serving_grams'] != null
          ? (details['serving_grams'] as num).toDouble()
          : grams;

      final item = MealItem(
        id: '${_uuid.v4()}_item',
        foodId: action.wgerId.toString(),
        name: action.name,
        weightGrams: servingGrams,
        calories: caloriesPer100g * servingGrams / 100,
        protein: proteinPer100g * servingGrams / 100,
        carbs: carbsPer100g * servingGrams / 100,
        fat: fatPer100g * servingGrams / 100,
      );

      final meal = MealModel(
        id: _uuid.v4(),
        userId: user.id,
        name: action.name,
        date: DateTime.now(),
        mealType: mealType,
        items: [item],
      );

      await _nutritionProvider!.addMeal(meal);
      debugPrint('✅ Food saved from action: ${action.name} (${servingGrams}g)');
    } catch (e) {
      debugPrint('❌ Error saving food from action: $e');
      rethrow;
    }
  }

  String _mapMealType(String mealType) {
    return MealTypeUtils.normalize(mealType);
  }

  double? _positiveDouble(dynamic value) {
    final parsed = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '');
    if (parsed == null || !parsed.isFinite || parsed <= 0) return null;
    return parsed;
  }

  double _nonNegativeDouble(dynamic value) {
    final parsed = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '');
    if (parsed == null || !parsed.isFinite || parsed < 0) return 0;
    return parsed;
  }

  List<Map<String, dynamic>> _serializeTodayMeals(List<MealModel> meals) =>
      meals
          .map((meal) => {
                'name': meal.name,
                'meal_type': meal.mealType,
                'record_status': meal.isCompleted ? 'CONSUMED' : 'PLANNED',
                'calories': meal.calories,
                'protein': meal.protein,
                'carbs': meal.carbs,
                'fat': meal.fat,
                'is_completed': meal.isCompleted,
              })
          .toList();

  Map<String, dynamic> _todayMealsResult(
    NutritionProvider provider,
    List<Map<String, dynamic>> meals,
  ) =>
      {
        'read_status':
            provider.activePlanReadStatus == ActivePlanStatus.readError
                ? 'PARTIAL'
                : 'CURRENT',
        'active_plan_read_status': provider.activePlanReadStatus.name
            .replaceAllMapped(RegExp(r'([A-Z])'), (m) => '_${m[1]}')
            .toUpperCase(),
        'today_calories_consumed': provider.consumedCalories,
        'today_meals_count': provider.completedMealsCount,
        'today_meals': meals,
        'planned_meals_count': provider.pendingMealsCount,
        'state': {
          'today_calories_consumed': AppStateValue<double>(
            value: provider.consumedCalories,
            source: 'firestore.meal_diary.consumed',
            observedAt: provider.todayMealsObservedAt,
            status: DataStatus.known,
          ).toJson(),
          'today_meals': AppStateValue<List<Map<String, dynamic>>>(
            value: meals,
            source: 'firestore.meal_diary_and_active_plan',
            observedAt: provider.todayMealsObservedAt,
            status: provider.activePlanReadStatus == ActivePlanStatus.readError
                ? DataStatus.error
                : DataStatus.known,
          ).toJson(),
        },
      };

  List<Map<String, dynamic>> _serializeTodayExercises(
    List<ExerciseModel> exercises,
  ) =>
      exercises
          .map((exercise) => {
                'name': exercise.name,
                'type': exercise.type,
                'duration_min': exercise.duration,
                'calories_burned': exercise.caloriesBurned,
              })
          .toList();

  Map<String, dynamic> _todayExercisesResult(
    ExerciseProvider provider,
    List<Map<String, dynamic>> exercises,
  ) =>
      {
        'read_status': 'CURRENT',
        'today_calories_burned': provider.totalCaloriesBurned,
        'today_exercises_count': exercises.length,
        'today_exercises': exercises,
        'state': {
          'today_exercises': AppStateValue<List<Map<String, dynamic>>>(
            value: exercises,
            source: 'firestore.exercise_diary',
            observedAt: provider.todayExercisesObservedAt,
            status: DataStatus.known,
          ).toJson(),
        },
      };

  Map<String, dynamic> _unloadedLifestyleResult({
    DataStatus status = DataStatus.notLoaded,
  }) {
    AppStateValue<Object?> unavailable(String source) => AppStateValue<Object?>(
          value: null,
          source: source,
          observedAt: null,
          status: status,
        );
    return {
      'read_status': status == DataStatus.error ? 'READ_ERROR' : 'NOT_LOADED',
      'mood_score': null,
      'mood_label': null,
      'sleep_hours': null,
      'stress_score': null,
      'lifestyle_water_logged_today_ml': null,
      'water_consumed_today_ml': null,
      'state': {
        'mood': unavailable('firestore.lifestyle_logs').toJson(),
        'sleep_hours': unavailable('firestore.lifestyle_logs').toJson(),
        'stress_score': unavailable('firestore.lifestyle_logs').toJson(),
        'lifestyle_water_logged_today':
            unavailable('firestore.lifestyle_logs.legacy_water').toJson(),
        'water_consumed_today': unavailable('health.water_intake').toJson(),
      },
    };
  }

  Map<String, dynamic> _currentLifestyleResult(
    UserModel user,
    LifestyleProvider lifestyle,
    HealthProvider? health,
  ) {
    final log = lifestyle.todayLog;
    AppStateValue<T> observed<T>(
      bool hasObservation,
      T displayValue,
      String source,
    ) =>
        AppStateValue<T>(
          value: hasObservation ? displayValue : null,
          source: source,
          observedAt: hasObservation ? lifestyle.observedAt : null,
          status: hasObservation ? DataStatus.known : DataStatus.missing,
        );

    final mood = observed<Map<String, Object?>>(
      log.hasMoodObservation,
      {'score': log.moodScore, 'label': log.moodLabel},
      'firestore.lifestyle_logs',
    );
    final sleep = observed<double>(
      log.hasSleepObservation,
      log.sleepHours,
      'firestore.lifestyle_logs',
    );
    final stress = observed<int>(
      log.hasStressObservation,
      log.stressScore,
      'firestore.lifestyle_logs',
    );
    final legacyWater = observed<double>(
      log.hasLifestyleWaterObservation,
      log.waterIntakeMl,
      'firestore.lifestyle_logs.legacy_water',
    );
    final waterStatus = health?.waterStatus ?? DataStatus.notLoaded;
    final consumedWater = AppStateValue<double>(
      value: waterStatus == DataStatus.known ? health!.todayWaterIntake : null,
      source: 'health.water_intake',
      observedAt: health?.waterObservedAt,
      status: waterStatus,
    );
    final target = AppStateValue<double>(
      value: user.id != 'demo' && user.dailyWaterGoal != null
          ? user.dailyWaterGoal! * 1000
          : null,
      source: 'profile_weight_derived_target',
      observedAt: null,
      status: user.id != 'demo' && user.dailyWaterGoal != null
          ? DataStatus.known
          : DataStatus.missing,
    );
    return {
      'read_status': waterStatus == DataStatus.error ? 'PARTIAL' : 'CURRENT',
      'mood_score': log.hasMoodObservation ? log.moodScore : null,
      'mood_label': log.hasMoodObservation ? log.moodLabel : null,
      'sleep_hours': log.hasSleepObservation ? log.sleepHours : null,
      'stress_score': log.hasStressObservation ? log.stressScore : null,
      'lifestyle_water_logged_today_ml':
          log.hasLifestyleWaterObservation ? log.waterIntakeMl : null,
      'water_consumed_today_ml': consumedWater.value,
      'water_target_ml': target.value,
      'notes': log.hasNotesObservation ? log.notes : null,
      'state': {
        'mood': mood.toJson(),
        'sleep_hours': sleep.toJson(),
        'stress_score': stress.toJson(),
        'lifestyle_water_logged_today': legacyWater.toJson(),
        'water_consumed_today': consumedWater.toJson(),
        'water_target': target.toJson(),
      },
    };
  }

  Map<String, Object?> _buildSendTimeStateManifest(
    UserModel user, {
    required double todayCalories,
    required int todayMealsCount,
    required double todayCaloriesBurned,
    required int todayExercisesCount,
    required List<Map<String, dynamic>> todayMeals,
    required List<Map<String, dynamic>> todayExercises,
  }) {
    final mealObservedAt = _nutritionProvider?.todayMealsObservedAt;
    final exerciseObservedAt = _exerciseProvider?.todayExercisesObservedAt;
    final waterProvider = _healthProvider;
    final waterSnapshotStatus = waterProvider == null
        ? DataStatus.notLoaded
        : waterProvider.waterStatus == DataStatus.known
            ? DataStatus.stale
            : waterProvider.waterStatus;
    return {
      'profile.current_weight': AppStateValue<double>(
        value: user.id == 'demo' ? null : user.weight,
        source: user.id == 'demo'
            ? 'demo_ui_defaults'
            : 'send_time_profile_snapshot',
        observedAt: null,
        status: user.id == 'demo' ? DataStatus.notLoaded : DataStatus.stale,
      ).toJson(),
      'today.calories_consumed': AppStateValue<double>(
        value: todayCalories,
        source: 'send_time_meal_snapshot',
        observedAt: mealObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'today.consumed_meal_count': AppStateValue<int>(
        value: todayMealsCount,
        source: 'send_time_meal_snapshot',
        observedAt: mealObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'today.meals': AppStateValue<List<Map<String, dynamic>>>(
        value: todayMeals,
        source: 'send_time_meal_snapshot',
        observedAt: mealObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'today.calories_burned': AppStateValue<double>(
        value: todayCaloriesBurned,
        source: 'send_time_exercise_snapshot',
        observedAt: exerciseObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'today.exercise_count': AppStateValue<int>(
        value: todayExercisesCount,
        source: 'send_time_exercise_snapshot',
        observedAt: exerciseObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'today.exercises': AppStateValue<List<Map<String, dynamic>>>(
        value: todayExercises,
        source: 'send_time_exercise_snapshot',
        observedAt: exerciseObservedAt,
        status: DataStatus.stale,
      ).toJson(),
      'water_target': AppStateValue<double>(
        value: user.id != 'demo' && user.dailyWaterGoal != null
            ? user.dailyWaterGoal! * 1000
            : null,
        source: 'profile_weight_derived_target',
        observedAt: null,
        status: user.id != 'demo' && user.dailyWaterGoal != null
            ? DataStatus.stale
            : DataStatus.missing,
      ).toJson(),
      'water_consumed_today': AppStateValue<double>(
        value: waterProvider?.waterStatus == DataStatus.known
            ? waterProvider!.todayWaterIntake
            : null,
        source: 'health.water_intake',
        observedAt: waterProvider?.waterObservedAt,
        status: waterSnapshotStatus,
      ).toJson(),
    };
  }
}
