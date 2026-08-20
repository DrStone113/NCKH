import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/services/local_exercise_service.dart';
import 'package:health_app/services/wger_cache_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads and indexes the bundled wger catalog consistently', () async {
    final local = LocalExerciseService();
    final firstLoad = local.loadExercises();
    final concurrentLoad = local.loadExercises();

    expect(identical(firstLoad, concurrentLoad), isTrue);
    await Future.wait([firstLoad, concurrentLoad]);

    expect(local.allExercises, isNotEmpty);
    expect(local.categories, isNotEmpty);
    expect(local.muscles, isNotEmpty);
    expect(local.equipment, isNotEmpty);

    final category = local.categories.first;
    final categoryExercises = local.getByCategoryId(category.id);
    expect(categoryExercises, isNotEmpty);
    expect(
      categoryExercises.every(
        (exercise) => exercise.categoryName == category.name,
      ),
      isTrue,
    );

    final firstExercise = local.allExercises.first;
    expect(local.search(firstExercise.name), contains(firstExercise));
  });

  test('wger cache honors category IDs and exact final-page boundaries',
      () async {
    final cache = WgerCacheService();
    await cache.preFetchData();
    final category = cache.cachedCategories.first;

    final filtered = await cache.getExercises(categoryId: category.id);
    expect(filtered, isNotEmpty);
    expect(filtered.every((exercise) => exercise.categoryName == category.name),
        isTrue);

    final response = await cache.loadMoreExercises(
      page: 1,
      categoryId: category.id,
      pageSize: filtered.length,
    );
    expect(response.results, hasLength(filtered.length));
    expect(response.next, isNull);
  });
}
