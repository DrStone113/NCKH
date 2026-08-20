-- Persist the exact presentation payload used by Flutter action cards so
-- opening a conversation from history renders the same card as live chat.
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS structured_data JSONB;
