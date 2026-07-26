import 'package:cloud_firestore/cloud_firestore.dart';
import '../constants/firestore_collections.dart';

class SeedData {
  static final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  /// Seed dữ liệu mẫu cho database
  static Future<void> seedDatabase() async {
    try {
      await _seedExercises();
      await _seedFoods();
      await _seedSymptoms();
      await _seedNutritionDeficiency();
      print('✅ Seed data thành công!');
    } catch (e) {
      print('❌ Lỗi seed data: $e');
      rethrow;
    }
  }

  /// Seed bài tập
  static Future<void> _seedExercises() async {
    final exercises = [
      // Cardio
      {'ten_bai_tap': 'Đi bộ', 'chi_so_met': 3.5, 'mo_ta': 'Đi bộ nhẹ nhàng 4-5 km/h'},
      {'ten_bai_tap': 'Đi bộ nhanh', 'chi_so_met': 5.0, 'mo_ta': 'Đi bộ nhanh 6-7 km/h'},
      {'ten_bai_tap': 'Chạy bộ', 'chi_so_met': 8.0, 'mo_ta': 'Chạy bộ vừa phải 8 km/h'},
      {'ten_bai_tap': 'Chạy nhanh', 'chi_so_met': 11.5, 'mo_ta': 'Chạy nhanh 12 km/h'},
      {'ten_bai_tap': 'Đạp xe', 'chi_so_met': 6.0, 'mo_ta': 'Đạp xe tốc độ vừa phải'},
      {'ten_bai_tap': 'Bơi lội', 'chi_so_met': 7.0, 'mo_ta': 'Bơi tự do tốc độ vừa'},
      {'ten_bai_tap': 'Nhảy dây', 'chi_so_met': 10.0, 'mo_ta': 'Nhảy dây cường độ vừa'},
      {'ten_bai_tap': 'Leo cầu thang', 'chi_so_met': 8.0, 'mo_ta': 'Leo cầu thang'},
      
      // Strength
      {'ten_bai_tap': 'Tập tạ nhẹ', 'chi_so_met': 3.5, 'mo_ta': 'Tập tạ cường độ nhẹ'},
      {'ten_bai_tap': 'Tập tạ nặng', 'chi_so_met': 6.0, 'mo_ta': 'Tập tạ cường độ cao'},
      {'ten_bai_tap': 'Hít đất', 'chi_so_met': 8.0, 'mo_ta': 'Push-ups cường độ vừa'},
      {'ten_bai_tap': 'Squats', 'chi_so_met': 5.0, 'mo_ta': 'Squat không tạ'},
      {'ten_bai_tap': 'Plank', 'chi_so_met': 3.5, 'mo_ta': 'Giữ plank'},
      
      // Flexibility
      {'ten_bai_tap': 'Yoga', 'chi_so_met': 3.0, 'mo_ta': 'Yoga cơ bản'},
      {'ten_bai_tap': 'Stretching', 'chi_so_met': 2.5, 'mo_ta': 'Giãn cơ toàn thân'},
      {'ten_bai_tap': 'Pilates', 'chi_so_met': 4.0, 'mo_ta': 'Pilates cường độ vừa'},
      
      // Sports
      {'ten_bai_tap': 'Cầu lông', 'chi_so_met': 5.5, 'mo_ta': 'Chơi cầu lông'},
      {'ten_bai_tap': 'Bóng đá', 'chi_so_met': 7.0, 'mo_ta': 'Đá bóng'},
      {'ten_bai_tap': 'Bóng rổ', 'chi_so_met': 6.5, 'mo_ta': 'Chơi bóng rổ'},
      {'ten_bai_tap': 'Bóng bàn', 'chi_so_met': 4.0, 'mo_ta': 'Chơi bóng bàn'},
    ];

    for (var exercise in exercises) {
      await _firestore.collection(FirestoreCollections.exercises).add(exercise);
    }
    print('✅ Đã seed ${exercises.length} bài tập');
  }

