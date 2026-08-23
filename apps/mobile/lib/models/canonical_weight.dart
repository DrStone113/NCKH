import 'app_state_value.dart';
import 'health_models.dart';

/// Weight-history measurements take precedence because they carry a specific
/// measurement timestamp. Profile weight is the fallback when history is empty.
abstract final class CanonicalWeightResolver {
  static AppStateValue<double> resolve({
    required double? profileWeight,
    required BodyMetrics? latestMeasurement,
  }) {
    if (latestMeasurement == null && profileWeight == null) {
      return const AppStateValue<double>(
        value: null,
        source: 'none',
        observedAt: null,
        status: DataStatus.missing,
      );
    }

    if (latestMeasurement == null) {
      return AppStateValue<double>(
        value: profileWeight,
        source: 'profile.current_weight',
        observedAt: null,
        status: DataStatus.known,
      );
    }

    final conflict = profileWeight != null &&
        (profileWeight - latestMeasurement.weight).abs() > 0.05;
    return AppStateValue<double>(
      value: latestMeasurement.weight,
      source: 'weight_history.latest_measurement',
      observedAt: latestMeasurement.recordedAt,
      status: conflict ? DataStatus.conflict : DataStatus.known,
      conflict: conflict
          ? ConflictMetadata(
              reason: 'PROFILE_WEIGHT_DIFFERS_FROM_LATEST_MEASUREMENT',
              candidates: {
                'profile.current_weight': profileWeight,
                'weight_history.latest_measurement': latestMeasurement.weight,
              },
            )
          : null,
    );
  }
}
