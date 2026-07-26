import 'package:flutter/foundation.dart';
import '../services/backend_api_service.dart';

class ProactiveProvider with ChangeNotifier {
  final BackendApiService _apiService = BackendApiService();

  Map<String, dynamic>? _activeNudge;
  bool _isLoading = false;
  bool _isDismissed = false;
  String? _lastAiReply;
  String? _error;

  Map<String, dynamic>? get activeNudge => _isDismissed ? null : _activeNudge;
  bool get isLoading => _isLoading;
  bool get isDismissed => _isDismissed;
  String? get lastAiReply => _lastAiReply;
  String? get error => _error;

  /// Load active check-in nudge from backend
  Future<void> loadActiveCheckin(String userId) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final nudge = await _apiService.getActiveCheckin(userId: userId);
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
