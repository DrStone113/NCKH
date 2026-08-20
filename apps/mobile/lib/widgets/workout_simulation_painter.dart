import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/workout_routine_model.dart';
import '../theme/app_theme.dart';

/// Biến thể chuyển động chi tiết dùng để chọn đúng hoạt ảnh theo tên bài tập.
///
/// [WorkoutAnimationType] chỉ mô tả nhóm vận động lớn, vì vậy riêng nó không
/// đủ để phân biệt chống đẩy với đẩy vai, hoặc xoay khớp với giãn cơ tĩnh.
enum WorkoutMovementVariant {
  overheadPress,
  benchPress,
  bicepsCurl,
  pushUp,
  squat,
  lunge,
  row,
  plank,
  coreStability,
  standingCoreHold,
  legExtension,
  hipAdduction,
  bearWalk,
  jumpingJack,
  jumpRope,
  highKnees,
  swimming,
  elliptical,
  suspensionCross,
  jointRotation,
  staticStretch,
  recoveryBreathing,
  generic,
}

WorkoutMovementVariant resolveWorkoutMovementVariant(
  WorkoutAnimationType animationType,
  String exerciseName,
) {
  final name = exerciseName.toLowerCase();

  bool hasAny(Iterable<String> terms) => terms.any(name.contains);

  if (hasAny(['jumping jack', 'star jump', 'bật nhảy'])) {
    return WorkoutMovementVariant.jumpingJack;
  }
  if (hasAny(['jump rope', 'skipping', 'nhảy dây'])) {
    return WorkoutMovementVariant.jumpRope;
  }
  if (hasAny(['joint rotation', 'joint mobility', 'arm circle', 'xoay khớp'])) {
    return WorkoutMovementVariant.jointRotation;
  }
  if (hasAny(['high knee', 'running', 'jogging', 'chạy', 'nâng cao đùi'])) {
    return WorkoutMovementVariant.highKnees;
  }
  if (hasAny(['swimming', 'swim', 'bơi', 'crawl stroke', 'butterfly'])) {
    return WorkoutMovementVariant.swimming;
  }
  if (hasAny(['elliptical', 'crosstrainer', 'cross trainer'])) {
    return WorkoutMovementVariant.elliptical;
  }
  if (hasAny(['suspended cross', 'suspension cross', 'trx cross'])) {
    return WorkoutMovementVariant.suspensionCross;
  }
  if (hasAny(['bench press', 'chest press', 'đẩy ngực'])) {
    return WorkoutMovementVariant.benchPress;
  }
  if (hasAny(['biceps curl', 'bicep curl', 'hammer curl', 'wrist curl'])) {
    return WorkoutMovementVariant.bicepsCurl;
  }
  if (hasAny(['push up', 'push-up', 'pushup', 'hít đất', 'chống đẩy'])) {
    return WorkoutMovementVariant.pushUp;
  }
  if (hasAny(['bear walk', 'bear crawl', 'bò gấu'])) {
    return WorkoutMovementVariant.bearWalk;
  }
  if (hasAny(['lunge', 'split squat', 'chùng chân'])) {
    return WorkoutMovementVariant.lunge;
  }
  if (hasAny(['plank', 'đo ván'])) {
    return WorkoutMovementVariant.plank;
  }
  if (hasAny(['abdominal stabilization', 'dead bug', 'ổn định'])) {
    return WorkoutMovementVariant.coreStability;
  }
  if (hasAny(['axe hold', 'front hold', 'giữ tạ'])) {
    return WorkoutMovementVariant.standingCoreHold;
  }
  if (hasAny(['adduction', 'khép đùi', 'ép đùi'])) {
    return WorkoutMovementVariant.hipAdduction;
  }
  if (hasAny(['leg extension', 'đá đùi', 'duỗi gối'])) {
    return WorkoutMovementVariant.legExtension;
  }
  if (hasAny(['breathing', 'hít thở', 'thở sâu'])) {
    return WorkoutMovementVariant.recoveryBreathing;
  }
  if (hasAny(['static stretch', 'cooldown', 'cool-down', 'giãn cơ tĩnh'])) {
    return WorkoutMovementVariant.staticStretch;
  }

  return switch (animationType) {
    WorkoutAnimationType.press => WorkoutMovementVariant.overheadPress,
    WorkoutAnimationType.squat => WorkoutMovementVariant.squat,
    WorkoutAnimationType.pull => WorkoutMovementVariant.row,
    WorkoutAnimationType.coreHold => WorkoutMovementVariant.plank,
    WorkoutAnimationType.legExtension => WorkoutMovementVariant.legExtension,
    WorkoutAnimationType.dynamicMovement => WorkoutMovementVariant.jumpingJack,
    WorkoutAnimationType.stretch => WorkoutMovementVariant.staticStretch,
    WorkoutAnimationType.cardio => WorkoutMovementVariant.highKnees,
    WorkoutAnimationType.generic => WorkoutMovementVariant.generic,
  };
}

String workoutMovementLabel(WorkoutMovementVariant variant) {
  return switch (variant) {
    WorkoutMovementVariant.overheadPress => 'Đẩy qua đầu',
    WorkoutMovementVariant.benchPress => 'Đẩy ngực nằm',
    WorkoutMovementVariant.bicepsCurl => 'Cuốn tay trước',
    WorkoutMovementVariant.pushUp => 'Chống đẩy',
    WorkoutMovementVariant.squat => 'Squat',
    WorkoutMovementVariant.lunge => 'Chùng chân',
    WorkoutMovementVariant.row => 'Kéo lưng',
    WorkoutMovementVariant.plank => 'Giữ plank',
    WorkoutMovementVariant.coreStability => 'Ổn định core',
    WorkoutMovementVariant.standingCoreHold => 'Giữ tạ trước',
    WorkoutMovementVariant.legExtension => 'Duỗi gối',
    WorkoutMovementVariant.hipAdduction => 'Khép đùi',
    WorkoutMovementVariant.bearWalk => 'Bò gấu',
    WorkoutMovementVariant.jumpingJack => 'Bật mở–khép',
    WorkoutMovementVariant.jumpRope => 'Nhảy dây',
    WorkoutMovementVariant.highKnees => 'Nâng cao đùi',
    WorkoutMovementVariant.swimming => 'Quạt tay bơi',
    WorkoutMovementVariant.elliptical => 'Sải bước elip',
    WorkoutMovementVariant.suspensionCross => 'Ép mở dây treo',
    WorkoutMovementVariant.jointRotation => 'Xoay khớp',
    WorkoutMovementVariant.staticStretch => 'Giãn cơ',
    WorkoutMovementVariant.recoveryBreathing => 'Nhịp thở',
    WorkoutMovementVariant.generic => 'Toàn thân',
  };
}

