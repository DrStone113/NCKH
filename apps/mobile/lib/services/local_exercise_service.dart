import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import '../models/wger_models.dart';
import '../utils/exercise_utils.dart';

int _localInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

/// Service load bài tập từ file JSON local (wger_exercises_raw.json)
/// Không cần gọi API, hoạt động offline hoàn toàn
class LocalExerciseService {
  static final LocalExerciseService _instance =
      LocalExerciseService._internal();
  factory LocalExerciseService() => _instance;
  LocalExerciseService._internal();

  List<WgerExercise>? _exercises;
  List<WgerExerciseCategory>? _categories;
  List<WgerMuscle>? _muscles;
  List<WgerEquipment>? _equipment;
  Future<void>? _loadFuture;
  Map<String, List<WgerExercise>> _byCategory = const {};
  Map<int, List<WgerExercise>> _byCategoryId = const {};
  Map<int, List<WgerExercise>> _byMuscle = const {};
  Map<int, String> _searchDocuments = const {};

  bool get isLoaded => _exercises != null;

  /// Load và parse toàn bộ exercises từ asset JSON
  Future<void> loadExercises() {
    if (_exercises != null) return Future.value();
    return _loadFuture ??= _loadExercisesInternal().whenComplete(() {
      _loadFuture = null;
    });
  }

  Future<void> _loadExercisesInternal() async {
    try {
      final jsonStr = await rootBundle.loadString(
        'assets/data/wger_exercises_raw.json',
      );
      final List<dynamic> raw = json.decode(jsonStr);

      final exercises = <WgerExercise>[];
      final categoryMap = <int, WgerExerciseCategory>{};
      final muscleMap = <int, WgerMuscle>{};
      final equipmentMap = <int, WgerEquipment>{};

      for (final item in raw) {
        try {
          final exercise = _parseExercise(item as Map<String, dynamic>);
          if (exercise.name.isNotEmpty) {
            exercises.add(exercise);
          }

          // Collect categories
          final cat = item['category'];
          if (cat is Map<String, dynamic>) {
            final id = _localInt(cat['id']);
            if (!categoryMap.containsKey(id)) {
              categoryMap[id] = WgerExerciseCategory.fromJson(cat);
            }
          }

          // Collect muscles
          for (final m in [
            ...(item['muscles'] ?? []),
            ...(item['muscles_secondary'] ?? [])
          ]) {
            if (m is Map<String, dynamic>) {
              final id = _localInt(m['id']);
              if (!muscleMap.containsKey(id)) {
                muscleMap[id] = WgerMuscle.fromJson(m);
              }
            }
          }

          for (final equipment
              in (item['equipment'] as List<dynamic>? ?? const [])) {
            if (equipment is Map) {
              final parsed =
                  WgerEquipment.fromJson(Map<String, dynamic>.from(equipment));
              if (parsed.id > 0 && parsed.name.isNotEmpty) {
                equipmentMap[parsed.id] = parsed;
              }
            }
          }
        } catch (_) {
          continue;
        }
      }

      exercises.sort((a, b) {
        final byName = a.name.toLowerCase().compareTo(b.name.toLowerCase());
        return byName != 0 ? byName : a.id.compareTo(b.id);
      });

      final uniqueExercises = <int, WgerExercise>{};
      for (final exercise in exercises) {
        uniqueExercises.putIfAbsent(exercise.id, () => exercise);
      }
      _exercises = List.unmodifiable(uniqueExercises.values);
      _categories = List.unmodifiable(
        categoryMap.values.toList()..sort((a, b) => a.name.compareTo(b.name)),
      );
      _muscles = List.unmodifiable(
        muscleMap.values.toList()..sort((a, b) => a.nameEn.compareTo(b.nameEn)),
      );
      _equipment = List.unmodifiable(
        equipmentMap.values.toList()..sort((a, b) => a.name.compareTo(b.name)),
      );
      _buildIndexes(categoryMap);
    } catch (e) {
      // Giữ trạng thái chưa load để lần mở màn hình sau có thể thử lại.
      _exercises = null;
      _categories = null;
      _muscles = null;
      _equipment = null;
      _byCategory = const {};
      _byCategoryId = const {};
      _byMuscle = const {};
      _searchDocuments = const {};
      debugPrint('Không thể tải dữ liệu bài tập wger cục bộ: $e');
    }
  }

