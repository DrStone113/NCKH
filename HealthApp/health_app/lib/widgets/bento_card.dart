import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class BentoCard extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry padding;
  final Color? color;
  final LinearGradient? gradient;
  final double? width;
  final double? height;

  const BentoCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.all(24),
    this.color,
    this.gradient,
    this.width,
    this.height,
  });

  @override
  State<BentoCard> createState() => _BentoCardState();
}

class _BentoCardState extends State<BentoCard> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  bool _isHovered = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
       vsync: this,
       duration: const Duration(milliseconds: 150),
    );
    _scaleAnimation = Tween<double>(begin: 1.0, end: 0.98).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget card = AnimatedBuilder(
      animation: _scaleAnimation,
      builder: (context, child) => Transform.scale(
        scale: _scaleAnimation.value,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: widget.width,
          height: widget.height,
          padding: widget.padding,
          decoration: BoxDecoration(
            color: widget.gradient == null ? (widget.color ?? AppColors.surface) : null,
            gradient: widget.gradient,
            borderRadius: BorderRadius.circular(32), // Signature Bento severe rounding
            boxShadow: [
              BoxShadow(
                color: _isHovered 
                    ? Colors.black.withOpacity(0.08) 
                    : Colors.black.withOpacity(0.04), // Very subtle shadow
                blurRadius: _isHovered ? 24 : 16,
                offset: Offset(0, _isHovered ? 12 : 8),
              ),
            ],
          ),
          child: child,
        ),
      ),
      child: widget.child,
    );

    if (widget.onTap != null) {
      card = MouseRegion(
        onEnter: (_) => setState(() => _isHovered = true),
        onExit: (_) => setState(() => _isHovered = false),
        child: GestureDetector(
          onTapDown: (_) => _controller.forward(),
          onTapUp: (_) {
            _controller.reverse();
            widget.onTap!();
          },
          onTapCancel: () => _controller.reverse(),
          child: card,
        ),
      );
    }

    return card;
  }
}
