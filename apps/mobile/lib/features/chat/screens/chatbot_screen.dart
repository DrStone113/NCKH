import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/ai_chat_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/lifestyle_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../models/chat_message.dart';
import '../../../models/wger_models.dart';
import '../../../models/meal_model.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/action_card_widget.dart';
import '../../../widgets/detail_bottom_sheet.dart';
import '../../../services/backend_api_service.dart';
import '../../../widgets/formatted_markdown_text.dart';

class ChatbotScreen extends StatefulWidget {
  const ChatbotScreen({super.key});

  @override
  State<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends State<ChatbotScreen> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final BackendApiService _backendApi = BackendApiService();
  Map<String, dynamic>? _activePlan;
  bool _isLoadingPlan = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final aiChatProvider =
          Provider.of<AIChatProvider>(context, listen: false);
      final exerciseProvider =
          Provider.of<ExerciseProvider>(context, listen: false);
      final nutritionProvider =
          Provider.of<NutritionProvider>(context, listen: false);
      final lifestyleProvider =
          Provider.of<LifestyleProvider>(context, listen: false);
      final healthProvider =
          Provider.of<HealthProvider>(context, listen: false);

      aiChatProvider.setProviders(
        exerciseProvider: exerciseProvider,
        nutritionProvider: nutritionProvider,
        lifestyleProvider: lifestyleProvider,
        healthProvider: healthProvider,
      );

