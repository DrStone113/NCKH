import 'dart:collection';

const semanticRouterVersion = 'semantic-router-s1-v1';
const semanticSchemaVersion = 'semantic-parse-v1';
const semanticNormalizerVersion = 'semantic-normalizer-v1';

const Set<String> supportedSemanticIntents = {
  'DAILY_NUTRITION_STATUS',
  'MEAL_RECOMMENDATION',
  'FOOD_NUTRITION_LOOKUP',
  'MEAL_OR_DIET_EVALUATION',
  'WEIGHT_PROGRESS',
  'EXERCISE_RECOVERY',
  'WORKOUT_RECOMMENDATION',
  'PLAN_MANAGEMENT',
  'PROFILE_OR_CONSTRAINT_UPDATE',
  'GENERAL_NUTRITION_KNOWLEDGE',
  'EVIDENCE_HEALTH_QUESTION',
  'FOLLOWUP_EXPLANATION',
  'APP_ACTION',
  'SMALLTALK_OR_OTHER',
};

const Set<String> supportedSemanticActions = {
  'LOG_MEAL',
  'LOG_WEIGHT',
  'LOG_EXERCISE',
  'LOG_LIFESTYLE',
  'CREATE_PLAN',
  'SAVE_PLAN',
  'ACTIVATE_PLAN',
  'UPDATE_PROFILE',
  'DELETE_RECORD',
};

enum SemanticRouterMode { off, shadow, enforced }

enum SemanticAmbiguityStatus { none, ambiguous }

enum SemanticAmbiguityType {
  lexical,
  domain,
  reference,
  conflict,
  missingRequiredContext,
}

enum SemanticVerifierStatus { valid, invalid, fallback }

enum SemanticUncertainty {
  routeConfident,
  routeUncertain,
  clarificationRequired,
}

class NormalizationTransform {
  const NormalizationTransform({required this.kind, required this.count});

  final String kind;
  final int count;

  Map<String, Object> toJson() => {'kind': kind, 'count': count};
}

class SemanticReference {
  const SemanticReference({
    required this.kind,
    this.ordinal,
    this.surface,
  });

  final String kind;
  final int? ordinal;
  final String? surface;

  factory SemanticReference.fromJson(Map<String, dynamic> json) {
    return SemanticReference(
      kind: json['kind'] as String? ?? '',
      ordinal: json['ordinal'] as int?,
      surface: json['surface'] as String?,
    );
  }

  Map<String, Object?> toJson() => {
        'kind': kind,
        if (ordinal != null) 'ordinal': ordinal,
        if (surface != null) 'surface': surface,
      };
}

class SemanticAmbiguity {
  const SemanticAmbiguity({required this.status, this.type});

  final SemanticAmbiguityStatus status;
  final SemanticAmbiguityType? type;

  factory SemanticAmbiguity.fromJson(Map<String, dynamic> json) {
    final rawStatus = json['status'];
    final status = rawStatus == 'NONE'
        ? SemanticAmbiguityStatus.none
        : SemanticAmbiguityStatus.ambiguous;
    final rawType = json['type'];
    final type = switch (rawType) {
      'LEXICAL' => SemanticAmbiguityType.lexical,
      'DOMAIN' => SemanticAmbiguityType.domain,
      'REFERENCE' => SemanticAmbiguityType.reference,
      'CONFLICT' => SemanticAmbiguityType.conflict,
      'MISSING_REQUIRED_CONTEXT' =>
        SemanticAmbiguityType.missingRequiredContext,
      _ => null,
    };
    return SemanticAmbiguity(status: status, type: type);
  }

  String get statusWire =>
      status == SemanticAmbiguityStatus.none ? 'NONE' : 'AMBIGUOUS';

  String? get typeWire => switch (type) {
        SemanticAmbiguityType.lexical => 'LEXICAL',
        SemanticAmbiguityType.domain => 'DOMAIN',
        SemanticAmbiguityType.reference => 'REFERENCE',
        SemanticAmbiguityType.conflict => 'CONFLICT',
        SemanticAmbiguityType.missingRequiredContext =>
          'MISSING_REQUIRED_CONTEXT',
        null => null,
      };

  Map<String, Object?> toJson() => {'status': statusWire, 'type': typeWire};
}

