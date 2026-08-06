import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import '../models/lifestyle_model.dart';

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

  LifestyleLog get todayLog => _todayLog;
  List<LifestyleReminder> get reminders => _reminders;
  bool get isLoading => _isLoading;

  double get todayWaterMl => _todayLog.waterIntakeMl;
  int get todayMoodScore => _todayLog.moodScore;
  String get todayMoodLabel => _todayLog.moodLabel;
  double get todaySleepHours => _todayLog.sleepHours;
  int get todayStressScore => _todayLog.stressScore;

  /// Load thông tin lifestyle hôm nay của user
  Future<void> loadTodayLogs(String userId) async {
    if (userId.isEmpty || userId == 'demo') {
      _initDemoData(userId);
      return;
    }

    _isLoading = true;
    notifyListeners();

    try {
      final todayStr = DateTime.now().toIso8601String().substring(0, 10);
      final docId = '${userId}_$todayStr';

      final doc = await _firestore.collection('lifestyle_logs').doc(docId).get();
      if (doc.exists && doc.data() != null) {
        _todayLog = LifestyleLog.fromMap(doc.data()!);
      } else {
        _todayLog = LifestyleLog(
          id: docId,
          userId: userId,
          date: DateTime.now(),
        );
      }

      // Load reminders
      final reminderSnapshot = await _firestore
          .collection('lifestyle_reminders')
          .where('userId', isEqualTo: userId)
          .get();

      _reminders = reminderSnapshot.docs
          .map((d) => LifestyleReminder.fromMap(d.data()))
          .toList();

      if (_reminders.isEmpty) {
        _initDefaultReminders(userId);
      }
    } catch (e) {
      debugPrint('❌ Error loading lifestyle logs: $e');
      _initDemoData(userId);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Ghi nhận tâm trạng (Mood Check-in)
  Future<void> logMood(String userId, int score, String label, {String notes = ''}) async {
    final updated = _todayLog.copyWith(
      moodScore: score,
      moodLabel: label,
      notes: notes.isNotEmpty ? notes : _todayLog.notes,
    );
    _todayLog = updated;
    notifyListeners();
    await _saveTodayLog(userId);
  }

  /// Ghi nhận giấc ngủ & độ stress
  Future<void> logSleepAndStress(String userId, double hours, int stressScore) async {
    final updated = _todayLog.copyWith(
      sleepHours: hours,
      stressScore: stressScore,
    );
    _todayLog = updated;
    notifyListeners();
    await _saveTodayLog(userId);
  }

  /// Ghi nhận lượng nước uống (ml)
  Future<void> addWater(String userId, double amountMl) async {
    final newTotal = _todayLog.waterIntakeMl + amountMl;
    final updated = _todayLog.copyWith(waterIntakeMl: newTotal);
    _todayLog = updated;
    notifyListeners();
    await _saveTodayLog(userId);
  }

  /// Thêm nhắc nhở mới
  Future<void> addReminder(String userId, LifestyleReminder reminder) async {
    _reminders.add(reminder);
    notifyListeners();

    if (userId.isNotEmpty && userId != 'demo') {
      try {
        await _firestore
            .collection('lifestyle_reminders')
            .doc(reminder.id)
            .set(reminder.toMap());
      } catch (e) {
        debugPrint('❌ Error adding reminder: $e');
      }
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
    if (userId.isEmpty || userId == 'demo') return;
    try {
      final todayStr = DateTime.now().toIso8601String().substring(0, 10);
      final docId = '${userId}_$todayStr';
      await _firestore
          .collection('lifestyle_logs')
          .doc(docId)
          .set(_todayLog.toMap(), SetOptions(merge: true));
      debugPrint('✅ Lifestyle log saved for $docId');
    } catch (e) {
      debugPrint('❌ Error saving lifestyle log: $e');
    }
  }

  void _initDemoData(String userId) {
    _todayLog = LifestyleLog(
      id: 'demo_log',
      userId: userId.isEmpty ? 'demo' : userId,
      date: DateTime.now(),
      moodScore: 4,
      moodLabel: 'Hào hứng',
      sleepHours: 7.5,
      stressScore: 2,
      waterIntakeMl: 1500,
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
