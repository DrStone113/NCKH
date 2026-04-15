# THÔNG TIN DỰ ÁN - CHATBOT Y TẾ

## 📋 Thông tin chung

- **Đề tài**: THS2025-78
- **Tên đề tài**: Xây dựng chatbot tư vấn y tế sử dụng RASA Framework
- **Sinh viên**: Lê Nhật Bằng
- **Giảng viên hướng dẫn**: TS. Thái Minh Tuấn
- **Trường**: Đại học Cần Thơ
- **Thời gian**: 05/2025 - 10/2025
- **Ngân sách**: 15,000,000 VND

## 📁 Cấu trúc project

```
MedicalBot/
│
├── 📂 actions/                      # Custom actions
│   └── actions.py                   # 6 actions: search, BMI, nutrition, exercise, health summary
│
├── 📂 data/                         # Training data
│   ├── nlu.yml                      # Basic NLU (13 intents)
│   ├── nlu_faq.yml                  # FAQ data (4,598 intents)
│   ├── rules.yml                    # Conversation rules
│   └── stories.yml                  # Conversation stories
│
├── 📂 docs/                         # Tài liệu
│   ├── CHECKLIST.md                # Checklist hoàn thành
│   ├── HUONG_DAN_SU_DUNG.md       # Hướng dẫn đầy đủ
│   └── SETUP_WINDOWS.md           # Hướng dẫn cài đặt
│
├── 📂 scripts/                      # Scripts tiện ích
│   ├── start.bat                    # Menu khởi động
│   ├── setup_fresh_venv.bat        # Setup môi trường
│   ├── train_final.bat             # Train model
│   ├── train_data_generator.py     # Tạo training data
│   ├── merge_domain.py             # Merge domain files
│   └── fix_duplicate_responses.py  # Fix duplicate responses
│
├── 📂 raw_data/                     # Dữ liệu crawl gốc (không cần cho RASA)
│   ├── app.py, app2.py             # Web crawlers
│   ├── converter.py, info.py       # Data processors
│   └── *.csv, *.json               # Raw data files
│
├── 📂 venv/                         # Virtual environment (Python 3.10)
│
├── 📄 config.yml                    # RASA pipeline config
├── 📄 domain.yml                    # Domain (intents, entities, slots, responses)
├── 📄 endpoints.yml                 # Endpoints config
├── 📄 credentials.yml               # Channel credentials
├── 📄 medical_knowledge_base.json  # Knowledge base (8,756 bài viết, 22MB)
├── 📄 requirements.txt              # Python dependencies
├── 📄 README.md                     # README chính
├── 📄 QUICK_START.md               # Hướng dẫn nhanh
└── 📄 PROJECT_INFO.md              # File này
```

## 📊 Thống kê dự án

### Dữ liệu
- **Knowledge Base**: 8,756 bài viết y tế từ các nguồn uy tín
- **FAQ Intents**: 4,598 intents được tạo tự động
- **Training Examples**: ~46,000 câu (4,598 intents × 10 examples)
- **Kích thước KB**: 22MB

### RASA Components
- **Intents**: 13 intents (greet, goodbye, faq, calculate_bmi, log_nutrition, log_exercise, view_health_summary, ...)
- **Entities**: 9 entities (disease_name, symptom, height, weight, meal_type, calories, exercise_type, duration, body_part)
- **Slots**: 9 slots
- **Custom Actions**: 6 actions
- **Responses**: 4,600+ responses

### Công nghệ
- **Framework**: RASA 3.5.17
- **Python**: 3.10.9
- **NLU Pipeline**: WhitespaceTokenizer, DIETClassifier, ResponseSelector
- **Policies**: MemoizationPolicy, RulePolicy, TEDPolicy, UnexpecTEDIntentPolicy

## 🎯 Tính năng chính

### 1. Tư vấn y tế (FAQ)
- 4,598 chủ đề y tế đa dạng
- Trả lời câu hỏi về bệnh lý, triệu chứng, điều trị, phòng ngừa
- Hỗ trợ tiếng Việt tự nhiên

### 2. Theo dõi sức khỏe
- **BMI Calculator**: Tính và phân loại chỉ số BMI (thiếu cân, bình thường, thừa cân, béo phì)
- **Nutrition Tracking**: Ghi nhận bữa ăn (sáng, trưa, tối, ăn vặt) và calories
- **Exercise Tracking**: Ghi nhận vận động (chạy bộ, đi bộ, bơi lội, gym, yoga...) và ước tính calories đốt cháy
- **Health Summary**: Xem tổng quan sức khỏe cá nhân (BMI, số bữa ăn, số lần tập, tổng calories)

### 3. Hội thoại tự nhiên
- Chào hỏi, tạm biệt
- Xác nhận, từ chối
- Fallback khi không hiểu

## 🚀 Hướng dẫn sử dụng

### Quick Start (3 bước)
```bash
# 1. Setup
scripts\setup_fresh_venv.bat

# 2. Train
scripts\train_final.bat

# 3. Run
# Terminal 1: rasa run actions
# Terminal 2: rasa shell
```

### Chi tiết
Xem [QUICK_START.md](QUICK_START.md) hoặc [docs/HUONG_DAN_SU_DUNG.md](docs/HUONG_DAN_SU_DUNG.md)

## 📝 Ghi chú kỹ thuật

### Yêu cầu hệ thống
- Windows 10/11
- Python 3.10 (RASA 3.5.17 không hỗ trợ Python 3.11+)
- RAM: 4GB+ (khuyến nghị 8GB)
- Disk: 2GB+ free space

### Vấn đề đã giải quyết
1. ✅ PyYAML build error trên Windows → Dùng PyYAML 6.0.1+
2. ✅ pkg_resources error → Dùng setuptools==65.5.0
3. ✅ Duplicate responses trong domain.yml → Script fix_duplicate_responses.py
4. ✅ Python version incompatibility → Virtual environment với Python 3.10

### Files quan trọng
- `medical_knowledge_base.json` - Không được xóa (22MB)
- `domain.yml` - Chứa tất cả responses (đã merge từ domain_faq.yml)
- `data/nlu_faq.yml` - 4,598 FAQ intents (3.67MB)
- `actions/actions.py` - 6 custom actions

## ✅ Checklist hoàn thành

- [x] Thu thập dữ liệu y tế (8,756 bài viết)
- [x] Xử lý và làm sạch dữ liệu
- [x] Tạo training data tự động (4,598 intents)
- [x] Cấu hình RASA pipeline
- [x] Xây dựng custom actions
- [x] Tính năng theo dõi sức khỏe (BMI, nutrition, exercise)
- [x] Tài liệu hướng dẫn đầy đủ
- [x] Scripts tiện ích
- [x] Dọn dẹp và tổ chức project

## 📞 Liên hệ

- Email: [email sinh viên]
- Giảng viên: TS. Thái Minh Tuấn
- Trường: Đại học Cần Thơ
