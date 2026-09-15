import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:health_app/models/canonical_nutrition.dart';
import 'package:health_app/models/app_state_value.dart';
import 'package:health_app/models/meal_model.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:health_app/providers/nutrition_provider.dart';
import 'package:health_app/features/settings/screens/profile_settings_screen.dart';
import 'package:health_app/features/auth/screens/workout_account_intake_screen.dart';
import 'package:health_app/features/nutrition/screens/nutrition_screen.dart';
import 'package:health_app/features/nutrition/widgets/nutrition_overview.dart';
import 'package:health_app/features/nutrition/widgets/meal_plan_card.dart';
import 'package:health_app/features/plans/plan_snapshot.dart';
import 'package:health_app/features/plans/screens/plan_detail_screen.dart';
import 'package:health_app/features/plans/widgets/planned_day_plan_section.dart';
import 'package:health_app/widgets/profile_wizard.dart';
import 'package:health_app/widgets/health_surface.dart';
import 'package:health_app/widgets/recommendation_feedback_bar.dart';
import 'package:health_app/theme/app_theme.dart';

// SYNTHETIC_DEVELOPMENT fixtures. No Firebase or recommendation writes.
final day = DateTime(2026, 9, 8);
const lunch = <String, dynamic>{
  'item_id': 'exact-item-123',
  'dish_id': 'exact-dish-456',
  'slot': 'lunch',
  'dish_name': 'Cơm gà áp chảo',
  'nutrition': {
    'total_calories': 520,
    'total_protein': 38,
    'total_carbs': 62,
    'total_fat': 14
  },
  'content': {
    'serving_grams': 350,
    'ingredients': [
      {'name': 'Thịt gà', 'grams': 150},
      {'name': 'Cơm', 'grams': 200}
    ]
  }
};
final plan = <String, dynamic>{
  'plan_id': 'synthetic-ui-plan',
  'revision_id': 'exact-revision',
  'revision_number': 1,
  'domain': 'NUTRITION',
  'lifecycle_status': 'SAVED',
  'valid_lifecycle_targets': <String>[],
  'days': [
    {
      'date': '2026-09-08',
      'items': [
        lunch,
        {
          ...lunch,
          'item_id': 'breakfast-id',
          'slot': 'breakfast',
          'dish_name': 'Cháo thịt bằm'
        }
      ]
    },
    {
      'date': '2026-09-09',
      'items': [lunch]
    },
  ]
};
const canonical = CanonicalNutritionState(
    status: CanonicalNutritionStatus.ready,
    calorieTargetKcalPerDay: 2000,
    carbohydrateRangeGramsPerDay: NutritionRange(225, 325),
    fatRangeGramsPerDay: NutritionRange(44, 78),
    protein: ProteinPolicyResult(
        branch: 'fixture',
        recommendedGramsPerKg: NutritionRange(1, 2),
        planningGramsPerKg: 1.5,
        referenceMinimumGramsPerDay: 50,
        recommendedGramsPerDay: NutritionRange(60, 120),
        planningGramsPerDay: 90));
DailyNutritionSummary summary(
        [NutritionInputStatus status = NutritionInputStatus.known]) =>
    summarizeDailyNutrition(
        CanonicalNutritionValue(
            value: status == NutritionInputStatus.known
                ? const [
                    ConsumedMealNutrition(
                        energyKcal: 753,
                        proteinGrams: 42,
                        carbohydrateGrams: 95,
                        fatGrams: 21,
                        recordStatus: 'CONSUMED'),
                    ConsumedMealNutrition(
                        energyKcal: 900,
                        proteinGrams: 60,
                        carbohydrateGrams: 130,
                        fatGrams: 30,
                        recordStatus: 'PLANNED')
                  ]
                : null,
            source: 'SYNTHETIC_DEVELOPMENT',
            status: status),
        canonical);

