/// Freshness and availability semantics for values exposed to the chatbot.
///
/// A value of zero is valid data. Availability is represented only by
/// [DataStatus], never by inspecting the value itself.
enum DataStatus {
  known,
  missing,
  notLoaded,
  error,
  conflict,
  stale,
}

enum WriteStatus { persisted, rejected, error }

enum MealRecordStatus { planned, consumed }

enum ActivePlanStatus { activePlanFound, noActivePlan, readError }

extension DataStatusWireName on DataStatus {
  String get wireName => switch (this) {
        DataStatus.known => 'KNOWN',
        DataStatus.missing => 'MISSING',
        DataStatus.notLoaded => 'NOT_LOADED',
        DataStatus.error => 'ERROR',
        DataStatus.conflict => 'CONFLICT',
        DataStatus.stale => 'STALE',
      };
}

class ConflictMetadata {
  final String reason;
  final Map<String, Object?> candidates;

  const ConflictMetadata({required this.reason, required this.candidates});

  Map<String, Object?> toJson() => {
        'reason': reason,
        'candidates': candidates,
      };
}

/// Typed envelope for every authoritative value sent to the chatbot.
class AppStateValue<T> {
  final T? value;
  final String source;
  final DateTime? observedAt;
  final DataStatus status;
  final ConflictMetadata? conflict;

  const AppStateValue({
    required this.value,
    required this.source,
    required this.observedAt,
    required this.status,
    this.conflict,
  });

  Map<String, Object?> toJson() => {
        'value': value,
        'source': source,
        'observed_at': observedAt?.toUtc().toIso8601String(),
        'status': status.wireName,
        if (conflict != null) 'conflict': conflict!.toJson(),
      };
}

class WriteResult<T> {
  final WriteStatus status;
  final T? value;
  final String? errorCode;

  const WriteResult._(this.status, {this.value, this.errorCode});

  const WriteResult.persisted([T? value])
      : this._(WriteStatus.persisted, value: value);

  const WriteResult.rejected(String errorCode)
      : this._(WriteStatus.rejected, errorCode: errorCode);

  const WriteResult.error(String errorCode)
      : this._(WriteStatus.error, errorCode: errorCode);

  bool get isPersisted => status == WriteStatus.persisted;

  Map<String, Object?> toJson() => {
        'write_status': status.name.toUpperCase(),
        if (value != null) 'value': value,
        if (errorCode != null) 'error_code': errorCode,
      };
}

class ActivePlanReadResult {
  final ActivePlanStatus status;
  final Map<String, dynamic>? plan;
  final String? errorCode;

  const ActivePlanReadResult._(this.status, {this.plan, this.errorCode});

  const ActivePlanReadResult.found(Map<String, dynamic> plan)
      : this._(ActivePlanStatus.activePlanFound, plan: plan);

  const ActivePlanReadResult.none()
      : this._(ActivePlanStatus.noActivePlan);

  const ActivePlanReadResult.error(String errorCode)
      : this._(ActivePlanStatus.readError, errorCode: errorCode);
}
