import 'package:flutter/material.dart';

class ResponsiveUtils {
  // Breakpoints
  static const double mobileMaxWidth = 600;
  static const double tabletMaxWidth = 1024;
  
  // Check device type
  static bool isMobile(BuildContext context) {
    return MediaQuery.of(context).size.width < mobileMaxWidth;
  }
  
  static bool isTablet(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    return width >= mobileMaxWidth && width < tabletMaxWidth;
  }
  
  static bool isDesktop(BuildContext context) {
    return MediaQuery.of(context).size.width >= tabletMaxWidth;
  }
  
  // Get responsive value
  static T responsive<T>(
    BuildContext context, {
    required T mobile,
    T? tablet,
    T? desktop,
  }) {
    if (isDesktop(context) && desktop != null) return desktop;
    if (isTablet(context) && tablet != null) return tablet;
    return mobile;
  }
  
  // Grid columns
  static int getGridColumns(BuildContext context) {
    if (isDesktop(context)) return 3;
    if (isTablet(context)) return 2;
    return 1;
  }
  
  // Font sizes
  static double getHeadingSize(BuildContext context) {
    return responsive(context, mobile: 24.0, tablet: 28.0, desktop: 32.0);
  }
  
  static double getTitleSize(BuildContext context) {
    return responsive(context, mobile: 18.0, tablet: 20.0, desktop: 22.0);
  }
  
  static double getBodySize(BuildContext context) {
    return responsive(context, mobile: 14.0, tablet: 16.0, desktop: 16.0);
  }
  
  static double getSmallSize(BuildContext context) {
    return responsive(context, mobile: 12.0, tablet: 14.0, desktop: 14.0);
  }
  
  // Padding
  static double getScreenPadding(BuildContext context) {
    return responsive(context, mobile: 20.0, tablet: 32.0, desktop: 48.0);
  }
  
  static double getCardPadding(BuildContext context) {
    return responsive(context, mobile: 16.0, tablet: 20.0, desktop: 24.0);
  }
  
  // Card sizes
  static double getCardHeight(BuildContext context) {
    return responsive(context, mobile: 140.0, tablet: 160.0, desktop: 180.0);
  }
  
  // Icon sizes
  static double getIconSize(BuildContext context) {
    return responsive(context, mobile: 24.0, tablet: 28.0, desktop: 32.0);
  }
  
  // Carousel
  static int getCarouselVisibleCards(BuildContext context) {
    if (isDesktop(context)) return 3;
    if (isTablet(context)) return 2;
    return 1;
  }
  
  static double getCarouselCardWidth(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final padding = getScreenPadding(context);
    final visibleCards = getCarouselVisibleCards(context);
    final spacing = 16.0 * (visibleCards - 1);
    
    return (screenWidth - (padding * 2) - spacing) / visibleCards;
  }
}
