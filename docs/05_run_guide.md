# 05. Hướng Dẫn Khởi Chạy Hệ Thống (System Startup Guide)

Tài liệu này hướng dẫn cách chuẩn bị môi trường và khởi chạy toàn bộ hệ thống HealthApp bao gồm **Cơ sở dữ liệu**, **FastAPI Backend**, và **Flutter Web Client**.

> **Thư mục gốc dự án hiện tại**: `C:\Project\Chatbot\NCKH`

---

## 🧰 Môi Trường Đã Xác Minh (Verified Environment)

| Thành phần | Phiên bản / Đường dẫn | Trạng thái |
| :--- | :--- | :--- |
| **Flutter SDK** | 3.44.8 (stable) tại `C:\flutter` | ✅ Đã thêm `C:\flutter\bin` vào biến môi trường `PATH` hệ thống |
| **Dart SDK** | 3.12.2 (đi kèm Flutter) | ✅ |
| **Android SDK** | 36.0.0 (`C:\Users\ADMIN\AppData\Local\Android\sdk`) | ⚠️ Cần chạy `flutter doctor --android-licenses` để chấp nhận license |
| **Trình duyệt Web** | Microsoft Edge 151 (device id: `edge`) | ✅ Chrome chưa cài — dùng `edge` hoặc `web-server` thay thế |
| **Visual Studio C++** | Chưa cài | ❌ Chỉ cần khi build app Windows Desktop |

Kiểm tra nhanh môi trường:
```powershell
flutter --version
flutter doctor -v
flutter devices
```

> **Quan trọng**: Vì `C:\flutter\bin` đã có trong `PATH`, mọi tài liệu trong dự án dùng lệnh `flutter` trực tiếp. **Không còn dùng đường dẫn tương đối** kiểu `..\..\flutter\bin\flutter.bat` (thư mục `flutter/` không còn nằm trong workspace).

---

## ⚡ Khởi Chạy Nhanh (Automated Script)

Thư mục dự án cung cấp script khởi động tự động: **`C:\Project\Chatbot\NCKH\start-all.bat`**.

### Yêu cầu trước khi chạy:
1. Đảm bảo ứng dụng **Docker Desktop** đã được mở và chạy trên máy tính của bạn.
2. Click đúp chuột vào file `start-all.bat` hoặc chạy từ PowerShell:
   ```powershell
   .\start-all.bat
   ```

*Lưu ý: Nếu terminal của bạn gặp lỗi font hoặc lỗi biên dịch ký tự do mã hóa UTF-8 của file `.bat`, hãy sử dụng **Phương pháp thủ công** dưới đây.*

---

## 🛠️ Phương Pháp Thủ Cấu (Manual Commands)

Thực hiện chạy tuần tự 3 dịch vụ theo các bước dưới đây trên các cửa sổ PowerShell riêng biệt.

### Bước 1: Khởi chạy Database Postgres (pgvector)
Mở cửa sổ PowerShell tại thư mục gốc của dự án (`NCKH`) và chạy lệnh khởi tạo container Postgres:
```powershell
docker compose up -d postgres
```
> Lệnh này sẽ tải và chạy container Docker ở chế độ chạy nền (background mode) trên cổng **5432**.

### Bước 2: Khởi chạy FastAPI Backend (AI Engine)
Mở cửa sổ PowerShell mới và di chuyển vào thư mục backend:
```powershell
cd HealthApp/ai_backend/backend
```
Kích hoạt môi trường ảo và khởi chạy server uvicorn:
```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```
> Server API của AI Backend sẽ lắng nghe trên cổng **8080** với chế độ reload tự động khi thay đổi code.

### Bước 3: Khởi chạy Web Client (Flutter Web Simulator)
Mở cửa sổ PowerShell mới và di chuyển vào thư mục ứng dụng Flutter:
```powershell
cd HealthApp/health_app
```

#### Cách 1: Phục vụ bản build tĩnh qua Python (khung giả lập điện thoại)
```powershell
flutter build web --release --no-tree-shake-icons
..\ai_backend\backend\venv\Scripts\python.exe serve_web.py
```
> Web Client sẽ được phục vụ trên cổng **3000**. Màn hình web tự động tích hợp khung giả lập điện thoại di động thông minh cho các buổi demo/test.

#### Cách 2: Chạy trực tiếp bằng Flutter (Hot Reload khi lập trình)
```powershell
flutter pub get
flutter run -d edge --web-port 3000
```
> Máy này **chưa cài Chrome**, nên dùng device `edge`. Nếu muốn tự mở trình duyệt thủ công, dùng `flutter run -d web-server --web-port 3000`.

---

## ✅ Lệnh Kiểm Thử (Verification Commands)

Chạy tại `HealthApp/health_app`:

```powershell
flutter pub get                                  # Cài dependencies
flutter analyze                                  # Lint & phân tích tĩnh
flutter test                                     # Chạy unit + widget test
flutter build web --release --no-tree-shake-icons # Build bản web production
```

**Kết quả kiểm thử thực tế (2026-08-06, Flutter 3.44.8):**

| Lệnh | Kết quả |
| :--- | :--- |
| `flutter pub get` | ✅ `Got dependencies!` (37 package có bản mới hơn nhưng bị ràng buộc constraint) |
| `flutter analyze` | ✅ 22 issues — toàn bộ ở mức `info` (`deprecated_member_use` của `withOpacity` trong `lib/main.dart`), **0 error / 0 warning** |
| `flutter test` | ✅ **23/23 test passed** (`wger_models_test`, `wger_service_test`, `action_card_widget_test`, `widget_test`) |
| `flutter build web --release --no-tree-shake-icons` | ✅ `Built build\web` (~48s) |

> Ghi chú: log `⚠️ Session restore failed: [core/no-app] No Firebase App '[DEFAULT]'` trong smoke test là hành vi mong đợi vì môi trường test không khởi tạo Firebase; test vẫn pass.

---

## 🔗 Liên Kết Truy Cập Dịch Vụ

Sau khi các dịch vụ đã hoạt động, bạn có thể kiểm tra qua các địa chỉ sau:

| Dịch vụ | Địa chỉ URL | Ghi chú |
| :--- | :--- | :--- |
| **Flutter Web Client** | **[http://localhost:3000](http://localhost:3000)** | Giao diện giả lập điện thoại (16:9, 19.5:9, 21:9) |
| **Backend API Interactive Docs** | **[http://localhost:8080/docs](http://localhost:8080/docs)** | Tài liệu API FastAPI Swagger UI |
| **Backend Health Check** | **[http://localhost:8080/health](http://localhost:8080/health)** | Kiểm tra trạng thái LLM & DB |

---

## 📱 Khởi Chạy Trên Giả Lập Android (LDPlayer 9)
Nếu bạn muốn chạy ứng dụng trực tiếp trên giả lập android (để test tính năng native hoặc Google Auth), tham khảo hướng dẫn chi tiết tại:
- **[RUN_GUIDE_LDPLAYER.md](./RUN_GUIDE_LDPLAYER.md)**
