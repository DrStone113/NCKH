import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/lifestyle_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../models/lifestyle_model.dart';

class LifestyleScreen extends StatefulWidget {
  const LifestyleScreen({super.key});

  @override
  State<LifestyleScreen> createState() => _LifestyleScreenState();
}

class _LifestyleScreenState extends State<LifestyleScreen> {
  final _waterController = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = Provider.of<UserProvider>(context, listen: false).currentUser;
      final userId = user?.id ?? 'demo';
      Provider.of<LifestyleProvider>(context, listen: false).loadTodayLogs(userId);
    });
  }

  @override
  void dispose() {
    _waterController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;
    final userId = user?.id ?? 'demo';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'Sức khỏe Tinh thần & Lifestyle',
          style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.textPrimary),
        ),
        backgroundColor: AppColors.surface,
        elevation: 0.5,
        centerTitle: true,
      ),
      body: Consumer<LifestyleProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          final log = provider.todayLog;

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Banner giới thiệu Module 3
                _buildHeaderBanner(),
                const SizedBox(height: 20),

                // Card 1: Check-in Tâm trạng (Mood Check-in)
                _buildMoodCard(context, provider, userId, log),
                const SizedBox(height: 16),

                // Card 2: Giấc ngủ & Mức độ Stress
                _buildSleepAndStressCard(context, provider, userId, log),
                const SizedBox(height: 16),

                // Card 3: Tiến trình Uống nước (Hydration Tracker)
                _buildHydrationCard(context, provider, userId, log),
                const SizedBox(height: 16),

                // Card 4: Danh sách Nhắc nhở Sinh hoạt (Reminders)
                _buildRemindersCard(context, provider, userId),
                const SizedBox(height: 24),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildHeaderBanner() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF673AB7), Color(0xFF512DA8)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.purple.withValues(alpha: 0.2),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.spa, color: Colors.white, size: 28),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Module 3: Tâm trí & Lối sống',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 8),
          Text(
            'Theo dõi cảm xúc, chất lượng giấc ngủ, nhịp stress và duy trì thói quen uống nước tích cực hàng ngày.',
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
        ],
      ),
    );
  }

  Widget _buildMoodCard(
    BuildContext context,
    LifestyleProvider provider,
    String userId,
    LifestyleLog log,
  ) {
    final moodEmojis = ['😞', '🙁', '😐', '🙂', '😄'];
    final moodLabels = ['Rất tệ', 'Tệ', 'Bình thường', 'Tốt', 'Rất tốt'];

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.sentiment_satisfied_alt, color: Color(0xFFE91E63)),
                SizedBox(width: 8),
                Text(
                  'Check-in Tâm trạng',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: List.generate(5, (index) {
                final score = index + 1;
                final isSelected = log.moodScore == score;
                return GestureDetector(
                  onTap: () {
                    provider.logMood(userId, score, moodLabels[index]);
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? const Color(0xFFE91E63).withValues(alpha: 0.15)
                          : Colors.grey.shade100,
                      shape: BoxShape.circle,
                      border: isSelected
                          ? Border.all(color: const Color(0xFFE91E63), width: 2)
                          : null,
                    ),
                    child: Text(
                      moodEmojis[index],
                      style: const TextStyle(fontSize: 28),
                    ),
                  ),
                );
              }),
            ),
            const SizedBox(height: 12),
            Center(
              child: Text(
                'Tâm trạng hiện tại: ${log.moodLabel}',
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 15,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSleepAndStressCard(
    BuildContext context,
    LifestyleProvider provider,
    String userId,
    LifestyleLog log,
  ) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.bedtime, color: Color(0xFF3F51B5)),
                SizedBox(width: 8),
                Text(
                  'Giấc ngủ & Độ Căng thẳng (Stress)',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 16),
            // Giấc ngủ
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Giấc ngủ hôm qua:'),
                Text(
                  '${log.sleepHours.toStringAsFixed(1)} giờ',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
              ],
            ),
            Slider(
              value: log.sleepHours.clamp(3.0, 12.0),
              min: 3.0,
              max: 12.0,
              divisions: 18,
              activeColor: const Color(0xFF3F51B5),
              label: '${log.sleepHours.toStringAsFixed(1)} giờ',
              onChanged: (val) {
                provider.logSleepAndStress(userId, val, log.stressScore);
              },
            ),
            const Divider(height: 24),
            // Stress level
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Mức độ Căng thẳng (1-5):'),
                Text(
                  'Mức ${log.stressScore}/5',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: log.stressScore >= 4 ? Colors.red : Colors.green,
                  ),
                ),
              ],
            ),
            Slider(
              value: log.stressScore.toDouble().clamp(1.0, 5.0),
              min: 1.0,
              max: 5.0,
              divisions: 4,
              activeColor: log.stressScore >= 4 ? Colors.red : Colors.green,
              label: 'Mức ${log.stressScore}',
              onChanged: (val) {
                provider.logSleepAndStress(userId, log.sleepHours, val.toInt());
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHydrationCard(
    BuildContext context,
    LifestyleProvider provider,
    String userId,
    LifestyleLog log,
  ) {
    const targetWater = 2500.0; // Target 2.5L
    final percent = (log.waterIntakeMl / targetWater).clamp(0.0, 1.0);

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.water_drop, color: Color(0xFF0288D1)),
                SizedBox(width: 8),
                Text(
                  'Nhật ký Nước uống (Hydration)',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '${log.waterIntakeMl.toInt()} / ${targetWater.toInt()} ml',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                Text(
                  '${(percent * 100).toInt()}%',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF0288D1),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: percent,
                minHeight: 12,
                backgroundColor: Colors.blue.shade50,
                valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF0288D1)),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                ElevatedButton.icon(
                  onPressed: () => provider.addWater(userId, 250),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('+250 ml'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF0288D1),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: () => provider.addWater(userId, 500),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('+500 ml'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF0288D1),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRemindersCard(
    BuildContext context,
    LifestyleProvider provider,
    String userId,
  ) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Row(
                  children: [
                    Icon(Icons.alarm, color: Color(0xFFFF9800)),
                    SizedBox(width: 8),
                    Text(
                      'Nhắc nhở Sinh hoạt',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                IconButton(
                  icon: const Icon(Icons.add_circle, color: Color(0xFFFF9800)),
                  onPressed: () => _showAddReminderDialog(context, provider, userId),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (provider.reminders.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Chưa có nhắc nhở nào.', style: TextStyle(color: Colors.grey)),
              )
            else
              Column(
                children: provider.reminders.map((rem) {
                  return SwitchListTile(
                    activeColor: const Color(0xFFFF9800),
                    title: Text(rem.title, style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text('Thời gian: ${rem.time}'),
                    value: rem.isActive,
                    onChanged: (_) => provider.toggleReminder(rem.id),
                  );
                }).toList(),
              ),
          ],
        ),
      ),
    );
  }

  void _showAddReminderDialog(
    BuildContext context,
    LifestyleProvider provider,
    String userId,
  ) {
    final titleController = TextEditingController();
    final timeController = TextEditingController(text: '08:00');

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Thêm Nhắc nhở Sinh hoạt'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: titleController,
              decoration: const InputDecoration(labelText: 'Tên nhắc nhở (vd: Uống nước)'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: timeController,
              decoration: const InputDecoration(labelText: 'Giờ nhắc nhở (vd: 09:00)'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () {
              final title = titleController.text.trim();
              if (title.isNotEmpty) {
                final rem = LifestyleReminder(
                  id: 'rem_${DateTime.now().millisecondsSinceEpoch}',
                  userId: userId,
                  title: title,
                  type: 'lifestyle',
                  time: timeController.text.trim(),
                  isActive: true,
                );
                provider.addReminder(userId, rem);
              }
              Navigator.pop(ctx);
            },
            child: const Text('Thêm'),
          ),
        ],
      ),
    );
  }
}
