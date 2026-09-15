import 'local_slm_runtime_contract.dart';

class UnsupportedSemanticSlmRuntime implements SemanticSlmRuntime {
  @override
  Future<SemanticSlmAvailability> availability() async =>
      const SemanticSlmAvailability(
        available: false,
        reasonCode: 'UNSUPPORTED_PLATFORM',
      );

  @override
  Future<String> infer(SemanticSlmRequest request) {
    throw UnsupportedError('On-device SLM is unavailable on this platform.');
  }

  @override
  Future<void> dispose() async {}
}

SemanticSlmRuntime createRuntime() => UnsupportedSemanticSlmRuntime();
