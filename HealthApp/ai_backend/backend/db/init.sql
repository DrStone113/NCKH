-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Chat sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Knowledge chunks table for RAG
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category    TEXT NOT NULL CHECK (category IN ('food', 'exercise', 'wger_exercise', 'wger_ingredient')),
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Chunk embeddings table (BAAI/bge-m3 = 1024 dims)
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    UUID PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    embedding   vector(1024)
);

-- IVFFlat index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS chunk_embeddings_embedding_idx
    ON chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Cache bài tập từ wger
CREATE TABLE IF NOT EXISTS wger_exercises (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    category_id     INTEGER,
    category_name   TEXT,
    muscles         JSONB DEFAULT '[]',
    muscles_secondary JSONB DEFAULT '[]',
    equipment       JSONB DEFAULT '[]',
    image_url       TEXT,
    cached_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Cache thực phẩm từ wger
CREATE TABLE IF NOT EXISTS wger_ingredients (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    energy          NUMERIC(8,2),
    protein         NUMERIC(8,2),
    carbohydrates   NUMERIC(8,2),
    fat             NUMERIC(8,2),
    fiber           NUMERIC(8,2),
    sugar           NUMERIC(8,2),
    cached_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Index cho tìm kiếm theo tên
CREATE INDEX IF NOT EXISTS wger_exercises_name_idx ON wger_exercises USING gin(to_tsvector('simple', name));
CREATE INDEX IF NOT EXISTS wger_ingredients_name_idx ON wger_ingredients USING gin(to_tsvector('simple', name));

-- Index cho tìm kiếm theo category và muscles (dùng bởi WgerSearchService)
CREATE INDEX IF NOT EXISTS wger_exercises_category_idx ON wger_exercises (category_id);
CREATE INDEX IF NOT EXISTS wger_exercises_muscles_idx ON wger_exercises USING gin(muscles);
CREATE INDEX IF NOT EXISTS wger_exercises_equipment_idx ON wger_exercises USING gin(equipment);

-- Migration: cập nhật category constraint để hỗ trợ wger (idempotent cho DB đã tồn tại)
ALTER TABLE knowledge_chunks DROP CONSTRAINT IF EXISTS knowledge_chunks_category_check;
ALTER TABLE knowledge_chunks ADD CONSTRAINT knowledge_chunks_category_check
    CHECK (category IN ('food', 'exercise', 'wger_exercise', 'wger_ingredient'));

-- Grant quyền cho user health trên tất cả bảng hiện tại
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO health;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO health;

-- Long-term plans
CREATE TABLE IF NOT EXISTS plans (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    goal              TEXT NOT NULL,
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    duration_days     INTEGER NOT NULL CHECK (duration_days >= 3 AND duration_days <= 120),
    daily_kcal_target NUMERIC(8,2) NOT NULL,
    target_weight     NUMERIC(6,2),
    notes             TEXT,
    status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_items (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id        UUID NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    day_index      INTEGER NOT NULL,
    plan_date      DATE NOT NULL,
    item_type      TEXT NOT NULL CHECK (item_type IN ('meal', 'exercise')),
    title          TEXT NOT NULL,
    payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_kcal    NUMERIC(8,2),
    target_protein NUMERIC(8,2),
    completed      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS plans_user_status_idx ON plans(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS plan_items_plan_day_idx ON plan_items(plan_id, day_index, plan_date);