class FixtureNutrition extends NutritionProvider {
  int mutations = 0;
  @override
  DateTime get selectedDate => day;
  @override
  bool get isToday => false;
  @override
  bool get isLoading => false;
  @override
  DataStatus get todayMealsStatus => DataStatus.known;
  @override
  List<MealModel> get todayMeals => [
        MealModel(
            id: 'actual-id',
            userId: 'demo',
            name: 'Bữa ăn đã ghi nhận',
            date: day,
            mealType: 'breakfast',
            isCompleted: true,
            items: [
              MealItem(
                  id: 'fixture-item',
                  foodId: 'fixture-food',
                  name: 'Bữa sáng',
                  weightGrams: 350,
                  calories: 753,
                  protein: 42,
                  carbs: 95,
                  fat: 21)
            ])
      ];
  @override
  int get completedMealsCount => 1;
  @override
  int get pendingMealsCount => 0;
  @override
  DailyNutritionSummary canonicalDailySummary(
          CanonicalNutritionState canonical) =>
      summary();
  @override
  Future<void> loadTodayMeals(String userId) async {}
  @override
  Future<void> loadMealsForDate(String userId, DateTime date) async {}
  @override
  Future<void> toggleMealCompleted(String id) async {
    mutations++;
  }
}

final captureKey = GlobalKey();
Widget app(Widget screen,
        {UserProvider? users, NutritionProvider? nutrition}) =>
    MultiProvider(
        providers: [
          if (users != null)
            ChangeNotifierProvider<UserProvider>.value(value: users),
          if (nutrition != null)
            ChangeNotifierProvider<NutritionProvider>.value(value: nutrition),
          Provider<Object>.value(value: Object()),
        ],
        child: MaterialApp(
            theme: ThemeData(
                useMaterial3: true,
                fontFamily: 'Roboto',
                filledButtonTheme: FilledButtonThemeData(
                    style: FilledButton.styleFrom(
                        minimumSize: const Size(48, 52),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18)))),
                outlinedButtonTheme: OutlinedButtonThemeData(
                    style: OutlinedButton.styleFrom(
                        minimumSize: const Size(48, 48),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18)))),
                scaffoldBackgroundColor: AppColors.background,
                colorScheme: ColorScheme.fromSeed(
                    seedColor: AppColors.primary, primary: AppColors.primary),
                inputDecorationTheme: InputDecorationTheme(
                    filled: true,
                    fillColor: Colors.white,
                    border:
                        OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
                    contentPadding: const EdgeInsets.all(18))),
            builder: (context, child) => RepaintBoundary(key: captureKey, child: child!),
            home: screen));

