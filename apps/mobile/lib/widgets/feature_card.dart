import 'package:flutter/material.dart';
import '../utils/responsive_utils.dart';

class FeatureCard extends StatefulWidget {
  final Widget image;
  final String title;
  final String description;

  const FeatureCard({
    super.key,
    required this.image,
    required this.title,
    required this.description,
  });

  @override
  State<FeatureCard> createState() => _FeatureCardState();
}

class _FeatureCardState extends State<FeatureCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final titleSize = ResponsiveUtils.getTitleSize(context);
    final bodySize = ResponsiveUtils.getBodySize(context);
    final cardPadding = ResponsiveUtils.getCardPadding(context);

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOutCubic,
        transform: Matrix4.translationValues(0, _isHovered ? -4 : 0, 0),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: _isHovered 
                ? Theme.of(context).primaryColor.withValues(alpha: 0.35)
                : Colors.grey.withValues(alpha: 0.12),
            width: _isHovered ? 1.5 : 1.0,
          ),
          boxShadow: [
            BoxShadow(
              color: _isHovered
                  ? Colors.black.withValues(alpha: 0.08)
                  : Colors.black.withValues(alpha: 0.04),
              blurRadius: _isHovered ? 16 : 10,
              offset: Offset(0, _isHovered ? 6 : 3),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Graphic section
            Expanded(
              flex: 5,
              child: Container(
                margin: EdgeInsets.all(cardPadding * 0.4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  color: const Color(0xFFF8F9FA),
                ),
                clipBehavior: Clip.antiAlias,
                child: widget.image,
              ),
            ),
            // Text info section
            Expanded(
              flex: 3,
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: cardPadding * 0.8,
                  vertical: 4.0,
                ),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: SizedBox(
                    width: 260,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          widget.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: (titleSize * 0.95).clamp(15.0, 18.0),
                            fontWeight: FontWeight.w700,
                            color: const Color(0xFF1E293B),
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          widget.description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: (bodySize * 0.85).clamp(11.0, 13.0),
                            color: const Color(0xFF64748B),
                            height: 1.25,
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
  }
}
