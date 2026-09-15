import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:llama_flutter_android/llama_flutter_android.dart';

import 'local_slm_runtime_contract.dart';

const _modelPath = String.fromEnvironment('SEMANTIC_ROUTER_MODEL_PATH');
const _expectedModelHash =
    String.fromEnvironment('SEMANTIC_ROUTER_MODEL_SHA256');
const _modelId = String.fromEnvironment(
  'SEMANTIC_ROUTER_MODEL_ID',
  defaultValue: 'Qwen/Qwen3-0.6B-GGUF',
);
const _modelQuantization = String.fromEnvironment(
  'SEMANTIC_ROUTER_MODEL_QUANTIZATION',
  defaultValue: 'Q4_K_M',
);

class AndroidLlamaSemanticSlmRuntime implements SemanticSlmRuntime {
  LlamaController? _controller;
  SemanticSlmAvailability? _cachedAvailability;
  Future<void>? _loading;
  Future<String>? _activeGeneration;
  bool _poisoned = false;

  @override
  Future<SemanticSlmAvailability> availability() async {
    if (_poisoned) {
      return const SemanticSlmAvailability(
        available: false,
        reasonCode: 'RUNTIME_RECOVERY_REQUIRED',
      );
    }
    final cached = _cachedAvailability;
    if (cached != null) return cached;
    if (!Platform.isAndroid) {
      return _cachedAvailability = const SemanticSlmAvailability(
        available: false,
        reasonCode: 'UNSUPPORTED_PLATFORM',
      );
    }
    if (_modelPath.trim().isEmpty || _expectedModelHash.trim().isEmpty) {
      return _cachedAvailability = const SemanticSlmAvailability(
        available: false,
        reasonCode: 'MODEL_CONFIGURATION_MISSING',
      );
    }
    final file = File(_modelPath);
    if (!await file.exists()) {
      return _cachedAvailability = const SemanticSlmAvailability(
        available: false,
        reasonCode: 'MODEL_UNAVAILABLE',
      );
    }
    try {
      final digest = await sha256.bind(file.openRead()).first;
      final actual = digest.toString().toLowerCase();
      if (actual != _expectedModelHash.trim().toLowerCase()) {
        return _cachedAvailability = SemanticSlmAvailability(
          available: false,
          reasonCode: 'CHECKSUM_MISMATCH',
          modelId: _modelId,
          quantization: _modelQuantization,
          modelHash: actual,
        );
      }
      return _cachedAvailability = SemanticSlmAvailability(
        available: true,
        reasonCode: 'AVAILABLE',
        modelId: _modelId,
        quantization: _modelQuantization,
        modelHash: actual,
      );
    } on FileSystemException {
      return _cachedAvailability = const SemanticSlmAvailability(
        available: false,
        reasonCode: 'MODEL_READ_FAILED',
      );
    }
  }

  Future<void> _ensureLoaded() async {
    if (_controller != null) return;
    final inFlight = _loading;
    if (inFlight != null) return inFlight;
    final completer = Completer<void>();
    _loading = completer.future;
    try {
      final state = await availability();
      if (!state.available) throw StateError(state.reasonCode);
      final controller = LlamaController();
      await controller.loadModel(
        modelPath: _modelPath,
        threads: 2,
        contextSize: 1024,
        gpuLayers: 0,
      );
      _controller = controller;
      completer.complete();
    } catch (error, stack) {
      completer.completeError(error, stack);
      rethrow;
    } finally {
      _loading = null;
    }
  }

  @override
  Future<String> infer(SemanticSlmRequest request) async {
    if (_poisoned) throw StateError('RUNTIME_RECOVERY_REQUIRED');
    if (_activeGeneration != null) throw StateError('GENERATION_IN_PROGRESS');
    await _ensureLoaded();
    final controller = _controller!;
    final generation = controller
        .generate(
          prompt: request.prompt,
          maxTokens: request.maxOutputTokens,
          temperature: 0,
          topP: 1,
          topK: 1,
          minP: 0,
          repeatPenalty: 1.1,
          seed: 1,
        )
        .join();
    _activeGeneration = generation;
    generation.then<void>(
      (_) {
        if (identical(_activeGeneration, generation)) {
          _activeGeneration = null;
        }
      },
      onError: (_) {
        if (identical(_activeGeneration, generation)) {
          _activeGeneration = null;
        }
      },
    );
    try {
      return await generation.timeout(request.timeout);
    } on TimeoutException {
      // Future.timeout does not cancel the native generation. Mark this
      // controller unusable, request a stop, and wait for its terminal event
      // before any later dispose can free the underlying model.
      _poisoned = true;
      await controller.stop();
      try {
        await generation.timeout(const Duration(seconds: 60));
      } catch (_) {
        // dispose() below intentionally leaks the native controller rather
        // than freeing memory while a native call could still be executing.
      }
      rethrow;
    } catch (_) {
      _poisoned = true;
      rethrow;
    }
  }

  @override
  Future<void> dispose() async {
    final controller = _controller;
    if (controller == null) return;
    final active = _activeGeneration;
    if (active != null) {
      await controller.stop();
      try {
        await active.timeout(const Duration(seconds: 60));
      } on TimeoutException {
        // Native work is still live. Do not call freeModel: process cleanup is
        // safer than a use-after-free crash in this unsupported condition.
        return;
      } catch (_) {
        // A terminal generation error is settled and safe to dispose.
      }
    }
    _controller = null;
    await controller.dispose();
  }
}

SemanticSlmRuntime createRuntime() => AndroidLlamaSemanticSlmRuntime();
