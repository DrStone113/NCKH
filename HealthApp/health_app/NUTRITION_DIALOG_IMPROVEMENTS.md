# Cải tiến Dialog Thêm Bữa Ăn

## Các tính năng mới được thêm vào:

### 1. Sắp xếp danh sách món ăn thông minh theo bữa ăn ⭐ MỚI
- Danh sách món ăn tự động sắp xếp theo độ phù hợp với bữa ăn đang chọn
- **Bữa sáng (🌅)**: Ưu tiên bánh mì, phở, trứng, sữa, cháo, xôi
- **Bữa trưa (☀️)**: Ưu tiên cơm, thịt, cá, gà, rau, canh
- **Bữa tối (🌙)**: Ưu tiên cơm, cá, gà, rau (nhẹ hơn bữa trưa)
- **Ăn phụ (🍎)**: Ưu tiên trái cây, sữa, bánh nhẹ
- Khi đổi loại bữa ăn, danh sách tự động sắp xếp lại
- Có indicator "✨ Danh sách được sắp xếp phù hợp với..." để người dùng biết

### 2. Gợi ý khối lượng thông minh theo bữa ăn
### 2. Gợi ý khối lượng thông minh theo bữa ăn
- **Bữa sáng (🌅)**: Giảm 20% khối lượng (hệ số 0.8)
- **Bữa trưa (☀️)**: Tăng 20% khối lượng (hệ số 1.2) - bữa chính trong ngày
- **Bữa tối (🌙)**: Giữ nguyên khối lượng (hệ số 1.0)
- **Ăn phụ (🍎)**: Giảm 40% khối lượng (hệ số 0.6)

### 3. Tự động cập nhật khối lượng
### 3. Tự động cập nhật khối lượng
- Khi người dùng thay đổi loại bữa ăn, khối lượng sẽ tự động điều chỉnh
- Khi chọn món ăn mới, khối lượng được gợi ý phù hợp với bữa ăn hiện tại

### 4. Gợi ý nhanh thông minh
### 4. Gợi ý nhanh thông minh
- Các nút gợi ý khối lượng nhanh được điều chỉnh theo:
  - Loại món ăn (cơm, phở, thịt, rau, trái cây...)
  - Loại bữa ăn (sáng/trưa/tối/phụ)
- Nút được chọn sẽ được highlight rõ ràng

### 5. Hiển thị thông tin dinh dưỡng dự kiến
### 5. Hiển thị thông tin dinh dưỡng dự kiến
- Hiển thị realtime khi thay đổi khối lượng:
  - 🔥 Calories (kcal)
  - 💪 Protein (g)
  - 🌾 Carbs (g)
  - 🥑 Fat (g)
- Giúp người dùng đưa ra quyết định tốt hơn về khối lượng ăn

### 6. UI/UX cải thiện
### 6. UI/UX cải thiện
- Label rõ ràng: "Gợi ý khối lượng cho bữa sáng/trưa/tối/phụ"
- Nút gợi ý có viền và màu sắc phân biệt rõ ràng
- Thông tin dinh dưỡng được đóng khung đẹp mắt với icon
- Placeholder tìm kiếm động: "Tìm kiếm thực phẩm phù hợp với bữa sáng..."
- Indicator sắp xếp thông minh với icon ✨

## Ví dụ sử dụng:

### Trường hợp 1: Chọn bữa sáng
- Danh sách tự động hiển thị: Bánh mì, Phở, Trứng, Sữa... lên đầu
- Chọn "Bánh mì" → Gợi ý: 64g (80g × 0.8)
- Các lựa chọn nhanh: 40g, 64g, 80g, 96g

### Trường hợp 2: Chọn bữa trưa
- Danh sách tự động hiển thị: Cơm, Thịt, Cá, Gà, Rau... lên đầu
- Chọn "Cơm trắng" → Gợi ý: 180g (150g × 1.2)
- Các lựa chọn nhanh: 120g, 180g, 240g, 300g

### Trường hợp 3: Chọn ăn phụ
- Danh sách tự động hiển thị: Chuối, Táo, Cam, Sữa... lên đầu
- Chọn "Chuối" → Gợi ý: 70g (120g × 0.6)
- Các lựa chọn nhanh: 60g, 70g, 90g, 120g

### Trường hợp 4: Đổi từ bữa sáng sang bữa trưa
- Đã chọn "Phở bò" cho bữa sáng (280g)
- Đổi sang bữa trưa → Khối lượng tự động tăng lên 420g
- Danh sách món ăn tự động sắp xếp lại

## Lợi ích:
✅ Tiết kiệm thời gian nhập liệu
✅ Gợi ý phù hợp với thói quen ăn uống Việt Nam
✅ Giúp kiểm soát khẩu phần ăn tốt hơn
✅ Hiển thị thông tin dinh dưỡng trực quan
✅ Trải nghiệm người dùng mượt mà hơn
✅ Danh sách món ăn được sắp xếp thông minh theo bữa ăn
✅ Dễ dàng tìm món ăn phù hợp với từng bữa

## Chi tiết thuật toán sắp xếp:

### Điểm ưu tiên theo bữa ăn:

**Bữa sáng:**
- Bánh mì: 100 điểm
- Phở: 90 điểm
- Trứng: 85 điểm
- Sữa: 80 điểm
- Cháo: 75 điểm
- Xôi: 70 điểm
- Bún: 60 điểm
- Trái cây: 50 điểm

**Bữa trưa:**
- Cơm: 100 điểm
- Thịt (bò, heo): 90 điểm
- Cá: 85 điểm
- Gà: 80 điểm
- Rau: 75 điểm
- Canh: 70 điểm
- Phở/Bún: 60 điểm
- Hải sản: 55 điểm

**Bữa tối:**
- Cơm: 90 điểm
- Cá: 85 điểm
- Rau: 85 điểm
- Gà: 80 điểm
- Canh: 75 điểm
- Phở/Bún: 70 điểm
- Tôm: 65 điểm
- Thịt: 60 điểm

**Ăn phụ:**
- Trái cây: 100 điểm
- Sữa: 90 điểm
- Bánh ngọt: 80 điểm
- Snack: 70 điểm
- Trứng: 60 điểm
