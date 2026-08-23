import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../models/canonical_nutrition.dart';

class HealthStatsScreen extends StatefulWidget {
  const HealthStatsScreen({super.key});

  @override
  State<HealthStatsScreen> createState() => _HealthStatsScreenState();
}

class _HealthStatsScreenState extends State<HealthStatsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final userId =
          Provider.of<UserProvider>(context, listen: false).currentUser?.id;
      if (userId != null) {
        Provider.of<HealthProvider>(context, listen: false)
            .loadWeightHistory(userId);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;
    final healthProvider = Provider.of<HealthProvider>(context);

    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chỉ số sức khỏe'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Personal info
            _buildPersonalInfoCard(user),
            const SizedBox(height: 16),

            // Health metrics grid
            _buildMetricsGrid(user),
            const SizedBox(height: 20),

            // Weight chart
            const Text('Biểu đồ cân nặng',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _buildWeightChart(healthProvider),
            const SizedBox(height: 20),

            // BMI Scale
            _buildBmiScale(user),
            const SizedBox(height: 20),

            // Recommendations
            _buildRecommendations(user),
          ],
        ),
      ),
    );
  }

  Widget _buildPersonalInfoCard(dynamic user) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AppColors.primaryGradient,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(
              user.gender == 'male'
                  ? Icons.person
                  : user.gender == 'female'
                      ? Icons.person_2
                      : Icons.person_outline,
              color: Colors.white,
              size: 28,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(user.name,
                    style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Colors.white)),
                const SizedBox(height: 4),
                Text(
                  '${user.age} tuổi • ${_genderLabel(user.gender)} • ${user.activityLevelText}',
                  style: TextStyle(
                      fontSize: 13, color: Colors.white.withValues(alpha: 0.8)),
                ),
              ],
            ),
          ),
          // Nút chỉnh sửa độ tuổi
          IconButton(
            onPressed: () => _showUpdateAgeDialog(context),
            icon: const Icon(Icons.edit, color: Colors.white, size: 20),
            tooltip: 'Cập nhật độ tuổi',
          ),
        ],
      ),
    );
  }

  Widget _buildMetricsGrid(dynamic user) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.5,
      children: [
        _metricCard('BMI', user.displayBmi.toStringAsFixed(1), user.bmiCategory,
            _getBmiColor(user.bmiCategoryCode)),
        _metricCard(
            'RMR ước tính',
            user.displayRmr?.toStringAsFixed(0) ?? 'Chưa có',
            'kcal/ngày',
            AppColors.accent),
        _metricCard(
            'TDEE ước tính',
            user.displayTdee?.toStringAsFixed(0) ?? 'Chưa có',
            'kcal/ngày',
            AppColors.primary),
        _metricCard(
            'Mỡ cơ thể',
            user.estimatedBodyFat == null
                ? 'Chưa có'
                : '${user.estimatedBodyFat!.toStringAsFixed(1)}%',
            'ước tính',
            AppColors.warning),
        _metricCard(
          'Chiều cao',
          '${user.height.toStringAsFixed(0)}',
          'cm',
          AppColors.info,
          onEdit: () => _showUpdateHeightDialog(context),
        ),
        _metricCard(
          'Cân nặng',
          '${user.weight.toStringAsFixed(1)}',
          'kg',
          AppColors.calories,
          onEdit: () => _showUpdateWeightDialog(context),
        ),
      ],
    );
  }

  Widget _metricCard(String title, String value, String subtitle, Color color,
      {VoidCallback? onEdit}) {
    return GestureDetector(
      onTap: onEdit,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.textSecondary)),
                if (onEdit != null)
                  Icon(Icons.edit,
                      size: 16, color: color.withValues(alpha: 0.6)),
              ],
            ),
            const SizedBox(height: 4),
            Text(value,
                style: TextStyle(
                    fontSize: 22, fontWeight: FontWeight.bold, color: color)),
            Text(subtitle,
                style:
                    const TextStyle(fontSize: 11, color: AppColors.textHint)),
          ],
        ),
      ),
    );
  }

  Widget _buildWeightChart(HealthProvider healthProvider) {
    final history = healthProvider.weightHistory;

    if (history.isEmpty) {
      return Container(
        height: 200,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(16),
        ),
        child: const Center(
          child: Text(
            'Chưa có dữ liệu cân nặng\nCập nhật cân nặng để xem biểu đồ',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
        ),
      );
    }

    final spots = history.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value.weight);
    }).toList();

    final minWeight = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
    final maxWeight = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);

    return Container(
      height: 220,
      padding: const EdgeInsets.fromLTRB(8, 20, 16, 8),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: LineChart(
        LineChartData(
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (value) => const FlLine(
              color: AppColors.surfaceLight,
              strokeWidth: 1,
            ),
          ),
          titlesData: FlTitlesData(
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 40,
                getTitlesWidget: (value, meta) => Text(
                  value.toStringAsFixed(0),
                  style: const TextStyle(
                      fontSize: 10, color: AppColors.textSecondary),
                ),
              ),
            ),
            bottomTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            topTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          borderData: FlBorderData(show: false),
          minX: 0,
          maxX: (spots.length - 1).toDouble(),
          minY: minWeight - 2,
          maxY: maxWeight + 2,
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: AppColors.primary,
              barWidth: 3,
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, barData, index) {
                  return FlDotCirclePainter(
                    radius: 4,
                    color: AppColors.primary,
                    strokeWidth: 2,
                    strokeColor: Colors.white,
                  );
                },
              ),
              belowBarData: BarAreaData(
                show: true,
                color: AppColors.primary.withValues(alpha: 0.1),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBmiScale(dynamic user) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Thang đo BMI (Tiêu chuẩn Việt Nam)',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          ...NutritionPolicyV1.bmiCategories.map(
            (category) => _bmiRange(
              category.label,
              category.displayRange,
              _getBmiColor(category.code),
              user.bmiCategoryCode == category.code,
            ),
          ),
        ],
      ),
    );
  }

  Widget _bmiRange(String label, String range, Color color, bool isActive) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isActive ? color.withValues(alpha: 0.15) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        border:
            isActive ? Border.all(color: color.withValues(alpha: 0.4)) : null,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                  width: 12,
                  height: 12,
                  decoration: BoxDecoration(
                      color: color, borderRadius: BorderRadius.circular(3))),
              const SizedBox(width: 10),
              Text(label,
                  style: TextStyle(
                      fontWeight:
                          isActive ? FontWeight.bold : FontWeight.normal)),
            ],
          ),
          Text(range,
              style: const TextStyle(
                  fontSize: 13, color: AppColors.textSecondary)),
          if (isActive) Icon(Icons.check_circle, color: color, size: 18),
        ],
      ),
    );
  }

  Widget _buildRecommendations(dynamic user) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Khuyến nghị',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const Divider(color: AppColors.surfaceLight),
          const SizedBox(height: 8),
          _recommendItem(
              Icons.restaurant,
              'Mục tiêu calo',
              user.displayRecommendedCalories == null
                  ? 'Cần hướng dẫn chuyên gia'
                  : '${user.displayRecommendedCalories!.toStringAsFixed(0)} kcal/ngày (${user.healthGoalText})'),
          _recommendItem(
              Icons.water_drop,
              'Mục tiêu dịch gần đúng',
              user.displayDailyWaterGoal == null
                  ? 'Không khả dụng'
                  : '${user.displayDailyWaterGoal!.toStringAsFixed(1)} lít/ngày (ước tính)'),
          _recommendItem(
              Icons.fitness_center, 'Vận động', '150-300 phút/tuần theo WHO'),
          _recommendItem(Icons.bedtime, 'Giấc ngủ', '7-9 giờ/đêm'),
          const SizedBox(height: 8),
          Text(user.bmiAdvice,
              style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary,
                  fontStyle: FontStyle.italic)),
        ],
      ),
    );
  }

  Widget _recommendItem(IconData icon, String title, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600)),
                Text(value,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _genderLabel(String? gender) => switch (gender) {
        'male' => 'Nam',
        'female' => 'Nữ',
        _ => 'Chưa cung cấp',
      };

  Color _getBmiColor(String? code) => switch (code) {
        'UNDERWEIGHT' => AppColors.info,
        'NORMAL' => AppColors.success,
        'OVERWEIGHT' => AppColors.warning,
        'OBESITY_I' => const Color(0xFFFF9800),
        'OBESITY_II' => AppColors.error,
        _ => AppColors.textSecondary,
      };

  void _showUpdateWeightDialog(BuildContext context) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Cập nhật cân nặng'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Cân nặng (kg)',
            suffixText: 'kg',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () async {
              final weight = double.tryParse(controller.text);
              if (weight != null && weight > 0) {
                final userProvider =
                    Provider.of<UserProvider>(context, listen: false);
                final healthProvider =
                    Provider.of<HealthProvider>(context, listen: false);
                await userProvider.updateWeight(weight);
                if (userProvider.currentUser != null) {
                  await healthProvider
                      .loadWeightHistory(userProvider.currentUser!.id);
                }
                if (context.mounted) Navigator.pop(context);
              }
            },
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
  }

  void _showUpdateHeightDialog(BuildContext context) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    final controller =
        TextEditingController(text: user?.height.toStringAsFixed(0));

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Cập nhật chiều cao'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Chiều cao (cm)',
            suffixText: 'cm',
            helperText: 'Ví dụ: 170',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () async {
              final height = double.tryParse(controller.text);
              if (height != null && height > 50 && height < 300) {
                await Provider.of<UserProvider>(context, listen: false)
                    .updateHeight(height);
                if (context.mounted) Navigator.pop(context);
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content:
                          Text('Vui lòng nhập chiều cao hợp lệ (50-300 cm)')),
                );
              }
            },
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
  }

  void _showUpdateAgeDialog(BuildContext context) {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    final controller = TextEditingController(text: user?.age.toString());

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Cập nhật độ tuổi'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Tuổi',
            suffixText: 'tuổi',
            helperText: 'Ví dụ: 25',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () async {
              final age = int.tryParse(controller.text);
              if (age != null && age > 0 && age < 150) {
                await Provider.of<UserProvider>(context, listen: false)
                    .updateAge(age);
                if (context.mounted) Navigator.pop(context);
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content: Text('Vui lòng nhập tuổi hợp lệ (1-150)')),
                );
              }
            },
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
  }
}
