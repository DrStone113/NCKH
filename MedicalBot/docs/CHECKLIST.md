# CHECKLIST DỰ ÁN CHATBOT Y TẾ

## ✅ ĐÃ HOÀN THÀNH

### 1. ✅ Sinh NLU Data từ Knowledge Base
- [x] Script `train_data_generator.py` với trích xuất topic thông minh
- [x] 4,598 intents FAQ từ 8,756 bài viết y tế
- [x] Câu hỏi tự nhiên (10 variations/topic)
- [x] Responses rút gọn dưới 500 ký tự
- [x] File output: `data/nlu_faq.yml`, `domain_faq.yml`

### 2. ✅ Tạo đầy đủ các file RASA config
- [x] `config.yml` - Pipeline cho tiếng Việt với DIETClassifier, ResponseSelector
- [x] `domain.yml` - Intents, entities, slots, responses, actions
- [x] `data/nlu.yml` - NLU training data cơ bản + health tracking
- [x] `data/rules.yml` - Conversation rules + health tracking rules
- [x] `data/stories.yml` - Conversation flows
- [x] `endpoints.yml` - Action server configuration
- [x] `credentials.yml` - Channel credentials

### 3. ✅ Xây dựng Custom Actions
- [x] `actions/actions.py` với 6 custom actions:
  - `ActionSearchMedicalInfo` - Tìm kiếm thông tin y tế
  - `ActionDefaultFallback` - Xử lý khi không hiểu
  - `ActionCalculateBMI` - Tính chỉ số BMI
  - `ActionLogNutrition` - Ghi nhận dinh dưỡng
  - `ActionLogExercise` - Ghi nhận vận động
  - `ActionViewHealthSummary` - Xem tổng quan sức khỏe

### 4. ✅ Thêm tính năng theo dõi sức khỏe
- [x] Tính BMI với phân loại (thiếu cân, bình thường, thừa cân, béo phì)
- [x] Ghi nhận bữa ăn (sáng, trưa, tối, ăn vặt)
- [x] Ghi nhận vận động (chạy bộ, đi bộ, bơi lội, gym, yoga...)
- [x] Ước tính calories đốt cháy
- [x] Xem tổng quan sức khỏe (BMI, số bữa ăn, số lần tập, calories)
- [x] Lưu log vào `health_logs.json`

### 5. ✅ Tài liệu và hướng dẫn
- [x] `README.md` - Tài liệu dự án (tiếng Anh)
- [x] `HUONG_DAN_SU_DUNG.md` - Hướng dẫn chi tiết (tiếng Việt)
- [x] `SETUP_WINDOWS.md` - Hướng dẫn cài đặt trên Windows
- [x] `requirements.txt` - Dependencies
- [x] `start.bat` - Menu khởi động nhanh
- [x] `setup_venv.bat` - Script tự động setup virtual environment
- [x] `merge_domain.py` - Script merge domain files

## 📋 CẤU TRÚC DỰ ÁN

```
MedicalBot/
├── actions/
│   └── actions.py                    ✅ 6 custom actions
├── data/
│   ├── nlu.yml                       ✅ Basic + health tracking intents
│   ├── nlu_faq.yml                   ✅ 4,598 FAQ intents
│   ├── rules.yml                     ✅ Rules + health tracking rules
│   └── stories.yml                   ✅ Conversation flows
├── config.yml                        ✅ RASA pipeline config
├── domain.yml                        ✅ Domain với health tracking
├── domain_faq.yml                    ✅ FAQ responses (cần merge)
├── endpoints.yml                     ✅ Endpoints config
├── credentials.yml                   ✅ Credentials config
├── medical_knowledge_base.json       ✅ 8,756 bài viết y tế
├── train_data_generator.py           ✅ Script sinh training data
├── merge_domain.py                   ✅ Script merge domain
├── start.bat                         ✅ Menu khởi động
├── setup_venv.bat                    ✅ Setup virtual environment
├── requirements.txt                  ✅ Dependencies
├── README.md                         ✅ Tài liệu dự án
├── HUONG_DAN_SU_DUNG.md             ✅ Hướng dẫn sử dụng
├── SETUP_WINDOWS.md                  ✅ Hướng dẫn cài đặt Windows
└── CHECKLIST.md                      ✅ File này
```

