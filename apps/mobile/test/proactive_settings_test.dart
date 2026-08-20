import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/providers/proactive_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeProactiveApi implements ProactiveApiClient {
  Map<String, dynamic> remoteSettings = {
    'enable_proactive': true,
    'water_checkin': false,
    'nutrition_checkin': true,
    'fitness_checkin': true,
    'mood_checkin': true,
  };
  int activeCalls = 0;
  int updateCalls = 0;

  @override
  Future<Map<String, dynamic>?> getActiveCheckin(
      {required String userId}) async {
    activeCalls++;
    return {'id': 'nudge-1'};
  }

  @override
  Future<Map<String, dynamic>> getCheckinSettings({
    required String userId,
  }) async {
    return Map.of(remoteSettings);
  }

  @override
  Future<Map<String, dynamic>> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    required String userId,
  }) async {
    return {'status': 'ok'};
  }

  @override
  Future<Map<String, dynamic>> updateCheckinSettings(
    Map<String, dynamic> settings, {
    required String userId,
  }) async {
    updateCalls++;
    remoteSettings = Map.of(settings);
    return Map.of(remoteSettings);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('check-in settings persist per user and disable nudge requests',
      () async {
    final api = _FakeProactiveApi();
    final provider = ProactiveProvider(apiService: api);

    await provider.loadCheckinSettings('user-1');
    expect(provider.checkinSettings['water_checkin'], isFalse);

    final updated = Map<String, bool>.of(provider.checkinSettings)
      ..['enable_proactive'] = false
      ..['water_checkin'] = true;
    expect(await provider.updateCheckinSettings('user-1', updated), isTrue);

    await provider.loadActiveCheckin('user-1');
    expect(api.activeCalls, 0);
    expect(provider.activeNudge, isNull);

    final nextApi = _FakeProactiveApi();
    final restored = ProactiveProvider(apiService: nextApi);
    await restored.loadCheckinSettings('user-1');

    expect(restored.checkinSettings['enable_proactive'], isFalse);
    expect(restored.checkinSettings['water_checkin'], isTrue);
    expect(nextApi.updateCalls, 1);
  });
}
