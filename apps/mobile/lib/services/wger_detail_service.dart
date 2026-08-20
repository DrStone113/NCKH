import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../config/wger_config.dart';

int _detailInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

double? _detailDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

class MuscleDetail {
  final int id;
  final String name;
  final String nameEn;
  final bool isFront;
  final String? imageUrlMain;

  MuscleDetail({
    required this.id,
    required this.name,
    required this.nameEn,
    required this.isFront,
    this.imageUrlMain,
  });

  factory MuscleDetail.fromJson(Map<String, dynamic> j) => MuscleDetail(
        id: _detailInt(j['id']),
        name: j['name']?.toString() ?? '',
        nameEn: j['name_en']?.toString() ?? '',
        isFront: j['is_front'] ?? true,
        imageUrlMain: j['image_url_main'],
      );
}

class ExerciseDetail {
  final int id;
  final String name;
  final String description;
  final String category;
  final List<MuscleDetail> muscles;
  final List<MuscleDetail> musclesSecondary;
  final List<String> equipment;
  final String? imageUrl;
  final List<String> aliases;

  ExerciseDetail({
    required this.id,
    required this.name,
    required this.description,
    required this.category,
    required this.muscles,
    required this.musclesSecondary,
    required this.equipment,
    this.imageUrl,
    this.aliases = const [],
  });

  factory ExerciseDetail.fromJson(Map<String, dynamic> j) => ExerciseDetail(
        id: _detailInt(j['id']),
        name: j['name']?.toString() ?? '',
        description: j['description']?.toString() ?? '',
        category: j['category']?.toString() ?? '',
        muscles: (j['muscles'] as List? ?? [])
            .whereType<Map>()
            .map((m) => MuscleDetail.fromJson(Map<String, dynamic>.from(m)))
            .toList(growable: false),
        musclesSecondary: (j['muscles_secondary'] as List? ?? [])
            .whereType<Map>()
            .map((m) => MuscleDetail.fromJson(Map<String, dynamic>.from(m)))
            .toList(growable: false),
        equipment: (j['equipment'] as List? ?? [])
            .map((item) => item.toString())
            .toList(growable: false),
        imageUrl: j['image_url'],
        aliases: List<String>.from(j['aliases'] ?? []),
      );
}

class WeightUnit {
  final int id;
  final double gram;
  final String name;
  WeightUnit({required this.id, required this.gram, required this.name});
  factory WeightUnit.fromJson(Map<String, dynamic> j) => WeightUnit(
        id: _detailInt(j['id']),
        gram: _detailDouble(j['gram']) ?? 0,
        name: j['name']?.toString() ?? '',
      );
}

class IngredientDetail {
  final int id;
  final String name;
  final String? commonName;
  final String? brand;
  final double? energy;
  final double? protein;
  final double? carbohydrates;
  final double? carbohydratesSugar;
  final double? fat;
  final double? fatSaturated;
  final double? fiber;
  final double? sodium;
  final bool? isVegan;
  final bool? isVegetarian;
  final String? nutriscore;
  final List<WeightUnit> weightUnits;
  final String? imageUrl;

  IngredientDetail({
    required this.id,
    required this.name,
    this.commonName,
    this.brand,
    this.energy,
    this.protein,
    this.carbohydrates,
    this.carbohydratesSugar,
    this.fat,
    this.fatSaturated,
    this.fiber,
    this.sodium,
    this.isVegan,
    this.isVegetarian,
    this.nutriscore,
    this.weightUnits = const [],
    this.imageUrl,
  });

  factory IngredientDetail.fromJson(Map<String, dynamic> j) => IngredientDetail(
        id: _detailInt(j['id']),
        name: j['name']?.toString() ?? '',
        commonName: j['common_name'],
        brand: j['brand'],
        energy: _detailDouble(j['energy']),
        protein: _detailDouble(j['protein']),
        carbohydrates: _detailDouble(j['carbohydrates']),
        carbohydratesSugar: _detailDouble(j['carbohydrates_sugar']),
        fat: _detailDouble(j['fat']),
        fatSaturated: _detailDouble(j['fat_saturated']),
        fiber: _detailDouble(j['fiber']),
        sodium: _detailDouble(j['sodium']),
        isVegan: j['is_vegan'],
        isVegetarian: j['is_vegetarian'],
        nutriscore: j['nutriscore'],
        weightUnits: (j['weight_units'] as List? ?? [])
            .whereType<Map>()
            .map((w) => WeightUnit.fromJson(Map<String, dynamic>.from(w)))
            .toList(growable: false),
        imageUrl: j['image_url'],
      );
}

class WgerDetailService {
  static final WgerDetailService _instance = WgerDetailService._();
  factory WgerDetailService() => _instance;
  WgerDetailService._();

  final http.Client _client = http.Client();
  final Map<int, ExerciseDetail> _exerciseCache = {};
  final Map<int, IngredientDetail> _ingredientCache = {};
  final Map<int, Future<ExerciseDetail?>> _exerciseRequests = {};
  final Map<int, Future<IngredientDetail?>> _ingredientRequests = {};
  static const int _maxCacheEntries = 80;

  Future<ExerciseDetail?> fetchExercise(int id) {
    if (id <= 0) return Future.value();
    final cached = _exerciseCache[id];
    if (cached != null) return Future.value(cached);
    return _exerciseRequests[id] ??= _fetchExercise(id);
  }

  Future<ExerciseDetail?> _fetchExercise(int id) async {
    try {
      final resp = await _client
          .get(Uri.parse('${WgerConfig.backendBaseUrl}/wger/exercise/$id'))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        final detail = ExerciseDetail.fromJson(
          jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>,
        );
        _putBounded(_exerciseCache, id, detail);
        return detail;
      }
      return null;
    } catch (e) {
      debugPrint('⚠️ fetchExercise($id) failed: $e');
      return null;
    } finally {
      _exerciseRequests.remove(id);
    }
  }

  Future<IngredientDetail?> fetchIngredient(int id) {
    if (id <= 0) return Future.value();
    final cached = _ingredientCache[id];
    if (cached != null) return Future.value(cached);
    return _ingredientRequests[id] ??= _fetchIngredient(id);
  }

  Future<IngredientDetail?> _fetchIngredient(int id) async {
    try {
      final resp = await _client
          .get(Uri.parse('${WgerConfig.backendBaseUrl}/wger/ingredient/$id'))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        final detail = IngredientDetail.fromJson(
          jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>,
        );
        _putBounded(_ingredientCache, id, detail);
        return detail;
      }
      return null;
    } catch (e) {
      debugPrint('⚠️ fetchIngredient($id) failed: $e');
      return null;
    } finally {
      _ingredientRequests.remove(id);
    }
  }

  void _putBounded<T>(Map<int, T> cache, int id, T value) {
    cache[id] = value;
    if (cache.length > _maxCacheEntries) {
      cache.remove(cache.keys.first);
    }
  }
}