/// Widget hoạt ảnh mô phỏng động tác tập luyện trực quan
class WorkoutSimulationWidget extends StatefulWidget {
  final WorkoutAnimationType animationType;
  final String exerciseName;
  final bool isResting;
  final double
      progress; // 0.0 -> 1.0 (ví dụ thời gian còn lại hoặc chu kỳ hiệp)
  final double height;

  const WorkoutSimulationWidget({
    super.key,
    required this.animationType,
    required this.exerciseName,
    this.isResting = false,
    this.progress = 0.0,
    this.height = 220,
  });

  @override
  State<WorkoutSimulationWidget> createState() =>
      _WorkoutSimulationWidgetState();
}

class _WorkoutSimulationWidgetState extends State<WorkoutSimulationWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat();
  }

  @override
  void didUpdateWidget(WorkoutSimulationWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isResting != oldWidget.isResting) {
      if (widget.isResting) {
        _controller.duration =
            const Duration(milliseconds: 4000); // nhịp thở chậm khi nghỉ
      } else {
        _controller.duration =
            const Duration(milliseconds: 2400); // nhịp tập bình thường
      }
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isRest = widget.isResting;
    final primaryColor = isRest ? const Color(0xFF00ACC1) : AppColors.primary;
    final accentColor =
        isRest ? const Color(0xFF80DEEA) : const Color(0xFFFF9800);
    final movementVariant = resolveWorkoutMovementVariant(
      widget.animationType,
      widget.exerciseName,
    );

    return Container(
      height: widget.height,
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isRest
              ? [const Color(0xFF0D2538), const Color(0xFF071420)]
              : [const Color(0xFF131B2E), const Color(0xFF0B101E)],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: primaryColor.withValues(alpha: 0.3),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: primaryColor.withValues(alpha: 0.15),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        children: [
          // Background Grid / Ambient glow
          Positioned.fill(
            child: CustomPaint(
              painter: _AmbientGlowPainter(
                color: primaryColor,
                accent: accentColor,
                animationValue: _controller.value,
                isRest: isRest,
              ),
            ),
          ),

          // Human Avatar / Movement Simulation Canvas
          Positioned.fill(
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                return CustomPaint(
                  painter: _MovementSimulationPainter(
                    animationType: widget.animationType,
                    exerciseName: widget.exerciseName,
                    animationValue: _controller.value,
                    primaryColor: primaryColor,
                    accentColor: accentColor,
                    isRest: isRest,
                  ),
                );
              },
            ),
          ),

          // Top Info overlay
          Positioned(
            top: 14,
            left: 16,
            right: 16,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: (isRest ? Colors.teal : AppColors.primary)
                        .withValues(alpha: 0.25),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: (isRest ? Colors.tealAccent : AppColors.primary)
                          .withValues(alpha: 0.5),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        isRest
                            ? Icons.bedtime_outlined
                            : Icons.fitness_center_rounded,
                        size: 14,
                        color: isRest ? Colors.tealAccent : Colors.white,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        isRest ? 'THỜI GIAN NGHỈ NGƠI' : 'MÔ PHỎNG ĐỘNG TÁC',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 0.5,
                          color: isRest ? Colors.tealAccent : Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.4),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color:
                              isRest ? Colors.tealAccent : Colors.greenAccent,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        isRest
                            ? 'Thả lỏng cơ bắp'
                            : workoutMovementLabel(movementVariant),
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.white70,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Bottom Breathing & Motion Cue Overlay
          Positioned(
            bottom: 12,
            left: 16,
            right: 16,
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                final val = _controller.value;
                final bool isExpanding = val < 0.5;
                String cueText;
                if (isRest) {
                  cueText = isExpanding
                      ? '🌬️ Hít sâu bằng mũi...'
                      : '💨 Thở chậm bằng miệng...';
                } else {
                  switch (movementVariant) {
                    case WorkoutMovementVariant.overheadPress:
                      cueText = isExpanding
                          ? '⬇️ Hạ tạ ngang vai · Hít vào'
                          : '⬆️ Đẩy thẳng qua đầu · Thở ra';
                      break;
                    case WorkoutMovementVariant.pushUp:
                      cueText = isExpanding
                          ? '⬇️ Hạ cả thân thành một khối · Hít vào'
                          : '⬆️ Đẩy sàn, giữ lưng thẳng · Thở ra';
                      break;
                    case WorkoutMovementVariant.squat:
                      cueText = isExpanding
                          ? '⬇️ Đẩy hông ra sau · Gối theo mũi chân'
                          : '⬆️ Đạp gót đứng lên · Siết mông';
                      break;
                    case WorkoutMovementVariant.row:
                      cueText = isExpanding
                          ? '⬆️ Kéo ép xương bả vai (Thở ra)'
                          : '⬇️ Nhả chậm có lực (Hít vào)';
                      break;
                    case WorkoutMovementVariant.plank:
                      cueText = '🔒 Gồng cứng cơ bụng · Hít thở đều';
                      break;
                    case WorkoutMovementVariant.coreStability:
                      cueText = '🧱 Ép lưng xuống sàn · Tay chân đối bên';
                      break;
                    case WorkoutMovementVariant.standingCoreHold:
                      cueText = '🎯 Giữ tạ ngang ngực · Không ngả lưng';
                      break;
                    case WorkoutMovementVariant.legExtension:
                      cueText = isExpanding
                          ? '⬆️ Đá duỗi gối (Thở ra)'
                          : '⬇️ Thu chân chậm (Hít vào)';
                      break;
                    case WorkoutMovementVariant.hipAdduction:
                      cueText = isExpanding
                          ? '➡️⬅️ Khép đùi, siết 1 giây'
                          : '↔️ Mở chân chậm có kiểm soát';
                      break;
                    case WorkoutMovementVariant.bearWalk:
                      cueText = '🐻 Tay và chân đối bên · Gối luôn gần sàn';
                      break;
                    case WorkoutMovementVariant.jumpingJack:
                      cueText = isExpanding
                          ? '↗️ Bật mở chân, đưa tay qua đầu'
                          : '↘️ Khép chân, tiếp đất thật êm';
                      break;
                    case WorkoutMovementVariant.highKnees:
                      cueText = '🏃 Nâng gối ngang hông · Đánh tay đối bên';
                      break;
                    case WorkoutMovementVariant.jointRotation:
                      cueText = '🔄 Xoay tròn chậm · Biên độ vừa, không giật';
                      break;
                    case WorkoutMovementVariant.staticStretch:
                      cueText = '🧘 Giữ ở điểm căng nhẹ · Không nhấp nhả';
                      break;
                    case WorkoutMovementVariant.recoveryBreathing:
                      cueText = isExpanding
                          ? '🌬️ Hít vào 4 giây · Bụng nở'
                          : '💨 Thở ra 6 giây · Thả lỏng vai';
                      break;
                    default:
                      cueText = isExpanding
                          ? '⚡ Chu kỳ phát lực'
                          : '🔄 Chu kỳ hồi vị trí';
                  }
                }

                return Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: primaryColor.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          cueText,
                          style: const TextStyle(
                            fontSize: 12.5,
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                          ),
                        ),
                      ),
                      // Tempo indicator
                      Row(
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: isExpanding ? accentColor : primaryColor,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            isExpanding ? 'Pha 1' : 'Pha 2',
                            style: TextStyle(
                              fontSize: 11,
                              color: isExpanding ? accentColor : primaryColor,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Custom painter cho hiệu ứng lưới và ánh sáng nền
class _AmbientGlowPainter extends CustomPainter {
  final Color color;
  final Color accent;
  final double animationValue;
  final bool isRest;

  _AmbientGlowPainter({
    required this.color,
    required this.accent,
    required this.animationValue,
    required this.isRest,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final pulse = math.sin(animationValue * math.pi * 2) * 0.15 + 0.85;

    // Vẽ vầng sáng phát ra từ trung tâm
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withValues(alpha: 0.25 * pulse),
          color.withValues(alpha: 0.08 * pulse),
          Colors.transparent,
        ],
        stops: const [0.0, 0.5, 1.0],
      ).createShader(
          Rect.fromCircle(center: center, radius: size.width * 0.45));

    canvas.drawCircle(center, size.width * 0.45, glowPaint);

    // Vẽ lưới tọa độ mờ
    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.04)
      ..strokeWidth = 1.0;

    const step = 28.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    // Vẽ sàn tập (Floor line)
    final floorY = size.height * 0.78;
    final floorPaint = Paint()
      ..shader = LinearGradient(
        colors: [
          Colors.transparent,
          color.withValues(alpha: 0.6),
          Colors.transparent,
        ],
      ).createShader(Rect.fromLTWH(0, floorY, size.width, 2))
      ..strokeWidth = 2.0;

    canvas.drawLine(Offset(size.width * 0.15, floorY),
        Offset(size.width * 0.85, floorY), floorPaint);
  }

  @override
  bool shouldRepaint(covariant _AmbientGlowPainter oldDelegate) => true;
}

