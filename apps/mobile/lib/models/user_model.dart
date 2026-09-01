import 'canonical_nutrition.dart';

class UserModel {
  final String id;
  final String email;
  final String name;
  final int age;
  final String? gender; // General identity field; not an equation input.
  final String?
      equationSex; // Explicit Mifflin input: male, female, or missing.
  final NutritionSafetyProfile nutritionSafetyProfile;
  final double height; // cm
  final double weight; // kg
  final double? targetWeight; // kg - can_nang_muc_tieu
  final String activityLevel; // sedentary, light, moderate, active, very_active
  final String healthGoal; // lose_weight, maintain, gain_muscle
  /// Optional free-text nutrition preferences, kept separate from structured
  /// safety answers so the assistant never mistakes prose for a verified tag.
  final NutritionProfile? nutritionProfile;

  /// Nullable E4.1 exercise profile. Old Firestore user documents intentionally
  /// stay unknown rather than receiving fabricated training defaults.
  final WorkoutProfile? workoutProfile;

  /// V2 envelope for the unified nutrition, workout and safety intake. The
  /// legacy top-level profile fields above remain readable and are mirrored on
  /// writes so existing account documents and older app releases keep working.
  final HealthProfile? healthProfile;
  final DateTime? createdAt;

  UserModel({
    required this.id,
    required this.email,
    required this.name,
    required this.age,
    this.gender,
    this.equationSex,
    this.nutritionSafetyProfile = const NutritionSafetyProfile(),
    required this.height,
    required this.weight,
    this.targetWeight,
    required this.activityLevel,
    this.healthGoal = 'maintain',
    this.nutritionProfile,
    this.workoutProfile,
    this.healthProfile,
    this.createdAt,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'email': email,
      'name': name,
      'age': age,
      'gender': gender,
      'equation_sex': equationSex,
      'nutrition_safety_profile': nutritionSafetyProfile.toJson(),
      'height': height,
      'weight': weight,
      'targetWeight': targetWeight,
      'activityLevel': activityLevel,
      'healthGoal': healthGoal,
      if (nutritionProfile != null)
        'nutrition_profile': nutritionProfile!.toJson(),
      if (workoutProfile != null) 'workout_profile': workoutProfile!.toJson(),
      if (healthProfile != null) 'health_profile': healthProfile!.toJson(),
      'createdAt': (createdAt ?? DateTime.now()).toIso8601String(),
    };
  }

  factory UserModel.fromMap(Map<String, dynamic> map) {
    return UserModel(
      id: map['id'] ?? '',
      email: map['email'] ?? '',
      name: map['name'] ?? '',
      age: map['age'] ?? 0,
      gender: map['gender']?.toString(),
      equationSex: const {'male', 'female'}.contains(map['equation_sex'])
          ? map['equation_sex'].toString()
          : null,
      nutritionSafetyProfile:
          NutritionSafetyProfile.fromJson(map['nutrition_safety_profile']),
      height: (map['height'] ?? 0).toDouble(),
      weight: (map['weight'] ?? 0).toDouble(),
      targetWeight: map['targetWeight']?.toDouble(),
      activityLevel: map['activityLevel'] ?? 'sedentary',
      healthGoal: map['healthGoal'] ?? 'maintain',
      nutritionProfile: NutritionProfile.fromJson(map['nutrition_profile']),
      workoutProfile: WorkoutProfile.fromJson(map['workout_profile']),
      healthProfile: HealthProfile.fromJson(map['health_profile']),
      createdAt:
          map['createdAt'] != null ? DateTime.tryParse(map['createdAt']) : null,
    );
  }

  /// Old accounts and accounts from an older questionnaire version return
  /// `true`, allowing the authenticated app shell to request only the missing
  /// account intake before it opens the main experience.
  bool get needsWorkoutAccountIntake =>
      !(workoutProfile?.hasCompletedCurrentAccountIntake ?? false);

  bool get needsAccountHealthIntake =>
      !(healthProfile?.hasCompletedCurrentAccountIntake ?? false);

  /// The authoritative shared profile layer.  These values intentionally stay
  /// at the user root so nutrition and workout can both consume them without
  /// copying a second, potentially stale value into either subprofile.
  GeneralProfile get generalProfile => GeneralProfile(
        age: age,
        heightCm: height,
        weightKg: weight,
        equationSex: equationSex,
        activityLevel: activityLevel,
        healthGoal: healthGoal,
      );

  static const _notSet = Object();

  UserModel copyWith({
    String? id,
    String? email,
    String? name,
    int? age,
    Object? gender = _notSet,
    Object? equationSex = _notSet,
    NutritionSafetyProfile? nutritionSafetyProfile,
    double? height,
    double? weight,
    double? targetWeight,
    String? activityLevel,
    String? healthGoal,
    Object? nutritionProfile = _notSet,
    Object? workoutProfile = _notSet,
    Object? healthProfile = _notSet,
  }) {
    return UserModel(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
      age: age ?? this.age,
      gender: identical(gender, _notSet) ? this.gender : gender as String?,
      equationSex: identical(equationSex, _notSet)
          ? this.equationSex
          : equationSex as String?,
      nutritionSafetyProfile:
          nutritionSafetyProfile ?? this.nutritionSafetyProfile,
      height: height ?? this.height,
      weight: weight ?? this.weight,
      targetWeight: targetWeight ?? this.targetWeight,
      activityLevel: activityLevel ?? this.activityLevel,
      healthGoal: healthGoal ?? this.healthGoal,
      nutritionProfile: identical(nutritionProfile, _notSet)
          ? this.nutritionProfile
          : nutritionProfile as NutritionProfile?,
      workoutProfile: identical(workoutProfile, _notSet)
          ? this.workoutProfile
          : workoutProfile as WorkoutProfile?,
      healthProfile: identical(healthProfile, _notSet)
          ? this.healthProfile
          : healthProfile as HealthProfile?,
      createdAt: createdAt,
    );
  }

  // === CHỈ SỐ CƠ THỂ ===

  CanonicalNutritionState canonicalForGoal(String goal) =>
      calculateCanonicalNutrition(CanonicalNutritionInput(
        age: CanonicalNutritionValue.known(age, source: 'user_profile.age'),
        equationSex: equationSex == null
            ? const CanonicalNutritionValue<String>(
                value: null,
                source: 'user_profile.equation_sex',
                status: NutritionInputStatus.missing,
              )
            : CanonicalNutritionValue.known(equationSex,
                source: 'user_profile.equation_sex'),
        heightCm: CanonicalNutritionValue.known(height,
            source: 'user_profile.height'),
        weightKg: CanonicalNutritionValue.known(weight,
            source: 'user_profile.weight'),
        activityLevel: CanonicalNutritionValue.known(activityLevel,
            source: 'user_profile.activity_level'),
        healthGoal: CanonicalNutritionValue.known(goal,
            source: 'user_profile.health_goal'),
        safetyProfile: nutritionSafetyProfile,
      ));

  CanonicalNutritionState get canonicalNutrition =>
      canonicalForGoal(healthGoal);

  // Compatibility getters delegate to the canonical policy-v1 state.
  double get bmi => canonicalNutrition.bmi ?? double.nan;
  double get displayBmi => canonicalNutrition.displayBmi ?? double.nan;

  String get bmiCategory {
    return canonicalNutrition.bmiClassification ?? 'Không khả dụng';
  }

  String? get bmiCategoryCode => canonicalNutrition.bmiClassificationCode;

