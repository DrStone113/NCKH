# 🚀 HƯỚNG DẪN KHỞI ĐỘNG NHANH

## Yêu cầu hệ thống

- **Docker Desktop** đã cài đặt và đang chạy
- **GPU NVIDIA** (khuyến nghị) hoặc CPU (chậm hơn)
- **RAM**: Tối thiểu 8GB, khuyến nghị 16GB
- **Disk**: Tối thiểu 10GB trống

---

## 🎯 Khởi động lần đầu (3 bước)

### Bước 1: Chạy script tự động
```bash
cd NCKH/HealthApp/ai_backend
docker-start.bat
```

Chọn **Option 1** - First-time setup

Script sẽ tự động:
- ✅ Khởi động PostgreSQL + pgvector extension
- ✅ Tải model Llama 3.2 (~2GB)
- ✅ Load dữ liệu món ăn Việt Nam + tạo vector embeddings (384 chiều)
- ✅ Sync bài tập từ Wger + tạo embeddings
- ✅ Khởi động backend API với RAG support

### Bước 2: Đợi khởi động hoàn tất

Xem logs để biết khi nào sẵn sàng:
```bash
docker logs -f health_backend
```

Khi thấy dòng này là OK:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Bước 3: Test API

Mở trình duyệt: http://localhost:8080/health

Kết quả mong đợi:
```json
{"status": "ok", "model": "llama3.2"}
```

---

## 🔄 Khởi động lần sau

Chỉ cần chạy:
```bash
docker-start.bat
```

Chọn **Option 2** - Normal startup

---

## 📱 Kết nối Flutter App

Trong Flutter app, cấu hình API endpoint:

```dart
// lib/config/api_config.dart
class ApiConfig {
  static const String baseUrl = 'http://localhost:8080';
  // Hoặc nếu test trên điện thoại thật:
  // static const String baseUrl = 'http://192.168.1.xxx:8080';
}
```

---

## 🛠️ Các lệnh hữu ích

### Xem logs
```bash
# Backend logs
docker logs -f health_backend

# Ollama logs
docker logs -f health_ollama

# Database logs
docker logs -f health_postgres
```

### Kiểm tra trạng thái
```bash
docker ps
```

### Dừng hệ thống
```bash
docker-start.bat
# Chọn Option 4 - Stop all containers
```

### Reset toàn bộ (xóa dữ liệu)
```bash
docker-start.bat
# Chọn Option 5 - Reset everything
```

---

## 🐛 Xử lý lỗi thường gặp

### Lỗi: "Cannot connect to Docker daemon"
**Giải pháp**: Mở Docker Desktop và đợi nó khởi động xong

### Lỗi: "Port 8080 already in use"
**Giải pháp**: 
```bash
# Tìm process đang dùng port
netstat -ano | findstr :8080

# Kill process (thay PID bằng số thực tế)
taskkill /PID <PID> /F
```

### Lỗi: "Ollama model not found"
**Giải pháp**: Pull model thủ công
```bash
docker exec -it health_ollama ollama pull llama3.2
```

### Backend khởi động chậm
**Nguyên nhân**: Đang tải embedding model lần đầu (~500MB)
**Giải pháp**: Đợi thêm 2-3 phút, xem logs để theo dõi

---

## 📊 Kiểm tra GPU

Nếu có GPU NVIDIA:
```bash
# Kiểm tra GPU có được nhận không
docker exec -it health_ollama nvidia-smi

# Xem Ollama có dùng GPU không
docker logs health_ollama | findstr "GPU"
```

---

## 🌐 Deploy lên Internet (Production)

Xem hướng dẫn chi tiết trong [DOCKER_README.md](DOCKER_README.md#production-deployment)

Tóm tắt:
1. Tạo Cloudflare Tunnel
2. Thêm token vào `.env`
3. Chạy: `docker-start.bat` → Option 3

---

## 📚 Tài liệu chi tiết

- [DOCKER_README.md](DOCKER_README.md) - Hướng dẫn đầy đủ về Docker
- [GPU_SETUP.md](GPU_SETUP.md) - Cấu hình GPU NVIDIA
- [AI_ANALYZER_README.md](backend/services/AI_ANALYZER_README.md) - Cách AI phân tích dinh dưỡng

---

## 💡 Tips

1. **Lần đầu khởi động mất 5-10 phút** (tải model + data)
2. **Lần sau chỉ mất 30 giây** (data đã có sẵn)
3. **Dùng GPU nhanh hơn CPU ~10 lần**
4. **Model Llama 3.2 nhẹ hơn Llama 3 (~2GB vs ~4.7GB)**
5. **Logs 404 từ Hugging Face là bình thường** (không phải lỗi)

---

## ❓ Cần trợ giúp?

1. Kiểm tra logs: `docker logs -f health_backend`
2. Xem troubleshooting trong [DOCKER_README.md](DOCKER_README.md#troubleshooting)
3. Kiểm tra Docker Desktop có đang chạy không
4. Restart Docker Desktop và thử lại
