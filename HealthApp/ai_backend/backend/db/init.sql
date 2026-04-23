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

-- Chunk embeddings table (paraphrase-multilingual-MiniLM-L12-v2 = 384 dims)
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    UUID PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    embedding   vector(384)
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

-- Migration: cập nhật category constraint để hỗ trợ wger (idempotent cho DB đã tồn tại)
ALTER TABLE knowledge_chunks DROP CONSTRAINT IF EXISTS knowledge_chunks_category_check;
ALTER TABLE knowledge_chunks ADD CONSTRAINT knowledge_chunks_category_check
    CHECK (category IN ('food', 'exercise', 'wger_exercise', 'wger_ingredient'));

-- Grant quyền cho user health trên tất cả bảng hiện tại
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO health;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO health;
