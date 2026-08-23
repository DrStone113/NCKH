import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import '../models/lifestyle_model.dart';
import '../models/app_state_value.dart';

/// Provider quản lý Module 3: Sức khỏe tinh thần & Lifestyle
class LifestyleProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;

  LifestyleLog _todayLog = LifestyleLog(
    id: '',
    userId: '',
    date: DateTime.now(),
  );

  List<LifestyleReminder> _reminders = [];
  bool _isLoading = false;
  DataStatus _loadStatus = DataStatus.notLoaded;
  DateTime? _observedAt;

  LifestyleLog get todayLog => _todayLog;
  List<LifestyleReminder> get reminders => _reminders;
  bool get isLoading => _isLoading;
  DataStatus get loadStatus => _loadStatus;
  DateTime? get observedAt => _observedAt;

  double get todayWaterMl => _todayLog.waterIntakeMl;
  int get todayMoodScore => _todayLog.moodScore;
  String get todayMoodLabel => _todayLog.moodLabel;
  double get todaySleepHours => _todayLog.sleepHours;
  int get todayStressScore => _todayLog.stressScore;

  /// Load thông tin lifestyle hôm nay của user
  Future<void> loadTodayLogs(String userId) async {
    if (userId.isEmpty || userId == 'demo') {
      _initEmptyData(userId);
      _loadStatus = DataStatus.notLoaded;
      _observedAt = null;
      notifyListeners();
      return;
    }

    _isLoading = true;
    notifyListeners();

    try {
      final todayStr = DateTime.now().toIso8601String().substring(0, 10);
      final docId = '${userId}_$todayStr';

      final doc = await _firestore
          .collection('lifestyle_logs')
          .doc(docId)
          .get(const GetOptions(source: Source.server));
      if (doc.exists && doc.data() != null) {
        _todayLog = LifestyleLog.fromMap(doc.data()!);
      } else {
        _todayLog = LifestyleLog(
          id: docId,
          userId: userId,
          date: DateTime.now(),
        );
      }
      _loadStatus = DataStatus.known;
      _observedAt = DateTime.now();

      // Load reminders
      final reminderSnapshot = await _firestore
          .collection('lifestyle_reminders')
          .where('userId', isEqualTo: userId)
          .get(const GetOptions(source: Source.server));

      _reminders = reminderSnapshot.docs
          .map((d) => LifestyleReminder.fromMap(d.data()))
          .toList();

      if (_reminders.isEmpty) {
        _initDefaultReminders(userId);
      }
    } catch (e) {
      debugPrint('❌ Error loading lifestyle logs: $e');
      _todayLog = LifestyleLog(
        id: '',
        userId: userId,
        date: DateTime.now(),
      );
      _loadStatus = DataStatus.error;
      _observedAt = null;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Ghi nhận tâm trạng (Mood Check-in)
  Future<WriteResult<LifestyleLog>> logMood(
    String userId,
    int score,
    String label, {
    String notes = '',
  }) async {
    if (userId.isEmpty || userId == 'demo' || score < 1 || score > 5) {
      return const WriteResult.rejected('INVALID_LIFESTYLE_WRITE');
    }
    final previous = _todayLog;
    var updated = _todayLog.copyWith(
      moodScore: score,
      moodLabel: label,
    );
    if (notes.isNotEmpty) updated = updated.copyWith(notes: notes);
    _todayLog = updated;
    notifyListeners();
    try {
      await _saveTodayLog(userId);
      _loadStatus = DataStatus.known;
      _observedAt = DateTime.now();
      return WriteResult.persisted(updated);
    } catch (e) {
      _todayLog = previous;
      notifyListeners();
      return const WriteResult.error('LIFESTYLE_PERSISTENCE_ERROR');
    }
  }

  /// Ghi nhận giấc ngủ & độ stress
  Future<WriteResult<LifestyleLog>> logSleepAndStress(
    String userId,
    double hours,
    int stressScore,
  ) async {
    if (userId.isEmpty ||
        userId == 'demo' ||
        hours < 0 ||
        hours > 24 ||
        stressScore < 1 ||
        stressScore > 5) {
      return const WriteResult.rejected('INVALID_LIFESTYLE_WRITE');
    }
    final previous = _todayLog;
    final updated = _todayLog.copyWith(
      sleepHours: hours,
      stressScore: stressScore,
    );
    _todayLog = updated;
    notifyListeners();
    try {
      await _saveTodayLog(userId);
      _loadStatus = DataStatus.known;
      _observedAt = DateTime.now();
      return WriteResult.persisted(updated);
    } catch (e) {
      _todayLog = previous;
      notifyListeners();
      return const WriteResult.error('LIFESTYLE_PERSISTENCE_ERROR');
    }
  }

  /// Ghi nhận lượng nước uống (ml)
  Future<WriteResult<LifestyleLog>> addWater(
    String userId,
    double amountMl,
  ) async {
    if (userId.isEmpty || userId == 'demo' || amountMl <= 0) {
      return const WriteResult.rejected('INVALID_LIFESTYLE_WRITE');
    }
    final previous = _todayLog;
    final newTotal = _todayLog.waterIntakeMl + amountMl;
    final updated = _todayLog.copyWith(waterIntakeMl: newTotal);
    _todayLog = updated;
    notifyListeners();
    try {
      await _saveTodayLog(userId);
      _loadStatus = DataStatus.known;
      _observedAt = DateTime.now();
      return WriteResult.persisted(updated);
    } catch (e) {
      _todayLog = previous;
      notifyListeners();
      return const WriteResult.error('LIFESTYLE_PERSISTENCE_ERROR');
    }
  }

  /// Thêm nhắc nhở mới
  Future<WriteResult<LifestyleReminder>> addReminder(
    String userId,
    LifestyleReminder reminder,
  ) async {
    if (userId.isEmpty || userId == 'demo') {
      return const WriteResult.rejected('REMINDER_PERSISTENCE_UNAVAILABLE');
    }
    _reminders.add(reminder);
    notifyListeners();

    try {
      await _firestore
          .collection('lifestyle_reminders')
          .doc(reminder.id)
          .set(reminder.toMap());
      return WriteResult.persisted(reminder);
    } catch (e) {
      _reminders.removeWhere((item) => item.id == reminder.id);
      notifyListeners();
      debugPrint('❌ Error adding reminder: $e');
      return const WriteResult.error('REMINDER_PERSISTENCE_ERROR');
    }
  }

  /// Bật/tắt nhắc nhở
  Future<void> toggleReminder(String reminderId) async {
    final index = _reminders.indexWhere((r) => r.id == reminderId);
    if (index != -1) {
      final old = _reminders[index];
      final updated = LifestyleReminder(
        id: old.id,
        userId: old.userId,
        title: old.title,
        type: old.type,
        time: old.time,
        isActive: !old.isActive,
        note: old.note,
      );
      _reminders[index] = updated;
      notifyListeners();

      if (old.userId.isNotEmpty && old.userId != 'demo') {
        try {
          await _firestore
              .collection('lifestyle_reminders')
              .doc(reminderId)
              .update({'isActive': updated.isActive});
        } catch (e) {
          debugPrint('❌ Error toggling reminder: $e');
        }
      }
    }
  }

  /// Lưu log ngày hôm nay vào Firestore
  Future<void> _saveTodayLog(String userId) async {
    final todayStr = DateTime.now().toIso8601String().substring(0, 10);
    final docId = '${userId}_$todayStr';
    await _firestore
        .collection('lifestyle_logs')
        .doc(docId)
        .set(_todayLog.toMap(), SetOptions(merge: true));
    debugPrint('✅ Lifestyle log saved for $docId');
  }

  void _initEmptyData(String userId) {
    _todayLog = LifestyleLog(
      id: 'local_empty_log',
      userId: userId.isEmpty ? 'demo' : userId,
      date: DateTime.now(),
    );
    _initDefaultReminders(userId.isEmpty ? 'demo' : userId);
  }

  void _initDefaultReminders(String userId) {
    _reminders = [
      LifestyleReminder(
        id: 'rem_1',
        userId: userId,
        title: 'Uống nước buổi sáng',
        type: 'water',
        time: '08:00',
        isActive: true,
      ),
      LifestyleReminder(
        id: 'rem_2',
        userId: userId,
        title: 'Nghỉ ngơi & Vận động nhẹ',
        type: 'exercise',
        time: '14:30',
        isActive: true,
      ),
      LifestyleReminder(
        id: 'rem_3',
        userId: userId,
        title: 'Check-in tâm trạng & Giấc ngủ',
        type: 'mood_checkin',
        time: '21:30',
        isActive: true,
      ),
    ];
  }
}
