import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/models/exercise_model.dart';
import 'package:health_app/services/exercise_cache_service.dart';

ExerciseModel _exercise(String id, String userId, DateTime date) {
  return ExerciseModel(
    id: id,
    userId: userId,
    name: 'Running',
    date: date,
    duration: 30,
    caloriesBurned: 250,
    type: 'cardio',
  );
}

void main() {
  final cache = ExerciseCacheService();

  setUp(cache.clearAllCache);
  tearDown(cache.clearAllCache);

  test('returns defensive lists and deduplicates optimistic additions', () {
    final date = DateTime(2026, 8, 13);
    final exercise = _exercise('one', 'user', date);

    cache.cacheExercises('user', date, [exercise]);
    cache.addExerciseToCache('user', date, exercise);

    final cached = cache.getCachedExercises('user', date)!;
    expect(cached, hasLength(1));
    expect(() => cached.add(exercise), throwsUnsupportedError);
  });

  test('clearing one user does not clear users with the same prefix', () {
    final date = DateTime(2026, 8, 13);
    cache.cacheExercises('ann', date, [_exercise('a', 'ann', date)]);
    cache.cacheExercises('anna', date, [_exercise('b', 'anna', date)]);

    cache.clearUserCache('ann');

    expect(cache.getCachedExercises('ann', date), isNull);
    expect(cache.getCachedExercises('anna', date), hasLength(1));
  });

  test('all-exercises history cache is copied and read-only', () {
    final date = DateTime(2026, 8, 13);
    final source = [_exercise('one', 'user', date)];
    cache.cacheAllExercises('user', source);
    source.clear();

    final cached = cache.getAllCachedExercises('user')!;
    expect(cached, hasLength(1));
    expect(() => cached.clear(), throwsUnsupportedError);
  });
}
