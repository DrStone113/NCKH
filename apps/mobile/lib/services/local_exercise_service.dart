import 'dart:convert';
import 'package:flutter/services.dart';
import '../models/wger_models.dart';

/// Service load bài tập từ file JSON local (wger_exercises_raw.json)
/// Không cần gọi API, hoạt động offline hoàn toàn
class LocalExerciseService {
  static final LocalExerciseService _instance = LocalExerciseService._internal();
  factory LocalExerciseService() => _instance;
  LocalExerciseService._internal();

  List<WgerExercise>? _exercises;
  List<WgerExerciseCategory>? _categories;
  List<WgerMuscle>? _muscles;

  bool get isLoaded => _exercises != null;

  /// Load và parse toàn bộ exercises từ asset JSON
  Future<void> loadExercises() async {
    if (_exercises != null) return; // đã load rồi

    try {
      final jsonStr = await rootBundle.loadString(
        'assets/data/wger_exercises_raw.json',
      );
      final List<dynamic> raw = json.decode(jsonStr);

      final exercises = <WgerExercise>[];
      final categoryMap = <int, WgerExerciseCategory>{};
      final muscleMap = <int, WgerMuscle>{};

      for (final item in raw) {
        try {
          final exercise = _parseExercise(item as Map<String, dynamic>);
          if (exercise.name.isNotEmpty) {
            exercises.add(exercise);
          }

          // Collect categories
          final cat = item['category'];
          if (cat is Map<String, dynamic>) {
            final id = cat['id'] as int? ?? 0;
            if (!categoryMap.containsKey(id)) {
              categoryMap[id] = WgerExerciseCategory.fromJson(cat);
            }
          }

          // Collect muscles
          for (final m in [...(item['muscles'] ?? []), ...(item['muscles_secondary'] ?? [])]) {
            if (m is Map<String, dynamic>) {
              final id = m['id'] as int? ?? 0;
              if (!muscleMap.containsKey(id)) {
                muscleMap[id] = WgerMuscle.fromJson(m);
              }
            }
          }
        } catch (_) {
          continue;
        }
      }

      _exercises = exercises;
      _categories = categoryMap.values.toList()
        ..sort((a, b) => a.name.compareTo(b.name));
      _muscles = muscleMap.values.toList()
        ..sort((a, b) => a.nameEn.compareTo(b.nameEn));
    } catch (e) {
      _exercises = [];
      _categories = [];
      _muscles = [];
    }
  }

  WgerExercise _parseExercise(Map<String, dynamic> item) {
    // Lấy tên tiếng Anh từ translations (language=2)
    String name = '';
    String description = '';
    final translations = item['translations'] as List<dynamic>? ?? [];
    for (final t in translations) {
      if (t is Map<String, dynamic> && t['language'] == 2) {
        name = (t['name'] as String? ?? '').trim();
        description = (t['description'] as String? ?? '').trim();
        break;
      }
    }
    // Fallback: lấy translation đầu tiên nếu không có EN
    if (name.isEmpty && translations.isNotEmpty) {
      final first = translations.first as Map<String, dynamic>;
      name = (first['name'] as String? ?? '').trim();
      description = (first['description'] as String? ?? '').trim();
    }

    // Category
    final cat = item['category'];
    String categoryName = '';
    if (cat is Map<String, dynamic>) {
      categoryName = cat['name'] as String? ?? '';
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
        imageUrl = img['image'] as String?;
        break;
      }
    }
    if (imageUrl == null && images.isNotEmpty) {
      final first = images.first;
      if (first is Map<String, dynamic>) {
        imageUrl = first['image'] as String?;
      }
    }

    return WgerExercise(
      id: item['id'] as int? ?? 0,
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

  /// Lấy exercises theo category name
  List<WgerExercise> getByCategory(String categoryName) {
    return allExercises
        .where((e) => e.categoryName.toLowerCase() == categoryName.toLowerCase())
        .toList();
  }

  /// Lấy exercises theo muscle id
  List<WgerExercise> getByMuscle(int muscleId) {
    return allExercises.where((e) {
      return e.muscles.any((m) => m.id == muscleId) ||
          e.musclesSecondary.any((m) => m.id == muscleId);
    }).toList();
  }

  /// Tìm kiếm theo tên
  List<WgerExercise> search(String query) {
    if (query.isEmpty) return allExercises;
    final q = query.toLowerCase();
    return allExercises
        .where((e) => e.name.toLowerCase().contains(q))
        .toList();
  }

  /// Lấy trang (pagination)
  List<WgerExercise> getPage(
    List<WgerExercise> source,
    int page, {
    int pageSize = 20,
  }) {
    final start = (page - 1) * pageSize;
    if (start >= source.length) return [];
    final end = (start + pageSize).clamp(0, source.length);
    return source.sublist(start, end);
  }
}
