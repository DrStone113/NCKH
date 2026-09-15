import 'semantic_contract.dart';

class SemanticVerification {
  const SemanticVerification({required this.valid, required this.reasonCodes});

  final bool valid;
  final List<String> reasonCodes;
}

class SemanticResultVerifier {
  const SemanticResultVerifier();

  SemanticVerification verify(
    SemanticParseResult result, {
    Set<String> candidateIntents = const {},
    bool pendingActionActive = false,
  }) {
    final reasons = <String>[];
    if (result.schemaVersion != semanticSchemaVersion) {
      reasons.add('SCHEMA_VERSION_MISMATCH');
    }
    if (!supportedSemanticIntents.contains(result.primaryIntent)) {
      reasons.add('UNKNOWN_PRIMARY_INTENT');
    }
    if (result.secondaryIntents
        .any((intent) => !supportedSemanticIntents.contains(intent))) {
      reasons.add('UNKNOWN_SECONDARY_INTENT');
    }
    if (result.negatedActions
        .any((action) => !supportedSemanticActions.contains(action))) {
      reasons.add('UNKNOWN_NEGATED_ACTION');
    }
    if (result.writeIntent && result.negatedActions.isNotEmpty) {
      reasons.add('NEGATED_WRITE_CONFLICT');
    }
    if (result.writeIntent &&
        !const {
          'APP_ACTION',
          'PLAN_MANAGEMENT',
          'PROFILE_OR_CONSTRAINT_UPDATE',
        }.contains(result.primaryIntent)) {
      reasons.add('WRITE_INTENT_DOMAIN_MISMATCH');
    }
    if (candidateIntents.isNotEmpty &&
        result.primaryIntent != 'SMALLTALK_OR_OTHER' &&
        !candidateIntents.contains(result.primaryIntent)) {
      reasons.add('PRIMARY_OUTSIDE_CANDIDATES');
    }
    if (result.ambiguity.status == SemanticAmbiguityStatus.none &&
        result.ambiguity.type != null) {
      reasons.add('AMBIGUITY_TYPE_WITH_NONE');
    }
    if (result.ambiguity.status == SemanticAmbiguityStatus.ambiguous &&
        result.ambiguity.type == null) {
      reasons.add('AMBIGUITY_TYPE_MISSING');
    }
    if (pendingActionActive &&
        result.confirmationIntent != null &&
        !const {'AFFIRM', 'REJECT', 'CLARIFY'}
            .contains(result.confirmationIntent)) {
      reasons.add('INVALID_CONFIRMATION_INTENT');
    }
    return SemanticVerification(valid: reasons.isEmpty, reasonCodes: reasons);
  }
}
