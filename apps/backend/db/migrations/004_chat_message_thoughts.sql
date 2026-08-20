-- Persist the reasoning stream used by the Flutter AIThoughtsPanel so a
-- conversation has the same presentation after it is loaded from history.
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS thoughts TEXT NOT NULL DEFAULT '';
