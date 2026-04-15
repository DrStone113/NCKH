# Cảnh báo Uống Nước Thông Minh

## Tính năng mới

Đã thêm hệ thống cảnh báo thông minh khi uống quá nhiều nước để bảo vệ sức khỏe người dùng.

## Các mức cảnh báo

### 1. Cảnh báo uống quá nhiều cùng 1 lúc
- **Ngưỡng**: > 500ml
- **Thông báo**: Dialog cảnh báo ngay sau khi thêm nước
- **Nội dung**: "⚠️ Cảnh báo: Uống quá nhiều nước cùng lúc (>500ml) có thể gây khó chịu cho dạ dày. Nên uống từ từ và chia nhỏ lượng nước trong ngày."

### 2. Cảnh báo gần đến giới hạn trong ngày
- **Ngưỡng**: 4000ml - 5000ml (4L - 5L)
- **Hiển thị**: 
  - Icon cảnh báo màu vàng trên card
  - Màu chữ chuyển sang vàng
  - Text "⚠️ Gần giới hạn"

### 3. Cảnh báo uống quá nhiều trong ngày
- **Ngưỡng**: > 5000ml (5L)
- **Hiển thị**:
  - Icon cảnh báo màu đỏ trên card
  - Màu chữ chuyển sang đỏ
  - Text "⚠️ Quá nhiều!"
- **Thông báo**: Dialog cảnh báo khi thêm nước
- **Nội dung**: "⚠️ Cảnh báo: Bạn đã uống quá nhiều nước trong ngày (X.XL). Uống quá nhiều nước có thể gây mất cân bằng điện giải và ảnh hưởng đến sức khỏe."

## Lý do y học

### Tại sao không nên uống quá nhiều cùng lúc?
- Dạ dày chỉ chứa được khoảng 500-1000ml
- Uống quá nhanh gây căng phồng dạ dày
- Có thể gây buồn nôn, khó tiêu

### Tại sao không nên uống quá 5L/ngày?
- Gây loãng điện giải trong máu (hyponatremia)
- Tăng áp lực lên thận
- Có thể gây ngộ độc nước (water intoxication)
- Ảnh hưởng đến cân bằng natri trong cơ thể

## Các file đã cập nhật

1. **lib/providers/health_provider.dart**
   - Cập nhật hàm `addWater()` trả về `Future<String?>` thay vì `Future<void>`
   - Thêm logic kiểm tra ngưỡng 500ml và 5000ml
   - Trả về cảnh báo nếu vượt ngưỡng

2. **lib/screens/home_screen.dart**
   - Cập nhật `_addWater()` để xử lý cảnh báo từ provider
   - Hiển thị dialog cảnh báo khi có warning
   - Cập nhật `_buildWaterCard()` với visual indicators:
     - Màu sắc động (xanh/vàng/đỏ)
     - Icon cảnh báo
     - Text trạng thái

## Trải nghiệm người dùng

### Kịch bản 1: Uống bình thường
- Chọn 250ml → Thêm thành công, không có cảnh báo
- Card hiển thị màu xanh bình thường

### Kịch bản 2: Uống nhiều cùng lúc
- Chọn 500ml → Dialog cảnh báo xuất hiện
- Người dùng đọc và nhấn "Đã hiểu"
- Nước vẫn được thêm vào

### Kịch bản 3: Gần đến giới hạn
- Đã uống 4.2L trong ngày
- Card chuyển màu vàng
- Hiển thị "⚠️ Gần giới hạn"

### Kịch bản 4: Vượt giới hạn
- Đã uống 5.2L trong ngày
- Card chuyển màu đỏ
- Hiển thị "⚠️ Quá nhiều!"
- Khi thêm nước mới → Dialog cảnh báo nghiêm trọng

## Lợi ích

✅ Bảo vệ sức khỏe người dùng
✅ Giáo dục về thói quen uống nước đúng cách
✅ Cảnh báo kịp thời trước khi gây hại
✅ Giao diện trực quan với màu sắc
✅ Không chặn hoàn toàn (vẫn cho phép thêm nước)
