import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../models/workout_routine_model.dart';
import '../../../models/exercise_model.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/workout_simulation_painter.dart';

/// Màn hình tương tác mô phỏng và phát bài tập luyện (Interactive Workout Player)
class WorkoutSimulationScreen extends StatefulWidget {
  final WorkoutRoutinePlan routine;
  final Future<void> Function()? onSaveToJournal;

  const WorkoutSimulationScreen({
    super.key,
    required this.routine,
    this.onSaveToJournal,
  });

  @override
  State<WorkoutSimulationScreen> createState() =>
      _WorkoutSimulationScreenState();
}

class _WorkoutSimulationScreenState extends State<WorkoutSimulationScreen>
    with TickerProviderStateMixin {
  late List<WorkoutExerciseStep> _allExercises;
  int _currentExerciseIndex = 0;
  int _currentSet = 1;

  bool _isResting = false;
  int _restSecondsRemaining = 45;
  Timer? _restTimer;

  bool _isTimedExercise = false;
  int _timedSecondsRemaining = 30;
  bool _isTimerRunning = false;
  Timer? _exerciseTimer;

  int _totalWorkoutElapsedSeconds = 0;
  Timer? _workoutStopwatch;

  @override
  void initState() {
    super.initState();
    _allExercises = widget.routine.allExercises;
    _setupCurrentExercise();
    _startWorkoutStopwatch();
  }

  @override
  void dispose() {
    _restTimer?.cancel();
    _exerciseTimer?.cancel();
    _workoutStopwatch?.cancel();
    super.dispose();
  }

  void _startWorkoutStopwatch() {
    _workoutStopwatch = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _totalWorkoutElapsedSeconds++;
        });
      }
    });
  }

  void _setupCurrentExercise() {
    _restTimer?.cancel();
    _exerciseTimer?.cancel();
    _isResting = false;

    if (_currentExerciseIndex < _allExercises.length) {
      final ex = _allExercises[_currentExerciseIndex];
      _currentSet = (ex.completedSets + 1).clamp(1, ex.sets);
      _isTimedExercise = ex.durationSeconds != null && ex.durationSeconds! > 0;
      if (_isTimedExercise) {
        _timedSecondsRemaining = ex.durationSeconds!;
        _isTimerRunning = true;
        _startExerciseTimer();
      } else {
        _isTimerRunning = false;
      }
    }
  }

  void _startExerciseTimer() {
    _exerciseTimer?.cancel();
    _exerciseTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      if (_timedSecondsRemaining > 0) {
        setState(() {
          _timedSecondsRemaining--;
        });
      } else {
        _exerciseTimer?.cancel();
        _onCompleteSet();
      }
    });
  }

  void _toggleExerciseTimer() {
    setState(() {
      _isTimerRunning = !_isTimerRunning;
      if (_isTimerRunning) {
        _startExerciseTimer();
      } else {
        _exerciseTimer?.cancel();
      }
    });
  }

  void _startRestTimer(int durationSeconds) {
    _exerciseTimer?.cancel();
    setState(() {
      _isResting = true;
      _restSecondsRemaining = durationSeconds;
    });

    _restTimer?.cancel();
    _restTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      if (_restSecondsRemaining > 0) {
        setState(() {
          _restSecondsRemaining--;
        });
      } else {
        _restTimer?.cancel();
        _skipRest();
      }
    });
  }

  void _skipRest() {
    _restTimer?.cancel();
    setState(() {
      _isResting = false;
    });
    // Nếu hiệp tiếp theo của bài hiện tại
    final currentEx = _allExercises[_currentExerciseIndex];
    if (_currentSet <= currentEx.sets) {
      _setupCurrentExercise();
    } else {
      _nextExercise();
    }
  }

  void _onCompleteSet() {
    final currentEx = _allExercises[_currentExerciseIndex];
    setState(() {
      currentEx.completedSets++;
      if (currentEx.completedSets >= currentEx.sets) {
        currentEx.isCompleted = true;
      }
    });

    if (currentEx.completedSets < currentEx.sets) {
      _currentSet = currentEx.completedSets + 1;
      _startRestTimer(currentEx.restSeconds);
    } else {
      // Đã xong tất cả các hiệp của bài hiện tại
      if (_currentExerciseIndex < _allExercises.length - 1) {
        _startRestTimer(currentEx.restSeconds + 15); // Nghỉ dài hơn khi đổi bài
      } else {
        // Đã hoàn thành toàn bộ bài tập trong buổi!
        _showWorkoutCelebrationDialog();
      }
    }
  }

  void _nextExercise() {
    if (_currentExerciseIndex < _allExercises.length - 1) {
      setState(() {
        _currentExerciseIndex++;
      });
      _setupCurrentExercise();
    } else {
      _showWorkoutCelebrationDialog();
    }
  }

  void _previousExercise() {
    if (_currentExerciseIndex > 0) {
      setState(() {
        _currentExerciseIndex--;
      });
      _setupCurrentExercise();
    }
  }

  String _formatTime(int totalSeconds) {
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }

  double get _overallProgress {
    if (_allExercises.isEmpty) return 1.0;
    int totalSets = 0;
    int doneSets = 0;
    for (final ex in _allExercises) {
      totalSets += ex.sets;
      doneSets += ex.completedSets;
    }
    return totalSets == 0 ? 1.0 : (doneSets / totalSets).clamp(0.0, 1.0);
  }

  String _getCurrentPhaseTitle() {
    if (_allExercises.isEmpty) return '';
    final ex = _allExercises[_currentExerciseIndex];
    for (final p in widget.routine.phases) {
      if (p.exercises.any((e) => e.id == ex.id)) {
        return p.title;
      }
    }
    return 'Thân bài tập luyện';
  }

  @override
  Widget build(BuildContext context) {
    final currentEx = _currentExerciseIndex < _allExercises.length
        ? _allExercises[_currentExerciseIndex]
        : _allExercises.last;

    final phaseTitle = _getCurrentPhaseTitle();
    final primaryColor = _isResting ? AppColors.info : AppColors.primary;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: AppColors.textPrimary),
          tooltip: 'Thoát',
          onPressed: _showExitConfirmationDialog,
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              widget.routine.title,
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            Text(
              'Bài ${_currentExerciseIndex + 1} / ${_allExercises.length} · ${_formatTime(_totalWorkoutElapsedSeconds)}',
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline, color: AppColors.textPrimary),
            tooltip: 'Hướng dẫn động tác',
            onPressed: () => _showExerciseDetailSheet(currentEx),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Thanh tiến độ tổng thể (Overall Progress Bar)
            Container(
              height: 4,
              width: double.infinity,
              color: AppColors.surfaceLight,
              child: FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: _overallProgress,
                child: Container(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        AppColors.primary,
                        AppColors.accent,
                      ],
                    ),
                  ),
                ),
              ),
            ),

            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Phase badge
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(AppRadius.pill),
                        border: Border.all(color: AppColors.surfaceLight),
                      ),
                      child: Text(
                        phaseTitle,
                        style: const TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),

                    // Canvas Hoạt ảnh mô phỏng
                    WorkoutSimulationWidget(
                      animationType: currentEx.animationType,
                      exerciseName: currentEx.name,
                      isResting: _isResting,
                      height: 230,
                    ),

                    const SizedBox(height: 16),

                    // Thẻ thông tin bài tập hiện tại
                    _buildExerciseHeaderCard(currentEx),

                    const SizedBox(height: 16),

                    // Vùng đếm giờ hoặc hoàn thành hiệp
                    _isResting
                        ? _buildRestControlCard()
                        : _buildActiveSetControlCard(currentEx, primaryColor),

                    const SizedBox(height: 16),

                    // Cues kỹ thuật tóm tắt
                    _buildTechniqueSummary(currentEx),
                  ],
                ),
              ),
            ),

            // Thanh điều hướng đáy
            _buildBottomNavigationBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildExerciseHeaderCard(WorkoutExerciseStep currentEx) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: AppColors.surfaceLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      currentEx.name,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    if (currentEx.vietnameseName.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        currentEx.vietnameseName,
                        style: const TextStyle(
                          fontSize: 13,
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(AppRadius.pill),
                ),
                child: Text(
                  '${currentEx.sets} hiệp × ${currentEx.reps}',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // Chips nhóm cơ và thiết bị
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _infoBadge(Icons.fitness_center, currentEx.equipment,
                  AppColors.textSecondary),
              _infoBadge(Icons.accessibility_new, currentEx.targetMusclesText,
                  AppColors.warning),
              _infoBadge(Icons.timer_outlined, 'Nghỉ ${currentEx.restSeconds}s',
                  AppColors.info),
            ],
          ),

          const SizedBox(height: 12),

          // Hiển thị các chấm hiệp tập (Set progression dots)
          Row(
            children: [
              const Text(
                'Tiến độ hiệp: ',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
              const SizedBox(width: 6),
              ...List.generate(currentEx.sets, (index) {
                final isDone = index < currentEx.completedSets;
                final isCurrent =
                    index == currentEx.completedSets && !_isResting;
                return Container(
                  margin: const EdgeInsets.only(right: 6),
                  width: 28,
                  height: 24,
                  decoration: BoxDecoration(
                    color: isDone
                        ? AppColors.accent
                        : isCurrent
                            ? AppColors.primary
                            : AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                    border: isCurrent
                        ? Border.all(color: AppColors.primary, width: 1.5)
                        : null,
                  ),
                  child: Center(
                    child: Text(
                      'H${index + 1}',
                      style: TextStyle(
                        fontSize: 10.5,
                        fontWeight: FontWeight.bold,
                        color: isDone
                            ? Colors.black
                            : isCurrent
                                ? Colors.white
                                : AppColors.textSecondary,
                      ),
                    ),
                  ),
                );
              }),
            ],
          ),
        ],
      ),
    );
  }

  Widget _infoBadge(IconData icon, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
                fontSize: 11, color: color, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveSetControlCard(
      WorkoutExerciseStep currentEx, Color primaryColor) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: AppColors.surfaceLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'HIỆP $_currentSet / ${currentEx.sets}',
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.8,
                  color: AppColors.textSecondary,
                ),
              ),
              Text(
                _isTimedExercise
                    ? 'Đếm thời gian'
                    : 'Mục tiêu: ${currentEx.reps}',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_isTimedExercise) ...[
            // Vòng tròn đếm ngược thời gian
            Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: 120,
                  height: 120,
                  child: CircularProgressIndicator(
                    value: currentEx.durationSeconds != null &&
                            currentEx.durationSeconds! > 0
                        ? _timedSecondsRemaining / currentEx.durationSeconds!
                        : 0.0,
                    strokeWidth: 8,
                    backgroundColor: AppColors.surfaceLight,
                    valueColor: AlwaysStoppedAnimation<Color>(primaryColor),
                  ),
                ),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '$_timedSecondsRemaining',
                      style: const TextStyle(
                        fontSize: 34,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const Text(
                      'giây',
                      style: TextStyle(
                          fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _toggleExerciseTimer,
                    icon: Icon(
                      _isTimerRunning
                          ? Icons.pause_rounded
                          : Icons.play_arrow_rounded,
                      size: 20,
                    ),
                    label: Text(_isTimerRunning ? 'Tạm dừng' : 'Tiếp tục'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.textPrimary,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      side: const BorderSide(color: AppColors.textPrimary),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(AppRadius.pill)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _onCompleteSet,
                    icon: const Icon(Icons.check_circle_outline, size: 20),
                    label: const Text('Xong hiệp'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(AppRadius.pill)),
                    ),
                  ),
                ),
              ],
            ),
          ] else ...[
            // Động tác tính theo số lần (reps)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.repeat_rounded,
                      color: AppColors.textSecondary, size: 24),
                  const SizedBox(width: 8),
                  Text(
                    currentEx.reps,
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _onCompleteSet,
                icon: const Icon(Icons.check_circle, size: 22),
                label: Text(
                  _currentSet < currentEx.sets
                      ? 'Hoàn thành Hiệp $_currentSet'
                      : 'Hoàn thành bài tập',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.pill)),
                  elevation: 0,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildRestControlCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.info.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: AppColors.info.withValues(alpha: 0.22)),
      ),
      child: Column(
        children: [
          const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.bedtime_outlined, color: AppColors.info, size: 18),
              SizedBox(width: 8),
              Text(
                'NGHỈ NGƠI & HỒI SỨC',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1,
                  color: AppColors.info,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Vòng tròn đếm ngược thời gian nghỉ
          Stack(
            alignment: Alignment.center,
            children: [
              SizedBox(
                width: 100,
                height: 100,
                child: CircularProgressIndicator(
                  value: _restSecondsRemaining / 45.0,
                  strokeWidth: 6,
                  backgroundColor: AppColors.surfaceLight,
                  valueColor: const AlwaysStoppedAnimation<Color>(AppColors.info),
                ),
              ),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '$_restSecondsRemaining',
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const Text(
                    'giây',
                    style: TextStyle(
                        fontSize: 11, color: AppColors.textSecondary),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Nút bỏ qua nghỉ
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _skipRest,
              icon: const Icon(Icons.fast_forward_rounded, size: 20),
              label: const Text('Bỏ qua nghỉ & Tập tiếp'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.pill)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTechniqueSummary(WorkoutExerciseStep currentEx) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E1),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.lightbulb_outline, color: Colors.amber, size: 16),
              SizedBox(width: 6),
              Text(
                'Lưu ý kỹ thuật nhanh',
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.bold,
                  color: Colors.amber,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            currentEx.tips.isNotEmpty
                ? currentEx.tips
                : 'Giữ thân người thẳng, hít thở sâu và gồng chắc cơ lõi.',
            style: const TextStyle(
              fontSize: 12.5,
              color: AppColors.textSecondary,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomNavigationBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: const Border(top: BorderSide(color: AppColors.surfaceLight)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: _currentExerciseIndex > 0 ? _previousExercise : null,
            icon: const Icon(Icons.skip_previous_rounded),
            color: AppColors.textPrimary,
            disabledColor: AppColors.textHint,
            tooltip: 'Bài trước',
          ),
          Text(
            'Tiến độ: ${(_overallProgress * 100).toStringAsFixed(0)}%',
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.bold,
              color: AppColors.textSecondary,
            ),
          ),
          IconButton(
            onPressed: _currentExerciseIndex < _allExercises.length - 1
                ? _nextExercise
                : null,
            icon: const Icon(Icons.skip_next_rounded),
            color: AppColors.textPrimary,
            disabledColor: AppColors.textHint,
            tooltip: 'Bài tiếp theo',
          ),
        ],
      ),
    );
  }

  void _showExerciseDetailSheet(WorkoutExerciseStep ex) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Container(
        padding: const EdgeInsets.all(20),
        decoration: const BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.textHint,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              ex.displayName,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Nhóm cơ: ${ex.targetMusclesText}',
              style: const TextStyle(
                  fontSize: 13, color: AppColors.textSecondary),
            ),
            const Divider(color: AppColors.surfaceLight, height: 24),
            const Text(
              '📋 Hướng dẫn thực hiện:',
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary),
            ),
            const SizedBox(height: 8),
            Text(
              ex.instructions.isNotEmpty
                  ? ex.instructions
                  : 'Thực hiện động tác đúng kỹ thuật, kiểm soát nhịp phát lực.',
              style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary,
                  height: 1.6),
            ),
            const SizedBox(height: 16),
            const Text(
              '🌬️ Nhịp thở chuẩn:',
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary),
            ),
            const SizedBox(height: 6),
            Text(
              ex.breathingCue.isNotEmpty
                  ? ex.breathingCue
                  : 'Hít sâu khi hạ tạ, thở ra dứt khoát khi dùng lực đẩy/kéo.',
              style: const TextStyle(fontSize: 13, color: AppColors.info),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => Navigator.pop(ctx),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.pill)),
                ),
                child: const Text('Đã hiểu, quay lại tập'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showExitConfirmationDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Tạm dừng buổi tập?',
            style: TextStyle(color: AppColors.textPrimary)),
        content: const Text(
          'Tiến độ của bạn sẽ được giữ lại. Bạn có chắc muốn thoát ra ngoài không?',
          style: TextStyle(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Tiếp tục tập'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              Navigator.pop(context);
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('Thoát'),
          ),
        ],
      ),
    );
  }

  void _showWorkoutCelebrationDialog() {
    _workoutStopwatch?.cancel();
    final elapsedMinutes = (_totalWorkoutElapsedSeconds / 60).ceil();
    final burnedCalories = (elapsedMinutes * 7.0).clamp(50.0, 800.0);

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 70,
              height: 70,
              decoration: BoxDecoration(
                color: AppColors.accent.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.emoji_events_rounded,
                  color: AppColors.accent, size: 40),
            ),
            const SizedBox(height: 16),
            const Text(
              '🎉 HOÀN THÀNH XUẤT SẮC!',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Bạn đã hoàn thành trọn vẹn giáo án "${widget.routine.title}"',
              style: const TextStyle(
                  fontSize: 13, color: AppColors.textSecondary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),

            // Thống kê thành tích
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(AppRadius.lg),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _statItem('Thời gian', '$elapsedMinutes phút',
                      Icons.timer_outlined, AppColors.info),
                  _statItem(
                      'Calo đốt',
                      '~${burnedCalories.toStringAsFixed(0)} kcal',
                      Icons.local_fire_department,
                      AppColors.warning),
                  _statItem('Số bài tập', '${_allExercises.length} bài',
                      Icons.fitness_center, AppColors.accentDark),
                ],
              ),
            ),
            const SizedBox(height: 24),

            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () async {
                  final saved = await _saveWorkoutToExerciseProvider(
                      elapsedMinutes, burnedCalories);
                  if (!saved) return;
                  if (ctx.mounted) Navigator.pop(ctx);
                  if (mounted) Navigator.pop(context);
                },
                icon: const Icon(Icons.bookmark_add_outlined, size: 20),
                label: const Text('Lưu vào nhật ký vận động',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.pill)),
                ),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () {
                Navigator.pop(ctx);
                Navigator.pop(context);
              },
              child:
                  const Text('Đóng',
                      style: TextStyle(color: AppColors.textSecondary)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statItem(String label, String value, IconData icon, Color color) {
    return Column(
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        Text(
          label,
          style: const TextStyle(
              fontSize: 11, color: AppColors.textSecondary),
        ),
      ],
    );
  }

  Future<bool> _saveWorkoutToExerciseProvider(
      int durationMin, double calBurned) async {
    try {
      final customSave = widget.onSaveToJournal;
      if (customSave != null) {
        // Callback là nguồn lưu duy nhất khi màn gọi cần giữ wger_id, category
        // hoặc chỉ đánh dấu một bản ghi đã tồn tại. Tránh tạo hai nhật ký.
        await customSave();
      } else {
        final user =
            Provider.of<UserProvider>(context, listen: false).currentUser;
        if (user == null) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Vui lòng đăng nhập để lưu buổi tập.'),
              backgroundColor: AppColors.error,
            ));
          }
          return false;
        }

        final mainExercise = widget.routine.mainPhase?.exercises.firstOrNull;
        final exercise = ExerciseModel(
          id: 'ex_${DateTime.now().millisecondsSinceEpoch}',
          userId: user.id,
          name: widget.routine.title,
          date: DateTime.now(),
          duration: durationMin > 0 ? durationMin : 30,
          caloriesBurned: calBurned,
          type: ExerciseProvider.mapCategoryToType(
            widget.routine.title,
            mainExercise?.category ?? '',
          ),
          intensity: 'medium',
          isCompleted: true,
        );

        await Provider.of<ExerciseProvider>(context, listen: false)
            .addExercise(exercise);
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Không thể lưu buổi tập. Vui lòng thử lại.'),
          backgroundColor: AppColors.error,
        ));
      }
      return false;
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              '✅ Đã lưu "${widget.routine.title}" (${calBurned.toStringAsFixed(0)} kcal) vào nhật ký vận động hôm nay!'),
          backgroundColor: Colors.green,
          duration: const Duration(seconds: 3),
        ),
      );
    }
    return true;
  }
}
