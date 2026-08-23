import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/health_models.dart';
import '../constants/firestore_collections.dart';
import '../models/app_state_value.dart';

class HealthProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;

  List<BodyMetrics> _weightHistory = [];
  double _todayWaterIntake = 0;
  DataStatus _weightHistoryStatus = DataStatus.notLoaded;
  DateTime? _weightHistoryObservedAt;
  DataStatus _waterStatus = DataStatus.notLoaded;
  DateTime? _waterObservedAt;

  List<BodyMetrics> get weightHistory => _weightHistory;
  double get todayWaterIntake => _todayWaterIntake;
  DataStatus get weightHistoryStatus => _weightHistoryStatus;
  DateTime? get weightHistoryObservedAt => _weightHistoryObservedAt;
  DataStatus get waterStatus => _waterStatus;
  DateTime? get waterObservedAt => _waterObservedAt;

  Future<bool> loadWeightHistory(String userId) async {
    if (userId == 'demo') {
      _weightHistoryStatus = DataStatus.notLoaded;
      _weightHistoryObservedAt = null;
      return false;
    }
    try {
      QuerySnapshot snapshot = await _firestore
          .collection(FirestoreCollections.bodyMetrics)
          .where('userId', isEqualTo: userId)
          .orderBy('recordedAt', descending: true)
          .limit(30)
          .get(const GetOptions(source: Source.server));

      _weightHistory = snapshot.docs
          .map((doc) => BodyMetrics.fromMap(doc.data() as Map<String, dynamic>))
          .toList()
          .reversed
          .toList();
      _weightHistoryStatus = DataStatus.known;
      _weightHistoryObservedAt = DateTime.now();
      notifyListeners();
      return true;
    } catch (e) {
      _weightHistoryStatus = DataStatus.error;
      return false;
    }
  }

  /// Ghi một bản ghi cân nặng mới.
  ///
  /// Trả về `true` khi đã lưu thành công. Người gọi PHẢI tôn trọng giá trị trả
  /// về: chatbot dùng hàm này qua tool `log_weight`, và báo "đã ghi" trong khi
  /// thực tế chưa lưu là kiểu lỗi tệ nhất — người dùng tin là xong rồi.
  ///
  /// Ghi cùng shape với `UserProvider.updateWeight` để `BodyMetrics.fromMap`
  /// đọc được cả hai nguồn.
  Future<bool> addBodyMetrics({
    required String userId,
    required double weight,
    required double bmi,
    DateTime? recordedAt,
  }) async {
    if (userId.isEmpty) return false;
    final timestamp = recordedAt ?? DateTime.now();

    // Demo has no durable store. An in-memory update must not be reported as a
    // persisted health measurement.
    if (userId == 'demo') {
      return false;
    }

    try {
      final doc = await _firestore.collection(FirestoreCollections.bodyMetrics).add({
        'userId': userId,
        'weight': weight,
        'bmi': bmi,
        'recordedAt': timestamp.toIso8601String(),
      });
      final refreshed = await loadWeightHistory(userId);
      if (!refreshed) {
        _weightHistory = [
          ..._weightHistory.where((item) => item.id != doc.id),
          BodyMetrics(
            id: doc.id,
            userId: userId,
            weight: weight,
            bmi: bmi,
            recordedAt: timestamp,
          ),
        ]..sort((a, b) => a.recordedAt.compareTo(b.recordedAt));
        notifyListeners();
      }
      return true;
    } catch (e) {
      debugPrint('❌ [HealthProvider] addBodyMetrics failed: $e');
      return false;
    }
  }

  Future<String?> addWater(String userId, double amount) async {
    // Cảnh báo uống quá nhiều cùng 1 lúc
    if (amount > 500) {
      return '⚠️ Cảnh báo: Uống quá nhiều nước cùng lúc (>${amount.toInt()}ml) có thể gây khó chịu cho dạ dày. Nên uống từ từ và chia nhỏ lượng nước trong ngày.';
    }
    
    // Cảnh báo uống quá nhiều trong ngày
    final newTotal = _todayWaterIntake + amount;
    if (newTotal > 5000) {
      return '⚠️ Cảnh báo: Bạn đã uống quá nhiều nước trong ngày (${(newTotal/1000).toStringAsFixed(1)}L). Uống quá nhiều nước có thể gây mất cân bằng điện giải và ảnh hưởng đến sức khỏe.';
    }
    
    final result = await recordWater(userId, amount);
    if (!result.isPersisted) return 'Không thể lưu lượng nước lúc này.';
    
    // Trả về null nếu không có cảnh báo
    return null;
  }

  Future<WriteResult<double>> recordWater(String userId, double amount) async {
    if (userId.isEmpty || userId == 'demo' || amount <= 0) {
      return const WriteResult.rejected('INVALID_WATER_WRITE');
    }
    try {
      await _firestore.collection('water_intake').add({
        'userId': userId,
        'amount': amount,
        'date': DateTime.now().toIso8601String(),
      });
      _todayWaterIntake += amount;
      _waterStatus = DataStatus.known;
      _waterObservedAt = DateTime.now();
      notifyListeners();
      debugPrint('✅ Water intake saved to Firestore: ${amount}ml');
      return WriteResult.persisted(_todayWaterIntake);
    } catch (e) {
      debugPrint('❌ Error saving water intake to Firestore: $e');
      return const WriteResult.error('WATER_PERSISTENCE_ERROR');
    }
  }

  Future<bool> loadTodayWaterIntake(String userId) async {
    if (userId.isEmpty || userId == 'demo') {
      _waterStatus = DataStatus.missing;
      _waterObservedAt = null;
      return true;
    }
    try {
      debugPrint('🔄 Loading water intake for user: $userId');
      DateTime today = DateTime.now();
      DateTime startOfDay = DateTime(today.year, today.month, today.day);
      DateTime endOfDay = startOfDay.add(const Duration(days: 1));

      QuerySnapshot snapshot = await _firestore
          .collection('water_intake')
          .where('userId', isEqualTo: userId)
          .get(const GetOptions(source: Source.server));

      // Filter by date in memory
      _todayWaterIntake = snapshot.docs
          .where((doc) {
            final data = doc.data() as Map<String, dynamic>;
            final dateStr = data['date'] as String?;
            if (dateStr == null) return false;
            final date = DateTime.parse(dateStr);
            return !date.isBefore(startOfDay) && date.isBefore(endOfDay);
          })
          .fold(0.0, (acc, doc) => acc + ((doc.data() as Map<String, dynamic>)['amount'] ?? 0).toDouble());
      
      debugPrint('✅ Loaded water intake: ${_todayWaterIntake}ml from Firestore');
      _waterStatus = DataStatus.known;
      _waterObservedAt = DateTime.now();
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('❌ Error loading water intake from Firestore: $e');
      _waterStatus = DataStatus.error;
      return false;
    }
  }
}
