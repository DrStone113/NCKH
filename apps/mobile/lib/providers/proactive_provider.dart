import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/backend_api_service.dart';

abstract interface class ProactiveApiClient {
  Future<Map<String, dynamic>?> getActiveCheckin({
    required String userId,
    Map<String, dynamic>? userContext,
  });

  Future<Map<String, dynamic>> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    required String userId,
  });

  Future<Map<String, dynamic>> getCheckinSettings({required String userId});

  Future<Map<String, dynamic>> updateCheckinSettings(
    Map<String, dynamic> settings, {
    required String userId,
  });
}

class BackendProactiveApiClient implements ProactiveApiClient {
  BackendProactiveApiClient([BackendApiService? service])
      : _service = service ?? BackendApiService();

  final BackendApiService _service;

  @override
  Future<Map<String, dynamic>?> getActiveCheckin({
    required String userId,
    Map<String, dynamic>? userContext,
  }) {
    return _service.getActiveCheckin(
      userId: userId,
      userContext: userContext,
    );
  }

  @override
  Future<Map<String, dynamic>> getCheckinSettings({required String userId}) {
    return _service.getCheckinSettings(userId: userId);
  }

  @override
  Future<Map<String, dynamic>> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    required String userId,
  }) {
    return _service.respondToCheckin(
      nudgeId: nudgeId,
      selectedOptionId: selectedOptionId,
      responseText: responseText,
      userId: userId,
    );
  }

  @override
  Future<Map<String, dynamic>> updateCheckinSettings(
    Map<String, dynamic> settings, {
    required String userId,
  }) {
    return _service.updateCheckinSettings(settings, userId: userId);
  }
}

class ProactiveProvider with ChangeNotifier {
  ProactiveProvider({ProactiveApiClient? apiService})
      : _apiService = apiService ?? BackendProactiveApiClient();

  final ProactiveApiClient _apiService;

  static const Map<String, bool> defaultCheckinSettings = {
    'enable_proactive': true,
    'water_checkin': true,
    'nutrition_checkin': true,
    'fitness_checkin': true,
    'mood_checkin': true,
  };

  Map<String, dynamic>? _activeNudge;
  Map<String, bool> _checkinSettings = Map.of(defaultCheckinSettings);
  bool _isLoading = false;
  bool _isLoadingSettings = false;
  bool _isSavingSettings = false;
  bool _isDismissed = false;
  String? _settingsUserId;
  String? _lastAiReply;
  String? _error;

  Map<String, dynamic>? get activeNudge => _isDismissed ? null : _activeNudge;
  bool get isLoading => _isLoading;
  bool get isLoadingSettings => _isLoadingSettings;
  bool get isSavingSettings => _isSavingSettings;
  bool get isDismissed => _isDismissed;
  String? get lastAiReply => _lastAiReply;
  String? get error => _error;
  Map<String, bool> get checkinSettings => Map.unmodifiable(_checkinSettings);

  String _preferenceKey(String userId, String setting) {
    return 'checkin_${userId}_$setting';
  }

  Map<String, bool> _normalizeSettings(Map<String, dynamic> raw) {
    return {
      for (final entry in defaultCheckinSettings.entries)
        entry.key:
            raw[entry.key] is bool ? raw[entry.key] as bool : entry.value,
    };
  }

  Future<void> _saveLocalSettings(String userId) async {
    final preferences = await SharedPreferences.getInstance();
    for (final entry in _checkinSettings.entries) {
      await preferences.setBool(
        _preferenceKey(userId, entry.key),
        entry.value,
      );
    }
  }

  Future<void> loadCheckinSettings(
    String userId, {
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh && _settingsUserId == userId && !_isLoadingSettings) {
      return;
    }

    _isLoadingSettings = true;
    _error = null;
    notifyListeners();
    try {
      final preferences = await SharedPreferences.getInstance();
      final hasLocal = preferences.containsKey(
        _preferenceKey(userId, 'enable_proactive'),
      );

      if (hasLocal) {
        _checkinSettings = {
          for (final entry in defaultCheckinSettings.entries)
            entry.key: preferences.getBool(
                  _preferenceKey(userId, entry.key),
                ) ??
                entry.value,
        };
        // Backend hiện giữ cache runtime; đồng bộ lại cài đặt cục bộ mỗi khi
        // app mở để các lựa chọn vẫn có hiệu lực sau khi server restart.
        try {
          await _apiService.updateCheckinSettings(
            _checkinSettings,
            userId: userId,
          );
        } catch (error) {
          debugPrint('⚠️ Chưa đồng bộ được cài đặt check-in: $error');
        }
      } else {
        final remote = await _apiService.getCheckinSettings(userId: userId);
        _checkinSettings = _normalizeSettings(remote);
        await _saveLocalSettings(userId);
      }
      _settingsUserId = userId;
    } catch (error) {
      _checkinSettings = Map.of(defaultCheckinSettings);
      _settingsUserId = null;
      _error = error.toString();
      debugPrint('❌ ProactiveProvider: Error loading settings: $error');
    } finally {
      _isLoadingSettings = false;
      notifyListeners();
    }
  }

  Future<bool> updateCheckinSettings(
    String userId,
    Map<String, bool> settings,
  ) async {
    _isSavingSettings = true;
    _error = null;
    _checkinSettings = _normalizeSettings(settings);
    _settingsUserId = userId;
    notifyListeners();

    try {
      await _saveLocalSettings(userId);
      await _apiService.updateCheckinSettings(
        _checkinSettings,
        userId: userId,
      );
      if (!(_checkinSettings['enable_proactive'] ?? true)) {
        _activeNudge = null;
        _isDismissed = true;
      }
      return true;
    } catch (error) {
      // Local settings remain authoritative and will be re-synced later.
      _error = error.toString();
      debugPrint('❌ ProactiveProvider: Error saving settings: $error');
      return false;
    } finally {
      _isSavingSettings = false;
      notifyListeners();
    }
  }

  /// Load active check-in nudge from backend
  Future<void> loadActiveCheckin(
    String userId, {
    Map<String, dynamic>? userContext,
  }) async {
    await loadCheckinSettings(userId);
    if (!(_checkinSettings['enable_proactive'] ?? true)) {
      _activeNudge = null;
      _isDismissed = true;
      _isLoading = false;
      notifyListeners();
      return;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final nudge = await _apiService.getActiveCheckin(
        userId: userId,
        userContext: userContext,
      );
      _activeNudge = nudge;
      _isDismissed = false;
    } catch (e) {
      _error = e.toString();
      debugPrint('❌ ProactiveProvider: Error loading checkin: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Respond to active check-in
  Future<Map<String, dynamic>?> respondToCheckin({
    required String nudgeId,
    String? selectedOptionId,
    String? responseText,
    String userId = 'default_user',
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await _apiService.respondToCheckin(
        nudgeId: nudgeId,
        selectedOptionId: selectedOptionId,
        responseText: responseText,
        userId: userId,
      );
      _lastAiReply = result['ai_reply'] as String?;
      // Mark as dismissed after responding so card disappears or shows success state
      _isDismissed = true;
      notifyListeners();
      return result;
    } catch (e) {
      _error = e.toString();
      debugPrint('❌ ProactiveProvider: Error responding checkin: $e');
      notifyListeners();
      return null;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Dismiss the current checkin card for this session
  void dismissCheckin() {
    _isDismissed = true;
    notifyListeners();
  }

  /// Clear reply feedback
  void clearReply() {
    _lastAiReply = null;
    notifyListeners();
  }
}
