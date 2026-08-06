# HƯỚNG DẪN CÀI ĐẶT VÀ CHẠY ỨNG DỤNG

## Bước 1: Chuẩn bị môi trường

### Kiểm tra Flutter SDK
Flutter SDK được cài đặt **ngoài workspace** tại `C:\flutter`, và `C:\flutter\bin` đã được thêm vào biến môi trường `PATH` của hệ thống. Vì vậy có thể gọi lệnh `flutter` trực tiếp từ bất kỳ thư mục nào.

```powershell
flutter --version
# Kỳ vọng: Flutter 3.44.8 • channel stable • Dart 3.12.2

flutter doctor -v
```

Nếu lệnh `flutter` không nhận diện, thêm lại vào PATH (mở PowerShell với quyền Admin):
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\flutter\bin", "Machine")
```
Sau đó **mở lại terminal** để PATH có hiệu lực.

Cấu trúc thư mục hiện tại:
```
C:\flutter\                   # Flutter SDK (nằm ngoài workspace)

C:\Project\Chatbot\NCKH\
└── HealthApp/
    ├── ai_backend/           # FastAPI backend
    └── health_app/           # Ứng dụng Flutter
        ├── lib/
        ├── android/
        ├── test/
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

```powershell
cd C:\Project\Chatbot\NCKH\HealthApp\health_app
flutter pub get
```

Kiểm tra dự án biên dịch sạch:
```powershell
flutter analyze
flutter test
```

## Bước 4: Chạy ứng dụng

### 4.1. Kết nối thiết bị
Chọn một trong hai cách:

**Cách 1: Sử dụng thiết bị Android thật**
1. Bật "Developer options" trên điện thoại
2. Bật "USB debugging"
3. Kết nối điện thoại với máy tính qua USB
4. Chấp nhận "Allow USB debugging"

**Cách 2: Sử dụng Android Emulator / LDPlayer 9**
1. Cài đặt Android Studio (Android SDK 36.0.0 đã có tại `C:\Users\ADMIN\AppData\Local\Android\sdk`)
2. Mở AVD Manager, tạo và chạy một emulator — hoặc dùng LDPlayer 9 (xem `docs/RUN_GUIDE_LDPLAYER.md`)
3. Nếu `flutter doctor` báo thiếu Android license, chạy: `flutter doctor --android-licenses`

**Cách 3: Chạy trên Web**
- Máy hiện **chưa cài Chrome**, dùng Microsoft Edge (device id `edge`) hoặc `web-server`:
  ```powershell
  flutter run -d edge --web-port 3000
  ```

### 4.2. Chạy ứng dụng
```powershell
cd C:\Project\Chatbot\NCKH\HealthApp\health_app
flutter run
```

Hoặc khởi chạy toàn bộ hệ thống (DB + Backend + Web) bằng script ở thư mục gốc `NCKH`:
```powershell
.\start-all.bat
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

### Lỗi: "Flutter not found" / "flutter is not recognized"
- Kiểm tra Flutter đã cài tại `C:\flutter` và `C:\flutter\bin` có trong PATH:
  ```powershell
  $env:Path -split ';' | Where-Object { $_ -like '*flutter*' }
  ```
- Nếu trống, thêm lại PATH (xem Bước 1) và **mở lại terminal**.

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
├── test/                    # Unit & widget tests
├── serve_web.py             # Server phục vụ build\web kèm khung giả lập điện thoại
└── README.md                # Tài liệu

```

## Lệnh Flutter hữu ích

```powershell
# Kiểm tra môi trường
flutter doctor -v

# Xem danh sách thiết bị
flutter devices

# Cài đặt dependencies
flutter pub get

# Chạy ứng dụng
flutter run

# Phân tích tĩnh (lint)
flutter analyze

# Chạy bộ test
flutter test

# Build APK
flutter build apk

# Build Web (giữ nguyên bộ icon)
flutter build web --release --no-tree-shake-icons

# Clean project
flutter clean
```

## Trạng thái kiểm thử gần nhất

Chạy ngày **2026-08-06** với Flutter 3.44.8 / Dart 3.12.2 tại `C:\Project\Chatbot\NCKH\HealthApp\health_app`:

| Lệnh | Kết quả |
| :--- | :--- |
| `flutter pub get` | ✅ Got dependencies! |
| `flutter analyze` | ✅ 22 issues, tất cả mức `info` (`withOpacity` deprecated trong `lib/main.dart`) — 0 error, 0 warning |
| `flutter test` | ✅ 23/23 test passed |
| `flutter build web --release --no-tree-shake-icons` | ✅ Built `build\web` |

## Liên hệ hỗ trợ

Nếu gặp vấn đề, liên hệ:
- Lê Nhật Bằng - bangb2205974@student.ctu.edu.vn
- Nhóm phát triển: DI22V7F1

## Tài liệu tham khảo

- Flutter: https://flutter.dev/docs
- Firebase: https://firebase.google.com/docs
- Provider: https://pub.dev/packages/provider
