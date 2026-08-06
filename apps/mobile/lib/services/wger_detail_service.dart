import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../config/wger_config.dart';

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
        id: j['id'],
        name: j['name'] ?? '',
        nameEn: j['name_en'] ?? '',
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
        id: j['id'],
        name: j['name'] ?? '',
        description: j['description'] ?? '',
        category: j['category'] ?? '',
        muscles: (j['muscles'] as List? ?? [])
            .map((m) => MuscleDetail.fromJson(m))
            .toList(),
        musclesSecondary: (j['muscles_secondary'] as List? ?? [])
            .map((m) => MuscleDetail.fromJson(m))
            .toList(),
        equipment: List<String>.from(j['equipment'] ?? []),
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
        id: j['id'],
        gram: (j['gram'] as num).toDouble(),
        name: j['name'] ?? '',
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
        id: j['id'],
        name: j['name'] ?? '',
        commonName: j['common_name'],
        brand: j['brand'],
        energy: (j['energy'] as num?)?.toDouble(),
        protein: (j['protein'] as num?)?.toDouble(),
        carbohydrates: (j['carbohydrates'] as num?)?.toDouble(),
        carbohydratesSugar: (j['carbohydrates_sugar'] as num?)?.toDouble(),
        fat: (j['fat'] as num?)?.toDouble(),
        fatSaturated: (j['fat_saturated'] as num?)?.toDouble(),
        fiber: (j['fiber'] as num?)?.toDouble(),
        sodium: (j['sodium'] as num?)?.toDouble(),
        isVegan: j['is_vegan'],
        isVegetarian: j['is_vegetarian'],
        nutriscore: j['nutriscore'],
        weightUnits: (j['weight_units'] as List? ?? [])
            .map((w) => WeightUnit.fromJson(w))
            .toList(),
        imageUrl: j['image_url'],
      );
}

class WgerDetailService {
  static final WgerDetailService _instance = WgerDetailService._();
  factory WgerDetailService() => _instance;
  WgerDetailService._();

  Future<ExerciseDetail?> fetchExercise(int id) async {
    if (id == 0) return null;
    try {
      final resp = await http
          .get(Uri.parse('${WgerConfig.backendBaseUrl}/wger/exercise/$id'))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        return ExerciseDetail.fromJson(jsonDecode(resp.body));
      }
    } catch (e) {
      debugPrint('⚠️ fetchExercise($id) failed: $e');
    }
    return null;
  }

  Future<IngredientDetail?> fetchIngredient(int id) async {
    if (id == 0) return null;
    try {
      final resp = await http
          .get(Uri.parse('${WgerConfig.backendBaseUrl}/wger/ingredient/$id'))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        return IngredientDetail.fromJson(jsonDecode(resp.body));
      }
    } catch (e) {
      debugPrint('⚠️ fetchIngredient($id) failed: $e');
    }
    return null;
  }
}
