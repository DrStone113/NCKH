import 'dart:async';
import 'dart:convert';

import 'local_slm_runtime.dart';
import 'semantic_candidate_router.dart';
import 'semantic_contract.dart';
import 'semantic_verifier.dart';
import 'text_normalizer.dart';

const _modeValue = String.fromEnvironment(
  'SEMANTIC_ROUTER_MODE',
  defaultValue: 'shadow',
);

class SemanticRoutingObservation {
  const SemanticRoutingObservation({
    required this.mode,
    required this.slmInvoked,
    required this.reasonCode,
    required this.rawLength,
    required this.transforms,
    this.candidateScores = const {},
    this.result,
    this.verifierReasons = const [],
  });

  final SemanticRouterMode mode;
  final bool slmInvoked;
  final String reasonCode;
  final int rawLength;
  final List<NormalizationTransform> transforms;
  final Map<String, int> candidateScores;
  final SemanticParseResult? result;
  final List<String> verifierReasons;

  Map<String, Object?> toTelemetryJson() => {
        'mode': mode.name,
        'slm_invoked': slmInvoked,
        'reason_code': reasonCode,
        'raw_length': rawLength,
        'normalization_transforms':
            transforms.map((item) => item.toJson()).toList(),
        'candidate_scores': candidateScores,
        'verifier_reasons': verifierReasons,
        if (result != null) 'parse': result!.toTelemetryJson(),
      };
}

class SemanticRouter {
  SemanticRouter({
    SemanticRouterMode? mode,
    SemanticSlmRuntime? runtime,
    ConservativeVietnameseNormalizer normalizer =
        const ConservativeVietnameseNormalizer(),
    CheapSemanticCandidateRouter candidateRouter =
        const CheapSemanticCandidateRouter(),
    SemanticResultVerifier verifier = const SemanticResultVerifier(),
  })  : mode = mode ?? parseSemanticRouterMode(_modeValue),
        _runtime = runtime ?? createSemanticSlmRuntime(),
        _normalizer = normalizer,
        _candidateRouter = candidateRouter,
        _verifier = verifier;

  final SemanticRouterMode mode;
  final SemanticSlmRuntime _runtime;
  final ConservativeVietnameseNormalizer _normalizer;
  final CheapSemanticCandidateRouter _candidateRouter;
  final SemanticResultVerifier _verifier;

  static SemanticRouterMode parseSemanticRouterMode(String value) =>
      switch (value.trim().toLowerCase()) {
        'off' => SemanticRouterMode.off,
        'enforced' => SemanticRouterMode.enforced,
        _ => SemanticRouterMode.shadow,
      };

  Future<SemanticRoutingObservation> analyze(
    String rawText, {
    bool pendingActionActive = false,
    String? recentReferenceKind,
  }) async {
    final normalized = _normalizer.normalize(rawText);
    if (mode == SemanticRouterMode.off) {
      return SemanticRoutingObservation(
        mode: mode,
        slmInvoked: false,
        reasonCode: 'MODE_OFF',
        rawLength: rawText.length,
        transforms: normalized.transforms,
      );
    }
    final decision = _candidateRouter.classify(normalized);
    final candidateScores = {
      for (final candidate in decision.candidates)
        candidate.intent: candidate.score,
    };
    if (pendingActionActive && decision.confirmationIntent != null) {
      final parse = _deterministicParse(
        normalized,
        decision,
        parserSource: 'PENDING_ACTION_FAST_PATH',
      );
      return SemanticRoutingObservation(
        mode: mode,
        slmInvoked: false,
        reasonCode: 'PENDING_ACTION_AUTHORITATIVE',
        rawLength: rawText.length,
        transforms: normalized.transforms,
        candidateScores: candidateScores,
        result: parse,
      );
    }
    if (decision.highConfidence) {
      final parse = _deterministicParse(
        normalized,
        decision,
        parserSource: 'DETERMINISTIC_CANDIDATE',
      );
      return SemanticRoutingObservation(
        mode: mode,
        slmInvoked: false,
        reasonCode: 'DETERMINISTIC_HIGH_CONFIDENCE',
        rawLength: rawText.length,
        transforms: normalized.transforms,
        candidateScores: candidateScores,
        result: parse,
      );
    }

    final availability = await _runtime.availability();
    if (!availability.available) {
      return _fallback(
        normalized,
        decision,
        availability.reasonCode,
        candidateScores: candidateScores,
      );
    }

    final stopwatch = Stopwatch()..start();
    try {
      final output = await _runtime.infer(SemanticSlmRequest(
        prompt: _prompt(normalized, decision, recentReferenceKind),
      ));
      stopwatch.stop();
      final parsed = _parseModelOutput(
        output,
        normalized,
        decision,
        availability,
        stopwatch.elapsedMilliseconds,
      );
      final verification = _verifier.verify(
        parsed,
        candidateIntents:
            decision.candidates.map((item) => item.intent).toSet(),
        pendingActionActive: pendingActionActive,
      );
      if (!verification.valid) {
        return _fallback(
          normalized,
          decision,
          'VERIFIER_REJECTED',
          slmInvoked: true,
          candidateScores: candidateScores,
          verifierReasons: verification.reasonCodes,
        );
      }
      return SemanticRoutingObservation(
        mode: mode,
        slmInvoked: true,
        reasonCode: 'SLM_VERIFIED',
        rawLength: rawText.length,
        transforms: normalized.transforms,
        candidateScores: candidateScores,
        result: parsed.copyWith(
          verifierStatus: SemanticVerifierStatus.valid,
          latencyMs: stopwatch.elapsedMilliseconds,
        ),
      );
    } on TimeoutException {
      return _fallback(
        normalized,
        decision,
        'INFERENCE_TIMEOUT',
        slmInvoked: true,
        candidateScores: candidateScores,
      );
    } on FormatException {
      return _fallback(
        normalized,
        decision,
        'INVALID_STRUCTURED_OUTPUT',
        slmInvoked: true,
        candidateScores: candidateScores,
      );
    } catch (_) {
      return _fallback(
        normalized,
        decision,
        'INFERENCE_FAILED',
        slmInvoked: true,
        candidateScores: candidateScores,
      );
    }
  }