  String get bmiAdvice {
    final category = canonicalNutrition.bmiClassification;
    if (category == null) return 'Chưa đủ dữ liệu để hiển thị BMI.';
    return 'Phân loại BMI: $category. Đây là thông tin sàng lọc, không phải chẩn đoán.';
  }

  double? get bmr => canonicalNutrition.estimatedRmrKcalPerDay;
  double? get displayRmr => canonicalNutrition.displayEstimatedRmrKcalPerDay;

  // TDEE
  double? get tdee => canonicalNutrition.estimatedTdeeKcalPerDay;
  double? get displayTdee => canonicalNutrition.displayEstimatedTdeeKcalPerDay;

  // Recommended daily calories based on goal
  double? get recommendedCalories => canonicalNutrition.calorieTargetKcalPerDay;
  double? get displayRecommendedCalories =>
      canonicalNutrition.displayCalorieTargetKcalPerDay;

  // Body fat estimation (US Navy method approximation)
  double? get estimatedBodyFat {
    if (gender == 'male') {
      return 1.20 * bmi + 0.23 * age - 16.2;
    }
    if (gender == 'female') {
      return 1.20 * bmi + 0.23 * age - 5.4;
    }
    return null;
  }

  // Daily water goal in liters
  double? get dailyWaterGoal =>
      canonicalNutrition.approximateFluidGoalMlPerDay == null
          ? null
          : canonicalNutrition.approximateFluidGoalMlPerDay! / 1000.0;
  double? get displayDailyWaterGoal =>
      canonicalNutrition.displayApproximateFluidGoalMlPerDay == null
          ? null
          : canonicalNutrition.displayApproximateFluidGoalMlPerDay! / 1000.0;

  // Activity level in Vietnamese
  String get activityLevelText {
    switch (activityLevel) {
      case 'sedentary':
        return 'Ít vận động';
      case 'light':
        return 'Vận động nhẹ';
      case 'moderate':
        return 'Vận động vừa';
      case 'active':
        return 'Vận động nhiều';
      case 'very_active':
        return 'Vận động rất nhiều';
      default:
        return 'Không rõ';
    }
  }

  String get healthGoalText {
    switch (healthGoal) {
      case 'lose_weight':
        return 'Giảm cân';
      case 'gain_muscle':
        return 'Tăng cơ';
      default:
        return 'Duy trì';
    }
  }
}

/// Shared values used by both nutrition and workout personalization.
///
/// This is a typed view over the authoritative user document rather than a
/// second persisted copy under `nutrition_profile` or `workout_profile`.
/// That makes a later weight/activity update visible to both domains at once.
class GeneralProfile {
  final int age;
  final double heightCm;
  final double weightKg;
  final String? equationSex;
  final String activityLevel;
  final String healthGoal;

  const GeneralProfile({
    required this.age,
    required this.heightCm,
    required this.weightKg,
    required this.equationSex,
    required this.activityLevel,
    required this.healthGoal,
  });

  Map<String, dynamic> toJson() => {
        'age': age,
        'height_cm': heightCm,
        'weight_kg': weightKg,
        'equation_sex': equationSex,
        'activity_level': activityLevel,
        'health_goal': healthGoal,
      };
}

/// Provenance and freshness attached to one persisted profile field.
///
/// `CANDIDATE_FACT` is retained for an auditable recap, but deliberately does
/// not count as confirmation and cannot drive deterministic constraints.
class ProfileFieldState {
  static const confirmed = 'CONFIRMED';
  static const legacy = 'LEGACY';
  static const candidateFact = 'CANDIDATE_FACT';
  static const notProvided = 'NOT_PROVIDED';

  final Object? value;
  final String status;
  final String source;
  final DateTime? updatedAt;
  final DateTime? confirmedAt;
  final String freshness;

  const ProfileFieldState({
    required this.value,
    required this.status,
    required this.source,
    required this.freshness,
    this.updatedAt,
    this.confirmedAt,
  });

  bool get isConfirmed =>
      status == confirmed && source.toUpperCase() != candidateFact;

  static ProfileFieldState? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final json = Map<String, dynamic>.from(raw);
    final source = json['source']?.toString().trim().toUpperCase();
    final status = json['status']?.toString().trim().toUpperCase();
    if (source == null || source.isEmpty || status == null || status.isEmpty) {
      return null;
    }
    return ProfileFieldState(
      value: json['value'],
      source: source,
      status: status,
      freshness: json['freshness']?.toString().trim().toUpperCase() ??
          'STABLE_UNTIL_CHANGED',
      updatedAt: DateTime.tryParse(json['updated_at']?.toString() ?? ''),
      confirmedAt: DateTime.tryParse(json['confirmed_at']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
        'value': value,
        'status': status,
        'source': source,
        'freshness': freshness,
        if (updatedAt != null)
          'updated_at': updatedAt!.toUtc().toIso8601String(),
        if (confirmedAt != null)
          'confirmed_at': confirmedAt!.toUtc().toIso8601String(),
      };
}

/// Structured and free-text nutrition facts explicitly supplied by a user.
///
/// The fields deliberately stay nullable: `null` means the user has not
/// supplied that fact, rather than "none". Free text is retained verbatim
/// (after whitespace trimming) and never promoted to a clinical diagnosis or
/// a canonical allergy tag without an explicit UI selection/confirmation.
class NutritionProfile {
  static const currentAccountIntakeVersion = 2;
  static const maxNoteLength = 600;
  static const supportedAllergenIds = <String>{
    'CRUSTACEAN',
    'MOLLUSC',
    'FISH',
    'EGG',
    'MILK',
    'PEANUT',
    'TREE_NUT',
    'SOY',
    'WHEAT_GLUTEN',
    'SESAME',
  };
  static const supportedDietaryRestrictions = <String>{
    'vegetarian',
    'vegan',
    'no_seafood',
    'no_pork',
    'no_beef',
    'low_carb',
    'high_protein',
  };
  static const supportedGoals = <String>{
    'LOSE_WEIGHT',
    'MAINTAIN',
    'GAIN_WEIGHT',
    'GAIN_MUSCLE',
    'IMPROVE_HABITS',
    'UNKNOWN',
    'NOT_PROVIDED',
  };

  /// Compatibility aliases from the V1 intake. They deliberately remain in
  /// the wire format so older clients can still display their own notes.
  final String? allergyAndAvoidanceNote;
  final String? foodPreferenceNote;
  final String? nutritionGoalNote;

  final String? nutritionGoal;
  final List<String>? foodAllergies;
  final List<String>? dietaryRestrictions;
  final List<String>? preferredFoods;
  final List<String>? dislikedFoods;
  final List<String>? preferredCuisines;
  final List<String>? mealPreferences;
  final List<String>? foodExclusions;
  final String? goalDescription;
  final String? foodPreferencesText;
  final String? foodDislikesText;
  final String? otherDietaryRestrictionsText;
  final String? nutritionNotes;
  final Map<String, String>? provenance;
  final Map<String, ProfileFieldState>? fieldStates;
  final List<ProfileCandidateFact>? candidateFacts;
  final int? accountIntakeVersion;
  final DateTime? accountIntakeCompletedAt;

  const NutritionProfile({
    this.allergyAndAvoidanceNote,
    this.foodPreferenceNote,
    this.nutritionGoalNote,
    this.nutritionGoal,
    this.foodAllergies,
    this.dietaryRestrictions,
    this.preferredFoods,
    this.dislikedFoods,
    this.preferredCuisines,
    this.mealPreferences,
    this.foodExclusions,
    this.goalDescription,
    this.foodPreferencesText,
    this.foodDislikesText,
    this.otherDietaryRestrictionsText,
    this.nutritionNotes,
    this.provenance,
    this.fieldStates,
    this.candidateFacts,
    this.accountIntakeVersion,
    this.accountIntakeCompletedAt,
  });

