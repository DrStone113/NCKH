import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/health_models.dart';
import '../constants/firestore_collections.dart';

class HealthProvider with ChangeNotifier {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;

  List<BodyMetrics> _weightHistory = [];
  double _todayWaterIntake = 0;

  List<BodyMetrics> get weightHistory => _weightHistory;
  double get todayWaterIntake => _todayWaterIntake;

  Future<void> loadWeightHistory(String userId) async {
    if (userId == 'demo') return;
    try {
      QuerySnapshot snapshot = await _firestore
          .collection(FirestoreCollections.bodyMetrics)
          .where('userId', isEqualTo: userId)
          .orderBy('recordedAt', descending: true)
          .limit(30)
          .get();

      _weightHistory = snapshot.docs
          .map((doc) => BodyMetrics.fromMap(doc.data() as Map<String, dynamic>))
          .toList()
          .reversed
          .toList();
      notifyListeners();
    } catch (e) {
      _weightHistory = [];
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

    // Tài khoản demo không có Firestore — vẫn cập nhật danh sách trong bộ nhớ
    // để giao diện và chatbot thấy được thay đổi.
    if (userId == 'demo') {
      _weightHistory = [
        ..._weightHistory,
        BodyMetrics(
          id: 'demo-${timestamp.millisecondsSinceEpoch}',
          userId: userId,
          weight: weight,
          bmi: bmi,
          recordedAt: timestamp,
        ),
      ]..sort((a, b) => a.recordedAt.compareTo(b.recordedAt));
      notifyListeners();
      return true;
    }

    try {
      await _firestore.collection(FirestoreCollections.bodyMetrics).add({
        'userId': userId,
        'weight': weight,
        'bmi': bmi,
        'recordedAt': timestamp.toIso8601String(),
      });
      await loadWeightHistory(userId);
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
    
    // Update local state first for immediate UI update
    _todayWaterIntake += amount;
    notifyListeners();
    
    try {
      await _firestore.collection('water_intake').add({
        'userId': userId,
        'amount': amount,
        'date': DateTime.now().toIso8601String(),
      });
      debugPrint('✅ Water intake saved to Firestore: ${amount}ml');
    } catch (e) {
      debugPrint('❌ Error saving water intake to Firestore: $e');
      // Keep in local state even if Firestore fails (offline support)
    }
    
    // Trả về null nếu không có cảnh báo
    return null;
  }

  Future<void> loadTodayWaterIntake(String userId) async {
    try {
      debugPrint('🔄 Loading water intake for user: $userId');
      DateTime today = DateTime.now();
      DateTime startOfDay = DateTime(today.year, today.month, today.day);

      QuerySnapshot snapshot = await _firestore
          .collection('water_intake')
          .where('userId', isEqualTo: userId)
          .get();

      // Filter by date in memory
      _todayWaterIntake = snapshot.docs
          .where((doc) {
            final data = doc.data() as Map<String, dynamic>;
            final dateStr = data['date'] as String?;
            if (dateStr == null) return false;
            final date = DateTime.parse(dateStr);
            return date.isAfter(startOfDay);
          })
          .fold(0.0, (acc, doc) => acc + ((doc.data() as Map<String, dynamic>)['amount'] ?? 0).toDouble());
      
      debugPrint('✅ Loaded water intake: ${_todayWaterIntake}ml from Firestore');
      notifyListeners();
    } catch (e) {
      debugPrint('❌ Error loading water intake from Firestore: $e');
      _todayWaterIntake = 0;
    }
  }
}
