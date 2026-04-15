# HƯỚNG DẪN CÀI ĐẶT VÀ CHẠY ỨNG DỤNG

## Bước 1: Chuẩn bị môi trường

### Kiểm tra Flutter SDK
Ứng dụng sử dụng Flutter SDK có sẵn trong thư mục `flutter/` cùng cấp.

Cấu trúc thư mục:
```
NCKH/
├── flutter/              # Flutter SDK
└── health_app/           # Ứng dụng của bạn
    ├── lib/
    ├── android/
    ├── setup.bat
    └── run.bat
```

## Bước 2: Cài đặt Firebase

### 2.1. Tạo Firebase Project
1. Truy cập: https://console.firebase.google.com
2. Nhấn "Add project" (Thêm dự án)
3. Đặt tên: `health-app` hoặc tên bạn muốn
4. Tắt Google Analytics (không bắt buộc)
5. Nhấn "Create project"

### 2.2. Thêm Android App
1. Trong Firebase Console, chọn project vừa tạo
2. Nhấn biểu tượng Android
3. Nhập thông tin:
   - **Android package name**: `com.example.health_app`
   - **App nickname**: `Health App`
   - **Debug signing certificate SHA-1**: (Bỏ qua)
4. Nhấn "Register app"

### 2.3. Download file cấu hình
1. Tải file `google-services.json`
2. Sao chép file vào: `health_app/android/app/google-services.json`

### 2.4. Kích hoạt Authentication
1. Trong Firebase Console, vào **Authentication**
2. Nhấn "Get started"
3. Chọn **Email/Password**
4. Bật "Enable"
5. Nhấn "Save"

### 2.5. Kích hoạt Firestore Database
1. Trong Firebase Console, vào **Firestore Database**
2. Nhấn "Create database"
3. Chọn "Start in test mode"
4. Chọn location: `asia-southeast1` (Singapore)
5. Nhấn "Enable"

## Bước 3: Cài đặt ứng dụng

### Chạy file setup.bat
```bash
cd health_app
setup.bat
```

Script sẽ tự động:
- Kiểm tra Flutter SDK
- Chạy `flutter doctor`
- Cài đặt dependencies (`flutter pub get`)
- Tạo cấu trúc thư mục

## Bước 4: Chạy ứng dụng

### 4.1. Kết nối thiết bị
Chọn một trong hai cách:

**Cách 1: Sử dụng thiết bị Android thật**
1. Bật "Developer options" trên điện thoại
2. Bật "USB debugging"
3. Kết nối điện thoại với máy tính qua USB
4. Chấp nhận "Allow USB debugging"

**Cách 2: Sử dụng Android Emulator**
1. Cài đặt Android Studio
2. Mở AVD Manager
3. Tạo và chạy một emulator

### 4.2. Chạy ứng dụng
```bash
run.bat
```

Hoặc chạy thủ công:
```bash
cd health_app
..\flutter\bin\flutter run
```

## Bước 5: Kiểm tra ứng dụng

### Đăng ký tài khoản mới
1. Mở ứng dụng
2. Chọn "Đăng ký"
3. Nhập thông tin:
   - Email: test@example.com
   - Mật khẩu: 123456
   - Họ tên: Nguyễn Văn A
   - Tuổi: 25
   - Giới tính: Nam
   - Chiều cao: 170 cm
   - Cân nặng: 65 kg
   - Mức độ hoạt động: Vận động vừa
4. Nhấn "Đăng ký"

### Thử các tính năng
- **Tab Tổng quan**: Xem chỉ số BMI, BMR, TDEE
- **Tab Dinh dưỡng**: Thêm bữa ăn, theo dõi calo
- **Tab Vận động**: Thêm hoạt động thể chất
- **Tab Tư vấn**: Chat với bot về sức khỏe

## Xử lý lỗi thường gặp

### Lỗi: "Flutter not found"
- Kiểm tra thư mục `flutter/` có tồn tại không
- Chạy lại `setup.bat`

### Lỗi: "google-services.json not found"
- Đảm bảo file `google-services.json` nằm trong `android/app/`
- Kiểm tra tên file chính xác (không có khoảng trắng)

### Lỗi: "No devices found"
- Kết nối thiết bị Android hoặc chạy emulator
- Chạy `flutter devices` để kiểm tra

### Lỗi Firebase Authentication
- Kiểm tra đã bật Email/Password trong Firebase Console
- Kiểm tra kết nối internet

### Lỗi Firestore
- Kiểm tra đã tạo Firestore Database
- Đảm bảo chọn "test mode" để dễ phát triển

## Cấu trúc dự án

```
health_app/
├── lib/
│   ├── models/              # Data models
│   │   ├── user_model.dart
│   │   ├── meal_model.dart
│   │   └── exercise_model.dart
│   ├── providers/           # State management
│   │   ├── user_provider.dart
│   │   ├── health_provider.dart
│   │   ├── nutrition_provider.dart
│   │   └── exercise_provider.dart
│   ├── screens/             # UI screens
│   │   ├── auth_screen.dart
│   │   ├── home_screen.dart
│   │   ├── health_stats_screen.dart
│   │   ├── nutrition_screen.dart
│   │   ├── exercise_screen.dart
│   │   └── chatbot_screen.dart
│   └── main.dart            # Entry point
├── android/
│   └── app/
│       ├── build.gradle
│       └── google-services.json  # File Firebase (cần thêm)
├── pubspec.yaml             # Dependencies
├── setup.bat                # Script cài đặt
├── run.bat                  # Script chạy app
└── README.md                # Tài liệu

```

## Lệnh Flutter hữu ích

```bash
# Kiểm tra môi trường
..\flutter\bin\flutter doctor

# Xem danh sách thiết bị
..\flutter\bin\flutter devices

# Cài đặt dependencies
..\flutter\bin\flutter pub get

# Chạy ứng dụng
..\flutter\bin\flutter run

# Build APK
..\flutter\bin\flutter build apk

# Clean project
..\flutter\bin\flutter clean
```

## Liên hệ hỗ trợ

Nếu gặp vấn đề, liên hệ:
- Lê Nhật Bằng - bangb2205974@student.ctu.edu.vn
- Nhóm phát triển: DI22V7F1

## Tài liệu tham khảo

- Flutter: https://flutter.dev/docs
- Firebase: https://firebase.google.com/docs
- Provider: https://pub.dev/packages/provider
