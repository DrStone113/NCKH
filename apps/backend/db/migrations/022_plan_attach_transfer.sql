-- Attach a standalone MENU or WORKOUT to a COMBINED_PLAN exactly once.
-- The action ledger makes a retry return the same combined revision and
-- prevents an idempotency key from being replayed against another source.

CREATE TABLE IF NOT EXISTS plan_v2_attach_actions (
    owner_user_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    combined_plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    base_revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    source_plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    source_revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    target_revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    combined_content_hash CHAR(64) NOT NULL,
    source_content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, action_id)
);

CREATE INDEX IF NOT EXISTS plan_v2_attach_actions_owner_combined_idx
    ON plan_v2_attach_actions (owner_user_id, combined_plan_id, created_at DESC);
