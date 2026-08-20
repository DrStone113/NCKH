import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';
import '../models/user_model.dart';
import '../models/chat_message.dart';
import '../models/wger_models.dart';
import '../models/exercise_model.dart';
import '../models/meal_model.dart';
import '../models/lifestyle_model.dart';
import '../constants/ai_chatbot_config.dart';
import '../services/backend_api_service.dart';
import 'exercise_provider.dart';
import 'nutrition_provider.dart';
import 'lifestyle_provider.dart';
import 'health_provider.dart';
import '../utils/location_helper.dart';
import '../utils/meal_nutrition_utils.dart';
import '../utils/streaming_typewriter.dart';

class AIChatProvider extends ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  final List<AIChatMessage> _messages = [];
  bool _isStreaming = false;
  String? _streamingMessageId;
  String? _errorMessage;
  Timer? _timeoutTimer;
  late final StreamingTypewriter _responseTypewriter;
  late final StreamingTypewriter _thoughtTypewriter;
  Map<String, dynamic>? _pendingDoneData;
  String _deferredResponseText = '';
  final _uuid = const Uuid();
  String? _sessionId;
  final BackendApiService _backendApi = BackendApiService();
  double? _latitude;
  double? _longitude;

  AIChatProvider({
    Duration typewriterInterval = const Duration(milliseconds: 18),
  }) {
    _thoughtTypewriter = StreamingTypewriter(
      interval: typewriterInterval,
      batchMultiplier: 2,
      onChunk: _appendThoughtTypewriterChunk,
      onIdle: _onThoughtTypewriterIdle,
    );
    _responseTypewriter = StreamingTypewriter(
      interval: typewriterInterval,
      onChunk: _appendTypewriterChunk,
      onIdle: _completePendingStream,
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

  /// Callback to navigate screens in Flutter UI
  void Function(String screen)? onNavigateToScreen;

  List<AIChatMessage> get messages => List.unmodifiable(_messages);
  bool get isStreaming => _isStreaming;
  String? get errorMessage => _errorMessage;
  bool get canRetry => _lastMessageText != null && _lastUser != null;
  String? get currentSessionId => _sessionId;

  /// Set provider references for saving actions
  void setProviders({
    ExerciseProvider? exerciseProvider,
    NutritionProvider? nutritionProvider,
    LifestyleProvider? lifestyleProvider,
    HealthProvider? healthProvider,
  }) {
    if (exerciseProvider != null) _exerciseProvider = exerciseProvider;
    if (nutritionProvider != null) _nutritionProvider = nutritionProvider;
    if (lifestyleProvider != null) _lifestyleProvider = lifestyleProvider;
    if (healthProvider != null) _healthProvider = healthProvider;
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

  /// Start a new fresh chat session
  void startNewSession() {
    disconnect();
    _sessionId = _uuid.v4();
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
    _messages.clear();
    _errorMessage = null;
    _isStreaming = false;

    for (final raw in rawMessages) {
      final role = raw['role'] ?? 'user';
      final isUser = role == 'user';
      final text = raw['content'] ?? '';
      final thoughts = raw['thoughts']?.toString() ?? '';
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
        thoughts: thoughts,
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

    debugPrint('🔌 [AIChatProvider] Connecting to ${AIChatbotConfig.wsUrl}...');

    try {
      _channel = WebSocketChannel.connect(
        Uri.parse(AIChatbotConfig.wsUrl),
      );

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

      _subscription = _channel!.stream.listen(
        _handleMessage,
        onError: (error) {
          debugPrint('❌ [AIChatProvider] Stream error: $error');
          disconnect(); // Clear resources and set _channel = null
          _onError('CONNECTION_ERROR', error.toString());
        },
        onDone: () {
          debugPrint('🔌 [AIChatProvider] Connection closed');
          final wasStreaming = _isStreaming;
          disconnect(); // Clear resources and set _channel = null
          if (wasStreaming) {
            _onError('CONNECTION_ERROR', 'Kết nối bị ngắt');
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

    // Xóa tin nhắn user cuối cùng (sẽ được thêm lại trong sendMessage)
    // Tìm từ cuối lên để xử lý cả trường hợp có partial bot message
    final lastUserIdx = _messages.lastIndexWhere((m) => m.isUser);
    if (lastUserIdx != -1) {
      // Xóa user message và tất cả bot message sau nó (partial response)
      _messages.removeRange(lastUserIdx, _messages.length);
    }

    _errorMessage = null;
    notifyListeners();

    await sendMessage(
      _lastMessageText!,
      _lastUser!,
      todayCalories: _lastTodayCalories,
      todayMealsCount: _lastTodayMealsCount,
      todayCaloriesBurned: _lastTodayCaloriesBurned,
      todayExercisesCount: _lastTodayExercisesCount,
      todayMeals: _lastTodayMeals,
      todayExercises: _lastTodayExercises,
    );
  }

  /// Gửi tin nhắn người dùng và tạo streaming placeholder
  Future<void> sendMessage(
    String text,
    UserModel user, {
    double todayCalories = 0,
    int todayMealsCount = 0,
    double todayCaloriesBurned = 0,
    int todayExercisesCount = 0,
    List<Map<String, dynamic>> todayMeals = const [],
    List<Map<String, dynamic>> todayExercises = const [],
  }) async {
    debugPrint('📤 [AIChatProvider] Sending message: $text');
    debugPrint('👤 [AIChatProvider] User: ${user.name}, age: ${user.age}');

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
      if (_channel == null) return;
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
    _thoughtTypewriter.clear();
    _responseTypewriter.clear();
    _pendingDoneData = null;
    _deferredResponseText = '';
    final streamingId = _uuid.v4();
    _streamingMessageId = streamingId;
    _isStreaming = true;
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

    // Bắt đầu timeout 30 giây
    _timeoutTimer?.cancel();
    _timeoutTimer = Timer(AIChatbotConfig.streamTimeout, () {
      debugPrint('⏰ [AIChatProvider] Stream timeout');
      _onError('TIMEOUT', 'Phản hồi quá lâu');
    });

    // 3. Gửi ChatRequest JSON qua WebSocket kèm user_context phong phú
    final Map<String, dynamic> userContext = {
      'user_id': user.id,
      'name': user.name,
      'age': user.age,
      'gender': user.gender,
      'height': user.height,
      'weight': user.weight,
      'target_weight': user.targetWeight,
      'activity_level': user.activityLevel,
      'health_goal': user.healthGoal,
      'bmi': user.bmi,
      'bmi_category': user.bmiCategory,
      'bmr': user.bmr,
      'tdee': user.tdee,
      'recommended_calories': user.recommendedCalories,
      'daily_water_goal': user.dailyWaterGoal,
      'today_calories_consumed': todayCalories,
      'today_meals_count': todayMealsCount,
      'today_calories_burned': todayCaloriesBurned,
      'today_exercises_count': todayExercisesCount,
      'today_meals': todayMeals,
      'today_exercises': todayExercises,
    };

    final Map<String, dynamic> request = {
      'type': 'chat',
      'session_id': _sessionId,
      'user_id': user.id,
      'message': text,
      'user_context': userContext,
    };
    if (_latitude != null && _longitude != null) {
      request['latitude'] = _latitude;
      request['longitude'] = _longitude;
    }

    try {
      debugPrint('📡 [AIChatProvider] Sending request: ${jsonEncode(request)}');
      _channel!.sink.add(jsonEncode(request));
      debugPrint('✅ [AIChatProvider] Request sent');
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Send error: $e');
      _onError('CONNECTION_ERROR', e.toString());
    }
  }

  /// Xử lý message nhận từ WebSocket
  void _handleMessage(dynamic raw) {
    debugPrint(
        '📥 [AIChatProvider] Received message: ${raw.toString().substring(0, raw.toString().length > 100 ? 100 : raw.toString().length)}...');

    try {
      final data = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = data['type'] as String?;

      debugPrint('📦 [AIChatProvider] Message type: $type');

      switch (type) {
        case 'token':
          _onTokenReceived(data['content'] as String? ?? '');
          break;
        case 'thought':
          _onThoughtReceived(data['content'] as String? ?? '');
          break;
        case 'status':
          _onStatusReceived();
          break;
        case 'done':
          debugPrint('✅ [AIChatProvider] Stream done');
          _onStreamDone(data);
          break;
        case 'error':
          _onError(data['code'] as String? ?? 'ERROR',
              data['message'] as String? ?? 'Lỗi không xác định');
          break;
        case 'tool_call':
          _handleToolCall(data);
          break;
        default:
          debugPrint('⚠️ [AIChatProvider] Unknown message type: $type');
      }
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Parse error: $e');
    }
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

    debugPrint('🛠️ [AIChatProvider] Handling tool_call: $name');

    Map<String, dynamic> resultData = {};
    Map<String, dynamic>? uiMessage;
    bool isOk = true;
    String? error;

    switch (name) {
      case 'get_user_profile':
        if (_lastUser != null) {
          resultData = {
            'user_id': _lastUser!.id,
            'id': _lastUser!.id,
            'name': _lastUser!.name,
            'age': _lastUser!.age,
            'gender': _lastUser!.gender,
            'height': _lastUser!.height,
            'weight': _lastUser!.weight,
            'target_weight': _lastUser!.targetWeight,
            'activity_level': _lastUser!.activityLevel,
            'health_goal': _lastUser!.healthGoal,
            'bmi': _lastUser!.bmi,
            'bmi_category': _lastUser!.bmiCategory,
            'bmr': _lastUser!.bmr,
            'tdee': _lastUser!.tdee,
            'recommended_calories': _lastUser!.recommendedCalories,
            'daily_water_goal': _lastUser!.dailyWaterGoal,
            'today_calories_consumed': _lastTodayCalories,
            'today_meals_count': _lastTodayMealsCount,
            'today_calories_burned': _lastTodayCaloriesBurned,
            'today_exercises_count': _lastTodayExercisesCount,
            'today_meals': _lastTodayMeals,
            'today_exercises': _lastTodayExercises,
          };
        } else {
          isOk = false;
          error = 'No user profile available';
        }
        break;
      case 'get_today_meals':
        resultData = {
          'today_calories_consumed': _lastTodayCalories,
          'today_meals_count': _lastTodayMealsCount,
          'today_meals': _lastTodayMeals,
        };
        break;
      case 'get_today_exercises':
        resultData = {
          'today_calories_burned': _lastTodayCaloriesBurned,
          'today_exercises_count': _lastTodayExercisesCount,
          'today_exercises': _lastTodayExercises,
        };
        break;
      case 'log_meal':
        final dishName = args['dish_name'] as String? ?? 'Món ăn';
        final mealTypeRaw = args['meal_type'] as String? ?? 'lunch';
        final mealType = _mapMealType(mealTypeRaw);
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

        var mealLogged = false;
        String? mealLogError;
        if (_nutritionProvider != null && _lastUser != null) {
          try {
            final meal = MealModel(
              id: DateTime.now().millisecondsSinceEpoch.toString(),
              userId: _lastUser!.id,
              name: dishName,
              date: DateTime.now(),
              mealType: mealType,
              items: items,
            );
            await _nutritionProvider!.addMeal(meal);
            mealLogged = true;
            debugPrint('✅ Auto-logged meal: $dishName');
          } catch (e) {
            mealLogError = e.toString();
            debugPrint('❌ Error auto-logging meal: $e');
          }
        } else {
          mealLogError = 'Chưa có hồ sơ người dùng hoặc dịch vụ dinh dưỡng';
        }

        if (!mealLogged) {
          _messages.add(AIChatMessage(
            id: _uuid.v4(),
            text:
                '⚠️ Chưa thể ghi nhận món **$dishName**. Vui lòng thử lại sau.',
            isUser: false,
            isStreaming: false,
            timestamp: DateTime.now(),
          ));
          notifyListeners();
          resultData = {
            'status': 'error',
            'error': mealLogError ?? 'Không thể lưu món ăn',
          };
          break;
        }

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
          'status': 'success',
          'logged_meal': dishName,
          'calories': totalCal
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
            debugPrint('✅ Auto-logged exercise: $exName ($duration min)');
          } catch (e) {
            debugPrint('❌ Error auto-logging exercise: $e');
          }
        }

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
          'status': 'success',
          'logged_exercise': exName,
          'calories_burned': calBurned
        };
        break;
      case 'get_lifestyle_logs':
        if (_lifestyleProvider != null) {
          final log = _lifestyleProvider!.todayLog;
          resultData = {
            'today_water_ml': log.waterIntakeMl,
            'mood_score': log.moodScore,
            'mood_label': log.moodLabel,
            'sleep_hours': log.sleepHours,
            'stress_score': log.stressScore,
            'notes': log.notes,
          };
        } else {
          resultData = {
            'today_water_ml': 0,
            'mood_score': 3,
            'mood_label': 'Bình thường',
            'sleep_hours': 7.0,
            'stress_score': 2,
            'notes': '',
          };
        }
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

        if (_lifestyleProvider != null && _lastUser != null) {
          if (moodScore != null) {
            await _lifestyleProvider!
                .logMood(_lastUser!.id, moodScore, moodLabel, notes: notes);
          }
          if (sleepHours != null && stressScore != null) {
            await _lifestyleProvider!
                .logSleepAndStress(_lastUser!.id, sleepHours, stressScore);
          }
          if (waterMl != null) {
            await _lifestyleProvider!.addWater(_lastUser!.id, waterMl);
          }
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

        resultData = {'status': 'success', 'logged_type': logType};
        break;
      case 'set_lifestyle_reminder':
        final title = args['title'] as String? ?? 'Nhắc nhở sinh hoạt';
        final remType = args['rem_type'] as String? ?? 'water';
        final timeStr = args['time'] as String? ?? '08:00';
        final note = args['note'] as String? ?? '';

        if (_lifestyleProvider != null && _lastUser != null) {
          final reminder = LifestyleReminder(
            id: 'rem_${DateTime.now().millisecondsSinceEpoch}',
            userId: _lastUser!.id,
            title: title,
            type: remType,
            time: timeStr,
            isActive: true,
            note: note,
          );
          await _lifestyleProvider!.addReminder(_lastUser!.id, reminder);
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
          'status': 'success',
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
        final history = await _fetchWeightHistory(days);
        if (history == null) {
          isOk = false;
          error = 'TOOL_INTERNAL_ERROR';
        } else {
          resultData = {
            'days': days,
            'count': history.length,
            'history': history
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
          error = 'INVALID_ARGS';
          break;
        }
        final saved = await _saveWeight(valueKg, args['date'] as String?);
        if (!saved) {
          // Không báo "success" khi chưa ghi được — người dùng sẽ tưởng đã lưu.
          isOk = false;
          error = 'TOOL_INTERNAL_ERROR';
        } else {
          resultData = {'status': 'saved', 'value_kg': valueKg};
        }
        break;

      case 'get_active_plan':
        if (_lastUser != null) {
          try {
            final planDetail =
                await _backendApi.getActivePlanDetail(_lastUser!.id);
            resultData = {'active_plan': planDetail};
          } catch (e) {
            debugPrint('⚠️ [AIChatProvider] get_active_plan error: $e');
            resultData = {'active_plan': null};
          }
        } else {
          resultData = {'active_plan': null};
        }
        break;

      case 'mark_plan_item_complete':
        final itemId = args['item_id'] as String?;
        if (itemId != null && itemId.isNotEmpty) {
          try {
            await _backendApi.updatePlanItemCompletion(
                itemId: itemId, completed: true);
            resultData = {
              'status': 'success',
              'item_id': itemId,
              'completed': true
            };
          } catch (e) {
            debugPrint('❌ [AIChatProvider] mark_plan_item_complete error: $e');
            isOk = false;
            error = 'TOOL_INTERNAL_ERROR';
          }
        } else {
          isOk = false;
          error = 'INVALID_ARGS';
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
      if (isOk) 'data': resultData,
      if (isOk && uiMessage != null) 'ui_message': uiMessage,
      if (!isOk) 'error': error,
    };

    try {
      debugPrint(
          '📡 [AIChatProvider] Sending tool_result: ${jsonEncode(response)}');
      _channel?.sink.add(jsonEncode(response));
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Send tool_result error: $e');
    }
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
      await health.loadWeightHistory(user.id);
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

  /// Ghi cân nặng thật vào Firestore. Trả false nếu không lưu được.
  Future<bool> _saveWeight(double valueKg, String? dateRaw) async {
    final user = _lastUser;
    final health = _healthProvider;
    if (user == null || health == null) return false;

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
      if (ok) {
        _messages.add(AIChatMessage(
          id: _uuid.v4(),
          text: '⚖️ Đã ghi cân nặng **${valueKg.toStringAsFixed(1)} kg** '
              '(BMI ${bmi.toStringAsFixed(1)}).',
          isUser: false,
          isStreaming: false,
          timestamp: DateTime.now(),
        ));
        notifyListeners();
      }
      return ok;
    } catch (e) {
      debugPrint('❌ [AIChatProvider] _saveWeight failed: $e');
      return false;
    }
  }

  void _resetTimeoutTimer() {
    _timeoutTimer?.cancel();
    _timeoutTimer = Timer(AIChatbotConfig.streamTimeout, () {
      debugPrint('⏰ [AIChatProvider] Stream timeout');
      _onError('TIMEOUT', 'Phản hồi quá lâu');
    });
  }

  /// Đưa token câu trả lời vào hàng đợi typewriter thích ứng.
  void _onTokenReceived(String token) {
    _resetTimeoutTimer();
    if (_streamingMessageId == null || token.isEmpty) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    // Giữ câu trả lời lại để panel suy nghĩ có thời gian chạy hết hiệu ứng.
    if (_thoughtTypewriter.hasPending || _deferredResponseText.isNotEmpty) {
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

  /// Nhận token suy nghĩ từ backend
  void _onThoughtReceived(String token) {
    _resetTimeoutTimer();
    if (_streamingMessageId == null || token.isEmpty) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    _thoughtTypewriter.add(token);
  }

  void _appendThoughtTypewriterChunk(String chunk) {
    if (_streamingMessageId == null || chunk.isEmpty) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;
    final currentMessage = _messages[idx];
    _messages[idx] = currentMessage.copyWith(
      thoughts: currentMessage.thoughts + chunk,
      // Một thought đến muộn không được làm ẩn phần câu trả lời đang chạy.
      status: currentMessage.status == MessageStatus.streaming
          ? MessageStatus.streaming
          : MessageStatus.thinking,
    );
    notifyListeners();
  }

  void _onThoughtTypewriterIdle() {
    _flushDeferredResponse();
    _completePendingStream();
  }

  void _flushDeferredResponse() {
    if (_deferredResponseText.isEmpty) return;
    final deferredText = _deferredResponseText;
    _deferredResponseText = '';
    _responseTypewriter.add(deferredText);
  }

  /// Status trung gian chỉ là heartbeat; UI chỉ hiển thị thought thật.
  void _onStatusReceived() {
    _resetTimeoutTimer();
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

    _pendingDoneData = Map<String, dynamic>.from(data);
    _reconcileTypewriterWithFullResponse(data);
    _completePendingStream();
  }

  void _reconcileTypewriterWithFullResponse(Map<String, dynamic> data) {
    final fullResponse = data['full_response'] as String? ?? '';
    if (fullResponse.isEmpty || _streamingMessageId == null) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    final visibleText = _messages[idx].text;
    final receivedText =
        visibleText + _responseTypewriter.pendingText + _deferredResponseText;
    if (receivedText == fullResponse) return;

    if (fullResponse.startsWith(visibleText)) {
      _replacePendingResponse(fullResponse.substring(visibleText.length));
      return;
    }

    // Phục hồi an toàn nếu full_response khác với các delta đã nhận.
    _messages[idx] = _messages[idx].copyWith(
      text: '',
      status: _thoughtTypewriter.hasPending
          ? MessageStatus.thinking
          : MessageStatus.streaming,
    );
    _replacePendingResponse(fullResponse);
    notifyListeners();
  }

  void _replacePendingResponse(String text) {
    _responseTypewriter.clear();
    if (_thoughtTypewriter.hasPending) {
      _deferredResponseText = text;
      return;
    }
    _deferredResponseText = '';
    _responseTypewriter.replacePending(text);
  }

  void _completePendingStream() {
    final data = _pendingDoneData;
    if (data == null ||
        _thoughtTypewriter.hasPending ||
        _responseTypewriter.hasPending ||
        _deferredResponseText.isNotEmpty) {
      return;
    }
    _pendingDoneData = null;
    _applyStreamDone(data);
  }

  void _applyStreamDone(Map<String, dynamic> data) {
    _thoughtTypewriter.clear();
    _responseTypewriter.clear();
    _deferredResponseText = '';

    final fullResponse = data['full_response'] as String? ?? '';
    final structuredData = data['structured'] as Map<String, dynamic>?;
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
          // Text đã được typewriter dựng đủ; full_response chỉ là fallback.
          text: _messages[idx].text.isNotEmpty
              ? _messages[idx].text
              : fullResponse,
          isStreaming: false,
          status: MessageStatus.done,
          structuredResponse: structuredResponse,
          suggestions: options.isNotEmpty ? options : suggestions,
          isFlowQuestion: options.isNotEmpty,
        );
      }
    }

    _isStreaming = false;
    _streamingMessageId = null;
    notifyListeners();
  }

  /// Xử lý lỗi — set error message tiếng Việt dựa trên code
  void _onError(String code, String message) {
    disconnect(); // Ensure channel is completely cleaned up and nullified
    _timeoutTimer?.cancel();
    _timeoutTimer = null;

    debugPrint('❌ [AIChatProvider] Error: $code - $message');

    // Xóa streaming placeholder nếu còn trống
    if (_streamingMessageId != null) {
      final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
      if (idx != -1 && _messages[idx].text.isEmpty) {
        _messages.removeAt(idx);
      } else if (idx != -1) {
        _messages[idx] = _messages[idx].copyWith(isStreaming: false);
      }
    }

    _isStreaming = false;
    _streamingMessageId = null;

    switch (code) {
      case 'LLM_UNAVAILABLE':
        _errorMessage =
            'Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.';
        break;
      case 'TIMEOUT':
        _errorMessage = 'Phản hồi quá lâu. Vui lòng thử lại.';
        break;
      case 'CONNECTION_ERROR':
        _errorMessage = 'Không thể kết nối đến server. Kiểm tra kết nối mạng.';
        break;
      default:
        _errorMessage = 'Có lỗi xảy ra. Nhấn để thử lại.';
    }

    notifyListeners();
  }

  /// Ngắt kết nối WebSocket và hủy tất cả subscriptions
  void disconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
    _thoughtTypewriter.clear();
    _responseTypewriter.clear();
    _pendingDoneData = null;
    _deferredResponseText = '';
  }

  @override
  void dispose() {
    disconnect();
    _thoughtTypewriter.dispose();
    _responseTypewriter.dispose();
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
}
