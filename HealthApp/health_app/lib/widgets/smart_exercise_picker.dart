import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:provider/provider.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../models/exercise_model.dart';
import '../models/wger_models.dart';
import '../services/local_exercise_service.dart';
import '../theme/app_theme.dart';
import '../config/svg_proxy.dart';
import '../widgets/wger_image.dart';

/// Helper widget — load SVG qua proxy trên Web, URL gốc trên native
class _SvgW extends StatelessWidget {
  final String url;
  final ColorFilter? colorFilter;
  final BoxFit fit;

  const _SvgW(this.url, {this.colorFilter, this.fit = BoxFit.contain});

  @override
  Widget build(BuildContext context) => SvgPicture.network(
        SvgProxy.resolve(url),
        fit: fit,
        colorFilter: colorFilter,
        placeholderBuilder: (_) => const SizedBox.shrink(),
      );
}

/// Data nhóm cơ hardcode từ wger (id, tên, SVG URL, body side)
class _MuscleGroup {
  final int id;
  final String nameVi;
  final String nameEn;
  final String svgUrl;
  final bool isFront;
  final Color color;

  const _MuscleGroup({
    required this.id,
    required this.nameVi,
    required this.nameEn,
    required this.svgUrl,
    required this.isFront,
    required this.color,
  });
}
const _bodyFront = 'https://wger.de/static/images/muscles/muscular_system_front.svg';
const _bodyBack  = 'https://wger.de/static/images/muscles/muscular_system_back.svg';

