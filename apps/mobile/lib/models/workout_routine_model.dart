/// Model và Parser cho kế hoạch luyện tập, giai đoạn và từng bài tập con
library;

import 'wger_models.dart';
import '../utils/exercise_utils.dart';

/// Kiểu hoạt ảnh mô phỏng động tác
enum WorkoutAnimationType {
  press, // Đẩy ngực / vai (Shoulder press, Bench press)
  squat, // Ngồi xổm / Chân (Squat, Leg press, Lunge)
  pull, // Kéo lưng / xô (Bent row, Lat pull, High pull)
  coreHold, // Giữ bụng / Plank (Plank, Axe hold, Abdominal stabilization)
  legExtension, // Mở chân / Đùi (Leg extension, Hip adduction)
  dynamicMovement, // Chuyển động động (Bear walk, Jumping jacks, Burpees)
  stretch, // Giãn cơ (Stretching, Yoga)
  cardio, // Chạy bộ / Nhảy dây (Running, Skipping)
  generic, // Mặc định
}

/// Chi tiết của một bài tập con trong chuỗi bài tập
class WorkoutExerciseStep {
  final String id;
  final String name;
  final String vietnameseName;
  final int sets;
  final String reps;
  final int?
      durationSeconds; // thời gian nếu là bài tính theo giây (ví dụ: Plank 45s)
  final int restSeconds; // thời gian nghỉ khuyến nghị giữa các hiệp
  final List<String> targetMuscles; // nhóm cơ tác động chính & phụ
  final String category; // Sức mạnh, Cardio, Core, Linh hoạt
  final String equipment; // Tạ đơn, Thảm, Ghế, Bodyweight...
  final String instructions; // Hướng dẫn thực hiện từng bước
  final String tips; // Lưu ý kỹ thuật & phòng tránh chấn thương
  final String
      breathingCue; // Nhịp hít thở chuẩn (Hít khi hạ, thở khi phát lực)
  final WorkoutAnimationType animationType;
  bool isCompleted;
  int completedSets;

  WorkoutExerciseStep({
    required this.id,
    required this.name,
    this.vietnameseName = '',
    this.sets = 3,
    this.reps = '10-12 lần',
    this.durationSeconds,
    this.restSeconds = 45,
    this.targetMuscles = const [],
    this.category = 'Sức mạnh',
    this.equipment = 'Không cần dụng cụ',
    this.instructions = '',
    this.tips = '',
    this.breathingCue = '',
    this.animationType = WorkoutAnimationType.generic,
    this.isCompleted = false,
    this.completedSets = 0,
  });

  String get displayName =>
      vietnameseName.isNotEmpty ? '$name ($vietnameseName)' : name;

  String get targetMusclesText =>
      targetMuscles.isNotEmpty ? targetMuscles.join(', ') : 'Toàn thân';

  WorkoutExerciseStep copyWith({
    String? id,
    String? name,
    String? vietnameseName,
    int? sets,
    String? reps,
    int? durationSeconds,
    int? restSeconds,
    List<String>? targetMuscles,
    String? category,
    String? equipment,
    String? instructions,
    String? tips,
    String? breathingCue,
    WorkoutAnimationType? animationType,
    bool? isCompleted,
    int? completedSets,
  }) {
    return WorkoutExerciseStep(
      id: id ?? this.id,
      name: name ?? this.name,
      vietnameseName: vietnameseName ?? this.vietnameseName,
      sets: sets ?? this.sets,
      reps: reps ?? this.reps,
      durationSeconds: durationSeconds ?? this.durationSeconds,
      restSeconds: restSeconds ?? this.restSeconds,
      targetMuscles: targetMuscles ?? this.targetMuscles,
      category: category ?? this.category,
      equipment: equipment ?? this.equipment,
      instructions: instructions ?? this.instructions,
      tips: tips ?? this.tips,
      breathingCue: breathingCue ?? this.breathingCue,
      animationType: animationType ?? this.animationType,
      isCompleted: isCompleted ?? this.isCompleted,
      completedSets: completedSets ?? this.completedSets,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'vietnamese_name': vietnameseName,
      'sets': sets,
      'reps': reps,
      'duration_seconds': durationSeconds,
      'rest_seconds': restSeconds,
      'target_muscles': targetMuscles,
      'category': category,
      'equipment': equipment,
      'instructions': instructions,
      'tips': tips,
      'breathing_cue': breathingCue,
      'animation_type': animationType.name,
      'is_completed': isCompleted,
      'completed_sets': completedSets,
    };
  }

