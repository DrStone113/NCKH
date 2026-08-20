import 'dart:async';
import 'dart:collection';

import 'package:characters/characters.dart';

typedef TypewriterChunkCallback = void Function(String chunk);

/// Smooths bursty WebSocket text into short, readable UI updates.
///
/// Some OpenAI-compatible providers buffer SSE events and release hundreds of
/// chunks together. This queue preserves real streaming when chunks arrive
/// slowly, while pacing a burst instead of painting the whole answer at once.
class StreamingTypewriter {
  StreamingTypewriter({
    required this.onChunk,
    required this.onIdle,
    this.interval = const Duration(milliseconds: 18),
    this.batchMultiplier = 1,
  }) : assert(batchMultiplier > 0);

  final TypewriterChunkCallback onChunk;
  final void Function() onIdle;
  final Duration interval;
  final int batchMultiplier;

  final Queue<String> _pendingCharacters = Queue<String>();
  Timer? _timer;
  bool _disposed = false;

  bool get hasPending => _pendingCharacters.isNotEmpty;
  String get pendingText => _pendingCharacters.join();

  void add(String text) {
    if (_disposed || text.isEmpty) return;

    _pendingCharacters.addAll(text.characters);
    if (_timer != null) return;

    // Show the first character immediately. Keep the timer alive for one
    // interval so subsequent WebSocket events in the same burst are coalesced.
    _emitNextBatch();
    _timer = Timer.periodic(interval, _onTick);
  }

  /// Replaces only the text that has not been painted yet.
  ///
  /// Used when the server's final `full_response` contains a suffix that was
  /// not present in preceding token events.
  void replacePending(String text) {
    if (_disposed) return;
    _pendingCharacters
      ..clear()
      ..addAll(text.characters);

    if (_pendingCharacters.isNotEmpty && _timer == null) {
      _emitNextBatch();
      _timer = Timer.periodic(interval, _onTick);
    }
  }

  void _onTick(Timer timer) {
    if (_pendingCharacters.isEmpty) {
      timer.cancel();
      _timer = null;
      onIdle();
      return;
    }
    _emitNextBatch();
  }

  void _emitNextBatch() {
    final count =
        batchSizeForBacklog(_pendingCharacters.length) * batchMultiplier;
    final chunk = StringBuffer();
    for (var i = 0; i < count && _pendingCharacters.isNotEmpty; i++) {
      chunk.write(_pendingCharacters.removeFirst());
    }
    if (chunk.isNotEmpty) onChunk(chunk.toString());
  }

  /// Keeps short answers typewriter-like and catches up on long answers.
  static int batchSizeForBacklog(int backlog) {
    if (backlog > 1200) return 16;
    if (backlog > 600) return 10;
    if (backlog > 240) return 6;
    if (backlog > 80) return 3;
    return 1;
  }

  void clear() {
    _timer?.cancel();
    _timer = null;
    _pendingCharacters.clear();
  }

  void dispose() {
    _disposed = true;
    clear();
  }
}
