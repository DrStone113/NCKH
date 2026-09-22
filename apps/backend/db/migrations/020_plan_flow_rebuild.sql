-- Plan flow rebuild: one public artifact contract, durable pending actions,
-- append-only change events, and cross-domain activation claims.

ALTER TABLE plan_v2_plans
    ADD COLUMN IF NOT EXISTS artifact_kind TEXT;

UPDATE plan_v2_plans
SET artifact_kind = CASE domain
    WHEN 'NUTRITION' THEN 'MENU'
    WHEN 'WORKOUT' THEN 'WORKOUT'
    ELSE 'COMBINED_PLAN'
END
WHERE artifact_kind IS NULL;

ALTER TABLE plan_v2_plans
    ALTER COLUMN artifact_kind SET DEFAULT 'MENU';
ALTER TABLE plan_v2_plans
    ALTER COLUMN artifact_kind SET NOT NULL;
ALTER TABLE plan_v2_plans
    DROP CONSTRAINT IF EXISTS plan_v2_artifact_kind_check;
ALTER TABLE plan_v2_plans
    ADD CONSTRAINT plan_v2_artifact_kind_check
    CHECK (artifact_kind IN ('MENU', 'WORKOUT', 'COMBINED_PLAN'));

CREATE TABLE IF NOT EXISTS plan_v2_pending_actions (
    owner_user_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    session_id TEXT,
    action_type TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    target_plan_id UUID NOT NULL,
    target_revision_id UUID NOT NULL,
    target_content_hash CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING_CONFIRMATION', 'EXECUTING', 'EXECUTED', 'SUPERSEDED', 'EXPIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (owner_user_id, action_id)
);

CREATE INDEX IF NOT EXISTS plan_v2_pending_actions_lookup_idx
    ON plan_v2_pending_actions (owner_user_id, session_id, status, expires_at);

CREATE TABLE IF NOT EXISTS plan_v2_change_events (
    event_id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    from_revision_id UUID REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    to_revision_id UUID REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('USER', 'ASSISTANT', 'SYSTEM')),
    source_surface TEXT NOT NULL CHECK (source_surface IN ('CHAT', 'PLAN_UI', 'MENU_UI', 'WORKOUT_UI', 'MIGRATION', 'SYSTEM')),
    operation TEXT NOT NULL,
    affected_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    before_payload JSONB,
    after_payload JSONB,
    reason TEXT,
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS plan_v2_change_events_owner_plan_idx
    ON plan_v2_change_events (owner_user_id, plan_id, created_at DESC);

CREATE TABLE IF NOT EXISTS plan_v2_active_claims (
    owner_user_id TEXT NOT NULL,
    content_domain TEXT NOT NULL CHECK (content_domain IN ('NUTRITION', 'WORKOUT')),
    plan_id UUID NOT NULL REFERENCES plan_v2_plans(id) ON DELETE RESTRICT,
    revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
    effective_period DATERANGE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, content_domain, plan_id, revision_id)
);

ALTER TABLE plan_v2_active_claims
    DROP CONSTRAINT IF EXISTS plan_v2_active_claims_no_overlap;
ALTER TABLE plan_v2_active_claims
    ADD CONSTRAINT plan_v2_active_claims_no_overlap
    EXCLUDE USING gist (
        owner_user_id WITH =,
        content_domain WITH =,
        effective_period WITH &&
    );

INSERT INTO plan_v2_active_claims (
    owner_user_id, content_domain, plan_id, revision_id, effective_period
)
SELECT owner_user_id, CASE WHEN domain = 'COMBINED_HEALTH' THEN 'NUTRITION' ELSE domain END,
       plan_id, id, daterange(period_start, period_end, '[]')
FROM plan_v2_revisions
WHERE lifecycle_status = 'ACTIVE' AND domain IN ('NUTRITION', 'WORKOUT', 'COMBINED_HEALTH')
ON CONFLICT DO NOTHING;

INSERT INTO plan_v2_active_claims (
    owner_user_id, content_domain, plan_id, revision_id, effective_period
)
SELECT owner_user_id, 'WORKOUT', plan_id, id, daterange(period_start, period_end, '[]')
FROM plan_v2_revisions
WHERE lifecycle_status = 'ACTIVE' AND domain = 'COMBINED_HEALTH'
ON CONFLICT DO NOTHING;

