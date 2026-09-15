import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'dart:convert';
import 'package:health_app/services/wger_service.dart';

void main() {
  group('WgerService', () {
    test('fetchExercises returns WgerExerciseListResponse on success',
        () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          json.encode({
            'count': 1,
            'next': null,
            'results': [
              {
                'id': 1,
                'name': 'Push-up',
                'description': 'A basic exercise',
                'category_name': 'Strength',
                'muscles': [],
                'muscles_secondary': [],
                'equipment': [],
              }
            ]
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final response = await service.fetchExercises();

      expect(response.count, 1);
      expect(response.results.length, 1);
      expect(response.results[0].name, 'Push-up');
    });

    test('fetchExercises throws WgerApiException on non-200 status', () async {
      final mockClient = MockClient((request) async {
        return http.Response('Not Found', 404);
      });

      final service = WgerService(client: mockClient);

      expect(
        () => service.fetchExercises(),
        throwsA(isA<WgerApiException>()),
      );
    });

    test('fetchExerciseDetail returns WgerExercise on success', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          json.encode({
            'id': 1,
            'name': 'Push-up',
            'description': 'A basic exercise',
            'category_name': 'Strength',
            'muscles': [],
            'muscles_secondary': [],
            'equipment': [],
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final exercise = await service.fetchExerciseDetail(1);

      expect(exercise.id, 1);
      expect(exercise.name, 'Push-up');
    });

    test('searchIngredients returns WgerIngredientListResponse on success',
        () async {
      final mockClient = MockClient((request) async {
        expect(request.url.path, '/wger/ingredient/');
        expect(request.url.queryParameters['name'], 'chicken');
        expect(request.url.queryParameters['page'], '1');
        return http.Response(
          json.encode({
            'count': 1,
            'next': null,
            'results': [
              {
                'id': 1,
                'name': 'Chicken Breast',
                'energy': 165.0,
                'protein': 31.0,
                'carbohydrates': 0.0,
                'fat': 3.6,
              }
            ]
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final response = await service.searchIngredients('chicken');

      expect(response.count, 1);
      expect(response.results.length, 1);
      expect(response.results[0].name, 'Chicken Breast');
    });

    test('fetchExerciseCategories returns list on success', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          json.encode({
            'results': [
              {'id': 1, 'name': 'Strength'},
              {'id': 2, 'name': 'Cardio'},
            ]
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final categories = await service.fetchExerciseCategories();

      expect(categories.length, 2);
      expect(categories[0].name, 'Strength');
    });

    test('fetchMuscles returns list on success', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          json.encode({
            'results': [
              {'id': 1, 'name_en': 'Chest', 'is_front': true},
              {'id': 2, 'name_en': 'Back', 'is_front': false},
            ]
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final muscles = await service.fetchMuscles();

      expect(muscles.length, 2);
      expect(muscles[0].nameEn, 'Chest');
    });

    test('fetchEquipment returns list on success', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          json.encode({
            'results': [
              {'id': 1, 'name': 'Barbell'},
              {'id': 2, 'name': 'Dumbbell'},
            ]
          }),
          200,
        );
      });

      final service = WgerService(client: mockClient);
      final equipment = await service.fetchEquipment();

      expect(equipment.length, 2);
      expect(equipment[0].name, 'Barbell');
    });

    test('WgerApiException contains Vietnamese error message', () {
      final exception =
          WgerApiException('Không thể tải dữ liệu', statusCode: 500);

      expect(exception.message, contains('Không thể'));
      expect(exception.statusCode, 500);
    });
  });
}
