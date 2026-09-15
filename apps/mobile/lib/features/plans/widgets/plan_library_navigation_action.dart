import 'package:flutter/material.dart';

/// Stable, non-localized accessibility contract for opening the Plan library.
///
/// The visible child supplies the localized user-facing copy; this label is
/// intentionally technical so browser automation and assistive technology do
/// not depend on Vietnamese text encoding.
class PlanLibraryNavigationAction extends StatelessWidget {
  static const String semanticsLabel = 'app-nav-plan-library';

  const PlanLibraryNavigationAction({
    super.key,
    required this.onActivate,
    required this.child,
  });

  final VoidCallback onActivate;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticsLabel,
      button: true,
      onTap: onActivate,
      excludeSemantics: true,
      child: child,
    );
  }
}