const _muscleGroups = <_MuscleGroup>[
  _MuscleGroup(id: 4,  nameVi: 'Ngực',       nameEn: 'Chest',      isFront: true,  color: Color(0xFFfa709a), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-4.c9fa9a228bc8.svg'),
  _MuscleGroup(id: 1,  nameVi: 'Tay trước',  nameEn: 'Biceps',     isFront: true,  color: Color(0xFF667eea), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-1.8790f8a0b3b9.svg'),
  _MuscleGroup(id: 5,  nameVi: 'Tay sau',    nameEn: 'Triceps',    isFront: false, color: Color(0xFF764ba2), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-5.8a2b934b5486.svg'),
  _MuscleGroup(id: 2,  nameVi: 'Vai',        nameEn: 'Shoulders',  isFront: true,  color: Color(0xFF43e97b), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-2.e1e1205a3202.svg'),
  _MuscleGroup(id: 6,  nameVi: 'Bụng',       nameEn: 'Abs',        isFront: true,  color: Color(0xFF4facfe), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-6.592f938fa8c7.svg'),
  _MuscleGroup(id: 12, nameVi: 'Lưng xô',    nameEn: 'Lats',       isFront: false, color: Color(0xFF30cfd0), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-12.6a5de7a0e373.svg'),
  _MuscleGroup(id: 9,  nameVi: 'Cơ thang',   nameEn: 'Trapezius',  isFront: false, color: Color(0xFFa18cd1), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-9.b491050a7108.svg'),
  _MuscleGroup(id: 8,  nameVi: 'Mông',       nameEn: 'Glutes',     isFront: false, color: Color(0xFFf5576c), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-8.fbdfb46f3bc0.svg'),
  _MuscleGroup(id: 10, nameVi: 'Đùi trước',  nameEn: 'Quads',      isFront: true,  color: Color(0xFFff9a56), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-10.b1445ea1acf6.svg'),
  _MuscleGroup(id: 11, nameVi: 'Đùi sau',    nameEn: 'Hamstrings', isFront: false, color: Color(0xFFfee140), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-11.54ef31755917.svg'),
  _MuscleGroup(id: 7,  nameVi: 'Bắp chân',   nameEn: 'Calves',     isFront: false, color: Color(0xFF56ab2f), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-7.edbd8c381b0c.svg'),
  _MuscleGroup(id: 14, nameVi: 'Cơ chéo',    nameEn: 'Obliques',   isFront: true,  color: Color(0xFFf093fb), svgUrl: 'https://wger.de/static/images/muscles/main/muscle-14.153978038d0b.svg'),
];

//  Main widget 

class SmartExercisePicker extends StatefulWidget {
  const SmartExercisePicker({super.key});

  @override
  State<SmartExercisePicker> createState() => _SmartExercisePickerState();
}

class _SmartExercisePickerState extends State<SmartExercisePicker> {
  final LocalExerciseService _local = LocalExerciseService();
  _MuscleGroup? _selectedMuscle;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _local.loadExercises().then((_) => setState(() => _loading = false));
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.92,
      minChildSize: 0.5,
      maxChildSize: 0.97,
      expand: false,
      builder: (ctx, sc) => Container(
        decoration: const BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(children: [
          _buildHandle(),
          if (_selectedMuscle == null)
            _buildMuscleGrid(sc)
          else
            _buildExerciseList(sc),
        ]),
      ),
    );
  }

  Widget _buildHandle() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      child: Column(children: [
        Center(
          child: Container(
            width: 40, height: 4,
            decoration: BoxDecoration(
              color: AppColors.textHint, borderRadius: BorderRadius.circular(2)),
          ),
        ),
        const SizedBox(height: 14),
        Row(children: [
          if (_selectedMuscle != null)
            GestureDetector(
              onTap: () => setState(() => _selectedMuscle = null),
              child: Container(
                margin: const EdgeInsets.only(right: 10),
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.arrow_back_ios_new, size: 16),
              ),
            ),
          Text(
            _selectedMuscle == null ? 'Chọn nhóm cơ' : _selectedMuscle!.nameVi,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          if (_selectedMuscle != null) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: _selectedMuscle!.color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '${_local.getByMuscle(_selectedMuscle!.id).length} bài',
                style: TextStyle(fontSize: 11, color: _selectedMuscle!.color, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ]),
        const SizedBox(height: 12),
      ]),
    );
  }

  //  Trang 1: Grid nhóm cơ 

  Widget _buildMuscleGrid(ScrollController sc) {
    return Expanded(
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : GridView.builder(
              controller: sc,
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 0.78,
              ),
              itemCount: _muscleGroups.length,
              itemBuilder: (_, i) => _buildMuscleCard(_muscleGroups[i]),
            ),
    );
  }

  Widget _buildMuscleCard(_MuscleGroup muscle) {
    final count = _local.getByMuscle(muscle.id).length;

    return GestureDetector(
      onTap: () => setState(() => _selectedMuscle = muscle),
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: muscle.color.withOpacity(0.3), width: 1.5),
          boxShadow: [
            BoxShadow(color: muscle.color.withOpacity(0.08), blurRadius: 8, offset: const Offset(0, 2)),
          ],
        ),
        child: Column(children: [
          // Cartoon body diagram
          Expanded(
            child: ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(14)),
              child: Container(
                color: muscle.color.withOpacity(0.06),
                child: _AnimatedMuscleCard(muscle: muscle),
              ),
            ),
          ),
          // Label
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
            child: Column(children: [
              Text(
                muscle.nameVi,
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 2),
              Text(
                '$count bài',
                style: TextStyle(fontSize: 10, color: muscle.color, fontWeight: FontWeight.w600),
              ),
            ]),
          ),
        ]),
      ),
    );
  }

  //  Trang 2: Danh sách bài tập của nhóm cơ 

  Widget _buildExerciseList(ScrollController sc) {
    final muscle = _selectedMuscle!;
    final exercises = _local.getByMuscle(muscle.id);

    return Expanded(
      child: Column(children: [
        // Muscle diagram header
        _buildMuscleDiagramHeader(muscle),
        const Divider(height: 1),
        // Exercise list
        Expanded(
          child: exercises.isEmpty
              ? const Center(
                  child: Text('Không có bài tập', style: TextStyle(color: AppColors.textSecondary)),
                )
              : ListView.builder(
                  controller: sc,
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                  itemCount: exercises.length,
                  itemBuilder: (_, i) => _buildExerciseCard(exercises[i], muscle),
                ),
        ),
      ]),
    );
  }

  Widget _buildMuscleDiagramHeader(_MuscleGroup muscle) {
    return Container(
      color: muscle.color.withOpacity(0.05),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Row(children: [
        // Cartoon diagram nhỏ
        SizedBox(
          width: 80, height: 80,
          child: _AnimatedMuscleCard(muscle: muscle),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(muscle.nameVi,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            Text(muscle.nameEn,
                style: TextStyle(fontSize: 13, color: muscle.color, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            Text(
              '${_local.getByMuscle(muscle.id).length} bài tập',
              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ]),
        ),
        Container(
          width: 10, height: 10,
          decoration: BoxDecoration(color: muscle.color, shape: BoxShape.circle),
        ),
      ]),
    );
  }

  Widget _buildExerciseCard(WgerExercise exercise, _MuscleGroup muscle) {
    final isPrimary = exercise.muscles.any((m) => m.id == muscle.id);

    return GestureDetector(
      onTap: () => _showAddDialog(exercise, muscle),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isPrimary ? muscle.color.withOpacity(0.4) : AppColors.surfaceLight,
            width: isPrimary ? 1.5 : 1,
          ),
        ),
        child: Row(children: [
          // Exercise image or gradient icon
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              width: 52, height: 52,
              child: exercise.imageUrl != null
                  ? WgerImage(exercise.imageUrl!, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => _iconBox(muscle.color))
                  : _iconBox(muscle.color),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(exercise.name,
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
              const SizedBox(height: 4),
              Row(children: [
                // Category badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: muscle.color.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(exercise.categoryName,
                      style: TextStyle(fontSize: 9, color: muscle.color, fontWeight: FontWeight.w700)),
                ),
                if (isPrimary) ...[
                  const SizedBox(width: 5),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.success.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text('Chính',
                        style: TextStyle(fontSize: 9, color: AppColors.success, fontWeight: FontWeight.w700)),
                  ),
                ],
                if (exercise.equipment.isNotEmpty) ...[
                  const SizedBox(width: 5),
                  Flexible(
                    child: Text(exercise.equipment.first.name,
                        style: const TextStyle(fontSize: 10, color: AppColors.textHint),
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
                ],
              ]),
            ]),
          ),
          Container(
            width: 32, height: 32,
            decoration: BoxDecoration(
              color: muscle.color.withOpacity(0.15),
              shape: BoxShape.circle,
            ),
            child: Icon(Icons.add, size: 18, color: muscle.color),
          ),
        ]),
      ),
    );
  }

  Widget _iconBox(Color color) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [color, color.withOpacity(0.6)]),
      ),
      child: const Icon(Icons.fitness_center, color: Colors.white, size: 26),
    );
  }

  void _showAddDialog(WgerExercise exercise, _MuscleGroup muscle) {
    final ctrl = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;
    String selectedTimeOfDay = _defaultTimeOfDay();

    final timeSlots = [
      {'value': 'morning',   'label': 'Sáng',  'icon': Icons.wb_sunny_outlined,    'color': const Color(0xFFFF9800)},
      {'value': 'afternoon', 'label': 'Chiều', 'icon': Icons.wb_cloudy_outlined,   'color': const Color(0xFF2196F3)},
      {'value': 'evening',   'label': 'Tối',   'icon': Icons.nights_stay_outlined, 'color': const Color(0xFF9C27B0)},
      {'value': 'night',     'label': 'Đêm',   'icon': Icons.bedtime_outlined,     'color': const Color(0xFF3F51B5)},
    ];

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, ss) {
          final dur = int.tryParse(ctrl.text) ?? 30;
          final cal = user != null ? 5.0 * user.weight * (dur / 60.0) : 0.0;
          return AlertDialog(
            backgroundColor: AppColors.surface,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Text(exercise.name, style: const TextStyle(fontSize: 15)),
            content: Column(mainAxisSize: MainAxisSize.min, children: [
              // Muscle diagram mini
              SizedBox(
                height: 80,
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  SizedBox(
                    width: 70, height: 80,
                    child: _AnimatedMuscleCard(muscle: muscle),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(muscle.nameVi,
                          style: TextStyle(fontSize: 13, color: muscle.color, fontWeight: FontWeight.bold)),
                      if (exercise.equipment.isNotEmpty)
                        Text(exercise.equipment.first.name,
                            style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                    ],
                  ),
                ]),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: ctrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Thời gian (phút)', suffixText: 'phút'),
                onChanged: (_) => ss(() {}),
                autofocus: true,
              ),
              const SizedBox(height: 14),
              // Chọn buổi tập
              Align(
                alignment: Alignment.centerLeft,
                child: Text('Buổi tập', style: TextStyle(fontSize: 13, color: AppColors.textSecondary, fontWeight: FontWeight.w500)),
              ),
              const SizedBox(height: 8),
              Row(
                children: timeSlots.map((slot) {
                  final isSelected = selectedTimeOfDay == slot['value'];
                  final color = slot['color'] as Color;
                  return Expanded(
                    child: GestureDetector(
                      onTap: () => ss(() => selectedTimeOfDay = slot['value'] as String),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        decoration: BoxDecoration(
                          color: isSelected ? color.withOpacity(0.15) : AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: isSelected ? color : Colors.transparent,
                            width: 1.5,
                          ),
                        ),
                        child: Column(
                          children: [
                            Icon(slot['icon'] as IconData, size: 18, color: isSelected ? color : AppColors.textHint),
                            const SizedBox(height: 3),
                            Text(slot['label'] as String, style: TextStyle(fontSize: 10, color: isSelected ? color : AppColors.textHint, fontWeight: isSelected ? FontWeight.bold : FontWeight.normal)),
                          ],
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  gradient: AppColors.calorieGradient,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  const Icon(Icons.local_fire_department, color: Colors.white, size: 20),
                  const SizedBox(width: 8),
                  Text('~${cal.toStringAsFixed(0)} kcal',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                ]),
              ),
            ]),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Hủy')),
              ElevatedButton(
                onPressed: () {
                  _addExercise(exercise, int.tryParse(ctrl.text) ?? 30, cal, selectedTimeOfDay);
                  Navigator.pop(ctx);
                  Navigator.pop(context);
                },
                child: const Text('Thêm vào nhật ký'),
              ),
            ],
          );
        },
      ),
    );
  }

  String _defaultTimeOfDay() {
    final hour = DateTime.now().hour;
    if (hour >= 5 && hour < 12) return 'morning';
    if (hour >= 12 && hour < 17) return 'afternoon';
    if (hour >= 17 && hour < 21) return 'evening';
    return 'night';
  }

  void _addExercise(WgerExercise exercise, int duration, double calories, String timeOfDay) {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;

    final cat = exercise.categoryName.toLowerCase();
    String type = 'strength';
    if (cat.contains('cardio')) type = 'cardio';

    Provider.of<ExerciseProvider>(context, listen: false).addExercise(
      ExerciseModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: userId,
        name: exercise.name,
        date: DateTime.now(),
        duration: duration,
        caloriesBurned: calories,
        type: type,
        intensity: 'medium',
        timeOfDay: timeOfDay,
      ),
    );

    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text('Da them "${exercise.name}"'),
      backgroundColor: AppColors.success,
      duration: const Duration(seconds: 2),
    ));
  }
}

