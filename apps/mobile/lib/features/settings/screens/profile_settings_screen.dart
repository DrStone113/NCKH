import 'package:flutter/material.dart';
import '../../../widgets/profile_wizard.dart';
import '../../../widgets/health_surface.dart';
import 'package:provider/provider.dart';

import '../../../models/canonical_nutrition.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';

class ProfileSettingsScreen extends StatefulWidget {
  const ProfileSettingsScreen(
      {super.key, this.isAccountSetup = false, this.onSaved});

  final bool isAccountSetup;
  final VoidCallback? onSaved;

  @override
  State<ProfileSettingsScreen> createState() => _ProfileSettingsScreenState();
}

class _ProfileSettingsScreenState extends State<ProfileSettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late final TextEditingController _ageController;
  late final TextEditingController _heightController;
  late final TextEditingController _weightController;
  late final TextEditingController _targetWeightController;
  String? _gender;
  String _equationSex = 'not_provided';
  late Map<String, NutritionSafetyAnswer> _safetyAnswers;
  String? _activityLevel;
  String? _healthGoal;
  bool _isSaving = false;
  String? _saveError;
  int _step = 0;
  bool _started = false;

  static const _goals = <String, String>{
    'lose_weight': 'Giảm cân',
    'maintain': 'Duy trì cân nặng',
    'gain_muscle': 'Tăng cơ',
  };

  static const _activities = <String, String>{
    'sedentary': 'Ít vận động',
    'light': 'Vận động nhẹ (1–3 buổi/tuần)',
    'moderate': 'Vận động vừa (3–5 buổi/tuần)',
    'active': 'Vận động nhiều (6–7 buổi/tuần)',
    'very_active': 'Vận động cường độ cao',
  };

  static const _safetyLabels = <String, String>{
    'pregnancy': 'Đang mang thai',
    'lactation': 'Đang cho con bú',
    'eating_disorder_risk_or_history':
        'Có nguy cơ hoặc tiền sử rối loạn ăn uống',
    'serious_renal_condition': 'Có tình trạng thận nghiêm trọng đã biết',
    'fluid_restricted_cardiac_condition':
        'Có tình trạng tim cần hạn chế dịch đã biết',
    'clinically_complex_metabolic_condition':
        'Có tình trạng chuyển hóa phức tạp đã biết',
  };

  bool get _asksMaternalSafetyQuestions =>
      (_gender ?? '').trim().toLowerCase() == 'female';

  Iterable<MapEntry<String, String>> get _visibleSafetyLabels =>
      _safetyLabels.entries.where(
        (entry) =>
            _asksMaternalSafetyQuestions ||
            (entry.key != 'pregnancy' && entry.key != 'lactation'),
      );

  @override
  void initState() {
    super.initState();
    final user = context.read<UserProvider>().currentUser;
    _nameController = TextEditingController(text: user?.name ?? '');
    _ageController = TextEditingController(
      text: user != null && user.age > 0 ? '${user.age}' : '',
    );
    _heightController = TextEditingController(
      text: user != null && user.height > 0 ? '${user.height}' : '',
    );
    _weightController = TextEditingController(
      text: user != null && user.weight > 0 ? '${user.weight}' : '',
    );
    _targetWeightController = TextEditingController(
      text: user?.targetWeight?.toStringAsFixed(1) ?? '',
    );
    _gender = user?.gender ?? (widget.isAccountSetup ? null : 'not_provided');
    _equationSex = user?.equationSex ?? 'not_provided';
    final safety =
        user?.nutritionSafetyProfile ?? const NutritionSafetyProfile();
    _safetyAnswers = {
      'pregnancy': safety.pregnancy,
      'lactation': safety.lactation,
      'eating_disorder_risk_or_history': safety.eatingDisorderRiskOrHistory,
      'serious_renal_condition': safety.seriousRenalCondition,
      'fluid_restricted_cardiac_condition':
          safety.fluidRestrictedCardiacCondition,
      'clinically_complex_metabolic_condition':
          safety.clinicallyComplexMetabolicCondition,
    };
    _activityLevel = _normalizeActivity(user?.activityLevel);
    _healthGoal =
        _goals.containsKey(user?.healthGoal) ? user!.healthGoal : null;
  }

  @override
  void dispose() {
    _nameController.dispose();
    _ageController.dispose();
    _heightController.dispose();
    _weightController.dispose();
    _targetWeightController.dispose();
    super.dispose();
  }

  String? _normalizeActivity(String? value) {
    switch (value?.toLowerCase()) {
      case 'lightly_active':
      case 'light':
        return 'light';
      case 'moderately_active':
      case 'moderate':
        return 'moderate';
      case 'very_active':
      case 'active':
        return value == 'very_active' ? 'very_active' : 'active';
      case 'extra_active':
        return 'very_active';
      case 'sedentary':
        return 'sedentary';
      default:
        return null;
    }
  }

  double? _parseNumber(String raw) {
    return double.tryParse(raw.trim().replaceAll(',', '.'));
  }

  String? _requiredText(String? value) {
    final text = value?.trim() ?? '';
    if (text.length < 2) return 'Vui lòng nhập ít nhất 2 ký tự';
    return null;
  }

  String? _validAge(String? value) {
    final age = int.tryParse(value?.trim() ?? '');
    if (age == null) return 'Tuổi phải là số nguyên';
    if (age < 13 || age > 120) return 'Nhập trong khoảng 13–120 tuổi';
    return null;
  }

  String? _numberInRange(
    String? value, {
    required double min,
    required double max,
    required String unit,
    bool optional = false,
  }) {
    final raw = value?.trim() ?? '';
    if (optional && raw.isEmpty) return null;
    final number = _parseNumber(raw);
    if (number == null || !number.isFinite) return 'Giá trị không hợp lệ';
    if (number < min || number > max) {
      return 'Nhập trong khoảng $min–$max $unit';
    }
    return null;
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final provider = context.read<UserProvider>();
    final current = provider.currentUser;
    if (current == null) return;

    setState(() {
      _isSaving = true;
      _saveError = null;
    });
    try {
      final updated = current.copyWith(
        name: _nameController.text.trim(),
        age: int.parse(_ageController.text.trim()),
        gender: _gender == 'not_provided' ? null : _gender,
        equationSex: _equationSex == 'not_provided' ? null : _equationSex,
        nutritionSafetyProfile: NutritionSafetyProfile(
          pregnancy: _safetyAnswers['pregnancy']!,
          lactation: _safetyAnswers['lactation']!,
          eatingDisorderRiskOrHistory:
              _safetyAnswers['eating_disorder_risk_or_history']!,
          seriousRenalCondition: _safetyAnswers['serious_renal_condition']!,
          fluidRestrictedCardiacCondition:
              _safetyAnswers['fluid_restricted_cardiac_condition']!,
          clinicallyComplexMetabolicCondition:
              _safetyAnswers['clinically_complex_metabolic_condition']!,
        ),
        height: _parseNumber(_heightController.text)!,
        weight: _parseNumber(_weightController.text)!,
        targetWeight: _targetWeightController.text.trim().isEmpty
            ? current.targetWeight
            : _parseNumber(_targetWeightController.text),
        activityLevel: _activityLevel!,
        healthGoal: _healthGoal!,
      );
      if (widget.isAccountSetup) {
        await provider.completeBasicProfile(updated);
        if (mounted) widget.onSaved?.call();
        // AuthWrapper advances only after the persisted provider update.
        return;
      }
      await provider.updateProfile(updated);
      if (!mounted) return;
      if (widget.onSaved != null) {
        widget.onSaved!();
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã cập nhật hồ sơ sức khỏe')),
      );
      Navigator.pop(context);
    } catch (error) {
      if (!mounted) return;
      setState(() => _saveError =
          'Chưa thể lưu hồ sơ. Vui lòng kiểm tra kết nối và thử lại.');
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  String _safetyText(NutritionSafetyAnswer? value) => switch (value) {
        NutritionSafetyAnswer.yes => 'Có',
        NutritionSafetyAnswer.no => 'Không',
        NutritionSafetyAnswer.unknown => 'Chưa rõ',
        _ => 'Chưa cung cấp',
      };
  void _back() {
    if (_step > 0) {
      setState(() {
        _step--;
        _saveError = null;
      });
    } else if (widget.isAccountSetup) {
      setState(() => _started = false);
    } else {
      Navigator.maybePop(context);
    }
  }

  void _next() {
    FocusManager.instance.primaryFocus?.unfocus();
    String? error;
    if (_step == 0) {
      error = _requiredText(_nameController.text) ??
          _validAge(_ageController.text) ??
          _numberInRange(_heightController.text,
              min: 100, max: 250, unit: 'cm') ??
          _numberInRange(_weightController.text,
              min: 25, max: 400, unit: 'kg') ??
          (_gender == null ? 'Chọn giới tính hoặc không cung cấp' : null);
    } else if (_step == 1) {
      error = _activityLevel == null || _healthGoal == null
          ? 'Chọn mục tiêu và mức vận động của bạn.'
          : null;
      error ??= _numberInRange(_targetWeightController.text,
          min: 25, max: 400, unit: 'kg', optional: true);
    }
    if (error != null) {
      setState(() => _saveError = error);
      return;
    }
    if (_step == 3 || (widget.isAccountSetup && _step == 2)) {
      _save();
      return;
    }
    setState(() {
      _saveError = null;
      _step++;
    });
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<UserProvider>().currentUser;
    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (widget.isAccountSetup && !_started) {
      return Scaffold(
          body: ProfileWelcome(onStart: () => setState(() => _started = true)));
    }
    final titles = [
      'Cho mình biết thêm về bạn',
      'Mục tiêu của bạn là gì?',
      'Một chút về sức khỏe',
      'Xác nhận hồ sơ'
    ];
    final subtitles = [
      'Những thông tin này giúp tính toán nhu cầu năng lượng phù hợp hơn.',
      'Chọn mục tiêu và nhịp vận động phù hợp với bạn.',
      'Bạn có thể chọn chưa rõ hoặc chưa cung cấp. Mỗi câu trả lời đều được giữ đúng ý nghĩa.',
      'Kiểm tra lại thông tin trước khi hoàn tất.'
    ];
    return PopScope(
      canPop: _step == 0 && !widget.isAccountSetup,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop && !_isSaving) _back();
      },
      child: Scaffold(
        appBar: AppBar(
            title: const Text('Hồ sơ sức khỏe'),
            automaticallyImplyLeading: false,
            leading: IconButton(
                tooltip: 'Quay lại',
                onPressed: _isSaving ? null : _back,
                icon: const Icon(Icons.arrow_back_rounded))),
        body: SafeArea(
            child: Form(
                key: _formKey,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                  child: Center(
                      child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 600),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                ProfileStepHeader(
                                    step: _step + 1,
                                    total: widget.isAccountSetup ? 6 : 4,
                                    title: titles[_step],
                                    subtitle: subtitles[_step]),
                                Visibility(
                                    visible: _step == 0,
                                    maintainState: true,
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          const _SectionTitle(
                                            title: 'Thông tin cơ bản',
                                            subtitle:
                                                'Dùng để cá nhân hóa các chỉ số sức khỏe.',
                                          ),
                                          const SizedBox(height: 12),
                                          TextFormField(
                                            key: const Key('profile-name'),
                                            controller: _nameController,
                                            textInputAction:
                                                TextInputAction.next,
                                            validator: _requiredText,
                                            decoration: const InputDecoration(
                                              labelText: 'Họ và tên',
                                              prefixIcon:
                                                  Icon(Icons.person_outline),
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          TextFormField(
                                            initialValue: user.email,
                                            readOnly: true,
                                            decoration: const InputDecoration(
                                              labelText: 'Email',
                                              prefixIcon:
                                                  Icon(Icons.email_outlined),
                                              helperMaxLines: 3,
                                              helperText:
                                                  'Email được quản lý bởi tài khoản đăng nhập.',
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          TextFormField(
                                            key: const Key('profile-age'),
                                            controller: _ageController,
                                            keyboardType: TextInputType.number,
                                            validator: _validAge,
                                            decoration: const InputDecoration(
                                              labelText: 'Tuổi',
                                              prefixIcon:
                                                  Icon(Icons.cake_outlined),
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          DropdownButtonFormField<String>(
                                            key: const Key('profile-gender'),
                                            initialValue: _gender,
                                            isExpanded: true,
                                            validator: (value) => value == null
                                                ? 'Chọn giới tính hoặc không cung cấp'
                                                : null,
                                            decoration: const InputDecoration(
                                              labelText: 'Giới tính',
                                              prefixIcon:
                                                  Icon(Icons.person_outline),
                                            ),
                                            items: const [
                                              DropdownMenuItem(
                                                  value: 'not_provided',
                                                  child:
                                                      Text('Không cung cấp')),
                                              DropdownMenuItem(
                                                  value: 'male',
                                                  child: Text('Nam')),
                                              DropdownMenuItem(
                                                  value: 'female',
                                                  child: Text('Nữ')),
                                              DropdownMenuItem(
                                                  value: 'other',
                                                  child: Text('Khác')),
                                            ],
                                            onChanged: (value) {
                                              if (value != null) {
                                                setState(() => _gender = value);
                                              }
                                            },
                                          ),
                                          const SizedBox(height: 24),
                                          const _SectionTitle(
                                            title: 'Chỉ số cơ thể',
                                            subtitle:
                                                'Cập nhật đúng số liệu để BMI, BMR và TDEE chính xác.',
                                          ),
                                          const SizedBox(height: 12),
                                          Row(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Expanded(
                                                child: TextFormField(
                                                  key: const Key(
                                                      'profile-height'),
                                                  controller: _heightController,
                                                  keyboardType:
                                                      const TextInputType
                                                          .numberWithOptions(
                                                    decimal: true,
                                                  ),
                                                  validator: (value) =>
                                                      _numberInRange(
                                                    value,
                                                    min: 100,
                                                    max: 250,
                                                    unit: 'cm',
                                                  ),
                                                  decoration:
                                                      const InputDecoration(
                                                    labelText: 'Chiều cao (cm)',
                                                    prefixIcon:
                                                        Icon(Icons.height),
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 12),
                                              Expanded(
                                                child: TextFormField(
                                                  key: const Key(
                                                      'profile-weight'),
                                                  controller: _weightController,
                                                  keyboardType:
                                                      const TextInputType
                                                          .numberWithOptions(
                                                    decimal: true,
                                                  ),
                                                  validator: (value) =>
                                                      _numberInRange(
                                                    value,
                                                    min: 25,
                                                    max: 400,
                                                    unit: 'kg',
                                                  ),
                                                  decoration:
                                                      const InputDecoration(
                                                    labelText: 'Cân nặng (kg)',
                                                    prefixIcon: Icon(Icons
                                                        .monitor_weight_outlined),
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 12),
                                        ])),
                                Visibility(
                                    visible: _step == 1,
                                    maintainState: true,
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          Column(
                                              key: const Key('profile-goal'),
                                              children: [
                                                for (final entry
                                                    in _goals.entries)
                                                  ProfileOptionCard<String>(
                                                      value: entry.key,
                                                      selected: _healthGoal ==
                                                          entry.key,
                                                      title: entry.value,
                                                      icon: Icons.flag_outlined,
                                                      onSelected: (value) =>
                                                          setState(() =>
                                                              _healthGoal =
                                                                  value)),
                                              ]),
                                          const SizedBox(height: 16),
                                          TextFormField(
                                            controller: _targetWeightController,
                                            keyboardType: const TextInputType
                                                .numberWithOptions(
                                              decimal: true,
                                            ),
                                            validator: (value) =>
                                                _numberInRange(
                                              value,
                                              min: 25,
                                              max: 400,
                                              unit: 'kg',
                                              optional: true,
                                            ),
                                            decoration: const InputDecoration(
                                              labelText:
                                                  'Cân nặng mục tiêu (kg)',
                                              prefixIcon:
                                                  Icon(Icons.flag_outlined),
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          DropdownButtonFormField<String>(
                                            initialValue: _equationSex,
                                            isExpanded: true,
                                            decoration: const InputDecoration(
                                              labelText:
                                                  'Thông tin ước tính năng lượng',
                                              helperMaxLines: 3,
                                              helperText:
                                                  'Tùy chọn. Dùng riêng cho ước tính năng lượng; không suy ra từ giới tính.',
                                              prefixIcon: Icon(
                                                  Icons.calculate_outlined),
                                            ),
                                            items: const [
                                              DropdownMenuItem(
                                                  value: 'not_provided',
                                                  child: Text(
                                                      'Chưa xác nhận / từ chối')),
                                              DropdownMenuItem(
                                                  value: 'male',
                                                  child: Text('Hệ số nam')),
                                              DropdownMenuItem(
                                                  value: 'female',
                                                  child: Text('Hệ số nữ')),
                                            ],
                                            onChanged: (value) {
                                              if (value != null) {
                                                _equationSex = value;
                                              }
                                            },
                                          ),
                                          const SizedBox(height: 24),
                                          const _SectionTitle(
                                            title: 'Mức độ vận động',
                                            subtitle:
                                                'Ảnh hưởng trực tiếp đến TDEE và lượng calo đề xuất.',
                                          ),
                                          const SizedBox(height: 12),
                                          DropdownButtonFormField<String>(
                                            key: const Key('profile-activity'),
                                            initialValue: _activityLevel,
                                            isExpanded: true,
                                            validator: (value) => value == null
                                                ? 'Vui lòng chọn mức độ vận động'
                                                : null,
                                            decoration: const InputDecoration(
                                              labelText: 'Hoạt động hằng tuần',
                                              prefixIcon:
                                                  Icon(Icons.directions_run),
                                            ),
                                            items: _activities.entries
                                                .map(
                                                  (entry) => DropdownMenuItem(
                                                    value: entry.key,
                                                    child: Semantics(
                                                      label:
                                                          'profile-activity-${entry.key}',
                                                      button: true,
                                                      child: Text(entry.value),
                                                    ),
                                                  ),
                                                )
                                                .toList(),
                                            onChanged: (value) {
                                              if (value != null) {
                                                _activityLevel = value;
                                              }
                                            },
                                          ),
                                          const SizedBox(height: 12),
                                        ])),
                                Visibility(
                                    visible: _step == 2,
                                    maintainState: true,
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          const _SectionTitle(
                                            title:
                                                'Khả năng áp dụng mục tiêu dinh dưỡng',
                                            subtitle:
                                                'Thông tin tự khai để xác định khi nào cần hướng dẫn chuyên gia; không phải chẩn đoán.',
                                          ),
                                          const SizedBox(height: 12),
                                          ..._visibleSafetyLabels.map(
                                            (entry) => Padding(
                                              padding: const EdgeInsets.only(
                                                  bottom: 12),
                                              child: HealthSurface(
                                                  padding:
                                                      const EdgeInsets.all(16),
                                                  child: Column(
                                                      crossAxisAlignment:
                                                          CrossAxisAlignment
                                                              .stretch,
                                                      children: [
                                                        Text(entry.value,
                                                            style: const TextStyle(
                                                                fontSize: 15,
                                                                fontWeight:
                                                                    FontWeight
                                                                        .w700,
                                                                height: 1.4)),
                                                        const SizedBox(
                                                            height: 12),
                                                        DropdownButtonFormField<
                                                            NutritionSafetyAnswer>(
                                                          initialValue:
                                                              _safetyAnswers[
                                                                  entry.key],
                                                          decoration:
                                                              const InputDecoration(
                                                                  labelText:
                                                                      'Trạng thái'),
                                                          items: const [
                                                            DropdownMenuItem(
                                                                value: NutritionSafetyAnswer
                                                                    .notProvided,
                                                                child: Text(
                                                                    'Chưa cung cấp')),
                                                            DropdownMenuItem(
                                                                value:
                                                                    NutritionSafetyAnswer
                                                                        .unknown,
                                                                child: Text(
                                                                    'Không rõ')),
                                                            DropdownMenuItem(
                                                                value:
                                                                    NutritionSafetyAnswer
                                                                        .no,
                                                                child: Text(
                                                                    'Không')),
                                                            DropdownMenuItem(
                                                                value:
                                                                    NutritionSafetyAnswer
                                                                        .yes,
                                                                child:
                                                                    Text('Có')),
                                                          ],
                                                          onChanged: (value) {
                                                            if (value != null) {
                                                              _safetyAnswers[
                                                                      entry
                                                                          .key] =
                                                                  value;
                                                            }
                                                          },
                                                        )
                                                      ])),
                                            ),
                                          ),
                                          const SizedBox(height: 24),
                                        ])),
                                if (_step == 3) ...[
                                  ProfileSummaryCard(
                                      title: 'Thông tin cơ bản',
                                      onEdit: () => setState(() => _step = 0),
                                      values: {
                                        'Họ và tên': _nameController.text,
                                        'Tuổi': _ageController.text,
                                        'Chiều cao / cân nặng':
                                            '${_heightController.text} cm · ${_weightController.text} kg',
                                        'Giới tính': {
                                              'male': 'Nam',
                                              'female': 'Nữ',
                                              'other': 'Khác'
                                            }[_gender] ??
                                            'Không cung cấp',
                                      }),
                                  ProfileSummaryCard(
                                      title: 'Mục tiêu',
                                      onEdit: () => setState(() => _step = 1),
                                      values: {
                                        'Mục tiêu': _goals[_healthGoal] ??
                                            'Chưa cung cấp',
                                        'Vận động':
                                            _activities[_activityLevel] ??
                                                'Chưa cung cấp'
                                      }),
                                  ProfileSummaryCard(
                                      title: 'An toàn dinh dưỡng',
                                      onEdit: () => setState(() => _step = 2),
                                      values: {
                                        for (final entry
                                            in _visibleSafetyLabels)
                                          entry.value: _safetyText(
                                              _safetyAnswers[entry.key])
                                      }),
                                ],
                              ]))),
                ))),
        bottomNavigationBar: SafeArea(
            child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_saveError != null)
                        Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Text(_saveError!,
                                key: const Key('profile-save-error'),
                                style:
                                    const TextStyle(color: AppColors.error))),
                      Semantics(
                        label: 'profile-save-step-$_step',
                        button: true,
                        child: FilledButton(
                          key: const Key('profile-save'),
                          onPressed: _isSaving ? null : _next,
                          style: FilledButton.styleFrom(
                              minimumSize: const Size.fromHeight(54),
                              backgroundColor: AppColors.primary),
                          child: Text(_isSaving
                              ? 'Đang lưu...'
                              : _step == 3
                                  ? 'Hoàn tất'
                                  : widget.isAccountSetup && _step == 2
                                      ? 'Lưu và tiếp tục'
                                      : 'Tiếp tục'),
                        ),
                      ),
                      if (_step > 0)
                        TextButton(
                            onPressed: _isSaving ? null : _back,
                            child: const Text('Quay lại chỉnh sửa')),
                    ]))),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 3),
        Text(
          subtitle,
          style: const TextStyle(
            color: AppColors.textSecondary,
            fontSize: 12,
            height: 1.35,
          ),
        ),
      ],
    );
  }
}
