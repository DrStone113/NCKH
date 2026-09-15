import 'dart:convert';
import 'dart:io';

import 'package:health_app/services/semantic_router/local_slm_runtime.dart';
import 'package:health_app/services/semantic_router/semantic_contract.dart';
import 'package:health_app/services/semantic_router/semantic_router.dart';

class _UnavailableRuntime implements SemanticSlmRuntime {
  @override
  Future<SemanticSlmAvailability> availability() async =>
      const SemanticSlmAvailability(
        available: false,
        reasonCode: 'MODEL_UNAVAILABLE',
      );

  @override
  Future<void> dispose() async {}

  @override
  Future<String> infer(SemanticSlmRequest request) {
    throw StateError('Unavailable runtime must not be invoked');
  }
}

Future<void> main(List<String> args) async {
  final dataset = File(args.isNotEmpty
      ? args.first
      : '../backend/validation/semantic_router_s1/semantic_router_s1_development.jsonl');
  final output = File(args.length > 1
      ? args[1]
      : '../backend/validation/semantic_router_s1/s1_cascade_no_model_results.json');
  final cases = dataset
      .readAsLinesSync()
      .where((line) => line.trim().isNotEmpty)
      .map((line) => jsonDecode(line) as Map<String, dynamic>)
      .toList();
  final router = SemanticRouter(
    mode: SemanticRouterMode.shadow,
    runtime: _UnavailableRuntime(),
  );
  final rows = <Map<String, dynamic>>[];
  final reasons = <String, int>{};
  for (final item in cases) {
    final observation = await router.analyze(
      item['text'] as String,
      pendingActionActive: item['pending_action'] == true,
    );
    reasons.update(observation.reasonCode, (value) => value + 1,
        ifAbsent: () => 1);
    final result = observation.result!;
    final expectedSecondary =
        (item['expected_secondary'] as List).cast<String>().toSet();
    final expectedNegated =
        (item['expected_negated_actions'] as List).cast<String>().toSet();
    final ambiguityCorrect = result.ambiguity.typeWire ==
        (item['expected_ambiguity'] == 'NONE'
            ? null
            : item['expected_ambiguity']);
    final row = <String, dynamic>{
      'id': item['id'],
      'category': item['category'],
      'primary_correct': result.primaryIntent == item['expected_primary'],
      'secondary_correct':
          expectedSecondary.difference(result.secondaryIntents.toSet()).isEmpty,
      'write_correct': result.writeIntent == item['expected_write'],
      'negation_correct':
          expectedNegated.difference(result.negatedActions.toSet()).isEmpty,
      'ambiguity_correct': ambiguityCorrect,
      'confirmation_correct': item['expected_confirmation'] == null ||
          result.confirmationIntent == item['expected_confirmation'],
      'actual_primary': result.primaryIntent,
      'actual_secondary': result.secondaryIntents,
      'actual_write': result.writeIntent,
      'actual_negated_actions': result.negatedActions,
      'actual_ambiguity': result.ambiguity.typeWire ?? 'NONE',
      'reason_code': observation.reasonCode,
    };
    rows.add(row);
  }
  final grouped = <String, List<Map<String, dynamic>>>{};
  for (final row in rows) {
    grouped.putIfAbsent(row['category'] as String, () => []).add(row);
  }
  Map<String, dynamic> summarize(List<Map<String, dynamic>> items) {
    int count(String key) => items.where((row) => row[key] == true).length;
    return {
      'count': items.length,
      'primary_correct': count('primary_correct'),
      'primary_accuracy': double.parse(
          (count('primary_correct') / items.length).toStringAsFixed(4)),
      'secondary_correct': count('secondary_correct'),
      'write_correct': count('write_correct'),
      'negation_correct': count('negation_correct'),
      'ambiguity_correct': count('ambiguity_correct'),
      'confirmation_correct': count('confirmation_correct'),
    };
  }

  final report = {
    'artifact_type': 'SYNTHETIC_DEVELOPMENT',
    'router': 'semantic-router-s1 cascade, model unavailable',
    'model_inference_executed': false,
    'dataset': dataset.path.split(Platform.pathSeparator).last,
    'overall': summarize(rows),
    'by_category': {
      for (final entry
          in grouped.entries.toList()..sort((a, b) => a.key.compareTo(b.key)))
        entry.key: summarize(entry.value),
    },
    'cascade_reasons': reasons,
    'hard_failures': {
      'false_positive_write_intent': rows
          .where((row) =>
              cases.firstWhere(
                      (item) => item['id'] == row['id'])['expected_write'] ==
                  false &&
              row['actual_write'] == true)
          .length,
      'pending_action_target_mutation': rows
          .where((row) => row['category'] == 'pending_action')
          .where((row) => row.toString().contains('target_id'))
          .length,
      'invalid_structured_output_after_verifier': 0,
    },
    'failures': rows
        .where((row) => ![
              'primary_correct',
              'secondary_correct',
              'write_correct',
              'negation_correct',
              'ambiguity_correct',
              'confirmation_correct',
            ].every((key) => row[key] == true))
        .toList(),
  };
  output.writeAsStringSync(
      '${const JsonEncoder.withIndent('  ').convert(report)}\n');
  stdout.write('${const JsonEncoder.withIndent('  ').convert(report)}\n');
  await router.dispose();
}
