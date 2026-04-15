# Hướng dẫn sử dụng Scripts

## Scripts đã được tối ưu

### 1. run_fast.bat ⚡ (NHANH NHẤT)
**Mục đích**: Chạy app nhanh nhất có thể, bỏ qua tất cả kiểm tra

**Khi nào dùng**:
- Đang phát triển và cần test nhanh
- Đã chạy setup trước đó
- Không có thay đổi dependencies

**Tốc độ**: ⚡⚡⚡⚡⚡ (Nhanh nhất)

```bash
run_fast.bat
```

---

### 2. dev.bat 🔥 (HOT RELOAD)
**Mục đích**: Development mode với hot reload

**Tính năng**:
- Hot reload (nhấn 'r')
- Hot restart (nhấn 'R')
- Verbose logging
- Tự động reload khi save file

**Khi nào dùng**:
- Đang code và muốn thấy thay đổi ngay lập tức
- Debug và cần log chi tiết

**Tốc độ**: ⚡⚡⚡⚡ (Rất nhanh)

```bash
dev.bat
```

---

### 3. run.bat 🚀 (CHUẨN)
**Mục đích**: Chạy app với kiểm tra thông minh

**Tính năng**:
- Kiểm tra Flutter SDK
- Chỉ pub get nếu cần thiết (kiểm tra .dart_tool)
- Tự động chọn Chrome
- Chỉ pause khi có lỗi

**Khi nào dùng**:
- Lần đầu chạy trong ngày
- Sau khi pull code mới
- Không chắc dependencies đã cài chưa

**Tốc độ**: ⚡⚡⚡ (Nhanh)

```bash
run.bat
```

---

### 4. setup.bat 🔧 (SETUP)
**Mục đích**: Cài đặt lần đầu

**Khi nào dùng**:
- Lần đầu clone project
- Sau khi xóa node_modules/.dart_tool

**Tốc độ**: ⚡⚡ (Chậm, nhưng chỉ chạy 1 lần)

```bash
setup.bat
```

---

### 5. build_apk.bat 📦 (BUILD)
**Mục đích**: Build APK release đã tối ưu

**Tính năng mới**:
- Tùy chọn clean (y/N) - mặc định không clean
- Split per ABI - tạo APK riêng cho từng CPU
- Obfuscate - mã hóa code
- Split debug info - giảm kích thước APK

**Khi nào dùng**:
- Cần build APK để test trên thiết bị thật
- Chuẩn bị release

**Tốc độ**: ⚡ (Chậm, nhưng tối ưu APK)

```bash
build_apk.bat
```

---

### 6. clean_build.bat 🧹 (CLEAN)
**Mục đích**: Xóa toàn bộ cache và build lại từ đầu

**Khi nào dùng**:
- Gặp lỗi lạ không giải quyết được
- Sau khi update Flutter SDK
- Dependencies bị conflict

**Tốc độ**: ⚡ (Rất chậm)

```bash
clean_build.bat
```


## So sánh tốc độ

| Script | Thời gian khởi động | Hot Reload | Kiểm tra | Dùng khi |
|--------|-------------------|------------|----------|----------|
| run_fast.bat | ~5s | ✅ | ❌ | Đang dev |
| dev.bat | ~7s | ✅✅ | ❌ | Đang code |
| run.bat | ~10s | ✅ | ✅ | Chạy bình thường |
| setup.bat | ~30s | ❌ | ✅✅ | Lần đầu |
| build_apk.bat | ~2-5 phút | ❌ | ✅ | Build release |
| clean_build.bat | ~1-2 phút | ❌ | ✅✅ | Fix lỗi |

## Workflow khuyến nghị

### Workflow hàng ngày (Development)
1. Sáng: Chạy `run.bat` lần đầu
2. Đang code: Dùng `dev.bat` với hot reload
3. Test nhanh: Dùng `run_fast.bat`

### Workflow build
1. Test local: `run.bat`
2. Build APK: `build_apk.bat` (chọn N khi hỏi clean)
3. Nếu lỗi: `clean_build.bat` rồi build lại

## Tips tối ưu thêm

### 1. Tăng tốc pub get
Thêm vào file `pubspec.yaml`:
```yaml
dependency_overrides:
  # Chỉ dùng khi cần thiết
```

### 2. Tăng RAM cho Flutter
Thêm vào biến môi trường:
```
FLUTTER_TOOL_ARGS=--verbose
```

### 3. Sử dụng Flutter DevTools
```bash
flutter pub global activate devtools
flutter pub global run devtools
```

### 4. Cache dependencies
Dependencies đã được cache tự động tại:
- Windows: `%LOCALAPPDATA%\Pub\Cache`
- Không cần xóa trừ khi gặp lỗi

## Troubleshooting

### Script chạy chậm?
1. Kiểm tra antivirus (có thể scan Flutter files)
2. Chạy `clean_build.bat` để xóa cache
3. Đảm bảo SSD có đủ dung lượng

### Hot reload không hoạt động?
1. Dùng `dev.bat` thay vì `run_fast.bat`
2. Nhấn 'r' trong terminal
3. Nếu vẫn không được, nhấn 'R' (restart)