  SemanticRoutingObservation _fallback(
    NormalizedSemanticText normalized,
    SemanticCandidateDecision decision,
    String reasonCode, {
    bool slmInvoked = false,
    List<String> verifierReasons = const [],
    Map<String, int> candidateScores = const {},
  }) {
    final fallback = _deterministicParse(
      normalized,
      decision,
      parserSource: 'LEGACY_FALLBACK',
      verifierStatus: SemanticVerifierStatus.fallback,
    );
    return SemanticRoutingObservation(
      mode: mode,
      slmInvoked: slmInvoked,
      reasonCode: reasonCode,
      rawLength: normalized.rawText.length,
      transforms: normalized.transforms,
      candidateScores: candidateScores,
      result: fallback,
      verifierReasons: verifierReasons,
    );
  }

  SemanticParseResult _deterministicParse(
    NormalizedSemanticText normalized,
    SemanticCandidateDecision decision, {
    required String parserSource,
    SemanticVerifierStatus verifierStatus = SemanticVerifierStatus.valid,
  }) {
    final candidates = decision.candidates.map((item) => item.intent).toList();
    final primary =
        candidates.isEmpty ? 'SMALLTALK_OR_OTHER' : candidates.first;
    final secondary = decision.candidates
        .skip(1)
        .where((item) => item.score >= 8)
        .map((item) => item.intent)
        .toList();
    final clarification =
        decision.ambiguity.status == SemanticAmbiguityStatus.ambiguous
            ? candidates
            : const <String>[];
    return SemanticParseResult(
      rawText: normalized.rawText,
      normalizedText: normalized.normalizedText,
      normalizedCandidates: normalized.candidates,
      primaryIntent: primary,
      secondaryIntents: secondary,
      candidateIntents: candidates,
      entities: const {},
      writeIntent: decision.writeIntent,
      negatedActions: decision.negatedActions,
      confirmationIntent: decision.confirmationIntent,
      references: decision.references,
      ambiguity: decision.ambiguity,
      clarificationCandidates: clarification,
      parserSource: parserSource,
      parserVersion: semanticRouterVersion,
      modelId: null,
      modelQuantization: null,
      modelHash: null,
      latencyMs: 0,
      verifierStatus: verifierStatus,
      uncertainty:
          decision.ambiguity.status == SemanticAmbiguityStatus.ambiguous
              ? SemanticUncertainty.clarificationRequired
              : decision.highConfidence
                  ? SemanticUncertainty.routeConfident
                  : SemanticUncertainty.routeUncertain,
    );
  }

  SemanticParseResult _parseModelOutput(
    String output,
    NormalizedSemanticText normalized,
    SemanticCandidateDecision decision,
    SemanticSlmAvailability availability,
    int latencyMs,
  ) {
    final start = output.indexOf('{');
    final end = output.lastIndexOf('}');
    if (start < 0 || end <= start) {
      throw const FormatException('No JSON object');
    }
    final decoded = jsonDecode(output.substring(start, end + 1));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('JSON root must be an object');
    }
    T required<T>(String key) {
      final value = decoded[key];
      if (value is! T) throw FormatException('Invalid $key');
      return value;
    }

