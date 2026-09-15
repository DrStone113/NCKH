import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/user_provider.dart';
import '../../../providers/nutrition_provider.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/health_provider.dart';
import '../../../providers/chat_provider.dart';
import '../../../providers/ai_chat_provider.dart';
import '../../../providers/plan_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/animated_card.dart';
import '../../../widgets/animated_counter.dart';
import '../../../utils/responsive_utils.dart';
import 'health_stats_screen.dart';
import '../../nutrition/screens/nutrition_screen.dart';
import '../../exercise/screens/exercise_screen.dart';
import '../../chat/screens/chatbot_screen.dart';
import '../../plans/screens/plan_list_screen.dart';
import '../../plans/widgets/plan_library_navigation_action.dart';
import '../../plans/widgets/planned_day_plan_section.dart';
import '../../plans/plan_snapshot.dart';
import '../../auth/screens/auth_wrapper.dart';
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
  static const String _planV2E2EConfigurationMarker = String.fromEnvironment(
    'PLAN_V2_E2E_CONFIGURATION_MARKER',
  );
  static const String _expectedPlanV2E2EConfigurationMarker =
      'PLAN_V2_E2E_CONFIGURED_V1';

  int _currentIndex = 0;

  late final List<Widget> _screens = [
    _DashboardTab(
      onOpenChat: () => _openChatModal(context),
      onOpenPlans: () => _openPlanLibrary(context),
    ),
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

  void _openPlanLibrary(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => PlanListScreen(
          onOpenChat: () {
            Navigator.of(context).pop();
            _openChatModal(context);
          },
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final user =
          Provider.of<UserProvider>(context, listen: false).currentUser;
      final userId = user?.id;
      if (userId != null && user != null) {
        final nutrition =
            Provider.of<NutritionProvider>(context, listen: false);
        final exercise = Provider.of<ExerciseProvider>(context, listen: false);
        await Future.wait([
          nutrition.loadTodayMeals(userId),
          exercise.loadTodayExercises(userId),
        ]);
        if (!mounted) return;
        Provider.of<PlanProvider>(context, listen: false)
            .loadForUser(userId)
            .catchError((_) => const <PlanSnapshot>[]);
        if (!mounted) return;
        Provider.of<HealthProvider>(context, listen: false)
            .loadTodayWaterIntake(userId);
        nutrition.loadSavedMeals();
        Provider.of<ProactiveProvider>(context, listen: false)
            .loadActiveCheckin(
          userId,
          userContext: {
            'age': user.age,
            'gender': user.gender,
            'equation_sex': user.equationSex,
            'nutrition_safety_profile': user.nutritionSafetyProfile.toJson(),
            'height': user.height,
            'weight': user.weight,
            'activity_level': user.activityLevel,
            'health_goal': user.healthGoal,
            'today_calories_consumed': nutrition.consumedCalories,
            'today_meals_count': nutrition.completedMealsCount,
            'today_calories_burned': exercise.totalCaloriesBurned,
            'today_exercises_count': exercise.completedCount,
          },
        );
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
      body:
          _planV2E2EConfigurationMarker == _expectedPlanV2E2EConfigurationMarker
              ? Semantics(
                  container: true,
                  label: 'Plan V2 E2E configuration active',
                  child: IndexedStack(
                    index: _currentIndex,
                    children: _screens,
                  ),
                )
              : IndexedStack(
                  index: _currentIndex,
                  children: _screens,
                ),
      // ===== CENTER RAISED CHATBOT BUBBLE =====
      floatingActionButton: _AIAssistantFab(
        onTap: () => _openChatModal(context),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,

      // ===== CURVED NOTCHED BOTTOM BAR =====
      bottomNavigationBar: BottomAppBar(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        shape: const CircularNotchedRectangle(),
        notchMargin: 8.0,
        clipBehavior: Clip.antiAlias,
        color: AppColors.surface,
        elevation: 0,
        child: Container(
          decoration: BoxDecoration(
            border: Border(
              top: BorderSide(
                color: Colors.black.withValues(alpha: 0.04),
                width: 1,
              ),
            ),
          ),
          height: 64,
          child: Row(
            children: [
              // Tab 0: Tổng quan
              Expanded(
                child: _buildNavItem(
                  index: 0,
                  activeIcon: Icons.dashboard_rounded,
                  inactiveIcon: Icons.dashboard_outlined,
                  label: 'Tổng quan',
                ),
              ),
              // Tab 1: Dinh dưỡng
              Expanded(
                child: _buildNavItem(
                  index: 1,
                  activeIcon: Icons.restaurant_rounded,
                  inactiveIcon: Icons.restaurant_outlined,
                  label: 'Dinh dưỡng',
                ),
              ),
              // Vùng trống ở tâm dành cho nút chatbot.
              const SizedBox(width: 64),
              // Tab 2: Vận động
              Expanded(
                child: _buildNavItem(
                  index: 2,
                  activeIcon: Icons.fitness_center_rounded,
                  inactiveIcon: Icons.fitness_center_outlined,
                  label: 'Vận động',
                ),
              ),
              // Tab 3: Cài đặt
              Expanded(
                child: _buildNavItem(
                  index: 3,
                  activeIcon: Icons.person_rounded,
                  inactiveIcon: Icons.person_outlined,
                  label: 'Cài đặt',
                ),
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
    final navigationTarget = switch (index) {
      0 => 'overview',
      1 => 'nutrition',
      2 => 'activity',
      3 => 'settings',
      _ => 'unknown',
    };
    return Semantics(
      label: 'Main navigation $navigationTarget',
      button: true,
      onTap: () => _onTabChanged(index),
      excludeSemantics: true,
      child: InkWell(
        onTap: () => _onTabChanged(index),
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          decoration: BoxDecoration(
            color: isSelected
                ? AppColors.primary.withValues(alpha: 0.05)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AnimatedScale(
                scale: isSelected ? 1.08 : 1.0,
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeOutBack,
                child: Icon(
                  isSelected ? activeIcon : inactiveIcon,
                  color:
                      isSelected ? AppColors.primary : AppColors.textSecondary,
                  size: 22,
                ),
              ),
              const SizedBox(height: 3),
              SizedBox(
                width: double.infinity,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    label,
                    maxLines: 1,
                    softWrap: false,
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight:
                          isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: isSelected
                          ? AppColors.primary
                          : AppColors.textSecondary,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AIAssistantFab extends StatefulWidget {
  final VoidCallback onTap;
  const _AIAssistantFab({required this.onTap});

  @override
  State<_AIAssistantFab> createState() => _AIAssistantFabState();
}

class _AIAssistantFabState extends State<_AIAssistantFab>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _scaleAnimation = Tween<double>(begin: 1.0, end: 1.05).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, child) {
        return Transform.scale(
          scale: _scaleAnimation.value,
          child: Semantics(
            label: 'n3-open-chat',
            button: true,
            child: GestureDetector(
              onTap: widget.onTap,
              child: Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: const LinearGradient(
                    colors: [Color(0xFF1E293B), Color(0xFF0F172A)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF6366F1).withValues(
                        alpha: 0.35 + (_pulseAnimation.value * 0.25),
                      ),
                      blurRadius: 16 + (_pulseAnimation.value * 8),
                      spreadRadius: 1 + (_pulseAnimation.value * 2),
                      offset: const Offset(0, 4),
                    ),
                  ],
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.25),
                    width: 1.5,
                  ),
                ),
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    const Icon(
                      Icons.smart_toy_rounded,
                      color: Colors.white,
                      size: 28,
                    ),
                    Positioned(
                      right: 6,
                      top: 6,
                      child: Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: AppColors.accent,
                          border: Border.all(
                              color: AppColors.primaryDark, width: 1.5),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

// ===== DASHBOARD TAB =====
class _DashboardTab extends StatelessWidget {
  final VoidCallback? onOpenChat;
  final VoidCallback? onOpenPlans;

  const _DashboardTab({this.onOpenChat, this.onOpenPlans});

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

                PlannedDayPlanSection(
                  userId: user.id,
                  date: DateTime.now(),
                  domain: 'NUTRITION',
                  snapshots: context.watch<PlanProvider>().plans,
                  compact: true,
                ),

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
    final cardHeight = ResponsiveUtils.responsive(
      context,
      mobile: 180.0,
      tablet: 220.0,
      desktop: 250.0,
    );

    return Column(
      children: [
        // Calorie & Exercise Row
        Row(
          children: [
            Expanded(
              child: _buildStatCard(
                delay: 200,
                height: cardHeight,
                child: _buildCalorieCard(context, nutritionProvider, user),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildStatCard(
                delay: 250,
                height: cardHeight,
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
              child: _buildStatCard(
                delay: 300,
                height: cardHeight,
                child: _buildTdeeCard(context, user),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildStatCard(
                delay: 350,
                height: cardHeight,
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
    final cardHeight = ResponsiveUtils.responsive(
      context,
      mobile: 180.0,
      tablet: 220.0,
      desktop: 250.0,
    );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: _buildStatCard(
            delay: 200,
            height: cardHeight,
            child: _buildCalorieCard(context, nutritionProvider, user),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: _buildStatCard(
            delay: 250,
            height: cardHeight,
            child: _buildExerciseCard(context, exerciseProvider),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: _buildStatCard(
            delay: 300,
            height: cardHeight,
            child: _buildTdeeCard(context, user),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: _buildStatCard(
            delay: 350,
            height: cardHeight,
            child: _buildWaterCard(context, user),
          ),
        ),
      ],
    );
  }

  Widget _buildStatCard({
    required int delay,
    required double height,
    required Widget child,
  }) {
    return SizedBox(
      height: height,
      child: AnimatedCard(delay: delay, child: child),
    );
  }

  Widget _buildHeader(BuildContext context, dynamic user) {
    final now = DateTime.now();
    final hour = now.hour;
    String greeting;
    IconData greetIcon;
    Color greetColor;
    if (hour >= 5 && hour < 11) {
      greeting = 'Chào buổi sáng';
      greetIcon = Icons.wb_sunny_rounded;
      greetColor = const Color(0xFFF59E0B);
    } else if (hour >= 11 && hour < 14) {
      greeting = 'Chào buổi trưa';
      greetIcon = Icons.wb_sunny_outlined;
      greetColor = const Color(0xFFF59E0B);
    } else if (hour >= 14 && hour < 18) {
      greeting = 'Chào buổi chiều';
      greetIcon = Icons.cloud_outlined;
      greetColor = const Color(0xFF0284C7);
    } else {
      greeting = 'Chào buổi tối';
      greetIcon = Icons.nightlight_round;
      greetColor = const Color(0xFF8B5CF6);
    }

    final headingSize = ResponsiveUtils.getHeadingSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    const weekdays = ['Th 2', 'Th 3', 'Th 4', 'Th 5', 'Th 6', 'Th 7', 'CN'];
    final weekdayLabel = weekdays[(now.weekday - 1) % 7];
    final dateBadge = '$weekdayLabel, ${now.day}/${now.month}';

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(greetIcon, color: greetColor, size: 16),
                  const SizedBox(width: 6),
                  Text(
                    greeting,
                    style: TextStyle(
                      fontSize: bodySize * 0.95,
                      fontWeight: FontWeight.w500,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(AppRadius.pill),
                      border: Border.all(
                        color: Colors.black.withValues(alpha: 0.04),
                        width: 1,
                      ),
                    ),
                    child: Text(
                      dateBadge,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                user.name,
                style: TextStyle(
                  fontSize: headingSize,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.5,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            InteractiveCard(
              padding: EdgeInsets.all(
                  ResponsiveUtils.getCardPadding(context) * 0.45),
              borderRadius: BorderRadius.circular(AppRadius.md),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const HealthStatsScreen()),
              ),
              child: Icon(
                Icons.bar_chart_rounded,
                color: AppColors.primary,
                size: iconSize * 0.9,
              ),
            ),
            const SizedBox(width: 8),
            InteractiveCard(
              padding: EdgeInsets.all(
                  ResponsiveUtils.getCardPadding(context) * 0.45),
              borderRadius: BorderRadius.circular(AppRadius.md),
              onTap: () => _showLogoutDialog(context),
              child: Icon(
                Icons.logout_rounded,
                color: AppColors.textSecondary,
                size: iconSize * 0.9,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildBmiCard(BuildContext context, dynamic user) {
    final bmiValue = user.bmi;
    final bmiDisplayValue = user.displayBmi;
    final bmiPercent = ((bmiValue - 10) / 35).clamp(0.0, 1.0);
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);

    final bmiColor = _bmiColorForCode(user.bmiCategoryCode);

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
                value: bmiDisplayValue,
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

  Color _bmiColorForCode(String? code) => switch (code) {
        'UNDERWEIGHT' => AppColors.info,
        'NORMAL' => AppColors.success,
        'OVERWEIGHT' => AppColors.warning,
        'OBESITY_I' => const Color(0xFFFF9800),
        'OBESITY_II' => AppColors.error,
        _ => AppColors.textSecondary,
      };

  Widget _buildCalorieCard(
      BuildContext context, NutritionProvider nutritionProvider, dynamic user) {
    final target = user.recommendedCalories;
    final consumed = nutritionProvider.consumedCalories;
    final progress = target != null && target > 0
        ? (consumed / target).clamp(0.0, 1.5)
        : 0.0;
    final bodySize = ResponsiveUtils.getBodySize(context);
    final smallSize = ResponsiveUtils.getSmallSize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return BentoCard(
      padding: EdgeInsets.all(cardPadding),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
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
            color: target != null && consumed > target
                ? AppColors.error
                : AppColors.calories,
            backgroundColor: AppColors.surfaceLight,
            child: AnimatedCounter(
              value: consumed,
              decimals: 0,
              style: TextStyle(fontSize: bodySize, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            target == null
                ? 'Chưa có mục tiêu thông thường'
                : '/ ${user.displayRecommendedCalories.toStringAsFixed(0)} kcal',
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
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
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
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.bolt, color: AppColors.accent, size: iconSize * 0.75),
              const SizedBox(width: 6),
              Text('TDEE ước tính',
                  style: TextStyle(
                      fontSize: smallSize, color: AppColors.textSecondary)),
            ],
          ),
          const SizedBox(height: 8),
          if (user.displayTdee == null)
            Text('Cần xác nhận',
                style:
                    TextStyle(fontSize: smallSize, fontWeight: FontWeight.bold))
          else
            AnimatedCounter(
              value: user.displayTdee!,
              decimals: 0,
              style:
                  TextStyle(fontSize: titleSize, fontWeight: FontWeight.bold),
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
    final glassesTarget =
        waterGoal == null ? null : (waterGoal * 1000 / 250).round();
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
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
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
                const SizedBox(width: 6),
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
          Text(
              waterGoal == null
                  ? 'Mục tiêu dịch không khả dụng'
                  : '/ ${user.displayDailyWaterGoal.toStringAsFixed(1)}L',
              style: TextStyle(
                  fontSize: smallSize, color: AppColors.textSecondary)),
          const SizedBox(height: 4),
          Text(
            glassesTarget == null
                ? '$glassesDone ly'
                : '$glassesDone / $glassesTarget ly',
            style: TextStyle(
                fontSize: smallSize,
                color: AppColors.info.withValues(alpha: 0.7)),
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
        'icon': Icons.restaurant_rounded,
        'label': 'Thêm bữa ăn',
        'color': AppColors.calories,
        'tab': 1
      },
      {
        'icon': Icons.fitness_center_rounded,
        'label': 'Ghi tập luyện',
        'color': AppColors.success,
        'tab': 2
      },
      {
        'icon': Icons.smart_toy_rounded,
        'label': 'Hỏi Trợ lý AI',
        'color': const Color(0xFF6366F1),
        'tab': -3
      },
      {
        'icon': Icons.event_note_rounded,
        'label': 'Kế hoạch',
        'color': AppColors.info,
        'tab': -4
      },
      {
        'icon': Icons.flag_rounded,
        'label': 'Mục tiêu',
        'color': const Color(0xFFF59E0B),
        'tab': -2
      },
    ];

    final smallSize = ResponsiveUtils.getSmallSize(context);
    final iconSize = ResponsiveUtils.getIconSize(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: actions.map((action) {
        final color = action['color'] as Color;
        void actionTap() {
          if (action['tab'] == -3) {
            onOpenChat?.call();
          } else if (action['tab'] == -4) {
            onOpenPlans?.call();
          } else if (action['tab'] == -1) {
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const HealthStatsScreen()));
          } else if (action['tab'] == -2) {
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const GoalSettingsScreen()));
          } else {
            final homeState =
                context.findAncestorStateOfType<_HomeScreenState>();
            homeState?._onTabChanged(action['tab'] as int);
          }
        }

        final actionCard = InteractiveCard(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
          borderRadius: BorderRadius.circular(AppRadius.lg),
          onTap: actionTap,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: iconSize * 1.8,
                height: iconSize * 1.8,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: Icon(
                  action['icon'] as IconData,
                  color: color,
                  size: iconSize * 0.9,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                action['label'] as String,
                style: TextStyle(
                  fontSize: smallSize * 0.95,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        );
        return Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 3),
            child: action['tab'] == -4
                ? PlanLibraryNavigationAction(
                    onActivate: actionTap,
                    child: actionCard,
                  )
                : actionCard,
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
                        border: Border.all(
                            color: AppColors.info.withValues(alpha: 0.3)),
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
                  MaterialPageRoute(builder: (_) => const AuthWrapper()),
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
