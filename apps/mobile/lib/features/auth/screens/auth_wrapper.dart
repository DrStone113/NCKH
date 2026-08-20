import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../providers/user_provider.dart';
import '../../home/screens/home_screen.dart';
import 'auth_screen.dart';

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
        if (userProvider.isAuthenticated) {
          return const HomeScreen();
        }
        return const AuthScreen();
      },
    );
  }
}
