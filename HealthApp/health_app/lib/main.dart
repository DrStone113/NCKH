import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';
import 'package:provider/provider.dart';
import 'theme/app_theme.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'providers/user_provider.dart';
import 'providers/health_provider.dart';
import 'providers/nutrition_provider.dart';
import 'providers/exercise_provider.dart';
import 'providers/chat_provider.dart';
import 'providers/ai_chat_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Try Firebase init - may fail on web/desktop without config
  bool firebaseOk = false;
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
    firebaseOk = true;
  } catch (e) {
    debugPrint('Firebase init failed: $e (running in demo mode)');
  }

  runApp(MyApp(firebaseOk: firebaseOk));
}

class MyApp extends StatelessWidget {
  final bool firebaseOk;
  const MyApp({super.key, required this.firebaseOk});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => UserProvider()),
        ChangeNotifierProvider(create: (_) => HealthProvider()),
        ChangeNotifierProvider(create: (_) => NutritionProvider()),
        ChangeNotifierProvider(create: (_) => ExerciseProvider()),
        ChangeNotifierProvider(create: (_) => ChatProvider()),
        ChangeNotifierProvider(create: (_) => AIChatProvider()),
      ],
      child: MaterialApp(
        title: 'Health App',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.darkTheme,
        home: const AuthWrapper(),
      ),
    );
  }
}

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
