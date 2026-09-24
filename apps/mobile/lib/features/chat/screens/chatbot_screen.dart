import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../../providers/ai_chat_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/lifestyle_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../models/chat_message.dart';
import '../../../models/profile_readiness.dart';
import '../../../widgets/profile_completion_notice.dart';
import '../../../models/wger_models.dart';
import '../../../models/meal_model.dart';
import '../../../models/app_state_value.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/action_card_widget.dart';
import '../../../widgets/detail_bottom_sheet.dart';
import '../../../widgets/plan_detail_bottom_sheet.dart';
import '../../../services/backend_api_service.dart';
import '../../../constants/ai_chatbot_config.dart';
import '../../../widgets/formatted_markdown_text.dart';
import '../../../widgets/meal_summary_card.dart';
import '../../nutrition/widgets/meal_plan_card.dart';
import '../../../widgets/recommendation_feedback_bar.dart';
import '../../../widgets/personalized_workout_card.dart';
import '../../../widgets/versioned_plan_card.dart';
import '../chat_debug_transcript.dart';
import '../../plans/screens/plan_detail_screen.dart';
import '../../plans/screens/plan_list_screen.dart';
import '../../settings/screens/profile_settings_screen.dart';
import '../../auth/screens/workout_account_intake_screen.dart';
import '../chat_presentation.dart';
import '../chat_tail_follower.dart';

const bool _developerTraceBuild =
    bool.fromEnvironment('CHAT_DEBUG_TRACE', defaultValue: kDebugMode);

class ChatbotScreen extends StatefulWidget {
  const ChatbotScreen({super.key, this.showBackButton = true});

  final bool showBackButton;