class SemanticParseResult {
  SemanticParseResult({
    required this.rawText,
    required this.normalizedText,
    required List<String> normalizedCandidates,
    required this.primaryIntent,
    required List<String> secondaryIntents,
    required List<String> candidateIntents,
    required Map<String, Object?> entities,
    required this.writeIntent,
    required List<String> negatedActions,
    required this.confirmationIntent,
    required List<SemanticReference> references,
    required this.ambiguity,
    required List<String> clarificationCandidates,
    required this.parserSource,
    required this.parserVersion,
    required this.modelId,
    required this.modelQuantization,
    required this.modelHash,
    required this.latencyMs,
    required this.verifierStatus,
    required this.uncertainty,
    this.schemaVersion = semanticSchemaVersion,
  })  : normalizedCandidates = List.unmodifiable(normalizedCandidates),
        secondaryIntents = List.unmodifiable(secondaryIntents),
        candidateIntents = List.unmodifiable(candidateIntents),
        entities = UnmodifiableMapView(Map.of(entities)),
        negatedActions = List.unmodifiable(negatedActions),
        references = List.unmodifiable(references),
        clarificationCandidates = List.unmodifiable(clarificationCandidates);

  final String rawText;
  final String normalizedText;
  final List<String> normalizedCandidates;
  final String primaryIntent;
  final List<String> secondaryIntents;
  final List<String> candidateIntents;
  final Map<String, Object?> entities;
  final bool writeIntent;
  final List<String> negatedActions;
  final String? confirmationIntent;
  final List<SemanticReference> references;
  final SemanticAmbiguity ambiguity;
  final List<String> clarificationCandidates;
  final String parserSource;
  final String parserVersion;
  final String? modelId;
  final String? modelQuantization;
  final String? modelHash;
  final int latencyMs;
  final SemanticVerifierStatus verifierStatus;
  final SemanticUncertainty uncertainty;
  final String schemaVersion;

  SemanticParseResult copyWith({
    SemanticVerifierStatus? verifierStatus,
    SemanticUncertainty? uncertainty,
    int? latencyMs,
    String? parserSource,
  }) {
    return SemanticParseResult(
      rawText: rawText,
      normalizedText: normalizedText,
      normalizedCandidates: normalizedCandidates,
      primaryIntent: primaryIntent,
      secondaryIntents: secondaryIntents,
      candidateIntents: candidateIntents,
      entities: entities,
      writeIntent: writeIntent,
      negatedActions: negatedActions,
      confirmationIntent: confirmationIntent,
      references: references,
      ambiguity: ambiguity,
      clarificationCandidates: clarificationCandidates,
      parserSource: parserSource ?? this.parserSource,
      parserVersion: parserVersion,
      modelId: modelId,
      modelQuantization: modelQuantization,
      modelHash: modelHash,
      latencyMs: latencyMs ?? this.latencyMs,
      verifierStatus: verifierStatus ?? this.verifierStatus,
      uncertainty: uncertainty ?? this.uncertainty,
      schemaVersion: schemaVersion,
    );
  }

  /// Full local representation. Raw text is deliberately excluded from
  /// [toTelemetryJson], the only representation allowed over the wire.
  Map<String, Object?> toJson() => {
        'schema_version': schemaVersion,
        'raw_text': rawText,
        'normalized_text': normalizedText,
        'normalized_candidates': normalizedCandidates,
        'primary_intent': primaryIntent,
        'secondary_intents': secondaryIntents,
        'candidate_intents': candidateIntents,
        'entities': entities,
        'write_intent': writeIntent,
        'negated_actions': negatedActions,
        'confirmation_intent': confirmationIntent,
        'references': references.map((item) => item.toJson()).toList(),
        'ambiguity': ambiguity.toJson(),
        'clarification_candidates': clarificationCandidates,
        'parser_source': parserSource,
        'parser_version': parserVersion,
        'model_id': modelId,
        'model_quantization': modelQuantization,
        'model_hash': modelHash,
        'latency_ms': latencyMs,
        'verifier_status': verifierStatus.name.toUpperCase(),
        'uncertainty': _uncertaintyWire,
      };

  Map<String, Object?> toTelemetryJson() => {
        'schema_version': schemaVersion,
        'semantic_router_version': semanticRouterVersion,
        'normalizer_version': semanticNormalizerVersion,
        'primary_intent': primaryIntent,
        'secondary_intents': secondaryIntents,
        'candidate_intents': candidateIntents,
        'write_intent': writeIntent,
        'negated_actions': negatedActions,
        'confirmation_intent': confirmationIntent,
        'reference_kinds': references.map((item) => item.kind).toList(),
        'ambiguity_status': ambiguity.statusWire,
        'ambiguity_type': ambiguity.typeWire,
        'parser_source': parserSource,
        'parser_version': parserVersion,
        'model_id': modelId,
        'model_quantization': modelQuantization,
        'model_hash': modelHash,
        'latency_ms': latencyMs,
        'verifier_status': verifierStatus.name.toUpperCase(),
        'uncertainty': _uncertaintyWire,
      };

  String get _uncertaintyWire => switch (uncertainty) {
        SemanticUncertainty.routeConfident => 'ROUTE_CONFIDENT',
        SemanticUncertainty.routeUncertain => 'ROUTE_UNCERTAIN',
        SemanticUncertainty.clarificationRequired => 'CLARIFICATION_REQUIRED',
      };
}
