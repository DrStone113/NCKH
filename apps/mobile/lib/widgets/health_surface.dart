import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class HealthSurface extends StatelessWidget {
  const HealthSurface(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(20),
      this.color = AppColors.surface});
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            boxShadow: AppShadows.subtle),
        child: Material(
          color: color,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(24),
              side: const BorderSide(color: Color(0xFFE5E9EE))),
          child: Padding(padding: padding, child: child),
        ),
      );
}

class HealthSectionTitle extends StatelessWidget {
  const HealthSectionTitle(this.title, {super.key, this.subtitle, this.action});
  final String title;
  final String? subtitle;
  final Widget? action;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 24, bottom: 14),
        child: Row(children: [
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.5)),
                if (subtitle != null) ...[
                  const SizedBox(height: 5),
                  Text(subtitle!,
                      style: const TextStyle(
                          color: AppColors.textSecondary, height: 1.4))
                ],
              ])),
          if (action != null) action!
        ]),
      );
}

class NutritionEmptyState extends StatelessWidget {
  const NutritionEmptyState(
      {super.key,
      required this.title,
      this.message,
      this.actionLabel,
      this.onAction,
      this.icon = Icons.restaurant_menu_rounded});
  final String title;
  final String? message, actionLabel;
  final VoidCallback? onAction;
  final IconData icon;
  @override
  Widget build(BuildContext context) => HealthSurface(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Align(
            alignment: Alignment.centerLeft,
            child: CircleAvatar(
                radius: 25,
                backgroundColor: AppColors.surfaceLight,
                child: Icon(icon, color: AppColors.primary))),
        const SizedBox(height: 16),
        Text(title,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        if (message != null) ...[
          const SizedBox(height: 8),
          Text(message!,
              style:
                  const TextStyle(color: AppColors.textSecondary, height: 1.5))
        ],
        if (onAction != null && actionLabel != null) ...[
          const SizedBox(height: 12),
          Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                  onPressed: onAction,
                  icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                  label: Text(actionLabel!)))
        ],
      ]));
}

class NutritionSkeleton extends StatelessWidget {
  const NutritionSkeleton({super.key, this.lines = 3});
  final int lines;
  @override
  Widget build(BuildContext context) => Semantics(
      label: 'Đang tải thông tin dinh dưỡng',
      child: HealthSurface(
          child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: List.generate(
            lines,
            (i) => Container(
                  margin: const EdgeInsets.symmetric(vertical: 8),
                  width: i == 0 ? 140 : double.infinity,
                  height: i == 0 ? 24 : 40,
                  decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(12)),
                )),
      )));
}
