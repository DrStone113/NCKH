# Tóm tắt thay đổi Flutter

## 1. Đơn giản hóa `_buildActionCards`:
- Loại bỏ logic phức tạp kiểm tra `dishGroups.length == 1`
- Luôn nhóm theo `dish_name` và render mỗi món 1 card
- Thêm helper `_getMealTypeLabel()` để convert meal_type → tiếng Việt

## 2. Cập nhật `_MealActionCard`:
- Thêm parameter `mealType` vào constructor
- Cập nhật `_mealTypeLabel` getter để hỗ trợ cả tiếng Việt và tiếng Anh
- Subtitle hiển thị: "Bữa trưa · 3 nguyên liệu"

## 3. Kết quả:
**Trước:**
```
Bữa trưa
· 3 nguyên liệu
```

**Sau:**
```
Cơm gà
Bữa trưa · 3 nguyên liệu
```

## 4. Test cases:
1. Gợi ý 1 bữa: "Gợi ý bữa trưa" → 1 card với tên món
2. Gợi ý nhiều bữa: "Gợi ý cả ngày" → 3 cards, mỗi bữa 1 món
3. Fallback: Nếu không có dish_name → dùng meal_type label

## 5. Rebuild app:
```bash
cd HealthApp/health_app
flutter clean
flutter pub get
flutter run
```
