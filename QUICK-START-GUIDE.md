# 🚀 Hướng Dẫn Khởi Động Nhanh HealthApp

## 📋 Các File Tiện Ích

### 1. `quick-start.bat` - Khởi động nhanh
**Chức năng:** Khởi động tất cả các service (Ollama, Backend, Flutter) một cách tự động

**Cách dùng:**
```bash
# Chỉ cần double-click hoặc chạy:
quick-start.bat
```

**Đặc điểm:**
- ✅ Tự động kiểm tra service đã chạy chưa (không khởi động lại nếu đã chạy)
- ✅ Chạy các service trong cửa sổ riêng biệt (minimized)
- ✅ Tự động đóng sau 5 giây, các service vẫn chạy nền
- ✅ An toàn cho Cloud PC - không ảnh hưởng Remote Desktop

### 2. `stop-all.bat` - Dừng tất cả
**Chức năng:** Dừng tất cả các service đang chạy

**Cách dùng:**
```bash
# Double-click hoặc chạy:
stop-all.bat
```

**Đặc điểm:**
- ✅ Dừng service theo port (an toàn)
- ✅ Đóng các cửa sổ terminal đã mở
- ✅ Tự động đóng sau 3 giây

### 3. `check-status.bat` - Kiểm tra trạng thái
**Chức năng:** Xem trạng thái các service và quản lý

**Cách dùng:**
```bash
# Double-click hoặc chạy:
check-status.bat
```

**Tính năng:**
- 📊 Hiển thị trạng thái real-time của từng service
- 🔄 Làm mới trạng thái (phím R)
- ▶️ Khởi động tất cả (phím S)
- ⏹️ Dừng tất cả (phím X)
- ❌ Thoát (phím Q)

### 4. `dev.bat` - Menu đầy đủ (có sẵn)
**Chức năng:** Menu đầy đủ với nhiều tùy chọn (setup, database, sync wger, logs...)

**Khi nào dùng:**
- Lần đầu cài đặt (setup dependencies, database)
- Cần xem logs chi tiết
- Cần sync dữ liệu wger
- Cần chạy từng service riêng lẻ

---

## 🎯 Quy Trình Sử Dụng Hàng Ngày

### Lần đầu tiên (Setup)
```bash
1. Chạy dev.bat
2. Chọn [4] - Cài đặt Dependencies
3. Chọn [5] - Setup Database
4. Chọn [6] - Đồng bộ dữ liệu Wger (tùy chọn)
```

### Mỗi ngày làm việc
```bash
# Sáng - Khởi động
quick-start.bat

# Làm việc...

# Tối - Dừng lại
stop-all.bat
```

### Kiểm tra nhanh
```bash
# Xem service nào đang chạy
check-status.bat
```

---

## 🌐 Các URL Quan Trọng

| Service | URL | Mô tả |
|---------|-----|-------|
| **Backend API** | http://localhost:8080 | FastAPI Backend |
| **API Docs** | http://localhost:8080/docs | Swagger UI |
| **Flutter Web** | http://localhost:3000 | Ứng dụng web |
| **Ollama** | http://localhost:11434 | AI Model Server |

---

## 🔧 Xử Lý Sự Cố

### Service không khởi động?
```bash
1. Chạy check-status.bat để xem service nào bị lỗi
2. Chạy stop-all.bat để dừng tất cả
3. Chạy quick-start.bat để khởi động lại
```

### Port bị chiếm?
```bash
# Dừng tất cả service
stop-all.bat

# Hoặc dừng thủ công theo port:
netstat -ano | findstr :8080
taskkill /f /pid <PID>
```

### Cần xem logs?
```bash
# Chạy dev.bat và chọn [9] - Xem Logs
dev.bat
```

### Backend lỗi?
```bash
# Xem logs chi tiết
cd HealthApp\ai_backend\backend
venv\Scripts\python.exe -m uvicorn main:app --reload
```

### Flutter lỗi?
```powershell
# Kiểm tra SDK & PATH (Flutter 3.44.8 cài tại C:\flutter)
flutter --version
flutter doctor -v

# Chạy với logs chi tiết (máy chưa có Chrome → dùng edge)
cd HealthApp\health_app
flutter run -d edge --web-port 3000 -v

# Nếu lỗi dependency / cache
flutter clean
flutter pub get
```

---

## 💡 Tips & Tricks

### 1. Tạo shortcut trên Desktop
- Right-click `quick-start.bat` → Send to → Desktop (create shortcut)
- Đổi tên thành "🚀 Start HealthApp"

### 2. Chạy khi Windows khởi động
- Win + R → `shell:startup`
- Copy shortcut của `quick-start.bat` vào folder này

### 3. Kiểm tra nhanh bằng browser
- Bookmark: http://localhost:8080/docs
- Nếu mở được = Backend đang chạy

### 4. Cloud PC - Lưu ý
- ✅ Các file .bat này an toàn cho Cloud PC
- ✅ Không ảnh hưởng Remote Desktop Connection
- ✅ Chỉ dừng service theo port cụ thể
- ⚠️ Đừng dùng `taskkill /f /im cmd.exe` (sẽ đóng remote)

---

## 📞 Hỗ Trợ

Nếu gặp vấn đề:
1. Chạy `check-status.bat` để xem trạng thái
2. Chạy `dev.bat` → [9] để xem logs
3. Kiểm tra file logs trong folder `logs/`

---

## 🎨 Màu Sắc Terminal

- 🟢 **Xanh lá** (0B) - Quick Start
- 🔴 **Đỏ** (0C) - Stop All
- 🟡 **Vàng** (0E) - Check Status
- 🟢 **Xanh lá** (0A) - Dev Menu

---

**Chúc bạn code vui vẻ! 🎉**
