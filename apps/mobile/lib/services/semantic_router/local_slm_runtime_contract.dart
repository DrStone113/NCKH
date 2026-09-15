class SemanticSlmRequest {
  const SemanticSlmRequest({
    required this.prompt,
    this.maxOutputTokens = 160,
    this.timeout = const Duration(seconds: 12),
  });

  final String prompt;
  final int maxOutputTokens;
  final Duration timeout;
}

class SemanticSlmAvailability {
  const SemanticSlmAvailability({
    required this.available,
    required this.reasonCode,
    this.modelId,
    this.quantization,
    this.modelHash,
  });

  final bool available;
  final String reasonCode;
  final String? modelId;
  final String? quantization;
  final String? modelHash;
}

abstract class SemanticSlmRuntime {
  Future<SemanticSlmAvailability> availability();

  Future<String> infer(SemanticSlmRequest request);

  Future<void> dispose();
}
