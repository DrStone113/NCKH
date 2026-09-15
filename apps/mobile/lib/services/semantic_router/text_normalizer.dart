import 'semantic_contract.dart';

class NormalizedSemanticText {
  NormalizedSemanticText({
    required this.rawText,
    required this.normalizedText,
    required List<String> candidates,
    required List<NormalizationTransform> transforms,
  })  : candidates = List.unmodifiable(candidates),
        transforms = List.unmodifiable(transforms);

  final String rawText;
  final String normalizedText;
  final List<String> candidates;
  final List<NormalizationTransform> transforms;
}

class ConservativeVietnameseNormalizer {
  const ConservativeVietnameseNormalizer();

  static const Map<String, String> _unambiguousChatTokens = {
    'j': 'gì',
    'dc': 'được',
    'đc': 'được',
    'mún': 'muốn',
    'hok': 'không',
    'hông': 'không',
  };

  static const Map<String, String> _ambiguousChatTokens = {
    'k': 'không',
    'ko': 'không',
  };

  NormalizedSemanticText normalize(String rawText) {
    var base = rawText.replaceAll(RegExp(r'[\u200B-\u200D\uFEFF]'), '');
    final controlRemoved = rawText.length - base.length;
    final beforeWhitespace = base;
    base = base.trim().replaceAll(RegExp(r'\s+'), ' ');

    final transforms = <NormalizationTransform>[];
    if (controlRemoved > 0) {
      transforms.add(NormalizationTransform(
        kind: 'UNICODE_CONTROL_REMOVED',
        count: controlRemoved,
      ));
    }
    if (base != beforeWhitespace) {
      transforms.add(const NormalizationTransform(
        kind: 'WHITESPACE_COLLAPSED',
        count: 1,
      ));
    }

    final safeExpanded = _expandTokens(base, _unambiguousChatTokens);
    if (safeExpanded != base) {
      transforms.add(const NormalizationTransform(
        kind: 'UNAMBIGUOUS_CHAT_TOKEN_CANDIDATE',
        count: 1,
      ));
    }
    final ambiguousExpanded = _expandTokens(
      safeExpanded,
      _ambiguousChatTokens,
    );
    if (ambiguousExpanded != safeExpanded) {
      transforms.add(const NormalizationTransform(
        kind: 'AMBIGUOUS_CHAT_TOKEN_CANDIDATE',
        count: 1,
      ));
    }

    final repeatedCandidate = ambiguousExpanded.replaceAllMapped(
      RegExp(r'([\p{L}])\1{2,}', unicode: true, caseSensitive: false),
      (match) => '${match.group(1)}${match.group(1)}',
    );
    if (repeatedCandidate != ambiguousExpanded) {
      transforms.add(const NormalizationTransform(
        kind: 'REPEATED_CHARACTER_CANDIDATE',
        count: 1,
      ));
    }
    final candidates = <String>{
      base,
      safeExpanded,
      ambiguousExpanded,
      repeatedCandidate,
    }.where((value) => value.isNotEmpty).toList(growable: false);
    return NormalizedSemanticText(
      rawText: rawText,
      normalizedText: base,
      candidates: candidates,
      transforms: transforms,
    );
  }

  static String _expandTokens(String input, Map<String, String> replacements) {
    return input.split(' ').map((token) {
      final match = RegExp(
              r'^([^\p{L}\p{N}]*)((?:[\p{L}\p{N}]+))([^\p{L}\p{N}]*)$',
              unicode: true)
          .firstMatch(token);
      if (match == null) return token;
      final core = match.group(2)!;
      final replacement = replacements[core.toLowerCase()];
      if (replacement == null) return token;
      return '${match.group(1)}$replacement${match.group(3)}';
    }).join(' ');
  }
}
