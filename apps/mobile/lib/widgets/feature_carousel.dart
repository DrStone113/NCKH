import 'dart:async';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'feature_card.dart';
import '../utils/responsive_utils.dart';

class FeatureCarousel extends StatefulWidget {
  const FeatureCarousel({super.key});

  @override
  State<FeatureCarousel> createState() => _FeatureCarouselState();
}

class _FeatureCarouselState extends State<FeatureCarousel> {
  static const int _itemCount = 4;
  static const int _baseOffset = 1000; // Base index for smooth 2-way infinite scroll

  late PageController _pageController;
  Timer? _autoRotateTimer;
  int _activeCard = 0;
  bool _isUserInteracting = false;
  double _viewportFraction = 0.88;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(
      initialPage: _baseOffset,
      viewportFraction: _viewportFraction,
    );
    _startAutoRotate();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final newFraction = _calculateViewportFraction(context);
    if ((_viewportFraction - newFraction).abs() > 0.01) {
      _viewportFraction = newFraction;
      final currentPage = _pageController.hasClients 
          ? (_pageController.page?.round() ?? _baseOffset + _activeCard)
          : _baseOffset + _activeCard;
      _pageController.dispose();
      _pageController = PageController(
        initialPage: currentPage,
        viewportFraction: _viewportFraction,
      );
      setState(() {});
    }
  }

  double _calculateViewportFraction(BuildContext context) {
    if (ResponsiveUtils.isDesktop(context)) {
      return 0.34;
    } else if (ResponsiveUtils.isTablet(context)) {
      return 0.52;
    }
    return 0.88;
  }

  void _startAutoRotate() {
    _autoRotateTimer?.cancel();
    _autoRotateTimer = Timer.periodic(const Duration(milliseconds: 3600), (timer) {
      if (!mounted || _isUserInteracting || !_pageController.hasClients) return;
      
      _pageController.nextPage(
        duration: const Duration(milliseconds: 650),
        curve: Curves.easeInOutCubic,
      );
    });
  }

  void _changeCard(int targetCardIndex) {
    if (!_pageController.hasClients) return;

    final currentPage = _pageController.page?.round() ?? (_baseOffset + _activeCard);
    final currentCardIndex = currentPage % _itemCount;

    int diff = targetCardIndex - currentCardIndex;
    if (diff > 2) diff -= _itemCount;
    if (diff < -2) diff += _itemCount;

    _pageController.animateToPage(
      currentPage + diff,
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  void dispose() {
    _autoRotateTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: NotificationListener<ScrollNotification>(
            onNotification: (ScrollNotification notification) {
              if (notification is ScrollStartNotification) {
                _isUserInteracting = true;
                _autoRotateTimer?.cancel();
              } else if (notification is ScrollEndNotification) {
                _isUserInteracting = false;
                _startAutoRotate();
              }
              return false;
            },
            child: ScrollConfiguration(
              behavior: const MaterialScrollBehavior().copyWith(
                dragDevices: {
                  PointerDeviceKind.touch,
                  PointerDeviceKind.mouse,
                  PointerDeviceKind.trackpad,
                  PointerDeviceKind.stylus,
                },
              ),
              child: PageView.builder(
                controller: _pageController,
                physics: const BouncingScrollPhysics(),
                onPageChanged: (index) {
                  final normalizedIndex = index % _itemCount;
                  if (_activeCard != normalizedIndex) {
                    setState(() {
                      _activeCard = normalizedIndex;
                    });
                  }
                },
                itemBuilder: (context, index) {
                  final cardIndex = index % _itemCount;
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 8.0),
                    child: _getCardByIndex(cardIndex),
                  );
                },
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        // Dots indicator
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(_itemCount, (index) {
            final isActive = _activeCard == index;
            return GestureDetector(
              onTap: () => _changeCard(index),
              behavior: HitTestBehavior.opaque,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeOutCubic,
                margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                width: isActive ? 26 : 8,
                height: 8,
                decoration: BoxDecoration(
                  color: isActive 
                      ? const Color(0xFF4CAF50)
                      : const Color(0xFFD1D5DB),
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            );
          }),
        ),
        const SizedBox(height: 12),
      ],
    );
  }

  Widget _getCardByIndex(int index) {
    switch (index) {
      case 0:
        return const FeatureCard(
          title: 'Theo dõi Hoạt động',
          description: 'Giám sát số bước chân, lượng calo tiêu hao và thời gian vận động mỗi ngày.',
          image: _FeatureGraphic(
            gradientColors: [Color(0xFFE8F5E9), Color(0xFFC8E6C9)],
            icon: Icons.directions_run,
            iconColor: Color(0xFF2E7D32),
            label: 'Bước chân & Vận động',
          ),
        );
      case 1:
        return const FeatureCard(
          title: 'Kế hoạch Tập luyện',
          description: 'Các bài tập thể chất thông minh giúp bạn tối ưu hóa vóc dáng và sức khỏe.',
          image: _FeatureGraphic(
            gradientColors: [Color(0xFFFFF3E0), Color(0xFFFFE0B2)],
            icon: Icons.fitness_center,
            iconColor: Color(0xFFEF6C00),
            label: 'Sức mạnh & Cơ bắp',
          ),
        );
      case 2:
        return const FeatureCard(
          title: 'Phân tích Dinh dưỡng',
          description: 'Gợi ý thực đơn cá nhân hóa và tính toán Macro/Calo chuẩn xác theo mục tiêu.',
          image: _FeatureGraphic(
            gradientColors: [Color(0xFFE0F2F1), Color(0xFFB2DFDB)],
            icon: Icons.restaurant_menu,
            iconColor: Color(0xFF00796B),
            label: 'Dinh dưỡng Lành mạnh',
          ),
        );
      case 3:
        return const FeatureCard(
          title: 'Theo dõi Nước uống',
          description: 'Nhắc nhở uống nước đúng giờ và duy trì độ ẩm lý tưởng cho cơ thể suốt ngày dài.',
          image: _FeatureGraphic(
            gradientColors: [Color(0xFFE3F2FD), Color(0xFFBBDEFB)],
            icon: Icons.water_drop,
            iconColor: Color(0xFF1976D2),
            label: 'Cân bằng Nước',
          ),
        );
      default:
        return const SizedBox();
    }
  }
}

class _FeatureGraphic extends StatelessWidget {
  final List<Color> gradientColors;
  final IconData icon;
  final Color iconColor;
  final String label;

  const _FeatureGraphic({
    required this.gradientColors,
    required this.icon,
    required this.iconColor,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: gradientColors,
        ),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(8.0),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 54,
                  height: 54,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: iconColor.withValues(alpha: 0.22),
                        blurRadius: 14,
                        spreadRadius: 1,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
                  child: Icon(
                    icon,
                    size: 30,
                    color: iconColor,
                  ),
                ),
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.94),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.05),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Text(
                    label,
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: iconColor,
                      fontSize: 12.5,
                      letterSpacing: -0.2,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
