import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'feature_card.dart';
import '../utils/responsive_utils.dart';

class FeatureCarousel extends StatefulWidget {
  const FeatureCarousel({super.key});

  @override
  State<FeatureCarousel> createState() => _FeatureCarouselState();
}

class _FeatureCarouselState extends State<FeatureCarousel> with TickerProviderStateMixin {
  late AnimationController _rotationController;
  late AnimationController _floatController;
  late PageController _pageController;
  Timer? _autoRotateTimer;
  int _activeCard = 0;
  int _previousCard = 0;

  @override
  void initState() {
    super.initState();
    
    _pageController = PageController(initialPage: 0);
    
    // Animation cho hiệu ứng xoay mượt mà
    _rotationController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );

    // Animation cho hiệu ứng float nhẹ nhàng
    _floatController = AnimationController(
      duration: const Duration(milliseconds: 3000),
      vsync: this,
    )..repeat(reverse: true);

    // Tự động xoay cards sau mỗi 3.5 giây
    _startAutoRotate();
  }

  void _startAutoRotate() {
    _autoRotateTimer = Timer.periodic(const Duration(milliseconds: 3500), (timer) {
      if (mounted && _pageController.hasClients) {
        final nextPage = (_activeCard + 1) % 5; // 5 cards
        _pageController.animateToPage(
          nextPage,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOutCubic,
        );
      }
    });
  }

  void _changeCard(int newIndex) {
    if (_pageController.hasClients) {
      _pageController.animateToPage(
        newIndex,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOutCubic,
      );
    }
  }

  @override
  void dispose() {
    _autoRotateTimer?.cancel();
    _pageController.dispose();
    _rotationController.dispose();
    _floatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final visibleCards = ResponsiveUtils.getCarouselVisibleCards(context);
    final cardWidth = ResponsiveUtils.getCarouselCardWidth(context);
    final screenWidth = MediaQuery.of(context).size.width;
    
    return LayoutBuilder(
      builder: (context, constraints) {
        return Column(
          children: [
            Expanded(
              child: visibleCards > 1 
                  ? _buildMultiCardView(cardWidth, visibleCards)
                  : _buildSingleCardView(),
            ),
            const SizedBox(height: 16),
            // Dots indicator
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(5, (index) {
                return GestureDetector(
                  onTap: () => _changeCard(index),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: _activeCard == index ? 24 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: _activeCard == index 
                          ? const Color(0xFF4CAF50)
                          : const Color(0xFFBDBDBD),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                );
              }),
            ),
            const SizedBox(height: 16),
          ],
        );
      },
    );
  }

  Widget _buildSingleCardView() {
    return Center(
      child: AspectRatio(
        aspectRatio: 0.85,
        child: PageView.builder(
          controller: _pageController,
          onPageChanged: (index) {
            setState(() {
              _previousCard = _activeCard;
              _activeCard = index;
            });
          },
          itemCount: 5,
          itemBuilder: (context, index) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: _getCardByIndex(index),
            );
          },
        ),
      ),
    );
  }

  Widget _buildMultiCardView(double cardWidth, int visibleCards) {
    return Center(
      child: AspectRatio(
        aspectRatio: 0.85,
        child: PageView.builder(
          controller: _pageController,
          onPageChanged: (index) {
            setState(() {
              _previousCard = _activeCard;
              _activeCard = index;
            });
          },
          itemCount: 5,
          itemBuilder: (context, index) {
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: SizedBox(
                width: cardWidth,
                child: _getCardByIndex(index),
              ),
            );
          },
        ),
      ),
    );
  }


  Widget _getCardByIndex(int index) {
    switch (index) {
      case 0:
        return _buildCard1();
      case 1:
        return _buildCard2();
      case 2:
        return _buildCard3();
      case 3:
        return _buildCard4();
      case 4:
        return _buildCard5();
      default:
        return _buildCard1();
    }
  }

  Widget _buildAnimatedCard(int index, Widget card) {
    final isActive = index == _activeCard;
    final cardOrder = (index - _activeCard) % 3;
    
    return AnimatedBuilder(
      animation: Listenable.merge([_rotationController, _floatController]),
      builder: (context, child) {
        // Tính toán vị trí và góc xoay dựa trên thứ tự
        double xOffset = 0;
        double yOffset = 0;
        double rotation = 0;
        double scale = 1.0;
        double opacity = 1.0;
        
        // Float effect nhẹ nhàng
        final floatValue = math.sin(_floatController.value * 2 * math.pi + index * 0.5);
        final floatOffset = floatValue * 6;
        
        switch (cardOrder) {
          case 0: // Card phía trước
            xOffset = 0;
            yOffset = 0 + floatOffset;
            rotation = 0;
            scale = 1.0;
            opacity = 1.0;
            break;
          case 1: // Card ở giữa
            xOffset = -30;
            yOffset = -30 + floatOffset * 0.5;
            rotation = -6; // Nghiêng trái
            scale = 0.90;
            opacity = 0.75;
            break;
          case 2: // Card phía sau
            xOffset = 30;
            yOffset = -60 + floatOffset * 0.3;
            rotation = 6; // Nghiêng phải
            scale = 0.80;
            opacity = 0.5;
            break;
        }
        
        // Smooth transition khi xoay
        final t = Curves.easeInOutCubic.transform(_rotationController.value);
        xOffset = xOffset * (1 - t * 0.3);
        yOffset = yOffset * (1 - t * 0.3);
        
        return Positioned(
          left: 20 + xOffset,
          top: 20 + yOffset,
          child: Transform.rotate(
            angle: rotation * math.pi / 180,
            child: Transform.scale(
              scale: scale,
              child: Opacity(
                opacity: opacity,
                child: GestureDetector(
                  onTap: () {
                    if (!isActive) {
                      setState(() {
                        _activeCard = index;
                      });
                      _rotationController.forward(from: 0.0);
                    }
                  },
                  child: SizedBox(
                    width: 320,
                    height: 420,
                    child: child,
                  ),
                ),
              ),
            ),
          ),
        );
      },
      child: card,
    );
  }

  Widget _buildCard1() {
    return FeatureCard(
      title: 'Theo dõi Hoạt động',
      description: 'Giám sát số bước chân, lượng calo đốt cháy và thời gian vận động hàng ngày.',
      image: const _PlaceholderGraphic(
        color: Color(0xFFE8F5E9),
        icon: Icons.directions_run,
        iconColor: Color(0xFF4CAF50),
        label: 'Bước chân & Cardio',
      ),
    );
  }

  Widget _buildCard2() {
    return FeatureCard(
      title: 'Kế hoạch Tập luyện',
      description: 'Các bài tập được tùy chỉnh để giúp bạn đạt được mục tiêu thể hình.',
      image: const _PlaceholderGraphic(
        color: Color(0xFFFFF3E0),
        icon: Icons.fitness_center,
        iconColor: Color(0xFFFF9800),
        label: 'Sức mạnh',
        isDark: true,
      ),
    );
  }

  Widget _buildCard3() {
    return FeatureCard(
      title: 'Phân tích Dinh dưỡng',
      description: 'Theo dõi bữa ăn và nhận thông tin sức khỏe cá nhân hóa hàng ngày.',
      image: const _PlaceholderGraphic(
        color: Color(0xFFE0F2F1),
        icon: Icons.restaurant_menu,
        iconColor: Color(0xFF009688),
        label: 'Chế độ ăn lành mạnh',
      ),
    );
  }

  Widget _buildCard4() {
    return FeatureCard(
      title: 'Theo dõi Nước uống',
      description: 'Duy trì đủ nước với nhắc nhở thông minh và mục tiêu uống nước hàng ngày.',
      image: const _PlaceholderGraphic(
        color: Color(0xFFE3F2FD),
        icon: Icons.water_drop,
        iconColor: Color(0xFF2196F3),
        label: 'Cân bằng nước',
      ),
    );
  }

  Widget _buildCard5() {
    return FeatureCard(
      title: 'Phân tích Giấc ngủ',
      description: 'Giám sát chất lượng giấc ngủ và cải thiện sự nghỉ ngơi của bạn.',
      image: const _PlaceholderGraphic(
        color: Color(0xFFF3E5F5),
        icon: Icons.bedtime,
        iconColor: Color(0xFF9C27B0),
        label: 'Chất lượng giấc ngủ',
        isDark: true,
      ),
    );
  }
}

