import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../models/user_model.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';

class ProfileSettingsScreen extends StatefulWidget {
  const ProfileSettingsScreen({super.key});

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
  String _gender = 'male';
  String _activityLevel = 'moderate';
  bool _isSaving = false;

  static const _activities = <String, String>{
    'sedentary': 'Ít vận động',
    'light': 'Vận động nhẹ (1–3 buổi/tuần)',
    'moderate': 'Vận động vừa (3–5 buổi/tuần)',
    'active': 'Vận động nhiều (6–7 buổi/tuần)',
    'very_active': 'Vận động cường độ cao',
  };

  @override
  void initState() {
    super.initState();
    final user = context.read<UserProvider>().currentUser;
    _nameController = TextEditingController(text: user?.name ?? '');
    _ageController = TextEditingController(text: '${user?.age ?? 25}');
    _heightController = TextEditingController(
      text: (user?.height ?? 170).toStringAsFixed(0),
    );
    _weightController = TextEditingController(
      text: (user?.weight ?? 65).toStringAsFixed(1),
    );
    _targetWeightController = TextEditingController(
      text: user?.targetWeight?.toStringAsFixed(1) ?? '',
    );
    _gender = user?.gender == 'female' ? 'female' : 'male';
    _activityLevel = _normalizeActivity(user?.activityLevel);
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

  String _normalizeActivity(String? value) {
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
      default:
        return 'sedentary';
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
    if (number == null) return 'Giá trị không hợp lệ';
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

    setState(() => _isSaving = true);
    try {
      final updated = current.copyWith(
        name: _nameController.text.trim(),
        age: int.parse(_ageController.text.trim()),
        gender: _gender,
        height: _parseNumber(_heightController.text)!,
        weight: _parseNumber(_weightController.text)!,
        targetWeight: _targetWeightController.text.trim().isEmpty
            ? current.targetWeight
            : _parseNumber(_targetWeightController.text),
        activityLevel: _activityLevel,
      );
      await provider.updateProfile(updated);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã cập nhật hồ sơ sức khỏe')),
      );
      Navigator.pop(context);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không thể lưu hồ sơ: $error')),
      );
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<UserProvider>().currentUser;
    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Thông tin cá nhân')),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
            children: [
              _ProfileSummary(user: user),
              const SizedBox(height: 24),
              const _SectionTitle(
                title: 'Thông tin cơ bản',
                subtitle: 'Dùng để cá nhân hóa các chỉ số sức khỏe.',
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _nameController,
                textInputAction: TextInputAction.next,
                validator: _requiredText,
                decoration: const InputDecoration(
                  labelText: 'Họ và tên',
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                initialValue: user.email,
                readOnly: true,
                decoration: const InputDecoration(
                  labelText: 'Email',
                  prefixIcon: Icon(Icons.email_outlined),
                  helperText: 'Email được quản lý bởi tài khoản đăng nhập.',
                ),
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _ageController,
                      keyboardType: TextInputType.number,
                      validator: _validAge,
                      decoration: const InputDecoration(
                        labelText: 'Tuổi',
                        prefixIcon: Icon(Icons.cake_outlined),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: _gender,
                      decoration: const InputDecoration(
                        labelText: 'Giới tính',
                      ),
                      items: const [
                        DropdownMenuItem(value: 'male', child: Text('Nam')),
                        DropdownMenuItem(value: 'female', child: Text('Nữ')),
                      ],
                      onChanged: (value) {
                        if (value != null) _gender = value;
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              const _SectionTitle(
                title: 'Chỉ số cơ thể',
                subtitle:
                    'Cập nhật đúng số liệu để BMI, BMR và TDEE chính xác.',
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _heightController,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      validator: (value) => _numberInRange(
                        value,
                        min: 100,
                        max: 250,
                        unit: 'cm',
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Chiều cao (cm)',
                        prefixIcon: Icon(Icons.height),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _weightController,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      validator: (value) => _numberInRange(
                        value,
                        min: 25,
                        max: 400,
                        unit: 'kg',
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Cân nặng (kg)',
                        prefixIcon: Icon(Icons.monitor_weight_outlined),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _targetWeightController,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                validator: (value) => _numberInRange(
                  value,
                  min: 25,
                  max: 400,
                  unit: 'kg',
                  optional: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Cân nặng mục tiêu (kg)',
                  prefixIcon: Icon(Icons.flag_outlined),
                ),
              ),
              const SizedBox(height: 24),
              const _SectionTitle(
                title: 'Mức độ vận động',
                subtitle: 'Ảnh hưởng trực tiếp đến TDEE và lượng calo đề xuất.',
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _activityLevel,
                decoration: const InputDecoration(
                  labelText: 'Hoạt động hằng tuần',
                  prefixIcon: Icon(Icons.directions_run),
                ),
                items: _activities.entries
                    .map(
                      (entry) => DropdownMenuItem(
                        value: entry.key,
                        child: Text(entry.value),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null) _activityLevel = value;
                },
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: FilledButton.icon(
            onPressed: _isSaving ? null : _save,
            icon: _isSaving
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.save_outlined),
            label: Text(_isSaving ? 'Đang lưu...' : 'Lưu thay đổi'),
          ),
        ),
      ),
    );
  }
}

class _ProfileSummary extends StatelessWidget {
  const _ProfileSummary({required this.user});

  final UserModel user;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: AppColors.primaryGradient,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Row(
        children: [
          const CircleAvatar(
            radius: 25,
            backgroundColor: Colors.white12,
            child: Icon(Icons.health_and_safety, color: Colors.white),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  user.name,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'BMI ${user.bmi.toStringAsFixed(1)} • ${user.bmiCategory}',
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
        ],
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
