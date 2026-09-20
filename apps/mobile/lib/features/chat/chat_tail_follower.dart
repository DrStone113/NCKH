import 'dart:math' as math;

import 'package:flutter/widgets.dart';

/// Keeps a growing chat transcript aligned with its real bottom extent.
///
/// Streaming text, structured cards and a changing composer/footer can update
/// the scroll extent over several consecutive frames. A single `animateTo`
/// targets the old extent and can therefore leave the newest response clipped.
/// This coordinator coalesces requests and corrects the position after layout
/// has settled, without starting competing animations for every streamed chunk.
class ChatTailFollower {
  ChatTailFollower(
    this.controller, {
    this.defaultSettleFrames = 3,
  }) : assert(defaultSettleFrames > 0);

  final ScrollController controller;
  final int defaultSettleFrames;

  bool _disposed = false;
  bool _frameScheduled = false;
  int _remainingPasses = 0;

  void request({int? settleFrames}) {
    if (_disposed) return;
    final requestedPasses = math.max(1, settleFrames ?? defaultSettleFrames);
    _remainingPasses = math.max(_remainingPasses, requestedPasses);
    _scheduleFrame();
  }

  void _scheduleFrame() {
    if (_disposed || _frameScheduled || _remainingPasses <= 0) return;
    _frameScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _frameScheduled = false;
      if (_disposed) return;

      if (controller.hasClients) {
        final position = controller.position;
        if (position.hasContentDimensions) {
          final target = position.maxScrollExtent;
          if ((target - position.pixels).abs() > 0.5) {
            controller.jumpTo(target);
          }
        }
      }

      _remainingPasses -= 1;
      _scheduleFrame();
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void dispose() {
    _disposed = true;
    _remainingPasses = 0;
  }
}
