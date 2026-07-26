import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/proactive_provider.dart';
import '../providers/user_provider.dart';
import '../theme/app_theme.dart';

class ProactiveCheckinCard extends StatelessWidget {
  final VoidCallback? onOpenChat;

  const ProactiveCheckinCard({
    super.key,
    this.onOpenChat,
  });

  IconData _getCategoryIcon(String category) {
    switch (category) {
      case 'hydration':
        return Icons.water_drop_rounded;
      case 'nutrition':
        return Icons.restaurant_rounded;
      case 'fitness':
        return Icons.fitness_center_rounded;
      case 'mental':
        return Icons.spa_rounded;
      default:
        return Icons.chat_bubble_outline_rounded;
    }
  }

  LinearGradient _getCategoryGradient(String category) {
    switch (category) {
      case 'hydration':
        return const LinearGradient(
          colors: [Color(0xFF00B4DB), Color(0xFF0083B0)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        );
      case 'nutrition':
        return const LinearGradient(
          colors: [Color(0xFF11998E), Color(0xFF38EF7D)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        );
      case 'fitness':
        return const LinearGradient(
          colors: [Color(0xFFFF416C), Color(0xFFFF4B2B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        );
      case 'mental':
        return const LinearGradient(
          colors: [Color(0xFF8E2DE2), Color(0xFF4A00E0)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        );
      default:
        return const LinearGradient(
          colors: [Color(0xFF4776E6), Color(0xFF8E54E9)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ProactiveProvider>(
      builder: (context, provider, child) {
        final nudge = provider.activeNudge;
        if (nudge == null || provider.isDismissed) {
          return const SizedBox.shrink();
        }

        final category = (nudge['category'] ?? 'hydration').toString();
        final title = (nudge['title'] ?? 'Check-in sức khỏe').toString();
        final message = (nudge['message'] ?? '').toString();
        final options = (nudge['quick_options'] as List<dynamic>?) ?? [];

        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            gradient: _getCategoryGradient(category),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.15),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.25),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        _getCategoryIcon(category),
                        color: Colors.white,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, color: Colors.white70, size: 20),
                      onPressed: () => provider.dismissCheckin(),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  message,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    height: 1.35,
                  ),
                ),
                const SizedBox(height: 14),
                // Quick options chips
                if (options.isNotEmpty)
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: options.map((opt) {
                      final optMap = opt as Map<String, dynamic>;
                      final label = (optMap['label'] ?? '').toString();
                      final actionType = (optMap['action_type'] ?? '').toString();
                      final optId = (optMap['id'] ?? '').toString();

                      return InkWell(
                        onTap: () async {
                          if (actionType == 'chat' && onOpenChat != null) {
                            onOpenChat!();
                            return;
                          }

                          final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id ?? 'default_user';
                          final res = await provider.respondToCheckin(
                            nudgeId: (nudge['id'] ?? '').toString(),
                            selectedOptionId: optId,
                            userId: userId,
                          );

                          if (res != null && context.mounted) {
                            final aiReply = res['ai_reply'] as String? ?? 'Đã lưu phản hồi!';
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Row(
                                  children: [
                                    const Icon(Icons.auto_awesome, color: Colors.amber, size: 20),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        aiReply,
                                        style: const TextStyle(fontSize: 13),
                                      ),
                                    ),
                                  ],
                                ),
                                backgroundColor: const Color(0xFF1E293B),
                                duration: const Duration(seconds: 4),
                                behavior: SnackBarBehavior.floating,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                            );
                          }
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.9),
                            borderRadius: BorderRadius.circular(20),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.08),
                                blurRadius: 4,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: Text(
                            label,
                            style: const TextStyle(
                              color: Color(0xFF1E293B),
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
