import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../models/user_model.dart';
import '../../../providers/proactive_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';
import '../../auth/screens/auth_wrapper.dart';
import '../../chat/screens/chatbot_screen.dart';
import 'chat_history_settings_screen.dart';
import 'checkin_settings_screen.dart';
import 'goal_settings_screen.dart';
import 'profile_settings_screen.dart';

class AccountSettingsScreen extends StatelessWidget {
  const AccountSettingsScreen({super.key});

  Future<void> _open(BuildContext context, Widget screen) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => screen),
    );
  }

  Future<void> _showLogoutDialog(BuildContext context) async {
    final confirmed = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.logout, color: AppColors.error),
                SizedBox(width: 8),
                Text('Đăng xuất'),
              ],
            ),
            content: const Text(
              'Bạn có chắc chắn muốn đăng xuất khỏi tài khoản không?',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Hủy'),
              ),
              FilledButton(
                key: const ValueKey('account-logout-confirm'),
                onPressed: () => Navigator.pop(dialogContext, true),
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.error,
                ),
                child: const Text('Đăng xuất'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !context.mounted) return;

    await context.read<UserProvider>().signOut();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AuthWrapper()),
      (_) => false,
    );
  }

  void _showAbout(BuildContext context) {
    showAboutDialog(
      context: context,
      applicationName: 'HealthApp AI',
      applicationVersion: '1.0.0 (1)',
      applicationIcon: Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFFFF8C00), Color(0xFFFF5500)],
          ),
          borderRadius: BorderRadius.circular(14),
        ),
        child: const Icon(Icons.health_and_safety, color: Colors.white),
      ),
      children: const [
        Text(
          'Ứng dụng theo dõi dinh dưỡng, vận động và sức khỏe cá nhân với trợ lý AI.',
        ),
      ],
    );
  }

  String _checkinSummary(ProactiveProvider provider) {
    final settings = provider.checkinSettings;
    if (!(settings['enable_proactive'] ?? true)) {
      return 'Đang tắt';
    }
    const categories = [
      'water_checkin',
      'nutrition_checkin',
      'fitness_checkin',
      'mood_checkin',
    ];
    final enabled = categories.where((key) => settings[key] ?? true).length;
    return '$enabled/4 nhóm nội dung đang bật';
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<UserProvider>().currentUser;
    final proactive = context.watch<ProactiveProvider>();

    return Scaffold(
      appBar: AppBar(
        centerTitle: false,
        title: const Text('Cài đặt'),
      ),
      body: user == null
          ? const Center(child: CircularProgressIndicator())
          : SafeArea(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
                children: [
                  _ProfileHeader(
                    user: user,
                    onEdit: () => _open(
                      context,
                      const ProfileSettingsScreen(),
                    ),
                  ),
                  const SizedBox(height: 22),
                  const _SectionLabel('Hồ sơ sức khỏe'),
                  const SizedBox(height: 9),
                  _SettingsSection(
                    children: [
                      _SettingsTile(
                        icon: Icons.person_outline,
                        color: const Color(0xFF2563EB),
                        title: 'Thông tin cá nhân',
                        subtitle:
                            '${user.age} tuổi • ${user.height.toStringAsFixed(0)} cm • ${user.weight.toStringAsFixed(1)} kg',
                        onTap: () => _open(
                          context,
                          const ProfileSettingsScreen(),
                        ),
                      ),
                      _SettingsTile(
                        icon: Icons.flag_outlined,
                        color: const Color(0xFFF97316),
                        title: 'Mục tiêu sức khỏe',
                        subtitle: user.displayRecommendedCalories == null
                            ? '${user.healthGoalText} • Cần hướng dẫn chuyên gia'
                            : '${user.healthGoalText} • ${user.displayRecommendedCalories!.toStringAsFixed(0)} kcal/ngày',
                        onTap: () => _open(
                          context,
                          const GoalSettingsScreen(),
                        ),
                      ),
                      _SettingsTile(
                        icon: Icons.directions_run,
                        color: const Color(0xFF16A34A),
                        title: 'Mức độ vận động',
                        subtitle: user.activityLevelText,
                        onTap: () => _open(
                          context,
                          const ProfileSettingsScreen(),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  const _SectionLabel('Trợ lý & nhắc nhở'),
                  const SizedBox(height: 9),
                  _SettingsSection(
                    children: [
                      _SettingsTile(
                        icon: Icons.notifications_active_outlined,
                        color: const Color(0xFF7C3AED),
                        title: 'Nhắc nhở sức khỏe',
                        subtitle: _checkinSummary(proactive),
                        onTap: () => _open(
                          context,
                          const CheckinSettingsScreen(),
                        ),
                      ),
                      _SettingsTile(
                        icon: Icons.smart_toy_outlined,
                        color: const Color(0xFFFF6F00),
                        title: 'Mở trợ lý AI',
                        subtitle: 'Tư vấn dinh dưỡng, vận động và lối sống',
                        onTap: () => _open(
                          context,
                          const ChatbotScreen(),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  const _SectionLabel('Dữ liệu & ứng dụng'),
                  const SizedBox(height: 9),
                  _SettingsSection(
                    children: [
                      _SettingsTile(
                        icon: Icons.history,
                        color: const Color(0xFF0891B2),
                        title: 'Lịch sử hội thoại',
                        subtitle: 'Xem, mở lại hoặc xóa các phiên chat',
                        onTap: () => _open(
                          context,
                          const ChatHistorySettingsScreen(),
                        ),
                      ),
                      _SettingsTile(
                        icon: Icons.info_outline,
                        color: const Color(0xFF475569),
                        title: 'Giới thiệu ứng dụng',
                        subtitle: 'Phiên bản 1.0.0 (1)',
                        onTap: () => _showAbout(context),
                      ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  _SettingsSection(
                    children: [
                      Semantics(
                        label: 'account-logout',
                        button: true,
                        child: _SettingsTile(
                          key: const ValueKey('account-logout'),
                          icon: Icons.logout,
                          color: AppColors.error,
                          title: 'Đăng xuất',
                          subtitle:
                              'Kết thúc phiên đăng nhập trên thiết bị này',
                          titleColor: AppColors.error,
                          showChevron: false,
                          onTap: () => _showLogoutDialog(context),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  const Center(
                    child: Text(
                      'HealthApp AI • Dữ liệu sức khỏe thuộc quyền kiểm soát của bạn',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: AppColors.textHint,
                        fontSize: 11,
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.user, required this.onEdit});

  final UserModel user;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final initial = user.name.trim().isEmpty
        ? 'U'
        : user.name.trim().characters.first.toUpperCase();
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF111827), Color(0xFF334155)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 18,
            offset: const Offset(0, 7),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white24),
                ),
                alignment: Alignment.center,
                child: Text(
                  initial,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      user.email,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton.filledTonal(
                onPressed: onEdit,
                tooltip: 'Chỉnh sửa hồ sơ',
                icon: const Icon(Icons.edit_outlined, size: 19),
                style: IconButton.styleFrom(
                  backgroundColor: Colors.white.withValues(alpha: 0.12),
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _HeaderMetric(
                  label: 'BMI',
                  value: user.displayBmi.toStringAsFixed(1),
                ),
              ),
              const _HeaderDivider(),
              Expanded(
                child: _HeaderMetric(
                  label: 'TDEE ước tính',
                  value: user.displayTdee == null
                      ? 'Cần xác nhận đầu vào RMR'
                      : '${user.displayTdee!.toStringAsFixed(0)} kcal',
                ),
              ),
              const _HeaderDivider(),
              Expanded(
                child: _HeaderMetric(
                  label: 'Mục tiêu',
                  value: user.healthGoalText,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeaderMetric extends StatelessWidget {
  const _HeaderMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(height: 3),
        Text(
          label,
          style: const TextStyle(color: Colors.white60, fontSize: 10),
        ),
      ],
    );
  }
}

class _HeaderDivider extends StatelessWidget {
  const _HeaderDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 28,
      color: Colors.white.withValues(alpha: 0.15),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 4),
      child: Text(
        text,
        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      elevation: 1,
      shadowColor: Colors.black.withValues(alpha: 0.08),
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: Color(0xFFE2E8F0)),
      ),
      child: Column(
        children: [
          for (var index = 0; index < children.length; index++) ...[
            children[index],
            if (index < children.length - 1)
              const Divider(height: 1, indent: 66),
          ],
        ],
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    super.key,
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.titleColor,
    this.showChevron = true,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color? titleColor;
  final bool showChevron;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 13, vertical: 5),
      leading: Container(
        width: 42,
        height: 42,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Icon(icon, color: color, size: 21),
      ),
      title: Text(
        title,
        style: TextStyle(
          color: titleColor ?? AppColors.textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
      subtitle: Text(
        subtitle,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(
          color: AppColors.textSecondary,
          fontSize: 11,
          height: 1.35,
        ),
      ),
      trailing: showChevron
          ? const Icon(Icons.chevron_right, color: AppColors.textHint)
          : null,
    );
  }
}
