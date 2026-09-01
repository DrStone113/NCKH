-- P1 Plan Tool V2: versioned planned state, deliberately separate from
-- historical plans/plan_items and from meal/workout observation tables.
-- This migration does not rewrite or recalculate legacy records.

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
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
        'DRAFT', 'PENDING_CONFIRMATION', 'SAVED', 'ACTIVE', 'PAUSED',
        'COMPLETED', 'CANCELLED', 'SUPERSEDED'
    )),
    validation_status TEXT NOT NULL CHECK (validation_status IN (
        'READY', 'CLARIFICATION_REQUIRED', 'REQUIRES_SPECIALIST_GUIDANCE', 'INVALID'
    )),
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
    CONSTRAINT plan_v2_revision_hash_unique UNIQUE (id, content_hash),
    CONSTRAINT plan_v2_active_requires_ready CHECK (
        lifecycle_status <> 'ACTIVE' OR (validation_status = 'READY' AND hard_violation_count = 0)
    )
);

-- One ACTIVE plan per owner/domain/effective local-date range.  A new active
-- revision supersedes an overlapping revision in the same transaction before
-- this constraint is checked.
ALTER TABLE plan_v2_revisions DROP CONSTRAINT IF EXISTS plan_v2_active_period_exclusion;
ALTER TABLE plan_v2_revisions ADD CONSTRAINT plan_v2_active_period_exclusion
    EXCLUDE USING gist (
        owner_user_id WITH =,
        domain WITH =,
        daterange(period_start, period_end, '[]') WITH &&
    ) WHERE (lifecycle_status = 'ACTIVE');

CREATE TABLE IF NOT EXISTS plan_v2_items (
    id UUID PRIMARY KEY,
    revision_id UUID NOT NULL REFERENCES plan_v2_revisions(id) ON DELETE RESTRICT,
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

CREATE INDEX IF NOT EXISTS plan_v2_revisions_owner_domain_period_idx
    ON plan_v2_revisions (owner_user_id, domain, period_start, period_end, revision_number DESC);
CREATE INDEX IF NOT EXISTS plan_v2_items_revision_date_idx
    ON plan_v2_items (revision_id, scheduled_date, schedule_slot);

-- Stable action keys give save/status operations retry safety independently of
-- chat history.  It never stores actual meal consumption or workout results.
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

-- Classification is append-only audit metadata.  Legacy values stay as they
-- were; a user edit/recalculation is required to create a V2 revision.
CREATE TABLE IF NOT EXISTS legacy_plan_v2_classification (
    legacy_plan_id UUID PRIMARY KEY,
    classification TEXT NOT NULL CHECK (classification IN (
        'LEGACY_READABLE', 'MIGRATABLE', 'LEGACY_UNVERSIONED', 'INVALID'
    )),
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

COMMENT ON TABLE plan_v2_revisions IS
    'P1 planned state only. It must never be used as a meal-consumption or workout-completion record.';
COMMENT ON COLUMN plan_v2_items.planned_content IS
    'Prescribed/canonical plan data only; actual consumption/performance belongs in observation tables.';
