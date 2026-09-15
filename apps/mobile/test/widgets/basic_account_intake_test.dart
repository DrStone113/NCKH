import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/auth/screens/auth_wrapper.dart';
import 'package:health_app/features/auth/screens/workout_account_intake_screen.dart';
import 'package:health_app/features/settings/screens/profile_settings_screen.dart';
import 'package:health_app/models/user_model.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:provider/provider.dart';

class _RetryProfileProvider extends UserProvider {
  bool failWrites = false;

  @override
  Future<void> updateProfile(UserModel updatedUser) async {
    if (failWrites) throw StateError('test persistence failure');
    await super.updateProfile(updatedUser);
  }
}

Future<void> _open(WidgetTester tester, UserProvider provider) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  provider.setDemoUser();
  await provider.updateProfile(UserModel.newAccount(
    id: 'demo',
    email: 'new@example.com',
  ));
  await tester.pumpWidget(ChangeNotifierProvider<UserProvider>.value(
    value: provider,
    child: const MaterialApp(home: AuthWrapper()),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Bắt đầu'));
  await tester.pumpAndSettle();
}

Future<void> _text(WidgetTester tester, String key, String value) async {
  final field = find.byKey(Key(key));
  await tester.ensureVisible(field);
  await tester.enterText(field, value);
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String key, String label) async {
  await tester.ensureVisible(find.byKey(Key(key)));
  await tester.tap(find.byKey(Key(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

Future<void> _answer(WidgetTester tester) async {
  await _text(tester, 'profile-name', 'Nguyễn An');
  await _text(tester, 'profile-age', '29');
  await _select(tester, 'profile-gender', 'Nữ');
  await _text(tester, 'profile-height', '165,5');
  await _text(tester, 'profile-weight', '57,25');
  await tester.tap(find.byKey(const Key('profile-save')));
  await tester.pumpAndSettle();
  await _select(tester, 'profile-activity', 'Vận động nhẹ (1–3 buổi/tuần)');
  await tester.ensureVisible(find.text('Duy trì cân nặng'));
  await tester.tap(find.text('Duy trì cân nặng'));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('profile-save')));
  await tester.pumpAndSettle();
  FocusManager.instance.primaryFocus?.unfocus();
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
      'new account asks all basic fields and rejects a blank submission',
      (tester) async {
    final provider = UserProvider();
    await _open(tester, provider);
    expect(find.text('Cho mình biết thêm về bạn'), findsOneWidget);
    for (final key in [
      'profile-name',
      'profile-age',
      'profile-height',
      'profile-weight'
    ]) {
      expect(
          tester.widget<TextFormField>(find.byKey(Key(key))).controller!.text,
          isEmpty);
    }
    expect(find.byKey(const Key('profile-gender')), findsOneWidget);
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    expect(provider.needsBasicProfileIntake, isTrue);
    expect(provider.currentUser!.basicProfileCompletedAt, isNull);
    expect(find.byKey(const Key('profile-save-error')), findsOneWidget);
    expect(find.byType(WorkoutAccountIntakeScreen), findsNothing);
  });

  testWidgets('save keeps exact measurements and advances to domain intake',
      (tester) async {
    final provider = UserProvider();
    await _open(tester, provider);
    await _answer(tester);
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    final saved = UserModel.fromMap(provider.currentUser!.toMap());
    expect(saved.name, 'Nguyễn An');
    expect(saved.age, 29);
    expect(saved.gender, 'female');
    expect(saved.height, 165.5);
    expect(saved.weight, 57.25);
    expect(saved.equationSex, isNull);
    expect(saved.needsBasicProfileIntake, isFalse);
    expect(find.byType(WorkoutAccountIntakeScreen), findsOneWidget);
    expect(find.byType(ProfileSettingsScreen), findsNothing);
  });

  testWidgets(
      'failed persistence keeps onboarding and entered data until retry succeeds',
      (tester) async {
    final provider = _RetryProfileProvider();
    await _open(tester, provider);
    await _answer(tester);
    provider.failWrites = true;
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('profile-save-error')), findsOneWidget);
    expect(provider.currentUser!.basicProfileCompletedAt, isNull);
    expect(
        tester
            .widget<TextFormField>(
                find.byKey(const Key('profile-weight'), skipOffstage: false))
            .controller!
            .text,
        '57,25');
    expect(find.byType(WorkoutAccountIntakeScreen), findsNothing);
    provider.failWrites = false;
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    expect(provider.needsBasicProfileIntake, isFalse);
    expect(find.byType(WorkoutAccountIntakeScreen), findsOneWidget);
  });

  testWidgets('male profile does not ask pregnancy or lactation',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    await provider.updateProfile(
      provider.currentUser!.copyWith(gender: 'male'),
    );
    await tester.pumpWidget(ChangeNotifierProvider<UserProvider>.value(
      value: provider,
      child: const MaterialApp(home: ProfileSettingsScreen()),
    ));

    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();

    expect(find.text('Đang mang thai'), findsNothing);
    expect(find.text('Đang cho con bú'), findsNothing);
    expect(
        find.text('Có nguy cơ hoặc tiền sử rối loạn ăn uống'), findsOneWidget);
  });

  testWidgets('female profile still asks pregnancy and lactation',
      (tester) async {
    final provider = UserProvider()..setDemoUser();
    addTearDown(provider.dispose);
    await provider.updateProfile(
      provider.currentUser!.copyWith(gender: 'female'),
    );
    await tester.pumpWidget(ChangeNotifierProvider<UserProvider>.value(
      value: provider,
      child: const MaterialApp(home: ProfileSettingsScreen()),
    ));

    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();

    expect(find.text('Đang mang thai'), findsOneWidget);
    expect(find.text('Đang cho con bú'), findsOneWidget);
  });
}