class _AthletePose {
  final Offset head;
  final Offset leftShoulder;
  final Offset rightShoulder;
  final Offset leftElbow;
  final Offset rightElbow;
  final Offset leftHand;
  final Offset rightHand;
  final Offset leftHip;
  final Offset rightHip;
  final Offset leftKnee;
  final Offset rightKnee;
  final Offset leftAnkle;
  final Offset rightAnkle;

  const _AthletePose({
    required this.head,
    required this.leftShoulder,
    required this.rightShoulder,
    required this.leftElbow,
    required this.rightElbow,
    required this.leftHand,
    required this.rightHand,
    required this.leftHip,
    required this.rightHip,
    required this.leftKnee,
    required this.rightKnee,
    required this.leftAnkle,
    required this.rightAnkle,
  });
}

/// Painter dùng một bộ khung khớp 13 điểm để giữ đúng tỷ lệ cơ thể và thể hiện
/// rõ góc vai, hông, gối, khuỷu tay trong từng pha chuyển động.
class _MovementSimulationPainter extends CustomPainter {
  final WorkoutAnimationType animationType;
  final String exerciseName;
  final double animationValue;
  final Color primaryColor;
  final Color accentColor;
  final bool isRest;

  _MovementSimulationPainter({
    required this.animationType,
    required this.exerciseName,
    required this.animationValue,
    required this.primaryColor,
    required this.accentColor,
    required this.isRest,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final availableHeight = math.max(90.0, size.height - 98.0);
    final scale = math.min(size.width / 235.0, availableHeight / 118.0);
    final center = Offset(size.width / 2, 49 + availableHeight / 2);
    final phase = animationValue * math.pi * 2;
    final t = (math.sin(phase - math.pi / 2) + 1.0) / 2.0;

    _drawGroundShadow(canvas, center, scale);

    if (isRest) {
      _drawRecoveryBreathing(canvas, center, scale, t);
      return;
    }

    final variant = resolveWorkoutMovementVariant(animationType, exerciseName);
    switch (variant) {
      case WorkoutMovementVariant.overheadPress:
        _drawOverheadPress(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.benchPress:
        _drawBenchPress(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.bicepsCurl:
        _drawBicepsCurl(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.pushUp:
        _drawPushUp(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.squat:
        _drawSquat(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.lunge:
        _drawLunge(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.row:
        _drawBentRow(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.plank:
        _drawPlank(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.coreStability:
        _drawCoreStability(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.standingCoreHold:
        _drawStandingCoreHold(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.legExtension:
        _drawLegExtension(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.hipAdduction:
        _drawHipAdduction(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.bearWalk:
        _drawBearWalk(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.jumpingJack:
        _drawJumpingJack(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.jumpRope:
        _drawJumpRope(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.highKnees:
        _drawHighKnees(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.swimming:
        _drawSwimming(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.elliptical:
        _drawElliptical(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.suspensionCross:
        _drawSuspensionCross(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.jointRotation:
        _drawJointRotation(canvas, center, scale, phase);
        break;
      case WorkoutMovementVariant.staticStretch:
        _drawStaticStretch(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.recoveryBreathing:
        _drawRecoveryBreathing(canvas, center, scale, t);
        break;
      case WorkoutMovementVariant.generic:
        _drawHighKnees(canvas, center, scale, phase * 0.55);
        break;
    }
  }

  Offset _p(Offset center, double scale, double x, double y) =>
      Offset(center.dx + x * scale, center.dy + y * scale);

  Offset _mix(Offset from, Offset to, double t) =>
      Offset.lerp(from, to, Curves.easeInOut.transform(t))!;

  void _drawAthlete(
    Canvas canvas,
    _AthletePose pose,
    double scale, {
    List<List<Offset>> highlights = const [],
    bool showCore = false,
  }) {
    final backLimb = Paint()
      ..color = Colors.white.withValues(alpha: 0.58)
      ..strokeWidth = 6.0 * scale
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;
    final frontLimb = Paint()
      ..color = Colors.white.withValues(alpha: 0.96)
      ..strokeWidth = 6.5 * scale
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;

    void limb(Offset a, Offset b, Offset c, Paint paint) {
      final path = Path()
        ..moveTo(a.dx, a.dy)
        ..lineTo(b.dx, b.dy)
        ..lineTo(c.dx, c.dy);
      canvas.drawPath(path, paint);
    }

    // Chi phía sau được vẽ trước để tư thế nhìn có chiều sâu.
    limb(pose.rightShoulder, pose.rightElbow, pose.rightHand, backLimb);
    limb(pose.rightHip, pose.rightKnee, pose.rightAnkle, backLimb);

    final torso = Path()
      ..moveTo(pose.leftShoulder.dx, pose.leftShoulder.dy)
      ..lineTo(pose.rightShoulder.dx, pose.rightShoulder.dy)
      ..lineTo(pose.rightHip.dx, pose.rightHip.dy)
      ..lineTo(pose.leftHip.dx, pose.leftHip.dy)
      ..close();
    canvas.drawPath(
      torso,
      Paint()
        ..color = primaryColor.withValues(alpha: 0.34)
        ..style = PaintingStyle.fill,
    );
    canvas.drawPath(
      torso,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.9)
        ..strokeWidth = 2.2 * scale
        ..strokeJoin = StrokeJoin.round
        ..style = PaintingStyle.stroke,
    );

    for (final segment in highlights) {
      if (segment.length < 2) continue;
      final path = Path()..moveTo(segment.first.dx, segment.first.dy);
      for (final point in segment.skip(1)) {
        path.lineTo(point.dx, point.dy);
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = accentColor.withValues(alpha: 0.82)
          ..strokeWidth = 9.5 * scale
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round
          ..style = PaintingStyle.stroke,
      );
    }

    limb(pose.leftShoulder, pose.leftElbow, pose.leftHand, frontLimb);
    limb(pose.leftHip, pose.leftKnee, pose.leftAnkle, frontLimb);

    final jointPaint = Paint()
      ..color = accentColor
      ..style = PaintingStyle.fill;
    for (final joint in [
      pose.leftShoulder,
      pose.rightShoulder,
      pose.leftElbow,
      pose.rightElbow,
      pose.leftHip,
      pose.rightHip,
      pose.leftKnee,
      pose.rightKnee,
    ]) {
      canvas.drawCircle(joint, 2.8 * scale, jointPaint);
    }

    if (showCore) {
      final core = Offset(
        (pose.leftHip.dx +
                pose.rightHip.dx +
                pose.leftShoulder.dx +
                pose.rightShoulder.dx) /
            4,
        (pose.leftHip.dy +
                pose.rightHip.dy +
                pose.leftShoulder.dy +
                pose.rightShoulder.dy) /
            4,
      );
      canvas.drawCircle(
        core,
        9 * scale,
        Paint()
          ..color = accentColor.withValues(alpha: 0.24)
          ..style = PaintingStyle.fill,
      );
    }

    canvas.drawCircle(
      pose.head,
      9.5 * scale,
      Paint()..color = const Color(0xFFF8FAFC),
    );
    canvas.drawCircle(
      pose.head,
      9.5 * scale,
      Paint()
        ..color = primaryColor.withValues(alpha: 0.8)
        ..strokeWidth = 1.6 * scale
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawOverheadPress(
      Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final eased = Curves.easeInOut.transform(t);
    final leftElbow = _mix(p(-27, -15), p(-17, -49), eased);
    final rightElbow = _mix(p(27, -15), p(17, -49), eased);
    final leftHand = _mix(p(-21, -31), p(-12, -67), eased);
    final rightHand = _mix(p(21, -31), p(12, -67), eased);
    final pose = _AthletePose(
      head: p(0, -47),
      leftShoulder: p(-15, -32),
      rightShoulder: p(15, -32),
      leftElbow: leftElbow,
      rightElbow: rightElbow,
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(-10, 2),
      rightHip: p(10, 2),
      leftKnee: p(-15, 28),
      rightKnee: p(15, 28),
      leftAnkle: p(-18, 57),
      rightAnkle: p(18, 57),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftShoulder, pose.rightShoulder]
    ]);
    _drawDumbbell(canvas, leftHand, scale);
    _drawDumbbell(canvas, rightHand, scale);
  }

  void _drawBicepsCurl(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final curl = Curves.easeInOut.transform(t);
    final leftElbow = p(-18, -7);
    final rightElbow = p(18, -7);
    final leftHand = _mix(p(-19, 20), p(-25, -25), curl);
    final rightHand = _mix(p(19, 20), p(25, -25), curl);
    final pose = _AthletePose(
      head: p(0, -48),
      leftShoulder: p(-15, -32),
      rightShoulder: p(15, -32),
      leftElbow: leftElbow,
      rightElbow: rightElbow,
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(-10, 3),
      rightHip: p(10, 3),
      leftKnee: p(-12, 31),
      rightKnee: p(12, 31),
      leftAnkle: p(-14, 59),
      rightAnkle: p(14, 59),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftShoulder, pose.leftElbow],
      [pose.rightShoulder, pose.rightElbow],
    ]);
    _drawDumbbell(canvas, leftHand, scale);
    _drawDumbbell(canvas, rightHand, scale);
    _drawMotionArc(canvas, leftElbow, 28 * scale, math.pi / 2, math.pi, scale);
  }

  void _drawBenchPress(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final press = Curves.easeInOut.transform(t);
    final leftElbow = _mix(p(-31, 4), p(-26, -23), press);
    final rightElbow = _mix(p(-21, 7), p(-17, -20), press);
    final leftHand = _mix(p(-15, -5), p(-17, -48), press);
    final rightHand = _mix(p(-5, -2), p(-7, -45), press);

    final benchPaint = Paint()
      ..color = primaryColor.withValues(alpha: 0.75)
      ..strokeWidth = 5 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(p(-48, 23), p(25, 23), benchPaint);
    canvas.drawLine(p(-36, 23), p(-36, 55), benchPaint);
    canvas.drawLine(p(16, 23), p(16, 55), benchPaint);

    final pose = _AthletePose(
      head: p(-49, 11),
      leftShoulder: p(-34, 13),
      rightShoulder: p(-28, 17),
      leftElbow: leftElbow,
      rightElbow: rightElbow,
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(7, 14),
      rightHip: p(11, 18),
      leftKnee: p(30, 31),
      rightKnee: p(34, 35),
      leftAnkle: p(41, 58),
      rightAnkle: p(49, 58),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftShoulder, pose.leftElbow],
      [pose.rightShoulder, pose.rightElbow],
    ]);
    _drawDumbbell(canvas, leftHand, scale);
    _drawDumbbell(canvas, rightHand, scale);
  }

  void _drawPushUp(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final down = Curves.easeInOut.transform(t);
    final shoulderY = -12 + 19 * down;
    final hipY = -6 + 19 * down;
    final pose = _AthletePose(
      head: p(-51, shoulderY - 9),
      leftShoulder: p(-34, shoulderY - 2),
      rightShoulder: p(-30, shoulderY + 2),
      leftElbow: p(-45, 17),
      rightElbow: p(-22, 17),
      leftHand: p(-43, 39),
      rightHand: p(-23, 39),
      leftHip: p(8, hipY - 2),
      rightHip: p(12, hipY + 2),
      leftKnee: p(32, 5 + 8 * down),
      rightKnee: p(35, 8 + 8 * down),
      leftAnkle: p(55, 39),
      rightAnkle: p(58, 42),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftHip]
    ]);
  }

  void _drawSquat(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final d = Curves.easeInOut.transform(t);
    final shoulder = _mix(p(0, -33), p(10, -8), d);
    final hip = _mix(p(0, 1), p(-17, 18), d);
    final leftKnee = _mix(p(-8, 29), p(17, 31), d);
    final rightKnee = _mix(p(8, 29), p(25, 34), d);
    final pose = _AthletePose(
      head: shoulder + Offset(0, -17 * scale),
      leftShoulder: shoulder + Offset(-3 * scale, -2 * scale),
      rightShoulder: shoulder + Offset(3 * scale, 2 * scale),
      leftElbow: p(17, -20 + 18 * d),
      rightElbow: p(22, -15 + 18 * d),
      leftHand: p(37, -19 + 17 * d),
      rightHand: p(40, -13 + 17 * d),
      leftHip: hip + Offset(-3 * scale, -2 * scale),
      rightHip: hip + Offset(3 * scale, 2 * scale),
      leftKnee: leftKnee,
      rightKnee: rightKnee,
      leftAnkle: p(-9, 58),
      rightAnkle: p(11, 58),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);
  }

  void _drawLunge(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final depth = Curves.easeInOut.transform(t);
    final bodyDrop = 18 * depth;
    final pose = _AthletePose(
      head: p(0, -48 + bodyDrop),
      leftShoulder: p(-14, -32 + bodyDrop),
      rightShoulder: p(14, -32 + bodyDrop),
      leftElbow: p(-22, -12 + bodyDrop),
      rightElbow: p(22, -12 + bodyDrop),
      leftHand: p(-16, 7 + bodyDrop),
      rightHand: p(16, 7 + bodyDrop),
      leftHip: p(-9, 2 + bodyDrop),
      rightHip: p(9, 2 + bodyDrop),
      leftKnee: _mix(p(-14, 31), p(26, 34), depth),
      rightKnee: _mix(p(14, 31), p(-23, 38), depth),
      leftAnkle: _mix(p(-16, 59), p(47, 59), depth),
      rightAnkle: _mix(p(16, 59), p(-47, 59), depth),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);
  }

  void _drawBentRow(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final pull = Curves.easeInOut.transform(t);
    final leftElbow = _mix(p(-9, 11), p(21, -17), pull);
    final rightElbow = _mix(p(-3, 15), p(26, -11), pull);
    final leftHand = _mix(p(-4, 39), p(12, 2), pull);
    final rightHand = _mix(p(2, 42), p(18, 7), pull);
    final pose = _AthletePose(
      head: p(-40, -29),
      leftShoulder: p(-27, -20),
      rightShoulder: p(-23, -16),
      leftElbow: leftElbow,
      rightElbow: rightElbow,
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(10, 1),
      rightHip: p(14, 5),
      leftKnee: p(2, 31),
      rightKnee: p(18, 33),
      leftAnkle: p(-3, 58),
      rightAnkle: p(21, 58),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftShoulder, pose.leftHip]
    ]);
    _drawDumbbell(canvas, leftHand, scale);
    _drawDumbbell(canvas, rightHand, scale);
  }

  void _drawPlank(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final breath = math.sin(animationValue * math.pi * 2) * 1.5;
    final pose = _AthletePose(
      head: p(-55, -10 + breath),
      leftShoulder: p(-38, -3 + breath),
      rightShoulder: p(-35, 1 + breath),
      leftElbow: p(-42, 20),
      rightElbow: p(-31, 22),
      leftHand: p(-23, 21),
      rightHand: p(-12, 23),
      leftHip: p(5, 1 + breath),
      rightHip: p(9, 5 + breath),
      leftKnee: p(31, 7),
      rightKnee: p(34, 11),
      leftAnkle: p(57, 16),
      rightAnkle: p(60, 20),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftHip]
    ]);
    _drawPulse(canvas, p(-10, 1), scale, t);
  }

  void _drawCoreStability(
      Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final alternate = math.sin(phase);
    final pose = _AthletePose(
      head: p(-47, 25),
      leftShoulder: p(-31, 19),
      rightShoulder: p(-29, 23),
      leftElbow: p(-18, -2 - 7 * alternate),
      rightElbow: p(-11, 5 + 7 * alternate),
      leftHand: p(-5, -25 - 12 * alternate),
      rightHand: p(1, -18 + 12 * alternate),
      leftHip: p(8, 19),
      rightHip: p(11, 23),
      leftKnee: p(27, -2 + 15 * alternate),
      rightKnee: p(31, 4 - 15 * alternate),
      leftAnkle: p(52, -14 + 28 * alternate),
      rightAnkle: p(55, -9 - 28 * alternate),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftHip]
    ]);
  }

  void _drawStandingCoreHold(
      Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final pulse = math.sin(animationValue * math.pi * 2) * 1.2;
    final pose = _AthletePose(
      head: p(0, -48),
      leftShoulder: p(-15, -32 + pulse),
      rightShoulder: p(15, -32 + pulse),
      leftElbow: p(-23, -14),
      rightElbow: p(23, -14),
      leftHand: p(-7, -13),
      rightHand: p(7, -13),
      leftHip: p(-10, 3),
      rightHip: p(10, 3),
      leftKnee: p(-11, 31),
      rightKnee: p(11, 31),
      leftAnkle: p(-13, 59),
      rightAnkle: p(13, 59),
    );
    _drawAthlete(canvas, pose, scale, showCore: true);
    canvas.drawCircle(
      p(0, -13),
      8 * scale,
      Paint()..color = accentColor.withValues(alpha: 0.9),
    );
    _drawPulse(canvas, p(0, 0), scale, t);
  }

  void _drawLegExtension(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    _drawBench(canvas, p(-5, 15), scale);
    final extend = Curves.easeInOut.transform(t);
    final activeFoot = _mix(p(18, 56), p(57, 18), extend);
    final pose = _AthletePose(
      head: p(-18, -43),
      leftShoulder: p(-24, -28),
      rightShoulder: p(-18, -27),
      leftElbow: p(-31, -7),
      rightElbow: p(-10, -7),
      leftHand: p(-25, 11),
      rightHand: p(-4, 11),
      leftHip: p(-15, 10),
      rightHip: p(-8, 12),
      leftKnee: p(18, 14),
      rightKnee: p(14, 20),
      leftAnkle: activeFoot,
      rightAnkle: p(14, 56),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftHip, pose.leftKnee]
    ]);
    _drawMotionArc(
        canvas, p(18, 14), 33 * scale, -math.pi / 2.1, math.pi / 2.1, scale);
  }

  void _drawHipAdduction(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final close = Curves.easeInOut.transform(t);
    final kneeSpread = 31 - 17 * close;
    final ankleSpread = 38 - 20 * close;
    final pose = _AthletePose(
      head: p(0, -47),
      leftShoulder: p(-15, -32),
      rightShoulder: p(15, -32),
      leftElbow: p(-20, -12),
      rightElbow: p(20, -12),
      leftHand: p(-27, 7),
      rightHand: p(27, 7),
      leftHip: p(-10, 2),
      rightHip: p(10, 2),
      leftKnee: p(-kneeSpread, 25),
      rightKnee: p(kneeSpread, 25),
      leftAnkle: p(-ankleSpread, 54),
      rightAnkle: p(ankleSpread, 54),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);
    _drawInwardArrows(canvas, p(0, 24), kneeSpread * scale, scale);
  }

  void _drawBearWalk(Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final stride = math.sin(phase) * 12;
    final pose = _AthletePose(
      head: p(-49, -16),
      leftShoulder: p(-34, -8),
      rightShoulder: p(-31, -4),
      leftElbow: p(-39, 14),
      rightElbow: p(-25, 17),
      leftHand: p(-48 + stride, 36),
      rightHand: p(-17 - stride, 38),
      leftHip: p(9, -5),
      rightHip: p(13, -1),
      leftKnee: p(1, 21),
      rightKnee: p(24, 22),
      leftAnkle: p(-9 - stride, 38),
      rightAnkle: p(39 + stride, 39),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftHip]
    ]);
  }

  void _drawJumpingJack(Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final open = Curves.easeInOut.transform(t);
    final leftElbow = _mix(p(-21, -12), p(-34, -48), open);
    final rightElbow = _mix(p(21, -12), p(34, -48), open);
    final leftHand = _mix(p(-17, 8), p(-13, -66), open);
    final rightHand = _mix(p(17, 8), p(13, -66), open);
    final kneeSpread = 10 + 14 * open;
    final ankleSpread = 12 + 31 * open;
    final jump = math.sin(t * math.pi) * 3;
    final pose = _AthletePose(
      head: p(0, -47 - jump),
      leftShoulder: p(-15, -32 - jump),
      rightShoulder: p(15, -32 - jump),
      leftElbow: leftElbow - Offset(0, jump * scale),
      rightElbow: rightElbow - Offset(0, jump * scale),
      leftHand: leftHand - Offset(0, jump * scale),
      rightHand: rightHand - Offset(0, jump * scale),
      leftHip: p(-9, 2 - jump),
      rightHip: p(9, 2 - jump),
      leftKnee: p(-kneeSpread, 29 - jump),
      rightKnee: p(kneeSpread, 29 - jump),
      leftAnkle: p(-ankleSpread, 58 - jump),
      rightAnkle: p(ankleSpread, 58 - jump),
    );
    _drawAthlete(canvas, pose, scale);
  }

  void _drawJumpRope(Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final bounce = math.sin(phase).abs() * 5;
    final handSwing = math.sin(phase) * 3;
    final pose = _AthletePose(
      head: p(0, -48 - bounce),
      leftShoulder: p(-14, -32 - bounce),
      rightShoulder: p(14, -32 - bounce),
      leftElbow: p(-25, -13 - bounce),
      rightElbow: p(25, -13 - bounce),
      leftHand: p(-37, -1 - bounce + handSwing),
      rightHand: p(37, -1 - bounce + handSwing),
      leftHip: p(-8, 2 - bounce),
      rightHip: p(8, 2 - bounce),
      leftKnee: p(-9, 31 - bounce),
      rightKnee: p(9, 31 - bounce),
      leftAnkle: p(-10, 58 - bounce),
      rightAnkle: p(10, 58 - bounce),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);

    final rope = Path()
      ..moveTo(pose.leftHand.dx, pose.leftHand.dy)
      ..cubicTo(
        p(-63, 22).dx,
        p(-63, 22).dy,
        p(-42, 68).dx,
        p(-42, 68).dy,
        p(0, 65).dx,
        p(0, 65).dy,
      )
      ..cubicTo(
        p(42, 68).dx,
        p(42, 68).dy,
        p(63, 22).dx,
        p(63, 22).dy,
        pose.rightHand.dx,
        pose.rightHand.dy,
      );
    canvas.drawPath(
      rope,
      Paint()
        ..color = accentColor.withValues(alpha: 0.72)
        ..strokeWidth = 1.8 * scale
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawSwimming(Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final stroke = math.sin(phase);
    final kick = math.sin(phase * 2) * 8;
    final pose = _AthletePose(
      head: p(-49, -7),
      leftShoulder: p(-34, -2),
      rightShoulder: p(-31, 3),
      leftElbow: p(-18 + 15 * stroke, -28 - 8 * stroke),
      rightElbow: p(-17 - 15 * stroke, 25 + 8 * stroke),
      leftHand: p(8 + 31 * stroke, -39 - 9 * stroke),
      rightHand: p(7 - 31 * stroke, 38 + 9 * stroke),
      leftHip: p(7, 0),
      rightHip: p(10, 5),
      leftKnee: p(30, -2 + kick),
      rightKnee: p(33, 4 - kick),
      leftAnkle: p(58, -5 + kick),
      rightAnkle: p(60, 8 - kick),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftElbow],
    ]);

    final waterPaint = Paint()
      ..color = const Color(0xFF38BDF8).withValues(alpha: 0.4)
      ..strokeWidth = 1.5 * scale
      ..style = PaintingStyle.stroke;
    for (var i = 0; i < 3; i++) {
      canvas.drawArc(
        Rect.fromCenter(
          center: p(-10 + i * 25, 31 + i * 3),
          width: 28 * scale,
          height: 8 * scale,
        ),
        0,
        math.pi,
        false,
        waterPaint,
      );
    }
  }

  void _drawElliptical(
      Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final stride = math.sin(phase);
    final pose = _AthletePose(
      head: p(0, -48),
      leftShoulder: p(-14, -32),
      rightShoulder: p(14, -32),
      leftElbow: p(-20 + 10 * stride, -13),
      rightElbow: p(20 + 10 * stride, -13),
      leftHand: p(-13 + 18 * stride, 5),
      rightHand: p(13 + 18 * stride, 5),
      leftHip: p(-8, 2),
      rightHip: p(8, 2),
      leftKnee: p(-9 + 20 * stride, 30 - 8 * stride),
      rightKnee: p(9 - 20 * stride, 30 + 8 * stride),
      leftAnkle: p(-19 + 31 * stride, 57),
      rightAnkle: p(19 - 31 * stride, 57),
    );

    final machinePaint = Paint()
      ..color = primaryColor.withValues(alpha: 0.7)
      ..strokeWidth = 3 * scale
      ..style = PaintingStyle.stroke;
    canvas.drawOval(
      Rect.fromCenter(center: p(0, 58), width: 92 * scale, height: 14 * scale),
      machinePaint,
    );
    canvas.drawLine(p(-8, 55), p(-24, -28), machinePaint);
    canvas.drawLine(p(8, 55), p(24, -28), machinePaint);
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);
  }

  void _drawSuspensionCross(
      Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final close = Curves.easeInOut.transform(t);
    final leftHand = _mix(p(-45, -17), p(-7, -18), close);
    final rightHand = _mix(p(45, -17), p(7, -18), close);
    final pose = _AthletePose(
      head: p(8, -46),
      leftShoulder: p(-7, -31),
      rightShoulder: p(20, -27),
      leftElbow: _mix(p(-31, -28), p(-16, -23), close),
      rightElbow: _mix(p(40, -18), p(17, -18), close),
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(-1, 4),
      rightHip: p(17, 7),
      leftKnee: p(-8, 31),
      rightKnee: p(15, 34),
      leftAnkle: p(-19, 58),
      rightAnkle: p(7, 59),
    );
    final anchor = p(0, -72);
    final strapPaint = Paint()
      ..color = accentColor.withValues(alpha: 0.75)
      ..strokeWidth = 2 * scale
      ..style = PaintingStyle.stroke;
    canvas.drawLine(anchor, leftHand, strapPaint);
    canvas.drawLine(anchor, rightHand, strapPaint);
    canvas.drawCircle(anchor, 4 * scale, Paint()..color = accentColor);
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftShoulder, pose.leftElbow],
      [pose.rightShoulder, pose.rightElbow],
    ]);
  }

