import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/wger_models.dart';
import 'package:health_app/widgets/action_card_widget.dart';

void main() {
  group('ActionCardWidget', () {
    testWidgets('renders exercise action card correctly', (WidgetTester tester) async {
      // Arrange
      final exerciseAction = ActionItem(
        kind: 'exercise',
        wgerId: 123,
        name: 'Push-ups',
        details: {
          'duration': 30,
          'calories_burned': 150,
          'type': 'strength',
        },
      );

      bool savePressed = false;
      bool detailPressed = false;

      // Act
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionCardWidget(
              action: exerciseAction,
              onSaveToJournal: () => savePressed = true,
              onViewDetail: () => detailPressed = true,
            ),
          ),
        ),
      );

      // Assert
      expect(find.text('Push-ups'), findsOneWidget);
      expect(find.text('30 phút'), findsOneWidget);
      expect(find.text('150 kcal'), findsOneWidget);
      expect(find.text('strength'), findsOneWidget);
      expect(find.byIcon(Icons.fitness_center), findsOneWidget);
      expect(find.text('Lưu vào nhật ký'), findsOneWidget);
      expect(find.text('Xem chi tiết'), findsOneWidget);

      // Test button callbacks
      await tester.tap(find.text('Lưu vào nhật ký'));
      await tester.pump();
      expect(savePressed, true);

      await tester.tap(find.text('Xem chi tiết'));
      await tester.pump();
      expect(detailPressed, true);
    });

    testWidgets('renders food action card correctly', (WidgetTester tester) async {
      // Arrange
      final foodAction = ActionItem(
        kind: 'food',
        wgerId: 456,
        name: 'Chicken Breast',
        details: {
          'calories': 165,
          'protein': 31.0,
          'carbs': 0.0,
          'fat': 3.6,
        },
      );

      // Act
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionCardWidget(
              action: foodAction,
              onSaveToJournal: () {},
              onViewDetail: () {},
            ),
          ),
        ),
      );

      // Assert
      expect(find.text('Chicken Breast'), findsOneWidget);
      expect(find.text('165 kcal'), findsOneWidget);
      expect(find.text('P: 31g'), findsOneWidget);
      expect(find.text('C: 0g'), findsOneWidget);
      expect(find.text('F: 3.6g'), findsOneWidget);
      expect(find.byIcon(Icons.restaurant), findsOneWidget);
    });

    testWidgets('handles null details gracefully', (WidgetTester tester) async {
      // Arrange
      final actionWithNullDetails = ActionItem(
        kind: 'exercise',
        wgerId: 789,
        name: 'Running',
        details: {},
      );

      // Act
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionCardWidget(
              action: actionWithNullDetails,
              onSaveToJournal: () {},
              onViewDetail: () {},
            ),
          ),
        ),
      );

      // Assert - should render without crashing
      expect(find.text('Running'), findsOneWidget);
      expect(find.byIcon(Icons.fitness_center), findsOneWidget);
    });

    testWidgets('formats numbers correctly', (WidgetTester tester) async {
      // Arrange
      final foodAction = ActionItem(
        kind: 'food',
        wgerId: 999,
        name: 'Test Food',
        details: {
          'calories': 100,
          'protein': 25.5,
          'carbs': 10.0,
          'fat': 5.25,
        },
      );

      // Act
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionCardWidget(
              action: foodAction,
              onSaveToJournal: () {},
              onViewDetail: () {},
            ),
          ),
        ),
      );

      // Assert
      expect(find.text('100 kcal'), findsOneWidget);
      expect(find.text('P: 25.5g'), findsOneWidget);
      expect(find.text('C: 10g'), findsOneWidget);
      expect(find.text('F: 5.3g'), findsOneWidget); // Rounded to 1 decimal
    });
  });
}
