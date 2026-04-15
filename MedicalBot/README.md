# Chatbot Y Tế - RASA

Chatbot tư vấn y tế với 4,598 intents từ 8,756 bài viết y tế Việt Nam.

## 🚀 Quick Start

```bash
# 1. Setup môi trường
scripts\setup_fresh_venv.bat

# 2. Train model
scripts\train_final.bat

# 3. Chạy chatbot
# Terminal 1: rasa run actions
# Terminal 2: rasa shell
```

## 📚 Tài liệu

- [Hướng dẫn sử dụng](docs/HUONG_DAN_SU_DUNG.md) - Hướng dẫn đầy đủ
- [Setup Windows](docs/SETUP_WINDOWS.md) - Cài đặt trên Windows
- [Checklist](docs/CHECKLIST.md) - Tổng quan dự án
- [Cấu trúc project](PROJECT_STRUCTURE.md) - Cấu trúc thư mục

## 🎯 Tính năng

### Tư vấn y tế (FAQ)
- 4,598 chủ đề y tế
- Trả lời câu hỏi về bệnh lý, triệu chứng, điều trị

### Theo dõi sức khỏe
- Tính BMI và phân loại
- Ghi nhận dinh dưỡng
- Ghi nhận vận động
- Xem tổng quan sức khỏe

## 📊 Thống kê

- Knowledge Base: 8,756 bài viết
- FAQ Intents: 4,598 intents
- Training Examples: ~46,000 câu
- Custom Actions: 6 actions

## 🛠️ Yêu cầu

- Python 3.10
- RASA 3.5.17
- RAM: 4GB+ (khuyến nghị 8GB)

## 📝 Thông tin

- Đề tài: THS2025-78
- Sinh viên: Lê Nhật Bằng
- Giảng viên: TS. Thái Minh Tuấn
- Trường: Đại học Cần Thơ
