import 'semantic_contract.dart';
import 'text_normalizer.dart';

class SemanticCandidate {
  const SemanticCandidate(this.intent, this.score);

  final String intent;
  final int score;
}

class SemanticCandidateDecision {
  SemanticCandidateDecision({
    required List<SemanticCandidate> candidates,
    required this.highConfidence,
    required this.negatedActions,
    required this.writeIntent,
    required this.confirmationIntent,
    required this.references,
    required this.ambiguity,
  }) : candidates = List.unmodifiable(candidates);

  final List<SemanticCandidate> candidates;
  final bool highConfidence;
  final List<String> negatedActions;
  final bool writeIntent;
  final String? confirmationIntent;
  final List<SemanticReference> references;
  final SemanticAmbiguity ambiguity;
}

class CheapSemanticCandidateRouter {
  const CheapSemanticCandidateRouter();

  SemanticCandidateDecision classify(NormalizedSemanticText input) {
    final text = _fold(input.candidates.join(' | '));
    final scores = <String, int>{};
    void add(String intent, int score) {
      scores[intent] = (scores[intent] ?? 0) + score;
    }

    if (_has(text, [
      'con bao nhieu calo',
      'calo con lai',
      'con bao nhieu protein',
      'macro hom nay'
    ])) {
      add('DAILY_NUTRITION_STATUS', 12);
    }
    if (_has(text, [
      'an gi',
      'mon gi',
      'mon chi',
      'goi y bua',
      'recommend meal',
      'recommend bua',
      'quat mon',
      'bua ni',
    ])) {
      add('MEAL_RECOMMENDATION', 10);
    }
    if (_has(
        text, ['dinh duong cua', 'bao nhieu calo trong', 'nutrition of'])) {
      add('FOOD_NUTRITION_LOOKUP', 11);
    }
    if (_has(
        text, ['co phu hop', 'danh gia bua', 'an qua nhieu', 'fit my goal'])) {
      add('MEAL_OR_DIET_EVALUATION', 10);
    }
    if (_has(text,
        ['can nang', 'weight trend', 'giam beo', 'giam can', 'tang can'])) {
      add('WEIGHT_PROGRESS', 8);
    }
    if (_has(text, [
      'phuc hoi',
      'dau moi',
      'met moi',
      'sleep',
      'stress',
      'dau nguc',
      'kho tho',
      'ngat sau',
    ])) {
      add('EXERCISE_RECOVERY', 8);
    }
    if (_has(text, [
      'bai tap',
      'bai taap',
      'lich tap',
      'workout',
      'tap gi',
      'chien bai',
      'suc ben',
    ])) {
      add('WORKOUT_RECOMMENDATION', 9);
    }
    if (_has(text, [
      'ke hoach',
      'len plan',
      'lap plan',
      'lap lich',
      'plan tuan',
      'kich hoat',
    ])) {
      add('PLAN_MANAGEMENT', 9);
    }
    if (_has(text, [
      'di ung',
      'an chay',
      'khong an hai san',
      'hong an duoc hai san',
      'cap nhat ho so',
    ])) {
      add('PROFILE_OR_CONSTRAINT_UPDATE', 10);
    }
    if (_has(text, ['la gi', 'loi ich', 'tai sao co the can', 'fiber'])) {
      add('GENERAL_NUTRITION_KNOWLEDGE', 7);
    }
    if (_has(text, ['nghien cuu', 'bang chung', 'lam sang', 'evidence'])) {
      add('EVIDENCE_HEALTH_QUESTION', 12);
    }
    if (_has(text, [
      'tai sao mon',
      'vi sao bai',
      'cai thu hai',
      'mon do',
      'buoi nay',
      'tuan sau ay',
      'doi cai do',
    ])) {
      add('FOLLOWUP_EXPLANATION', 8);
    }

    final negated = _negatedActions(text);
    final writeCue = _writeActions(text);
    final writeIntent = writeCue.isNotEmpty && negated.isEmpty;
    if (writeCue.isNotEmpty) add('APP_ACTION', writeIntent ? 12 : 3);

    if (_has(text, ['xin chao', 'cam on', 'hello']) ||
        RegExp(r'(^|[ |])hi($|[ |])').hasMatch(text)) {
      add('SMALLTALK_OR_OTHER', 10);
    }

    String? confirmation;
    for (final candidate in input.candidates) {
      confirmation ??= _confirmation(_fold(candidate));
    }
    final references = _references(text);
    final sorted = scores.entries
        .map((entry) => SemanticCandidate(entry.key, entry.value))
        .toList()
      ..sort((a, b) => b.score.compareTo(a.score));
    final top = sorted.isEmpty ? 0 : sorted.first.score;
    final second = sorted.length < 2 ? 0 : sorted[1].score;
    final highConfidence = top >= 10 && top - second >= 4;

    SemanticAmbiguity ambiguity = const SemanticAmbiguity(
      status: SemanticAmbiguityStatus.none,
    );
    if (_has(text, ['suc ben'])) {
      ambiguity = const SemanticAmbiguity(
        status: SemanticAmbiguityStatus.ambiguous,
        type: SemanticAmbiguityType.domain,
      );
    } else if (references.isNotEmpty &&
        input.normalizedText.split(' ').length <= 5) {
      ambiguity = const SemanticAmbiguity(
        status: SemanticAmbiguityStatus.ambiguous,
        type: SemanticAmbiguityType.reference,
      );
    } else if (_has(text, ['len plan di']) &&
        text.trim().split(' ').length <= 4) {
      ambiguity = const SemanticAmbiguity(
        status: SemanticAmbiguityStatus.ambiguous,
        type: SemanticAmbiguityType.missingRequiredContext,
      );
    } else if (sorted.isEmpty && confirmation == null) {
      ambiguity = const SemanticAmbiguity(
        status: SemanticAmbiguityStatus.ambiguous,
        type: SemanticAmbiguityType.lexical,
      );
    } else if (sorted.length > 1 && top == second) {
      ambiguity = const SemanticAmbiguity(
        status: SemanticAmbiguityStatus.ambiguous,
        type: SemanticAmbiguityType.conflict,
      );
    }

    return SemanticCandidateDecision(
      candidates: sorted.take(4).toList(),
      highConfidence:
          highConfidence && ambiguity.status == SemanticAmbiguityStatus.none,
      negatedActions: negated,
      writeIntent: writeIntent,
      confirmationIntent: confirmation,
      references: references,
      ambiguity: ambiguity,
    );
  }