  void _drawHighKnees(
      Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final leftLift = (math.sin(phase) + 1) / 2;
    final rightLift = 1 - leftLift;
    final bounce = math.sin(phase * 2).abs() * 2.5;
    final pose = _AthletePose(
      head: p(0, -48 - bounce),
      leftShoulder: p(-14, -32 - bounce),
      rightShoulder: p(14, -32 - bounce),
      leftElbow: p(-22 + 20 * leftLift, -13 - 8 * leftLift),
      rightElbow: p(22 - 20 * rightLift, -13 - 8 * rightLift),
      leftHand: p(-16 + 20 * leftLift, 7 - 24 * leftLift),
      rightHand: p(16 - 20 * rightLift, 7 - 24 * rightLift),
      leftHip: p(-8, 1 - bounce),
      rightHip: p(8, 1 - bounce),
      leftKnee: p(-8, 31 - 40 * leftLift),
      rightKnee: p(8, 31 - 40 * rightLift),
      leftAnkle: p(-10, 58 - 24 * leftLift),
      rightAnkle: p(10, 58 - 24 * rightLift),
    );
    _drawAthlete(canvas, pose, scale, highlights: [
      [pose.leftHip, pose.leftKnee],
      [pose.rightHip, pose.rightKnee],
    ]);
  }

