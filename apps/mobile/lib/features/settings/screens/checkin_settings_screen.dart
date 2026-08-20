import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../providers/proactive_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';

class CheckinSettingsScreen extends StatefulWidget {
  const CheckinSettingsScreen({super.key});

  @override
  State<CheckinSettingsScreen> createState() => _CheckinSettingsScreenState();
}

class _CheckinSettingsScreenState extends State<CheckinSettingsScreen> {
  Map<String, bool> _draft = Map.of(ProactiveProvider.defaultCheckinSettings);
  bool _initialized = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final userId = context.read<UserProvider>().currentUser?.id;
    if (userId == null) return;
    final provider = context.read<ProactiveProvider>();
    await provider.loadCheckinSettings(userId);
    if (!mounted) return;
    setState(() {
      _draft = Map.of(provider.checkinSettings);
      _initialized = true;
    });
  }

  Future<void> _save() async {
    final userId = context.read<UserProvider>().currentUser?.id;
    if (userId == null) return;
    final provider = context.read<ProactiveProvider>();
    final synced = await provider.updateCheckinSettings(userId, _draft);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          synced
              ? 'Đã lưu cài đặt nhắc nhở'
              : 'Đã lưu trên thiết bị; sẽ đồng bộ khi backend hoạt động',
        ),
      ),
    );
    Navigator.pop(context);
  }

  void _set(String key, bool value) {
    setState(() => _draft[key] = value);
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ProactiveProvider>();
    final masterEnabled = _draft['enable_proactive'] ?? true;
    final loading = provider.isLoadingSettings && !_initialized;

    return Scaffold(
      appBar: AppBar(title: const Text('Nhắc nhở sức khỏe')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
              children: [
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF0F172A), Color(0xFF334155)],
                    ),
                    borderRadius: BorderRadius.circular(22),
                  ),
                  child: const Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.notifications_active_outlined,
                        color: Colors.white,
                        size: 28,
                      ),
                      SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Check-in chủ động',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 17,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            SizedBox(height: 5),
                            Text(
                              'Trợ lý chỉ hiện lời nhắc trong ứng dụng khi có dữ liệu đáng chú ý.',
                              style: TextStyle(
                                color: Colors.white70,
                                fontSize: 13,
                                height: 1.4,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                _SettingsGroup(
                  children: [
                    _CheckinSwitch(
                      icon: Icons.auto_awesome,
                      color: AppColors.primary,
                      title: 'Bật check-in chủ động',
                      subtitle: 'Cho phép trợ lý chọn lời nhắc phù hợp.',
                      value: masterEnabled,
                      onChanged: (value) => _set('enable_proactive', value),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                const Text(
                  'Nội dung muốn nhận',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 10),
                _SettingsGroup(
                  children: [
                    _CheckinSwitch(
                      icon: Icons.water_drop_outlined,
                      color: const Color(0xFF0284C7),
                      title: 'Uống nước',
                      subtitle: 'Nhắc khi lượng nước trong ngày còn thấp.',
                      value: _draft['water_checkin'] ?? true,
                      enabled: masterEnabled,
                      onChanged: (value) => _set('water_checkin', value),
                    ),
                    _CheckinSwitch(
                      icon: Icons.restaurant_outlined,
                      color: const Color(0xFFF97316),
                      title: 'Dinh dưỡng',
                      subtitle: 'Theo dõi bữa ăn và mức calo trong ngày.',
                      value: _draft['nutrition_checkin'] ?? true,
                      enabled: masterEnabled,
                      onChanged: (value) => _set('nutrition_checkin', value),
                    ),
                    _CheckinSwitch(
                      icon: Icons.fitness_center,
                      color: const Color(0xFF16A34A),
                      title: 'Vận động',
                      subtitle: 'Gợi ý vận động dựa trên nhật ký hôm nay.',
                      value: _draft['fitness_checkin'] ?? true,
                      enabled: masterEnabled,
                      onChanged: (value) => _set('fitness_checkin', value),
                    ),
                    _CheckinSwitch(
                      icon: Icons.sentiment_satisfied_alt,
                      color: const Color(0xFF7C3AED),
                      title: 'Tâm trạng',
                      subtitle: 'Check-in nhẹ nhàng vào cuối ngày.',
                      value: _draft['mood_checkin'] ?? true,
                      enabled: masterEnabled,
                      onChanged: (value) => _set('mood_checkin', value),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                const Text(
                  'Đây là nhắc nhở bên trong HealthApp, không phải thông báo hệ thống chạy nền.',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
              ],
            ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: FilledButton.icon(
            onPressed: provider.isSavingSettings ? null : _save,
            icon: provider.isSavingSettings
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(
                      color: Colors.white,
                      strokeWidth: 2,
                    ),
                  )
                : const Icon(Icons.save_outlined),
            label: Text(
              provider.isSavingSettings ? 'Đang lưu...' : 'Lưu cài đặt',
            ),
          ),
        ),
      ),
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  const _SettingsGroup({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFFE2E8F0)),
      ),
      child: Column(
        children: [
          for (var index = 0; index < children.length; index++) ...[
            children[index],
            if (index < children.length - 1)
              const Divider(height: 1, indent: 64),
          ],
        ],
      ),
    );
  }
}

class _CheckinSwitch extends StatelessWidget {
  const _CheckinSwitch({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.enabled = true,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      value: value,
      onChanged: enabled ? onChanged : null,
      hoverColor: AppColors.surfaceLight.withValues(alpha: 0.65),
      overlayColor: const WidgetStatePropertyAll(Colors.transparent),
      secondary: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: color.withValues(alpha: enabled ? 0.1 : 0.05),
          borderRadius: BorderRadius.circular(12),
        ),
        child:
            Icon(icon, color: enabled ? color : AppColors.textHint, size: 21),
      ),
      title: Text(
        title,
        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
      ),
      subtitle: Text(
        subtitle,
        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
    );
  }
}