  static bool _has(String text, List<String> phrases) =>
      phrases.any(text.contains);

  static String _fold(String input) {
    const source =
        'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ';
    const target =
        'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd';
    var output = input.toLowerCase();
    for (var i = 0; i < source.length; i++) {
      output = output.replaceAll(source[i], target[i]);
    }
    return output.replaceAll(RegExp(r'[^a-z0-9_|]+'), ' ').trim();
  }

  static List<String> _writeActions(String text) {
    final actions = <String>[];
    if (_has(text, [
      'ghi bua',
      'ghi lai bua',
      'luu bua',
      'log meal',
      'ghi mon',
      'luu mon',
    ])) {
      actions.add('LOG_MEAL');
    }
    if (_has(text, ['ghi can', 'luu can', 'log weight'])) {
      actions.add('LOG_WEIGHT');
    }
    if (_has(text, ['ghi bai tap', 'luu bai tap', 'log exercise'])) {
      actions.add('LOG_EXERCISE');
    }
    if (_has(text, ['tao ke hoach', 'lap ke hoach', 'create plan'])) {
      actions.add('CREATE_PLAN');
    }
    if (_has(text, ['kich hoat'])) actions.add('ACTIVATE_PLAN');
    if (_has(text, ['cap nhat ho so'])) actions.add('UPDATE_PROFILE');
    return actions;
  }

  static List<String> _negatedActions(String text) {
    final hasNegation = _has(text, [
      'dung ',
      'khong can ',
      'chi hoi thoi',
      'chua ',
      'khong tao ',
      'dung kich hoat',
    ]);
    if (!hasNegation) return const [];
    final actions = _writeActions(text);
    if (actions.isNotEmpty) return actions;
    if (_has(text, ['dung luu', 'khong can ghi', 'chi hoi thoi'])) {
      return const ['LOG_MEAL'];
    }
    return const [];
  }

  static String? _confirmation(String text) {
    final compact = text.replaceAll('|', ' ').trim();
    if (RegExp(r'^(co|ok|oke|uh|u|dong y|yes)$').hasMatch(compact)) {
      return 'AFFIRM';
    }
    if (RegExp(r'^(khong|ko|k|thoi|no|huy)$').hasMatch(compact)) {
      return 'REJECT';
    }
    return null;
  }

  static List<SemanticReference> _references(String text) {
    final refs = <SemanticReference>[];
    final ordinal = RegExp(r'cai thu (\d+|hai|ba|tu)').firstMatch(text);
    if (ordinal != null) {
      final rawOrdinal = ordinal.group(1)!;
      final parsedOrdinal = int.tryParse(rawOrdinal) ??
          const {'hai': 2, 'ba': 3, 'tu': 4}[rawOrdinal];
      refs.add(SemanticReference(
        kind: 'ORDINAL_VISIBLE_ITEM',
        ordinal: parsedOrdinal,
        surface: ordinal.group(0),
      ));
    }
    if (_has(text, [
      'cai do',
      'mon do',
      'buoi nay',
      'tuan sau ay',
      'khong phai buoi',
    ])) {
      refs.add(const SemanticReference(kind: 'RECENT_VISIBLE_REFERENCE'));
    }
    return refs;
  }
}
