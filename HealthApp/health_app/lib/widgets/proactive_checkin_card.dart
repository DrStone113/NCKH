import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/proactive_provider.dart';
import '../providers/user_provider.dart';
import '../providers/nutrition_provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/health_provider.dart';

class ProactiveCheckinCard extends StatelessWidget {
  final VoidCallback? onOpenChat;

  const ProactiveCheckinCard({
    super.key,
    this.onOpenChat,
  });

  IconData _getCategoryIcon(String category) {
    switch (category) {
      case 'hydration':
        return Icons.water_drop;
      case 'nutrition':
        return Icons.restaurant;
      case 'fitness':
        return Icons.fitness_center;
      case 'mental':
        return Icons.spa;
      default:
        return Icons.chat_bubble_outline;
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
        var nudge = provider.activeNudge;
        
        // Fallback: nếu không có server nudge, tạo Nudge AI dựa trên dữ liệu sức khỏe thực tế hôm nay
        if ((nudge == null || provider.isDismissed)) {
          final nutrition = Provider.of<NutritionProvider>(context, listen: false);
          final exercise = Provider.of<ExerciseProvider>(context, listen: false);
          final health = Provider.of<HealthProvider>(context, listen: false);

          if (health.todayWaterIntake < 1000) {
            nudge = {
              'category': 'hydration',
              'title': '💡 AI Nudge: Nạp nước sinh hoạt',
              'message': 'Hôm nay bạn mới nạp ${health.todayWaterIntake.toStringAsFixed(0)}ml nước. Cơ thể cần khoảng 2000ml để duy trì năng lượng và sự tập trung!',
              'quick_options': [
                {'id': 'water_500', 'label': '+ 500ml Nước', 'action_type': 'quick_log'},
                {'id': 'open_chat', 'label': '💬 Hỏi Trợ lý AI', 'action_type': 'chat'},
              ]
            };
          } else if (nutrition.todayMeals.isEmpty) {
            nudge = {
              'category': 'nutrition',
              'title': '💡 AI Nudge: Nhật ký dinh dưỡng',
              'message': 'Bạn chưa ghi nhận bữa ăn nào hôm nay. Kể cho AI trợ lý món bạn đã ăn để theo dõi calo chuẩn xác nhé!',
              'quick_options': [
                {'id': 'open_chat', 'label': '💬 Nhắn cho AI món đã ăn', 'action_type': 'chat'},
              ]
            };
          } else if (exercise.todayExercises.isEmpty) {
            nudge = {
              'category': 'fitness',
              'title': '💡 AI Nudge: Gợi ý vận động',
              'message': 'Hôm nay bạn chưa có buổi tập nào. Hãy dành 15-20 phút vận động nhẹ nhàng để sảng khoái hơn!',
              'quick_options': [
                {'id': 'open_chat', 'label': '🏃 Nhờ AI gợi ý bài tập', 'action_type': 'chat'},
              ]
            };
          } else {
            return const SizedBox.shrink();
          }
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
                color: Colors.black.withValues(alpha: 0.15),
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
                        color: Colors.white.withValues(alpha: 0.25),
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
                      icon: const Icon(Icons.close, color: Colors.white70, size: 20),
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
                          if (actionType == 'quick_log' && optId == 'water_500') {
                            final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
                            if (userId != null) {
                              await Provider.of<HealthProvider>(context, listen: false).addWater(userId, 500);
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: const Row(
                                      children: [
                                        Icon(Icons.water_drop, color: Colors.lightBlueAccent, size: 20),
                                        SizedBox(width: 8),
                                        Text('Đã cộng thêm 500ml nước uống!'),
                                      ],
                                    ),
                                    backgroundColor: const Color(0xFF1E293B),
                                    duration: const Duration(seconds: 3),
                                    behavior: SnackBarBehavior.floating,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                  ),
                                );
                              }
                            }
                            return;
                          }

                          if (actionType == 'chat' && onOpenChat != null) {
                            onOpenChat!();
                            return;
                          }

                          final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id ?? 'default_user';
                          final res = await provider.respondToCheckin(
                            nudgeId: (nudge?['id'] ?? '').toString(),
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
                            color: Colors.white.withValues(alpha: 0.9),
                            borderRadius: BorderRadius.circular(20),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.08),
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
