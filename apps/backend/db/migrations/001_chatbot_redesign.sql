-- Migration: 001_chatbot_redesign
-- Spec: chatbot-redesign (design.md §10)
-- Requirements: 7.3, 7.5
--
-- Mở rộng schema để hỗ trợ kiến trúc agent có công cụ:
--   - chat_messages: thêm tool_call_id, tool_name; cho phép role='tool'
--   - chat_session_memory: rolling summary mỗi session
--   - user_facts: pinned facts (preference / allergy / goal / constraint)
--   - tool_invocations: audit log cho mỗi tool call
--   - plans: thêm daily_protein_target
--
-- Lưu ý: file này được apply trong một transaction do `apply_migrations` quản
-- lý, nên không tự mở BEGIN/COMMIT bên trong (asyncpg không cho nested
-- transaction qua simple query protocol).

-- 1. Mở rộng chat_messages để hỗ trợ tool turns
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS tool_call_id TEXT,
    ADD COLUMN IF NOT EXISTS tool_name    TEXT;

ALTER TABLE chat_messages
    DROP CONSTRAINT IF EXISTS chat_messages_role_check;

ALTER TABLE chat_messages
    ADD CONSTRAINT chat_messages_role_check
    CHECK (role IN ('user', 'assistant', 'tool'));

-- 2. Rolling summary mỗi session
CREATE TABLE IF NOT EXISTS chat_session_memory (
    session_id      UUID PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
    rolling_summary TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Pinned facts về user (sở thích, dị ứng, mục tiêu, ràng buộc)
CREATE TABLE IF NOT EXISTS user_facts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT NOT NULL,
    category      TEXT NOT NULL,
    fact          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'rejected')),
    source_msg_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS user_facts_user_idx
    ON user_facts(user_id, status);

-- 4. Audit log cho mỗi tool invocation (debug + property test)
CREATE TABLE IF NOT EXISTS tool_invocations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    correlation_id TEXT NOT NULL,
    tool_name      TEXT NOT NULL,
    side           TEXT NOT NULL CHECK (side IN ('server', 'client')),
    arguments      JSONB NOT NULL,
    result         JSONB,
    ok             BOOLEAN,
    error_code     TEXT,
    duration_ms    INTEGER,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS tool_invocations_corr_idx
    ON tool_invocations(session_id, correlation_id);

-- 5. Mở rộng plans với protein target
ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS daily_protein_target NUMERIC(8,2);

-- 6. Quyền cho user health (giữ nhất quán với init.sql)
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO health;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO health;
