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
    thoughts    TEXT NOT NULL DEFAULT '',
    structured_data JSONB,
    public_trace JSONB,
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

-- P1 Plan V2 tables are created by migration 010 for existing databases.  The
-- clean-install schema keeps the same isolated planned-state model so it
-- cannot be confused with legacy plans or actual meal/workout observations.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS plan_v2_plans (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    domain TEXT NOT NULL CHECK (domain IN ('NUTRITION', 'WORKOUT', 'COMBINED_HEALTH')),
    plan_schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_v2_revisions (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    owner_user_id TEXT NOT NULL,
    domain TEXT NOT NULL CHECK (domain IN ('NUTRITION', 'WORKOUT', 'COMBINED_HEALTH')),
    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
    parent_revision_id UUID REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('DRAFT', 'PENDING_CONFIRMATION', 'SAVED', 'ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED', 'SUPERSEDED')),
    validation_status TEXT NOT NULL CHECK (validation_status IN ('READY', 'CLARIFICATION_REQUIRED', 'REQUIRES_SPECIALIST_GUIDANCE', 'INVALID')),
    hard_violation_count INTEGER NOT NULL DEFAULT 0 CHECK (hard_violation_count >= 0),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    timezone TEXT NOT NULL,
    request_payload JSONB NOT NULL,
    policy_versions JSONB NOT NULL,
    catalog_versions JSONB NOT NULL,
    goal_snapshot JSONB NOT NULL,
    constraint_snapshot JSONB NOT NULL,
    summary JSONB NOT NULL,
    explanation_metadata JSONB NOT NULL,
    provenance JSONB NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT plan_v2_revision_period_valid CHECK (period_end >= period_start),
    CONSTRAINT plan_v2_revision_identity_unique UNIQUE (plan_id, revision_number),
    CONSTRAINT plan_v2_active_requires_ready CHECK (lifecycle_status <> 'ACTIVE' OR (validation_status = 'READY' AND hard_violation_count = 0))
);

ALTER TABLE plan_v2_revisions DROP CONSTRAINT IF EXISTS plan_v2_active_period_exclusion;
ALTER TABLE plan_v2_revisions ADD CONSTRAINT plan_v2_active_period_exclusion
    EXCLUDE USING gist (owner_user_id WITH =, domain WITH =, daterange(period_start, period_end, '[]') WITH &&)
    WHERE (lifecycle_status = 'ACTIVE');

CREATE TABLE IF NOT EXISTS plan_v2_items (
    id UUID PRIMARY KEY,
    revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    plan_item_id UUID NOT NULL,
    item_order INTEGER NOT NULL DEFAULT 0,
    scheduled_date DATE NOT NULL,
    schedule_slot TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('MEAL', 'WORKOUT_SESSION')),
    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'CANCELLED', 'SUPERSEDED')),
    canonical_refs JSONB NOT NULL,
    reason_codes JSONB NOT NULL,
    policy_provenance JSONB NOT NULL,
    planned_content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_v2_write_actions (
    owner_user_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('SAVE', 'SET_STATUS')),
    plan_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    content_hash CHAR(64),
    result_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, action_id)
);

CREATE TABLE IF NOT EXISTS legacy_plan_v2_classification (
    legacy_plan_id UUID PRIMARY KEY,
    classification TEXT NOT NULL CHECK (classification IN ('LEGACY_READABLE', 'MIGRATABLE', 'LEGACY_UNVERSIONED', 'INVALID')),
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

GRANT ALL PRIVILEGES ON plan_v2_plans, plan_v2_revisions, plan_v2_items, plan_v2_write_actions, legacy_plan_v2_classification TO health;
