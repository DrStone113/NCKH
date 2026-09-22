-- Idempotency ledger for non-authoritative typed revision previews.
-- The resulting revision remains in plan_v2_previews until explicit save.

CREATE TABLE IF NOT EXISTS plan_v2_preview_actions (
    owner_user_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    base_revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    preview_revision_id UUID NOT NULL,
    preview_content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, action_id)
);

CREATE INDEX IF NOT EXISTS plan_v2_preview_actions_owner_plan_idx
    ON plan_v2_preview_actions (owner_user_id, plan_id, created_at DESC);
