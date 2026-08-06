import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/wger_models.dart';

void main() {
  group('WgerMuscle', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'id': 1,
        'name_en': 'Biceps',
        'is_front': true,
      };

      final muscle = WgerMuscle.fromJson(json);
      expect(muscle.id, 1);
      expect(muscle.nameEn, 'Biceps');
      expect(muscle.isFront, true);

      final outputJson = muscle.toJson();
      expect(outputJson['id'], 1);
      expect(outputJson['name_en'], 'Biceps');
      expect(outputJson['is_front'], true);
    });
  });

  group('WgerEquipment', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'id': 1,
        'name': 'Barbell',
      };

      final equipment = WgerEquipment.fromJson(json);
      expect(equipment.id, 1);
      expect(equipment.name, 'Barbell');

      final outputJson = equipment.toJson();
      expect(outputJson['id'], 1);
      expect(outputJson['name'], 'Barbell');
    });
  });

  group('WgerExercise', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'id': 1,
        'name': 'Bench Press',
        'description': 'A chest exercise',
        'category_name': 'Strength',
        'muscles': [
          {'id': 1, 'name_en': 'Pectoralis major', 'is_front': true}
        ],
        'muscles_secondary': [],
        'equipment': [
          {'id': 1, 'name': 'Barbell'}
        ],
        'image_url': 'https://example.com/image.jpg',
      };

      final exercise = WgerExercise.fromJson(json);
      expect(exercise.id, 1);
      expect(exercise.name, 'Bench Press');
      expect(exercise.description, 'A chest exercise');
      expect(exercise.categoryName, 'Strength');
      expect(exercise.muscles.length, 1);
      expect(exercise.equipment.length, 1);
      expect(exercise.imageUrl, 'https://example.com/image.jpg');

      final outputJson = exercise.toJson();
      expect(outputJson['id'], 1);
      expect(outputJson['name'], 'Bench Press');
    });
  });

  group('WgerIngredient', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'id': 1,
        'name': 'Chicken Breast',
        'energy': 165.0,
        'protein': 31.0,
        'carbohydrates': 0.0,
        'fat': 3.6,
      };

      final ingredient = WgerIngredient.fromJson(json);
      expect(ingredient.id, 1);
      expect(ingredient.name, 'Chicken Breast');
      expect(ingredient.energy, 165.0);
      expect(ingredient.protein, 31.0);
      expect(ingredient.carbohydrates, 0.0);
      expect(ingredient.fat, 3.6);

      final outputJson = ingredient.toJson();
      expect(outputJson['id'], 1);
      expect(outputJson['name'], 'Chicken Breast');
    });

    test('macro calculation methods should work correctly', () {
      final ingredient = WgerIngredient(
        id: 1,
        name: 'Chicken Breast',
        energy: 165.0,
        protein: 31.0,
        carbohydrates: 0.0,
        fat: 3.6,
      );

      // Test for 200g
      expect(ingredient.caloriesForGrams(200), 330.0);
      expect(ingredient.proteinForGrams(200), 62.0);
      expect(ingredient.carbsForGrams(200), 0.0);
      expect(ingredient.fatForGrams(200), 7.2);

      // Test for 100g (should equal the per100g values)
      expect(ingredient.caloriesForGrams(100), 165.0);
      expect(ingredient.proteinForGrams(100), 31.0);
      expect(ingredient.carbsForGrams(100), 0.0);
      expect(ingredient.fatForGrams(100), 3.6);
    });

    test('should handle null macro values', () {
      final ingredient = WgerIngredient(
        id: 1,
        name: 'Unknown Food',
      );

      expect(ingredient.caloriesForGrams(100), 0.0);
      expect(ingredient.proteinForGrams(100), 0.0);
      expect(ingredient.carbsForGrams(100), 0.0);
      expect(ingredient.fatForGrams(100), 0.0);
    });
  });

  group('WgerExerciseListResponse', () {
    test('fromJson should work correctly', () {
      final json = {
        'count': 100,
        'next': 'https://wger.de/api/v2/exerciseinfo/?page=2',
        'results': [
          {
            'id': 1,
            'name': 'Push-up',
            'description': 'A bodyweight exercise',
            'category_name': 'Strength',
            'muscles': [],
            'muscles_secondary': [],
            'equipment': [],
          }
        ],
      };

      final response = WgerExerciseListResponse.fromJson(json);
      expect(response.count, 100);
      expect(response.next, 'https://wger.de/api/v2/exerciseinfo/?page=2');
      expect(response.results.length, 1);
      expect(response.results[0].name, 'Push-up');
    });
  });

  group('WgerIngredientListResponse', () {
    test('fromJson should work correctly', () {
      final json = {
        'count': 50,
        'next': null,
        'results': [
          {
            'id': 1,
            'name': 'Apple',
            'energy': 52.0,
            'protein': 0.3,
            'carbohydrates': 14.0,
            'fat': 0.2,
          }
        ],
      };

      final response = WgerIngredientListResponse.fromJson(json);
      expect(response.count, 50);
      expect(response.next, null);
      expect(response.results.length, 1);
      expect(response.results[0].name, 'Apple');
    });
  });

  group('ActionItem', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'kind': 'exercise',
        'wger_id': 192,
        'name': 'Bench Press',
        'details': {
          'duration': 45,
          'calories_burned': 200,
          'type': 'strength',
        },
      };

      final action = ActionItem.fromJson(json);
      expect(action.kind, 'exercise');
      expect(action.wgerId, 192);
      expect(action.name, 'Bench Press');
      expect(action.details['duration'], 45);

      final outputJson = action.toJson();
      expect(outputJson['kind'], 'exercise');
      expect(outputJson['wger_id'], 192);
    });
  });

  group('StructuredResponse', () {
    test('fromJson and toJson should work correctly', () {
      final json = {
        'type': 'structured',
        'text': 'Here are some exercises for you',
        'actions': [
          {
            'kind': 'exercise',
            'wger_id': 192,
            'name': 'Bench Press',
            'details': {'duration': 45},
          }
        ],
      };

      final response = StructuredResponse.fromJson(json);
      expect(response.type, 'structured');
      expect(response.text, 'Here are some exercises for you');
      expect(response.actions.length, 1);
      expect(response.actions[0].name, 'Bench Press');

      final outputJson = response.toJson();
      expect(outputJson['type'], 'structured');
      expect(outputJson['actions'].length, 1);
    });
  });
}
