import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/ai_chat_provider.dart';
import '../providers/user_provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/nutrition_provider.dart';
import '../models/chat_message.dart';
import '../models/wger_models.dart';
import '../models/meal_model.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';
import '../widgets/action_card_widget.dart';
import '../widgets/detail_bottom_sheet.dart';

class ChatbotScreen extends StatefulWidget {
  const ChatbotScreen({super.key});

  @override
  State<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends State<ChatbotScreen> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
      final exerciseProvider = Provider.of<ExerciseProvider>(context, listen: false);
      final nutritionProvider = Provider.of<NutritionProvider>(context, listen: false);
      
      aiChatProvider.setProviders(
        exerciseProvider: exerciseProvider,
        nutritionProvider: nutritionProvider,
      );
      
      aiChatProvider.initialize();
      _scrollToBottom();
      aiChatProvider.addListener(_onMessagesChanged);
    });
  }

  @override
  void dispose() {
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
    aiChatProvider.removeListener(_onMessagesChanged);
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onMessagesChanged() {
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final aiChatProvider = Provider.of<AIChatProvider>(context);
    final messages = aiChatProvider.messages;
    final showTypingIndicator =
        aiChatProvider.isStreaming && messages.isNotEmpty && messages.last.text.isEmpty;

    // Determine connection status
    final bool isConnected = aiChatProvider.errorMessage == null && !aiChatProvider.isStreaming;
    final bool isConnecting = aiChatProvider.isStreaming;
    final bool hasError = aiChatProvider.errorMessage != null;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                gradient: AppColors.primaryGradient,
                borderRadius: BorderRadius.circular(10),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Icon(Icons.smart_toy, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Tư vấn sức khỏe',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        margin: const EdgeInsets.only(right: 6),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: hasError
                              ? Colors.red
                              : isConnecting
                                  ? Colors.orange
                                  : Colors.green,
                        ),
                      ),
                      Text(
                        hasError
                            ? 'Mất kết nối'
                            : isConnecting
                                ? 'Đang xử lý...'
                                : 'Sẵn sàng',
                        style: TextStyle(
                          fontSize: 11,
                          color: hasError
                              ? Colors.red
                              : AppColors.textSecondary,
                          fontWeight: FontWeight.normal,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
        automaticallyImplyLeading: false,
      ),
      body: Container(
        color: AppColors.background,
        child: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.all(16),
                itemCount: messages.length + (showTypingIndicator ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == messages.length && showTypingIndicator) {
                    return _buildTypingIndicator();
                  }
                  final msg = messages[index];
                  // Ẩn streaming bubble rỗng — typing indicator đã thay thế
                  if (msg.isStreaming && msg.text.isEmpty) {
                    return const SizedBox.shrink();
                  }
                  return AnimatedCard(
                    delay: 0,
                    child: _buildMessageBubble(messages[index]),
                  );
                },
              ),
            ),
            // Error banner
            if (aiChatProvider.errorMessage != null)
              _buildErrorBanner(aiChatProvider.errorMessage!),
            // Quick actions — chỉ hiện khi chưa có tin nhắn nào từ user
            if (messages.length <= 1 && !aiChatProvider.isStreaming)
              _buildQuickActions(),
            _buildInputArea(),
          ],
        ),
      ),    );
  }

  Widget _buildErrorBanner(String errorMessage) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: const Color(0xFFFFEBEE),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: Color(0xFFD32F2F), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              errorMessage,
              style: const TextStyle(
                fontSize: 13,
                color: Color(0xFFD32F2F),
              ),
            ),
          ),
          TextButton(
            onPressed: () {
              final text = _textController.text.trim();
              if (text.isNotEmpty) {
                _sendMessage(text);
              }
            },
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFFD32F2F),
              padding: const EdgeInsets.symmetric(horizontal: 8),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text('Thử lại',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(AIChatMessage message) {
    // Ẩn [ACTION_DATA] block khi đang stream
    final rawText = message.isStreaming
        ? AIChatProvider.getDisplayText(message.text, true)
        : message.text;
    final displayText = message.isStreaming ? '$rawText▌' : rawText;

    // Nếu có structured response, hiển thị text từ structured response
    final String finalDisplayText;
    if (!message.isUser && message.structuredResponse != null) {
      finalDisplayText = message.structuredResponse!.text.isNotEmpty 
          ? message.structuredResponse!.text 
          : displayText;
    } else {
      finalDisplayText = displayText;
    }

    return Column(
      crossAxisAlignment:
          message.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment:
              message.isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!message.isUser) ...[
              Container(
                width: 34,
                height: 34,
                margin: const EdgeInsets.only(top: 4),
                decoration: BoxDecoration(
                  gradient: AppColors.primaryGradient,
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.primary.withOpacity(0.3),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Icon(Icons.smart_toy, color: Colors.white, size: 18),
              ),
              const SizedBox(width: 10),
            ],
            Flexible(
              child: Container(
                margin: const EdgeInsets.only(bottom: 4),
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  gradient: message.isUser ? AppColors.primaryGradient : null,
                  color: message.isUser ? null : AppColors.cardDark,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(18),
                    topRight: const Radius.circular(18),
                    bottomLeft:
                        Radius.circular(message.isUser ? 18 : 4),
                    bottomRight:
                        Radius.circular(message.isUser ? 4 : 18),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: message.isUser
                          ? AppColors.primary.withOpacity(0.2)
                          : Colors.black.withOpacity(0.05),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Text(
                  finalDisplayText,
                  style: TextStyle(
                    fontSize: 14,
                    color: message.isUser
                        ? Colors.white
                        : AppColors.textPrimary,
                    height: 1.5,
                  ),
                ),
              ),
            ),
            if (message.isUser) const SizedBox(width: 10),
          ],
        ),
        
        // Render ActionCardWidget if structured response exists
        if (!message.isUser && message.structuredResponse != null)
          ..._buildActionCards(message.structuredResponse!),

        // Suggestion tags hoặc Flow option buttons
        if (!message.isUser && !message.isStreaming && message.suggestions.isNotEmpty)
          message.isFlowQuestion
              ? _buildFlowOptions(message.suggestions)
              : _buildSuggestions(message.suggestions),

        const SizedBox(height: 12),
      ],
    );
  }

  /// Build action cards from structured response
  List<Widget> _buildActionCards(StructuredResponse structuredResponse) {
    final widgets = <Widget>[];
    final foodActions = structuredResponse.foodActions;
    final exerciseActions = structuredResponse.exerciseActions;

    if (foodActions.isNotEmpty) {
      // Nhóm food actions theo meal_type để tạo nhiều card nếu AI gợi ý nhiều bữa
      final groups = <String, List<ActionItem>>{};
      for (final action in foodActions) {
        final mealType = action.details['meal_type'] as String? ?? 'sang';
        groups.putIfAbsent(mealType, () => []).add(action);
      }

      // Nếu chỉ có 1 nhóm → dùng meal_name từ structured response
      // Nếu nhiều nhóm → mỗi nhóm là 1 card riêng
      if (groups.length == 1) {
        final mealName = structuredResponse.mealName?.isNotEmpty == true
            ? structuredResponse.mealName!
            : structuredResponse.text.isNotEmpty
                ? structuredResponse.text
                : foodActions.first.name;
        widgets.add(Padding(
          padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
          child: _MealActionCard(
            mealName: mealName,
            actions: foodActions,
            onSaveAll: () => _handleSaveMealToJournal(
              mealName: mealName,
              actions: foodActions,
            ),
          ),
        ));
      } else {
        // Nhiều bữa → mỗi bữa 1 card
        final mealTypeLabels = {
          'sang': 'Bữa sáng', 'breakfast': 'Bữa sáng',
          'trua': 'Bữa trưa', 'lunch': 'Bữa trưa',
          'toi': 'Bữa tối', 'dinner': 'Bữa tối',
          'phu': 'Ăn phụ', 'snack': 'Ăn phụ',
        };
        for (final entry in groups.entries) {
          final label = mealTypeLabels[entry.key] ?? entry.key;
          widgets.add(Padding(
            padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
            child: _MealActionCard(
              mealName: label,
              actions: entry.value,
              onSaveAll: () => _handleSaveMealToJournal(
                mealName: label,
                actions: entry.value,
              ),
            ),
          ));
        }
      }
    }

    for (final action in exerciseActions) {
      widgets.add(Padding(
        padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
        child: ActionCardWidget(
          action: action,
          onSaveToJournal: () => _handleSaveToJournal(action),
          onViewDetail: () => _handleViewDetail(action),
        ),
      ));
    }

    return widgets;
  }

  /// Lưu food actions thành 1 MealModel với nhiều MealItem
  Future<void> _handleSaveMealToJournal({
    required String mealName,
    required List<ActionItem> actions,
  }) async {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null || actions.isEmpty) return;

    // Hỏi người dùng muốn lưu vào bữa nào
    final mealType = await _showMealTypeDialog(
      defaultType: _mapMealType(actions.first.details['meal_type'] as String? ?? 'sang'),
    );
    if (mealType == null) return; // Người dùng huỷ

    try {
      final items = actions.map((action) {
        final details = action.details;
        final cal100g = (details['calories'] as num? ?? 0).toDouble();
        final pro100g = (details['protein'] as num? ?? 0).toDouble();
        final carb100g = (details['carbs'] as num? ?? 0).toDouble();
        final fat100g = (details['fat'] as num? ?? 0).toDouble();
        final grams = (details['serving_grams'] as num? ?? 100).toDouble();

        return MealItem(
          id: '${action.name}_${DateTime.now().millisecondsSinceEpoch}',
          foodId: action.wgerId.toString(),
          name: action.name,
          weightGrams: grams,
          calories: cal100g * grams / 100,
          protein: pro100g * grams / 100,
          carbs: carb100g * grams / 100,
          fat: fat100g * grams / 100,
        );
      }).toList();

      final meal = MealModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: user.id,
        name: mealName,
        date: DateTime.now(),
        mealType: mealType,
        items: items,
      );

      Provider.of<NutritionProvider>(context, listen: false).addMeal(meal);

      if (mounted) {
        final totalCal = items.fold(0.0, (s, i) => s + i.calories);
        final mealLabel = _mealTypeLabel(mealType);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✅ Đã lưu "$mealName" vào $mealLabel (${totalCal.toStringAsFixed(0)} kcal)'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('❌ Lỗi khi lưu: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// Dialog chọn bữa ăn
  Future<String?> _showMealTypeDialog({required String defaultType}) async {
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Lưu vào bữa nào?', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        contentPadding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _mealTypeOption(ctx, 'sang',  '🌅', 'Bữa sáng',  defaultType),
            _mealTypeOption(ctx, 'trua',  '☀️', 'Bữa trưa',  defaultType),
            _mealTypeOption(ctx, 'toi',   '🌙', 'Bữa tối',   defaultType),
            _mealTypeOption(ctx, 'phu',   '🍎', 'Ăn phụ',    defaultType),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Huỷ'),
          ),
        ],
      ),
    );
  }

  Widget _mealTypeOption(BuildContext ctx, String type, String emoji, String label, String defaultType) {
    final isDefault = type == defaultType;
    return GestureDetector(
      onTap: () => Navigator.pop(ctx, type),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: isDefault ? AppColors.primary.withOpacity(0.08) : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isDefault ? AppColors.primary.withOpacity(0.4) : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            Text(emoji, style: const TextStyle(fontSize: 20)),
            const SizedBox(width: 12),
            Text(label, style: TextStyle(
              fontSize: 15,
              fontWeight: isDefault ? FontWeight.w700 : FontWeight.w500,
              color: isDefault ? AppColors.primary : AppColors.textPrimary,
            )),
            const Spacer(),
            if (isDefault)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text('Gợi ý', style: TextStyle(fontSize: 11, color: AppColors.primary, fontWeight: FontWeight.w600)),
              ),
          ],
        ),
      ),
    );
  }

  String _mealTypeLabel(String type) {
    switch (type) {
      case 'sang': return 'bữa sáng';
      case 'trua': return 'bữa trưa';
      case 'toi':  return 'bữa tối';
      case 'phu':  return 'ăn phụ';
      default: return type;
    }
  }

  String _mapMealType(String t) {
    switch (t.toLowerCase()) {
      case 'breakfast': return 'sang';
      case 'lunch': return 'trua';
      case 'dinner': return 'toi';
      case 'snack': return 'phu';
      default: return t;
    }
  }

  /// Handle "Lưu vào nhật ký" button press
  Future<void> _handleSaveToJournal(ActionItem action) async {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;

    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);

    try {
      if (action.kind == 'exercise') {
        // Save exercise directly
        await aiChatProvider.saveExerciseFromAction(action, user);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('✅ Đã lưu bài tập "${action.name}" vào nhật ký'),
              duration: const Duration(seconds: 2),
              backgroundColor: Colors.green,
            ),
          );
        }
      } else if (action.kind == 'food') {
        // Nếu AI đã cung cấp serving_grams, dùng luôn không cần hỏi
        final servingGrams = action.details['serving_grams'];
        if (servingGrams != null) {
          final grams = (servingGrams as num).toDouble();
          await aiChatProvider.saveFoodFromAction(action, grams, user);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('✅ Đã lưu "${action.name}" (${grams.toStringAsFixed(0)}g) vào nhật ký'),
                duration: const Duration(seconds: 2),
                backgroundColor: Colors.green,
              ),
            );
          }
        } else {
          // Không có serving_grams → hỏi người dùng
          final grams = await _showGramsInputDialog(action.name);
          if (grams != null && grams > 0) {
            await aiChatProvider.saveFoodFromAction(action, grams, user);
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('✅ Đã lưu "${action.name}" (${grams.toStringAsFixed(0)}g) vào nhật ký'),
                  duration: const Duration(seconds: 2),
                  backgroundColor: Colors.green,
                ),
              );
            }
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ Lỗi khi lưu: $e'),
            duration: const Duration(seconds: 2),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  /// Show dialog to input grams for food
  Future<double?> _showGramsInputDialog(String foodName) async {
    final controller = TextEditingController(text: '100');
    
    return showDialog<double>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Nhập khối lượng'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Bạn đã ăn bao nhiêu gram "$foodName"?'),
            const SizedBox(height: 16),
            TextField(
              controller: controller,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Khối lượng (gram)',
                border: OutlineInputBorder(),
                suffixText: 'g',
              ),
              autofocus: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () {
              final grams = double.tryParse(controller.text);
              Navigator.of(context).pop(grams);
            },
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
  }

  /// Flow option buttons — hiện khi đang trong conversation flow
  Widget _buildFlowOptions(List<String> options) {
    return Padding(
      padding: const EdgeInsets.only(left: 44, top: 10, right: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: options.asMap().entries.map((entry) {
          final i = entry.key;
          final opt = entry.value;
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: GestureDetector(
              onTap: () => _sendMessage(opt),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.primary.withOpacity(0.3)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    Container(
                      width: 28, height: 28,
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Center(
                        child: Text(
                          '${i + 1}',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: AppColors.primary,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        opt,
                        style: const TextStyle(
                          fontSize: 14,
                          color: Color(0xFF1A1A1A),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    Icon(Icons.chevron_right,
                        size: 18, color: AppColors.primary.withOpacity(0.5)),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  /// Quick action buttons — hiện khi mới vào chat
  Widget _buildQuickActions() {
    final nutritionProvider = Provider.of<NutritionProvider>(context, listen: false);
    final exerciseProvider = Provider.of<ExerciseProvider>(context, listen: false);

    final todayMeals = nutritionProvider.todayMeals;
    final todayExercises = exerciseProvider.todayExercises;
    final totalCal = nutritionProvider.totalCalories;
    final burnedCal = exerciseProvider.totalCaloriesBurned;

    final hasTodayData = todayMeals.isNotEmpty || todayExercises.isNotEmpty;

    final actions = [
      ('🏋️', 'Tạo bài tập', 'Tạo bài tập hôm nay cho tôi'),
      ('🥗', 'Gợi ý bữa ăn', 'Gợi ý bữa ăn phù hợp với tôi'),
      ('📊', 'Tính calo', 'Tính calo và TDEE của tôi'),
      ('💪', 'Lịch tập tuần', 'Tạo lịch tập luyện cho cả tuần'),
    ];

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Today's summary card (if data exists)
          if (hasTodayData) ...[
            Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppColors.primary.withOpacity(0.08)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.today, size: 14, color: AppColors.textSecondary),
                      const SizedBox(width: 6),
                      const Text(
                        'Hôm nay của bạn',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textSecondary),
                      ),
                      const Spacer(),
                      GestureDetector(
                        onTap: () {
                          final summary = _buildTodaySummaryMessage(todayMeals, todayExercises, totalCal, burnedCal);
                          _sendMessage(summary);
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: AppColors.primary.withOpacity(0.08),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            'Hỏi AI phân tích',
                            style: TextStyle(fontSize: 11, color: AppColors.primary, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      if (todayMeals.isNotEmpty) ...[
                        Expanded(
                          child: _buildContextStat(
                            '🍽️',
                            '${totalCal.toStringAsFixed(0)} kcal',
                            '${todayMeals.length} bữa ăn',
                            AppColors.calories,
                          ),
                        ),
                        const SizedBox(width: 8),
                      ],
                      if (todayExercises.isNotEmpty)
                        Expanded(
                          child: _buildContextStat(
                            '🏃',
                            '${burnedCal.toStringAsFixed(0)} kcal',
                            '${todayExercises.length} bài tập',
                            AppColors.success,
                          ),
                        ),
                    ],
                  ),
                  if (todayMeals.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      '${nutritionProvider.completedMealsCount} đã ăn · ${nutritionProvider.pendingMealsCount} sắp ăn',
                      style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                    ),
                  ],
                ],
              ),
            ),
          ],
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'Bắt đầu nhanh',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: actions.map((a) => GestureDetector(
              onTap: () => _sendMessage(a.$3),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: AppColors.primary.withOpacity(0.25)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(a.$1, style: const TextStyle(fontSize: 14)),
                    const SizedBox(width: 6),
                    Text(
                      a.$2,
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.textPrimary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            )).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildContextStat(String emoji, String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 16)),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: color)),
              Text(label, style: const TextStyle(fontSize: 10, color: AppColors.textSecondary)),
            ],
          ),
        ],
      ),
    );
  }

  String _buildTodaySummaryMessage(
    List<dynamic> meals,
    List<dynamic> exercises,
    double totalCal,
    double burnedCal,
  ) {
    final buffer = StringBuffer('Hôm nay tôi đã:\n');
    if (meals.isNotEmpty) {
      buffer.write('- Ăn ${meals.length} bữa, tổng ${totalCal.toStringAsFixed(0)} kcal\n');
    }
    if (exercises.isNotEmpty) {
      buffer.write('- Tập ${exercises.length} bài tập, đốt ${burnedCal.toStringAsFixed(0)} kcal\n');
    }
    buffer.write('\nHãy phân tích và cho tôi lời khuyên.');
    return buffer.toString();
  }

  /// Build suggestion tags
  Widget _buildSuggestions(List<String> suggestions) {
    return Padding(
      padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: suggestions.map((s) => GestureDetector(
          onTap: () => _sendMessage(s),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.08),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: AppColors.primary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.add_circle_outline,
                    size: 14, color: AppColors.primary.withOpacity(0.8)),
                const SizedBox(width: 5),
                Text(
                  s,
                  style: TextStyle(
                    fontSize: 13,
                    color: AppColors.primary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        )).toList(),
      ),
    );
  }

  /// Handle "Xem chi tiết" button press — hiển thị bottom sheet với thông tin đầy đủ từ wger
  void _handleViewDetail(ActionItem action) {
    showDetailBottomSheet(
      context,
      action,
      onSave: () => _handleSaveToJournal(action),
    );
  }

  Widget _buildTypingIndicator() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              gradient: AppColors.primaryGradient,
              borderRadius: BorderRadius.circular(10),
              boxShadow: [
                BoxShadow(
                  color: AppColors.primary.withOpacity(0.3),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: const Icon(Icons.smart_toy, color: Colors.white, size: 18),
          ),
          const SizedBox(width: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.cardDark,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(18),
                topRight: Radius.circular(18),
                bottomRight: Radius.circular(18),
                bottomLeft: Radius.circular(4),
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: const _TypingDots(),
          ),
        ],
      ),
    );
  }

  Widget _buildInputArea() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: SafeArea(
        child: Row(
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(26),
                ),
                child: TextField(
                  controller: _textController,
                  decoration: const InputDecoration(
                    hintText: 'Nhập triệu chứng hoặc câu hỏi...',
                    hintStyle:
                        TextStyle(color: AppColors.textHint, fontSize: 14),
                    border: InputBorder.none,
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  ),
                  maxLines: null,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _handleSubmit(),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: AppColors.primaryGradient,
                borderRadius: BorderRadius.circular(24),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.4),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: IconButton(
                icon: const Icon(Icons.send_rounded, color: Colors.white, size: 22),
                onPressed: _handleSubmit,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _handleSubmit() {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _sendMessage(text);
  }

  void _sendMessage(String text) {
    _textController.clear();
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;

    final nutritionProvider = Provider.of<NutritionProvider>(context, listen: false);
    final exerciseProvider = Provider.of<ExerciseProvider>(context, listen: false);

    // Chuyển bữa ăn hôm nay thành dạng gọn để gửi lên AI
    final todayMeals = nutritionProvider.todayMeals.map((meal) {
      return {
        'name': meal.name,
        'meal_type': meal.mealType,
        'calories': meal.calories.toStringAsFixed(0),
        'protein': meal.protein.toStringAsFixed(1),
        'carbs': meal.carbs.toStringAsFixed(1),
        'fat': meal.fat.toStringAsFixed(1),
        'items': meal.items.map((i) => '${i.name} ${i.weightGrams.toStringAsFixed(0)}g').toList(),
        'is_completed': meal.isCompleted,
      };
    }).toList();

    // Chuyển bài tập hôm nay
    final todayExercises = exerciseProvider.todayExercises.map((ex) {
      return {
        'name': ex.name,
        'type': ex.type,
        'duration': ex.duration,
        'calories_burned': ex.caloriesBurned.toStringAsFixed(0),
      };
    }).toList();

    Provider.of<AIChatProvider>(context, listen: false).sendMessage(
      text,
      user,
      todayCalories: nutritionProvider.totalCalories,
      todayMealsCount: nutritionProvider.todayMeals.length,
      todayCaloriesBurned: exerciseProvider.totalCaloriesBurned,
      todayExercisesCount: exerciseProvider.todayExercises.length,
      todayMeals: todayMeals,
      todayExercises: todayExercises,
    );
  }
}

// === Typing dots animation ===
class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> with TickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (index) {
            final delay = index * 0.2;
            final bounce = ((_controller.value - delay) % 1.0);
            final opacity = bounce < 0.5 ? bounce * 2 : (1 - bounce) * 2;
            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 2),
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(opacity.clamp(0.3, 1.0)),
                shape: BoxShape.circle,
              ),
            );
          }),
        );
      },
    );
  }
}