// ═══════════════════════════════════════════════════════════════
// Wger body diagram với SVG overlay
// ═══════════════════════════════════════════════════════════════

class _AnimatedMuscleCard extends StatefulWidget {
  final _MuscleGroup muscle;
  const _AnimatedMuscleCard({required this.muscle});

  @override
  State<_AnimatedMuscleCard> createState() => _AnimatedMuscleCardState();
}

class _AnimatedMuscleCardState extends State<_AnimatedMuscleCard> {
  @override
  Widget build(BuildContext context) {
    // Sử dụng body diagram SVG từ Wger
    final bodyUrl = widget.muscle.isFront ? _bodyFront : _bodyBack;
    final muscleUrl = widget.muscle.svgUrl;

    return Container(
      color: widget.muscle.color.withOpacity(0.05),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Body diagram nền (màu xám nhạt)
          SvgPicture.network(
            SvgProxy.resolve(bodyUrl),
            fit: BoxFit.contain,
            colorFilter: ColorFilter.mode(
              Colors.grey.withOpacity(0.25),
              BlendMode.srcIn,
            ),
            placeholderBuilder: (_) => const Center(
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
          // Muscle highlight overlay (màu của nhóm cơ)
          SvgPicture.network(
            SvgProxy.resolve(muscleUrl),
            fit: BoxFit.contain,
            colorFilter: ColorFilter.mode(
              widget.muscle.color.withOpacity(0.9),
              BlendMode.srcIn,
            ),
            placeholderBuilder: (_) => const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}
