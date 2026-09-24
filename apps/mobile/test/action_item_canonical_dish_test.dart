import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/wger_models.dart';

void main() {
  test('canonical dish action remains one card instead of component expansion', () {
    final actions = ActionItem.parseActions([
      {
        'kind': 'food',
        'name': 'Cơm tấm sườn',
        'details': {
          'dish_name': 'Cơm tấm sườn',
          'catalog_dish_id': 'dish-42',
          'meal_type': 'dinner',
          'serving_grams': 400,
          'calories': 650,
          'components': [
            {'name': 'Cơm', 'serving_grams': 240},
            {'name': 'Thịt heo', 'serving_grams': 120},
          ],
        },
      },
    ]);

    expect(actions, hasLength(1));
    expect(actions.single.name, 'Cơm tấm sườn');
    expect(actions.single.details['dish_name'], 'Cơm tấm sườn');
  });
}
