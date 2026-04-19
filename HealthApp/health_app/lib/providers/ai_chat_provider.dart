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
import '../constants/ai_chatbot_config.dart';
import 'exercise_provider.dart';
import 'nutrition_provider.dart';

class AIChatProvider extends ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  final List<AIChatMessage> _messages = [];
  bool _isStreaming = false;
  String? _streamingMessageId;
  String? _errorMessage;
  Timer? _timeoutTimer;
  final _uuid = const Uuid();
  String? _sessionId;

  // References to other providers for saving actions
  ExerciseProvider? _exerciseProvider;
  NutritionProvider? _nutritionProvider;

  List<AIChatMessage> get messages => List.unmodifiable(_messages);
  bool get isStreaming => _isStreaming;
  String? get errorMessage => _errorMessage;

  /// Set provider references for saving actions
  void setProviders({
    ExerciseProvider? exerciseProvider,
    NutritionProvider? nutritionProvider,
  }) {
    _exerciseProvider = exerciseProvider;
    _nutritionProvider = nutritionProvider;
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
      debugPrint('✅ [AIChatProvider] Welcome message added. Total messages: ${_messages.length}');
      notifyListeners();
    } else {
      debugPrint('ℹ️ [AIChatProvider] Already initialized. Total messages: ${_messages.length}');
    }
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
          _onError('CONNECTION_ERROR', error.toString());
        },
        onDone: () {
          debugPrint('🔌 [AIChatProvider] Connection closed');
          if (_isStreaming) {
            _onError('CONNECTION_ERROR', 'Kết nối bị ngắt');
          }
        },
      );
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Connection failed: $e');
      if (e is! TimeoutException) {
        _onError('CONNECTION_ERROR', e.toString());
      }
    }
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
    
    if (_channel == null) {
      debugPrint('🔌 [AIChatProvider] No connection, connecting...');
      await connect(_sessionId ?? _uuid.v4());
    }

    // 1. Thêm user message vào list
    _messages.add(AIChatMessage(
      id: _uuid.v4(),
      text: text,
      isUser: true,
      isStreaming: false,
      timestamp: DateTime.now(),
    ));

    // 2. Tạo streaming message placeholder
    final streamingId = _uuid.v4();
    _streamingMessageId = streamingId;
    _isStreaming = true;
    _errorMessage = null;
    _messages.add(AIChatMessage(
      id: streamingId,
      text: '',
      isUser: false,
      isStreaming: true,
      timestamp: DateTime.now(),
    ));
    notifyListeners();

    // Bắt đầu timeout 30 giây
    _timeoutTimer?.cancel();
    _timeoutTimer = Timer(AIChatbotConfig.streamTimeout, () {
      debugPrint('⏰ [AIChatProvider] Stream timeout');
      _onError('TIMEOUT', 'Phản hồi quá lâu');
    });

    // 3. Gửi ChatRequest JSON qua WebSocket
    final request = {
      'type': 'chat',
      'session_id': _sessionId,
      'message': text,
      'user_context': {
        'age': user.age,
        'gender': user.gender,
        'height': user.height,
        'weight': user.weight,
        'activity_level': user.activityLevel,
        'health_goal': user.healthGoal,
        // Today's activity context
        if (todayCalories > 0) 'today_calories_consumed': todayCalories,
        if (todayMealsCount > 0) 'today_meals_count': todayMealsCount,
        if (todayCaloriesBurned > 0) 'today_calories_burned': todayCaloriesBurned,
        if (todayExercisesCount > 0) 'today_exercises_count': todayExercisesCount,
        if (todayMeals.isNotEmpty) 'today_meals': todayMeals,
        if (todayExercises.isNotEmpty) 'today_exercises': todayExercises,
      },
    };

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
    debugPrint('📥 [AIChatProvider] Received message: ${raw.toString().substring(0, raw.toString().length > 100 ? 100 : raw.toString().length)}...');
    
    try {
      final data = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = data['type'] as String?;
      
      debugPrint('📦 [AIChatProvider] Message type: $type');

      switch (type) {
        case 'token':
          _onTokenReceived(data['content'] as String? ?? '');
          break;
        case 'done':
          debugPrint('✅ [AIChatProvider] Stream done');
          _onStreamDone(data);
          break;
        case 'error':
          debugPrint('❌ [AIChatProvider] Error received: ${data['code']} - ${data['message']}');
          _onError(
            data['code'] as String? ?? 'UNKNOWN',
            data['message'] as String? ?? '',
          );
          break;
      }
    } catch (e) {
      debugPrint('❌ [AIChatProvider] Parse error: $e');
      // Bỏ qua message không parse được
    }
  }

  /// Append token vào streaming message — chỉ update message cuối, không rebuild toàn bộ list
  void _onTokenReceived(String token) {
    if (_streamingMessageId == null) return;

    final idx = _messages.indexWhere((m) => m.id == _streamingMessageId);
    if (idx == -1) return;

    _messages[idx] = _messages[idx].copyWith(
      text: _messages[idx].text + token,
    );
    notifyListeners();
  }

  /// Lấy text hiển thị khi đang stream — ẩn tất cả data block tags
  static String getDisplayText(String text, bool isStreaming) {
    if (!isStreaming) return text;
    // Ẩn bất kỳ [TAG], **TAG**, hoặc bare JSON block khi đang stream
    final tagPattern = RegExp(
      r'(\[(ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA)\]|\*\*(ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA)\*\*|\{\s*"type"\s*:\s*"structured")',
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
          text: fullResponse.isNotEmpty ? fullResponse : _messages[idx].text,
          isStreaming: false,
          structuredResponse: structuredResponse,
          // options (flow) ưu tiên hơn suggestions
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
  }

  @override
  void dispose() {
    disconnect();
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
      final duration = details['duration'] as int? ?? 30;
      final caloriesBurned = details['calories_burned'] as num? ?? 0;
      final type = details['type'] as String? ?? 'cardio';

      final exercise = ExerciseModel(
        id: _uuid.v4(),
        userId: user.id,
        name: action.name,
        exerciseTemplateId: null, // wger exercise, no local template
        date: DateTime.now(),
        duration: duration,
        caloriesBurned: caloriesBurned.toDouble(),
        type: type,
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
    switch (mealType.toLowerCase()) {
      case 'breakfast': return 'sang';
      case 'lunch': return 'trua';
      case 'dinner': return 'toi';
      case 'snack': return 'phu';
      default: return mealType; // đã là tiếng Việt
    }
  }
}
