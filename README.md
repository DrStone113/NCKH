# HealthApp — Ứng dụng quản lý sức khỏe AI

Ứng dụng Flutter + FastAPI + Ollama cho phép theo dõi dinh dưỡng, tập luyện và tư vấn sức khỏe bằng AI.

## Yêu cầu cài đặt

| Công cụ | Phiên bản | Link |
|---------|-----------|------|
| Flutter | ≥ 3.0 | https://flutter.dev/docs/get-started/install |
| Python | ≥ 3.10 | https://python.org |
| PostgreSQL | ≥ 14 | https://postgresql.org |
| Ollama | Latest | https://ollama.com |

## Khởi động nhanh

```bat
quick-start.bat
```

Truy cập: http://localhost:3000

---

## Cài đặt thủ công

### 1. Backend (FastAPI)

```bat
cd HealthApp\ai_backend\backend

# Tạo virtual environment
python -m venv venv
venv\Scripts\activate

# Cài dependencies
pip install -r requirements.txt

# Cấu hình môi trường
copy ..\env.example .env
# Chỉnh sửa .env với thông tin database của bạn

# Tạo database
psql -U postgres -c "CREATE DATABASE health_db;"
psql -U postgres -d health_db -f db\init.sql

# Chạy server
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 2. Ollama (LLM)

```bat
# Cài Ollama từ https://ollama.com
ollama pull llama3:8b-instruct-q4_K_M
ollama serve
```

### 3. Flutter App

```bat
cd HealthApp\health_app

# Cài dependencies
flutter pub get

# Cấu hình Firebase (xem HealthApp\setup_firebase_guide.md)

# Chạy web
flutter run -d web-server --web-port 3000
```

---

## Cấu trúc project

```
NCKH/
├── quick-start.bat          # Khởi động tất cả dịch vụ
├── stop-all.bat             # Dừng tất cả dịch vụ
├── Dataset/
│   ├── food_data.csv        # Bảng thành phần thực phẩm Việt Nam
│   └── convert_to_dart.py   # Script convert dataset → Dart code
└── HealthApp/
    ├── ai_backend/          # FastAPI + Ollama backend
    │   ├── backend/
    │   │   ├── main.py
    │   │   ├── requirements.txt
    │   │   ├── routers/     # API endpoints
    │   │   ├── services/    # Business logic (AI, RAG, prompt)
    │   │   ├── models/      # Pydantic schemas
    │   │   └── db/          # Database + session store
    │   ├── .env.example     # Template cấu hình
    │   └── docker-compose.yml
    └── health_app/          # Flutter app
        ├── lib/
        │   ├── screens/     # UI screens
        │   ├── providers/   # State management
        │   ├── models/      # Data models
        │   ├── services/    # API services
        │   └── widgets/     # Reusable widgets
        └── pubspec.yaml
```

---

## Tính năng

- 📊 **Dashboard** — Tổng quan sức khỏe hàng ngày
- 🍽️ **Dinh dưỡng** — Theo dõi bữa ăn, tính macro, gợi ý thực đơn
- 🏋️ **Vận động** — Nhật ký tập luyện, khám phá bài tập
- 🤖 **AI Chatbot** — Tư vấn sức khỏe cá nhân hóa theo chỉ số BMI/TDEE

## Lưu ý

- File `firebase_options.dart` và `google-services.json` không được push (chứa API keys). Xem `setup_firebase_guide.md` để cấu hình.
- File `.env` không được push. Sao chép từ `.env.example` và điền thông tin.
- `venv/` không được push. Chạy `pip install -r requirements.txt` để tạo lại.