Future<void> capture(WidgetTester tester, String name) async {
  await tester.pumpAndSettle();
  await tester.runAsync(() async {
    final boundary =
        captureKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 1);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final dir = Directory('build/ui_redesign')..createSync(recursive: true);
    File('${dir.path}/$name.png').writeAsBytesSync(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  setUpAll(() async {
    for (final entry in {
      'MaterialIcons':
          '.fvm/flutter_sdk/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
      'Segoe UI Emoji': 'C:/Windows/Fonts/seguiemj.ttf'
    }.entries) {
      final font = File(entry.value);
      if (font.existsSync()) {
        await (FontLoader(entry.key)
              ..addFont(
                  Future.value(ByteData.sublistView(font.readAsBytesSync()))))
            .load();
      }
    }

    final font = File('C:/Windows/Fonts/arial.ttf');
    if (font.existsSync()) {
      final loader = FontLoader('Roboto')
        ..addFont(Future.value(ByteData.sublistView(font.readAsBytesSync())));
      await loader.load();
    }
  });
  for (final size in [
    const Size(360, 640),
    const Size(390, 844),
    const Size(430, 932)
  ]) {
    testWidgets('responsive welcome and nutrition ${size.width}',
        (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester
          .pumpWidget(app(Scaffold(body: ProfileWelcome(onStart: () {}))));
      await capture(tester, 'welcome-${size.width.toInt()}');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(app(Scaffold(
          body: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(children: [
                DailyDateStrip(selected: day, onSelected: (_) {}),
                const SizedBox(height: 20),
                NutritionHeroCard(canonical: canonical, summary: summary()),
                const SizedBox(height: 20),
                NutritionMacroSummary(canonical: canonical, summary: summary()),
              ])))));
      await capture(tester, 'nutrition-${size.width.toInt()}');
      expect(find.text('1250'), findsNWidgets(2));
      expect(find.text('42.0 g đã ăn'), findsOneWidget);
      expect(find.text('102.0 g đã ăn'), findsNothing);
      expect(tester.takeException(), isNull);
      final users = UserProvider()..setDemoUser();
      addTearDown(users.dispose);
      await tester.pumpWidget(app(const ProfileSettingsScreen(), users: users));
      await capture(tester, 'basic-${size.width.toInt()}');
      await tester.enterText(
          find.byKey(const Key('profile-name')), 'Nguyễn An');
      tester.view.viewInsets = const FakeViewPadding(bottom: 250);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      tester.view.resetViewInsets();
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpWidget(app(
          const WorkoutAccountIntakeScreen(initialSupport: 'BOTH'),
          users: users));
      await capture(tester, 'nutrition-intake-${size.width.toInt()}');
      await tester.tap(find.byKey(const Key('health-wizard-next')));
      await tester.pumpAndSettle();
      await capture(tester, 'workout-intake-${size.width.toInt()}');
      await tester.tap(find.byKey(const Key('health-wizard-next')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Cần bổ sung:'), findsOneWidget);
      await tester
          .pumpWidget(app(PlanDetailScreen(plan: plan, initialDate: day)));
      await capture(tester, 'daily-${size.width.toInt()}');
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets('wizard draft, unknown and confirmation retain exact input',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final users = UserProvider()..setDemoUser();
    addTearDown(users.dispose);
    await tester.pumpWidget(app(const ProfileSettingsScreen(), users: users));
    // This scenario specifically verifies an explicit maternal safety answer.
    // Select female first because maternal questions are intentionally hidden
    // for male and unspecified profiles.
    await tester.ensureVisible(find.byKey(const Key('profile-gender')));
    await tester.tap(find.byKey(const Key('profile-gender')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nữ').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('profile-name')), 'Nguyễn An');
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    await capture(tester, 'profile-goal');
    await tester.tap(find.text('Quay lại chỉnh sửa'));
    await tester.pumpAndSettle();
    expect(
        tester
            .widget<TextFormField>(find.byKey(const Key('profile-name')))
            .controller!
            .text,
        'Nguyễn An');
    await capture(tester, 'profile-basic');
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    final safety =
        find.byType(DropdownButtonFormField<NutritionSafetyAnswer>).first;
    await tester.ensureVisible(safety);
    await tester.tap(safety);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Không rõ').last);
    await tester.pumpAndSettle();
    await capture(tester, 'profile-safety');
    await tester.tap(find.byKey(const Key('profile-save')));
    await tester.pumpAndSettle();
    expect(find.text('Nguyễn An'), findsOneWidget);
    expect(find.text('Chưa rõ'), findsOneWidget);
    await capture(tester, 'profile-confirmation');
    await tester.tap(find.text('Hoàn tất'));
    await tester.pumpAndSettle();
    expect(users.currentUser!.nutritionSafetyProfile.pregnancy,
        NutritionSafetyAnswer.unknown);
  });
  testWidgets('meal grouping and exact ID action do not log consumption',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    Map<String, dynamic>? selected;
    final items = [
      lunch,
      {...lunch, 'slot': 'breakfast', 'item_id': 'breakfast'}
    ];
    await tester.pumpWidget(app(Scaffold(
        body: SingleChildScrollView(
            child: MealSlotSection(
                items: items, onView: (item) => selected = item)))));
    expect(tester.getTopLeft(find.text('Bữa sáng')).dy,
        lessThan(tester.getTopLeft(find.text('Bữa trưa')).dy));
    await tester
        .ensureVisible(find.byKey(const ValueKey('view-meal-exact-item-123')));
    await tester.tap(find.byKey(const ValueKey('view-meal-exact-item-123')));
    expect(selected, same(lunch));
    expect(selected!['dish_id'], 'exact-dish-456');
    expect(lunch.containsKey('consumed_at'), isFalse);
    await capture(tester, 'meal-slots');
  });
  testWidgets('catalog detail and selection preserve the catalog object',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final dish = {
      'id': 'catalog-exact',
      'name': 'Cơm gà',
      'estimated_calories': 520,
      'ingredients': [
        {'name': 'Gà', 'grams': 150}
      ]
    };
    Map<String, dynamic>? selected;
    await tester.pumpWidget(app(Scaffold(
        body: CatalogDishCard(
            dish: dish, onSelect: (value) => selected = value))));
    await capture(tester, 'meal-selection');
    await tester.tap(find.text('Xem'));
    await tester.pumpAndSettle();
    await capture(tester, 'meal-detail');
    expect(selected, isNull);
    expect(find.text('07:30'), findsNothing);
    Navigator.of(tester.element(find.byType(MealDetailContent))).pop();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chọn'));
    expect(selected, same(dish));
  });
  testWidgets('plan loading empty error and retry have explicit states',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var calls = 0;
    final pending = Completer<List<PlanSnapshot>>();
    await tester.pumpWidget(app(Scaffold(
        body: PlannedDayPlanSection(
            userId: 'demo',
            date: day,
            domain: 'NUTRITION',
            loader: (_) {
              calls++;
              return calls == 1 ? pending.future : Future.value([]);
            }))));
    expect(find.byType(NutritionSkeleton), findsOneWidget);
    await capture(tester, 'plan-loading');
    pending.completeError(StateError('synthetic read failure'));
    await tester.pumpAndSettle();
    expect(find.text('Không thể tải kế hoạch lúc này.'), findsOneWidget);
    await capture(tester, 'plan-error');
    await tester.tap(find.text('Thử lại'));
    await tester.pumpAndSettle();
    expect(find.text('Bạn chưa có kế hoạch ăn cho ngày này.'), findsOneWidget);
    await capture(tester, 'plan-empty');
  });
  testWidgets('unknown summary never becomes zero and feedback is not logging',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final diary = FixtureNutrition();
    addTearDown(diary.dispose);
    var feedback = '';
    await tester.pumpWidget(app(
        Scaffold(
            body: SingleChildScrollView(
                child: Column(children: [
          NutritionHeroCard(
              canonical: canonical,
              summary: summary(NutritionInputStatus.error)),
          RecommendationFeedbackBar(
              onFeedback: (event, reason) async => feedback = event)
        ]))),
        nutrition: diary));
    expect(find.text('0'), findsNothing);
    await tester.tap(find.byKey(const Key('recommendation-like')));
    await tester.pumpAndSettle();
    await capture(tester, 'recommendation-feedback');
    expect(feedback, 'LIKED');
    expect(diary.mutations, 0);
  });
  testWidgets(
      'full today dashboard and daily plan keep planned and actual separate',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final users = UserProvider()..setDemoUser();
    final diary = FixtureNutrition();
    addTearDown(users.dispose);
    addTearDown(diary.dispose);
    await tester.pumpWidget(app(
        NutritionScreen(
            planLoader: (_) async => [
                  PlanSnapshot(plan: plan, sessionId: 'fixture', createdAt: day)
                ]),
        users: users,
        nutrition: diary));
    await capture(tester, 'nutrition-today');
    await tester.scrollUntilVisible(find.text('Cơm gà áp chảo'), 350,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Dự kiến · chưa ghi nhận'), findsWidgets);
    expect(diary.mutations, 0);
    await capture(tester, 'today-plan');
    await tester.pumpWidget(app(PlanDetailScreen(plan: plan, initialDate: day),
        users: users, nutrition: diary));
    await capture(tester, 'daily-plan');
    expect(find.text('Kế hoạch ăn theo ngày'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Tổng quan các ngày'), 350,
        scrollable: find.byType(Scrollable).first);
    await capture(tester, 'weekly-plan');
    expect(diary.mutations, 0);
    await tester.pumpWidget(app(
        const WorkoutAccountIntakeScreen(initialSupport: 'NUTRITION'),
        users: users));
    await capture(tester, 'profile-nutrition');
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await capture(tester, 'profile-workout');
    await tester.tap(find.byKey(const Key('health-wizard-next')));
    await tester.pumpAndSettle();
    await capture(tester, 'health-confirmation');
    expect(tester.takeException(), isNull);
  });
}