  static List<String>? _strings(Object? raw) {
    if (raw is! List) return null;
    final values = raw
        .whereType<String>()
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList(growable: false);
    return values.isEmpty ? null : values;
  }

  static Map<String, String>? _provenance(
      Object? raw, Map<String, dynamic> json) {
    if (raw is Map) {
      final values = <String, String>{};
      raw.forEach((key, value) {
        if (key is String && value is String && value.trim().isNotEmpty) {
          values[key] = value.trim().toUpperCase();
        }
      });
      if (values.isNotEmpty) return values;
    }
    // V1 notes were explicitly entered through the account UI, but did not
    // store a provenance map. Marking them LEGACY preserves their origin
    // without making new claims about their meaning.
    final legacy = <String, String>{};
    if (json['allergy_and_avoidance_note'] is String) {
      legacy['other_dietary_restrictions_text'] = 'LEGACY';
    }
    if (json['food_preference_note'] is String) {
      legacy['food_preferences_text'] = 'LEGACY';
    }
    if (json['nutrition_goal_note'] is String) {
      legacy['goal_description'] = 'LEGACY';
    }
    return legacy.isEmpty ? null : legacy;
  }

  static Map<String, ProfileFieldState>? _fieldStates(Object? raw) {
    if (raw is! Map) return null;
    final states = <String, ProfileFieldState>{};
    raw.forEach((key, value) {
      if (key is! String) return;
      final state = ProfileFieldState.fromJson(value);
      if (state != null) states[key] = state;
    });
    return states.isEmpty ? null : states;
  }

