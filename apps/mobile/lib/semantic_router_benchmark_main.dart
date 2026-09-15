import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import 'services/semantic_router/semantic_contract.dart';
import 'services/semantic_router/semantic_router.dart';

const _modelPath = String.fromEnvironment('SEMANTIC_ROUTER_MODEL_PATH');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MaterialApp(home: _BenchmarkScreen()));
}
class _BenchmarkScreen extends StatefulWidget {
  const _BenchmarkScreen();

  @override
  State<_BenchmarkScreen> createState() => _BenchmarkScreenState();
}

class _BenchmarkScreenState extends State<_BenchmarkScreen> {
  String _status = 'RUNNING';

  @override
  void initState() {
    super.initState();
    unawaited(_run());
  }

  Future<void> _run() async {
    final router = SemanticRouter(mode: SemanticRouterMode.shadow);
    const inputs = [
      'hom nai con bao nhieu clao',
      'bữa ni ăn món chi được',
      'đổi cái đó',
      'tôi chỉ hỏi thôi đừng ghi cân nặng',
      'sức bền',
      'hom nai con bao nhieu clao',
    ];
    final wallTimes = <int>[];
    final inferenceTimes = <int>[];
    var peakRss = ProcessInfo.currentRss;
    var slmExecuted = false;
    final reasons = <String>[];
    for (final input in inputs) {
      final stopwatch = Stopwatch()..start();
      final observation = await router.analyze(input);
      stopwatch.stop();
      wallTimes.add(stopwatch.elapsedMilliseconds);
      inferenceTimes.add(observation.result?.latencyMs ?? 0);
      slmExecuted = slmExecuted || observation.slmInvoked;
      reasons.add(observation.reasonCode);
      peakRss = peakRss > ProcessInfo.currentRss
          ? peakRss
          : ProcessInfo.currentRss;
    }
    await router.dispose();
    final sortedWarm = wallTimes.skip(1).toList()..sort();
    final model = _modelPath.isEmpty ? null : File(_modelPath);
    final report = {
      'artifact_type': 'ANDROID_DEVICE_MEASUREMENT',
      'semantic_router_version': semanticRouterVersion,
      'slm_actually_executed': slmExecuted,
      'model_file_bytes':
          model != null && await model.exists() ? await model.length() : null,
      'cold_wall_ms': wallTimes.first,
      'warm_wall_ms': wallTimes.skip(1).toList(),
      'warm_median_ms': _percentile(sortedWarm, 0.50),
      'warm_p95_ms': _percentile(sortedWarm, 0.95),
      'reported_inference_ms': inferenceTimes,
      'peak_rss_bytes': peakRss,
      'reason_codes': reasons,
      'tokens_per_second': 'NOT_MEASURED_NOT_MEANINGFUL',
      'battery_thermal': 'NOT_MEASURED',
    };
    final rendered = jsonEncode(report);
    // ignore: avoid_print
    print('SEMANTIC_ROUTER_BENCHMARK=$rendered');
    if (mounted) setState(() => _status = rendered);
  }

  static int? _percentile(List<int> sorted, double percentile) {
    if (sorted.isEmpty) return null;
    final index = ((sorted.length - 1) * percentile).ceil();
    return sorted[index];
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: SelectableText(_status),
          ),
        ),
      );
}
