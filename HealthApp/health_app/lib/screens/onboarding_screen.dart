import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/user_provider.dart';
import '../models/user_model.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_card.dart';
import 'home_screen.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  // Form data
  String _name = '';
  int _age = 25;
  String _gender = 'male';
  double _height = 170;
  double _weight = 65;
  String _activityLevel = 'moderate';
  String _healthGoal = 'maintain';

  @override
  void initState() {
    super.initState();
    // Khởi tạo giá trị từ user hiện tại nếu có
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final user = userProvider.currentUser;
    if (user != null) {
      _name = user.name;
      if (user.age > 0) _age = user.age;
      _gender = user.gender;
      if (user.height > 0) _height = user.height;
      if (user.weight > 0) _weight = user.weight;
      _activityLevel = user.activityLevel;
      _healthGoal = user.healthGoal;
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _nextPage() {
    if (_currentPage < 5) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    } else {
      _completeOnboarding();
    }
  }

  void _previousPage() {
    if (_currentPage > 0) {
      _pageController.previousPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    }
  }

  Future<void> _completeOnboarding() async {
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final currentUser = userProvider.currentUser;
    
    if (currentUser != null) {
      // Create updated user model with new information
      final updatedUser = UserModel(
        id: currentUser.id,
        email: currentUser.email,
        name: _name.isEmpty ? currentUser.name : _name,
        age: _age,
        gender: _gender,
        height: _height,
        weight: _weight,
        targetWeight: _weight, // Đặt target weight = weight hiện tại
        activityLevel: _activityLevel,
        healthGoal: _healthGoal,
        createdAt: currentUser.createdAt,
      );

      await userProvider.updateProfile(updatedUser);

      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Progress indicator
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: List.generate(6, (index) {
                  return Expanded(
                    child: Container(
                      height: 4,
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      decoration: BoxDecoration(
                        color: index <= _currentPage 
                            ? AppColors.primary 
                            : AppColors.surfaceLight,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  );
                }),
              ),
            ),

            // Pages
            Expanded(
              child: PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                onPageChanged: (index) {
                  setState(() => _currentPage = index);
                },
                children: [
                  _buildWelcomePage(),
                  _buildNamePage(),
                  _buildAgeGenderPage(),
                  _buildHeightWeightPage(),
                  _buildActivityLevelPage(),
                  _buildHealthGoalPage(),
                ],
              ),
            ),

            // Navigation buttons
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  if (_currentPage > 0)
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _previousPage,
                        style: OutlinedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          side: BorderSide(color: AppColors.primary),
                        ),
                        child: const Text('Quay lại'),
                      ),
                    ),
                  if (_currentPage > 0) const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: ElevatedButton(
                      onPressed: _nextPage,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: Text(_currentPage == 5 ? 'Hoàn thành' : 'Tiếp tục'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWelcomePage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              gradient: AppColors.primaryGradient,
              borderRadius: BorderRadius.circular(30),
              boxShadow: [
                BoxShadow(
                  color: AppColors.primary.withOpacity(0.3),
                  blurRadius: 20,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: const Icon(Icons.favorite, color: Colors.white, size: 60),
          ),
          const SizedBox(height: 32),
          const Text(
            'Chào mừng đến với\nHealth App',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.bold,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Hãy cho chúng tôi biết thêm về bạn\nđể cá nhân hóa trải nghiệm',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 16,
              color: AppColors.textSecondary,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 48),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.1),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                _buildFeatureItem(Icons.restaurant, 'Theo dõi dinh dưỡng'),
                const SizedBox(height: 12),
                _buildFeatureItem(Icons.fitness_center, 'Ghi nhận vận động'),
                const SizedBox(height: 12),
                _buildFeatureItem(Icons.chat_bubble, 'Tư vấn sức khỏe AI'),
              ],
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildFeatureItem(IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, color: AppColors.primary, size: 24),
        const SizedBox(width: 12),
        Text(
          text,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  Widget _buildNamePage() {
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    if (_name.isEmpty && user != null) {
      _name = user.name;
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 80),
          const Text(
            '👋',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'Bạn tên là gì?',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 48),
          TextField(
            controller: TextEditingController(text: _name),
            onChanged: (value) => _name = value,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            decoration: InputDecoration(
              hintText: 'Nhập tên của bạn',
              filled: true,
              fillColor: AppColors.surfaceLight,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(vertical: 20, horizontal: 24),
            ),
          ),
          const SizedBox(height: 80),
        ],
      ),
    );
  }

  Widget _buildAgeGenderPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          const Text(
            '🎂',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'Tuổi và giới tính',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 48),
          
          // Age slider
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                Text(
                  '$_age tuổi',
                  style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: AppColors.primary),
                ),
                const SizedBox(height: 16),
                Slider(
                  value: _age.toDouble(),
                  min: 10,
                  max: 100,
                  divisions: 90,
                  onChanged: (value) {
                    setState(() => _age = value.toInt());
                  },
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('10', style: TextStyle(color: AppColors.textSecondary)),
                    Text('100', style: TextStyle(color: AppColors.textSecondary)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          
          // Gender selection
          Row(
            children: [
              Expanded(
                child: _buildGenderCard('male', 'Nam', Icons.male),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _buildGenderCard('female', 'Nữ', Icons.female),
              ),
            ],
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildGenderCard(String value, String label, IconData icon) {
    final isSelected = _gender == value;
    return GestureDetector(
      onTap: () => setState(() => _gender = value),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 24),
        decoration: BoxDecoration(
          gradient: isSelected ? AppColors.primaryGradient : null,
          color: isSelected ? null : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? AppColors.primary : Colors.transparent,
            width: 2,
          ),
        ),
        child: Column(
          children: [
            Icon(
              icon,
              size: 48,
              color: isSelected ? Colors.white : AppColors.textSecondary,
            ),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: isSelected ? Colors.white : AppColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeightWeightPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          const Text(
            '📏',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'Chiều cao & Cân nặng',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 48),
          
          // Height
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      _height.toStringAsFixed(0),
                      style: const TextStyle(fontSize: 40, fontWeight: FontWeight.bold, color: AppColors.primary),
                    ),
                    const SizedBox(width: 8),
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text('cm', style: TextStyle(fontSize: 18, color: AppColors.textSecondary)),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Slider(
                  value: _height,
                  min: 100,
                  max: 220,
                  divisions: 120,
                  onChanged: (value) {
                    setState(() => _height = value);
                  },
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('100 cm', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                    Text('220 cm', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          
          // Weight
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      _weight.toStringAsFixed(1),
                      style: const TextStyle(fontSize: 40, fontWeight: FontWeight.bold, color: AppColors.calories),
                    ),
                    const SizedBox(width: 8),
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text('kg', style: TextStyle(fontSize: 18, color: AppColors.textSecondary)),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Slider(
                  value: _weight,
                  min: 30,
                  max: 150,
                  divisions: 240,
                  onChanged: (value) {
                    setState(() => _weight = value);
                  },
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('30 kg', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                    Text('150 kg', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildActivityLevelPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          const Text(
            '🏃',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'Mức độ vận động',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          Text(
            'Chọn mức độ phù hợp với lối sống của bạn',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 32),
          
          _buildActivityCard('sedentary', 'Ít vận động', 'Ngồi nhiều, ít hoạt động'),
          const SizedBox(height: 12),
          _buildActivityCard('light', 'Nhẹ nhàng', 'Tập nhẹ 1-3 ngày/tuần'),
          const SizedBox(height: 12),
          _buildActivityCard('moderate', 'Trung bình', 'Tập 3-5 ngày/tuần'),
          const SizedBox(height: 12),
          _buildActivityCard('active', 'Năng động', 'Tập 6-7 ngày/tuần'),
          const SizedBox(height: 12),
          _buildActivityCard('very_active', 'Rất năng động', 'Vận động viên, tập nặng'),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildActivityCard(String value, String title, String subtitle) {
    final isSelected = _activityLevel == value;
    return GestureDetector(
      onTap: () => setState(() => _activityLevel = value),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary.withOpacity(0.1) : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? AppColors.primary : Colors.transparent,
            width: 2,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: isSelected ? AppColors.primary : AppColors.textHint,
                  width: 2,
                ),
                color: isSelected ? AppColors.primary : Colors.transparent,
              ),
              child: isSelected
                  ? const Icon(Icons.check, size: 16, color: Colors.white)
                  : null,
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: isSelected ? AppColors.primary : AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHealthGoalPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          const Text(
            '🎯',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'Mục tiêu sức khỏe',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          Text(
            'Bạn muốn đạt được điều gì?',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 32),
          
          _buildGoalCard('lose', 'Giảm cân', 'Giảm mỡ, cải thiện vóc dáng', Icons.trending_down, AppColors.error),
          const SizedBox(height: 12),
          _buildGoalCard('maintain', 'Duy trì', 'Giữ cân nặng hiện tại', Icons.remove, AppColors.success),
          const SizedBox(height: 12),
          _buildGoalCard('gain', 'Tăng cân', 'Tăng cơ, tăng cân lành mạnh', Icons.trending_up, AppColors.info),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildGoalCard(String value, String title, String subtitle, IconData icon, Color color) {
    final isSelected = _healthGoal == value;
    return GestureDetector(
      onTap: () => setState(() => _healthGoal = value),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: isSelected ? color.withOpacity(0.1) : AppColors.surfaceLight,
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
                color: isSelected ? color.withOpacity(0.2) : AppColors.surface,
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
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            if (isSelected)
              Icon(Icons.check_circle, color: color, size: 28),
          ],
        ),
      ),
    );
  }
}
