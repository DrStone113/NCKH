import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/user_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/feature_carousel.dart';
import 'home_screen.dart';
import 'onboarding_screen.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _isLoading = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFFE8F5E9), // Light green
              Color(0xFFE0F2F1), // Light mint/teal
              Color(0xFFF9FAFB), // Off-white
            ],
            stops: [0.0, 0.4, 0.8],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
            const SizedBox(height: 24),
            // Header
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.favorite, color: Colors.white, size: 24),
                  ),
                  const SizedBox(width: 12),
                  const Text(
                    'Health App',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                      letterSpacing: -0.5,
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 32),
            
            // Carousel
            const Expanded(
              child: FeatureCarousel(),
            ),
            
            // Bottom Action Area
            Container(
              padding: const EdgeInsets.all(32),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(32),
                  topRight: Radius.circular(32),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.03),
                    offset: const Offset(0, -4),
                    blurRadius: 24,
                  ),
                ],
              ),
              child: SafeArea(
                top: false,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Bắt đầu nào',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: AppColors.textPrimary,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Đăng nhập để truy cập bảng điều khiển sức khỏe của bạn.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 15,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 32),
                    
                    SizedBox(
                      height: 56,
                      child: OutlinedButton(
                        onPressed: _isLoading ? null : _submitGoogle,
                        style: OutlinedButton.styleFrom(
                          backgroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(30),
                          ),
                          side: BorderSide(color: Colors.grey.shade300, width: 1.5),
                          elevation: 0,
                        ),
                        child: _isLoading 
                          ? const SizedBox(
                              width: 24, 
                              height: 24, 
                              child: CircularProgressIndicator(strokeWidth: 2)
                            )
                          : Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Image.network(
                                  'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Google_%22G%22_logo.svg/3840px-Google_%22G%22_logo.svg.png',
                                  width: 24,
                                  height: 24,
                                  errorBuilder: (context, error, stackTrace) => Container(
                                    width: 24,
                                    height: 24,
                                    decoration: BoxDecoration(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: const Icon(Icons.g_mobiledata, size: 24, color: Colors.blue),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                const Text(
                                  'Tiếp tục với Google', 
                                  style: TextStyle(
                                    color: AppColors.textPrimary, 
                                    fontWeight: FontWeight.w600, 
                                    fontSize: 16
                                  )
                                ),
                              ],
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      ),
    );
  }

  Future<void> _submitGoogle() async {
    setState(() => _isLoading = true);
    final userProvider = Provider.of<UserProvider>(context, listen: false);

    try {
      // In demo mode/desktop, Firebase might throw exception. 
      // We will catch it and allow demo user login as fallback.
      await userProvider.signInWithGoogle();
      if (mounted) {
        // Check if user needs onboarding (first time login)
        final user = userProvider.currentUser;
        final needsOnboarding = user != null && (user.age == 0 || user.height == 0);
        
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => needsOnboarding 
                ? const OnboardingScreen() 
                : const HomeScreen(),
          ),
        );
      }
    } catch (e) {
      debugPrint('Google Sign In Error: $e');
      if (mounted) {
        // Fallback for demo environments where Firebase isn't configured for Windows
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Firebase Error. Using Demo User.')),
        );
        userProvider.setDemoUser();
        
        // Check if demo user needs onboarding
        final user = userProvider.currentUser;
        final needsOnboarding = user != null && (user.age == 0 || user.height == 0);
        
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => needsOnboarding 
                ? const OnboardingScreen() 
                : const HomeScreen(),
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }
}
