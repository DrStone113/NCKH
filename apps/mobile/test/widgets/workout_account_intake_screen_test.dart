import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/auth/screens/workout_account_intake_screen.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:provider/provider.dart';

Widget _screen(UserProvider provider) => ChangeNotifierProvider.value(
      value: provider,
      child: const MaterialApp(home: WorkoutAccountIntakeScreen()),
    );

Future<void> _choose(WidgetTester tester, String label) async {
  await tester.tap(find.text(label).first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('nutrition-only intake prioritizes food questions and can save',
      (tester) async {
    final provider = UserProvider()..setDemoUser();

    await tester.pumpWidget(_screen(provider));
    expect(find.text('Bạn muốn mình hỗ trợ điều gì nhất?'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);

    await _choose(tester, 'Ăn uống & dinh dưỡng');
    expect(
        find.byType(TextField, skipOffstage: false), findsAtLeastNWidgets(2));
    expect(find.text('Kinh nghiệm và điều kiện tập'), findsNothing);

    await tester.scrollUntilVisible(
      find.text('Lưu và tiếp tục'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Lưu và tiếp tục'));
    await tester.pumpAndSettle();
    expect(provider.currentUser?.healthProfile?.primarySupport, 'NUTRITION');
    expect(provider.currentUser?.workoutProfile, isNull);
  });

  testWidgets('pregnancy is hidden for unknown and male exercise profiles',
      (tester) async {
    final unknownProvider = UserProvider()..setDemoUser();
    await tester.pumpWidget(_screen(unknownProvider));
    await _choose(tester, 'Tập luyện');
    await tester.drag(find.byType(ListView), const Offset(0, -1800));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.pregnant_woman_outlined), findsNothing);

    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();

    final maleProvider = UserProvider()..setDemoUser();
    await maleProvider.updateProfile(
      maleProvider.currentUser!.copyWith(gender: 'male'),
    );
    await tester.pumpWidget(_screen(maleProvider));
    await _choose(tester, 'Tập luyện');
    await tester.drag(find.byType(ListView), const Offset(0, -1800));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.pregnant_woman_outlined), findsNothing);
  });

  testWidgets('pregnancy is shown only for explicitly female exercise profile',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    await provider.updateProfile(
      provider.currentUser!.copyWith(gender: 'female'),
    );

    await tester.pumpWidget(_screen(provider));
    await _choose(tester, 'Tập luyện');
    await tester.drag(find.byType(ListView), const Offset(0, -1800));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.pregnant_woman_outlined), findsOneWidget);
  });
}