  static NutritionProfile? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final json = Map<String, dynamic>.from(raw);
    return NutritionProfile(
      allergyAndAvoidanceNote: _readText(json['allergy_and_avoidance_note']),
      foodPreferenceNote: _readText(json['food_preference_note']),
      nutritionGoalNote: _readText(json['nutrition_goal_note']),
      nutritionGoal: _readText(json['nutrition_goal'])?.toUpperCase(),
      foodAllergies: _strings(json['food_allergies']),
      dietaryRestrictions: _strings(json['dietary_restrictions']),
      preferredFoods: _strings(json['preferred_foods']),
      dislikedFoods: _strings(json['disliked_foods']),
      preferredCuisines: _strings(json['preferred_cuisines']),
      mealPreferences: _strings(json['meal_preferences']),
      foodExclusions: _strings(json['food_exclusions']),
      goalDescription: _readText(json['goal_description']),
      foodPreferencesText: _readText(json['food_preferences_text']),
      foodDislikesText: _readText(json['food_dislikes_text']),
      otherDietaryRestrictionsText:
          _readText(json['other_dietary_restrictions_text']),
      nutritionNotes: _readText(json['nutrition_notes']),
      provenance: _provenance(json['provenance'], json),
      fieldStates: _fieldStates(json['field_states']),
      candidateFacts:
          ProfileCandidateFact.listFromJson(json['candidate_facts']),
      accountIntakeVersion: (json['account_intake_version'] as num?)?.toInt(),
      accountIntakeCompletedAt: DateTime.tryParse(
          json['account_intake_completed_at']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
        if (allergyAndAvoidanceNote != null)
          'allergy_and_avoidance_note': allergyAndAvoidanceNote,
        if (foodPreferenceNote != null)
          'food_preference_note': foodPreferenceNote,
        if (nutritionGoalNote != null) 'nutrition_goal_note': nutritionGoalNote,
        if (nutritionGoal != null) 'nutrition_goal': nutritionGoal,
        if (foodAllergies != null) 'food_allergies': foodAllergies,
        if (dietaryRestrictions != null)
          'dietary_restrictions': dietaryRestrictions,
        if (preferredFoods != null) 'preferred_foods': preferredFoods,
        if (dislikedFoods != null) 'disliked_foods': dislikedFoods,
        if (preferredCuisines != null) 'preferred_cuisines': preferredCuisines,
        if (mealPreferences != null) 'meal_preferences': mealPreferences,
        if (foodExclusions != null) 'food_exclusions': foodExclusions,
        if (goalDescription != null) 'goal_description': goalDescription,
        if (foodPreferencesText != null)
          'food_preferences_text': foodPreferencesText,
        if (foodDislikesText != null) 'food_dislikes_text': foodDislikesText,
        if (otherDietaryRestrictionsText != null)
          'other_dietary_restrictions_text': otherDietaryRestrictionsText,
        if (nutritionNotes != null) 'nutrition_notes': nutritionNotes,
        if (provenance != null) 'provenance': provenance,
        if (fieldStates != null && fieldStates!.isNotEmpty)
          'field_states': fieldStates!
              .map((field, state) => MapEntry(field, state.toJson())),
        if (candidateFacts != null && candidateFacts!.isNotEmpty)
          'candidate_facts':
              candidateFacts!.map((fact) => fact.toJson()).toList(),
        if (requiresRelevantConfirmation)
          'requires_relevant_confirmation': true,
        if (accountIntakeVersion != null)
          'account_intake_version': accountIntakeVersion,
        if (accountIntakeCompletedAt != null)
          'account_intake_completed_at':
              accountIntakeCompletedAt!.toUtc().toIso8601String(),
      };

  bool get hasCompletedCurrentAccountIntake =>
      (accountIntakeVersion ?? 0) >= currentAccountIntakeVersion;

  bool get requiresRelevantConfirmation =>
      (candidateFacts?.isNotEmpty ?? false) ||
      (fieldStates?.values.any((state) =>
              state.status == ProfileFieldState.legacy ||
              state.status == ProfileFieldState.candidateFact ||
              state.source == ProfileFieldState.candidateFact) ??
          false) ||
      (provenance?.values.any((source) {
            final normalized = source.toUpperCase();
            return normalized == 'LEGACY' || normalized == 'CANDIDATE_FACT';
          }) ??
          false);

  bool _isConfirmedField(String field) {
    final state = fieldStates?[field];
    if (state != null) return state.isConfirmed;
    final source = provenance?[field]?.toUpperCase();
    return source == 'EXPLICIT_UI_SELECTION' ||
        source == 'EXPLICIT_USER_TEXT' ||
        source == 'USER_CONFIRMED';
  }

  /// Converts confirmed explicit selections into the exact tags understood by
  /// the deterministic dish tool.  This includes canonical allergens,
  /// confirmed dietary restrictions, and explicit food exclusions. Prose and
  /// unresolved candidate facts are deliberately excluded.
  List<String>? get canonicalDietaryRestrictions {
    final mappedAllergens = <String, String>{
      'PEANUT': 'no_peanut',
      'TREE_NUT': 'no_tree_nut',
      'MILK': 'no_milk',
      'EGG': 'no_egg',
      'FISH': 'no_fish',
      'CRUSTACEAN': 'no_crustacean',
      'MOLLUSC': 'no_mollusc',
      'SOY': 'no_soy',
      'WHEAT_GLUTEN': 'no_wheat_gluten',
      'SESAME': 'no_sesame',
    };
    final restrictions = <String>{};
    if (_isConfirmedField('dietary_restrictions')) {
      restrictions.addAll(dietaryRestrictions ?? const <String>[]);
    }
    if (_isConfirmedField('food_allergies')) {
      for (final allergen in foodAllergies ?? const <String>[]) {
        final tag = mappedAllergens[allergen];
        if (tag != null) restrictions.add(tag);
      }
    }
    if (_isConfirmedField('food_exclusions')) {
      const explicitExclusionTags = <String, String>{
        'no_pork': 'no_pork',
        'pork': 'no_pork',
        'thịt heo': 'no_pork',
        'thit heo': 'no_pork',
        'no_beef': 'no_beef',
        'beef': 'no_beef',
        'thịt bò': 'no_beef',
        'thit bo': 'no_beef',
        'no_seafood': 'no_seafood',
        'seafood': 'no_seafood',
        'hải sản': 'no_seafood',
        'hai san': 'no_seafood',
        'vegetarian': 'vegetarian',
        'vegan': 'vegan',
        'low_carb': 'low_carb',
        'high_protein': 'high_protein',
      };
      for (final exclusion in foodExclusions ?? const <String>[]) {
        final tag = explicitExclusionTags[exclusion.trim().toLowerCase()];
        if (tag != null) restrictions.add(tag);
      }
    }
    if (restrictions.isEmpty) return null;
    return restrictions.toList()..sort();
  }

  static String freshnessForField(String field) {
    switch (field) {
      case 'preferred_foods':
      case 'disliked_foods':
      case 'preferred_cuisines':
      case 'meal_preferences':
      case 'nutrition_goal':
        return 'PERIODIC_CONFIRMATION';
      default:
        return 'STABLE_UNTIL_CHANGED';
    }
  }

  static NutritionProfile completeAccountIntake(
    NutritionProfile? current, {
    required String? allergyAndAvoidanceNote,
    required String? foodPreferenceNote,
    required String? nutritionGoalNote,
    String? nutritionGoal,
    List<String>? foodAllergies,
    List<String>? dietaryRestrictions,
    List<String>? preferredFoods,
    List<String>? dislikedFoods,
    List<String>? preferredCuisines,
    List<String>? mealPreferences,
    List<String>? foodExclusions,
    String? goalDescription,
    String? foodPreferencesText,
    String? foodDislikesText,
    String? otherDietaryRestrictionsText,
    String? nutritionNotes,
    String selectionProvenance = 'EXPLICIT_UI_SELECTION',
    String textProvenance = 'EXPLICIT_USER_TEXT',
    DateTime? now,
  }) {
    final timestamp = (now ?? DateTime.now()).toUtc();
    final normalizedGoal = nutritionGoal == null
        ? current?.nutritionGoal
        : nutritionGoal.trim().toUpperCase();
    if (normalizedGoal != null && !supportedGoals.contains(normalizedGoal)) {
      throw ArgumentError('INVALID_NUTRITION_PROFILE_nutrition_goal');
    }
    final allergies = _validatedList(
      foodAllergies,
      fallback: current?.foodAllergies,
      allowed: supportedAllergenIds,
      field: 'food_allergies',
    );
    final restrictions = _validatedList(
      dietaryRestrictions,
      fallback: current?.dietaryRestrictions,
      allowed: supportedDietaryRestrictions,
      field: 'dietary_restrictions',
    );
    final otherText = _note(
      otherDietaryRestrictionsText ?? allergyAndAvoidanceNote,
      fallback: current?.otherDietaryRestrictionsText ??
          current?.allergyAndAvoidanceNote,
    );
    final preferenceText = _note(
      foodPreferencesText ?? foodPreferenceNote,
      fallback: current?.foodPreferencesText ?? current?.foodPreferenceNote,
    );
    final goalText = _note(
      goalDescription ?? nutritionGoalNote,
      fallback: current?.goalDescription ?? current?.nutritionGoalNote,
    );
    final changed = <String>{
      if (nutritionGoal != null) 'nutrition_goal',
      if (foodAllergies != null) 'food_allergies',
      if (dietaryRestrictions != null) 'dietary_restrictions',
      if (preferredFoods != null) 'preferred_foods',
      if (dislikedFoods != null) 'disliked_foods',
      if (preferredCuisines != null) 'preferred_cuisines',
      if (mealPreferences != null) 'meal_preferences',
      if (foodExclusions != null) 'food_exclusions',
      if (goalDescription != null || nutritionGoalNote != null)
        'goal_description',
      if (foodPreferencesText != null || foodPreferenceNote != null)
        'food_preferences_text',
      if (foodDislikesText != null) 'food_dislikes_text',
      if (otherDietaryRestrictionsText != null ||
          allergyAndAvoidanceNote != null)
        'other_dietary_restrictions_text',
      if (nutritionNotes != null) 'nutrition_notes',
    };
    final nextProvenance = <String, String>{...?current?.provenance};
    for (final field in changed) {
      nextProvenance[field] = field.endsWith('_text') ||
              field == 'goal_description' ||
              field == 'nutrition_notes'
          ? textProvenance
          : selectionProvenance;
    }
    final nextPreferredFoods =
        _freeList(preferredFoods, current?.preferredFoods);
    final nextDislikedFoods = _freeList(dislikedFoods, current?.dislikedFoods);
    final nextPreferredCuisines =
        _freeList(preferredCuisines, current?.preferredCuisines);
    final nextMealPreferences =
        _freeList(mealPreferences, current?.mealPreferences);
    final nextFoodExclusions =
        _freeList(foodExclusions, current?.foodExclusions);
    final nextFoodDislikesText =
        _note(foodDislikesText, fallback: current?.foodDislikesText);
    final nextNutritionNotes =
        _note(nutritionNotes, fallback: current?.nutritionNotes);
    final nextFieldStates = <String, ProfileFieldState>{
      ...?current?.fieldStates
    };

    Object? valueFor(String field) {
      switch (field) {
        case 'nutrition_goal':
          return normalizedGoal;
        case 'food_allergies':
          return allergies;
        case 'dietary_restrictions':
          return restrictions;
        case 'preferred_foods':
          return nextPreferredFoods;
        case 'disliked_foods':
          return nextDislikedFoods;
        case 'preferred_cuisines':
          return nextPreferredCuisines;
        case 'meal_preferences':
          return nextMealPreferences;
        case 'food_exclusions':
          return nextFoodExclusions;
        case 'goal_description':
          return goalText;
        case 'food_preferences_text':
          return preferenceText;
        case 'food_dislikes_text':
          return nextFoodDislikesText;
        case 'other_dietary_restrictions_text':
          return otherText;
        case 'nutrition_notes':
          return nextNutritionNotes;
      }
      return null;
    }

    for (final field in changed) {
      final source = nextProvenance[field]!;
      final normalizedSource = source.toUpperCase();
      final status = normalizedSource == ProfileFieldState.candidateFact
          ? ProfileFieldState.candidateFact
          : normalizedSource == ProfileFieldState.legacy
              ? ProfileFieldState.legacy
              : ProfileFieldState.confirmed;
      nextFieldStates[field] = ProfileFieldState(
        value: valueFor(field),
        status: status,
        source: normalizedSource,
        freshness: freshnessForField(field),
        updatedAt: timestamp,
        confirmedAt: status == ProfileFieldState.confirmed ? timestamp : null,
      );
    }
    return NutritionProfile(
      // Keep aliases synchronized without treating their text as hard tags.
      allergyAndAvoidanceNote: otherText,
      foodPreferenceNote: preferenceText,
      nutritionGoalNote: goalText,
      nutritionGoal: normalizedGoal,
      foodAllergies: allergies,
      dietaryRestrictions: restrictions,
      preferredFoods: nextPreferredFoods,
      dislikedFoods: nextDislikedFoods,
      preferredCuisines: nextPreferredCuisines,
      mealPreferences: nextMealPreferences,
      foodExclusions: nextFoodExclusions,
      goalDescription: goalText,
      foodPreferencesText: preferenceText,
      foodDislikesText: nextFoodDislikesText,
      otherDietaryRestrictionsText: otherText,
      nutritionNotes: nextNutritionNotes,
      provenance: nextProvenance.isEmpty ? null : nextProvenance,
      fieldStates: nextFieldStates.isEmpty ? null : nextFieldStates,
      candidateFacts: current?.candidateFacts,
      accountIntakeVersion: currentAccountIntakeVersion,
      accountIntakeCompletedAt: timestamp,
    );
  }

  /// Changes only supplied, explicit fields. This is the safe update path for
  /// a later correction; no model-generated interpretation is accepted here.
  static NutritionProfile applyExplicitUpdate(
    NutritionProfile? current,
    Map<String, dynamic> patch, {
    DateTime? now,
  }) {
    const allowed = {
      'nutrition_goal',
      'food_allergies',
      'dietary_restrictions',
      'preferred_foods',
      'disliked_foods',
      'preferred_cuisines',
      'meal_preferences',
      'food_exclusions',
      'goal_description',
      'food_preferences_text',
      'food_dislikes_text',
      'other_dietary_restrictions_text',
      'nutrition_notes',
    };
    if (patch.isEmpty || patch.keys.any((key) => !allowed.contains(key))) {
      throw ArgumentError('INVALID_NUTRITION_PROFILE_PATCH');
    }
    String? text(String key) => patch.containsKey(key)
        ? (patch[key] is String ? patch[key] as String : throw ArgumentError())
        : null;
    List<String>? list(String key) => patch.containsKey(key)
        ? (patch[key] is List
            ? (patch[key] as List).whereType<String>().toList(growable: false)
            : throw ArgumentError())
        : null;
    return completeAccountIntake(
      current,
      allergyAndAvoidanceNote: text('other_dietary_restrictions_text'),
      foodPreferenceNote: text('food_preferences_text'),
      nutritionGoalNote: text('goal_description'),
      nutritionGoal: text('nutrition_goal'),
      foodAllergies: list('food_allergies'),
      dietaryRestrictions: list('dietary_restrictions'),
      preferredFoods: list('preferred_foods'),
      dislikedFoods: list('disliked_foods'),
      preferredCuisines: list('preferred_cuisines'),
      mealPreferences: list('meal_preferences'),
      foodExclusions: list('food_exclusions'),
      foodDislikesText: text('food_dislikes_text'),
      nutritionNotes: text('nutrition_notes'),
      selectionProvenance: 'USER_CONFIRMED',
      textProvenance: 'EXPLICIT_USER_TEXT',
      now: now,
    );
  }

  static String? _readText(Object? value) =>
      value is String && value.trim().isNotEmpty ? value.trim() : null;

  static String? _note(String? value, {String? fallback}) {
    if (value == null) return fallback;
    final normalized = value.trim();
    if (normalized.length > maxNoteLength) {
      throw ArgumentError('NUTRITION_PROFILE_NOTE_TOO_LONG');
    }
    return normalized.isEmpty ? null : normalized;
  }

  static List<String>? _freeList(List<String>? value, List<String>? fallback) {
    if (value == null) return fallback;
    final values = value
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (values.any((item) => item.length > 120)) {
      throw ArgumentError('NUTRITION_PROFILE_LIST_ITEM_TOO_LONG');
    }
    return values.isEmpty ? null : values;
  }

  static List<String>? _validatedList(
    List<String>? value, {
    required List<String>? fallback,
    required Set<String> allowed,
    required String field,
  }) {
    final values = _freeList(value, fallback);
    if (values != null && !values.every(allowed.contains)) {
      throw ArgumentError('INVALID_NUTRITION_PROFILE_$field');
    }
    return values;
  }
}

/// A possible interpretation of free text. It is intentionally not a profile
/// constraint until the user confirms it. Current UI writes no candidates: it
/// stores raw text exactly, which is safer than guessing.
class ProfileCandidateFact {
  final String field;
  final String rawText;
  final String? proposedValue;
  final String status;
  final String source;
  final DateTime? updatedAt;
  final DateTime? confirmedAt;

