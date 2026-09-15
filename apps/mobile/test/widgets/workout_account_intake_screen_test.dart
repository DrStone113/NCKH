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
  if (label == 'Lưu và tiếp tục') {
    for (var i = 0; i < 3; i++) {
      await tester.tap(find.byKey(const Key('health-wizard-next')));
      await tester.pumpAndSettle();
    }
    return;
  }
  await tester.ensureVisible(find.text(label).first);
  await tester.tap(find.text(label).first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('explicit none persists as confirmed empty safety lists',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    var saved = false;
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
          home: WorkoutAccountIntakeScreen(
        initialSupport: 'NUTRITION',
        onSaved: () => saved = true,
      )),
    ));
    for (final label in [
      'Không có dị ứng đã biết',
      'Không có hạn chế ăn uống'
    ]) {
      await tester.scrollUntilVisible(find.text(label), 250,
          scrollable: find.byType(Scrollable).first);
      await _choose(tester, label);
    }
    await tester.scrollUntilVisible(
        find.byKey(const Key('health-wizard-next')), 300,
        scrollable: find.byType(Scrollable).first);
    await _choose(tester, 'Lưu và tiếp tục');
    final nutrition = provider.currentUser!.nutritionProfile!;
    expect(nutrition.foodAllergies, isEmpty);
    expect(nutrition.dietaryRestrictions, isEmpty);
    expect(nutrition.isConfirmedField('food_allergies'), isTrue);
    expect(nutrition.isConfirmedField('dietary_restrictions'), isTrue);
    expect(saved, isTrue);
  });

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
      find.byKey(const Key('health-wizard-next')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await _choose(tester, 'Lưu và tiếp tục');
    await tester.pumpAndSettle();
    expect(provider.currentUser?.healthProfile?.primarySupport, 'NUTRITION');
    expect(provider.currentUser?.workoutProfile, isNull);
  });

  testWidgets('pregnancy is hidden for unknown and male exercise profiles',
      (tester) async {
    final unknownProvider = UserProvider()..setDemoUser();
    await tester.pumpWidget(_screen(unknownProvider));
    await _choose(tester, 'Tập luyện');
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await tester.drag(
        find.byType(SingleChildScrollView).first, const Offset(0, -1800));
    await tester.pumpAndSettle();
    expect(
        find.text(
            'Thông tin thai kỳ có liên quan đến việc tập luyện của bạn không?'),
        findsNothing);

    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();

    final maleProvider = UserProvider()..setDemoUser();
    await maleProvider.updateProfile(
      maleProvider.currentUser!.copyWith(gender: 'male'),
    );
    await tester.pumpWidget(_screen(maleProvider));
    await _choose(tester, 'Tập luyện');
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await tester.drag(
        find.byType(SingleChildScrollView).first, const Offset(0, -1800));
    await tester.pumpAndSettle();
    expect(
        find.text(
            'Thông tin thai kỳ có liên quan đến việc tập luyện của bạn không?'),
        findsNothing);
  });

  testWidgets(
      'female nutrition-only account can save without hidden pregnancy answers',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    await provider
        .updateProfile(provider.currentUser!.copyWith(gender: 'female'));
    await tester.pumpWidget(_screen(provider));
    await _choose(tester, 'Ăn uống & dinh dưỡng');
    await tester.scrollUntilVisible(
      find.byKey(const Key('health-wizard-next')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await _choose(tester, 'Lưu và tiếp tục');
    await tester.pumpAndSettle();
    expect(provider.currentUser?.healthProfile?.primarySupport, 'NUTRITION');
    expect(provider.currentUser?.workoutProfile, isNull);
    expect(
        find.text(
            'Thông tin thai kỳ có liên quan đến việc tập luyện của bạn không?'),
        findsNothing);
  });

  testWidgets('pregnancy is shown only for explicitly female exercise profile',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    await provider.updateProfile(
      provider.currentUser!.copyWith(gender: 'female'),
    );

    await tester.pumpWidget(_screen(provider));
    await _choose(tester, 'Tập luyện');
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await tester.drag(
        find.byType(SingleChildScrollView).first, const Offset(0, -1800));
    await tester.pumpAndSettle();

    expect(
        find.text(
            'Thông tin thai kỳ có liên quan đến việc tập luyện của bạn không?'),
        findsOneWidget);
  });
}
