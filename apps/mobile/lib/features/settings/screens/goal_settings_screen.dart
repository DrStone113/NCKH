import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';

class GoalSettingsScreen extends StatefulWidget {
  const GoalSettingsScreen({super.key});

  @override
  State<GoalSettingsScreen> createState() => _GoalSettingsScreenState();
}

class _GoalSettingsScreenState extends State<GoalSettingsScreen> {
  String? _selectedGoal;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    // Map full format to short format for UI
    if (user?.healthGoal != null) {
      switch (user!.healthGoal.toLowerCase()) {
        case 'lose':
        case 'lose_weight':
          _selectedGoal = 'lose';
          break;
        case 'gain':
        case 'gain_muscle':
          _selectedGoal = 'gain';
          break;
        case 'maintain':
          _selectedGoal = 'maintain';
          break;
        default:
          _selectedGoal = 'maintain';
      }
    } else {
      _selectedGoal = 'maintain';
    }
  }

  Future<void> _saveGoal() async {
    if (_selectedGoal == null) return;

    setState(() => _isLoading = true);

    try {
      final userProvider = Provider.of<UserProvider>(context, listen: false);
      final currentUser = userProvider.currentUser;

      if (currentUser != null) {
        // Map short format to full format for backend compatibility
        String fullGoalFormat = _selectedGoal!;
        switch (_selectedGoal) {
          case 'lose':
            fullGoalFormat = 'lose_weight';
            break;
          case 'gain':
            fullGoalFormat = 'gain_muscle';
            break;
          case 'maintain':
            fullGoalFormat = 'maintain';
            break;
        }

        final updatedUser = currentUser.copyWith(healthGoal: fullGoalFormat);
        await userProvider.updateProfile(updatedUser);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('✅ Đã cập nhật mục tiêu thành công!'),
              backgroundColor: AppColors.success,
              duration: Duration(seconds: 2),
            ),
          );
          Navigator.pop(context);
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ Lỗi: $e'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Thay đổi mục tiêu'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Header
                    const Center(
                      child: Column(
                        children: [
                          Text(
                            '🎯',
                            style: TextStyle(fontSize: 64),
                          ),
                          SizedBox(height: 16),
                          Text(
                            'Mục tiêu sức khỏe',
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'Chọn mục tiêu phù hợp với bạn',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 16,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 32),

                    // Current stats
                    if (user != null) ...[
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _buildStatItem(
                              'Cân nặng',
                              '${user.weight.toStringAsFixed(1)} kg',
                              Icons.monitor_weight,
                            ),
                            Container(
                              width: 1,
                              height: 40,
                              color: AppColors.surface,
                            ),
                            _buildStatItem(
                              'BMI',
                              user.bmi.toStringAsFixed(1),
                              Icons.analytics,
                            ),
                            Container(
                              width: 1,
                              height: 40,
                              color: AppColors.surface,
                            ),
                            _buildStatItem(
                              'TDEE',
                              '${user.tdee.toStringAsFixed(0)} kcal',
                              Icons.bolt,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                    ],

                    // Goal options
                    _buildGoalCard(
                      'lose',
                      'Giảm cân',
                      'Giảm mỡ, cải thiện vóc dáng',
                      Icons.trending_down,
                      AppColors.error,
                      user != null
                          ? '${(user.tdee - 500).toStringAsFixed(0)} kcal/ngày'
                          : null,
                    ),
                    const SizedBox(height: 12),
                    _buildGoalCard(
                      'maintain',
                      'Duy trì',
                      'Giữ cân nặng hiện tại',
                      Icons.remove,
                      AppColors.success,
                      user != null
                          ? '${user.tdee.toStringAsFixed(0)} kcal/ngày'
                          : null,
                    ),
                    const SizedBox(height: 12),
                    _buildGoalCard(
                      'gain',
                      'Tăng cơ',
                      'Tăng cơ, tăng cân lành mạnh',
                      Icons.trending_up,
                      AppColors.info,
                      user != null
                          ? '${(user.tdee + 300).toStringAsFixed(0)} kcal/ngày'
                          : null,
                    ),
                    const SizedBox(height: 24),

                    // Info box
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: AppColors.primary.withValues(alpha: 0.3),
                        ),
                      ),
                      child: const Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.info_outline,
                            color: AppColors.primary,
                            size: 20,
                          ),
                          SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              'Mục tiêu sẽ ảnh hưởng đến lượng calo khuyến nghị hàng ngày và các gợi ý dinh dưỡng, vận động.',
                              style: TextStyle(
                                fontSize: 14,
                                color: AppColors.textSecondary,
                                height: 1.4,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Save button
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: AppColors.surface,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.1),
                    blurRadius: 10,
                    offset: const Offset(0, -2),
                  ),
                ],
              ),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _isLoading ? null : _saveGoal,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor:
                                AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Text(
                          'Lưu thay đổi',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(String label, String value, IconData icon) {
    return Column(
      children: [
        Icon(icon, color: AppColors.primary, size: 20),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildGoalCard(
    String value,
    String title,
    String subtitle,
    IconData icon,
    Color color,
    String? calorieInfo,
  ) {
    final isSelected = _selectedGoal == value;

    return GestureDetector(
      onTap: () => setState(() => _selectedGoal = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: isSelected
              ? color.withValues(alpha: 0.1)
              : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? color : Colors.transparent,
            width: 2,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: isSelected
                    ? color.withValues(alpha: 0.2)
                    : AppColors.surface,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 28),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: isSelected ? color : AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontSize: 14,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  if (calorieInfo != null) ...[
                    const SizedBox(height: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        calorieInfo,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: color,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (isSelected)
              Icon(
                Icons.check_circle,
                color: color,
                size: 28,
              ),
          ],
        ),
      ),
    );
  }
}
