import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
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
        builder: (context, child) {
          if (kIsWeb && child != null) {
            return _WebPhoneWrapper(child: child);
          }
          return child ?? const SizedBox.shrink();
        },
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

class _WebPhoneWrapper extends StatefulWidget {
  final Widget child;
  const _WebPhoneWrapper({required this.child});

  @override
  State<_WebPhoneWrapper> createState() => _WebPhoneWrapperState();
}

class _WebPhoneWrapperState extends State<_WebPhoneWrapper> {
  // Tỉ lệ mặc định 19.5:9
  double _aspectRatio = 19.5 / 9;
  String _ratioLabel = '19.5:9';

  // Theme của viền điện thoại: 'black', 'neon', 'glass'
  String _frameTheme = 'black';

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Nếu màn hình chiều ngang nhỏ hơn 600px, coi như đang ở trên điện thoại thật và cho hiển thị tràn viền
        if (constraints.maxWidth < 600) {
          return widget.child;
        }

        // Đặt kích thước cơ sở cố định cho màn hình điện thoại mô phỏng (giống iPhone thực tế)
        const double baseWidth = 375.0;
        final double baseHeight = baseWidth * _aspectRatio;

        // Cấu hình viền & bóng đổ dựa trên style lựa chọn
        Color frameBorderColor;
        List<BoxShadow> frameShadows;

        if (_frameTheme == 'neon') {
          frameBorderColor = const Color(0xFF6B4EFF);
          frameShadows = [
            BoxShadow(
              color: const Color(0xFF6B4EFF).withOpacity(0.5),
              blurRadius: 25,
              spreadRadius: 2,
            ),
            BoxShadow(
              color: Colors.black.withOpacity(0.6),
              blurRadius: 40,
              offset: const Offset(0, 20),
            ),
          ];
        } else if (_frameTheme == 'glass') {
          frameBorderColor = Colors.white.withOpacity(0.25);
          frameShadows = [
            BoxShadow(
              color: Colors.white.withOpacity(0.05),
              blurRadius: 20,
              spreadRadius: -5,
            ),
            BoxShadow(
              color: Colors.black.withOpacity(0.5),
              blurRadius: 40,
              offset: const Offset(0, 20),
            ),
          ];
        } else {
          // 'black' - Mặc định đen huyền bí
          frameBorderColor = const Color(0xFF1E1E2E);
          frameShadows = [
            BoxShadow(
              color: Colors.black.withOpacity(0.7),
              blurRadius: 45,
              offset: const Offset(0, 25),
            ),
            BoxShadow(
              color: const Color(0xFF6B4EFF).withOpacity(0.15),
              blurRadius: 60,
              offset: const Offset(0, 10),
            ),
          ];
        }

        return Scaffold(
          backgroundColor: const Color(0xFF090610),
          body: Container(
            width: double.infinity,
            height: double.infinity,
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFF0F0C1B),
                  Color(0xFF19122B),
                  Color(0xFF090610),
                ],
              ),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Các quầng sáng màu ảo diệu phía sau
                Positioned(
                  top: -150,
                  right: -150,
                  child: Container(
                    width: 500,
                    height: 500,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [
                          const Color(0xFF6B4EFF).withOpacity(0.18),
                          const Color(0xFF6B4EFF).withOpacity(0.0),
                        ],
                      ),
                    ),
                  ),
                ),
                Positioned(
                  bottom: -200,
                  left: -200,
                  child: Container(
                    width: 600,
                    height: 600,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [
                          const Color(0xFF00F2FE).withOpacity(0.12),
                          const Color(0xFF00F2FE).withOpacity(0.0),
                        ],
                      ),
                    ),
                  ),
                ),

                // Bảng điều khiển góc dưới bên trái (Desktop Control Panel)
                Positioned(
                  bottom: 30,
                  left: 30,
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1B1530).withOpacity(0.85),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.1),
                        width: 1,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.3),
                          blurRadius: 15,
                          offset: const Offset(0, 5),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'Tỷ Lệ Màn Hình',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _buildRatioButton('16:9', 16 / 9),
                            const SizedBox(width: 8),
                            _buildRatioButton('19.5:9', 19.5 / 9),
                            const SizedBox(width: 8),
                            _buildRatioButton('21:9', 21 / 9),
                          ],
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Phong Cách Viền',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _buildThemeButton('Bóng Đêm', 'black'),
                            const SizedBox(width: 8),
                            _buildThemeButton('Neon Glow', 'neon'),
                            const SizedBox(width: 8),
                            _buildThemeButton('Kính Mờ', 'glass'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                // Khung mô phỏng điện thoại ở giữa (dùng FittedBox để co giãn tự động dựa trên độ cao trình duyệt)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 20.0, horizontal: 10.0),
                    child: FittedBox(
                      fit: BoxFit.contain,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        curve: Curves.easeInOut,
                        width: baseWidth,
                        height: baseHeight,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(44),
                          boxShadow: frameShadows,
                        ),
                        child: Stack(
                          children: [
                            // Nội dung ứng dụng nằm bên trong viền màn hình điện thoại
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 300),
                              curve: Curves.easeInOut,
                              decoration: BoxDecoration(
                                border: Border.all(
                                  color: frameBorderColor,
                                  width: 12,
                                ),
                                borderRadius: BorderRadius.circular(44),
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(32),
                                child: MediaQuery(
                                  data: MediaQuery.of(context).copyWith(
                                    size: Size(baseWidth - 24, baseHeight - 24),
                                    padding: const EdgeInsets.only(top: 24, bottom: 16),
                                  ),
                                  child: widget.child,
                                ),
                              ),
                            ),
                            // Viền kim loại/ánh gương mỏng phản chiếu bên trong
                            IgnorePointer(
                              child: Container(
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(44),
                                  border: Border.all(
                                    color: Colors.white.withOpacity(0.08),
                                    width: 1,
                                  ),
                                ),
                              ),
                            ),
                            // Camera tai thỏ / Dynamic Island giả lập ở mép trên
                            Positioned(
                              top: 18,
                              left: 0,
                              right: 0,
                              child: IgnorePointer(
                                child: Align(
                                  alignment: Alignment.topCenter,
                                  child: Container(
                                    width: 100,
                                    height: 20,
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF1E1E2E),
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: Center(
                                      child: Container(
                                        width: 35,
                                        height: 3,
                                        decoration: BoxDecoration(
                                          color: Colors.white.withOpacity(0.12),
                                          borderRadius: BorderRadius.circular(2),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildRatioButton(String label, double ratio) {
    final bool isSelected = _ratioLabel == label;
    return InkWell(
      onTap: () {
        setState(() {
          _aspectRatio = ratio;
          _ratioLabel = label;
        });
      },
      borderRadius: BorderRadius.circular(8),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF6B4EFF) : Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? Colors.white.withOpacity(0.2) : Colors.transparent,
            width: 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white.withOpacity(0.7),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _buildThemeButton(String label, String theme) {
    final bool isSelected = _frameTheme == theme;
    return InkWell(
      onTap: () {
        setState(() {
          _frameTheme = theme;
        });
      },
      borderRadius: BorderRadius.circular(8),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF6B4EFF) : Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? Colors.white.withOpacity(0.2) : Colors.transparent,
            width: 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white.withOpacity(0.7),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