## 🎯 TÍNH NĂNG CHÍNH

### Tư vấn y tế (FAQ)
- 4,598 chủ đề y tế từ knowledge base
- Trả lời câu hỏi về bệnh lý, triệu chứng, điều trị
- Hỗ trợ tiếng Việt tự nhiên

### Theo dõi sức khỏe
- **BMI Calculator**: Tính và phân loại chỉ số BMI
- **Nutrition Tracking**: Ghi nhận bữa ăn và calories
- **Exercise Tracking**: Ghi nhận vận động và ước tính calories đốt cháy
- **Health Summary**: Xem tổng quan sức khỏe cá nhân

### Hội thoại tự nhiên
- Chào hỏi, tạm biệt
- Xác nhận, từ chối
- Fallback khi không hiểu

## 📊 THỐNG KÊ

- **Knowledge Base**: 8,756 bài viết y tế
- **FAQ Intents**: 4,598 intents
- **Training Examples**: ~46,000 câu (4,598 × 10)
- **Custom Actions**: 6 actions
- **Entities**: 9 entities (disease_name, symptom, height, weight, meal_type, calories, exercise_type, duration, body_part)
- **Slots**: 9 slots
- **Intents**: 13 intents (greet, goodbye, affirm, deny, mood_great, mood_unhappy, bot_challenge, ask_health_info, faq, calculate_bmi, log_nutrition, log_exercise, view_health_summary)

## 🚀 BƯỚC TIẾP THEO

### Để chạy chatbot:

1. **Cài đặt môi trường** (xem SETUP_WINDOWS.md)
   ```bash
   # Tạo virtual environment với Python 3.10
   py -3.10 -m venv venv
   venv\Scripts\activate
   
   # Cài đặt packages
   pip install rasa-sdk==3.6.0
   pip install pyyaml==6.0.1
   pip install rasa==3.6.0
   ```

2. **Merge domain files**
   ```bash
   python merge_domain.py
   ```

3. **Train model**
   ```bash
   rasa train
   ```

4. **Chạy action server** (Terminal 1)
   ```bash
   rasa run actions
   ```

5. **Chạy chatbot** (Terminal 2)
   ```bash
   rasa shell
   ```

## ⚠️ LƯU Ý

### Vấn đề Python Version
- RASA 3.6.0 yêu cầu Python 3.8-3.10
- Không hỗ trợ Python 3.11+
- Bạn đang có Python 3.13.4 (mặc định) và Python 3.10.9
- Phải dùng `py -3.10` hoặc virtual environment với Python 3.10

### Vấn đề PyYAML trên Windows
- PyYAML 5.4.1 không build được trên Python 3.10 Windows
- Giải pháp: Cài PyYAML 6.0+ trước khi cài RASA

### Nếu gặp lỗi
- Xem SETUP_WINDOWS.md để biết chi tiết
- Có thể dùng RASA 3.5.17 thay vì 3.6.0
- Hoặc cài đặt trên Linux/WSL2

## 📝 THÔNG TIN DỰ ÁN

- **Đề tài**: THS2025-78
- **Sinh viên**: Lê Nhật Bằng
- **Giảng viên**: TS. Thái Minh Tuấn
- **Trường**: Đại học Cần Thơ
- **Thời gian**: 05/2025 - 10/2025
- **Ngân sách**: 15,000,000 VND

## ✨ HOÀN THÀNH 100%

Tất cả 4 yêu cầu đã được hoàn thành:
1. ✅ Chạy train_data_generator.py để sinh NLU data
2. ✅ Tạo đầy đủ các file RASA config
3. ✅ Xây dựng custom actions
4. ✅ Thêm tính năng theo dõi sức khỏe (BMI, dinh dưỡng, vận động)

Dự án sẵn sàng để train và deploy!