  /// Seed món ăn
  static Future<void> _seedFoods() async {
    final foods = [
      // Cơm & Tinh bột
      {
        'ten_mon': 'Cơm trắng',
        'calo_tren_100g': 130.0,
        'protein_tren_100g': 2.7,
        'chat_beo_tren_100g': 0.3,
        'carbs_tren_100g': 28.2,
        'danh_muc': 'Cơm & Tinh bột',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Cơm gạo lứt',
        'calo_tren_100g': 123.0,
        'protein_tren_100g': 2.7,
        'chat_beo_tren_100g': 1.0,
        'carbs_tren_100g': 25.6,
        'danh_muc': 'Cơm & Tinh bột',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Phở bò',
        'calo_tren_100g': 46.0,
        'protein_tren_100g': 3.5,
        'chat_beo_tren_100g': 0.8,
        'carbs_tren_100g': 6.5,
        'danh_muc': 'Cơm & Tinh bột',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Bún',
        'calo_tren_100g': 110.0,
        'protein_tren_100g': 3.2,
        'chat_beo_tren_100g': 0.2,
        'carbs_tren_100g': 23.4,
        'danh_muc': 'Cơm & Tinh bột',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Bánh mì',
        'calo_tren_100g': 265.0,
        'protein_tren_100g': 9.0,
        'chat_beo_tren_100g': 3.2,
        'carbs_tren_100g': 49.0,
        'danh_muc': 'Cơm & Tinh bột',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },

      // Thịt
      {
        'ten_mon': 'Thịt gà luộc',
        'calo_tren_100g': 165.0,
        'protein_tren_100g': 31.0,
        'chat_beo_tren_100g': 3.6,
        'carbs_tren_100g': 0.0,
        'danh_muc': 'Thịt',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Thịt bò nạc',
        'calo_tren_100g': 250.0,
        'protein_tren_100g': 26.0,
        'chat_beo_tren_100g': 15.0,
        'carbs_tren_100g': 0.0,
        'danh_muc': 'Thịt',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Thịt heo nạc',
        'calo_tren_100g': 143.0,
        'protein_tren_100g': 26.0,
        'chat_beo_tren_100g': 3.5,
        'carbs_tren_100g': 0.0,
        'danh_muc': 'Thịt',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },

      // Hải sản
      {
        'ten_mon': 'Cá hồi',
        'calo_tren_100g': 208.0,
        'protein_tren_100g': 20.0,
        'chat_beo_tren_100g': 13.0,
        'carbs_tren_100g': 0.0,
        'danh_muc': 'Hải sản',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Tôm',
        'calo_tren_100g': 99.0,
        'protein_tren_100g': 24.0,
        'chat_beo_tren_100g': 0.3,
        'carbs_tren_100g': 0.2,
        'danh_muc': 'Hải sản',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },

      // Rau củ
      {
        'ten_mon': 'Rau muống',
        'calo_tren_100g': 19.0,
        'protein_tren_100g': 2.6,
        'chat_beo_tren_100g': 0.2,
        'carbs_tren_100g': 3.1,
        'danh_muc': 'Rau củ',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Cà rốt',
        'calo_tren_100g': 41.0,
        'protein_tren_100g': 0.9,
        'chat_beo_tren_100g': 0.2,
        'carbs_tren_100g': 9.6,
        'danh_muc': 'Rau củ',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },

      // Trứng & Sữa
      {
        'ten_mon': 'Trứng gà luộc',
        'calo_tren_100g': 155.0,
        'protein_tren_100g': 13.0,
        'chat_beo_tren_100g': 11.0,
        'carbs_tren_100g': 1.1,
        'danh_muc': 'Trứng & Sữa',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Sữa tươi',
        'calo_tren_100g': 61.0,
        'protein_tren_100g': 3.2,
        'chat_beo_tren_100g': 3.3,
        'carbs_tren_100g': 4.8,
        'danh_muc': 'Trứng & Sữa',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },

      // Trái cây
      {
        'ten_mon': 'Chuối',
        'calo_tren_100g': 89.0,
        'protein_tren_100g': 1.1,
        'chat_beo_tren_100g': 0.3,
        'carbs_tren_100g': 22.8,
        'danh_muc': 'Trái cây',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
      {
        'ten_mon': 'Cam',
        'calo_tren_100g': 47.0,
        'protein_tren_100g': 0.9,
        'chat_beo_tren_100g': 0.1,
        'carbs_tren_100g': 11.8,
        'danh_muc': 'Trái cây',
        'la_mon_he_thong': true,
        'nguoi_dung_id': null,
      },
    ];

    for (var food in foods) {
      await _firestore.collection(FirestoreCollections.foods).add(food);
    }
    print('✅ Đã seed ${foods.length} món ăn');
  }

  /// Seed triệu chứng
  static Future<void> _seedSymptoms() async {
    final symptoms = [
      {'ten_trieu_chung': 'Mệt mỏi', 'mo_ta': 'Cảm giác mệt mỏi, uể oải kéo dài'},
      {'ten_trieu_chung': 'Chóng mặt', 'mo_ta': 'Cảm giác đầu quay, mất thăng bằng'},
      {'ten_trieu_chung': 'Da khô', 'mo_ta': 'Da bị khô, nứt nẻ'},
      {'ten_trieu_chung': 'Rụng tóc', 'mo_ta': 'Tóc rụng nhiều bất thường'},
      {'ten_trieu_chung': 'Khó tập trung', 'mo_ta': 'Khó tập trung, giảm trí nhớ'},
      {'ten_trieu_chung': 'Tê tay chân', 'mo_ta': 'Cảm giác tê, châm chích ở tay chân'},
    ];

    for (var symptom in symptoms) {
      await _firestore.collection(FirestoreCollections.symptoms).add(symptom);
    }
    print('✅ Đã seed ${symptoms.length} triệu chứng');
  }

  /// Seed thiếu hụt vi chất
  static Future<void> _seedNutritionDeficiency() async {
    final deficiencies = [
      {
        'ten_vi_chat': 'Sắt',
        'loi_khuyen': 'Ăn nhiều thịt đỏ, gan, rau xanh đậm. Kết hợp với vitamin C để tăng hấp thu.'
      },
      {
        'ten_vi_chat': 'Vitamin B12',
        'loi_khuyen': 'Ăn thịt, cá, trứng, sữa. Người ăn chay nên bổ sung viên uống.'
      },
      {
        'ten_vi_chat': 'Vitamin D',
        'loi_khuyen': 'Phơi nắng 15-20 phút/ngày, ăn cá béo, trứng, sữa tăng cường vitamin D.'
      },
      {
        'ten_vi_chat': 'Canxi',
        'loi_khuyen': 'Uống sữa, ăn sữa chua, phô mai, rau xanh đậm, đậu phụ.'
      },
      {
        'ten_vi_chat': 'Kẽm',
        'loi_khuyen': 'Ăn hải sản, thịt đỏ, hạt, đậu.'
      },
    ];

    for (var deficiency in deficiencies) {
      await _firestore.collection(FirestoreCollections.nutritionDeficiency).add(deficiency);
    }
    print('✅ Đã seed ${deficiencies.length} thiếu hụt vi chất');
  }
}