  factory WorkoutExerciseStep.fromJson(Map<String, dynamic> json) {
    WorkoutAnimationType anim = WorkoutAnimationType.generic;
    final animName = json['animation_type']?.toString();
    if (animName != null) {
      anim = WorkoutAnimationType.values.firstWhere(
        (e) => e.name == animName,
        orElse: () => WorkoutAnimationType.generic,
      );
    }

    return WorkoutExerciseStep(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      vietnameseName: json['vietnamese_name']?.toString() ?? '',
      sets: (json['sets'] as num?)?.toInt() ?? 3,
      reps: json['reps']?.toString() ?? '10-12 lần',
      durationSeconds: (json['duration_seconds'] as num?)?.toInt(),
      restSeconds: (json['rest_seconds'] as num?)?.toInt() ?? 45,
      targetMuscles: (json['target_muscles'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      category: json['category']?.toString() ?? 'Sức mạnh',
      equipment: json['equipment']?.toString() ?? 'Không cần dụng cụ',
      instructions: json['instructions']?.toString() ?? '',
      tips: json['tips']?.toString() ?? '',
      breathingCue: json['breathing_cue']?.toString() ?? '',
      animationType: anim,
      isCompleted: json['is_completed'] == true,
      completedSets: (json['completed_sets'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Giai đoạn tập luyện trong buổi tập
class WorkoutPhase {
  final String id;
  final String title;
  final String phaseType; // 'warmup' | 'main' | 'cooldown'
  final String description;
  final int durationMinutes;
  final List<WorkoutExerciseStep> exercises;

  WorkoutPhase({
    required this.id,
    required this.title,
    required this.phaseType,
    required this.description,
    required this.durationMinutes,
    required this.exercises,
  });

  bool get isCompleted =>
      exercises.isNotEmpty && exercises.every((e) => e.isCompleted);

  int get completedCount => exercises.where((e) => e.isCompleted).length;

  double get progressPercentage => exercises.isEmpty
      ? 1.0
      : (completedCount / exercises.length).clamp(0.0, 1.0);
}

/// Kế hoạch buổi tập hoàn chỉnh
class WorkoutRoutinePlan {
  final String id;
  final String title;
  final String level; // Beginner, Intermediate, Advanced
  final int totalDurationMinutes;
  final double totalCalories;
  final String summary;
  final List<WorkoutPhase> phases;

  WorkoutRoutinePlan({
    required this.id,
    required this.title,
    required this.level,
    required this.totalDurationMinutes,
    required this.totalCalories,
    required this.summary,
    required this.phases,
  });

  /// Danh sách tất cả bài tập qua tất cả các giai đoạn
  List<WorkoutExerciseStep> get allExercises =>
      phases.expand((p) => p.exercises).toList();

  /// Tổng số bài tập
  int get totalExercisesCount => allExercises.length;

  /// Số bài tập đã hoàn thành
  int get completedExercisesCount =>
      allExercises.where((e) => e.isCompleted).length;

  /// Tiến độ tổng thể từ 0.0 -> 1.0
  double get overallProgress => totalExercisesCount == 0
      ? 1.0
      : (completedExercisesCount / totalExercisesCount).clamp(0.0, 1.0);

  /// Kiểm tra toàn bộ buổi tập đã hoàn thành chưa
  bool get isFullyCompleted =>
      totalExercisesCount > 0 && completedExercisesCount == totalExercisesCount;

  /// Giai đoạn khởi động
  WorkoutPhase? get warmupPhase => phases
      .cast<WorkoutPhase?>()
      .firstWhere((p) => p?.phaseType == 'warmup', orElse: () => null);

  /// Giai đoạn bài tập chính
  WorkoutPhase? get mainPhase => phases
      .cast<WorkoutPhase?>()
      .firstWhere((p) => p?.phaseType == 'main', orElse: () => null);

  /// Giai đoạn giãn cơ
  WorkoutPhase? get cooldownPhase => phases
      .cast<WorkoutPhase?>()
      .firstWhere((p) => p?.phaseType == 'cooldown', orElse: () => null);
}

/// Bộ parser thông minh và từ điển bài tập phong phú
class WorkoutRoutineParser {
  /// Từ điển dữ liệu chuẩn về kỹ thuật, cơ bắp, hướng dẫn các bài tập phổ biến
  static final Map<String, Map<String, dynamic>> _exerciseKnowledgeBase = {
    'seated hip adduction': {
      'vietnamese': 'Khép đùi trong trên máy/ngồi',
      'muscles': ['Cơ đùi trong (Adductors)', 'Cơ đáy chậu'],
      'category': 'Sức mạnh / Thân dưới',
      'equipment': 'Máy ép đùi hoặc Ghế & Bóng',
      'instructions':
          '1. Ngồi thẳng lưng, đặt hai đùi tựa sát vào đệm máy.\n2. Siết cơ bụng, dùng lực cơ đùi trong ép từ từ hai chân lại gần nhau.\n3. Giữ lại 1 giây ở điểm ép tối đa, sau đó mở chân trở lại vị trí ban đầu có kiểm soát.',
      'tips': 'Không dùng đà, giữ lưng thẳng áp sát tựa ghế suốt chuyển động.',
      'breathing': 'Thở ra khi khép đùi vào trong, Hít sâu khi mở chân ra.',
      'animation': WorkoutAnimationType.legExtension,
    },
    'arnold shoulder press': {
      'vietnamese': 'Đẩy tạ đôi xoay vai Arnold',
      'muscles': ['Cơ vai trước & giữa (Deltoids)', 'Tay sau (Triceps)'],
      'category': 'Sức mạnh / Thân trên',
      'equipment': 'Cặp tạ đơn (Dumbbells)',
      'instructions':
          '1. Ngồi thẳng lưng trên ghế, cầm 2 tạ đơn trước ngực, lòng bàn tay hướng vào thân người.\n2. Đẩy tạ lên cao qua đầu đồng thời xoay cổ tay 180 độ sao cho khi lên đỉnh lòng bàn tay hướng về phía trước.\n3. Hạ tạ từ từ và xoay ngược lại về vị trí xuất phát trước ngực.',
      'tips':
          'Không khóa khớp khuỷu tay ở đỉnh, giữ vai hạ thấp, không rụt cổ.',
      'breathing': 'Thở ra khi đẩy tạ lên cao, Hít vào khi hạ tạ có kiểm soát.',
      'animation': WorkoutAnimationType.press,
    },
    'axe hold': {
      'vietnamese': 'Giữ tạ tư thế búa / Rìu bổ',
      'muscles': [
        'Cơ vai (Shoulders)',
        'Cơ bụng & Trọng tâm (Core)',
        'Cẳng tay'
      ],
      'category': 'Sức bền & Core',
      'equipment': 'Tạ đơn hoặc Đĩa tạ',
      'instructions':
          '1. Đứng thẳng, 2 chân rộng bằng vai, hai tay cầm chắc tạ đưa thẳng ra phía trước ngực.\n2. Giữ cánh tay song song với sàn nhà, gồng chặt cơ bụng và cơ vai.\n3. Duy trì tư thế cố định không lắc lư trong thời gian quy định.',
      'tips': 'Gồng chặt cơ mông và cơ bụng, tránh ngả lưng về sau.',
      'breathing': 'Hít thở đều đặn, nhịp nhàng theo từng nhịp tim.',
      'animation': WorkoutAnimationType.coreHold,
    },
    'abdominal stabilization': {
      'vietnamese': 'Ổn định & Siết cơ bụng',
      'muscles': ['Cơ bụng sâu (Transverse Abdominis)', 'Cơ liên sườn'],
      'category': 'Core / Bụng',
      'equipment': 'Thảm tập',
      'instructions':
          '1. Nằm ngửa trên thảm, co 2 đầu gối 90 độ, lưng dưới dán chặt xuống sàn.\n2. Hóp chặt rốn về phía cột sống, nâng nhẹ đầu vai và giữ tư thế ổn định.\n3. Thực hiện cử động chân nhẹ nhàng luân phiên hoặc giữ cố định.',
      'tips':
          'Tuyệt đối không để hõm lưng dưới hở khỏi sàn để bảo vệ cột sống.',
      'breathing':
          'Hít thở ngắn bằng ngực, giữ bụng luôn ở trạng thái gồng cứng.',
      'animation': WorkoutAnimationType.coreHold,
    },
    'bear walk': {
      'vietnamese': 'Bò gấu linh hoạt',
      'muscles': ['Cơ bụng (Core)', 'Cơ vai', 'Đùi trước (Quads)'],
      'category': 'Vận động toàn thân',
      'equipment': 'Thảm tập / Không gian rộng',
      'instructions':
          '1. Bắt đầu ở tư thế chống 4 điểm (tay và mũi chân), đầu gối cách mặt sàn 5cm.\n2. Lưng giữ thẳng song song với sàn, bước chân trái và tay phải tiến lên trước một nhịp.\n3. Luân phiên bước nhịp nhàng, duy trì hông thấp và cơ bụng gồng chặt.',
      'tips':
          'Không đẩy mông lên quá cao, bước từng bước ngắn và giữ thân người cân bằng.',
      'breathing':
          'Duy trì nhịp thở tự nhiên, thở đều theo từng bước di chuyển.',
      'animation': WorkoutAnimationType.dynamicMovement,
    },
    'bear walk 2': {
      'vietnamese': 'Bò gấu tiến lùi nâng cao',
      'muscles': ['Toàn bộ Core', 'Cơ vai', 'Đùi trước & Khớp hông'],
      'category': 'Toàn thân & Tim mạch',
      'equipment': 'Thảm tập',
      'instructions':
          '1. Vào tư thế bò gấu với đầu gối nâng nhẹ cách sàn 5cm, lưng thẳng.\n2. Di chuyển tiến lên 4 bước, sau đó lùi lại 4 bước có kiểm soát.\n3. Giữ gối luôn gần sàn và thân người không lắc lư sang hai bên.',
      'tips': 'Tập trung giữ trục cột sống ổn định từ đỉnh đầu đến xương cụt.',
      'breathing': 'Hít thở nhịp nhàng, không nín thở trong lúc bò.',
      'animation': WorkoutAnimationType.dynamicMovement,
    },
    'single leg extension': {
      'vietnamese': 'Đá đùi từng chân',
      'muscles': ['Cơ đùi trước (Quadriceps)', 'Khớp gối'],
      'category': 'Sức mạnh / Đùi',
      'equipment': 'Máy đá đùi hoặc Ghế ngồi & Dây kháng lực',
      'instructions':
          '1. Ngồi thẳng trên ghế, đặt cẳng chân phía sau đệm tựa chân.\n2. Gồng cơ đùi trước, duỗi thẳng 1 chân lên cao cho đến khi chân gần thẳng hàng.\n3. Giữ lại 1 giây ở đỉnh để co thắt cơ đùi tối đa, sau đó hạ từ từ về vị trí cũ.',
      'tips':
          'Không vung giật chân, hạ chân chậm 2-3 giây để tăng hiệu quả kích thích cơ.',
      'breathing': 'Thở ra khi duỗi đá chân lên, Hít sâu khi hạ chân xuống.',
      'animation': WorkoutAnimationType.legExtension,
    },
    'bent high pulls': {
      'vietnamese': 'Kéo tạ cao cúi người',
      'muscles': [
        'Cơ lưng trên (Upper Back)',
        'Cơ vai sau (Rear Delts)',
        'Cầu vai'
      ],
      'category': 'Sức mạnh / Lưng & Vai',
      'equipment': 'Cặp tạ đơn hoặc Dây kháng lực',
      'instructions':
          '1. Cúi gập người về phía trước góc 45 độ, lưng thẳng, gối hơi chùng.\n2. Cầm tạ buông thõng, kéo cùi chỏ hướng lên cao và sang hai bên sao cho tạ lên ngang ngực trên.\n3. Ép chặt hai xương bả vai ở đỉnh, sau đó hạ tạ từ từ có kiểm soát.',
      'tips': 'Giữ cổ thẳng với cột sống, không giật lưng dưới khi kéo tạ.',
      'breathing': 'Thở ra khi kéo tạ lên, Hít vào khi hạ tạ xuống.',
      'animation': WorkoutAnimationType.pull,
    },
    'push up': {
      'vietnamese': 'Chống đẩy / Hít đất',
      'muscles': ['Cơ ngực (Chest)', 'Tay sau (Triceps)', 'Cơ vai trước'],
      'category': 'Sức mạnh / Thân trên',
      'equipment': 'Thảm tập / Không cần dụng cụ',
      'instructions':
          '1. Chống hai tay rộng hơn vai một chút, thân người tạo thành một đường thẳng từ đầu đến gót chân.\n2. Hạ ngực xuống cách sàn khoảng 2-3cm, khuỷu tay tạo góc 45 độ với thân người.\n3. Dùng lực ngực và tay sau đẩy mạnh thân người trở lại vị trí ban đầu.',
      'tips': 'Gồng chặt mông và bụng, không để võng lưng hoặc nhô mông.',
      'breathing': 'Hít vào khi hạ người xuống, Thở ra dứt khoát khi đẩy lên.',
      'animation': WorkoutAnimationType.press,
    },
    'squat': {
      'vietnamese': 'Ngồi xổm / Gánh đùi',
      'muscles': [
        'Cơ đùi trước (Quads)',
        'Cơ mông (Glutes)',
        'Đùi sau (Hamstrings)'
      ],
      'category': 'Sức mạnh / Thân dưới',
      'equipment': 'Bodyweight / Tạ đơn',
      'instructions':
          '1. Đứng thẳng, 2 chân rộng bằng vai, mũi chân hơi chếch ra ngoài 15-30 độ.\n2. Đẩy hông ra sau và gập gối hạ thấp trọng tâm như đang ngồi vào ghế.\n3. Hạ đến khi đùi song song với sàn, sau đó đạp mạnh gót chân đẩy người đứng thẳng dậy.',
      'tips':
          'Giữ ngực mở, lưng thẳng, đầu gối hướng theo hướng mũi chân suốt chuyển động.',
      'breathing': 'Hít sâu khi hạ người xuống, Thở mạnh khi đạp đứng lên.',
      'animation': WorkoutAnimationType.squat,
    },
    'plank': {
      'vietnamese': 'Tư thế đo ván giữ tĩnh',
      'muscles': ['Cơ bụng (Core)', 'Cơ vai', 'Cơ mông'],
      'category': 'Core / Sức bền',
      'equipment': 'Thảm tập',
      'instructions':
          '1. Chống cẳng tay vuông góc với sàn nhà, mũi chân chống đất.\n2. Nâng toàn bộ thân người tạo thành một đường thẳng tắp từ đầu, lưng đến gót chân.\n3. Siết chặt cơ bụng, cơ mông và giữ nguyên tư thế trong thời gian quy định.',
      'tips':
          'Không ngước đầu nhìn lên hoặc cúi đầu quá sâu, giữ cổ trung lập.',
      'breathing': 'Hít thở đều đặn và sâu bằng cơ hoành, không nín thở.',
      'animation': WorkoutAnimationType.coreHold,
    },
    'jumping jacks': {
      'vietnamese': 'Bật nhảy vung tay chân',
      'muscles': ['Tim mạch (Cardio)', 'Bắp chân', 'Cơ vai'],
      'category': 'Cardio / Khởi động',
      'equipment': 'Không cần dụng cụ',
      'instructions':
          '1. Đứng thẳng, 2 chân khép, 2 tay áp sát vào hông.\n2. Bật nhảy mở rộng 2 chân sang hai bên đồng thời vung 2 tay lên cao qua đầu.\n3. Bật nhảy tiếp nhịp 2 khép chân và hạ tay về vị trí ban đầu.',
      'tips':
          'Tiếp đất nhẹ nhàng bằng mũi bàn chân để giảm áp lực lên khớp gối.',
      'breathing': 'Thở đều theo nhịp bật nhảy.',
      'animation': WorkoutAnimationType.dynamicMovement,
    },
    'high knees': {
      'vietnamese': 'Chạy nâng cao đùi tại chỗ',
      'muscles': ['Cơ đùi', 'Khớp hông (Hip flexors)', 'Cardio'],
      'category': 'Cardio / Khởi động',
      'equipment': 'Không cần dụng cụ',
      'instructions':
          '1. Đứng thẳng, luân phiên nâng cao đùi sao cho đùi vuông góc với thân người.\n2. Đánh tay nhịp nhàng đối diện với chân nâng lên.\n3. Duy trì nhịp độ nhanh và liên tục.',
      'tips': 'Giữ thân người thẳng, tiếp đất bằng nửa bàn chân trước.',
      'breathing': 'Hít thở nhịp nhàng theo nhịp chạy.',
      'animation': WorkoutAnimationType.cardio,
    },
  };

  /// Phân tích ActionItem hoặc Map dữ liệu thành WorkoutRoutinePlan hoàn chỉnh
  static WorkoutRoutinePlan parseFromAction(ActionItem action) {
    final name = action.name;
    final details = action.details;
    final rawDesc = details['description']?.toString() ?? '';
    final rawDurationValue = details['duration'] ?? details['duration_min'];
    final rawDuration = rawDurationValue is num
        ? rawDurationValue.toInt()
        : int.tryParse(rawDurationValue?.toString() ?? '') ?? 30;
    final duration = rawDuration.clamp(3, 120);
    final rawCalories = details['calories_burned'];
    final parsedCalories = rawCalories is num
        ? rawCalories.toDouble()
        : double.tryParse(rawCalories?.toString() ?? '');
    final category =
        details['category']?.toString() ?? details['type']?.toString() ?? '';
    final calories =
        parsedCalories != null && parsedCalories.isFinite && parsedCalories > 0
            ? parsedCalories
            : ExerciseUtils.calculateCalories(
                met: ExerciseUtils.estimateMet(name, category, 0),
                weightKg: 70,
                durationMinutes: duration,
              );
    final warmupMinutes =
        duration <= 10 ? 1 : (duration * 0.1).round().clamp(2, 4);
    final cooldownMinutes =
        duration <= 10 ? 1 : (duration * 0.1).round().clamp(2, 4);
    final mainMinutes =
        (duration - warmupMinutes - cooldownMinutes).clamp(1, 112);

    // Trích xuất cấp độ (Beginner / Intermediate / Advanced)
    String level = 'Trung bình (Intermediate)';
    final nameLower = name.toLowerCase();
    if (nameLower.contains('beginner') ||
        nameLower.contains('cơ bản') ||
        nameLower.contains('mới bắt đầu')) {
      level = 'Cơ bản (Beginner)';
    } else if (nameLower.contains('advanced') ||
        nameLower.contains('nâng cao')) {
      level = 'Nâng cao (Advanced)';
    } else if (nameLower.contains('intermediate') ||
        nameLower.contains('trung bình')) {
      level = 'Trung bình (Intermediate)';
    }

    // 1. Phân tích các bài tập chính từ mô tả
    List<WorkoutExerciseStep> mainSteps = _parseStepsFromDescription(rawDesc);

    // Nếu không parse được từ description, tạo ít nhất 1 step dựa trên action name
    if (mainSteps.isEmpty) {
      mainSteps = [
        _createDefaultStep(
          id: 'step_1',
          rawName: name,
          sets: 3,
          reps: '10-12 lần',
          durationSeconds: _isTimedMovement(name) ? mainMinutes * 60 : null,
        )
      ];
    }

    // 2. Tạo giai đoạn khởi động (Warm-up Phase)
    final warmupSteps = [
      WorkoutExerciseStep(
        id: 'warmup_1',
        name: 'Joint Rotations & Dynamic Stretch',
        vietnameseName: 'Xoay khớp cổ tay, vai & hông',
        sets: 1,
        reps: '60 giây',
        durationSeconds: 60,
        restSeconds: 15,
        targetMuscles: ['Toàn thân', 'Khớp vai', 'Khớp hông'],
        category: 'Khởi động',
        equipment: 'Không cần dụng cụ',
        instructions:
            'Xoay tròn các khớp cổ tay, khuỷu tay, bả vai, hông và đầu gối từ từ theo chiều kim đồng hồ rồi đổi chiều.',
        tips:
            'Thực hiện biên độ vừa phải để kích hoạt chất nhờn bôi trơn ổ khớp.',
        breathingCue: 'Hít sâu thở chậm đều đặn.',
        animationType: WorkoutAnimationType.stretch,
      ),
      WorkoutExerciseStep(
        id: 'warmup_2',
        name: 'Jumping Jacks / Arm Circles',
        vietnameseName: 'Bật nhảy & vung tay làm nóng',
        sets: 2,
        reps: '30 giây',
        durationSeconds: 30,
        restSeconds: 20,
        targetMuscles: ['Tim mạch', 'Bắp chân', 'Vai'],
        category: 'Khởi động',
        equipment: 'Không cần dụng cụ',
        instructions:
            'Bật nhảy mở chân kết hợp vung tay đều đặn để tăng dần nhịp tim và làm ấm toàn bộ cơ thể.',
        tips: 'Tiếp đất êm ái bằng mũi chân, không tiếp đất bằng gót.',
        breathingCue: 'Hít thở đều theo nhịp nhảy.',
        animationType: WorkoutAnimationType.dynamicMovement,
      ),
    ];

    // 3. Tạo giai đoạn giãn cơ & hạ nhiệt (Cool-down Phase)
    final cooldownSteps = [
      WorkoutExerciseStep(
        id: 'cooldown_1',
        name: 'Static Muscle Stretch',
        vietnameseName: 'Giãn cơ tĩnh toàn thân',
        sets: 1,
        reps: '60 giây',
        durationSeconds: 60,
        restSeconds: 15,
        targetMuscles: ['Cơ đùi', 'Cơ ngực', 'Cơ lưng'],
        category: 'Hạ nhiệt',
        equipment: 'Thảm tập',
        instructions:
            'Đứng duỗi cơ đùi trước, gập người kéo giãn cơ đùi sau và mở ngực kéo giãn bả vai, giữ mỗi tư thế 15-20 giây.',
        tips: 'Giữ tư thế ở điểm căng nhẹ, không nhấp nhả đột ngột.',
        breathingCue:
            'Thở ra chậm rãi để đưa nhịp tim dần trở về mức bình thường.',
        animationType: WorkoutAnimationType.stretch,
      ),
      WorkoutExerciseStep(
        id: 'cooldown_2',
        name: 'Deep Diaphragmatic Breathing',
        vietnameseName: 'Hít thở sâu điều hòa nhịp tim',
        sets: 1,
        reps: '45 giây',
        durationSeconds: 45,
        restSeconds: 0,
        targetMuscles: ['Hệ thần kinh', 'Phổi & Tim mạch'],
        category: 'Phục hồi',
        equipment: 'Thảm tập / Ngồi tĩnh',
        instructions:
            'Ngồi thả lỏng, hít sâu bằng mũi trong 4 giây, giữ hơi 2 giây, rồi thở từ từ ra bằng miệng trong 6 giây.',
        tips: 'Thả lỏng toàn bộ cơ mặt, cơ vai và cơ bụng.',
        breathingCue: 'Hít sâu căng bụng, thở ra xẹp bụng hoàn toàn.',
        animationType: WorkoutAnimationType.stretch,
      ),
    ];

    final phases = [
      WorkoutPhase(
        id: 'phase_warmup',
        title: 'Giai đoạn 1: Khởi động & Kích hoạt cơ',
        phaseType: 'warmup',
        description: 'Làm ấm cơ bắp, bôi trơn khớp và tăng nhịp tim dần đều.',
        durationMinutes: warmupMinutes,
        exercises: warmupSteps,
      ),
      WorkoutPhase(
        id: 'phase_main',
        title: 'Giai đoạn 2: Thân bài tập luyện chính',
        phaseType: 'main',
        description:
            'Thực hiện các động tác chính theo số hiệp và số lần quy định.',
        durationMinutes: mainMinutes,
        exercises: mainSteps,
      ),
      WorkoutPhase(
        id: 'phase_cooldown',
        title: 'Giai đoạn 3: Giãn cơ & Hạ nhiệt phục hồi',
        phaseType: 'cooldown',
        description:
            'Giải tỏa căng thẳng cơ bắp, giảm tích tụ acid lactic và hạ nhịp tim.',
        durationMinutes: cooldownMinutes,
        exercises: cooldownSteps,
      ),
    ];

    return WorkoutRoutinePlan(
      id: 'routine_${DateTime.now().millisecondsSinceEpoch}',
      title: name,
      level: level,
      totalDurationMinutes: duration,
      totalCalories: calories,
      summary:
          'Giáo án rèn luyện ${mainSteps.length} bài tập trọng tâm kết hợp khởi động và giãn cơ chuẩn thể thao.',
      phases: phases,
    );
  }

  /// Trích xuất danh sách bài tập từ chuỗi mô tả
  static List<WorkoutExerciseStep> _parseStepsFromDescription(String text) {
    if (text.trim().isEmpty) return [];

    final List<WorkoutExerciseStep> steps = [];
    final lines = text.split('\n');

    int index = 1;
    for (var rawLine in lines) {
      var line = rawLine.trim();
      if (line.isEmpty) continue;

      final isListItem = RegExp(r'^(?:[-*•]\s+|\d+[\.)]\s*)').hasMatch(line);
      final hasPrescription = RegExp(
        r'(?:\d+\s*(?:hiệp|sets?|lần|reps?|giây|phút)|\d+\s*[x×]\s*\d+)',
        caseSensitive: false,
      ).hasMatch(line);
      // Mô tả kỹ thuật prose của wger không phải danh sách bài tập. Chỉ parse
      // dòng có bullet/số thứ tự hoặc một prescription rõ ràng sau dấu ':'.
      if (!isListItem && !(line.contains(':') && hasPrescription)) continue;

      // Bỏ qua các dòng chỉ chứa số lần / số hiệp mồ côi (ví dụ: "- 10-12 lần", "3 hiệp")
      if (RegExp(
              r'^[-*•\s]*\d+([-\s]\d+)?\s*(lần|reps|hiệp|giây|phút|cái|set|sets)[\s\.\)]*$',
              caseSensitive: false)
          .hasMatch(line)) {
        continue;
      }

      // Loại bỏ các ký tự gạch đầu dòng, dấu sao hoặc số thứ tự ở đầu (ví dụ: "- ", "1. ", "2) ")
      line = line.replaceAll(RegExp(r'^[-*•\s]+'), '').trim();
      line = line.replaceAll(RegExp(r'^\d+[\.\)]\s*'), '').trim();
      if (line.isEmpty || line.length <= 2) continue;

      // Bỏ qua nếu sau khi lọc chỉ còn chữ lần / hiệp
      if (RegExp(r'^(lần|reps|hiệp|giây|phút)$', caseSensitive: false)
          .hasMatch(line)) {
        continue;
      }

      // Tách tên bài tập và cấu hình (ví dụ: "Seated Hip Adduction: 3 hiệp x 10-12 lần")
      String exerciseName = line;
      int sets = 3;
      String reps = '10-12 lần';
      int? durationSec;

      if (line.contains(':')) {
        final parts = line.split(':');
        exerciseName = parts[0].trim();
        final detailPart = parts.sublist(1).join(':').trim();

        // Tìm số hiệp (ví dụ: 3 hiệp, 4 sets)
        final setsMatch =
            RegExp(r'(\d+)\s*(hiệp|set|sets)', caseSensitive: false)
                .firstMatch(detailPart);
        if (setsMatch != null) {
          sets = int.tryParse(setsMatch.group(1)!) ?? 3;
        }

        // Tìm số lần hoặc thời gian (ví dụ: 10-12 lần, 45s, 45 giây)
        final repsMatch = RegExp(r'(\d+[-\s]\d+|\d+)\s*(lần|reps|cái|rep)',
                caseSensitive: false)
            .firstMatch(detailPart);
        if (repsMatch != null) {
          reps = '${repsMatch.group(1)} lần';
        } else {
          final timeMatch =
              RegExp(r'(\d+)\s*(giây|s|giay)', caseSensitive: false)
                  .firstMatch(detailPart);
          if (timeMatch != null) {
            durationSec = int.tryParse(timeMatch.group(1)!);
            reps = '$durationSec giây';
          } else if (detailPart.isNotEmpty) {
            reps = detailPart;
          }
        }
      } else if (RegExp(r'\s[-–—]\s').hasMatch(line)) {
        final parts = line.split(RegExp(r'\s[-–—]\s'));
        if (parts.length >= 2) {
          exerciseName = parts[0].trim();
          reps = parts.sublist(1).join('-').trim();
        }
      }

      if (exerciseName.isNotEmpty) {
        steps.add(_createDefaultStep(
          id: 'step_$index',
          rawName: exerciseName,
          sets: sets,
          reps: reps,
          durationSeconds: durationSec,
        ));
        index++;
      }
    }

    return steps;
  }

  /// Tạo một bước bài tập hoàn chỉnh kèm thông tin tra cứu từ từ điển
  static WorkoutExerciseStep _createDefaultStep({
    required String id,
    required String rawName,
    int sets = 3,
    String reps = '10-12 lần',
    int? durationSeconds,
  }) {
    final cleanKey = rawName.toLowerCase().trim();

    // Tìm kiếm trong kho tri thức bài tập
    Map<String, dynamic>? match;
    for (final entry in _exerciseKnowledgeBase.entries) {
      if (cleanKey.contains(entry.key) || entry.key.contains(cleanKey)) {
        match = entry.value;
        break;
      }
    }

    if (match != null) {
      return WorkoutExerciseStep(
        id: id,
        name: rawName,
        vietnameseName: match['vietnamese'] ?? '',
        sets: sets,
        reps: reps,
        durationSeconds: durationSeconds,
        restSeconds: 45,
        targetMuscles: List<String>.from(match['muscles'] ?? []),
        category: match['category'] ?? 'Sức mạnh',
        equipment: match['equipment'] ?? 'Dụng cụ thể thao',
        instructions: match['instructions'] ?? '',
        tips: match['tips'] ?? 'Tập chuẩn kỹ thuật, gồng chắc cơ lõi.',
        breathingCue:
            match['breathing'] ?? 'Thở ra khi phát lực, hít vào khi hạ.',
        animationType: match['animation'] ?? WorkoutAnimationType.generic,
      );
    }

    // Nếu không khớp từ điển cụ thể, tự suy đoán dựa trên từ khóa
    String category = 'Sức mạnh';
    List<String> muscles = ['Toàn thân'];
    WorkoutAnimationType anim = inferAnimationType(rawName);
    String equipment = 'Không cần dụng cụ';

    if (cleanKey.contains('press') || cleanKey.contains('đẩy')) {
      muscles = ['Vai & Ngực', 'Tay sau'];
      equipment = 'Tạ đơn / Máy đẩy';
    } else if (cleanKey.contains('pull') || cleanKey.contains('kéo')) {
      muscles = ['Lưng & Xô', 'Tay trước'];
      equipment = 'Tạ đơn / Xà đơn';
    } else if (cleanKey.contains('leg') ||
        cleanKey.contains('squat') ||
        cleanKey.contains('đùi') ||
        cleanKey.contains('chân')) {
      muscles = ['Cơ đùi', 'Cơ mông'];
      equipment = 'Bodyweight / Ghế';
    } else if (cleanKey.contains('ab') ||
        cleanKey.contains('plank') ||
        cleanKey.contains('bụng') ||
        cleanKey.contains('core') ||
        cleanKey.contains('hold')) {
      muscles = ['Cơ bụng (Core)', 'Cơ lưng dưới'];
      equipment = 'Thảm tập';
    } else if (cleanKey.contains('walk') ||
        cleanKey.contains('jump') ||
        cleanKey.contains('cardio')) {
      muscles = ['Tim mạch', 'Toàn thân'];
    }

    return WorkoutExerciseStep(
      id: id,
      name: rawName,
      vietnameseName: '',
      sets: sets,
      reps: reps,
      durationSeconds: durationSeconds,
      restSeconds: 45,
      targetMuscles: muscles,
      category: category,
      equipment: equipment,
      instructions:
          '1. Chuẩn bị tư thế cân bằng, gồng chặt cơ bụng.\n2. Thực hiện động tác nhịp nhàng, có kiểm soát theo từng hiệp.\n3. Nghỉ ngơi đủ thời gian giữa các hiệp để cơ bắp phục hồi.',
      tips: 'Tập trung vào cảm nhận cơ bắp, không dùng quán tính.',
      breathingCue:
          'Hít sâu khi hạ xuống / mở rộng, Thở ra dứt khoát khi dùng lực ép.',
      animationType: anim,
    );
  }

  static bool _isTimedMovement(String name) {
    final animation = inferAnimationType(name);
    return animation == WorkoutAnimationType.cardio ||
        animation == WorkoutAnimationType.dynamicMovement ||
        animation == WorkoutAnimationType.coreHold ||
        animation == WorkoutAnimationType.stretch;
  }

  /// Một nguồn phân loại hoạt ảnh dùng chung cho parser và màn chi tiết.
  static WorkoutAnimationType inferAnimationType(String exerciseName) {
    final name = exerciseName.toLowerCase();
    bool hasAny(Iterable<String> terms) => terms.any(name.contains);

    if (hasAny(
        ['run', 'jog', 'high knee', 'cardio', 'jump rope', 'skipping'])) {
      return WorkoutAnimationType.cardio;
    }
    if (hasAny(['stretch', 'mobility', 'yoga', 'flex', 'rotation'])) {
      return WorkoutAnimationType.stretch;
    }
    if (hasAny(['plank', 'crunch', 'abdominal', 'core', 'hold'])) {
      return WorkoutAnimationType.coreHold;
    }
    if (hasAny(['extension', 'adduction', 'abduction'])) {
      return WorkoutAnimationType.legExtension;
    }
    if (hasAny(['squat', 'lunge', 'leg press', 'hip thrust'])) {
      return WorkoutAnimationType.squat;
    }
    if (hasAny(['pull', 'row', 'chin', 'lat', 'curl'])) {
      return WorkoutAnimationType.pull;
    }
    if (hasAny(['press', 'push', 'shoulder', 'bench', 'dip'])) {
      return WorkoutAnimationType.press;
    }
    if (hasAny(['walk', 'jump', 'jack', 'burpee', 'crawl'])) {
      return WorkoutAnimationType.dynamicMovement;
    }
    return WorkoutAnimationType.generic;
  }
}
