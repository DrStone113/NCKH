import 'package:flutter/material.dart';

/// E4 card: prescriptions are displayed exactly as delivered by the backend.
/// Actual observations are optional fields and are never prefilled from target
/// dosage or an energy estimate.
class PersonalizedWorkoutCard extends StatefulWidget {
  final Map<String, dynamic> workout;
  final Future<void> Function()? onSave;
  final Future<void> Function(String status, String pain,
          List<Map<String, dynamic>> actualExercises)?
      onLog;
  final void Function(String canonicalExerciseId)? onSubstitute;

  const PersonalizedWorkoutCard({
    super.key,
    required this.workout,
    this.onSave,
    this.onLog,
    this.onSubstitute,
  });

  @override
  State<PersonalizedWorkoutCard> createState() => _PersonalizedWorkoutCardState();
}

class _PersonalizedWorkoutCardState extends State<PersonalizedWorkoutCard> {
  final Map<String, TextEditingController> _reps = {};
  final Map<String, TextEditingController> _loads = {};
  String _pain = 'UNKNOWN';
  bool _writing = false;

  @override
  void dispose() {
    for (final controller in [..._reps.values, ..._loads.values]) {
      controller.dispose();
    }
    super.dispose();
  }

  TextEditingController _controller(
      Map<String, TextEditingController> values, String id) =>
      values.putIfAbsent(id, TextEditingController.new);

  Future<void> _save() async {
    if (widget.onSave == null) return;
    setState(() => _writing = true);
    try {
      await widget.onSave!();
    } finally {
      if (mounted) setState(() => _writing = false);
    }
  }

  Future<void> _log(String status) async {
    if (widget.onLog == null) return;
    final exercises = <Map<String, dynamic>>[];
    for (final raw in (widget.workout['exercises'] as List<dynamic>? ?? const [])) {
      if (raw is! Map) continue;
      final item = Map<String, dynamic>.from(raw);
      final id = item['canonical_exercise_id'] as String?;
      if (id == null) continue;
      final reps = int.tryParse(_controller(_reps, id).text.trim());
      final load = double.tryParse(_controller(_loads, id).text.trim());
      final set = <String, dynamic>{'set_index': 1};
      if (reps != null) set['actual_reps'] = reps;
      if (load != null) set['load_kg'] = load;
      if (set.length > 1) {
        exercises.add({'canonical_exercise_id': id, 'sets': [set]});
      }
    }
    setState(() => _writing = true);
    try {
      await widget.onLog!(status, _pain, exercises);
    } finally {
      if (mounted) setState(() => _writing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final exercises = widget.workout['exercises'] as List<dynamic>? ?? const [];
    final energy = widget.workout['energy_estimate'];
    final energyValue = energy is Map ? energy['estimated_energy_expenditure'] : null;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Buổi tập cá nhân hóa',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          if (widget.workout['estimated_duration_minutes'] != null)
            Text('Ước tính thời lượng: ${widget.workout['estimated_duration_minutes']} phút'),
          if (energyValue is num)
            Text('Năng lượng ước tính: ${energyValue.toStringAsFixed(0)} kcal (không phải số đo)'),
          const SizedBox(height: 8),
          for (final raw in exercises)
            if (raw is Map)
              _exerciseRow(Map<String, dynamic>.from(raw)),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _pain,
            decoration: const InputDecoration(labelText: 'Đau/khó chịu'),
            items: const [
              DropdownMenuItem(value: 'UNKNOWN', child: Text('Chưa ghi nhận')),
              DropdownMenuItem(value: 'NO', child: Text('Không')),
              DropdownMenuItem(value: 'YES', child: Text('Có')),
            ],
            onChanged: _writing ? null : (value) => setState(() => _pain = value ?? 'UNKNOWN'),
          ),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 6, children: [
            if (widget.onSave != null)
              OutlinedButton(onPressed: _writing ? null : _save, child: const Text('Lưu kế hoạch')),
            if (widget.onLog != null)
              FilledButton(onPressed: _writing ? null : () => _log('COMPLETED'), child: const Text('Hoàn thành')),
            if (widget.onLog != null)
              TextButton(onPressed: _writing ? null : () => _log('PARTIALLY_COMPLETED'), child: const Text('Tập một phần')),
          ]),
        ]),
      ),
    );
  }

  Widget _exerciseRow(Map<String, dynamic> exercise) {
    final id = exercise['canonical_exercise_id'] as String? ?? '';
    final reps = exercise['rep_range'];
    final rest = exercise['rest_range_seconds'];
    final rir = exercise['effort_target_rir'];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(exercise['display_name']?.toString() ?? id,
            style: const TextStyle(fontWeight: FontWeight.w600)),
        Text('${exercise['sets']} hiệp • ${reps ?? 'theo chính sách'} lần • nghỉ ${rest ?? '?'} giây'),
        if (rir != null) Text('Mức gắng sức: còn ${rir[0]}–${rir[1]} RIR'),
        Text('Tiến trình: ${exercise['progression_status'] ?? 'UNKNOWN'}'),
        Row(children: [
          Expanded(child: TextField(
            controller: _controller(_reps, id),
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Số lần thực tế (tuỳ chọn)'),
          )),
          const SizedBox(width: 8),
          Expanded(child: TextField(
            controller: _controller(_loads, id),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Tải kg (tuỳ chọn)'),
          )),
        ]),
        if (widget.onSubstitute != null)
          TextButton(onPressed: () => widget.onSubstitute!(id), child: const Text('Đổi bài')),
      ]),
    );
  }
}
