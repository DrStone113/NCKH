import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/user_provider.dart';
import '../../home/screens/home_screen.dart';
import '../../settings/screens/profile_settings_screen.dart';
import 'auth_screen.dart';
import 'workout_account_intake_screen.dart';

class AuthWrapper extends StatelessWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, userProvider, _) {
        // Chờ session restore xong trước khi quyết định route
        if (!userProvider.isInitialized) {
          return const Scaffold(
            body: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Đang tải...', style: TextStyle(color: Colors.grey)),
                ],
              ),
            ),
          );
        }
        if (userProvider.isFirebaseAuthenticated &&
            userProvider.isProfileLoading) {
          return Semantics(
            label: 'auth-profile-loading',
            child: const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            ),
          );
        }
        if (userProvider.hasProfileError) {
          return Semantics(
            label: 'auth-profile-error',
            child: Scaffold(
              body: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('Chưa thể tải hồ sơ tài khoản.'),
                    const SizedBox(height: 12),
                    FilledButton(
                      key: const ValueKey('auth-profile-retry'),
                      onPressed: userProvider.retryProfileBootstrap,
                      child: const Text('Thử lại'),
                    ),
                    TextButton(
                      key: const ValueKey('auth-profile-sign-out'),
                      onPressed: userProvider.signOut,
                      child: const Text('Đăng xuất'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }
        if (userProvider.isAuthenticated) {
          if (userProvider.needsBasicProfileIntake) {
            return ProfileSettingsScreen(
              key: ValueKey(userProvider.currentUser!.id),
              isAccountSetup: true,
            );
          }
          // A new registration reaches this gate immediately. Existing users
          // re-enter it only when an account-intake version gains a question
          // they have not explicitly answered yet.
          if (userProvider.needsAccountHealthIntake) {
            return const WorkoutAccountIntakeScreen();
          }
          return Semantics(
            label: 'auth-signed-in',
            child: const HomeScreen(),
          );
        }
        return Semantics(
          label: 'auth-signed-out',
          child: const AuthScreen(),
        );
      },
    );
  }
}
