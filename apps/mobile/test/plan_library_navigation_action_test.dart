import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/plans/widgets/plan_library_navigation_action.dart';

void main() {
  testWidgets('Plan library navigation has one stable semantic action',
      (WidgetTester tester) async {
    final semantics = tester.ensureSemantics();
    try {
      var navigationInvoked = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PlanLibraryNavigationAction(
              onActivate: () => navigationInvoked = true,
              child: GestureDetector(
                onTap: () => navigationInvoked = true,
                child: const Text('Kế hoạch'),
              ),
            ),
          ),
        ),
      );

      final planNavigation = find.bySemanticsLabel(
        PlanLibraryNavigationAction.semanticsLabel,
      );
      expect(planNavigation, findsOneWidget);
      expect(
        tester.getSemantics(planNavigation),
        matchesSemantics(
          label: PlanLibraryNavigationAction.semanticsLabel,
          isButton: true,
          hasTapAction: true,
        ),
      );

      await tester.tap(planNavigation);
      expect(navigationInvoked, isTrue);
    } finally {
      semantics.dispose();
    }
  });
}
