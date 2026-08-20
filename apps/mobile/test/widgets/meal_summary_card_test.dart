import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/widgets/meal_summary_card.dart';

void main() {
  testWidgets('renders the same compact meal summary used by chat and diary',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 360,
            child: MealSummaryCard(
              name: 'Bún cá',
              mealType: 'lunch',
              ingredients: [
                MealCardIngredientView(
                  name: 'Bún',
                  grams: 200,
                  calories: 300,
                ),
                MealCardIngredientView(
                  name: 'Cá rô phi',
                  grams: 120,
                  calories: 200,
                ),
              ],
              calories: 500,
              protein: 28,
              carbs: 55,
              fat: 12,
              actionLabel: 'Lưu vào nhật ký',
              onAction: _noop,
            ),
          ),
        ),
      ),
    );

    expect(find.text('Bún cá'), findsOneWidget);
    expect(find.textContaining('Bữa trưa · 2 thành phần'), findsOneWidget);
    expect(find.text('~500'), findsOneWidget);
    expect(find.text('Lưu vào nhật ký'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

void _noop() {}