      if (aiChatProvider.messages.isEmpty) {
        aiChatProvider.initialize();
      }
      _loadActivePlan();
      _scrollToBottom();
      aiChatProvider.addListener(_onMessagesChanged);
    });
  }

  Future<void> _loadActivePlan() async {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;
    setState(() => _isLoadingPlan = true);
    try {
      final plan = await _backendApi.getActivePlan(user.id);
      if (!mounted) return;
      setState(() => _activePlan = plan);
    } catch (_) {
      if (!mounted) return;
      setState(() => _activePlan = null);
    } finally {
      if (mounted) setState(() => _isLoadingPlan = false);
    }
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
                    color: AppColors.primary.withValues(alpha: 0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Icon(Icons.smart_toy, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Tư vấn sức khỏe',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Row(
                  mainAxisSize: MainAxisSize.min,
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
                        color:
                            hasError ? Colors.red : AppColors.textSecondary,
                        fontWeight: FontWeight.normal,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'Tạo cuộc trò chuyện mới',
            onPressed: () {
              aiChatProvider.startNewSession();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Đã tạo cuộc trò chuyện mới'),
                  duration: Duration(seconds: 2),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: 'Lịch sử hội thoại',
            onPressed: () => _showHistoryBottomSheet(context),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Container(
        color: AppColors.background,
        child: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.all(16),
                itemCount: messages.length,
                itemBuilder: (context, index) {
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
            if (_isLoadingPlan || _activePlan != null) _buildActivePlanCard(),
            _buildInputArea(),
          ],
        ),
      ),
    );
  }

  void _showHistoryBottomSheet(BuildContext context) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (modalContext) {
        return Container(
          height: MediaQuery.of(modalContext).size.height * 0.7,
          decoration: const BoxDecoration(
            color: AppColors.surfaceLight,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              Container(
                margin: const EdgeInsets.only(top: 10, bottom: 6),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey[300],
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Lịch sử hội thoại',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    TextButton.icon(
                      onPressed: () {
                        Navigator.pop(modalContext);
                        aiChatProvider.startNewSession();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Đã tạo cuộc trò chuyện mới'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                      },
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('Tạo mới'),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: FutureBuilder<List<Map<String, dynamic>>>(
                  future: _backendApi.getChatSessions(userId: user?.id),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (snapshot.hasError) {
                      return Center(
                        child: Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Text(
                            'Không thể tải lịch sử: ${snapshot.error}',
                            style: const TextStyle(color: Colors.red),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      );
                    }
                    final sessions = snapshot.data ?? [];
                    if (sessions.isEmpty) {
                      return const Center(
                        child: Text(
                          'Chưa có cuộc hội thoại cũ nào.',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                      );
                    }

                    return ListView.separated(
                      padding: const EdgeInsets.all(12),
                      itemCount: sessions.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final session = sessions[index];
                        final sessionId = session['id'] ?? '';
                        final title = session['title'] ?? 'Cuộc trò chuyện';
                        final isCurrent =
                            sessionId == aiChatProvider.currentSessionId;
                        final timeStr =
                            session['last_active'] ?? session['created_at'];

                        String formattedTime = '';
                        if (timeStr != null) {
                          final dt = DateTime.tryParse(timeStr.toString());
                          if (dt != null) {
                            formattedTime =
                                '${dt.day}/${dt.month}/${dt.year} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
                          }
                        }

                        return ListTile(
                          leading: CircleAvatar(
                            backgroundColor: isCurrent
                                ? AppColors.primary.withValues(alpha: 0.2)
                                : Colors.grey[200],
                            child: Icon(
                              Icons.chat_bubble_outline,
                              color: isCurrent
                                  ? AppColors.primary
                                  : Colors.grey[600],
                              size: 20,
                            ),
                          ),
                          title: Text(
                            title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontWeight: isCurrent
                                  ? FontWeight.bold
                                  : FontWeight.normal,
                              color: isCurrent
                                  ? AppColors.primary
                                  : AppColors.textPrimary,
                            ),
                          ),
                          subtitle: formattedTime.isNotEmpty
                              ? Text(formattedTime,
                                  style: const TextStyle(fontSize: 12))
                              : null,
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline,
                                color: Colors.redAccent, size: 20),
                            onPressed: () async {
                              final messenger = ScaffoldMessenger.of(context);
                              try {
                                await _backendApi.deleteChatSession(sessionId);
                                if (isCurrent) {
                                  aiChatProvider.startNewSession();
                                }
                                if (modalContext.mounted) {
                                  Navigator.pop(modalContext);
                                }
                                messenger.showSnackBar(
                                  const SnackBar(
                                      content: Text('Đã xóa cuộc trò chuyện')),
                                );
                              } catch (e) {
                                messenger.showSnackBar(
                                  SnackBar(content: Text('Lỗi xóa: $e')),
                                );
                              }
                            },
                          ),
                          onTap: () async {
                            final messenger = ScaffoldMessenger.of(context);
                            try {
                              final messages = await _backendApi
                                  .getSessionMessages(sessionId);
                              aiChatProvider.loadExistingSession(
                                  sessionId, messages);
                              if (modalContext.mounted) {
                                Navigator.pop(modalContext);
                              }
                              _scrollToBottom();
                            } catch (e) {
                              messenger.showSnackBar(
                                SnackBar(
                                    content:
                                        Text('Không thể tải tin nhắn: $e')),
                              );
                            }
                          },
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildActivePlanCard() {
    if (_isLoadingPlan) {
      return const Padding(
        padding: EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: LinearProgressIndicator(minHeight: 2),
      );
    }
    final plan = _activePlan;
    if (plan == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
        ),
        child: Row(
          children: [
            const Icon(Icons.event_note, color: AppColors.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Kế hoạch active: ${plan['duration_days']} ngày • ${plan['goal']}',
                style:
                    const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ),
            TextButton(
              onPressed: () => _sendMessage('Xem kế hoạch hiện tại của tôi'),
              child: const Text('Xem'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBanner(String errorMessage) {
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
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
          TextButton.icon(
            onPressed: () {
              // Ưu tiên retry tin nhắn cuối, fallback về text trong ô nhập
              if (aiChatProvider.canRetry) {
                aiChatProvider.retryLastMessage();
              } else {
                final text = _textController.text.trim();
                if (text.isNotEmpty) {
                  _sendMessage(text);
                }
              }
            },
            icon: const Icon(Icons.refresh, size: 15, color: Color(0xFFD32F2F)),
            label: const Text('Thử lại',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFFD32F2F),
              padding: const EdgeInsets.symmetric(horizontal: 8),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(AIChatMessage message) {
    // Bot đang thinking → hiện indicator trạng thái kèm thoughts nếu có
    if (message.isThinking) {
      return _buildThinkingBubble(message);
    }

    // Nếu có structured response, dùng text từ đó
    final String displayText;
    if (!message.isUser && message.structuredResponse != null) {
      displayText = message.structuredResponse!.text.isNotEmpty
          ? message.structuredResponse!.text
          : message.text;
    } else {
      displayText = message.isUser
          ? message.text
          : AIChatProvider.getDisplayText(message.text, message.isStreaming);
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
                      color: AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child:
                    const Icon(Icons.smart_toy, color: Colors.white, size: 18),
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
                    bottomLeft: Radius.circular(message.isUser ? 18 : 4),
                    bottomRight: Radius.circular(message.isUser ? 4 : 18),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: message.isUser
                          ? AppColors.primary.withValues(alpha: 0.2)
                          : Colors.black.withValues(alpha: 0.05),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (!message.isUser && message.thoughts.isNotEmpty) ...[
                      AIThoughtsPanel(
                        thoughts: message.thoughts,
                        isThinking: false,
                      ),
                      const SizedBox(height: 10),
                      Divider(
                        height: 1,
                        color: AppColors.textHint.withValues(alpha: 0.15),
                      ),
                      const SizedBox(height: 10),
                    ],
                    message.isUser
                        ? Text(
                            displayText,
                            style: const TextStyle(
                              fontSize: 14,
                              color: Colors.white,
                              height: 1.5,
                            ),
                          )
                        : FormattedMarkdownText(
                            text: displayText,
                            style: const TextStyle(
                              fontSize: 14,
                              color: AppColors.textPrimary,
                              height: 1.5,
                            ),
                          ),
                  ],
                ),
              ),
            ),
            if (message.isUser) const SizedBox(width: 10),
          ],
        ),

        // Action cards
        if (!message.isUser && message.structuredResponse != null)
          ..._buildActionCards(message),

        // Suggestions / flow options
        if (!message.isUser &&
            message.status == MessageStatus.done &&
            message.suggestions.isNotEmpty)
          message.isFlowQuestion
              ? _buildFlowOptions(message.suggestions)
              : _buildSuggestions(message.suggestions),

        const SizedBox(height: 12),
      ],
    );
  }

  /// Bubble "Đang suy nghĩ..." với animated dots + label trạng thái và thoughts panel nếu có
  Widget _buildThinkingBubble(AIChatMessage message) {
    final statusText = message.statusText.isNotEmpty ? message.statusText : 'Đang suy nghĩ...';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              gradient: AppColors.primaryGradient,
              borderRadius: BorderRadius.circular(10),
              boxShadow: [
                BoxShadow(
                  color: AppColors.primary.withValues(alpha: 0.3),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: const Icon(Icons.smart_toy, color: Colors.white, size: 18),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
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
                        color: Colors.black.withValues(alpha: 0.05),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const _TypingDots(),
                      const SizedBox(width: 10),
                      Flexible(
                        child: Text(
                          statusText,
                          style: const TextStyle(
                            fontSize: 13,
                            color: AppColors.textSecondary,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (message.thoughts.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  AIThoughtsPanel(
                    thoughts: message.thoughts,
                    isThinking: true,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Build action cards from structured response
  List<Widget> _buildActionCards(AIChatMessage message) {
    final structuredResponse = message.structuredResponse!;
    final widgets = <Widget>[];
    final foodActions = structuredResponse.foodActions;
    final exerciseActions = structuredResponse.exerciseActions;
    final bool showSaveButton = !message.text.contains('✅');

    if (foodActions.isNotEmpty) {
      // Kiểm tra có phải weekly plan không (có field "day")
      final isWeekly = foodActions.any((a) => a.details.containsKey('day'));

      if (isWeekly) {
        // Nhóm theo day → dish_name
        final dayGroups = <int, Map<String, List<ActionItem>>>{};
        for (final action in foodActions) {
          final day = (action.details['day'] as num?)?.toInt() ?? 1;
          final dishName = action.details['dish_name'] as String? ?? '';
          final mealType = action.details['meal_type'] as String? ?? 'lunch';
          final key =
              dishName.isNotEmpty ? dishName : _getMealTypeLabel(mealType);
          dayGroups
              .putIfAbsent(day, () => {})
              .putIfAbsent(key, () => [])
              .add(action);
        }

        const dayLabels = [
          '',
          'Thứ 2',
          'Thứ 3',
          'Thứ 4',
          'Thứ 5',
          'Thứ 6',
          'Thứ 7',
          'Chủ nhật'
        ];
        final sortedDays = dayGroups.keys.toList()..sort();

        for (final day in sortedDays) {
          final label = day >= 1 && day <= 7 ? dayLabels[day] : 'Ngày $day';
          // Header ngày
          widgets.add(Padding(
            padding:
                const EdgeInsets.only(left: 44, top: 14, right: 10, bottom: 4),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.primary.withValues(alpha: 0.25)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.calendar_today,
                      size: 14, color: AppColors.primary),
                  const SizedBox(width: 6),
                  Text(label,
                      style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: AppColors.primary)),
                ],
              ),
            ),
          ));

          // Các bữa trong ngày
          final mealOrder = ['breakfast', 'lunch', 'dinner', 'snack'];
          final dishMap = dayGroups[day] ?? {};
          // Sắp xếp theo meal_type
          final sortedDishes = dishMap.entries.toList()
            ..sort((a, b) {
              final ma = mealOrder
                  .indexOf(a.value.first.details['meal_type'] as String? ?? '');
              final mb = mealOrder
                  .indexOf(b.value.first.details['meal_type'] as String? ?? '');
              return ma.compareTo(mb);
            });

          for (final entry in sortedDishes) {
            final dishName = entry.key;
            final actions = entry.value;
            final mealType =
                actions.first.details['meal_type'] as String? ?? 'lunch';
            widgets.add(Padding(
              padding: const EdgeInsets.only(left: 44, top: 6, right: 10),
              child: _MealActionCard(
                mealName: dishName,
                mealType: mealType,
                actions: actions,
                onSaveAll: showSaveButton
                    ? () => _handleSaveMealToJournal(
                          mealName: dishName,
                          actions: actions,
                        )
                    : null,
              ),
            ));
          }
        }
      } else {
        // Single day — logic cũ
        final dishGroups = <String, List<ActionItem>>{};
        for (final action in foodActions) {
          final dishName = action.details['dish_name'] as String?;
          final mealType = action.details['meal_type'] as String? ?? 'lunch';
          final key = (dishName != null && dishName.isNotEmpty)
              ? dishName
              : _getMealTypeLabel(mealType);
          dishGroups.putIfAbsent(key, () => []).add(action);
        }

        for (final entry in dishGroups.entries) {
          final dishName = entry.key;
          final actions = entry.value;
          final mealType =
              actions.first.details['meal_type'] as String? ?? 'lunch';
          widgets.add(Padding(
            padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
            child: _MealActionCard(
              mealName: dishName,
              mealType: mealType,
              actions: actions,
              onSaveAll: showSaveButton
                  ? () => _handleSaveMealToJournal(
                        mealName: dishName,
                        actions: actions,
                      )
                  : null,
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
          onSaveToJournal: showSaveButton ? () => _handleSaveToJournal(action) : null,
          onViewDetail: () => _handleViewDetail(action),
        ),
      ));
    }

    return widgets;
  }

  /// Helper: Lấy label tiếng Việt cho meal_type
  String _getMealTypeLabel(String mealType) {
    const labels = {
      'sang': 'Bữa sáng',
      'breakfast': 'Bữa sáng',
      'trua': 'Bữa trưa',
      'lunch': 'Bữa trưa',
      'toi': 'Bữa tối',
      'dinner': 'Bữa tối',
      'phu': 'Ăn phụ',
      'snack': 'Ăn phụ',
    };
    return labels[mealType.toLowerCase()] ?? 'Bữa ăn';
  }

  /// Lưu food actions thành 1 MealModel với nhiều MealItem
  Future<void> _handleSaveMealToJournal({
    required String mealName,
    required List<ActionItem> actions,
  }) async {
    final messenger = ScaffoldMessenger.of(context);
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final nutritionProvider = Provider.of<NutritionProvider>(context, listen: false);
    final user = userProvider.currentUser;
    if (user == null || actions.isEmpty) return;

    // Hỏi người dùng muốn lưu vào bữa nào
    final mealType = await _showMealTypeDialog(
      defaultType:
          _mapMealType(actions.first.details['meal_type'] as String? ?? 'sang'),
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

      nutritionProvider.addMeal(meal);

      if (mounted) {
        final totalCal = items.fold(0.0, (s, i) => s + i.calories);
        final mealLabel = _mealTypeLabel(mealType);
        messenger.showSnackBar(
          SnackBar(
            content: Text(
                '✅ Đã lưu "$mealName" vào $mealLabel (${totalCal.toStringAsFixed(0)} kcal)'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('❌ Lỗi khi lưu: $e'), backgroundColor: Colors.red),
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
        title: const Text('Lưu vào bữa nào?',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        contentPadding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _mealTypeOption(ctx, 'sang', '🌅', 'Bữa sáng', defaultType),
            _mealTypeOption(ctx, 'trua', '☀️', 'Bữa trưa', defaultType),
            _mealTypeOption(ctx, 'toi', '🌙', 'Bữa tối', defaultType),
            _mealTypeOption(ctx, 'phu', '🍎', 'Ăn phụ', defaultType),
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

  Widget _mealTypeOption(BuildContext ctx, String type, String emoji,
      String label, String defaultType) {
    final isDefault = type == defaultType;
    return GestureDetector(
      onTap: () => Navigator.pop(ctx, type),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: isDefault
              ? AppColors.primary.withValues(alpha: 0.08)
              : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isDefault
                ? AppColors.primary.withValues(alpha: 0.4)
                : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            Text(emoji, style: const TextStyle(fontSize: 20)),
            const SizedBox(width: 12),
            Text(label,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: isDefault ? FontWeight.w700 : FontWeight.w500,
                  color: isDefault ? AppColors.primary : AppColors.textPrimary,
                )),
            const Spacer(),
            if (isDefault)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text('Gợi ý',
                    style: TextStyle(
                        fontSize: 11,
                        color: AppColors.primary,
                        fontWeight: FontWeight.w600)),
              ),
          ],
        ),
      ),
    );
  }

  String _mealTypeLabel(String type) {
    switch (type) {
      case 'sang':
        return 'bữa sáng';
      case 'trua':
        return 'bữa trưa';
      case 'toi':
        return 'bữa tối';
      case 'phu':
        return 'ăn phụ';
      default:
        return type;
    }
  }

  String _mapMealType(String t) {
    switch (t.toLowerCase()) {
      case 'breakfast':
        return 'sang';
      case 'lunch':
        return 'trua';
      case 'dinner':
        return 'toi';
      case 'snack':
        return 'phu';
      default:
        return t;
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
                content: Text(
                    '✅ Đã lưu "${action.name}" (${grams.toStringAsFixed(0)}g) vào nhật ký'),
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
                  content: Text(
                      '✅ Đã lưu "${action.name}" (${grams.toStringAsFixed(0)}g) vào nhật ký'),
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
        title: const Text('Nhập khối lượng'),
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
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.primary.withValues(alpha: 0.3)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.04),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Center(
                        child: Text(
                          '${i + 1}',
                          style: const TextStyle(
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
                        size: 18, color: AppColors.primary.withValues(alpha: 0.5)),
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
    final nutritionProvider =
        Provider.of<NutritionProvider>(context, listen: false);
    final exerciseProvider =
        Provider.of<ExerciseProvider>(context, listen: false);

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

    final planActions = [
      ('📅', 'Kế hoạch 7 ngày', 7),
      ('🗓️', 'Kế hoạch 14 ngày', 14),
      ('📆', 'Kế hoạch 30 ngày', 30),
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
                border: Border.all(color: AppColors.primary.withValues(alpha: 0.08)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.today,
                          size: 14, color: AppColors.textSecondary),
                      const SizedBox(width: 6),
                      const Text(
                        'Hôm nay của bạn',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textSecondary),
                      ),
                      const Spacer(),
                      GestureDetector(
                        onTap: () {
                          final summary = _buildTodaySummaryMessage(
                              todayMeals, todayExercises, totalCal, burnedCal);
                          _sendMessage(summary);
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: AppColors.primary.withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            'Hỏi AI phân tích',
                            style: TextStyle(
                                fontSize: 11,
                                color: AppColors.primary,
                                fontWeight: FontWeight.w600),
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
                      style: const TextStyle(
                          fontSize: 11, color: AppColors.textSecondary),
                    ),
                  ],
                ],
              ),
            ),
          ],
          const Padding(
            padding: EdgeInsets.only(bottom: 6),
            child: Text(
              '⚡ Gợi ý nhanh',
              style: TextStyle(
                fontSize: 11,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            child: Row(
              children: [
                ...actions.map((a) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ActionChip(
                        avatar: Text(a.$1, style: const TextStyle(fontSize: 13)),
                        label: Text(a.$2,
                            style: const TextStyle(
                                fontSize: 12, fontWeight: FontWeight.w500)),
                        backgroundColor: AppColors.surface,
                        side: BorderSide(
                            color: AppColors.primary.withValues(alpha: 0.25)),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18)),
                        onPressed: () => _sendMessage(a.$3),
                      ),
                    )),
                ...planActions.map((a) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ActionChip(
                        avatar: Text(a.$1, style: const TextStyle(fontSize: 13)),
                        label: Text(a.$2,
                            style: const TextStyle(
                                fontSize: 12,
                                color: AppColors.primary,
                                fontWeight: FontWeight.w600)),
                        backgroundColor: AppColors.primary.withValues(alpha: 0.08),
                        side: BorderSide(
                            color: AppColors.primary.withValues(alpha: 0.35)),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18)),
                        onPressed: () => _createPlanFromQuickAction(a.$3),
                      ),
                    )),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _createPlanFromQuickAction(int days) async {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;

    try {
      await _backendApi.createLongTermPlan(
        userId: user.id,
        userContext: {
          'age': user.age,
          'gender': user.gender,
          'height': user.height,
          'weight': user.weight,
          'activity_level': user.activityLevel,
          'health_goal': user.healthGoal,
        },
        days: days,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('✅ Đã tạo kế hoạch $days ngày thành công'),
          backgroundColor: Colors.green,
        ),
      );
      _loadActivePlan();
      _sendMessage('Hãy tạo kế hoạch $days ngày cho tôi');
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('❌ Không tạo được kế hoạch: $e'),
            backgroundColor: Colors.red),
      );
    }
  }

  Widget _buildContextStat(
      String emoji, String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 16)),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value,
                  style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.bold, color: color)),
              Text(label,
                  style: const TextStyle(
                      fontSize: 10, color: AppColors.textSecondary)),
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
      buffer.write(
          '- Ăn ${meals.length} bữa, tổng ${totalCal.toStringAsFixed(0)} kcal\n');
    }
    if (exercises.isNotEmpty) {
      buffer.write(
          '- Tập ${exercises.length} bài tập, đốt ${burnedCal.toStringAsFixed(0)} kcal\n');
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
        children: suggestions
            .map((s) => GestureDetector(
                  onTap: () => _sendMessage(s),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: AppColors.primary.withValues(alpha: 0.3),
                        width: 1,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.add_circle_outline,
                            size: 14,
                            color: AppColors.primary.withValues(alpha: 0.8)),
                        const SizedBox(width: 5),
                        Text(
                          s,
                          style: const TextStyle(
                            fontSize: 13,
                            color: AppColors.primary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ))
            .toList(),
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

  Widget _buildInputArea() {
    final aiChatProvider = Provider.of<AIChatProvider>(context);
    final isStreaming = aiChatProvider.isStreaming;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
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
                  enabled: !isStreaming,
                  decoration: InputDecoration(
                    hintText: isStreaming
                        ? 'AI đang phản hồi...'
                        : 'Nhập triệu chứng hoặc câu hỏi...',
                    hintStyle:
                        const TextStyle(color: AppColors.textHint, fontSize: 14),
                    border: InputBorder.none,
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  ),
                  maxLines: null,
                  textInputAction: TextInputAction.send,
                  onSubmitted: isStreaming ? null : (_) => _handleSubmit(),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: isStreaming ? null : AppColors.primaryGradient,
                color: isStreaming ? Colors.grey.shade300 : null,
                borderRadius: BorderRadius.circular(24),
                boxShadow: isStreaming
                    ? null
                    : [
                        BoxShadow(
                          color: AppColors.primary.withValues(alpha: 0.4),
                          blurRadius: 8,
                          offset: const Offset(0, 3),
                        ),
                      ],
              ),
              child: IconButton(
                icon: Icon(
                    isStreaming ? Icons.hourglass_bottom : Icons.send,
                    color: isStreaming ? Colors.grey.shade600 : Colors.white,
                    size: 22),
                onPressed: isStreaming ? null : _handleSubmit,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _handleSubmit() {
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
    if (aiChatProvider.isStreaming) return;

    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _sendMessage(text);
  }

  void _sendMessage(String text) {
    _textController.clear();
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;

    final nutritionProvider =
        Provider.of<NutritionProvider>(context, listen: false);
    final exerciseProvider =
        Provider.of<ExerciseProvider>(context, listen: false);

    // Chuyển bữa ăn hôm nay thành dạng gọn để gửi lên AI
    final todayMeals = nutritionProvider.todayMeals.map((meal) {
      return {
        'name': meal.name,
        'meal_type': meal.mealType,
        'calories': meal.calories.toStringAsFixed(0),
        'protein': meal.protein.toStringAsFixed(1),
        'carbs': meal.carbs.toStringAsFixed(1),
        'fat': meal.fat.toStringAsFixed(1),
        'items': meal.items
            .map((i) => '${i.name} ${i.weightGrams.toStringAsFixed(0)}g')
            .toList(),
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

class _TypingDotsState extends State<_TypingDots>
    with TickerProviderStateMixin {
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
                color: AppColors.primary.withValues(alpha: opacity.clamp(0.3, 1.0)),
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
// Card hiển thị món ăn gợi ý từ AI (nhóm nhiều nguyên liệu)
// ═══════════════════════════════════════════════════════════════
class _MealActionCard extends StatelessWidget {
  final String mealName;
  final String mealType;
  final List<ActionItem> actions;
  final VoidCallback? onSaveAll;

  const _MealActionCard({
    required this.mealName,
    required this.mealType,
    required this.actions,
    this.onSaveAll,
  });

  /// Lấy nhãn bữa ăn từ meal_type
  String get _mealTypeLabel {
    switch (mealType.toLowerCase()) {
      case 'breakfast':
      case 'sang':
        return 'Bữa sáng';
      case 'lunch':
      case 'trua':
        return 'Bữa trưa';
      case 'dinner':
      case 'toi':
        return 'Bữa tối';
      case 'snack':
      case 'phu':
        return 'Ăn phụ';
      default:
        return '';
    }
  }

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
        border: Border.all(
            color: const Color(0xFF4CAF50).withValues(alpha: 0.25), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4CAF50).withValues(alpha: 0.08),
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
              color: const Color(0xFF4CAF50).withValues(alpha: 0.06),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(14),
                topRight: Radius.circular(14),
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.restaurant_menu,
                      color: Color(0xFF4CAF50), size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(mealName,
                          style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1A1A1A))),
                      Row(
                        children: [
                          if (_mealTypeLabel.isNotEmpty) ...[
                            Text(_mealTypeLabel,
                                style: const TextStyle(
                                    fontSize: 11, color: Color(0xFF888888))),
                            const Text(' · ',
                                style: TextStyle(
                                    fontSize: 11, color: Color(0xFF888888))),
                          ],
                          Text('${actions.length} nguyên liệu',
                              style: const TextStyle(
                                  fontSize: 11, color: Color(0xFF4CAF50))),
                        ],
                      ),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(totalCal.toStringAsFixed(0),
                        style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: AppColors.calories)),
                    const Text('kcal',
                        style: TextStyle(
                            fontSize: 10, color: AppColors.textSecondary)),
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
                  final g =
                      (a.details['serving_grams'] as num? ?? 100).toDouble();
                  final cal =
                      (a.details['calories'] as num? ?? 0).toDouble() * g / 100;
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      children: [
                        const Icon(Icons.fiber_manual_record,
                            size: 6, color: AppColors.textHint),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text('${a.name}  ${g.toStringAsFixed(0)}g',
                              style: const TextStyle(fontSize: 13)),
                        ),
                        Text('${cal.toStringAsFixed(0)} kcal',
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.textSecondary)),
                      ],
                    ),
                  );
                }),
                const SizedBox(height: 4),
                // Macro tổng
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
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
          if (onSaveAll != null)
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
        Text('$label:',
            style: TextStyle(
                fontSize: 11, color: color, fontWeight: FontWeight.w600)),
        const SizedBox(width: 3),
        Text('${value.toStringAsFixed(0)}g',
            style:
                const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
      ],
    );
  }
}

class AIThoughtsPanel extends StatefulWidget {
  final String thoughts;
  final bool isThinking;

  const AIThoughtsPanel({
    super.key,
    required this.thoughts,
    required this.isThinking,
  });

  @override
  State<AIThoughtsPanel> createState() => _AIThoughtsPanelState();
}

class _AIThoughtsPanelState extends State<AIThoughtsPanel> {
  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();
    _isExpanded = widget.isThinking;
  }

  @override
  void didUpdateWidget(AIThoughtsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isThinking && !oldWidget.isThinking) {
      _isExpanded = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceLight.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.primary.withValues(alpha: 0.1),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: widget.isThinking
                ? null
                : () => setState(() => _isExpanded = !_isExpanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                children: [
                  Icon(
                    Icons.psychology_outlined,
                    size: 16,
                    color: AppColors.primary.withValues(alpha: 0.6),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    widget.isThinking ? 'Đang suy nghĩ...' : 'Xem quá trình suy nghĩ',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary.withValues(alpha: 0.8),
                    ),
                  ),
                  const Spacer(),
                  if (!widget.isThinking)
                    Icon(
                      _isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                      size: 16,
                      color: AppColors.textSecondary,
                    ),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: const SizedBox.shrink(),
            secondChild: Container(
              width: double.infinity,
              padding: const EdgeInsets.only(left: 12, right: 12, bottom: 12),
              child: Text(
                widget.thoughts.trim(),
                style: const TextStyle(
                  fontSize: 12.5,
                  color: AppColors.textSecondary,
                  fontStyle: FontStyle.italic,
                  height: 1.4,
                ),
              ),
            ),
            crossFadeState: _isExpanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 200),
          ),
        ],
      ),
    );
  }
}
