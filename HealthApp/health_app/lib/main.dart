import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';
import 'package:provider/provider.dart';
import 'theme/app_theme.dart';
import 'features/auth/screens/auth_screen.dart';
import 'features/home/screens/home_screen.dart';
import 'providers/user_provider.dart';
import 'providers/health_provider.dart';
import 'providers/nutrition_provider.dart';
import 'providers/exercise_provider.dart';
import 'providers/chat_provider.dart';
import 'providers/ai_chat_provider.dart';
import 'services/wger_cache_service.dart';
import 'services/local_exercise_service.dart';

import 'providers/lifestyle_provider.dart';
import 'providers/proactive_provider.dart';

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

  // Pre-load wger exercises từ local JSON
  _preLoadWgerExercises();

  // Pre-fetch wger data in background (không block app startup)
  _preFetchWgerData();

  runApp(MyApp(firebaseOk: firebaseOk));
}

/// Pre-load wger exercises từ local JSON
void _preLoadWgerExercises() {
  Future.delayed(const Duration(milliseconds: 100), () {
    debugPrint('🏋️ Loading wger exercises from local JSON...');
    LocalExerciseService().loadExercises().then((_) {
      final count = LocalExerciseService().allExercises.length;
      debugPrint('✅ Loaded $count wger exercises');
    }).catchError((e) {
      debugPrint('⚠️ Failed to load wger exercises: $e');
    });
  });
}

/// Pre-fetch wger data in background để cải thiện UX
void _preFetchWgerData() {
  Future.delayed(const Duration(milliseconds: 500), () {
    debugPrint('🚀 Starting wger pre-fetch...');
    WgerCacheService().preFetchData().then((_) {
      debugPrint('✅ Wger pre-fetch completed');
    }).catchError((e) {
      debugPrint('⚠️ Wger pre-fetch failed: $e');
    });
  });
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
        ChangeNotifierProvider(create: (_) => LifestyleProvider()),
        ChangeNotifierProvider(create: (_) => ProactiveProvider()),
        ChangeNotifierProvider(create: (_) {
          final provider = ExerciseProvider();
          provider.initWgerExercises(); // Load wger exercises
          return provider;
        }),
        ChangeNotifierProvider(create: (_) => ChatProvider()),
        // HealthProvider được thêm vào đây để chatbot đọc/ghi được lịch sử cân
        // nặng. Thiếu nó thì tool `get_weight_history` và `log_weight` không có
        // nguồn dữ liệu nào để làm việc.
        ChangeNotifierProxyProvider4<ExerciseProvider, NutritionProvider, LifestyleProvider, HealthProvider, AIChatProvider>(
          create: (_) => AIChatProvider(),
          update: (_, exercise, nutrition, lifestyle, health, aiChat) {
            final chat = aiChat ?? AIChatProvider();
            chat.setProviders(
              exerciseProvider: exercise,
              nutritionProvider: nutrition,
              lifestyleProvider: lifestyle,
              healthProvider: health,
            );
            return chat;
          },
        ),
      ],
      child: MaterialApp(
        title: 'Health App v1.1.0',
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
