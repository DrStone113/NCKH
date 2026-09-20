# HealthApp — Ứng dụng quản lý sức khỏe AI

Ứng dụng Flutter + FastAPI + Ollama cho phép theo dõi dinh dưỡng, tập luyện và tư vấn sức khỏe bằng AI.

## Yêu cầu cài đặt

| Công cụ    | Phiên bản yêu cầu | Đã cài trên máy hiện tại | Link                                         |
| ---------- | ----------------- | ------------------------ | -------------------------------------------- |
| Flutter    | ≥ 3.0             | ✅ 3.44.8 (stable) tại `C:\flutter`, `C:\flutter\bin` đã có trong `PATH` | https://flutter.dev/docs/get-started/install |
| Dart       | đi kèm Flutter    | ✅ 3.12.2                | —                                            |
| Android SDK| ≥ 34              | ✅ 36.0.0 (`%LOCALAPPDATA%\Android\sdk`) — cần `flutter doctor --android-licenses` | https://developer.android.com/studio |
| Python     | ≥ 3.10            | ✅                       | https://python.org                           |
| PostgreSQL | ≥ 14              | ✅ (qua Docker `pgvector`)| https://postgresql.org                       |
| Ollama     | Latest            | —                        | https://ollama.com                           |

> Trình duyệt: máy **chưa cài Chrome**. Dùng `flutter run -d edge` hoặc `-d web-server`.
> Kiểm tra nhanh: `flutter --version` và `flutter doctor -v`.

## Khởi động nhanh

### Dùng backend/LLM trên GPU server qua SSH tunnel

`quick-start.bat` sẽ tự mở SSH tunnel từ máy local tới backend chạy trên server GPU, rồi chạy Flutter với `API_BASE_URL=http://127.0.0.1:8080` để cả HTTP API lẫn WebSocket chatbot đều đi qua tunnel đó.

```bat
quick-start.bat
```

Truy cập: http://localhost:3000

> Điều kiện: backend trên server phải listen tại `127.0.0.1:8080` hoặc `0.0.0.0:8080`, và SSH user phải đăng nhập được vào `ssh root@e1.chiasegpu.vn -p 17560`.

### Dùng trực tiếp Cloudflare Tunnel từ máy local

Nếu server không mở public port, có thể chạy client local qua URL tunnel Cloudflare đã tạo sẵn.

```bat
start-cloudflare-client.bat
```

Script này chạy Flutter local với:

- `API_BASE_URL=https://hear-sunrise-speech-democrat.trycloudflare.com`
- REST: `https://hear-sunrise-speech-democrat.trycloudflare.com`
- WebSocket: `wss://hear-sunrise-speech-democrat.trycloudflare.com/chat/stream`

> Lưu ý: URL `trycloudflare.com` là tunnel tạm thời. Nếu restart `cloudflared`, hãy sửa lại `API_BASE_URL` trong `start-cloudflare-client.bat`.

---

## Cài đặt thủ công

### 1. Backend (FastAPI)

```bat
cd apps\backend

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
ollama pull qwen3:8b
ollama create health-qwen3:8b-8k -f apps\backend\ollama\Modelfile.qwen3-8k
ollama serve
```

Backend native (`apps/backend/.env`):

```env
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=health-qwen3:8b-8k
HEAVY_LLM_MODEL=health-qwen3:8b-8k
SCOPE_CLASSIFIER_MODEL=health-qwen3:8b-8k
LLM_REASONING_EFFORT=none
HEAVY_LLM_REASONING_EFFORT=high
EMBEDDING_MODEL=BAAI/bge-m3
```

Khi backend chạy trong Docker, dùng
`OPENAI_BASE_URL=http://host.docker.internal:11434/v1` trong file `.env` ở
thư mục gốc. `BAAI/bge-m3` vẫn là embedding model của RAG; Ollama chỉ thay
model sinh câu trả lời và gọi công cụ.

### 3. Flutter App

```bat
cd apps\mobile

# Cài dependencies
flutter pub get

# Cấu hình Firebase (xem docs/guides/setup_firebase.md)

# Chạy web (máy chưa có Chrome → dùng edge hoặc web-server)
flutter run -d edge --web-port 3000
flutter run -d web-server --web-port 3000
```

#### Kiểm thử

```bat
flutter analyze                                   :: lint (kỳ vọng: 0 error, 0 warning)
flutter test                                      :: 23/23 test passed
flutter build web --release --no-tree-shake-icons :: build production web
```

> Kết quả kiểm thử ngày 2026-08-06 (Flutter 3.44.8): `pub get` OK · `analyze` 22 info (`withOpacity` deprecated) · `test` 23/23 passed · `build web` thành công.


---

## Cấu trúc project

```
Chatbot/
├── start-all.bat            # Khởi động tất cả dịch vụ (DB + backend + web)
├── stop-all.bat             # Dừng tất cả dịch vụ
├── docker-compose.yml       # Postgres/pgvector, backend, frontend, tunnel
├── apps/
│   ├── backend/             # FastAPI + LLM backend
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   ├── config.py
│   │   ├── modules/         # API endpoints (chat, nutrition, wger, plans...)
│   │   ├── services/        # Business logic (agent, RAG, prompt, tools)
│   │   ├── models/          # Pydantic schemas + ORM models
│   │   ├── db/              # Database, migrations, session store
│   │   ├── scripts/         # Data loading & sync scripts
│   │   ├── tests/           # pytest suite
│   │   └── .env.example     # Template cấu hình
│   └── mobile/              # Flutter app (package: health_app)
│       ├── lib/
│       │   ├── features/    # Màn hình theo tính năng
│       │   ├── providers/   # State management
│       │   ├── models/      # Data models
│       │   ├── services/    # API services
│       │   └── widgets/     # Reusable widgets
│       ├── test/            # Unit & widget tests
│       └── pubspec.yaml
├── data/
│   ├── raw/                 # Dataset gốc (CSV, JSON, PDF nguồn)
│   └── scripts/             # Script parse/convert dataset
└── docs/
    ├── architecture/        # Kiến trúc, schema DB, thiết kế modular
    ├── features/            # Tài liệu từng tính năng
    ├── guides/              # Hướng dẫn chạy, cài đặt, Docker, GPU
    ├── archive/             # Nhật ký task đã hoàn thành
    ├── thesis/              # Tài liệu thuyết minh NCKH
    ├── CHANGELOG.md
    ├── evaluation_matrix.md
    └── troubleshooting.md
```

---

## Tính năng

- 📊 **Dashboard** — Tổng quan sức khỏe hàng ngày
- 🍽️ **Dinh dưỡng** — Theo dõi bữa ăn, tính macro, gợi ý thực đơn
- 🏋️ **Vận động** — Nhật ký tập luyện, khám phá bài tập
- 🤖 **AI Chatbot** — Tư vấn sức khỏe cá nhân hóa theo chỉ số BMI/TDEE

## Lưu ý

- File `firebase_options.dart` và `google-services.json` không được push (chứa API keys). Xem `docs/guides/setup_firebase.md` để cấu hình.
- File `.env` không được push. Sao chép từ `.env.example` và điền thông tin.
- `venv/` không được push. Chạy `pip install -r requirements.txt` để tạo lại.
