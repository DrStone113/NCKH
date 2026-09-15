-- migration-mode: autocommit
-- Online indexes for Backend Optimization V2 hot paths.
CREATE INDEX CONCURRENTLY IF NOT EXISTS chat_messages_session_history_idx
    ON chat_messages (session_id, created_at DESC, id DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS chat_sessions_owner_activity_idx
    ON chat_sessions (user_id, last_active DESC, id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS chat_messages_first_user_idx
    ON chat_messages (session_id, created_at ASC, id ASC)
    WHERE role = 'user';

CREATE INDEX CONCURRENTLY IF NOT EXISTS tool_invocations_request_id_idx
    ON tool_invocations (session_id, tool_name, (arguments ->> 'request_id'))
    WHERE arguments ? 'request_id';

CREATE INDEX CONCURRENTLY IF NOT EXISTS tool_invocations_audit_time_idx
    ON tool_invocations (created_at DESC, id);