// ═══════════════════════════════════════════════════════════════
// Card hiển thị món ăn gợi ý từ AI (nhóm nhiều nguyên liệu)
// ═══════════════════════════════════════════════════════════════
class _MealActionCard extends StatelessWidget {
  final String mealName;
  final List<ActionItem> actions;
  final VoidCallback onSaveAll;

  const _MealActionCard({
    required this.mealName,
    required this.actions,
    required this.onSaveAll,
  });

  @override
  Widget build(BuildContext context) {
    final totalCal = actions.fold(0.0, (sum, a) {
      final cal = (a.details['calories'] as num? ?? 0).toDouble();
      final g = (a.details['serving_grams'] as num? ?? 100).toDouble();
      return sum + cal * g / 100;
    });
    final totalProtein = actions.fold(0.0, (sum, a) {
      final p = (a.details['protein'] as num? ?? 0).toDouble();
      final g = (a.details['serving_grams'] as num? ?? 100).toDouble();
      return sum + p * g / 100;
    });
    final totalCarbs = actions.fold(0.0, (sum, a) {
      final c = (a.details['carbs'] as num? ?? 0).toDouble();
      final g = (a.details['serving_grams'] as num? ?? 100).toDouble();
      return sum + c * g / 100;
    });
    final totalFat = actions.fold(0.0, (sum, a) {
      final f = (a.details['fat'] as num? ?? 0).toDouble();
      final g = (a.details['serving_grams'] as num? ?? 100).toDouble();
      return sum + f * g / 100;
    });

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF4CAF50).withOpacity(0.25), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4CAF50).withOpacity(0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
            decoration: BoxDecoration(
              color: const Color(0xFF4CAF50).withOpacity(0.06),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(14),
                topRight: Radius.circular(14),
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFF4CAF50).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.restaurant_menu, color: Color(0xFF4CAF50), size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(mealName,
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Color(0xFF1A1A1A))),
                      Text('${actions.length} nguyên liệu',
                          style: const TextStyle(fontSize: 12, color: Color(0xFF4CAF50))),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(totalCal.toStringAsFixed(0),
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.calories)),
                    const Text('kcal', style: TextStyle(fontSize: 10, color: AppColors.textSecondary)),
                  ],
                ),
              ],
            ),
          ),

          // Danh sách nguyên liệu
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
            child: Column(
              children: [
                ...actions.map((a) {
                  final g = (a.details['serving_grams'] as num? ?? 100).toDouble();
                  final cal = (a.details['calories'] as num? ?? 0).toDouble() * g / 100;
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      children: [
                        const Icon(Icons.fiber_manual_record, size: 6, color: AppColors.textHint),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text('${a.name}  ${g.toStringAsFixed(0)}g',
                              style: const TextStyle(fontSize: 13)),
                        ),
                        Text('${cal.toStringAsFixed(0)} kcal',
                            style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                      ],
                    ),
                  );
                }),
                const SizedBox(height: 4),
                // Macro tổng
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _macroChip('P', totalProtein, AppColors.protein),
                      _macroChip('C', totalCarbs, AppColors.carbs),
                      _macroChip('F', totalFat, AppColors.fat),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const Divider(height: 1),

          // Nút lưu
          Padding(
            padding: const EdgeInsets.all(10),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: onSaveAll,
                icon: const Icon(Icons.bookmark_add_outlined, size: 16),
                label: Text('Lưu "$mealName" vào nhật ký'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4CAF50),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _macroChip(String label, double value, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$label:', style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
        const SizedBox(width: 3),
        Text('${value.toStringAsFixed(0)}g', style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
      ],
    );
  }
}
