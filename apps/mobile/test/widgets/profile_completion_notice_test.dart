import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/auth/screens/workout_account_intake_screen.dart';
import 'package:health_app/features/settings/screens/profile_settings_screen.dart';
import 'package:health_app/models/profile_readiness.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:health_app/widgets/profile_completion_notice.dart';
import 'package:provider/provider.dart';
import '../profile_readiness_test.dart' show completeUser;

void main() {
  testWidgets('checklist opens food form and updates after successful save',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    await provider.updateProfile(completeUser().copyWith(id: 'demo'));
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: provider,
      child: const MaterialApp(
          home: Scaffold(
              body: ProfileCompletionNotice(
        scope: ProfileContextScope.nutrition,
      ))),
    ));
    await tester.tap(find.byKey(const Key('complete-chat-profile')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dị ứng thực phẩm (kể cả xác nhận không có)'));
    await tester.pumpAndSettle();
    expect(find.byType(WorkoutAccountIntakeScreen), findsOneWidget);
    for (final label in [
      'Không có dị ứng đã biết',
      'Không có hạn chế ăn uống',
      'Tiếp tục'
    ]) {
      await tester.scrollUntilVisible(find.text(label), 250,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    expect(find.byType(WorkoutAccountIntakeScreen), findsNothing);
    await tester.tap(find.byKey(const Key('complete-chat-profile')));
    await tester.pumpAndSettle();
    expect(
        find.text('Dị ứng thực phẩm (kể cả xác nhận không có)'), findsNothing);
    await tester.tap(
        find.text('Thông tin ước tính năng lượng (cần để lập kế hoạch)'));
    await tester.pumpAndSettle();
    expect(find.byType(ProfileSettingsScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('read errors remain visible even if cached account is complete',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    await provider.updateProfile(completeUser().copyWith(id: 'demo'));
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: provider,
      child: const MaterialApp(
          home: Scaffold(
              body: ProfileCompletionNotice(
        scope: ProfileContextScope.general,
        issue: 'Chưa đọc được hồ sơ mới nhất.',
      ))),
    ));
    expect(find.text('Chưa đọc được hồ sơ mới nhất.'), findsOneWidget);
    expect(find.byKey(const Key('complete-chat-profile')), findsNothing);
  });
}
