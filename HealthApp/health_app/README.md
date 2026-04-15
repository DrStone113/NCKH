# Health App - Ứng dụng Quản lý Sức khỏe Cá nhân

Ứng dụng di động hỗ trợ quản lý sức khỏe cá nhân thông qua theo dõi dinh dưỡng, vận động, chỉ số cơ thể và tư vấn sức khỏe bằng chatbot.

## Tính năng chính

### 1. Theo dõi Chỉ số Cơ thể
- Tính toán BMI (Body Mass Index)
- Tính toán BMR (Basal Metabolic Rate)
- Tính toán TDEE (Total Daily Energy Expenditure)
- Theo dõi cân nặng, chiều cao
- Phân loại tình trạng sức khỏe

### 2. Quản lý Dinh dưỡng
- Ghi nhận bữa ăn hàng ngày
- Theo dõi lượng calo tiêu thụ
- Theo dõi macro nutrients (Protein, Carbs, Fat)
- So sánh với mục tiêu TDEE
- Gợi ý thực đơn phù hợp

### 3. Theo dõi Vận động
- Ghi nhận hoạt động thể chất
- Tính toán calo đốt cháy
- Theo dõi thời gian tập luyện
- Gợi ý bài tập phù hợp
- Phân loại theo loại hình (Cardio, Strength, Flexibility, Sports)

### 4. Chatbot Tư vấn Sức khỏe
- Tư vấn về triệu chứng thiếu hụt dinh dưỡng
- Gợi ý thực phẩm bổ sung vi chất
- Hướng dẫn chế độ ăn uống lành mạnh
- Tư vấn giảm cân/tăng cơ
- Phân tích triệu chứng và đề xuất giải pháp

## Công nghệ sử dụng

- **Frontend**: Flutter
- **Backend**: Firebase (Authentication, Firestore)
- **State Management**: Provider
- **Database**: Cloud Firestore
- **Charts**: fl_chart

## Cài đặt

### Yêu cầu
- Flutter SDK >= 3.0.0
- Dart SDK >= 3.0.0
- Firebase project

### Các bước cài đặt

1. Clone repository
```bash
git clone <repository-url>
cd health_app
```

2. Cài đặt dependencies
```bash
flutter pub get
```

3. Cấu hình Firebase
- Tạo project trên Firebase Console
- Thêm ứng dụng Android/iOS
- Download và thêm file cấu hình:
  - Android: `google-services.json` vào `android/app/`
  - iOS: `GoogleService-Info.plist` vào `ios/Runner/`

4. Chạy ứng dụng
```bash
flutter run
```

## Cấu trúc thư mục

```
lib/
├── models/           # Data models
│   ├── user_model.dart
│   ├── meal_model.dart
│   └── exercise_model.dart
├── providers/        # State management
│   ├── user_provider.dart
│   ├── health_provider.dart
│   ├── nutrition_provider.dart
│   └── exercise_provider.dart
├── screens/          # UI screens
│   ├── auth_screen.dart
│   ├── home_screen.dart
│   ├── health_stats_screen.dart
│   ├── nutrition_screen.dart
│   ├── exercise_screen.dart
│   └── chatbot_screen.dart
└── main.dart         # Entry point
```

## Hướng dẫn sử dụng

### Đăng ký tài khoản
1. Mở ứng dụng
2. Chọn "Đăng ký"
3. Nhập thông tin cá nhân (email, mật khẩu, họ tên, tuổi, giới tính, chiều cao, cân nặng, mức độ hoạt động)
4. Nhấn "Đăng ký"

### Theo dõi dinh dưỡng
1. Vào tab "Dinh dưỡng"
2. Nhấn nút "+" để thêm bữa ăn
3. Nhập thông tin món ăn (tên, loại bữa ăn, calo, protein, carbs, fat)
4. Xem tổng quan dinh dưỡng trong ngày

### Theo dõi vận động
1. Vào tab "Vận động"
2. Nhấn nút "+" để thêm hoạt động
3. Nhập thông tin (tên, loại, thời gian, calo đốt)
4. Hoặc chọn từ danh sách gợi ý

### Tư vấn sức khỏe
1. Vào tab "Tư vấn"
2. Nhập triệu chứng hoặc câu hỏi
3. Chatbot sẽ phân tích và đưa ra gợi ý

## Tính năng sắp tới

- [ ] Tích hợp USDA FoodData Central API
- [ ] Tích hợp RASA chatbot
- [ ] Biểu đồ theo dõi tiến trình
- [ ] Nhắc nhở uống nước
- [ ] Xuất báo cáo sức khỏe
- [ ] Chia sẻ kế hoạch với bạn bè
- [ ] Tích hợp thiết bị đeo (smartwatch)

## Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng tạo issue hoặc pull request.

## Nhóm phát triển

- Lê Nhật Bằng - Chủ nhiệm đề tài
- Thạch Nguyễn Khang
- Trần Phúc Khang
- Nguyễn Gia Kiên
- Trần Bảo Tuấn Quỳnh

## Giảng viên hướng dẫn

TS. Thái Minh Tuấn

## License

Dự án nghiên cứu khoa học - Trường CNTT & TT, Đại học Cần Thơ