  const ProfileCandidateFact({
    required this.field,
    required this.rawText,
    this.proposedValue,
    this.status = 'CANDIDATE_FACT',
    this.source = 'CANDIDATE_FACT',
    this.updatedAt,
    this.confirmedAt,
  });

  static List<ProfileCandidateFact>? listFromJson(Object? raw) {
    if (raw is! List) return null;
    final values = raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .map((item) {
          final field = item['field'];
          final text = item['raw_text'];
          if (field is! String ||
              text is! String ||
              field.isEmpty ||
              text.isEmpty) {
            return null;
          }
          return ProfileCandidateFact(
            field: field,
            rawText: text,
            proposedValue: item['proposed_value'] as String?,
            status:
                (item['status'] as String? ?? 'CANDIDATE_FACT').toUpperCase(),
            source:
                (item['source'] as String? ?? 'CANDIDATE_FACT').toUpperCase(),
            updatedAt: DateTime.tryParse(item['updated_at']?.toString() ?? ''),
            confirmedAt:
                DateTime.tryParse(item['confirmed_at']?.toString() ?? ''),
          );
        })
        .whereType<ProfileCandidateFact>()
        .toList(growable: false);
    return values.isEmpty ? null : values;
  }

  Map<String, dynamic> toJson() => {
        'field': field,
        'raw_text': rawText,
        if (proposedValue != null) 'proposed_value': proposedValue,
        'status': status,
        'source': source,
        if (updatedAt != null)
          'updated_at': updatedAt!.toUtc().toIso8601String(),
        if (confirmedAt != null)
          'confirmed_at': confirmedAt!.toUtc().toIso8601String(),
      };
}

/// V2 envelope. `health_profile` is additive: historical top-level
/// `nutrition_profile` and `workout_profile` are never reinterpreted or
/// removed, and are mirrored when this envelope is saved.
class HealthProfile {
  static const currentSchemaVersion = 2;
  static const supportedPrimarySupport = <String>{
    'NUTRITION',
    'EXERCISE',
    'BOTH',
    'GENERAL_HEALTH',
  };

  final int? schemaVersion;
  final String? primarySupport;
  final NutritionProfile? nutritionProfile;
  final WorkoutProfile? workoutProfile;
  final SafetyProfile? safetyProfile;
  final DateTime? completedAt;

  const HealthProfile({
    this.schemaVersion,
    this.primarySupport,
    this.nutritionProfile,
    this.workoutProfile,
    this.safetyProfile,
    this.completedAt,
  });

  bool get includesExercise =>
      primarySupport == 'EXERCISE' || primarySupport == 'BOTH';
  bool get includesNutrition =>
      primarySupport == 'NUTRITION' || primarySupport == 'BOTH';

  bool get hasCompletedCurrentAccountIntake =>
      (schemaVersion ?? 0) >= currentSchemaVersion &&
      supportedPrimarySupport.contains(primarySupport) &&
      (!includesExercise ||
          (workoutProfile?.hasCompletedCurrentAccountIntake ?? false));