  void _drawJointRotation(
      Canvas canvas, Offset center, double scale, double phase) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final leftShoulder = p(-15, -31);
    final rightShoulder = p(15, -31);
    final leftElbow = leftShoulder +
        Offset(math.cos(phase) * 17 * scale, math.sin(phase) * 17 * scale);
    final rightElbow = rightShoulder +
        Offset(math.cos(phase + math.pi) * 17 * scale,
            math.sin(phase + math.pi) * 17 * scale);
    final leftHand = leftShoulder +
        Offset(math.cos(phase) * 34 * scale, math.sin(phase) * 34 * scale);
    final rightHand = rightShoulder +
        Offset(math.cos(phase + math.pi) * 34 * scale,
            math.sin(phase + math.pi) * 34 * scale);
    final hipSway = math.sin(phase) * 3;
    final pose = _AthletePose(
      head: p(0, -48),
      leftShoulder: leftShoulder,
      rightShoulder: rightShoulder,
      leftElbow: leftElbow,
      rightElbow: rightElbow,
      leftHand: leftHand,
      rightHand: rightHand,
      leftHip: p(-10 + hipSway, 3),
      rightHip: p(10 + hipSway, 3),
      leftKnee: p(-14, 31),
      rightKnee: p(14, 31),
      leftAnkle: p(-18, 58),
      rightAnkle: p(18, 58),
    );
    _drawAthlete(canvas, pose, scale);
    _drawJointCircle(canvas, leftShoulder, 20 * scale, phase, scale);
    _drawJointCircle(canvas, rightShoulder, 20 * scale, phase + math.pi, scale);
    _drawJointCircle(canvas, p(0, 3), 14 * scale, -phase, scale);
  }

  void _drawStaticStretch(
      Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final lean = Curves.easeInOut.transform(t) * 12;
    final pose = _AthletePose(
      head: p(lean, -48),
      leftShoulder: p(-15 + lean * 0.8, -32),
      rightShoulder: p(15 + lean * 0.8, -32),
      leftElbow: p(-25 + lean * 0.3, -48),
      rightElbow: p(25 + lean, -49),
      leftHand: p(-12 + lean, -66),
      rightHand: p(39 + lean, -31),
      leftHip: p(-10, 2),
      rightHip: p(10, 2),
      leftKnee: p(-28, 31),
      rightKnee: p(26, 31),
      leftAnkle: p(-48, 57),
      rightAnkle: p(48, 57),
    );
    _drawAthlete(canvas, pose, scale, showCore: true, highlights: [
      [pose.leftHip, pose.leftShoulder]
    ]);
  }

  void _drawRecoveryBreathing(
      Canvas canvas, Offset center, double scale, double t) {
    Offset p(double x, double y) => _p(center, scale, x, y);
    final shoulderRise = t * 2.5;
    final pose = _AthletePose(
      head: p(0, -38 - shoulderRise),
      leftShoulder: p(-14, -23 - shoulderRise),
      rightShoulder: p(14, -23 - shoulderRise),
      leftElbow: p(-24, -2),
      rightElbow: p(24, -2),
      leftHand: p(-32, 15),
      rightHand: p(32, 15),
      leftHip: p(-9, 9),
      rightHip: p(9, 9),
      leftKnee: p(-32, 28),
      rightKnee: p(32, 28),
      leftAnkle: p(18, 36),
      rightAnkle: p(-18, 36),
    );
    _drawAthlete(canvas, pose, scale, showCore: true);
    final radius = (18 + 18 * t) * scale;
    canvas.drawCircle(
      p(0, -4),
      radius,
      Paint()
        ..color = const Color(0xFF80DEEA).withValues(alpha: 0.38 * (1 - t))
        ..strokeWidth = 2 * scale
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawGroundShadow(Canvas canvas, Offset center, double scale) {
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(center.dx, center.dy + 61 * scale),
        width: 112 * scale,
        height: 8 * scale,
      ),
      Paint()..color = Colors.black.withValues(alpha: 0.24),
    );
  }

  void _drawDumbbell(Canvas canvas, Offset pos, double scale) {
    final paint = Paint()
      ..color = accentColor
      ..strokeWidth = 3 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
      pos - Offset(7 * scale, 0),
      pos + Offset(7 * scale, 0),
      paint,
    );
    canvas.drawCircle(
        pos - Offset(8 * scale, 0), 4 * scale, Paint()..color = accentColor);
    canvas.drawCircle(
        pos + Offset(8 * scale, 0), 4 * scale, Paint()..color = accentColor);
  }

  void _drawBench(Canvas canvas, Offset seat, double scale) {
    final paint = Paint()
      ..color = primaryColor.withValues(alpha: 0.65)
      ..strokeWidth = 4 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
        seat - Offset(22 * scale, 0), seat + Offset(22 * scale, 0), paint);
    canvas.drawLine(seat - Offset(15 * scale, 0),
        seat - Offset(15 * scale, 35 * scale), paint);
  }

  void _drawPulse(Canvas canvas, Offset position, double scale, double t) {
    canvas.drawCircle(
      position,
      (10 + 9 * t) * scale,
      Paint()
        ..color = accentColor.withValues(alpha: 0.42 * (1 - t))
        ..strokeWidth = 2 * scale
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawMotionArc(Canvas canvas, Offset center, double radius, double start,
      double sweep, double scale) {
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      start,
      sweep,
      false,
      Paint()
        ..color = accentColor.withValues(alpha: 0.55)
        ..strokeWidth = 1.8 * scale
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawJointCircle(
      Canvas canvas, Offset center, double radius, double phase, double scale) {
    final paint = Paint()
      ..color = accentColor.withValues(alpha: 0.5)
      ..strokeWidth = 1.6 * scale
      ..style = PaintingStyle.stroke;
    canvas.drawCircle(center, radius, paint);
    canvas.drawCircle(
      center + Offset(math.cos(phase) * radius, math.sin(phase) * radius),
      3.2 * scale,
      Paint()..color = accentColor,
    );
  }

  void _drawInwardArrows(
      Canvas canvas, Offset center, double spread, double scale) {
    final paint = Paint()
      ..color = accentColor.withValues(alpha: 0.75)
      ..strokeWidth = 2 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
        center - Offset(spread, 0), center - Offset(8 * scale, 0), paint);
    canvas.drawLine(
        center + Offset(spread, 0), center + Offset(8 * scale, 0), paint);
  }

  @override
  bool shouldRepaint(covariant _MovementSimulationPainter oldDelegate) {
    return oldDelegate.animationValue != animationValue ||
        oldDelegate.animationType != animationType ||
        oldDelegate.exerciseName != exerciseName ||
        oldDelegate.primaryColor != primaryColor ||
        oldDelegate.accentColor != accentColor ||
        oldDelegate.isRest != isRest;
  }
}
