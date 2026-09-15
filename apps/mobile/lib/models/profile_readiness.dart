import 'user_model.dart';

enum ProfileContextScope { nutrition, workout, both, general }

/// Shared account gate and a scoped list of unanswered personalization fields.
/// Empty confirmed lists mean "none"; absent or unconfirmed lists do not.
class ProfileReadiness {
  final ProfileContextScope scope;
  final Map<String, String> requiredFields;
  final Map<String, String> personalizationFields;

  const ProfileReadiness({
    required this.scope,
    required this.requiredFields,
    required this.personalizationFields,
  });

  bool get canSend => requiredFields.isEmpty;
  bool get hasMissingFields =>
      requiredFields.isNotEmpty || personalizationFields.isNotEmpty;

  Map<String, String> get missingFields => {
        ...requiredFields,
        ...personalizationFields,
      };

  Map<String, Object> toJson() => {
        'scope': scope.name,
        'required_fields': requiredFields.keys.toList(growable: false),
        'personalization_fields':
            personalizationFields.keys.toList(growable: false),
        'account_ready': canSend,
        'personalization_ready': !hasMissingFields,
      };

  /// Inputs required by the deterministic energy calculation used to create
  /// a plan. General gender is deliberately not used as an equation input.
  static Map<String, String> planCreationMissingFields(UserModel user) => {
        if (user.age < 10 || user.age > 120) 'age': 'tuổi',
        if (!user.height.isFinite || user.height < 100 || user.height > 250)
          'height': 'chiều cao',
        if (!user.weight.isFinite || user.weight < 30 || user.weight > 300)
          'weight': 'cân nặng',
        if (!const {'male', 'female'}.contains(user.equationSex))
          'equation_sex': 'thông tin ước tính năng lượng',
        if (!const {'sedentary', 'light', 'moderate', 'active', 'very_active'}
            .contains(user.activityLevel))
          'activity_level': 'mức độ vận động',
        if (!const {'lose_weight', 'maintain', 'gain_muscle'}
            .contains(user.healthGoal))
          'health_goal': 'mục tiêu sức khỏe',
      };

  factory ProfileReadiness.assess(
    UserModel user, {
    ProfileContextScope scope = ProfileContextScope.general,
  }) {
    final required = {...user.missingBasicProfileFields};
    if (user.basicProfileCompletedAt == null) {
      if (user.gender == null) {
        required['gender'] = 'Giới tính hoặc lựa chọn không cung cấp';
      }
      required['basic_profile_confirmation'] = 'Xác nhận thông tin cá nhân';
    }
    if (user.needsAccountHealthIntake) {
      required['health_profile'] = 'Hồ sơ dinh dưỡng và tập luyện';
    }
    final additional = <String, String>{};
    if (scope == ProfileContextScope.nutrition ||
        scope == ProfileContextScope.both) {
      final nutrition = user.effectiveNutritionProfile;
      if (nutrition?.foodAllergies == null ||
          !(nutrition?.isConfirmedField('food_allergies') ?? false)) {
        additional['nutrition_profile.food_allergies'] =
            'Dị ứng thực phẩm (kể cả xác nhận không có)';
      }
      if (nutrition?.dietaryRestrictions == null ||
          !(nutrition?.isConfirmedField('dietary_restrictions') ?? false)) {
        additional['nutrition_profile.dietary_restrictions'] =
            'Chế độ và hạn chế ăn uống';
      }
      if (user.equationSex == null) {
        additional['equation_sex'] =
            'Thông tin ước tính năng lượng (cần để lập kế hoạch)';
      }
      const safetyLabels = {
        'pregnancy': 'Thông tin thai kỳ',
        'lactation': 'Thông tin cho con bú',
        'eating_disorder_risk_or_history': 'Sàng lọc rối loạn ăn uống',
        'serious_renal_condition': 'Tình trạng thận',
        'fluid_restricted_cardiac_condition': 'Tình trạng tim và hạn chế dịch',
        'clinically_complex_metabolic_condition': 'Tình trạng chuyển hóa',
      };
      for (final entry in user.nutritionSafetyProfile.toJson().entries) {
        final isMaternalSafetyField =
            entry.key == 'pregnancy' || entry.key == 'lactation';
        final asksMaternalSafetyQuestions =
            user.gender?.trim().toLowerCase() == 'female';
        if (isMaternalSafetyField && !asksMaternalSafetyQuestions) continue;
        if (entry.value == 'NOT_PROVIDED' || entry.value == 'UNKNOWN') {
          additional['nutrition_safety_profile.${entry.key}'] =
              safetyLabels[entry.key]!;
        }
      }
    }
    if (scope == ProfileContextScope.workout ||
        scope == ProfileContextScope.both) {
      final workout = user.effectiveWorkoutProfile;
      if (!(workout?.hasCompletedCurrentAccountIntake ?? false)) {
        additional['workout_profile'] =
            'Kinh nghiệm, lịch tập, dụng cụ và an toàn tập luyện';
      }
    }
    return ProfileReadiness(
      scope: scope,
      requiredFields: Map.unmodifiable(required),
      personalizationFields: Map.unmodifiable(additional),
    );
  }

  static ProfileContextScope scopeForMessage(String message) {
    final normalized = message.toLowerCase();
    final nutrition = RegExp(
      r'(ăn|uống|món|bữa|thực đơn|dinh dưỡng|calo|đạm|protein|carb|kiêng|dị ứng|giảm cân|tăng cân)',
    ).hasMatch(normalized);
    final workout = RegExp(
      r'(tập|workout|bài tập|hiệp|reps|rpe|rir|tạ|gym|chạy|cardio|cơ bụng|cơ vai|cơ ngực)',
    ).hasMatch(normalized);
    if (nutrition && workout) return ProfileContextScope.both;
    if (nutrition) return ProfileContextScope.nutrition;
    if (workout) return ProfileContextScope.workout;
    return ProfileContextScope.general;
  }
}