  void _buildIndexes(Map<int, WgerExerciseCategory> categoriesById) {
    final categoryNameToId = <String, int>{
      for (final entry in categoriesById.entries)
        ExerciseUtils.normalizeSearchText(entry.value.name): entry.key,
    };
    final byCategory = <String, List<WgerExercise>>{};
    final byCategoryId = <int, List<WgerExercise>>{};
    final byMuscle = <int, List<WgerExercise>>{};
    final searchDocuments = <int, String>{};

    for (final exercise in _exercises ?? const <WgerExercise>[]) {
      final categoryKey =
          ExerciseUtils.normalizeSearchText(exercise.categoryName);
      byCategory.putIfAbsent(categoryKey, () => []).add(exercise);
      final categoryId = categoryNameToId[categoryKey];
      if (categoryId != null) {
        byCategoryId.putIfAbsent(categoryId, () => []).add(exercise);
      }
      for (final muscle in exercise.allMuscles) {
        byMuscle.putIfAbsent(muscle.id, () => []).add(exercise);
      }
      searchDocuments[exercise.id] = ExerciseUtils.normalizeSearchText(
        '${exercise.name} ${ExerciseUtils.cleanHtml(exercise.description)} '
        '${exercise.categoryName} '
        '${exercise.allMuscles.map((muscle) => muscle.nameEn).join(' ')} '
        '${exercise.equipment.map((item) => item.name).join(' ')}',
      );
    }

    _byCategory = {
      for (final entry in byCategory.entries)
        entry.key: List.unmodifiable(entry.value),
    };
    _byCategoryId = {
      for (final entry in byCategoryId.entries)
        entry.key: List.unmodifiable(entry.value),
    };
    _byMuscle = {
      for (final entry in byMuscle.entries)
        entry.key: List.unmodifiable(entry.value),
    };
    _searchDocuments = Map.unmodifiable(searchDocuments);
  }

  WgerExercise _parseExercise(Map<String, dynamic> item) {
    // Lấy tên tiếng Anh từ translations (language=2)
    String name = '';
    String description = '';
    final translations = item['translations'] as List<dynamic>? ?? [];
    for (final t in translations) {
      if (t is Map && _localInt(t['language']) == 2) {
        name = t['name']?.toString().trim() ?? '';
        description = t['description']?.toString().trim() ?? '';
        break;
      }
    }
    // Fallback: lấy translation đầu tiên nếu không có EN
    if (name.isEmpty && translations.isNotEmpty) {
      final first = translations.whereType<Map>().firstOrNull;
      name = first?['name']?.toString().trim() ?? '';
      description = first?['description']?.toString().trim() ?? '';
    }

    // Category
    final cat = item['category'];
    String categoryName = '';
    if (cat is Map<String, dynamic>) {
      categoryName = cat['name']?.toString() ?? '';
    }

    // Muscles (giữ nguyên image_url_main / image_url_secondary)
    final muscles = <WgerMuscle>[];
    for (final m in (item['muscles'] as List<dynamic>? ?? [])) {
      if (m is Map<String, dynamic>) {
        muscles.add(WgerMuscle.fromJson(m));
      }
    }

    final musclesSecondary = <WgerMuscle>[];
    for (final m in (item['muscles_secondary'] as List<dynamic>? ?? [])) {
      if (m is Map<String, dynamic>) {
        musclesSecondary.add(WgerMuscle.fromJson(m));
      }
    }

    // Equipment
    final equipment = <WgerEquipment>[];
    for (final e in (item['equipment'] as List<dynamic>? ?? [])) {
      if (e is Map<String, dynamic>) {
        equipment.add(WgerEquipment.fromJson(e));
      }
    }

    // Image — ưu tiên is_main=true
    String? imageUrl;
    final images = item['images'] as List<dynamic>? ?? [];
    for (final img in images) {
      if (img is Map<String, dynamic> && img['is_main'] == true) {
        imageUrl = img['image']?.toString();
        break;
      }
    }
    if (imageUrl == null && images.isNotEmpty) {
      final first = images.first;
      if (first is Map<String, dynamic>) {
        imageUrl = first['image']?.toString();
      }
    }

    return WgerExercise(
      id: _localInt(item['id']),
      name: name,
      description: description,
      categoryName: categoryName,
      muscles: muscles,
      musclesSecondary: musclesSecondary,
      equipment: equipment,
      imageUrl: imageUrl,
    );
  }

  List<WgerExercise> get allExercises => _exercises ?? [];
  List<WgerExerciseCategory> get categories => _categories ?? [];
  List<WgerMuscle> get muscles => _muscles ?? [];
  List<WgerEquipment> get equipment => _equipment ?? [];

  /// Lấy exercises theo category name
  List<WgerExercise> getByCategory(String categoryName) {
    return _byCategory[ExerciseUtils.normalizeSearchText(categoryName)] ??
        const [];
  }

  List<WgerExercise> getByCategoryId(int categoryId) =>
      _byCategoryId[categoryId] ?? const [];

  /// Lấy exercises theo muscle id
  List<WgerExercise> getByMuscle(int muscleId) {
    return _byMuscle[muscleId] ?? const [];
  }

  /// Tìm kiếm theo tên
  List<WgerExercise> search(String query) {
    final q = ExerciseUtils.normalizeSearchText(query);
    if (q.isEmpty) return allExercises;
    return allExercises
        .where((exercise) => _searchDocuments[exercise.id]?.contains(q) == true)
        .toList(growable: false);
  }

  /// Lấy trang (pagination)
  List<WgerExercise> getPage(
    List<WgerExercise> source,
    int page, {
    int pageSize = 20,
  }) {
    if (page < 1 || pageSize < 1) return const [];
    final start = (page - 1) * pageSize;
    if (start >= source.length) return [];
    final end = (start + pageSize).clamp(0, source.length);
    return source.sublist(start, end);
  }
}
