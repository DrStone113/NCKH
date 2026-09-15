import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../models/app_state_value.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/profile_wizard.dart';
import '../../../widgets/health_surface.dart';
import '../../settings/screens/profile_settings_screen.dart';

/// Account-level workout and safety intake.
///
/// This is intentionally shown by [AuthWrapper] before the home screen for a
/// newly registered account and for an older intake schema version. The data
/// is then shared with chat, rather than asking the same questions in chat.
class WorkoutAccountIntakeScreen extends StatefulWidget {
  const WorkoutAccountIntakeScreen(
      {super.key, this.initialSupport, this.onSaved});

  final String? initialSupport;
  final VoidCallback? onSaved;

  @override
  State<WorkoutAccountIntakeScreen> createState() =>
      _WorkoutAccountIntakeScreenState();
}

class _WorkoutAccountIntakeScreenState
    extends State<WorkoutAccountIntakeScreen> {
  int _step = 0;
  String? _primarySupport;
  String? _experience;
  int? _daysPerWeek;
  int? _durationMinutes;
  String? _location;
  final Set<String> _equipment = <String>{};
  String? _pain;
  String? _healthState;
  String? _gender;
  String? _pregnancyStatus;
  bool? _hasWarningSymptoms;
  final Set<String> _warningSymptoms = <String>{};
  bool? _acuteInjury;
  bool? _recentSurgery;
  bool _understandsSafety = false;
  bool _saving = false;
  String? _error;
  bool _loadedInitialValues = false;
  bool _hasCompletedWorkoutIntake = false;
  bool _showOptionalNutrition = false;
  String? _nutritionGoal;
  final Set<String> _foodAllergies = <String>{};
  final Set<String> _dietaryRestrictions = <String>{};
  final Set<String> _preferredCuisines = <String>{};
  final Set<String> _mealPreferences = <String>{};
  bool _foodAllergiesTouched = false;
  bool _dietaryRestrictionsTouched = false;
  late final TextEditingController _allergyAndAvoidanceController;
  late final TextEditingController _foodPreferenceController;
  late final TextEditingController _nutritionGoalController;
  late final TextEditingController _foodDislikesController;
  late final TextEditingController _nutritionNotesController;
  late final TextEditingController _workoutPreferencesController;

  String get _profileGender => (_gender ?? '').trim().toLowerCase();

  /// Pregnancy is a sensitive, relevant question only for users who have
  /// self-identified as female. We do not infer an answer for an unknown or
  /// other profile; the safety policy keeps that state explicitly UNKNOWN.
  bool get _asksPregnancy => _profileGender == 'female';

  String get _implicitPregnancyStatus =>
      _profileGender == 'male' ? 'NOT_APPLICABLE' : 'UNKNOWN';

  bool get _requiresWorkout =>
      _primarySupport == 'EXERCISE' || _primarySupport == 'BOTH';

  bool get _needsWorkoutQuestions =>
      _requiresWorkout && !_hasCompletedWorkoutIntake;

  bool get _showsNutritionFirst =>
      _primarySupport == 'NUTRITION' ||
      _primarySupport == 'BOTH' ||
      _primarySupport == 'GENERAL_HEALTH';

  bool get _showsNutritionDetails =>
      _showsNutritionFirst || _showOptionalNutrition;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loadedInitialValues) return;
    _loadedInitialValues = true;
    final user = context.read<UserProvider>().currentUser;
    final profile = user?.workoutProfile;
    final nutrition = user?.nutritionProfile;
    final health = user?.healthProfile;
    _primarySupport = widget.initialSupport ?? health?.primarySupport;
    _hasCompletedWorkoutIntake =
        profile?.hasCompletedCurrentAccountIntake ?? false;
    _gender = user?.gender ?? 'not_provided';
    _allergyAndAvoidanceController = TextEditingController(
      text: nutrition?.allergyAndAvoidanceNote ?? '',
    );
    _foodPreferenceController = TextEditingController(
      text: nutrition?.foodPreferenceNote ?? '',
    );
    _nutritionGoalController = TextEditingController(
      text: nutrition?.goalDescription ?? nutrition?.nutritionGoalNote ?? '',
    );
    _foodDislikesController = TextEditingController(
      text: nutrition?.foodDislikesText ?? '',
    );
    _nutritionNotesController = TextEditingController(
      text: nutrition?.nutritionNotes ?? '',
    );
    _workoutPreferencesController = TextEditingController(
      text: profile?.additionalWorkoutPreferencesNote ?? '',
    );
    _nutritionGoal = nutrition?.nutritionGoal;
    _foodAllergies.addAll(nutrition?.foodAllergies ?? const []);
    _dietaryRestrictions.addAll(nutrition?.dietaryRestrictions ?? const []);
    _foodAllergiesTouched = nutrition?.foodAllergies != null;
    _dietaryRestrictionsTouched = nutrition?.dietaryRestrictions != null;
    _preferredCuisines.addAll(nutrition?.preferredCuisines ?? const []);
    _mealPreferences.addAll(nutrition?.mealPreferences ?? const []);
    final safety = profile?.exerciseSafetyProfile;
    _experience = profile?.trainingExperience;
    _daysPerWeek = profile?.availableDaysPerWeek;
    _durationMinutes = profile?.defaultSessionDurationMinutes;
    _location = profile?.trainingLocation;
    _equipment.addAll(profile?.availableEquipment ?? const []);
    _pain = profile?.currentPainStatus;
    _healthState = safety?['health_state'] as String?;
    _pregnancyStatus = safety?['pregnancy_status'] as String?;
    final symptoms = safety?['warning_symptoms'];
    if (symptoms is List) {
      _warningSymptoms.addAll(symptoms.whereType<String>());
      _hasWarningSymptoms = _warningSymptoms.isEmpty ? false : true;
    }
    _acuteInjury = safety?['acute_injury'] as bool?;
    _recentSurgery = safety?['recent_surgery'] as bool?;
    _understandsSafety = safety?['technique_screen_confirmed'] == true;
  }

  String? _workoutValidation() {
    final missing = <String>[
      if (_requiresWorkout) ...[
        if (_experience == null) 'kinh nghiệm tập luyện',
        if (_daysPerWeek == null) 'số ngày có thể tập',
        if (_durationMinutes == null) 'thời lượng buổi tập',
        if (_location == null) 'nơi tập',
        if (_equipment.isEmpty) 'dụng cụ',
        if (_pain == null) 'tình trạng đau hiện tại',
        if (_healthState == null) 'tình trạng sức khỏe',
        if (_asksPregnancy && _pregnancyStatus == null) 'thông tin thai kỳ',
        if (_hasWarningSymptoms == null) 'dấu hiệu cảnh báo',
        if (_hasWarningSymptoms == true && _warningSymptoms.isEmpty)
          'dấu hiệu cảnh báo cụ thể',
        if (_acuteInjury == null) 'chấn thương cấp',
        if (_recentSurgery == null) 'phẫu thuật gần đây',
      ],
    ];
    return missing.isEmpty
        ? null
        : 'Cần bổ sung: ${missing.take(3).join(', ')}${missing.length > 3 ? '…' : '.'}';
  }

  Future<void> _save() async {
    if (_primarySupport == null) {
      setState(() => _error = 'Hãy chọn điều bạn muốn được hỗ trợ chính.');
      return;
    }
    // A nutrition-only account must not be blocked by hidden workout or
    // pregnancy questions after confirming gender in the basic profile.
    final error = _workoutValidation();
    if (error != null) {
      setState(() {
        _error = error;
        _step = 1;
      });
      return;
    }

    setState(() {
      _saving = true;
      _error = null;
    });
    final answers = <String, dynamic>{
      'training_experience': _experience,
      'available_days_per_week': _daysPerWeek,
      'default_session_duration_minutes': _durationMinutes,
      'training_location': _location,
      'available_equipment': _equipment.toList(growable: false),
      if (_workoutPreferencesController.text.trim().isNotEmpty)
        'additional_workout_preferences_note':
            _workoutPreferencesController.text,
      'current_pain_status': _pain,
      'exercise_safety_profile': <String, dynamic>{
        'health_state': _healthState,
        'pregnancy_status':
            _asksPregnancy ? _pregnancyStatus : _implicitPregnancyStatus,
        'warning_symptoms': _hasWarningSymptoms == true
            ? _warningSymptoms.toList(growable: false)
            : <String>[],
        'acute_injury': _acuteInjury,
        'recent_surgery': _recentSurgery,
        'technique_screen_confirmed': _understandsSafety,
      },
    };
    final result =
        await context.read<UserProvider>().completeAccountHealthIntake(
              primarySupport: _primarySupport!,
              workoutAnswers:
                  _requiresWorkout ? answers : const <String, dynamic>{},
              gender: _gender == 'not_provided' ? null : _gender,
              allergyAndAvoidanceNote: _allergyAndAvoidanceController.text,
              foodPreferenceNote: _foodPreferenceController.text,
              nutritionGoalNote: _nutritionGoalController.text,
              nutritionGoal: _nutritionGoal,
              foodAllergies: _foodAllergiesTouched || _foodAllergies.isNotEmpty
                  ? _foodAllergies.toList(growable: false)
                  : null,
              dietaryRestrictions:
                  _dietaryRestrictionsTouched || _dietaryRestrictions.isNotEmpty
                      ? _dietaryRestrictions.toList(growable: false)
                      : null,
              preferredCuisines: _preferredCuisines.isEmpty
                  ? null
                  : _preferredCuisines.toList(growable: false),
              mealPreferences: _mealPreferences.isEmpty
                  ? null
                  : _mealPreferences.toList(growable: false),
              foodDislikesText: _foodDislikesController.text,
              nutritionNotes: _nutritionNotesController.text,
            );
    if (!mounted) return;
    if (!result.isPersisted) {
      setState(() {
        _saving = false;
        _error = result.status == WriteStatus.rejected
            ? 'Dữ liệu chưa hợp lệ. Hãy kiểm tra lại các câu trả lời.'
            : 'Chưa thể lưu hồ sơ. Vui lòng thử lại khi có mạng.';
      });
      return;
    }
    // AuthWrapper observes the provider update and opens HomeScreen.
    setState(() => _saving = false);
    widget.onSaved?.call();
  }

  @override
  void dispose() {
    _allergyAndAvoidanceController.dispose();
    _foodPreferenceController.dispose();
    _nutritionGoalController.dispose();
    _foodDislikesController.dispose();
    _nutritionNotesController.dispose();
    _workoutPreferencesController.dispose();
    super.dispose();
  }

  void _back() {
    if (_step > 0) {
      setState(() {
        _step--;
        _error = null;
      });
    } else if (widget.onSaved != null) {
      Navigator.maybePop(context);
    } else {
      Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => const ProfileSettingsScreen()));
    }
  }

  void _next() {
    FocusManager.instance.primaryFocus?.unfocus();
    if (_primarySupport == null) {
      setState(() => _error = 'Chọn điều bạn muốn được hỗ trợ.');
      return;
    }
    if (_step == 1) {
      final error = _workoutValidation();
      if (error != null) {
        setState(() => _error = error);
        return;
      }
    }
    if (_step == 2) {
      _save();
      return;
    }
    setState(() {
      _error = null;
      _step++;
    });
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: _step == 0 && widget.onSaved != null,
        onPopInvokedWithResult: (didPop, result) {
          if (!didPop && !_saving) _back();
        },
        child: Scaffold(
          appBar: AppBar(
              title: const Text('Hồ sơ sức khỏe'),
              automaticallyImplyLeading: false,
              leading: IconButton(
                  tooltip: 'Quay lại',
                  onPressed: _saving ? null : _back,
                  icon: const Icon(Icons.arrow_back_rounded))),
          body: SafeArea(
              child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                  child: Center(
                      child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 600),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          ProfileStepHeader(
                              step: _step + 4,
                              total: 6,
                              title: [
                                'Ăn uống theo cách của bạn',
                                'Vận động phù hợp với bạn',
                                'Xác nhận hồ sơ'
                              ][_step],
                              subtitle: [
                                'Tách riêng dị ứng, hạn chế ăn và sở thích để gợi ý đúng hơn.',
                                'Chia sẻ điều kiện tập và những lưu ý an toàn.',
                                'Kiểm tra lại thông tin trước khi hoàn tất.'
                              ][_step]),
                          Visibility(
                              visible: _step == 0,
                              maintainState: true,
                              child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    _section(
                                        'Bạn muốn mình hỗ trợ điều gì nhất?'),
                                    _choiceCards<String>(
                                      icon: Icons.auto_awesome_outlined,
                                      label:
                                          'Chọn ưu tiên hiện tại để mình sắp xếp câu hỏi phù hợp.',
                                      helper:
                                          'Bạn vẫn có thể bổ sung thông tin ở lĩnh vực khác bất cứ lúc nào.',
                                      value: _primarySupport,
                                      choices: const {
                                        'NUTRITION': 'Ăn uống & dinh dưỡng',
                                        'EXERCISE': 'Tập luyện',
                                        'BOTH': 'Cả ăn uống và tập luyện',
                                        'GENERAL_HEALTH': 'Sức khỏe chung',
                                      },
                                      onChanged: (value) => setState(() {
                                        _primarySupport = value;
                                        _error = null;
                                      }),
                                    ),
                                    if (_needsWorkoutQuestions)
                                      const _SafetyNote(),
                                    if (_showsNutritionDetails)
                                      _section('Ăn uống'),
                                    if (!_showsNutritionDetails)
                                      _optionalNutritionButton(),
                                    if (_showsNutritionDetails)
                                      _textAnswer(
                                        controller:
                                            _allergyAndAvoidanceController,
                                        icon: Icons.no_food_outlined,
                                        label:
                                            'Có món hoặc thành phần nào bạn cần tránh không?',
                                        hint:
                                            'Ví dụ: dị ứng tôm, không uống sữa, ăn chay, không ăn thịt heo…',
                                      ),
                                    if (_showsNutritionDetails)
                                      _textAnswer(
                                        controller: _foodPreferenceController,
                                        icon: Icons.restaurant_menu_outlined,
                                        label:
                                            'Bạn thích hoặc muốn hạn chế kiểu ăn nào?',
                                        hint:
                                            'Ví dụ: thích món Việt, ít cay, thường ăn ngoài, muốn giảm đồ ngọt…',
                                      ),
                                    if (_showsNutritionDetails)
                                      _textAnswer(
                                        controller: _nutritionGoalController,
                                        icon: Icons.flag_outlined,
                                        label:
                                            'Mục tiêu hoặc ghi chú dinh dưỡng của bạn',
                                        hint:
                                            'Ví dụ: muốn đủ đạm hơn, tăng cân lành mạnh, ăn đúng giờ…',
                                      ),
                                    if (_showsNutritionDetails) ...[
                                      _choiceCards<String>(
                                        icon: Icons.flag_outlined,
                                        label:
                                            'Mục tiêu dinh dưỡng của bạn là gì?',
                                        helper:
                                            'Bạn có thể chọn “Chưa rõ” và cập nhật sau.',
                                        value: _nutritionGoal,
                                        choices: const {
                                          'LOSE_WEIGHT': 'Giảm cân',
                                          'MAINTAIN': 'Duy trì sức khỏe',
                                          'GAIN_WEIGHT': 'Tăng cân lành mạnh',
                                          'GAIN_MUSCLE': 'Tăng cơ',
                                          'IMPROVE_HABITS':
                                              'Ăn uống đều đặn hơn',
                                          'UNKNOWN':
                                              'Chưa rõ / chưa muốn trả lời',
                                        },
                                        onChanged: (value) => setState(
                                            () => _nutritionGoal = value),
                                      ),
                                      _multiSelectCard(
                                        icon: Icons.warning_amber_rounded,
                                        label:
                                            'Dị ứng đã biết hoặc thành phần cần tránh',
                                        helper:
                                            'Chỉ chọn khi bạn biết rõ. Ghi chú “Khác” vẫn được lưu nguyên văn để hỏi lại, không tự gán thành dị ứng.',
                                        values: _foodAllergies,
                                        choices: const {
                                          'CRUSTACEAN': 'Tôm, cua',
                                          'MOLLUSC': 'Mực, nghêu, sò',
                                          'FISH': 'Cá',
                                          'EGG': 'Trứng',
                                          'MILK': 'Sữa',
                                          'PEANUT': 'Đậu phộng',
                                          'TREE_NUT': 'Các loại hạt cây',
                                          'SOY': 'Đậu nành',
                                          'WHEAT_GLUTEN': 'Lúa mì / gluten',
                                          'SESAME': 'Mè',
                                        },
                                        onSelectionChanged: () =>
                                            _foodAllergiesTouched = true,
                                        noneLabel: 'Không có dị ứng đã biết',
                                        answered: _foodAllergiesTouched,
                                      ),
                                      _multiSelectCard(
                                        icon: Icons.tune_rounded,
                                        label: 'Chế độ hoặc hạn chế ăn uống',
                                        values: _dietaryRestrictions,
                                        choices: const {
                                          'vegetarian': 'Ăn chay',
                                          'vegan': 'Thuần chay',
                                          'no_seafood': 'Không ăn hải sản',
                                          'no_pork': 'Không ăn thịt heo',
                                          'no_beef': 'Không ăn thịt bò',
                                          'low_carb': 'Ưu tiên ít tinh bột',
                                          'high_protein': 'Ưu tiên giàu đạm',
                                        },
                                        onSelectionChanged: () =>
                                            _dietaryRestrictionsTouched = true,
                                        noneLabel: 'Không có hạn chế ăn uống',
                                        answered: _dietaryRestrictionsTouched,
                                      ),
                                      _multiSelectCard(
                                        icon: Icons.restaurant_outlined,
                                        label: 'Bạn thường thích ẩm thực nào?',
                                        values: _preferredCuisines,
                                        choices: const {
                                          'vietnamese': 'Món Việt',
                                          'asian': 'Món Á',
                                          'vegetarian': 'Món chay',
                                          'other': 'Không cố định',
                                        },
                                      ),
                                      _multiSelectCard(
                                        icon: Icons.schedule_outlined,
                                        label:
                                            'Thói quen bữa ăn (nếu muốn chia sẻ)',
                                        values: _mealPreferences,
                                        choices: const {
                                          'regular_meals': 'Ăn đúng bữa',
                                          'late_meals': 'Hay ăn muộn',
                                          'eat_out': 'Thường ăn ngoài',
                                          'home_cooked': 'Hay tự nấu',
                                        },
                                      ),
                                      _textAnswer(
                                        controller: _foodDislikesController,
                                        icon: Icons.thumb_down_alt_outlined,
                                        label:
                                            'Có món nào bạn không thích không? (tùy chọn)',
                                        hint:
                                            'Ví dụ: không thích rau mùi, nội tạng, món quá cay…',
                                      ),
                                      _textAnswer(
                                        controller: _nutritionNotesController,
                                        icon: Icons.note_alt_outlined,
                                        label:
                                            'Ghi chú thêm về ăn uống hoặc sức khỏe (tùy chọn)',
                                        hint:
                                            'Ví dụ: tôi khó chịu sau khi uống sữa — ứng dụng sẽ không tự coi đây là chẩn đoán.',
                                      ),
                                    ],
                                  ])),
                          Visibility(
                              visible: _step == 1,
                              maintainState: true,
                              child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    if (_needsWorkoutQuestions)
                                      _section('Tập luyện'),
                                    if (_requiresWorkout &&
                                        !_needsWorkoutQuestions) ...[
                                      _existingWorkoutNotice(),
                                      TextButton(
                                          onPressed: _saving
                                              ? null
                                              : () => setState(() =>
                                                  _hasCompletedWorkoutIntake =
                                                      false),
                                          child: const Text(
                                              'Chỉnh sửa tập luyện')),
                                    ],
                                    if (_needsWorkoutQuestions) ...[
                                      _dropdown<String>(
                                        label:
                                            'Bạn đã tập luyện có cấu trúc trước đây chưa?',
                                        value: _experience,
                                        items: const [
                                          DropdownMenuItem(
                                              value: 'NOVICE',
                                              child: Text(
                                                  'Tôi là người mới bắt đầu')),
                                          DropdownMenuItem(
                                              value: 'EXPERIENCED',
                                              child: Text(
                                                  'Tôi đã tập và tự thấy có kinh nghiệm')),
                                          DropdownMenuItem(
                                              value: 'UNKNOWN',
                                              child: Text(
                                                  'Chưa rõ / không muốn trả lời')),
                                        ],
                                        onChanged: (value) =>
                                            setState(() => _experience = value),
                                      ),
                                      _dropdown<int>(
                                        label:
                                            'Bạn thường có thể tập mấy ngày mỗi tuần?',
                                        value: _daysPerWeek,
                                        items: List.generate(
                                          7,
                                          (index) => DropdownMenuItem(
                                            value: index + 1,
                                            child:
                                                Text('${index + 1} ngày/tuần'),
                                          ),
                                        ),
                                        onChanged: (value) => setState(
                                            () => _daysPerWeek = value),
                                      ),
                                      _dropdown<int>(
                                        label:
                                            'Một buổi tập thường kéo dài bao lâu?',
                                        value: _durationMinutes,
                                        items: const [
                                          DropdownMenuItem(
                                              value: 20,
                                              child: Text('Khoảng 20 phút')),
                                          DropdownMenuItem(
                                              value: 30,
                                              child: Text('Khoảng 30 phút')),
                                          DropdownMenuItem(
                                              value: 45,
                                              child: Text('Khoảng 45 phút')),
                                          DropdownMenuItem(
                                              value: 60,
                                              child: Text('Khoảng 60 phút')),
                                          DropdownMenuItem(
                                              value: 90,
                                              child: Text('Khoảng 90 phút')),
                                        ],
                                        onChanged: (value) => setState(
                                            () => _durationMinutes = value),
                                      ),
                                      _dropdown<String>(
                                        label: 'Bạn muốn tập chủ yếu ở đâu?',
                                        value: _location,
                                        items: const [
                                          DropdownMenuItem(
                                              value: 'home',
                                              child: Text('Tại nhà')),
                                          DropdownMenuItem(
                                              value: 'gym',
                                              child: Text('Phòng tập')),
                                          DropdownMenuItem(
                                              value: 'outdoor',
                                              child: Text('Ngoài trời')),
                                          DropdownMenuItem(
                                              value: 'other',
                                              child: Text('Nơi khác')),
                                        ],
                                        onChanged: (value) =>
                                            setState(() => _location = value),
                                      ),
                                      const SizedBox(height: 8),
                                      const Text('Dụng cụ bạn có thể dùng',
                                          style: TextStyle(
                                              fontWeight: FontWeight.w600)),
                                      Wrap(
                                        spacing: 8,
                                        children: [
                                          _equipmentChip(
                                              'none', 'Không có dụng cụ'),
                                          _equipmentChip('dumbbells', 'Tạ đơn'),
                                          _equipmentChip('barbell', 'Tạ đòn'),
                                          _equipmentChip('machines', 'Máy tập'),
                                          _equipmentChip(
                                              'bands', 'Dây kháng lực'),
                                        ],
                                      ),
                                      _textAnswer(
                                        controller:
                                            _workoutPreferencesController,
                                        icon: Icons.tune_rounded,
                                        label:
                                            'Điều bạn thích hoặc muốn tránh khi tập (tùy chọn)',
                                        hint:
                                            'Ví dụ: thích bài ngắn, không thích nhảy, muốn tập nhẹ buổi tối…',
                                      ),
                                      _section('Sức khỏe & an toàn'),
                                      _choiceCards<String>(
                                        icon: Icons.person_outline_rounded,
                                        label:
                                            'Bạn muốn chia sẻ giới tính để mình hiển thị câu hỏi sức khỏe phù hợp không?',
                                        helper:
                                            'Chỉ dùng để quyết định có hiển thị câu hỏi thai kỳ; bạn có thể chọn không muốn trả lời.',
                                        value: _gender,
                                        choices: const {
                                          'female': 'Nữ',
                                          'male': 'Nam',
                                          'other': 'Khác',
                                          'not_provided': 'Không muốn trả lời',
                                        },
                                        onChanged: (value) =>
                                            setState(() => _gender = value),
                                      ),
                                      _choiceCards<String>(
                                        icon: Icons.self_improvement_outlined,
                                        label:
                                            'Ngay lúc này, cơ thể bạn có đang đau hoặc khó chịu khi vận động không?',
                                        helper:
                                            'Chọn theo cảm nhận hiện tại của bạn.',
                                        value: _pain,
                                        choices: const {
                                          'NO': 'Không',
                                          'YES': 'Có',
                                          'UNKNOWN':
                                              'Chưa rõ / không muốn trả lời',
                                        },
                                        onChanged: (value) =>
                                            setState(() => _pain = value),
                                      ),
                                      _choiceCards<String>(
                                        icon: Icons.health_and_safety_outlined,
                                        label:
                                            'Bạn có bệnh lý hoặc tình trạng sức khỏe cần bác sĩ theo dõi để tập an toàn không?',
                                        helper:
                                            'Bạn không cần ghi chi tiết bệnh lý ở đây.',
                                        value: _healthState,
                                        choices: const {
                                          'HEALTHY_GENERAL':
                                              'Không / sức khỏe ổn định',
                                          'MANAGED_HEALTH_CONDITION': 'Có',
                                          'UNKNOWN':
                                              'Chưa rõ / không muốn trả lời',
                                        },
                                        onChanged: (value) => setState(
                                            () => _healthState = value),
                                      ),
                                      if (_asksPregnancy)
                                        _choiceCards<String>(
                                          icon: Icons.pregnant_woman_outlined,
                                          label:
                                              'Thông tin thai kỳ có liên quan đến việc tập luyện của bạn không?',
                                          value: _pregnancyStatus,
                                          choices: const {
                                            'NOT_APPLICABLE': 'Không áp dụng',
                                            'PREGNANT': 'Đang mang thai',
                                            'POSTPARTUM': 'Sau sinh',
                                            'UNKNOWN':
                                                'Chưa rõ / không muốn trả lời',
                                          },
                                          onChanged: (value) => setState(
                                              () => _pregnancyStatus = value),
                                        ),
                                      _choiceCards<bool>(
                                        icon: Icons.monitor_heart_outlined,
                                        label:
                                            'Gần đây bạn có gặp dấu hiệu cần thận trọng khi vận động không?',
                                        helper:
                                            'Ví dụ: đau/nghẹn ngực, khó thở bất thường, chóng mặt/ngất hoặc nhịp tim bất thường.',
                                        value: _hasWarningSymptoms,
                                        choices: const {
                                          false: 'Không',
                                          true: 'Có'
                                        },
                                        onChanged: (value) => setState(
                                            () => _hasWarningSymptoms = value),
                                      ),
                                      if (_hasWarningSymptoms == true) ...[
                                        const Text('Chọn các dấu hiệu đang có',
                                            style: TextStyle(
                                                fontWeight: FontWeight.w600)),
                                        ...const {
                                          'CHEST_PAIN_OR_PRESSURE':
                                              'Đau hoặc tức ngực',
                                          'UNUSUAL_SHORTNESS_OF_BREATH':
                                              'Khó thở bất thường',
                                          'DIZZINESS_OR_FAINTING':
                                              'Chóng mặt hoặc ngất',
                                          'IRREGULAR_HEARTBEAT':
                                              'Nhịp tim bất thường',
                                        }.entries.map((entry) =>
                                            _symptomCheckbox(
                                                entry.key, entry.value)),
                                      ],
                                      _choiceCards<bool>(
                                        icon: Icons.personal_injury_outlined,
                                        label:
                                            'Bạn có chấn thương cấp đang diễn ra không?',
                                        value: _acuteInjury,
                                        choices: const {
                                          false: 'Không',
                                          true: 'Có'
                                        },
                                        onChanged: (value) => setState(
                                            () => _acuteInjury = value),
                                      ),
                                      _choiceCards<bool>(
                                        icon: Icons.medical_services_outlined,
                                        label:
                                            'Bạn có phẫu thuật gần đây cần lưu ý khi vận động không?',
                                        value: _recentSurgery,
                                        choices: const {
                                          false: 'Không',
                                          true: 'Có'
                                        },
                                        onChanged: (value) => setState(
                                            () => _recentSurgery = value),
                                      ),
                                      CheckboxListTile(
                                        contentPadding: EdgeInsets.zero,
                                        value: _understandsSafety,
                                        onChanged: (value) => setState(() =>
                                            _understandsSafety =
                                                value ?? false),
                                        title: const Text(
                                            'Tôi hiểu cần dừng tập khi đau tăng, khó chịu hoặc có dấu hiệu bất thường.'),
                                        controlAffinity:
                                            ListTileControlAffinity.leading,
                                      ),
                                    ],
                                  ])),
                          if (_step == 1 && !_requiresWorkout)
                            const ProfileSummaryCard(
                                title: 'Tập luyện',
                                icon: Icons.directions_walk,
                                values: {
                                  'Hiện tại':
                                      'Bạn chưa chọn hỗ trợ tập luyện. Có thể bổ sung sau.'
                                }),
                          if (_step == 2) ..._summary(),
                        ]),
                  )))),
          bottomNavigationBar: SafeArea(
              child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                  child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (_error != null)
                          Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Text(_error!,
                                  style:
                                      const TextStyle(color: AppColors.error))),
                        FilledButton(
                            key: const Key('health-wizard-next'),
                            onPressed: _saving ? null : _next,
                            style: FilledButton.styleFrom(
                                minimumSize: const Size.fromHeight(54),
                                backgroundColor: AppColors.primary),
                            child: Text(_saving
                                ? 'Đang lưu...'
                                : _step == 2
                                    ? 'Hoàn tất'
                                    : 'Tiếp tục')),
                        if (_step > 0)
                          TextButton(
                              onPressed: _saving ? null : _back,
                              child: const Text('Quay lại chỉnh sửa')),
                      ]))),
        ),
      );

  List<Widget> _summary() {
    final user = context.watch<UserProvider>().currentUser;
    const labels = {
      'NUTRITION': 'Ăn uống & dinh dưỡng',
      'EXERCISE': 'Tập luyện',
      'BOTH': 'Cả ăn uống và tập luyện',
      'GENERAL_HEALTH': 'Sức khỏe chung',
      'LOSE_WEIGHT': 'Giảm cân',
      'MAINTAIN': 'Duy trì sức khỏe',
      'GAIN_WEIGHT': 'Tăng cân lành mạnh',
      'GAIN_MUSCLE': 'Tăng cơ',
      'IMPROVE_HABITS': 'Ăn uống đều đặn hơn',
      'UNKNOWN': 'Chưa rõ',
      'CRUSTACEAN': 'Tôm, cua',
      'MOLLUSC': 'Mực, nghêu, sò',
      'FISH': 'Cá',
      'EGG': 'Trứng',
      'MILK': 'Sữa',
      'PEANUT': 'Đậu phộng',
      'TREE_NUT': 'Các loại hạt cây',
      'SOY': 'Đậu nành',
      'WHEAT_GLUTEN': 'Lúa mì / gluten',
      'SESAME': 'Mè',
      'vegetarian': 'Món chay',
      'vegan': 'Thuần chay',
      'no_seafood': 'Không ăn hải sản',
      'no_pork': 'Không ăn thịt heo',
      'no_beef': 'Không ăn thịt bò',
      'low_carb': 'Ưu tiên ít tinh bột',
      'high_protein': 'Ưu tiên giàu đạm',
      'vietnamese': 'Món Việt',
      'asian': 'Món Á',
      'other': 'Khác',
      'regular_meals': 'Ăn đúng bữa',
      'late_meals': 'Hay ăn muộn',
      'eat_out': 'Thường ăn ngoài',
      'home_cooked': 'Hay tự nấu',
      'female': 'Nữ',
      'male': 'Nam',
      'not_provided': 'Không muốn trả lời',
      'NO': 'Không',
      'YES': 'Có',
      'HEALTHY_GENERAL': 'Không / sức khỏe ổn định',
      'MANAGED_HEALTH_CONDITION': 'Có',
      'NOT_APPLICABLE': 'Không áp dụng',
      'PREGNANT': 'Đang mang thai',
      'POSTPARTUM': 'Sau sinh',
      'CHEST_PAIN_OR_PRESSURE': 'Đau hoặc tức ngực',
      'UNUSUAL_SHORTNESS_OF_BREATH': 'Khó thở bất thường',
      'DIZZINESS_OR_FAINTING': 'Chóng mặt hoặc ngất',
      'IRREGULAR_HEARTBEAT': 'Nhịp tim bất thường',
      'NOVICE': 'Mới bắt đầu',
      'EXPERIENCED': 'Có kinh nghiệm',
      'dumbbells': 'Tạ đơn',
      'barbell': 'Tạ đòn',
      'machines': 'Máy tập',
      'bands': 'Dây kháng lực',
      'none': 'Không dụng cụ',
      'home': 'Tại nhà',
      'gym': 'Phòng tập',
      'outdoor': 'Ngoài trời',
    };
    String display(String? value) =>
        value == null ? 'Chưa cung cấp' : labels[value] ?? value;
    String list(Set<String> values, bool answered) => values.isEmpty
        ? answered
            ? 'Đã xác nhận không có'
            : 'Chưa cung cấp'
        : values.map(display).join(', ');
    String answer(bool? value) => value == null
        ? 'Chưa cung cấp'
        : value
            ? 'Có'
            : 'Không';
    void edit(int step) => setState(() => _step = step);
    return [
      if (user != null)
        ProfileSummaryCard(
            title: 'Thông tin cơ bản',
            onEdit: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => const ProfileSettingsScreen())),
            values: {
              'Họ và tên': user.name,
              'Tuổi': '${user.age}',
              'Chiều cao / cân nặng': '${user.height} cm · ${user.weight} kg',
              'Giới tính': display(user.gender),
              'Thông tin ước tính năng lượng': display(user.equationSex),
            }),
      ProfileSummaryCard(
          title: 'Mục tiêu',
          icon: Icons.flag_outlined,
          onEdit: () => edit(0),
          values: {
            'Hỗ trợ chính': display(_primarySupport),
            if (user != null) 'Mục tiêu sức khỏe': user.healthGoalText,
            'Dinh dưỡng': display(_nutritionGoal)
          }),
      ProfileSummaryCard(
          title: 'Dị ứng',
          icon: Icons.shield_outlined,
          onEdit: () => edit(0),
          values: {
            'Thông tin xác nhận': list(_foodAllergies, _foodAllergiesTouched)
          }),
      ProfileSummaryCard(
          title: 'Hạn chế ăn',
          icon: Icons.no_food_outlined,
          onEdit: () => edit(0),
          values: {
            'Lựa chọn': list(_dietaryRestrictions, _dietaryRestrictionsTouched)
          }),
      ProfileSummaryCard(
          title: 'Sở thích ăn uống',
          icon: Icons.restaurant_outlined,
          onEdit: () => edit(0),
          values: {
            'Sở thích': _foodPreferenceController.text.isEmpty
                ? 'Chưa cung cấp'
                : _foodPreferenceController.text,
            'Món không thích': _foodDislikesController.text.isEmpty
                ? 'Chưa cung cấp'
                : _foodDislikesController.text
          }),
      ProfileSummaryCard(
          title: 'Tập luyện',
          icon: Icons.fitness_center,
          onEdit: () => edit(1),
          values: {
            'Kinh nghiệm': display(_experience),
            'Lịch tập': _daysPerWeek == null
                ? 'Chưa cung cấp'
                : '$_daysPerWeek ngày/tuần · $_durationMinutes phút/buổi',
            'Dụng cụ': list(_equipment, _equipment.isNotEmpty)
          }),
      ProfileSummaryCard(
          title: 'An toàn tập luyện',
          icon: Icons.health_and_safety_outlined,
          onEdit: () => edit(1),
          values: {
            'Dấu hiệu cảnh báo': answer(_hasWarningSymptoms),
            'Chấn thương cấp': answer(_acuteInjury),
            'Phẫu thuật gần đây': answer(_recentSurgery),
            'Thai kỳ': display(_pregnancyStatus)
          }),
      if (user != null)
        ProfileSummaryCard(
          title: 'An toàn dinh dưỡng',
          icon: Icons.health_and_safety_outlined,
          onEdit: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => const ProfileSettingsScreen())),
          values: {
            for (final entry in user.nutritionSafetyProfile.toJson().entries)
              const {
                'pregnancy': 'Thai kỳ',
                'lactation': 'Cho con bú',
                'eating_disorder_risk_or_history': 'Rối loạn ăn uống',
                'serious_renal_condition': 'Tình trạng thận',
                'fluid_restricted_cardiac_condition': 'Tim và hạn chế dịch',
                'clinically_complex_metabolic_condition':
                    'Tình trạng chuyển hóa'
              }[entry.key]!: const {
                    'YES': 'Có',
                    'NO': 'Không',
                    'UNKNOWN': 'Chưa rõ',
                    'NOT_PROVIDED': 'Chưa cung cấp'
                  }[entry.value] ??
                  'Chưa cung cấp'
          },
        ),
    ];
  }

  Widget _section(String title) => Padding(
        padding: const EdgeInsets.only(top: 24, bottom: 10),
        child: Text(title,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      );

  Widget _dropdown<T>({
    required String label,
    required T? value,
    required List<DropdownMenuItem<T>> items,
    required ValueChanged<T?> onChanged,
  }) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: DropdownButtonFormField<T>(
          initialValue: value,
          isExpanded: true,
          decoration: InputDecoration(
              labelText: label, border: const OutlineInputBorder()),
          items: items,
          onChanged: _saving ? null : onChanged,
        ),
      );

  Widget _textAnswer({
    required TextEditingController controller,
    required IconData icon,
    required String label,
    required String hint,
  }) =>
      Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: HealthSurface(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(icon, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                              child: Text(label,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      height: 1.4)))
                        ]),
                    const SizedBox(height: 12),
                    TextField(
                        controller: controller,
                        enabled: !_saving,
                        minLines: 2,
                        maxLines: 4,
                        maxLength: 600,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: InputDecoration(
                            hintText: hint,
                            counterText: '',
                            border: InputBorder.none,
                            filled: false,
                            contentPadding: EdgeInsets.zero)),
                  ])));

  Widget _optionalNutritionButton() => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: OutlinedButton.icon(
          onPressed: _saving
              ? null
              : () => setState(() => _showOptionalNutrition = true),
          icon: const Icon(Icons.restaurant_menu_outlined),
          label: const Text('Thêm thông tin ăn uống (tùy chọn)'),
        ),
      );

  Widget _existingWorkoutNotice() => Container(
        margin: const EdgeInsets.only(top: 12, bottom: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(AppRadius.lg),
        ),
        child: const Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.check_circle_outline_rounded),
            SizedBox(width: 10),
            Expanded(
              child: Text(
                'Thông tin tập luyện và an toàn của bạn đã có. Mình sẽ dùng lại các mục này; bạn không cần trả lời lại ở đây.',
                style: TextStyle(height: 1.35),
              ),
            ),
          ],
        ),
      );

  Widget _multiSelectCard({
    required IconData icon,
    required String label,
    String? helper,
    required Set<String> values,
    required Map<String, String> choices,
    VoidCallback? onSelectionChanged,
    String? noneLabel,
    bool answered = false,
  }) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.lg),
            border: Border.all(color: AppColors.surfaceLight),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon, size: 20, color: AppColors.textPrimary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(label,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
              if (helper != null) ...[
                const SizedBox(height: 7),
                Text(helper,
                    style: const TextStyle(
                        color: AppColors.textSecondary, height: 1.35)),
              ],
              const SizedBox(height: 10),
              if (noneLabel != null)
                FilterChip(
                  label: Text(noneLabel),
                  selected: answered && values.isEmpty,
                  onSelected: _saving
                      ? null
                      : (_) => setState(() {
                            values.clear();
                            onSelectionChanged?.call();
                          }),
                ),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: choices.entries.map((entry) {
                  return FilterChip(
                    label: Text(entry.value),
                    selected: values.contains(entry.key),
                    onSelected: _saving
                        ? null
                        : (selected) => setState(() {
                              if (selected) {
                                values.add(entry.key);
                              } else {
                                values.remove(entry.key);
                              }
                              onSelectionChanged?.call();
                            }),
                  );
                }).toList(growable: false),
              ),
            ],
          ),
        ),
      );

  Widget _choiceCards<T>({
    required IconData icon,
    required String label,
    String? helper,
    required T? value,
    required Map<T, String> choices,
    required ValueChanged<T?> onChanged,
  }) =>
      Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(label,
                style:
                    const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            if (helper != null)
              Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(helper,
                      style: const TextStyle(
                          color: AppColors.textSecondary, height: 1.4))),
            const SizedBox(height: 8),
            for (final entry in choices.entries)
              ProfileOptionCard<T>(
                  value: entry.key,
                  selected: value == entry.key,
                  title: entry.value,
                  icon: icon,
                  onSelected: _saving ? null : onChanged),
          ]));

  Widget _equipmentChip(String id, String label) => FilterChip(
        label: Text(label),
        selected: _equipment.contains(id),
        onSelected: _saving
            ? null
            : (selected) => setState(() {
                  if (selected) {
                    _equipment.add(id);
                  } else {
                    _equipment.remove(id);
                  }
                }),
      );

  Widget _symptomCheckbox(String id, String label) => CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        value: _warningSymptoms.contains(id),
        title: Text(label),
        onChanged: _saving
            ? null
            : (selected) => setState(() {
                  if (selected == true) {
                    _warningSymptoms.add(id);
                  } else {
                    _warningSymptoms.remove(id);
                  }
                }),
      );
}

class _SafetyNote extends StatelessWidget {
  const _SafetyNote();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF4E5),
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Text(
          'Thông tin này chỉ để sàng lọc và cá nhân hóa, không thay thế chẩn đoán. '
          'Nếu có dấu hiệu cảnh báo hoặc chấn thương cấp, ứng dụng sẽ không tự kê bài tập.',
          style: TextStyle(height: 1.35),
        ),
      );
}