class _PlaceholderGraphic extends StatefulWidget {
  final Color color;
  final IconData icon;
  final Color iconColor;
  final String label;
  final bool isDark;

  const _PlaceholderGraphic({
    required this.color,
    required this.icon,
    required this.iconColor,
    required this.label,
    this.isDark = false,
  });

  @override
  State<_PlaceholderGraphic> createState() => _PlaceholderGraphicState();
}

class _PlaceholderGraphicState extends State<_PlaceholderGraphic> 
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    // Hiệu ứng pulse nhẹ cho icon
    _pulseAnimation = Tween<double>(
      begin: 1.0,
      end: 1.08,
    ).animate(
      CurvedAnimation(
        parent: _pulseController,
        curve: Curves.easeInOut,
      ),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final iconSize = ResponsiveUtils.getIconSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            widget.color,
            widget.color.withValues(alpha: widget.color.a * 0.7),
          ],
        ),
      ),
      child: Center(
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Padding(
            padding: const EdgeInsets.all(8.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: _pulseAnimation.value,
                      child: Container(
                        padding: EdgeInsets.all(iconSize * 0.67),
                        decoration: BoxDecoration(
                          color: widget.isDark ? const Color(0xFF1E1E1E) : Colors.white,
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: [
                            BoxShadow(
                              color: widget.iconColor.withValues(alpha: 0.25),
                              blurRadius: 16,
                              spreadRadius: 1,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: Icon(widget.icon, size: iconSize * 2, color: widget.iconColor),
                      ),
                    );
                  },
                ),
                const SizedBox(height: 16),
                Container(
                  padding: EdgeInsets.symmetric(horizontal: iconSize * 0.67, vertical: iconSize * 0.33),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.9),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.08),
                        blurRadius: 8,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Text(
                    widget.label,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: widget.isDark ? const Color(0xFF333333) : widget.iconColor,
                      fontSize: bodySize,
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