  @override
  State<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends State<ChatbotScreen>
    with WidgetsBindingObserver {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  late final ChatTailFollower _tailFollower =
      ChatTailFollower(_scrollController);
  final BackendApiService _backendApi = BackendApiService();
  Map<String, dynamic>? _activePlan;
  bool _isLoadingPlan = false;
  bool _sending = false;
  bool _restoringSession = true;
  AIChatProvider? _chatProvider;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final aiChatProvider =
          Provider.of<AIChatProvider>(context, listen: false);
      _chatProvider = aiChatProvider;
      final exerciseProvider =
          Provider.of<ExerciseProvider>(context, listen: false);
      final nutritionProvider =
          Provider.of<NutritionProvider>(context, listen: false);
      final lifestyleProvider =
          Provider.of<LifestyleProvider>(context, listen: false);
      final healthProvider =
          Provider.of<HealthProvider>(context, listen: false);
      final userProvider = Provider.of<UserProvider>(context, listen: false);
      final userId = userProvider.currentUser?.id;
      if (userId != null && _textController.text.isEmpty) {
        _textController.text = aiChatProvider.pendingDraftFor(userId) ?? '';
      }

      aiChatProvider.setProviders(
        exerciseProvider: exerciseProvider,
        nutritionProvider: nutritionProvider,
        lifestyleProvider: lifestyleProvider,
        healthProvider: healthProvider,
        userProvider: userProvider,
      );

      aiChatProvider.addListener(_onMessagesChanged);
      await _restoreLatestSession(aiChatProvider, userId);
      if (!mounted) return;
      _loadActivePlan();
      _scrollToBottom();
    });
  }

  Future<void> _restoreLatestSession(
    AIChatProvider aiChatProvider,
    String? userId,
  ) async {
    var restored = aiChatProvider.messages.isNotEmpty;
    if (!restored && userId != null && userId.isNotEmpty) {
      try {
        restored = await aiChatProvider
            .restoreLatestSession(
              loadSessions: () => _backendApi.getChatSessions(userId: userId),
              loadMessages: _backendApi.getSessionMessages,
            )
            .timeout(const Duration(seconds: 15));
      } catch (error) {
        debugPrint('Không thể tự khôi phục phiên chat gần nhất: $error');
      }
    }
    if (!mounted) return;
    if (!restored && aiChatProvider.messages.isEmpty) {
      aiChatProvider.initialize();
    }
    setState(() => _restoringSession = false);
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
      if (mounted) {
        setState(() => _isLoadingPlan = false);
        _scrollToBottom(settleFrames: 4);
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _chatProvider?.removeListener(_onMessagesChanged);
    _tailFollower.dispose();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void didChangeMetrics() {
    // Safari/iOS and the soft keyboard can resize the visual viewport after
    // the transcript itself has already laid out.
    _scrollToBottom(settleFrames: 4);
  }

  bool _wasStreaming = false;

  void _onMessagesChanged() {
    if (!mounted) return;
    _scrollToBottom();
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
    if (_wasStreaming && !aiChatProvider.isStreaming) {
      _loadActivePlan();
    }
    _wasStreaming = aiChatProvider.isStreaming;
  }

  void _scrollToBottom({int? settleFrames}) {
    _tailFollower.request(settleFrames: settleFrames);
  }

  @override
  Widget build(BuildContext context) {
    final aiChatProvider = Provider.of<AIChatProvider>(context);
    final messages = aiChatProvider.messages;
    final bool isConnecting = aiChatProvider.isStreaming;
    final bool hasError = aiChatProvider.errorMessage != null;

    return Scaffold(
      appBar: AppBar(
        centerTitle: false,
        titleSpacing: widget.showBackButton ? 0 : 16,
        leading: widget.showBackButton
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                tooltip: 'Quay lại',
                onPressed: () => Navigator.pop(context),
              )
            : null,
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
                        color: hasError ? Colors.red : AppColors.textSecondary,
                        fontWeight: FontWeight.normal,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
        automaticallyImplyLeading: widget.showBackButton,
        actions: [
          IconButton(
            icon: const Icon(Icons.event_note_outlined),
            tooltip: 'Mở kế hoạch',
            onPressed: _openPlanLibrary,
          ),
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'Tạo cuộc trò chuyện mới',
            onPressed: () {
              aiChatProvider.startNewSession();
              setState(() => _restoringSession = false);
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
            // A non-secret, E2E-only semantic marker proves that the isolated
            // build configuration reached the real chat surface. It has no
            // visual copy and is absent from normal builds.
            if (AIChatbotConfig.n3E2ERuntimeConfigurationActive)
              Semantics(
                label: 'n3-e2e-runtime-configured',
                container: true,
                child: const SizedBox.shrink(),
              ),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: _textController,
              builder: (context, value, child) => ProfileCompletionNotice(
                scope: value.text.trim().isNotEmpty
                    ? ProfileReadiness.scopeForMessage(value.text)
                    : aiChatProvider.profileReadiness?.scope ??
                        ProfileContextScope.both,
                issue: aiChatProvider.profileIssue,
              ),
            ),
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.all(16),
                itemCount: messages.length,
                itemBuilder: (context, index) {
                  final message = messages[index];
                  return AnimatedCard(
                    delay: 0,
                    child: _buildMessageBubble(
                      message,
                      precedingUserText: _precedingUserText(messages, index),
                    ),
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
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
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

  void _openPlanDetailSheet() {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null || _activePlan == null) return;

    if (_activePlan!['plan_id'] != null &&
        _activePlan!['revision_id'] != null) {
      _openVersionedPlan(_activePlan!);
      return;
    }

    showPlanDetailBottomSheet(
      context,
      userId: user.id,
      initialPlan: _activePlan!,
      backendApi: _backendApi,
      onAskAI: (prompt) => _sendMessage(prompt),
    );
  }

  void _openVersionedPlan(Map<String, dynamic> plan) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => PlanDetailScreen(plan: plan)),
    );
  }

  void _openPlanLibrary() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const PlanListScreen()),
    );
  }

  Widget _buildActivePlanCard() {
    // Keep an existing card mounted while it refreshes. Replacing it with a
    // 2px progress bar changes the transcript viewport twice and used to race
    // the streaming auto-scroll on short mobile screens.
    if (_isLoadingPlan && _activePlan == null) {
      return const Padding(
        padding: EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: LinearProgressIndicator(minHeight: 2),
      );
    }
    final plan = _activePlan;
    if (plan == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Material(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: _openPlanDetailSheet,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border:
                  Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
            ),
            child: Row(
              children: [
                const Icon(Icons.event_note, color: AppColors.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    plan['revision_id'] != null
                        ? 'Bản xem trước kế hoạch ${plan['period_start']} - ${plan['period_end']}'
                        : 'Kế hoạch hiện tại: ${plan['duration_days']} ngày • '
                            '${formatActivePlanGoal(plan['goal'])}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
                TextButton(
                  onPressed: _openPlanDetailSheet,
                  child: const Text('Xem'),
                ),
              ],
            ),
          ),
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

  String? _precedingUserText(List<AIChatMessage> messages, int index) {
    for (var previousIndex = index - 1; previousIndex >= 0; previousIndex--) {
      final previousMessage = messages[previousIndex];
      if (previousMessage.isUser) return previousMessage.text;
    }
    return null;
  }

  Future<void> _copyDebugTranscript({
    required AIChatMessage message,
    required String? precedingUserText,
    required String assistantText,
  }) async {
    final transcript = buildChatDebugTranscript(
      userText: precedingUserText,
      assistantText: assistantText,
      assistantMessage: message,
    );
    await Clipboard.setData(ClipboardData(text: transcript));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Đã copy debug transcript.')),
    );
  }

  Widget _buildMessageBubble(
    AIChatMessage message, {
    String? precedingUserText,
  }) {
    // Khi bot đang xử lý, chỉ hiển thị reasoning thật từ backend.
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
                  color: message.isUser ? null : AppColors.surface,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(20),
                    topRight: const Radius.circular(20),
                    bottomLeft: Radius.circular(message.isUser ? 20 : 6),
                    bottomRight: Radius.circular(message.isUser ? 6 : 20),
                  ),
                  border: message.isUser
                      ? null
                      : Border.all(
                          color: Colors.black.withValues(alpha: 0.04),
                          width: 1,
                        ),
                  boxShadow: message.isUser
                      ? [
                          BoxShadow(
                            color:
                                const Color(0xFF0F172A).withValues(alpha: 0.2),
                            blurRadius: 10,
                            offset: const Offset(0, 3),
                          ),
                        ]
                      : AppShadows.subtle,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (!message.isUser &&
                        (message.publicTrace?.hasSteps ?? false)) ...[
                      AIThoughtsPanel(
                        publicTrace: message.publicTrace!,
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

        if (!message.isUser &&
            _developerTraceBuild &&
            message.status == MessageStatus.done)
          Padding(
            padding: const EdgeInsets.only(left: 44, top: 2),
            child: TextButton.icon(
              onPressed: () => _copyDebugTranscript(
                message: message,
                precedingUserText: precedingUserText,
                assistantText: displayText,
              ),
              icon: const Icon(Icons.copy_all_outlined, size: 16),
              label: const Text('Copy debug transcript'),
              style: TextButton.styleFrom(
                foregroundColor: AppColors.textSecondary,
                visualDensity: VisualDensity.compact,
                padding: const EdgeInsets.symmetric(horizontal: 8),
              ),
            ),
          ),

        // Action cards
        if (!message.isUser && message.structuredResponse != null)
          ..._buildActionCards(message),

        if (!message.isUser &&
            _developerTraceBuild &&
            message.developerTrace.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(left: 44, top: 4, right: 10),
            child: DeveloperTracePanel(events: message.developerTrace),
          ),

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

  /// Chỉ hiện PublicReasoningTrace có allowlist, không hiển thị raw reasoning.
  Widget _buildThinkingBubble(AIChatMessage message) {
    final publicTrace = message.publicTrace;
    if (publicTrace == null || !publicTrace.hasSteps) {
      return const SizedBox.shrink();
    }

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
            child: AIThoughtsPanel(
              publicTrace: publicTrace,
              isThinking: true,
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
    final personalizedWorkout = structuredResponse.personalizedWorkout;
    final versionedPlan = structuredResponse.versionedPlan;
    if (versionedPlan != null) {
      widgets.add(Padding(
        padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
        child: VersionedPlanCard(
          plan: versionedPlan,
          onView: () => _openVersionedPlan(versionedPlan),
        ),
      ));
    }
    if (personalizedWorkout != null) {
      final planId = personalizedWorkout['plan_id'] as String?;
      final user =
          Provider.of<UserProvider>(context, listen: false).currentUser;
      widgets.add(Padding(
        padding: const EdgeInsets.only(left: 44, top: 8, right: 10),
        child: PersonalizedWorkoutCard(
          workout: personalizedWorkout,
          onSubstitute: planId == null
              ? null
              : (exerciseId) => _sendMessage(
                  'Đổi bài $exerciseId trong kế hoạch $planId cho tôi.'),
          onSave: planId == null || user == null
              ? null
              : () async {
                  final result = await _backendApi.savePersonalizedWorkoutPlan(
                    userId: user.id,
                    planId: planId,
                    requestId:
                        'workout-save-${DateTime.now().microsecondsSinceEpoch}',
                  );
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result['write_status'] == 'PERSISTED'
                          ? 'Đã lưu kế hoạch.'
                          : 'Chưa lưu: ${result['status'] ?? 'không xác định'}'),
                    ));
                  }
                },
          onLog: planId == null || user == null
              ? null
              : (status, pain, actualExercises) async {
                  final result = await _backendApi.logPersonalizedWorkoutResult(
                    userId: user.id,
                    planId: planId,
                    requestId:
                        'workout-result-${DateTime.now().microsecondsSinceEpoch}',
                    sessionCompletionStatus: status,
                    painDiscomfortStatus: pain,
                    exerciseResults: actualExercises,
                  );
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result['write_status'] == 'PERSISTED'
                          ? 'Đã ghi nhận kết quả thực tế.'
                          : 'Chưa ghi nhận: ${result['status'] ?? 'không xác định'}'),
                    ));
                  }
                },
        ),
      ));
    }

    final foodActions = structuredResponse.foodActions;
    final exerciseActions = structuredResponse.exerciseActions;
    final bool showSaveButton = !message.text.contains('✅') &&
        !message.text.toLowerCase().contains('đã lưu') &&
        !message.text.toLowerCase().contains('đã ghi nhận');

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
                border: Border.all(
                    color: AppColors.primary.withValues(alpha: 0.25)),
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
          const mealOrder = MealTypeUtils.orderedTypes;
          final dishMap = dayGroups[day] ?? {};
          // Sắp xếp theo meal_type
          final sortedDishes = dishMap.entries.toList()
            ..sort((a, b) {
              final ma = mealOrder.indexOf(MealTypeUtils.normalize(
                a.value.first.details['meal_type'] as String?,
              ));
              final mb = mealOrder.indexOf(MealTypeUtils.normalize(
                b.value.first.details['meal_type'] as String?,
              ));
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
                onRecommendationFeedback:
                    _canRecordRecommendationFeedback(actions)
                        ? (eventType, reasonCode) =>
                            _recordRecommendationFeedback(
                              actions,
                              eventType,
                              reasonCode,
                            )
                        : null,
                onChangeDish: _canRecordRecommendationFeedback(actions)
                    ? () => _sendMessage('Đổi món khác giúp tôi.')
                    : null,
                publicReasonCodes: _recommendationReasonCodes(actions),
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
              onRecommendationFeedback:
                  _canRecordRecommendationFeedback(actions)
                      ? (eventType, reasonCode) =>
                          _recordRecommendationFeedback(
                            actions,
                            eventType,
                            reasonCode,
                          )
                      : null,
              onChangeDish: _canRecordRecommendationFeedback(actions)
                  ? () => _sendMessage('Đổi món khác giúp tôi.')
                  : null,
              publicReasonCodes: _recommendationReasonCodes(actions),
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
          onSaveToJournal:
              showSaveButton ? () => _handleSaveToJournal(action) : null,
          onViewDetail: () => _handleViewDetail(action),
        ),
      ));
    }

    return widgets;
  }

  /// Helper: Lấy label tiếng Việt cho meal_type
  String _getMealTypeLabel(String mealType) {
    return MealTypeUtils.label(mealType);
  }

  bool _canRecordRecommendationFeedback(List<ActionItem> actions) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    return user != null &&
        actions.any((action) {
          final candidateId =
              action.details['recommendation_candidate_id']?.toString().trim();
          final recommendationEventId =
              action.details['recommendation_event_id']?.toString().trim();
          final policyVersion = action.details['recommendation_policy_version']
              ?.toString()
              .trim();
          return candidateId != null &&
              candidateId.isNotEmpty &&
              recommendationEventId != null &&
              recommendationEventId.isNotEmpty &&
              policyVersion != null &&
              policyVersion.isNotEmpty;
        });
  }

  List<String> _recommendationReasonCodes(List<ActionItem> actions) {
    for (final action in actions) {
      final raw = action.details['recommendation_reason_codes'];
      if (raw is List) {
        return raw
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .take(3)
            .toList(growable: false);
      }
    }
    return const [];
  }

  Future<void> _recordRecommendationFeedback(
    List<ActionItem> actions,
    String eventType,
    String? reasonCode,
  ) async {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;
    final action = actions.firstWhere(
      (item) {
        final candidateId =
            item.details['recommendation_candidate_id']?.toString().trim() ??
                '';
        final eventId =
            item.details['recommendation_event_id']?.toString().trim() ?? '';
        final policy =
            item.details['recommendation_policy_version']?.toString().trim() ??
                '';
        return candidateId.isNotEmpty &&
            eventId.isNotEmpty &&
            policy.isNotEmpty;
      },
    );
    final candidateId =
        action.details['recommendation_candidate_id'].toString();
    final recommendationEventId =
        action.details['recommendation_event_id'].toString();
    final policyVersion =
        action.details['recommendation_policy_version'].toString();
    await _backendApi.recordAdaptiveRecommendationFeedback(
      recommendationEventId: recommendationEventId,
      candidateId: candidateId,
      policyVersion: policyVersion,
      // A reconnect may repeat the same action. Keep its identity stable per
      // recommendation/event so the owner-bound backend can return it
      // idempotently instead of learning twice.
      idempotencyKey: '$recommendationEventId:$eventType',
      eventType: eventType,
      reasonCode: reasonCode,
    );
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Đã ghi nhận phản hồi cho gợi ý thử nghiệm.')),
      );
    }
  }

  /// Lưu food actions thành 1 MealModel với nhiều MealItem
  Future<void> _handleSaveMealToJournal({
    required String mealName,
    required List<ActionItem> actions,
  }) async {
    final messenger = ScaffoldMessenger.of(context);
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final nutritionProvider =
        Provider.of<NutritionProvider>(context, listen: false);
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
    return MealTypeUtils.normalize(t);
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
                  border: Border.all(
                      color: AppColors.primary.withValues(alpha: 0.3)),
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
                        size: 18,
                        color: AppColors.primary.withValues(alpha: 0.5)),
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
    final consumedCal = nutritionProvider.consumedCalories;
    final plannedCal = nutritionProvider.plannedCalories;
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
                border: Border.all(
                    color: AppColors.primary.withValues(alpha: 0.08)),
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
                              nutritionProvider, exerciseProvider);
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
                            nutritionProvider.completedMealsCount > 0
                                ? '${consumedCal.toStringAsFixed(0)} kcal đã ăn'
                                : '${plannedCal.toStringAsFixed(0)} kcal dự kiến',
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
                        avatar:
                            Text(a.$1, style: const TextStyle(fontSize: 13)),
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
                      child: Semantics(
                        label: 'n3-plan-quick-${a.$3}',
                        button: true,
                        child: ActionChip(
                          avatar:
                              Text(a.$1, style: const TextStyle(fontSize: 13)),
                          label: Text(a.$2,
                              style: const TextStyle(
                                  fontSize: 12,
                                  color: AppColors.primary,
                                  fontWeight: FontWeight.w600)),
                          backgroundColor:
                              AppColors.primary.withValues(alpha: 0.08),
                          side: BorderSide(
                              color: AppColors.primary.withValues(alpha: 0.35)),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(18)),
                          onPressed: () => _createPlanFromQuickAction(a.$3),
                        ),
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

    final missing = ProfileReadiness.planCreationMissingFields(user);
    if (missing.isNotEmpty) {
      final messenger = ScaffoldMessenger.of(context);
      messenger
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            key: const Key('plan-profile-required'),
            content: Text(
              'Cần bổ sung ${missing.values.join(', ')} trước khi tạo kế hoạch.',
            ),
            action: SnackBarAction(
              label: 'Bổ sung hồ sơ',
              onPressed: _openProfileForPlan,
            ),
          ),
        );
      return;
    }

    try {
      final createdPlan = await _backendApi.createLongTermPlan(
        userId: user.id,
        userContext: user.toPlanRequestContext(),
        days: days,
      );
      if (!mounted) return;
      final presentation = createdPlan['presentation'];
      if (createdPlan['status'] != 'READY') {
        final codes = createdPlan['clarification_codes'];
        final needsSafetyRefresh = codes is List &&
            codes.contains('EXERCISE_SAFETY_CONTEXT_REQUIRED');
        if (needsSafetyRefresh) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              key: const Key('plan-safety-refresh-required'),
              content: const Text(
                  'Cần xác nhận lại an toàn tập luyện hôm nay trước khi lập kế hoạch.'),
              action: SnackBarAction(
                label: 'Xác nhận ngay',
                onPressed: _refreshWorkoutSafetyForPlan,
              ),
            ),
          );
          return;
        }
        throw StateError('PLAN_PREVIEW_NOT_SAVEABLE');
      }
      if (presentation is! Map ||
          createdPlan['preview_persistence_status'] != 'PERSISTED') {
        throw StateError('PLAN_PREVIEW_NOT_SAVEABLE');
      }
      setState(() => _activePlan = Map<String, dynamic>.from(presentation));
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              'Đã tạo bản xem trước $days ngày. Hãy kiểm tra rồi lưu kế hoạch.'),
          backgroundColor: Colors.blue,
        ),
      );
      // Show the exact persisted preview; saving still requires the user's
      // explicit action in PlanDetailScreen.
    } on PlanCreationException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message), backgroundColor: Colors.red),
      );
    } catch (error) {
      debugPrint('Plan creation request failed: $error');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'Không thể kết nối để tạo kế hoạch. Vui lòng kiểm tra backend và thử lại.'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  void _openProfileForPlan() {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (routeContext) => ProfileSettingsScreen(
          isAccountSetup: user.needsBasicProfileIntake,
          onSaved: () => Navigator.of(routeContext).pop(),
        ),
      ),
    );
  }

  void _refreshWorkoutSafetyForPlan() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (routeContext) => WorkoutAccountIntakeScreen(
        initialSupport: 'BOTH',
        onSaved: () => Navigator.of(routeContext).pop(),
      ),
    ));
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
    NutritionProvider nutritionProvider,
    ExerciseProvider exerciseProvider,
  ) {
    final completedCount = nutritionProvider.completedMealsCount;
    final pendingCount = nutritionProvider.pendingMealsCount;
    final consumedCal = nutritionProvider.consumedCalories;
    final plannedCal = nutritionProvider.plannedCalories;
    final exercises = exerciseProvider.todayExercises;
    final burnedCal = exerciseProvider.totalCaloriesBurned;

    final buffer =
        StringBuffer('Hôm nay tình trạng dinh dưỡng & vận động của tôi:\n');
    if (completedCount > 0) {
      buffer.write(
          '- Đã ăn $completedCount bữa: tổng ${consumedCal.toStringAsFixed(0)} kcal\n');
    }
    if (pendingCount > 0) {
      buffer.write(
          '- Có $pendingCount bữa dự kiến trong kế hoạch chưa ăn (${(plannedCal - consumedCal).toStringAsFixed(0)} kcal)\n');
    }
    if (completedCount == 0 && pendingCount == 0) {
      buffer.write('- Chưa ghi nhận bữa ăn nào hôm nay\n');
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
    final isStreaming = _restoringSession ||
        aiChatProvider.isStreaming ||
        aiChatProvider.isCheckingProfile ||
        _sending;

    return Semantics(
      label: 'n3-chat-state-${aiChatProvider.transportState.name}',
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border(
            top: BorderSide(
              color: Colors.black.withValues(alpha: 0.05),
              width: 1,
            ),
          ),
          boxShadow: AppShadows.subtle,
        ),
        child: SafeArea(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(AppRadius.pill),
                    border: Border.all(
                      color: Colors.black.withValues(alpha: 0.04),
                      width: 1,
                    ),
                  ),
                  child: Semantics(
                    label: 'n3-chat-input',
                    textField: true,
                    child: TextField(
                      controller: _textController,
                      enabled: !isStreaming,
                      decoration: InputDecoration(
                        hintText: _restoringSession
                            ? 'Đang khôi phục cuộc trò chuyện...'
                            : isStreaming
                                ? 'AI đang suy nghĩ và phản hồi...'
                                : 'Nhập câu hỏi hoặc yêu cầu tư vấn...',
                        hintStyle: const TextStyle(
                          color: AppColors.textHint,
                          fontSize: 14,
                        ),
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 12,
                        ),
                      ),
                      maxLines: 4,
                      minLines: 1,
                      textInputAction: TextInputAction.send,
                      onSubmitted: isStreaming ? null : (_) => _handleSubmit(),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  gradient: isStreaming ? null : AppColors.primaryGradient,
                  color: isStreaming ? const Color(0xFFE2E8F0) : null,
                  shape: BoxShape.circle,
                  boxShadow: isStreaming
                      ? null
                      : [
                          BoxShadow(
                            color:
                                const Color(0xFF0F172A).withValues(alpha: 0.25),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ],
                ),
                child: Semantics(
                  label: 'n3-chat-send',
                  button: true,
                  child: IconButton(
                    icon: Icon(
                      isStreaming
                          ? Icons.more_horiz_rounded
                          : Icons.arrow_upward_rounded,
                      color:
                          isStreaming ? AppColors.textSecondary : Colors.white,
                      size: 22,
                    ),
                    onPressed: isStreaming ? null : _handleSubmit,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _handleSubmit() {
    final aiChatProvider = Provider.of<AIChatProvider>(context, listen: false);
    if (aiChatProvider.isStreaming ||
        aiChatProvider.isCheckingProfile ||
        _restoringSession ||
        _sending) {
      return;
    }

    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _sendMessage(text);
  }

  Future<void> _sendMessage(String text) async {
    if (_restoringSession || _sending || _chatProvider?.isStreaming == true) {
      return;
    }
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (user == null) return;
    if (_textController.text.isEmpty) _textController.text = text;
    setState(() => _sending = true);
    try {
      final nutritionProvider =
          Provider.of<NutritionProvider>(context, listen: false);
      final exerciseProvider =
          Provider.of<ExerciseProvider>(context, listen: false);

      // E4 must receive a current server-backed legacy history or an explicit
      // ERROR status. Cached records are never relabelled as authoritative.
      final now = DateTime.now();
      final history =
          await exerciseProvider.loadExercisesForDateRangeAuthoritatively(
        user.id,
        now.subtract(const Duration(days: 28)),
        now.add(const Duration(days: 1)),
      );
      if (!mounted) return;

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

      final accepted =
          await Provider.of<AIChatProvider>(context, listen: false).sendMessage(
        text,
        user,
        todayCalories: nutritionProvider.consumedCalories,
        todayMealsCount: nutritionProvider.completedMealsCount,
        todayCaloriesBurned: exerciseProvider.totalCaloriesBurned,
        todayExercisesCount: exerciseProvider.todayExercises.length,
        todayMeals: todayMeals,
        todayExercises: todayExercises,
        exerciseHistory:
            history.exercises.map((exercise) => exercise.toMap()).toList(),
        exerciseHistoryStatus: history.status.wireName,
        exerciseHistoryObservedAt: history.observedAt,
      );
      if (mounted && accepted && _textController.text.trim() == text.trim()) {
        _textController.clear();
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
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
  final RecommendationFeedbackHandler? onRecommendationFeedback;
  final VoidCallback? onChangeDish;
  final List<String> publicReasonCodes;

  const _MealActionCard({
    required this.mealName,
    required this.mealType,
    required this.actions,
    this.onSaveAll,
    this.onRecommendationFeedback,
    this.onChangeDish,
    this.publicReasonCodes = const [],
  });

  @override
  Widget build(BuildContext context) {
    final isShadowRecommendation = actions.any(
      (action) =>
          action.details['feedback_eligible'] == true &&
          (action.details['recommendation_event_id']?.toString().isNotEmpty ??
              false),
    );
    double gramsFor(ActionItem action) =>
        (action.details['serving_grams'] as num? ?? 100).toDouble();
    double totalFor(String field) => actions.fold(0, (sum, action) {
          final per100g = (action.details[field] as num? ?? 0).toDouble();
          return sum + per100g * gramsFor(action) / 100;
        });

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        MealSummaryCard(
          name: mealName,
          mealType: MealTypeUtils.normalize(mealType),
          ingredients: actions
              .map(
                (action) => MealCardIngredientView(
                  name: action.name,
                  grams: gramsFor(action),
                  calories:
                      (action.details['calories'] as num? ?? 0).toDouble() *
                          gramsFor(action) /
                          100,
                ),
              )
              .toList(growable: false),
          onTap: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              useSafeArea: true,
              showDragHandle: true,
              builder: (_) => FractionallySizedBox(
                  heightFactor: .9,
                  child: MealDetailContent(
                    name: mealName,
                    status: 'Gợi ý · chưa ghi nhận đã ăn',
                    nutrition: {
                      'total_calories': totalFor('calories'),
                      'total_protein': totalFor('protein'),
                      'total_carbs': totalFor('carbs'),
                      'total_fat': totalFor('fat')
                    },
                    content: {
                      'ingredients': actions
                          .map((action) =>
                              {'name': action.name, 'grams': gramsFor(action)})
                          .toList(),
                      if (actions.any((action) =>
                          action.details['recipe_origin'] ==
                          'ADAPTED_RECIPE_VARIANT'))
                        'recipe_origin': 'ADAPTED_RECIPE_VARIANT'
                    },
                    footer: onRecommendationFeedback == null
                        ? null
                        : RecommendationFeedbackBar(
                            onFeedback: onRecommendationFeedback!,
                            onChangeDish: onChangeDish,
                            publicReasonCodes: publicReasonCodes),
                  ))),
          calories: totalFor('calories'),
          protein: totalFor('protein'),
          carbs: totalFor('carbs'),
          fat: totalFor('fat'),
          // The feedback bar's "Lưu lại" is a weak preference signal. A meal
          // becomes actual only after this separate, explicit action.
          actionLabel: onSaveAll == null
              ? null
              : isShadowRecommendation
                  ? 'Ghi đã ăn'
                  : 'Lưu vào nhật ký',
          actionIcon: Icons.bookmark_add_outlined,
          onAction: onSaveAll,
          primaryAction: true,
        ),
        if (onRecommendationFeedback != null)
          RecommendationFeedbackBar(
            onFeedback: onRecommendationFeedback!,
            onChangeDish: onChangeDish,
            publicReasonCodes: publicReasonCodes,
          ),
      ],
    );
  }
}

class AIThoughtsPanel extends StatefulWidget {
  final PublicReasoningTrace publicTrace;
  final bool isThinking;

  const AIThoughtsPanel({
    super.key,
    required this.publicTrace,
    required this.isThinking,
  });

  @override
  State<AIThoughtsPanel> createState() => _AIThoughtsPanelState();
}

class _AIThoughtsPanelState extends State<AIThoughtsPanel> {
  bool _isExpanded = true;

  @override
  void didUpdateWidget(AIThoughtsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isThinking && !oldWidget.isThinking) {
      _isExpanded = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.publicTrace.hasSteps) return const SizedBox.shrink();

    final isLive = widget.isThinking;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.surfaceLight.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isLive
              ? AppColors.primary.withValues(alpha: 0.3)
              : AppColors.textHint.withValues(alpha: 0.15),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _isExpanded = !_isExpanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Icon(
                    Icons.psychology,
                    size: 16,
                    color: isLive
                        ? AppColors.primary
                        : AppColors.primary.withValues(alpha: 0.6),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isLive
                              ? 'Đang xử lý yêu cầu...'
                              : 'Xem cách mình xử lý',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: isLive
                                ? AppColors.primary
                                : AppColors.primary.withValues(alpha: 0.8),
                          ),
                        ),
                        const Text(
                          'Tóm tắt các bước hệ thống đã thực hiện',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10.5,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (isLive) ...[
                    const SizedBox(width: 8),
                    const SizedBox(
                      width: 10,
                      height: 10,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(AppColors.primary),
                      ),
                    ),
                  ],
                  const SizedBox(width: 8),
                  Icon(
                    _isExpanded
                        ? Icons.keyboard_arrow_up
                        : Icons.keyboard_arrow_down,
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
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: Column(
                children: widget.publicTrace.steps
                    .map(
                      (step) => Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              step.publicEventType == 'PERSISTENCE_IN_PROGRESS'
                                  ? Icons.more_horiz
                                  : Icons.check_circle_outline,
                              color: step.publicEventType ==
                                      'PERSISTENCE_IN_PROGRESS'
                                  ? AppColors.primary
                                  : AppColors.success,
                              size: 16,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    step.title,
                                    style: const TextStyle(
                                      fontSize: 12.5,
                                      color: AppColors.textPrimary,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    step.summary,
                                    style: const TextStyle(
                                      fontSize: 11.5,
                                      color: AppColors.textSecondary,
                                      height: 1.35,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                    .toList(growable: false),
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

/// This panel can be reached only in a build compiled with CHAT_DEBUG_TRACE.
/// Server-side policy still decides whether debug_trace events are sent.
class DeveloperTracePanel extends StatefulWidget {
  final List<DeveloperTraceEvent> events;

  const DeveloperTracePanel({super.key, required this.events});

  @override
  State<DeveloperTracePanel> createState() => _DeveloperTracePanelState();
}

class _DeveloperTracePanelState extends State<DeveloperTracePanel> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.textHint.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                children: [
                  const Icon(Icons.build_outlined,
                      size: 16, color: AppColors.textSecondary),
                  const SizedBox(width: 8),
                  const Text(
                    'Debug trace',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  Icon(
                    _expanded
                        ? Icons.keyboard_arrow_up
                        : Icons.keyboard_arrow_down,
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
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: Column(
                children: widget.events
                    .map(
                      (event) => Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: SelectableText(
                            '[${event.timestamp}] ${event.operation}\n'
                            '${event.sanitizedPayload}',
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 10.5,
                              color: AppColors.textSecondary,
                              height: 1.35,
                            ),
                          ),
                        ),
                      ),
                    )
                    .toList(growable: false),
              ),
            ),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 200),
          ),
        ],
      ),
    );
  }
}
