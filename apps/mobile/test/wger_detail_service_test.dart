import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/services/wger_detail_service.dart';

void main() {
  test('exercise detail tolerates loose wger JSON types', () {
    final detail = ExerciseDetail.fromJson({
      'id': '15',
      'name': 'Bench press',
      'description': 'Press with control',
      'category': 'Chest',
      'muscles': [
        {'id': '4', 'name_en': 'Chest', 'is_front': true},
        'invalid',
      ],
      'muscles_secondary': null,
      'equipment': ['Barbell', 42],
    });

    expect(detail.id, 15);
    expect(detail.muscles.single.id, 4);
    expect(detail.equipment, ['Barbell', '42']);
  });

  test('ingredient detail parses numeric strings safely', () {
    final detail = IngredientDetail.fromJson({
      'id': '7',
      'name': 'Apple',
      'energy': '52.3',
      'protein': '0.3',
      'weight_units': [
        {'id': '2', 'gram': '150', 'name': 'piece'},
      ],
    });

    expect(detail.id, 7);
    expect(detail.energy, 52.3);
    expect(detail.protein, 0.3);
    expect(detail.weightUnits.single.gram, 150);
  });
}
