# Cập nhật Tiêu chuẩn BMI cho Người Việt Nam

## Thay đổi

Đã cập nhật thuật toán tính và đánh giá chỉ số BMI theo tiêu chuẩn dành cho người Việt Nam (người châu Á) từ 20 tuổi trở lên.

## Bảng phân loại BMI mới

| Phân loại | Chỉ số BMI | Màu sắc | Mô tả |
|-----------|------------|---------|-------|
| **Gầy độ III** | < 16 | 🔴 Đỏ đậm | Gầy nghiêm trọng, cần gặp bác sĩ ngay |
| **Gầy độ II** | 16 - 16.9 | 🟠 Cam đỏ | Gầy mức độ II, cần tư vấn bác sĩ |
| **Gầy độ I** | 17 - 18.4 | 🔵 Xanh dương | Hơi gầy, cần bổ sung dinh dưỡng |
| **Bình thường** | 18.5 - 24.9 | 🟢 Xanh lá | Chỉ số lý tưởng |
| **Thừa cân** | 25 - 29.9 | 🟡 Vàng | Cần kiểm soát cân nặng |
| **Béo phì độ I** | 30 - 34.9 | 🟠 Cam | Cần tư vấn bác sĩ |
| **Béo phì độ II** | 35 - 39.9 | 🔴 Đỏ | Cần điều trị giảm cân |
| **Béo phì độ III** | ≥ 40 | 🟣 Tím | Cần điều trị chuyên khoa ngay |

## So sánh với tiêu chuẩn cũ

### Tiêu chuẩn cũ (không chính xác):
- Thiếu cân: < 18.5
- Bình thường: 18.5 - 22.9
- Thừa cân: 23 - 24.9
- Béo phì độ I: 25 - 29.9
- Béo phì độ II: ≥ 30

### Tiêu chuẩn mới (chuẩn Việt Nam):
- Gầy độ III: < 16
- Gầy độ II: 16 - 16.9
- Gầy độ I: 17 - 18.4
- Bình thường: 18.5 - 24.9 ✅ (mở rộng từ 22.9 lên 24.9)
- Thừa cân: 25 - 29.9
- Béo phì độ I: 30 - 34.9
- Béo phì độ II: 35 - 39.9
- Béo phì độ III: ≥ 40

## Lợi ích của tiêu chuẩn mới

✅ Phù hợp với người Việt Nam và người châu Á
✅ Phân loại chi tiết hơn (8 mức thay vì 5 mức)
✅ Cảnh báo sớm hơn về tình trạng gầy nghiêm trọng
✅ Phân biệt rõ các mức độ béo phì
✅ Lời khuyên cụ thể hơn cho từng mức

## Các file đã được cập nhật

1. `lib/models/user_model.dart`
   - Cập nhật `bmiCategory` getter
   - Cập nhật `bmiAdvice` getter với 8 mức phân loại

2. `lib/screens/home_screen.dart`
   - Cập nhật `_buildBmiCard()` với màu sắc mới
   - Điều chỉnh scale hiển thị BMI

3. `lib/screens/health_stats_screen.dart`
   - Cập nhật `_buildBmiScale()` với 8 mức phân loại
   - Cập nhật `_getBmiColor()` với màu sắc tương ứng

## Lời khuyên theo từng mức BMI

### Gầy độ III (< 16)
"Bạn bị gầy nghiêm trọng. Cần gặp bác sĩ để được tư vấn dinh dưỡng ngay."

### Gầy độ II (16 - 16.9)
"Bạn bị gầy mức độ II. Nên bổ sung dinh dưỡng và tham khảo ý kiến bác sĩ."

### Gầy độ I (17 - 18.4)
"Bạn hơi gầy. Nên tăng cân bằng cách bổ sung dinh dưỡng đầy đủ."

### Bình thường (18.5 - 24.9)
"Chỉ số BMI bình thường. Hãy duy trì lối sống lành mạnh!"

### Thừa cân (25 - 29.9)
"Bạn thừa cân. Nên tăng vận động và kiểm soát khẩu phần ăn."

### Béo phì độ I (30 - 34.9)
"Bạn béo phì độ I. Nên tham khảo ý kiến bác sĩ để có kế hoạch giảm cân."

### Béo phì độ II (35 - 39.9)
"Bạn béo phì độ II. Cần gặp bác sĩ để được tư vấn giảm cân an toàn."

### Béo phì độ III (≥ 40)
"Bạn béo phì độ III. Cần gặp bác sĩ chuyên khoa ngay để được điều trị."

## Nguồn tham khảo

Tiêu chuẩn BMI này dựa trên khuyến nghị của Bộ Y tế Việt Nam và Tổ chức Y tế Thế giới (WHO) cho khu vực Tây Thái Bình Dương, phù hợp với đặc điểm cơ thể người châu Á.
