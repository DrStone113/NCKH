import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/chat_provider.dart';
import '../providers/user_provider.dart';
import '../models/health_models.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';

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
      final chatProvider = Provider.of<ChatProvider>(context, listen: false);
      chatProvider.initialize();
      // Scroll to bottom after welcome message
      _scrollToBottom();
      
      // Add listener to auto-scroll when messages change
      chatProvider.addListener(_onMessagesChanged);
    });
  }

  @override
  void dispose() {
    final chatProvider = Provider.of<ChatProvider>(context, listen: false);
    chatProvider.removeListener(_onMessagesChanged);
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onMessagesChanged() {
    // Auto scroll when new message arrives
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
    final chatProvider = Provider.of<ChatProvider>(context);

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
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Tư vấn sức khỏe', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Text('Trợ lý AI', style: TextStyle(fontSize: 11, color: AppColors.textSecondary, fontWeight: FontWeight.normal)),
              ],
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
                itemCount: chatProvider.messages.length + (chatProvider.isTyping ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == chatProvider.messages.length && chatProvider.isTyping) {
                    return _buildTypingIndicator();
                  }
                  return AnimatedCard(
                    delay: 0,
                    child: _buildMessageBubble(chatProvider.messages[index]),
                  );
                },
              ),
            ),
            _buildInputArea(),
          ],
        ),
      ),
    );
  }

  Widget _buildMessageBubble(ChatMessage message) {
    return Column(
      crossAxisAlignment: message.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: [
        // Avatar + bubble
        Row(
          mainAxisAlignment: message.isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
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
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  gradient: message.isUser 
                      ? AppColors.primaryGradient
                      : null,
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
                          ? AppColors.primary.withOpacity(0.2)
                          : Colors.black.withOpacity(0.05),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Text(
                  message.text,
                  style: TextStyle(
                    fontSize: 14,
                    color: message.isUser ? Colors.white : AppColors.textPrimary,
                    height: 1.5,
                  ),
                ),
              ),
            ),
            if (message.isUser) const SizedBox(width: 10),
          ],
        ),

        // Quick replies
        if (!message.isUser && message.quickReplies != null && message.quickReplies!.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(left: 44, top: 8, bottom: 8),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: message.quickReplies!.map((reply) {
                return GestureDetector(
                  onTap: () => _sendMessage(reply),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AppColors.primary.withOpacity(0.3), width: 1.5),
                    ),
                    child: Text(
                      reply,
                      style: const TextStyle(
                        fontSize: 13, 
                        color: AppColors.textPrimary, 
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        if (!message.isUser && (message.quickReplies == null || message.quickReplies!.isEmpty))
          const SizedBox(height: 12),
        if (message.isUser)
          const SizedBox(height: 12),
      ],
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
                    hintStyle: TextStyle(color: AppColors.textHint, fontSize: 14),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 14),
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
    Provider.of<ChatProvider>(context, listen: false).sendMessage(text, user);
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
