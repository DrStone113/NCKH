-- Durable, non-authoritative previews. These rows preserve exact server-created
-- drafts across process restarts; they never count as saved/active plans or as
-- meal/workout observations.

CREATE TABLE IF NOT EXISTS plan_v2_previews (
    owner_user_id TEXT NOT NULL,
    plan_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    content_hash TEXT NOT NULL,
    revision_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    PRIMARY KEY (owner_user_id, plan_id, revision_id)
);

CREATE INDEX IF NOT EXISTS plan_v2_previews_expiry_idx
    ON plan_v2_previews (expires_at);

CREATE TABLE IF NOT EXISTS workout_plan_previews_e4 (
    owner_user_id TEXT NOT NULL,
    plan_id UUID NOT NULL,
    presentation JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    PRIMARY KEY (owner_user_id, plan_id)
);

CREATE INDEX IF NOT EXISTS workout_plan_previews_e4_expiry_idx
    ON workout_plan_previews_e4 (expires_at);

COMMENT ON TABLE plan_v2_previews IS
    'Non-authoritative exact Plan V2 drafts used only for later explicit save.';
COMMENT ON TABLE workout_plan_previews_e4 IS
    'Non-authoritative E4 presentations used only for later explicit save.';
