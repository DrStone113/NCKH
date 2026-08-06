import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../providers/chat_provider.dart';
import '../../../providers/ai_chat_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/animated_counter.dart';
import '../../../utils/responsive_utils.dart';
import 'health_stats_screen.dart';
import '../../nutrition/screens/nutrition_screen.dart';
import '../../exercise/screens/exercise_screen.dart';
import '../../chat/screens/chatbot_screen.dart';
import '../../auth/screens/auth_screen.dart';
import '../../settings/screens/goal_settings_screen.dart';
import '../../settings/screens/account_settings_screen.dart';
import '../../../widgets/bento_card.dart';

import '../../../providers/proactive_provider.dart';
import '../../../widgets/proactive_checkin_card.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;

  late final List<Widget> _screens = [
    _DashboardTab(onOpenChat: () => _openChatModal(context)),
    const NutritionScreen(),
    const ExerciseScreen(),
    const AccountSettingsScreen(),
  ];

  void _onTabChanged(int index) {
    setState(() => _currentIndex = index);
  }

  void _openChatModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.88,
        minChildSize: 0.5,
        maxChildSize: 0.96,
        builder: (context, scrollController) => ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          child: Container(
            color: AppColors.background,
            child: Column(
              children: [
                // Top Drag Handle
                Container(
                  margin: const EdgeInsets.symmetric(vertical: 10),
                  width: 40,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.grey[400],
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                const Expanded(child: ChatbotScreen()),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final userId =
          Provider.of<UserProvider>(context, listen: false).currentUser?.id;
      if (userId != null) {
        Provider.of<NutritionProvider>(context, listen: false)
            .loadTodayMeals(userId);
        Provider.of<ExerciseProvider>(context, listen: false)
            .loadTodayExercises(userId);
        Provider.of<HealthProvider>(context, listen: false)
            .loadTodayWaterIntake(userId);
        Provider.of<NutritionProvider>(context, listen: false).loadSavedMeals();
        Provider.of<ProactiveProvider>(context, listen: false).loadActiveCheckin(userId);
      }
      // Initialize ChatProvider
      Provider.of<ChatProvider>(context, listen: false).initialize();

      // Bind AI Chat screen navigation handler
      final aiChat = Provider.of<AIChatProvider>(context, listen: false);
      aiChat.onNavigateToScreen = (screen) {
        int targetIndex = 0;
        switch (screen.toLowerCase()) {
          case 'nutrition':
          case 'diet':
          case 'meal':
            targetIndex = 1;
            break;
          case 'workout':
          case 'exercise':
          case 'fitness':
            targetIndex = 2;
            break;
          case 'settings':
          case 'account':
          case 'profile':
            targetIndex = 3;
            break;
          case 'chat':
          case 'consult':
          case 'chatbot':
            _openChatModal(context);
            return;
          case 'dashboard':
          case 'home':
          default:
            targetIndex = 0;
            break;
        }
        if (mounted) {
          setState(() => _currentIndex = targetIndex);
        }
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      // ===== CENTER RAISED CHATBOT BUBBLE =====
      floatingActionButton: GestureDetector(
        onTap: () => _openChatModal(context),
        child: Container(
          width: 62,
          height: 62,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const LinearGradient(
              colors: [Color(0xFFFF8C00), Color(0xFFFF5500)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFFF6F00).withValues(alpha: 0.5),
                blurRadius: 16,
                spreadRadius: 3,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: const Stack(
            alignment: Alignment.center,
            children: [
              Icon(
                Icons.smart_toy,
                color: Colors.white,
                size: 32,
              ),
              Positioned(
                right: 4,
                top: 4,
                child: CircleAvatar(
                  radius: 5,
                  backgroundColor: Color(0xFF00C853),
                ),
              ),
            ],
          ),
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,

      // ===== CURVED NOTCHED BOTTOM BAR =====
      bottomNavigationBar: BottomAppBar(
        padding: EdgeInsets.zero,
        shape: const CircularNotchedRectangle(),
        notchMargin: 8.0,
        clipBehavior: Clip.antiAlias,
        color: AppColors.surface,
        elevation: 12,
        child: SizedBox(
          height: 64,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              // Tab 0: Tổng quan
              _buildNavItem(
                index: 0,
                activeIcon: Icons.dashboard,
                inactiveIcon: Icons.dashboard_outlined,
                label: 'Tổng quan',
              ),
              // Tab 1: Dinh dưỡng
              _buildNavItem(
                index: 1,
                activeIcon: Icons.restaurant,
                inactiveIcon: Icons.restaurant_outlined,
                label: 'Dinh dưỡng',
              ),
              // Center Notch Gap
              const SizedBox(width: 48),
              // Tab 2: Vận động
              _buildNavItem(
                index: 2,
                activeIcon: Icons.fitness_center,
                inactiveIcon: Icons.fitness_center_outlined,
                label: 'Vận động',
              ),
              // Tab 3: Cài đặt
              _buildNavItem(
                index: 3,
                activeIcon: Icons.person,
                inactiveIcon: Icons.person_outlined,
                label: 'Cài đặt',
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem({
    required int index,
    required IconData activeIcon,
    required IconData inactiveIcon,
    required String label,
  }) {
    final bool isSelected = _currentIndex == index;
    return InkWell(
      onTap: () => _onTabChanged(index),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              isSelected ? activeIcon : inactiveIcon,
              color: isSelected ? AppColors.primary : AppColors.textSecondary,
              size: 24,
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                color: isSelected ? AppColors.primary : AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ===== DASHBOARD TAB =====
class _DashboardTab extends StatelessWidget {
  final VoidCallback? onOpenChat;
  const _DashboardTab({this.onOpenChat});

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<UserProvider>(context).currentUser;
    final nutritionProvider = Provider.of<NutritionProvider>(context);
    final exerciseProvider = Provider.of<ExerciseProvider>(context);

    if (user == null) return const Center(child: CircularProgressIndicator());

    final isTabletOrLarger = !ResponsiveUtils.isMobile(context);
    final padding = ResponsiveUtils.getScreenPadding(context);

    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.all(padding),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1400),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                AnimatedCard(
                  delay: 0,
                  child: _buildHeader(context, user),
                ),
                const SizedBox(height: 16),

                // Proactive Check-in Card (Giao tiếp chủ động)
                ProactiveCheckinCard(onOpenChat: onOpenChat),
                const SizedBox(height: 16),

                // BMI Card
                AnimatedCard(
                  delay: 100,
                  child: _buildBmiCard(context, user),
                ),

                const SizedBox(height: 16),

                // Stats Grid - Responsive
                isTabletOrLarger
                    ? _buildTabletStatsGrid(
                        context, nutritionProvider, exerciseProvider, user)
                    : _buildMobileStatsGrid(
                        context, nutritionProvider, exerciseProvider, user),

                const SizedBox(height: 24),

                // Quick Actions
                AnimatedCard(
                  delay: 400,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Truy cập nhanh',
                        style: TextStyle(
                            fontSize: ResponsiveUtils.getTitleSize(context),
                            fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 12),
                      _buildQuickActions(context),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // Health Tips
                AnimatedCard(
                  delay: 500,
                  child: _buildHealthTip(context, user),
                ),
                const SizedBox(height: 120),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMobileStatsGrid(
      BuildContext context,
      NutritionProvider nutritionProvider,
      ExerciseProvider exerciseProvider,
      dynamic user) {
    return Column(
      children: [
        // Calorie & Exercise Row
        Row(
          children: [
            Expanded(
              child: AnimatedCard(
                delay: 200,
                child: _buildCalorieCard(context, nutritionProvider, user),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: AnimatedCard(
                delay: 250,
                child: _buildExerciseCard(context, exerciseProvider),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // TDEE & Water Row
        Row(
          children: [
            Expanded(
              child: AnimatedCard(
                delay: 300,
                child: _buildTdeeCard(context, user),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: AnimatedCard(
                delay: 350,
                child: _buildWaterCard(context, user),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildTabletStatsGrid(
      BuildContext context,
      NutritionProvider nutritionProvider,
      ExerciseProvider exerciseProvider,
      dynamic user) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: AnimatedCard(
            delay: 200,
            child: _buildCalorieCard(context, nutritionProvider, user),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: AnimatedCard(
            delay: 250,
            child: _buildExerciseCard(context, exerciseProvider),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: AnimatedCard(
            delay: 300,
            child: _buildTdeeCard(context, user),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: AnimatedCard(
            delay: 350,
            child: _buildWaterCard(context, user),
          ),
        ),
      ],
    );
  }

  Widget _buildHeader(BuildContext context, dynamic user) {
    final hour = DateTime.now().hour;
    String greeting;
    IconData greetIcon;
    if (hour < 12) {
      greeting = 'Chào buổi sáng';
      greetIcon = Icons.wb_sunny;
    } else if (hour < 18) {
      greeting = 'Chào buổi chiều';
      greetIcon = Icons.cloud;
    } else {
      greeting = 'Chào buổi tối';
      greetIcon = Icons.nights_stay;
    }

    final headingSize = ResponsiveUtils.getHeadingSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(greetIcon,
                      color: AppColors.primary, size: iconSize * 0.8),
                  const SizedBox(width: 8),
                  Text(
                    greeting,
                    style: TextStyle(
                        fontSize: bodySize, color: AppColors.textSecondary),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                user.name,
                style: TextStyle(
                    fontSize: headingSize, fontWeight: FontWeight.bold),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
        Row(
          children: [
            GestureDetector(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const HealthStatsScreen()),
              ),
              child: Container(
                padding: EdgeInsets.all(
                    ResponsiveUtils.getCardPadding(context) * 0.5),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(Icons.bar_chart,
                    color: AppColors.primary, size: iconSize),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () => _showLogoutDialog(context),
              child: Container(
                padding: EdgeInsets.all(
                    ResponsiveUtils.getCardPadding(context) * 0.5),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(Icons.logout,
                    color: AppColors.textSecondary, size: iconSize),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildBmiCard(BuildContext context, dynamic user) {
    final bmiValue = user.bmi;
    final bmiPercent = ((bmiValue - 10) / 35).clamp(0.0, 1.0);
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);

    Color bmiColor;
    if (bmiValue < 16) {
      bmiColor = const Color(0xFFE53935);
    } else if (bmiValue < 17) {
      bmiColor = const Color(0xFFFF5722);
    } else if (bmiValue < 18.5) {
      bmiColor = AppColors.info;
    } else if (bmiValue < 25) {
      bmiColor = AppColors.success;
    } else if (bmiValue < 30) {
      bmiColor = AppColors.warning;
    } else if (bmiValue < 35) {
      bmiColor = const Color(0xFFFF9800);
    } else if (bmiValue < 40) {
      bmiColor = AppColors.error;
    } else {
      bmiColor = const Color(0xFF9C27B0);
    }

    return BentoCard(
      padding: EdgeInsets.all(cardPadding),
      gradient: AppColors.cardGradient,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Chỉ số BMI',
                style: TextStyle(
                    fontSize: bodySize, color: AppColors.textSecondary),
              ),
              Container(
                padding: EdgeInsets.symmetric(
                    horizontal: cardPadding * 0.5,
                    vertical: cardPadding * 0.25),
                decoration: BoxDecoration(
                  color: bmiColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  user.bmiCategory,
                  style: TextStyle(
                      fontSize: smallSize,
                      fontWeight: FontWeight.w600,
                      color: bmiColor),
                ),
              ),
            ],
          ),
          SizedBox(height: cardPadding * 0.5),
          Row(
            children: [
              AnimatedCounter(
                value: bmiValue,
                decimals: 1,
                style: TextStyle(
                  fontSize: titleSize * 1.5,
                  fontWeight: FontWeight.bold,
                  color: bmiColor,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'kg/m²',
                style: TextStyle(
                    fontSize: bodySize, color: AppColors.textSecondary),
              ),
            ],
          ),
          SizedBox(height: cardPadding * 0.5),
          AnimatedProgressBar(
            value: bmiPercent,
            height: 8,
            gradient: const LinearGradient(
              colors: [
                Color(0xFF2196F3),
                Color(0xFF4CAF50),
                Color(0xFFFF9800),
                Color(0xFFE53935),
              ],
            ),
            borderRadius: BorderRadius.circular(6),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('${user.height.toStringAsFixed(0)} cm',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
              Text('${user.weight.toStringAsFixed(1)} kg',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCalorieCard(
      BuildContext context, NutritionProvider nutritionProvider, dynamic user) {
    final target = user.recommendedCalories;
    final consumed = nutritionProvider.totalCalories;
    final progress = target > 0 ? (consumed / target).clamp(0.0, 1.5) : 0.0;
    final bodySize = ResponsiveUtils.getBodySize(context);
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return BentoCard(
      padding: EdgeInsets.all(cardPadding),
      child: Column(
        children: [
          Row(
            children: [
              Icon(Icons.local_fire_department,
                  color: AppColors.calories, size: iconSize * 0.75),
              const SizedBox(width: 6),
              Text('Calo',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
            ],
          ),
          SizedBox(height: cardPadding * 0.6),
          AnimatedCircularProgress(
            value: progress.clamp(0.0, 1.0),
            size: ResponsiveUtils.responsive(context,
                mobile: 80.0, tablet: 100.0, desktop: 120.0),
            strokeWidth: ResponsiveUtils.responsive(context,
                mobile: 6.0, tablet: 8.0, desktop: 10.0),
            color: consumed > target ? AppColors.error : AppColors.calories,
            backgroundColor: AppColors.surfaceLight,
            child: AnimatedCounter(
              value: consumed,
              decimals: 0,
              style: TextStyle(fontSize: bodySize, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '/ ${target.toStringAsFixed(0)} kcal',
            style:
                TextStyle(fontSize: smallSize, color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildExerciseCard(
      BuildContext context, ExerciseProvider exerciseProvider) {
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return BentoCard(
      padding: EdgeInsets.all(cardPadding),
      child: Column(
        children: [
          Row(
            children: [
              Icon(Icons.fitness_center,
                  color: AppColors.success, size: iconSize * 0.75),
              const SizedBox(width: 6),
              Text('Vận động',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
            ],
          ),
          SizedBox(height: cardPadding * 0.6),
          AnimatedCounter(
            value: exerciseProvider.totalDuration.toDouble(),
            decimals: 0,
            style: TextStyle(
                fontSize: titleSize * 1.4,
                fontWeight: FontWeight.bold,
                color: AppColors.success),
          ),
          Text('phút',
              style: TextStyle(
                  fontSize: smallSize, color: AppColors.textSecondary)),
          const SizedBox(height: 8),
          Container(
            padding: EdgeInsets.symmetric(
                horizontal: cardPadding * 0.5, vertical: cardPadding * 0.25),
            decoration: BoxDecoration(
              color: AppColors.calories.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('🔥 ', style: TextStyle(fontSize: smallSize)),
                AnimatedCounter(
                  value: exerciseProvider.totalCaloriesBurned,
                  decimals: 0,
                  suffix: ' kcal',
                  style:
                      TextStyle(fontSize: smallSize, color: AppColors.calories),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTdeeCard(BuildContext context, dynamic user) {
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return BentoCard(
      padding: EdgeInsets.all(cardPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.bolt, color: AppColors.accent, size: iconSize * 0.75),
              const SizedBox(width: 6),
              Text('TDEE',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
            ],
          ),
          const SizedBox(height: 8),
          AnimatedCounter(
            value: user.tdee,
            decimals: 0,
            style: TextStyle(fontSize: titleSize, fontWeight: FontWeight.bold),
          ),
          Text('kcal/ngày',
              style: TextStyle(
                  fontSize: smallSize, color: AppColors.textSecondary)),
          const SizedBox(height: 4),
          Text(
            user.healthGoalText,
            style: TextStyle(fontSize: smallSize, color: AppColors.primary),
          ),
        ],
      ),
    );
  }

  Widget _buildWaterCard(BuildContext context, dynamic user) {
    final waterProvider = Provider.of<HealthProvider>(context);
    final waterGoal = user.dailyWaterGoal;
    final current = waterProvider.todayWaterIntake;
    final glassesTarget = (waterGoal * 1000 / 250).round();
    final glassesDone = (current / 250).round();

    final isOverLimit = current > 5000;
    final isNearLimit = current > 4000 && current <= 5000;

    final smallSize = ResponsiveUtils.getSmallSize(context);
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return BentoCard(
      onTap: () => _addWater(context, user),
      padding: EdgeInsets.all(cardPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.water_drop,
                  color: isOverLimit
                      ? AppColors.error
                      : (isNearLimit ? AppColors.warning : AppColors.info),
                  size: iconSize * 0.75),
              const SizedBox(width: 6),
              Text('Nước uống',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
              if (isOverLimit || isNearLimit) ...[
                const Spacer(),
                Icon(
                  Icons.warning_amber,
                  color: isOverLimit ? AppColors.error : AppColors.warning,
                  size: iconSize * 0.67,
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${(current / 1000).toStringAsFixed(1)}L',
            style: TextStyle(
                fontSize: titleSize,
                fontWeight: FontWeight.bold,
                color: isOverLimit
                    ? AppColors.error
                    : (isNearLimit ? AppColors.warning : AppColors.info)),
          ),
          Text('/ ${waterGoal.toStringAsFixed(1)}L',
              style: TextStyle(
                  fontSize: smallSize, color: AppColors.textSecondary)),
          const SizedBox(height: 4),
          Text(
            '$glassesDone / $glassesTarget ly',
            style: TextStyle(
                fontSize: smallSize, color: AppColors.info.withValues(alpha: 0.7)),
          ),
          if (isOverLimit)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '⚠️ Quá nhiều!',
                style: TextStyle(
                    fontSize: smallSize * 0.83,
                    color: AppColors.error,
                    fontWeight: FontWeight.w600),
              ),
            )
          else if (isNearLimit)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '⚠️ Gần giới hạn',
                style: TextStyle(
                    fontSize: smallSize * 0.83,
                    color: AppColors.warning,
                    fontWeight: FontWeight.w600),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    final actions = [
      {
        'icon': Icons.restaurant,
        'label': 'Thêm bữa ăn',
        'color': AppColors.calories,
        'tab': 1
      },
      {
        'icon': Icons.fitness_center,
        'label': 'Ghi tập luyện',
        'color': AppColors.success,
        'tab': 2
      },
      {
        'icon': Icons.chat_bubble,
        'label': 'Hỏi chatbot',
        'color': AppColors.accent,
        'tab': 3
      },
      {
        'icon': Icons.flag,
        'label': 'Thay đổi mục tiêu',
        'color': AppColors.primary,
        'tab': -2
      },
    ];

    final smallSize = ResponsiveUtils.getSmallSize(context);
    final iconSize = ResponsiveUtils.getIconSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: actions.map((action) {
        return Flexible(
          child: GestureDetector(
            onTap: () {
              if (action['tab'] == -1) {
                Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const HealthStatsScreen()));
              } else if (action['tab'] == -2) {
                Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const GoalSettingsScreen()));
              } else {
                final homeState =
                    context.findAncestorStateOfType<_HomeScreenState>();
                homeState?._onTabChanged(action['tab'] as int);
              }
            },
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: cardPadding * 0.25),
              child: Column(
                children: [
                  Container(
                    width: iconSize * 2,
                    height: iconSize * 2,
                    decoration: BoxDecoration(
                      color: (action['color'] as Color).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Icon(action['icon'] as IconData,
                        color: action['color'] as Color, size: iconSize),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    action['label'] as String,
                    style: TextStyle(
                        fontSize: smallSize, color: AppColors.textSecondary),
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildHealthTip(BuildContext context, dynamic user) {
    final tips = [
      '💡 Uống 1 ly nước trước bữa ăn giúp giảm cảm giác đói.',
      '🥗 Ăn nhiều rau xanh giúp bổ sung chất xơ và vitamin.',
      '🏃 30 phút vận động mỗi ngày giúp cải thiện sức khỏe tim mạch.',
      '😴 Ngủ đủ 7-8 giờ để cơ thể hồi phục tốt nhất.',
      '🍊 Vitamin C giúp tăng cường hệ miễn dịch.',
      '🧘 Thực hành hít thở sâu giúp giảm stress hiệu quả.',
    ];

    final tipIndex = DateTime.now().day % tips.length;
    final bodySize = ResponsiveUtils.getBodySize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);

    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(cardPadding),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            AppColors.primary.withValues(alpha: 0.15),
            AppColors.accent.withValues(alpha: 0.1)
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '💡',
            style: TextStyle(fontSize: bodySize * 1.2),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Mẹo sức khỏe hôm nay',
                  style: TextStyle(
                      fontSize: bodySize,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary),
                ),
                const SizedBox(height: 4),
                Text(
                  tips[tipIndex].replaceFirst(RegExp(r'^[^\s]+\s'), ''),
                  style: TextStyle(
                      fontSize: bodySize,
                      color: AppColors.textPrimary,
                      height: 1.4),
                  softWrap: true,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _addWater(BuildContext context, dynamic user) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Thêm nước uống',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [150, 250, 350, 500].map((ml) {
                return Flexible(
                  child: GestureDetector(
                    onTap: () async {
                      final warning = await Provider.of<HealthProvider>(context,
                              listen: false)
                          .addWater(user.id, ml.toDouble());

                      if (context.mounted) {
                        Navigator.pop(context);

                        // Hiển thị cảnh báo nếu có
                        if (warning != null) {
                          showDialog(
                            context: context,
                            builder: (context) => AlertDialog(
                              backgroundColor: AppColors.surface,
                              title: const Row(
                                children: [
                                  Icon(Icons.warning_amber,
                                      color: AppColors.warning, size: 28),
                                  SizedBox(width: 10),
                                  Text('Cảnh báo sức khỏe'),
                                ],
                              ),
                              content: Text(warning),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(context),
                                  child: const Text('Đã hiểu'),
                                ),
                              ],
                            ),
                          );
                        }
                      }
                    },
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 12),
                      decoration: BoxDecoration(
                        color: AppColors.info.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                        border:
                            Border.all(color: AppColors.info.withValues(alpha: 0.3)),
                      ),
                      child: Column(
                        children: [
                          const Icon(Icons.water_drop, color: AppColors.info),
                          const SizedBox(height: 4),
                          Text('${ml}ml',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  void _showLogoutDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Đăng xuất'),
        content: const Text('Bạn có chắc muốn đăng xuất?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () async {
              await Provider.of<UserProvider>(context, listen: false).signOut();
              if (context.mounted) {
                Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const AuthScreen()),
                  (route) => false,
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('Đăng xuất'),
          ),
        ],
      ),
    );
  }
}
