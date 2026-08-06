# Hướng Dẫn Khởi Chạy & Kiểm Thử Dự Án Trực Tiếp Trên LDPlayer 9

> **Dự án**: HealthApp - Hệ thống AI Chatbot Chăm sóc Sức khỏe & Giao tiếp chủ động (Proactive Engagement)  
> **Tác giả / Nhóm nghiên cứu**: NCKH Healthcare AI Team  
> **Cập nhật lần cuối**: 2026-08-06  

---

## 📋 1. Môi trường & Chuẩn bị

1. **Flutter SDK**: `3.44.8 (stable)` cài tại `C:\flutter`, đã thêm `C:\flutter\bin` vào biến môi trường `PATH` → gọi trực tiếp lệnh `flutter` ở mọi thư mục.
   ```powershell
   flutter --version   # Kỳ vọng: Flutter 3.44.8 • channel stable • Dart 3.12.2
   ```
2. **Thư mục gốc dự án**: `C:\Project\Chatbot`
3. **Android SDK**: `36.0.0` tại `C:\Users\ADMIN\AppData\Local\Android\sdk` (JDK 21 đi kèm Android Studio).
   - Nếu `flutter doctor` báo thiếu license, chạy: `flutter doctor --android-licenses`
4. **Giả lập LDPlayer 9**: Đã bật sẵn trên máy (Port ADB mặc định: `emulator-5554`).
5. **Đường dẫn ADB của LDPlayer**: `C:\LDPlayer\LDPlayer9\adb.exe`
6. **Mã SHA-1 Debug của máy bạn** (Dùng để khai báo Google Sign-In trên Firebase Console):
   ```text
   SHA1: 39:CB:76:D6:7F:72:9A:DE:47:42:33:D6:0F:19:C1:12:93:78:B5:AE
   ```

---

## 🚀 2. Bước 1: Khởi Chạy Python FastAPI Backend (AI & Proactive Check-in Engine)

Mở terminal PowerShell thứ nhất và chuyển vào thư mục backend:

```powershell
cd C:\Project\Chatbot\apps\backend
```

Khởi chạy server uvicorn (Host `0.0.0.0` trên cổng `8080`):

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8080
```

> **Kiểm tra trạng thái Backend**:
> Mở trình duyệt truy cập:
> - Health Check: `http://localhost:8080/health`
> - Active Proactive Nudge Check: `http://localhost:8080/checkin/active`

---

## 📱 3. Bước 2: Kết Nối & Chạy Flutter App Trên LDPlayer 9

Mở terminal PowerShell thứ hai và chuyển vào thư mục ứng dụng Flutter:

```powershell
cd C:\Project\Chatbot\apps\mobile
```

Thêm đường dẫn ADB của LDPlayer vào biến môi trường PATH tạm thời và kiểm tra thiết bị:

```powershell
$env:PATH += ";C:\LDPlayer\LDPlayer9"
flutter devices
```

> Nếu LDPlayer chưa xuất hiện, chạy `adb connect 127.0.0.1:5555` rồi kiểm tra lại bằng `adb devices`.

### 🔹 Cách 1: Chạy Chế độ Live Debug / Hot Reload (Khuyên dùng khi lập trình)

```powershell
flutter run -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

> **Lưu ý**: `10.0.2.2` là địa chỉ IP đặc biệt của giả lập Android để truy cập lại `localhost` của máy tính.

### 🔹 Cách 2: Biên dịch (Build) File APK & Cài đặt Thủ công

#### B3.1: Build file APK
```powershell
flutter build apk --debug --android-skip-build-dependency-validation --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

#### B3.2: Đẩy file APK vào LDPlayer 9
```powershell
& "C:\LDPlayer\LDPlayer9\adb.exe" install -r build\app\outputs\flutter-apk\app-debug.apk
```

---

## 🔐 4. Bước 3: Cấu Hình Firebase Google Sign-In (Nếu dùng tài khoản Google Thật)

Nếu bạn muốn bấm nút **"Tiếp tục với Google"** bằng tài khoản Google thật trên LDPlayer 9:

1. Truy cập **[Firebase Console](https://console.firebase.google.com/)** -> Chọn Dự án của bạn.
2. Vào **Project Settings (Cài đặt dự án)** -> Kéo xuống mục **Your apps (Ứng dụng của bạn)**.
3. Tìm ứng dụng Android (`com.example.app`) -> Bấm **Add fingerprint (Thêm vân tay)**.
4. Dán mã SHA-1 của máy bạn vào:
   `39:CB:76:D6:7F:72:9A:DE:47:42:33:D6:0F:19:C1:12:93:78:B5:AE`
5. Tải file `google-services.json` mới về dán đè vào thư mục `apps/mobile/android/app/google-services.json`.

> 💡 **Mẹo**: Nếu chưa thêm SHA-1, bạn có thể chọn **"Đăng nhập / Đăng ký bằng Email"** hoặc bấm **"🚀 Dùng thử ứng dụng (Tài khoản Demo)"** để vào app trải nghiệm ngay 100% tính năng.

---

## 💡 5. Trải Nghiệm Tính Năng Giao Tiếp Chủ Động (Proactive Engagement)

Khi mở ứng dụng trên LDPlayer 9 và vào màn hình chính **Tổng quan (Dashboard)**:

1. **Card Check-in Chủ động (Proactive Check-in Card)**: Hiển thị ngay ở đầu màn hình với thiết kế Glassmorphism gradient nổi bật.
2. **Nội dung Nudge Động**: Tự động thay đổi theo khung giờ:
   - Buổi sáng: *"Chào buổi sáng! Bạn đã uống ly nước đầu tiên trong ngày (300ml) chưa?"*
   - Buổi trưa: *"Bữa trưa hôm nay của bạn có nhiều rau xanh không?"*
   - Buổi chiều: *"Hôm nay bạn đã uống đủ 2L nước chưa? (Nạp thêm 250ml nhé!)"*
   - Buổi tối: *"Check-in Cuối Ngày: Hôm nay bạn có vận động thể chất hay cảm thấy thế nào?"*
3. **Thao tác nhanh**: Người dùng bấm trực tiếp vào các nút bấm chọn nhanh (*"Đã uống 300ml 💧"*, *"Nhiều rau xanh 🥦"*, *"Tâm sự với Bot 💬"*) để ghi nhận dữ liệu và tương tác trực tiếp với Chatbot AI.
