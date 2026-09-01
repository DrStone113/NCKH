-- PublicReasoningTrace is an allowlisted UX summary, never model reasoning.
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS public_trace JSONB;
