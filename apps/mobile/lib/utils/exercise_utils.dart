import 'dart:math' as math;

/// Các quy tắc dùng chung cho dữ liệu bài tập từ wger và nhật ký vận động.
///
/// Gom logic vào một nơi để danh sách, màn chi tiết, chatbot và nhật ký không
/// tự suy luận category/MET theo những cách khác nhau.
class ExerciseUtils {
  ExerciseUtils._();

  static const int defaultDurationMinutes = 30;
  static const int minDurationMinutes = 1;
  static const int maxDurationMinutes = 24 * 60;

  static String cleanHtml(String html) {
    if (html.isEmpty) return '';
    return html
        .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), ' ')
        .replaceAll(
            RegExp(r'</(?:p|li|div|h[1-6])>', caseSensitive: false), ' ')
        .replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&#160;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&#x27;', "'")
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  /// Chuẩn hóa để tìm kiếm không phân biệt hoa thường, dấu tiếng Việt và
  /// khoảng trắng thừa.
  static String normalizeSearchText(String value) {
    var text = value.toLowerCase().trim();
    const replacements = <String, String>{
      'àáạảãâầấậẩẫăằắặẳẵ': 'a',
      'èéẹẻẽêềếệểễ': 'e',
      'ìíịỉĩ': 'i',
      'òóọỏõôồốộổỗơờớợởỡ': 'o',
      'ùúụủũưừứựửữ': 'u',
      'ỳýỵỷỹ': 'y',
      'đ': 'd',
    };
    for (final entry in replacements.entries) {
      for (final char in entry.key.split('')) {
        text = text.replaceAll(char, entry.value);
      }
    }
    return text.replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
  }

  static String mapToAppType(String name, String categoryName) {
    final text = normalizeSearchText('$name $categoryName');
    bool has(String term) => text.contains(term);

    if (has('cardio') ||
        has('running') ||
        has('cycling') ||
        has('swim') ||
        has('jump rope') ||
        has('high knee') ||
        has('elliptical')) {
      return 'cardio';
    }
    if (has('stretch') ||
        has('flexibility') ||
        has('mobility') ||
        has('yoga') ||
        has('pilates')) {
      return 'flexibility';
    }
    if (has('strength') ||
        has('weight') ||
        has('barbell') ||
        has('dumbbell') ||
        has('arms') ||
        has('legs') ||
        has('chest') ||
        has('back') ||
        has('shoulders') ||
        has('abs') ||
        has('calves')) {
      return 'strength';
    }
    return 'sports';
  }

  static double estimateMet(
    String name,
    String categoryName,
    int muscleCount,
  ) {
    final n = normalizeSearchText(name);
    final cat = normalizeSearchText(categoryName);
    final safeMuscleCount = muscleCount.clamp(0, 20);

    bool named(Iterable<String> terms) => terms.any(n.contains);
    bool categorized(Iterable<String> terms) => terms.any(cat.contains);

    if (named(['sprint', 'nuoc rut', 'hiit', 'tabata', 'burpee'])) return 11.5;
    if (named(['jump rope', 'skipping', 'nhay day', 'box jump'])) return 10.0;
    if (named(['swimming', 'swim', 'boi', 'butterfly', 'crawl'])) {
      return named(['sprint', 'fast']) ? 10.0 : 8.0;
    }
    if (named(['running', 'chay bo', 'treadmill', 'jogging'])) {
      if (named(['fast', 'speed'])) return 10.5;
      if (named(['zone 2', 'slow', 'light'])) return 7.0;
      return 8.5;
    }
    if (named([
      'high knee',
      'mountain climber',
      'jumping jack',
      'bear crawl',
      'bear walk',
    ])) {
      return 8.0;
    }
    if (named(['rowing', 'cheo thuyen'])) return 7.5;
    if (named(['cycling', 'dap xe', 'spinning', 'bike'])) {
      return named(['fast', 'intense']) ? 8.5 : 6.5;
    }
    if (named(
        ['elliptical', 'crosstrainer', 'stair', 'cau thang', 'stepper'])) {
      return 6.0;
    }
    if (named(['suspended', 'trx', 'crossess', 'suspension'])) return 5.5;
    if (named(['walk', 'di bo', 'hiking', 'leo nui'])) {
      return named(['incline', 'fast', 'nhanh']) ? 5.0 : 3.5;
    }

    if (named(['deadlift', 'squat', 'clean', 'snatch', 'thruster'])) {
      return 6.5 + (safeMuscleCount > 2 ? 0.5 : 0.0);
    }
    if (named([
      'bench press',
      'pull up',
      'chin up',
      'push up',
      'hit dat',
      'dips',
      'overhead press',
      'military press',
      'barbell row',
    ])) {
      return 5.8 + (safeMuscleCount > 1 ? 0.4 : 0.0);
    }
    if (named(['lunge', 'leg press', 'hack squat', 'hip thrust'])) return 5.2;
    if (named([
      'plank',
      'crunch',
      'sit up',
      'russian twist',
      'leg raise',
      'ab wheel',
      'core',
    ])) {
      return 4.2;
    }
    if (named([
      'curl',
      'extension',
      'raise',
      'fly',
      'flyes',
      'pulldown',
      'kickback',
      'adduction',
      'abduction',
      'shrug',
    ])) {
      return 3.8 + (safeMuscleCount > 1 ? 0.3 : 0.0);
    }

    if (named([
      'football',
      'soccer',
      'bong da',
      'basketball',
      'bong ro',
      'boxing',
      'kickboxing',
    ])) {
      return 7.5;
    }
    if (named(['badminton', 'cau long', 'tennis', 'quan vot'])) return 6.0;
    if (named(['table tennis', 'bong ban', 'volleyball', 'bong chuyen'])) {
      return 4.5;
    }
    if (named(['yoga', 'pilates'])) {
      return named(['power', 'vinyasa']) ? 4.0 : 3.0;
    }
    if (named(['stretch', 'gian co', 'mobility', 'warmup', 'cooldown'])) {
      return 2.5;
    }

    // Checksum tự triển khai để kết quả giống nhau trên mọi runtime. Dao động
    // nhỏ chỉ tránh các bài chưa nhận diện bị hiển thị hoàn toàn giống nhau.
    var checksum = 0;
    for (final codeUnit in n.codeUnits) {
      checksum = (checksum * 31 + codeUnit) & 0x7fffffff;
    }
    final variation = ((checksum % 7) - 3) * 0.1;

    if (categorized(['cardio', 'running'])) {
      return (6.5 + safeMuscleCount * 0.3 + variation).clamp(4.0, 11.0);
    }
    if (categorized([
      'strength',
      'weight',
      'barbell',
      'dumbbell',
      'arms',
      'legs',
      'chest',
      'back',
      'shoulders',
      'abs',
      'calves',
    ])) {
      return (4.5 + safeMuscleCount * 0.4 + variation).clamp(3.5, 7.5);
    }
    if (categorized(['stretch', 'flexibility', 'yoga'])) {
      return (2.5 + variation).clamp(2.0, 3.5);
    }
    return (4.0 + safeMuscleCount * 0.2 + variation).clamp(3.0, 6.0);
  }

  static double calculateCalories({
    required double met,
    required double weightKg,
    required int durationMinutes,
  }) {
    if (!met.isFinite || !weightKg.isFinite || met <= 0 || weightKg <= 0) {
      return 0;
    }
    final duration = durationMinutes.clamp(0, maxDurationMinutes);
    return met * weightKg * (duration / 60.0);
  }

  static int parseDuration(
    String? raw, {
    int fallback = defaultDurationMinutes,
  }) {
    final parsed = int.tryParse(raw?.trim() ?? '');
    if (parsed == null) {
      return fallback.clamp(minDurationMinutes, maxDurationMinutes);
    }
    return math.max(minDurationMinutes, math.min(maxDurationMinutes, parsed));
  }

  /// Lấy ID gốc từ các template local có dạng `wger_123`.
  static int parseWgerId(String? templateId) {
    if (templateId == null || !templateId.startsWith('wger_')) return 0;
    final id = int.tryParse(templateId.substring('wger_'.length));
    return id != null && id > 0 ? id : 0;
  }
}
