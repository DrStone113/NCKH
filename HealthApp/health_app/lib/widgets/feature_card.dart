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
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeOutCubic,
        transform: Matrix4.identity()
          ..translate(0.0, _isHovered ? -6.0 : 0.0)
          ..scale(_isHovered ? 1.03 : 1.0),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: _isHovered 
                ? Theme.of(context).primaryColor.withValues(alpha: 0.4)
                : Colors.grey.withValues(alpha: 0.15),
            width: _isHovered ? 2 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 5,
              child: Container(
                margin: EdgeInsets.all(cardPadding * 0.5),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  color: const Color(0xFFF8F9FA),
                ),
                clipBehavior: Clip.antiAlias,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    widget.image,
                    Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Colors.transparent,
                            Colors.white.withValues(alpha: 0.05),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Expanded(
              flex: 3,
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  cardPadding,
                  (cardPadding * 0.25).clamp(2.0, 8.0),
                  cardPadding,
                  (cardPadding * 0.5).clamp(4.0, 16.0),
                ),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.topLeft,
                  child: SizedBox(
                    width: ResponsiveUtils.isMobile(context) ? MediaQuery.of(context).size.width * 0.7 : 280,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          widget.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: titleSize,
                            fontWeight: FontWeight.w700,
                            color: const Color(0xFF111111),
                            letterSpacing: -0.5,
                          ),
                        ),
                        SizedBox(height: cardPadding * 0.25),
                        Text(
                          widget.description,
                          style: TextStyle(
                            fontSize: bodySize,
                            color: const Color(0xFF666666),
                            height: 1.3,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
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