    final secondaryRaw = required<List<dynamic>>('secondary_intents');
    final negatedRaw = required<List<dynamic>>('negated_actions');
    final entitiesRaw = required<Map<String, dynamic>>('entities');
    final referencesRaw = required<List<dynamic>>('references');
    final ambiguityRaw = required<Map<String, dynamic>>('ambiguity');
    final clarificationRaw =
        required<List<dynamic>>('clarification_candidates');
    final primary = required<String>('primary_intent');
    final modelWrite = required<bool>('write_intent');
    if (secondaryRaw.any((item) => item is! String) ||
        negatedRaw.any((item) => item is! String) ||
        clarificationRaw.any((item) => item is! String) ||
        referencesRaw.any((item) => item is! Map)) {
      throw const FormatException('Invalid array member');
    }
    final ambiguityStatus = ambiguityRaw['status'];
    final ambiguityType = ambiguityRaw['type'];
    const ambiguityTypes = {
      'LEXICAL',
      'DOMAIN',
      'REFERENCE',
      'CONFLICT',
      'MISSING_REQUIRED_CONTEXT',
    };
    if (ambiguityStatus != 'NONE' && ambiguityStatus != 'AMBIGUOUS') {
      throw const FormatException('Invalid ambiguity status');
    }
    if (ambiguityType != null &&
        (ambiguityType is! String || !ambiguityTypes.contains(ambiguityType))) {
      throw const FormatException('Invalid ambiguity type');
    }
    if ((ambiguityStatus == 'NONE') != (ambiguityType == null)) {
      throw const FormatException('Inconsistent ambiguity');
    }
    final confirmation = decoded['confirmation_intent'];
    if (confirmation != null &&
        (confirmation is! String ||
            !const {'AFFIRM', 'REJECT', 'CLARIFY'}.contains(confirmation))) {
      throw const FormatException('Invalid confirmation intent');
    }

    // Deterministic negation is authoritative over model output.
    final negated = decision.negatedActions.isNotEmpty
        ? decision.negatedActions
        : negatedRaw.whereType<String>().toList();
    return SemanticParseResult(
      rawText: normalized.rawText,
      normalizedText: normalized.normalizedText,
      normalizedCandidates: normalized.candidates,
      primaryIntent: primary,
      secondaryIntents: secondaryRaw.whereType<String>().toList(),
      candidateIntents: decision.candidates.map((item) => item.intent).toList(),
      entities: entitiesRaw,
      writeIntent: negated.isEmpty && modelWrite,
      negatedActions: negated,
      confirmationIntent: confirmation as String?,
      references: referencesRaw
          .whereType<Map>()
          .map((item) =>
              SemanticReference.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
      ambiguity: SemanticAmbiguity.fromJson(ambiguityRaw),
      clarificationCandidates: clarificationRaw.whereType<String>().toList(),
      parserSource: 'ON_DEVICE_SLM',
      parserVersion: semanticRouterVersion,
      modelId: availability.modelId,
      modelQuantization: availability.quantization,
      modelHash: availability.modelHash,
      latencyMs: latencyMs,
      verifierStatus: SemanticVerifierStatus.valid,
      uncertainty: ambiguityRaw['status'] == 'NONE'
          ? SemanticUncertainty.routeUncertain
          : SemanticUncertainty.clarificationRequired,
    );
  }

  static String _prompt(
    NormalizedSemanticText normalized,
    SemanticCandidateDecision decision,
    String? recentReferenceKind,
  ) {
    final candidates = decision.candidates.map((item) => item.intent).toList();
    final payload = {
      'text': normalized.normalizedText,
      'normalized_candidates': normalized.candidates,
      'candidate_intents': candidates,
      if (recentReferenceKind != null)
        'recent_reference_kind': recentReferenceKind,
    };
    return '''/no_think
You are a Vietnamese semantic parser. Return one compact JSON object only. Never call tools, decide policy, or explain reasoning. Use only candidate_intents, or SMALLTALK_OR_OTHER when none fits.
Required keys: primary_intent (string), secondary_intents (array), entities (object), write_intent (bool), negated_actions (array), confirmation_intent (AFFIRM|REJECT|CLARIFY|null), references (array of {kind, ordinal?, surface?}), ambiguity ({status: NONE|AMBIGUOUS, type: LEXICAL|DOMAIN|REFERENCE|CONFLICT|MISSING_REQUIRED_CONTEXT|null}), clarification_candidates (array).
Input: ${jsonEncode(payload)}''';
  }

  Future<void> dispose() => _runtime.dispose();
}
