import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/settings/screens/account_settings_screen.dart';
import 'package:health_app/providers/proactive_provider.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('settings exposes real actions and updates demo profile', (
    tester,
  ) async {
    final userProvider = UserProvider()..setDemoUser();
    final proactiveProvider = ProactiveProvider();

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<UserProvider>.value(value: userProvider),
          ChangeNotifierProvider<ProactiveProvider>.value(
            value: proactiveProvider,
          ),
        ],
        child: const MaterialApp(home: AccountSettingsScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('Thông tin cá nhân'), findsOneWidget);
    expect(find.text('Nhắc nhở sức khỏe'), findsOneWidget);
    expect(find.text('Mở trợ lý AI'), findsOneWidget);

    await tester.tap(find.text('Thông tin cá nhân'));
    await tester.pumpAndSettle();
    expect(find.byType(TextFormField), findsAtLeastNWidgets(5));

    await tester.enterText(find.byType(TextFormField).first, 'Nguyễn Văn B');
    await tester.ensureVisible(find.text('Lưu thay đổi'));
    await tester.tap(find.text('Lưu thay đổi'));
    await tester.pumpAndSettle();

    expect(userProvider.currentUser?.name, 'Nguyễn Văn B');
    expect(find.byType(AccountSettingsScreen), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('Lịch sử hội thoại'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Lịch sử hội thoại'), findsOneWidget);
  });
}
