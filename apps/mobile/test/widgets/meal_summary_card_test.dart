import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/widgets/meal_summary_card.dart';

void main() {
  test('uses a dish-specific icon instead of the generic restaurant icon', () {
    expect(MealPresentation.dishIcon('Pizza'), Icons.local_pizza_outlined);
    expect(
        MealPresentation.dishIcon('Bò bít tết'), Icons.outdoor_grill_outlined);
    expect(
        MealPresentation.dishIcon('Cá hồi áp chảo'), Icons.set_meal_outlined);
    expect(MealPresentation.dishIcon('Gà nướng'), Icons.fastfood_outlined);
  });

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
    expect(find.text('kcal'), findsOneWidget);
    expect(find.text('Lưu vào nhật ký'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('renders the pizza icon on a pizza summary card', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MealSummaryCard(
            name: 'Pizza',
            mealType: 'lunch',
            ingredients: [
              MealCardIngredientView(
                name: 'Pizza',
                grams: 100,
                calories: 150,
              ),
            ],
            calories: 150,
            protein: 5,
            carbs: 25,
            fat: 3,
          ),
        ),
      ),
    );

    expect(find.text('🍕'), findsOneWidget);
    expect(find.byIcon(Icons.restaurant_outlined), findsNothing);
  });
}

void _noop() {}
