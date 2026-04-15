# HƯỚNG DẪN NHANH - CHATBOT Y TẾ

## 🚀 Bắt đầu nhanh (3 bước)

### Bước 1: Cài đặt môi trường
```bash
scripts\setup_fresh_venv.bat
```

### Bước 2: Train model
```bash
scripts\train_final.bat
```

### Bước 3: Chạy chatbot
```bash
# Terminal 1 - Action server
venv\Scripts\activate
rasa run actions

# Terminal 2 - Chatbot
venv\Scripts\activate
rasa shell
```

## 💬 Test chatbot

Sau khi chạy `rasa shell`, thử các câu hỏi:

```
Bạn: Xin chào
Bạn: Tôi bị tiêu chảy phải làm sao
Bạn: Cách chữa viêm xoang
Bạn: Tính BMI cho tôi cao 170 nặng 65
Bạn: Tôi vừa tập chạy bộ 30 phút
Bạn: Xem tổng quan sức khỏe
Bạn: Tạm biệt
```

## 📁 Cấu trúc project

```
MedicalBot/
├── actions/           # Custom actions (BMI, health tracking)
├── data/              # Training data (4,598 FAQ intents)
├── docs/              # Tài liệu chi tiết
├── scripts/           # Scripts tiện ích
├── config.yml         # RASA configuration
├── domain.yml         # Domain (intents, entities, responses)
├── medical_knowledge_base.json  # 8,756 bài viết y tế
└── requirements.txt   # Dependencies
```

## 🛠️ Yêu cầu hệ thống

- Windows 10/11
- Python 3.10
- RAM: 4GB+ (khuyến nghị 8GB)
- Disk: 2GB+ free space

## 📚 Tài liệu đầy đủ

- [Hướng dẫn sử dụng](docs/HUONG_DAN_SU_DUNG.md)
- [Setup Windows](docs/SETUP_WINDOWS.md)
- [Checklist dự án](docs/CHECKLIST.md)

## ⚠️ Xử lý lỗi

### Lỗi: "No module named 'pkg_resources'"
```bash
pip uninstall setuptools -y
pip install setuptools==65.5.0
```

### Lỗi: "duplicate key in domain.yml"
```bash
python scripts\fix_duplicate_responses.py
```

### Lỗi: Python version
- RASA 3.5.17 yêu cầu Python 3.8-3.10
- Dùng: `py -3.10 -m venv venv`

## 📊 Tính năng

### 1. Tư vấn y tế (FAQ)
- 4,598 chủ đề y tế
- Trả lời về bệnh lý, triệu chứng, điều trị

### 2. Theo dõi sức khỏe
- Tính BMI và phân loại
- Ghi nhận dinh dưỡng (bữa ăn, calories)
- Ghi nhận vận động (loại, thời gian, calories đốt)
- Xem tổng quan sức khỏe cá nhân

## 📞 Hỗ trợ

- Đề tài: THS2025-78
- Sinh viên: Lê Nhật Bằng
- Giảng viên: TS. Thái Minh Tuấn
- Trường: Đại học Cần Thơ
