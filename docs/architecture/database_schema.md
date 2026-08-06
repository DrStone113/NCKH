# 02. Cấu Trúc Database (Database Schema & Storage)

## 🗄️ Tổng Quan Cơ Sở Dữ Liệu

Hệ thống kết hợp **PostgreSQL** cho dữ liệu quan hệ (Kế hoạch lộ trình, Lịch sử trò chuyện, Nudge check-in) và mở rộng **pgvector** cho truy vấn ngữ nghĩa (RAG kiến thức y học & dinh dưỡng món ăn Việt Nam). Phía Flutter sử dụng `SharedPreferences` và In-Memory Caching cho phản hồi tức thì.

---

## 📊 Cấu Trúc Các Bảng (Tables Schema)

### 1. Bảng Kế Hoạch (`plans`)
Lưu trữ lộ trình sức khỏe cá nhân hóa do AI Agent khởi tạo.
```sql
CREATE TABLE plans (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    goal VARCHAR(64) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    duration_days INT NOT NULL,
    daily_kcal_target DOUBLE PRECISION NOT NULL,
    daily_protein_target DOUBLE PRECISION NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_plans_user_status ON plans(user_id, status);
```

### 2. Bảng Chi Tiết Mục Kế Hoạch (`plan_items`)
Lưu từng nhiệm vụ bữa ăn/tập luyện theo từng ngày trong kế hoạch.
```sql
CREATE TABLE plan_items (
    id VARCHAR(36) PRIMARY KEY,
    plan_id VARCHAR(36) NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    day_index INT NOT NULL,
    plan_date DATE NOT NULL,
    item_type VARCHAR(32) NOT NULL, -- 'meal' | 'exercise'
    title VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_kcal DOUBLE PRECISION,
    target_protein DOUBLE PRECISION,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_plan_items_plan_day ON plan_items(plan_id, day_index);
```

### 3. Bảng Phiên Trò Chuyện & Nhắc Nhở (`chat_sessions`, `nudge_logs`)
- `chat_sessions`: Lưu trữ `session_id`, `user_id`, `created_at`.
- `nudge_logs`: Lưu vết các thông điệp Nudge chủ động được gửi tới người dùng.

---

## 🔍 Vector Collection (pgvector RAG)

- **Vector Table**: `knowledge_embeddings`
- **Embedding Model**: `BAAI/bge-small-en-v1.5` / `multilingual-e5-small`.
- **Dimensions**: 384 dimensions.
- **Index Type**: IVFFlat / HNSW cosine distance search (`<=>`).
- **Nội dung lưu trữ**: Món ăn Việt Nam (`nutrition.json`), bài tập thể chất Wger, kiến thức y học và quy chuẩn dinh dưỡng.