  static HealthProfile? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final json = Map<String, dynamic>.from(raw);
    return HealthProfile(
      schemaVersion: (json['schema_version'] as num?)?.toInt(),
      primarySupport: (json['primary_support'] as String?)?.toUpperCase(),
      nutritionProfile: NutritionProfile.fromJson(json['nutrition_profile']),
      workoutProfile: WorkoutProfile.fromJson(json['workout_profile']),
      safetyProfile: SafetyProfile.fromJson(json['safety_profile']),
      completedAt: DateTime.tryParse(json['completed_at']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
        'schema_version': schemaVersion ?? currentSchemaVersion,
        if (primarySupport != null) 'primary_support': primarySupport,
        if (nutritionProfile != null)
          'nutrition_profile': nutritionProfile!.toJson(),
        if (workoutProfile != null) 'workout_profile': workoutProfile!.toJson(),
        if (safetyProfile != null) 'safety_profile': safetyProfile!.toJson(),
        if (completedAt != null)
          'completed_at': completedAt!.toUtc().toIso8601String(),
      };

  static HealthProfile completeAccountIntake({
    required String primarySupport,
    required NutritionProfile nutritionProfile,
    WorkoutProfile? workoutProfile,
    SafetyProfile? safetyProfile,
    DateTime? now,
  }) {
    final support = primarySupport.trim().toUpperCase();
    if (!supportedPrimarySupport.contains(support)) {
      throw ArgumentError('INVALID_PRIMARY_SUPPORT');
    }
    if ((support == 'EXERCISE' || support == 'BOTH') &&
        !(workoutProfile?.hasCompletedCurrentAccountIntake ?? false)) {
      throw ArgumentError('INCOMPLETE_ACCOUNT_WORKOUT_INTAKE');
    }
    return HealthProfile(
      schemaVersion: currentSchemaVersion,
      primarySupport: support,
      nutritionProfile: nutritionProfile,
      workoutProfile: workoutProfile,
      safetyProfile: safetyProfile,
      completedAt: (now ?? DateTime.now()).toUtc(),
    );
  }
}

/// Structured safety data remains distinct from free-text profile notes.
/// `nutritionSafetySnapshot` merely mirrors the already canonical safety
/// answers used by the frozen nutrition policy; it does not alter that policy.
class SafetyProfile {
  final Map<String, dynamic>? exerciseSafetyProfile;
  final Map<String, dynamic>? nutritionSafetySnapshot;
  final Map<String, String>? provenance;
  final Map<String, String>? freshness;

  const SafetyProfile({
    this.exerciseSafetyProfile,
    this.nutritionSafetySnapshot,
    this.provenance,
    this.freshness,
  });

  static SafetyProfile? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final json = Map<String, dynamic>.from(raw);
    Map<String, dynamic>? map(String key) =>
        json[key] is Map ? Map<String, dynamic>.from(json[key] as Map) : null;
    final provenance = json['provenance'] is Map
        ? Map<String, String>.fromEntries((json['provenance'] as Map)
            .entries
            .where((entry) => entry.key is String && entry.value is String)
            .map((entry) =>
                MapEntry(entry.key as String, entry.value as String)))
        : null;
    final freshness = json['freshness'] is Map
        ? Map<String, String>.fromEntries((json['freshness'] as Map)
            .entries
            .where((entry) => entry.key is String && entry.value is String)
            .map((entry) => MapEntry(
                entry.key as String, (entry.value as String).toUpperCase())))
        : null;
    return SafetyProfile(
      exerciseSafetyProfile: map('exercise_safety_profile'),
      nutritionSafetySnapshot: map('nutrition_safety_snapshot'),
      provenance: provenance,
      freshness: freshness,
    );
  }

  Map<String, dynamic> toJson() => {
        if (exerciseSafetyProfile != null)
          'exercise_safety_profile': exerciseSafetyProfile,
        if (nutritionSafetySnapshot != null)
          'nutrition_safety_snapshot': nutritionSafetySnapshot,
        if (provenance != null) 'provenance': provenance,
        if (freshness != null) 'freshness': freshness,
      };
}

/// Explicitly nullable fields are persisted beneath ``workout_profile``.
/// Values are self-reports only; the backend maps absent values to an explicit
/// missing/not-loaded status instead of inferring experience or equipment.
class WorkoutProfile {
  /// Increment this when the account intake gains a newly required question.
  /// Accounts holding an older version are routed through the short update
  /// form at their next authenticated app entry.
  static const currentAccountIntakeVersion = 1;

  /// Freshness is field-specific. The backend E4 adapter remains the
  /// enforcement point and treats `current_pain_status` as stale unless the
  /// linked `safety_checked_at` is from today.
  static const fieldFreshness = <String, String>{
    'training_experience': 'STABLE_UNTIL_CHANGED',
    'training_experience_detail': 'STABLE_UNTIL_CHANGED',
    'available_days_per_week': 'PERIODIC_CONFIRMATION',
    'preferred_training_days': 'PERIODIC_CONFIRMATION',
    'default_session_duration_minutes': 'PERIODIC_CONFIRMATION',
    'training_location': 'PERIODIC_CONFIRMATION',
    'available_equipment': 'PERIODIC_CONFIRMATION',
    'preferred_exercises': 'PERIODIC_CONFIRMATION',
    'disliked_exercises': 'PERIODIC_CONFIRMATION',
    'exercise_exclusions': 'STABLE_UNTIL_CHANGED',
    'self_reported_limitations': 'TIME_SENSITIVE',
    'current_pain_status': 'CURRENT_OBSERVATION',
    'exercise_safety_profile': 'TIME_SENSITIVE',
  };

  static String freshnessForField(String field) =>
      fieldFreshness[field] ?? 'STABLE_UNTIL_CHANGED';

  final String? trainingExperience;

  /// The user's original description (for example, "đã tập vài tháng").
  /// It is deliberately separate from the policy enum above: elapsed time
  /// alone must never be promoted to EXPERIENCED.
  final String? trainingExperienceDetail;
  final int? availableDaysPerWeek;
  final List<String>? preferredTrainingDays;
  final int? defaultSessionDurationMinutes;
  final String? trainingLocation;
  final List<String>? availableEquipment;
  final List<String>? preferredExercises;
  final List<String>? dislikedExercises;
  final List<String>? exerciseExclusions;
  final List<String>? selfReportedLimitations;
  final String? additionalWorkoutPreferencesNote;
  final String? currentPainStatus;
  final Map<String, dynamic>? exerciseSafetyProfile;

  /// Chat intake is captured immediately, then explicitly confirmed before a
  /// future planner may rely on the captured revision.
  final String? intakeConfirmationStatus;
  final int? intakeRevision;
  final DateTime? intakeCapturedAt;
  final DateTime? intakeConfirmedAt;

  /// A no-pain answer is a point-in-time self-report, not durable clearance.
  final DateTime? safetyCheckedAt;

  /// Separate from chat revisions: this records that the account-level
  /// exercise and safety questionnaire was explicitly completed.
  final int? accountIntakeVersion;
  final DateTime? accountIntakeCompletedAt;

  const WorkoutProfile({
    this.trainingExperience,
    this.trainingExperienceDetail,
    this.availableDaysPerWeek,
    this.preferredTrainingDays,
    this.defaultSessionDurationMinutes,
    this.trainingLocation,
    this.availableEquipment,
    this.preferredExercises,
    this.dislikedExercises,
    this.exerciseExclusions,
    this.selfReportedLimitations,
    this.additionalWorkoutPreferencesNote,
    this.currentPainStatus,
    this.exerciseSafetyProfile,
    this.intakeConfirmationStatus,
    this.intakeRevision,
    this.intakeCapturedAt,
    this.intakeConfirmedAt,
    this.safetyCheckedAt,
    this.accountIntakeVersion,
    this.accountIntakeCompletedAt,
  });

