import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/services/semantic_router/local_slm_runtime.dart';
import 'package:health_app/services/semantic_router/local_slm_runtime_stub.dart';
import 'package:health_app/services/semantic_router/semantic_contract.dart';
import 'package:health_app/services/semantic_router/semantic_router.dart';
import 'package:health_app/services/semantic_router/text_normalizer.dart';

class _FakeRuntime implements SemanticSlmRuntime {
  _FakeRuntime({
    this.output,
    this.available = true,
    this.error,
  });

  final String? output;
  final bool available;
  final Object? error;
  int calls = 0;

  @override
  Future<SemanticSlmAvailability> availability() async =>
      SemanticSlmAvailability(
        available: available,
        reasonCode: available ? 'AVAILABLE' : 'MODEL_UNAVAILABLE',
        modelId: available ? 'Qwen/Qwen3-0.6B-GGUF' : null,
        quantization: available ? 'Q4_K_M' : null,
      );

  @override
  Future<String> infer(SemanticSlmRequest request) async {
    calls++;
    if (error != null) throw error!;
    return output!;
  }

  @override
  Future<void> dispose() async {}
}

String _validOutput({
  String primary = 'WEIGHT_PROGRESS',
  bool writeIntent = false,
}) =>
    '''{
  "primary_intent": "$primary",
  "secondary_intents": [],
  "entities": {},
  "write_intent": $writeIntent,
  "negated_actions": [],
  "confirmation_intent": null,
  "references": [],
  "ambiguity": {"status": "NONE", "type": null},
  "clarification_candidates": []
}''';

void main() {
  group('conservative normalization', () {
    test('preserves raw text and keeps expansions as candidates', () {
      const raw = '  toi nay an j   dc  ';
      final result = const ConservativeVietnameseNormalizer().normalize(raw);

      expect(result.rawText, raw);
      expect(result.normalizedText, 'toi nay an j dc');
      expect(result.candidates, contains('toi nay an gì được'));
      expect(result.transforms.map((item) => item.kind),
          contains('UNAMBIGUOUS_CHAT_TOKEN_CANDIDATE'));
    });

    test('does not overwrite an ambiguous abbreviation', () {
      final result =
          const ConservativeVietnameseNormalizer().normalize('k tao plan');
      expect(result.normalizedText, 'k tao plan');
      expect(result.candidates, contains('không tao plan'));
    });
  });

  group('cascade and verifier', () {
    test('high-confidence deterministic route bypasses the model', () async {
      final runtime = _FakeRuntime(output: _validOutput());
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('Hôm nay còn bao nhiêu calo?');

      expect(runtime.calls, 0);
      expect(observation.result?.primaryIntent, 'DAILY_NUTRITION_STATUS');
      expect(observation.reasonCode, 'DETERMINISTIC_HIGH_CONFIDENCE');
    });

    test('pending confirmation wins and cannot carry a target identity',
        () async {
      final runtime = _FakeRuntime(output: _validOutput());
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('ừ', pendingActionActive: true);

      expect(runtime.calls, 0);
      expect(observation.result?.confirmationIntent, 'AFFIRM');
      expect(observation.reasonCode, 'PENDING_ACTION_AUTHORITATIVE');
      expect(
          observation.toTelemetryJson().toString(), isNot(contains('target')));
    });

    test('model unavailable falls back without failing chat', () async {
      final runtime = _FakeRuntime(available: false);
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('nay quất gì nhỉ');

      expect(runtime.calls, 0);
      expect(observation.reasonCode, 'MODEL_UNAVAILABLE');
      expect(
          observation.result?.verifierStatus, SemanticVerifierStatus.fallback);
    });

    test('invalid JSON output is rejected and falls back', () async {
      final runtime = _FakeRuntime(output: 'not-json');
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('giảm béo in 2 months');

      expect(runtime.calls, 1);
      expect(observation.reasonCode, 'INVALID_STRUCTURED_OUTPUT');
      expect(
          observation.result?.verifierStatus, SemanticVerifierStatus.fallback);
    });

    test('unknown intent is rejected by deterministic verifier', () async {
      final runtime =
          _FakeRuntime(output: _validOutput(primary: 'DO_ANYTHING'));
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('giảm béo in 2 months');

      expect(observation.reasonCode, 'VERIFIER_REJECTED');
      expect(observation.verifierReasons, contains('UNKNOWN_PRIMARY_INTENT'));
    });

    test('inference timeout is a safe fallback', () async {
      final runtime = _FakeRuntime(error: TimeoutException('slow'));
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('giảm béo in 2 months');

      expect(observation.reasonCode, 'INFERENCE_TIMEOUT');
      expect(observation.result, isNotNull);
    });

    test('verified model output remains observation-only', () async {
      final runtime = _FakeRuntime(output: _validOutput());
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: runtime,
      ).analyze('giảm béo in 2 months');

      expect(observation.reasonCode, 'SLM_VERIFIED');
      expect(observation.result?.primaryIntent, 'WEIGHT_PROGRESS');
      expect(observation.mode, SemanticRouterMode.shadow);
    });
  });

  group('hard semantic cases', () {
    test('negated write never becomes a positive write', () async {
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: _FakeRuntime(available: false),
      ).analyze('đừng lưu món này');

      expect(observation.result?.writeIntent, isFalse);
      expect(observation.result?.negatedActions, contains('LOG_MEAL'));
    });

    test('multi-intent preserves a secondary intent', () async {
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: _FakeRuntime(available: false),
      ).analyze('Hôm nay còn bao nhiêu calo và gợi ý bữa tối cho tôi');

      expect(observation.result?.primaryIntent, 'DAILY_NUTRITION_STATUS');
      expect(observation.result?.secondaryIntents,
          contains('MEAL_RECOMMENDATION'));
    });

    test('domain ambiguity is explicit', () async {
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: _FakeRuntime(available: false),
      ).analyze('tôi muốn tăng sức bền');

      expect(observation.result?.ambiguity.status,
          SemanticAmbiguityStatus.ambiguous);
      expect(observation.result?.ambiguity.type, SemanticAmbiguityType.domain);
    });

    test('reference ambiguity is explicit', () async {
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: _FakeRuntime(available: false),
      ).analyze('cái thứ hai');

      expect(observation.result?.references.single.ordinal, 2);
      expect(
          observation.result?.ambiguity.type, SemanticAmbiguityType.reference);
    });

    test('telemetry excludes raw and normalized text', () async {
      const secretText = 'tôi dị ứng tôm và email a@b.com';
      final observation = await SemanticRouter(
        mode: SemanticRouterMode.shadow,
        runtime: _FakeRuntime(available: false),
      ).analyze(secretText);
      final wire = observation.toTelemetryJson().toString();

      expect(wire, isNot(contains(secretText)));
      expect(wire, isNot(contains('a@b.com')));
      expect(wire, isNot(contains('normalized_text')));
      expect(wire, contains('raw_length'));
    });

    test('unsupported runtime reports fallback capability', () async {
      final availability = await UnsupportedSemanticSlmRuntime().availability();
      expect(availability.available, isFalse);
      expect(availability.reasonCode, 'UNSUPPORTED_PLATFORM');
    });
  });
}