  static List<String>? _strings(Object? value) => value is List
      ? value
          .whereType<String>()
          .where((item) => item.trim().isNotEmpty)
          .toList()
      : null;

  static WorkoutProfile? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final json = Map<String, dynamic>.from(raw);
    return WorkoutProfile(
      trainingExperience: json['training_experience'] as String?,
      trainingExperienceDetail: json['training_experience_detail'] as String?,
      availableDaysPerWeek: json['available_days_per_week'] as int?,
      preferredTrainingDays: _strings(json['preferred_training_days']),
      defaultSessionDurationMinutes:
          json['default_session_duration_minutes'] as int?,
      trainingLocation: json['training_location'] as String?,
      availableEquipment: _strings(json['available_equipment']),
      preferredExercises: _strings(json['preferred_exercises']),
      dislikedExercises: _strings(json['disliked_exercises']),
      exerciseExclusions: _strings(json['exercise_exclusions']),
      selfReportedLimitations: _strings(json['self_reported_limitations']),
      additionalWorkoutPreferencesNote:
          json['additional_workout_preferences_note'] as String?,
      currentPainStatus: json['current_pain_status'] as String?,
      exerciseSafetyProfile: json['exercise_safety_profile'] is Map
          ? Map<String, dynamic>.from(json['exercise_safety_profile'] as Map)
          : null,
      intakeConfirmationStatus: json['intake_confirmation_status'] as String?,
      intakeRevision: json['intake_revision'] as int?,
      intakeCapturedAt:
          DateTime.tryParse(json['intake_captured_at']?.toString() ?? ''),
      intakeConfirmedAt:
          DateTime.tryParse(json['intake_confirmed_at']?.toString() ?? ''),
      safetyCheckedAt:
          DateTime.tryParse(json['safety_checked_at']?.toString() ?? ''),
      accountIntakeVersion: (json['account_intake_version'] as num?)?.toInt(),
      accountIntakeCompletedAt: DateTime.tryParse(
          json['account_intake_completed_at']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
        if (trainingExperience != null)
          'training_experience': trainingExperience,
        if (trainingExperienceDetail != null)
          'training_experience_detail': trainingExperienceDetail,
        if (availableDaysPerWeek != null)
          'available_days_per_week': availableDaysPerWeek,
        if (preferredTrainingDays != null)
          'preferred_training_days': preferredTrainingDays,
        if (defaultSessionDurationMinutes != null)
          'default_session_duration_minutes': defaultSessionDurationMinutes,
        if (trainingLocation != null) 'training_location': trainingLocation,
        if (availableEquipment != null)
          'available_equipment': availableEquipment,
        if (preferredExercises != null)
          'preferred_exercises': preferredExercises,
        if (dislikedExercises != null) 'disliked_exercises': dislikedExercises,
        if (exerciseExclusions != null)
          'exercise_exclusions': exerciseExclusions,
        if (selfReportedLimitations != null)
          'self_reported_limitations': selfReportedLimitations,
        if (additionalWorkoutPreferencesNote != null)
          'additional_workout_preferences_note':
              additionalWorkoutPreferencesNote,
        if (currentPainStatus != null) 'current_pain_status': currentPainStatus,
        if (exerciseSafetyProfile != null)
          'exercise_safety_profile': exerciseSafetyProfile,
        if (intakeConfirmationStatus != null)
          'intake_confirmation_status': intakeConfirmationStatus,
        if (intakeRevision != null) 'intake_revision': intakeRevision,
        if (intakeCapturedAt != null)
          'intake_captured_at': intakeCapturedAt!.toUtc().toIso8601String(),
        if (intakeConfirmedAt != null)
          'intake_confirmed_at': intakeConfirmedAt!.toUtc().toIso8601String(),
        if (safetyCheckedAt != null)
          'safety_checked_at': safetyCheckedAt!.toUtc().toIso8601String(),
        if (accountIntakeVersion != null)
          'account_intake_version': accountIntakeVersion,
        if (accountIntakeCompletedAt != null)
          'account_intake_completed_at':
              accountIntakeCompletedAt!.toUtc().toIso8601String(),
      };

  /// Whether this account has explicitly answered every question required by
  /// the current workout/safety onboarding version. An explicit `UNKNOWN` is
  /// a valid answer; a missing key is not silently treated as one.
  bool get hasCompletedCurrentAccountIntake {
    final safety = exerciseSafetyProfile;
    return (accountIntakeVersion ?? 0) >= currentAccountIntakeVersion &&
        trainingExperience != null &&
        availableDaysPerWeek != null &&
        defaultSessionDurationMinutes != null &&
        trainingLocation != null &&
        availableEquipment != null &&
        currentPainStatus != null &&
        safety != null &&
        safety.containsKey('health_state') &&
        safety.containsKey('pregnancy_status') &&
        safety.containsKey('warning_symptoms') &&
        safety.containsKey('acute_injury') &&
        safety.containsKey('recent_surgery') &&
        safety.containsKey('technique_screen_confirmed');
  }

  /// Complete the account-level form in one explicit user action. The same
  /// strict field validation as the chatbot path is used, then the submitted
  /// values are marked confirmed because the user has reviewed this form.
  static WorkoutProfile completeAccountIntake(
    WorkoutProfile? current,
    Map<String, dynamic> patch, {
    DateTime? now,
  }) {
    const requiredFields = {
      'training_experience',
      'available_days_per_week',
      'default_session_duration_minutes',
      'training_location',
      'available_equipment',
      'current_pain_status',
      'exercise_safety_profile',
    };
    if (!patch.keys.toSet().containsAll(requiredFields)) {
      throw ArgumentError('INCOMPLETE_ACCOUNT_WORKOUT_INTAKE');
    }
    final captured = applyChatUpdate(current, patch, mode: 'CAPTURE', now: now);
    final confirmed =
        applyChatUpdate(captured, const {}, mode: 'CONFIRM', now: now);
    return _withAccountIntakeMetadata(
      confirmed,
      version: currentAccountIntakeVersion,
      completedAt: (now ?? DateTime.now()).toUtc(),
    );
  }

  static WorkoutProfile _withAccountIntakeMetadata(
    WorkoutProfile profile, {
    required int version,
    required DateTime completedAt,
  }) =>
      WorkoutProfile(
        trainingExperience: profile.trainingExperience,
        trainingExperienceDetail: profile.trainingExperienceDetail,
        availableDaysPerWeek: profile.availableDaysPerWeek,
        preferredTrainingDays: profile.preferredTrainingDays,
        defaultSessionDurationMinutes: profile.defaultSessionDurationMinutes,
        trainingLocation: profile.trainingLocation,
        availableEquipment: profile.availableEquipment,
        preferredExercises: profile.preferredExercises,
        dislikedExercises: profile.dislikedExercises,
        exerciseExclusions: profile.exerciseExclusions,
        selfReportedLimitations: profile.selfReportedLimitations,
        additionalWorkoutPreferencesNote:
            profile.additionalWorkoutPreferencesNote,
        currentPainStatus: profile.currentPainStatus,
        exerciseSafetyProfile: profile.exerciseSafetyProfile,
        intakeConfirmationStatus: profile.intakeConfirmationStatus,
        intakeRevision: profile.intakeRevision,
        intakeCapturedAt: profile.intakeCapturedAt,
        intakeConfirmedAt: profile.intakeConfirmedAt,
        safetyCheckedAt: profile.safetyCheckedAt,
        accountIntakeVersion: version,
        accountIntakeCompletedAt: completedAt,
      );

  /// Apply one explicit chat intake patch. This is intentionally strict so
  /// free-form model text cannot silently create an invalid E4 profile.
  ///
  /// `capture` stores an unconfirmed revision immediately. `confirm` accepts
  /// no field patch and marks the latest captured revision as user-confirmed.
  static WorkoutProfile applyChatUpdate(
    WorkoutProfile? current,
    Map<String, dynamic> patch, {
    required String mode,
    DateTime? now,
  }) {
    final timestamp = (now ?? DateTime.now()).toUtc();
    final base = current ?? const WorkoutProfile();
    final normalizedMode = mode.trim().toUpperCase();
    if (normalizedMode == 'CONFIRM') {
      if (patch.isNotEmpty || base.intakeRevision == null) {
        throw ArgumentError('INVALID_WORKOUT_PROFILE_CONFIRMATION');
      }
      return WorkoutProfile(
        trainingExperience: base.trainingExperience,
        trainingExperienceDetail: base.trainingExperienceDetail,
        availableDaysPerWeek: base.availableDaysPerWeek,
        preferredTrainingDays: base.preferredTrainingDays,
        defaultSessionDurationMinutes: base.defaultSessionDurationMinutes,
        trainingLocation: base.trainingLocation,
        availableEquipment: base.availableEquipment,
        preferredExercises: base.preferredExercises,
        dislikedExercises: base.dislikedExercises,
        exerciseExclusions: base.exerciseExclusions,
        selfReportedLimitations: base.selfReportedLimitations,
        additionalWorkoutPreferencesNote: base.additionalWorkoutPreferencesNote,
        currentPainStatus: base.currentPainStatus,
        exerciseSafetyProfile: base.exerciseSafetyProfile,
        intakeConfirmationStatus: 'CONFIRMED',
        intakeRevision: base.intakeRevision,
        intakeCapturedAt: base.intakeCapturedAt,
        intakeConfirmedAt: timestamp,
        safetyCheckedAt: base.safetyCheckedAt,
        accountIntakeVersion: base.accountIntakeVersion,
        accountIntakeCompletedAt: base.accountIntakeCompletedAt,
      );
    }
    if (normalizedMode != 'CAPTURE' || patch.isEmpty) {
      throw ArgumentError('INVALID_WORKOUT_PROFILE_PATCH');
    }

    String? text(String key, String? fallback, {int maxLength = 160}) {
      if (!patch.containsKey(key)) return fallback;
      final value = patch[key];
      if (value is! String ||
          value.trim().isEmpty ||
          value.trim().length > maxLength) {
        throw ArgumentError('INVALID_WORKOUT_PROFILE_$key');
      }
      return value.trim();
    }

    int? boundedInt(String key, int? fallback, int min, int max) {
      if (!patch.containsKey(key)) return fallback;
      final value = patch[key];
      if (value is! int || value < min || value > max) {
        throw ArgumentError('INVALID_WORKOUT_PROFILE_$key');
      }
      return value;
    }

    List<String>? strings(String key, List<String>? fallback) {
      if (!patch.containsKey(key)) return fallback;
      final value = patch[key];
      if (value is! List ||
          value.any((item) => item is! String || item.trim().isEmpty)) {
        throw ArgumentError('INVALID_WORKOUT_PROFILE_$key');
      }
      return value
          .map((item) => (item as String).trim())
          .toList(growable: false);
    }

    Map<String, dynamic>? safety(
      Map<String, dynamic>? fallback,
    ) {
      if (!patch.containsKey('exercise_safety_profile')) return fallback;
      final value = patch['exercise_safety_profile'];
      if (value is! Map) {
        throw ArgumentError('INVALID_WORKOUT_PROFILE_exercise_safety_profile');
      }
      const allowed = {
        'health_state',
        'pregnancy_status',
        'warning_symptoms',
        'acute_injury',
        'recent_surgery',
        'technique_screen_confirmed',
      };
      final merged = <String, dynamic>{...?fallback};
      for (final entry in value.entries) {
        final key = entry.key;
        if (key is! String || !allowed.contains(key)) {
          throw ArgumentError(
              'INVALID_WORKOUT_PROFILE_exercise_safety_profile');
        }
        final item = entry.value;
        final valid = switch (key) {
          'health_state' ||
          'pregnancy_status' =>
            item is String && item.trim().isNotEmpty,
          'warning_symptoms' => item is List &&
              item.every(
                  (symptom) => symptom is String && symptom.trim().isNotEmpty),
          _ => item is bool,
        };
        if (!valid) {
          throw ArgumentError(
              'INVALID_WORKOUT_PROFILE_exercise_safety_profile');
        }
        merged[key] = item is String
            ? item.trim()
            : item is List
                ? item
                    .map((symptom) => (symptom as String).trim())
                    .toList(growable: false)
                : item;
      }
      return merged;
    }

    final experience = text('training_experience', base.trainingExperience);
    if (experience != null &&
        !const {'NOVICE', 'EXPERIENCED', 'UNKNOWN'}
            .contains(experience.toUpperCase())) {
      throw ArgumentError('INVALID_WORKOUT_PROFILE_training_experience');
    }
    final pain = text('current_pain_status', base.currentPainStatus);
    if (pain != null &&
        !const {'YES', 'NO', 'UNKNOWN'}.contains(pain.toUpperCase())) {
      throw ArgumentError('INVALID_WORKOUT_PROFILE_current_pain_status');
    }

    return WorkoutProfile(
      trainingExperience: experience?.toUpperCase(),
      trainingExperienceDetail:
          text('training_experience_detail', base.trainingExperienceDetail),
      availableDaysPerWeek: boundedInt(
          'available_days_per_week', base.availableDaysPerWeek, 1, 7),
      preferredTrainingDays:
          strings('preferred_training_days', base.preferredTrainingDays),
      defaultSessionDurationMinutes: boundedInt(
        'default_session_duration_minutes',
        base.defaultSessionDurationMinutes,
        10,
        180,
      ),
      trainingLocation: text('training_location', base.trainingLocation),
      availableEquipment:
          strings('available_equipment', base.availableEquipment),
      preferredExercises:
          strings('preferred_exercises', base.preferredExercises),
      dislikedExercises: strings('disliked_exercises', base.dislikedExercises),
      exerciseExclusions:
          strings('exercise_exclusions', base.exerciseExclusions),
      selfReportedLimitations:
          strings('self_reported_limitations', base.selfReportedLimitations),
      additionalWorkoutPreferencesNote: text(
        'additional_workout_preferences_note',
        base.additionalWorkoutPreferencesNote,
        maxLength: NutritionProfile.maxNoteLength,
      ),
      currentPainStatus: pain?.toUpperCase(),
      exerciseSafetyProfile: safety(base.exerciseSafetyProfile),
      intakeConfirmationStatus: 'PENDING_CONFIRMATION',
      intakeRevision: (base.intakeRevision ?? 0) + 1,
      intakeCapturedAt: timestamp,
      intakeConfirmedAt: null,
      safetyCheckedAt: patch.containsKey('current_pain_status') ||
              patch.containsKey('exercise_safety_profile')
          ? timestamp
          : base.safetyCheckedAt,
      accountIntakeVersion: base.accountIntakeVersion,
      accountIntakeCompletedAt: base.accountIntakeCompletedAt,
    );
  }
}
