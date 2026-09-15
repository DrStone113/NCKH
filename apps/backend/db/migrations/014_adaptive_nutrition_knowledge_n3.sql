-- N3 Adaptive Nutrition Knowledge Loop.
--
-- These records are deliberately separate from the frozen research corpus and
-- from the JSON-backed canonical food/dish catalog. A row in this migration
-- can be used for personal memory, candidate staging, audit, and shadow
-- recommendation only. It is never a direct write path to production catalog
-- assets or to meal/workout observations.

CREATE TABLE IF NOT EXISTS nutrition_personal_memory_n3 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'PERSONAL_DISH_ALIAS', 'PREFERENCE', 'PERSONAL_PORTION_PRIOR'
    )),
    subject_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'EXPLICIT_USER_STATEMENT', 'CONFIRMED_RECIPE', 'ACTUAL_MEAL_LOG',
        'EXPLICIT_FEEDBACK', 'IMPLICIT_INTERACTION'
    )),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nutrition_personal_memory_n3_owner_subject_idx
    ON nutrition_personal_memory_n3 (owner_user_id, subject_key, observed_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_personal_recipes_n3 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    recipe_version INTEGER NOT NULL CHECK (recipe_version >= 1),
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('ACTIVE', 'DEPRECATED', 'REVOKED')),
    title TEXT NOT NULL,
    recipe_payload JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    supersedes_recipe_id UUID REFERENCES nutrition_personal_recipes_n3(id) ON DELETE RESTRICT,
    UNIQUE (owner_user_id, id, recipe_version)
);

CREATE TABLE IF NOT EXISTS nutrition_recipe_candidates_n3 (
    id UUID PRIMARY KEY,
    trust_domain TEXT NOT NULL CHECK (trust_domain IN (
        'PERSONAL_RECIPE', 'RUNTIME_EXTERNAL_CANDIDATE', 'STAGING_RECIPE'
    )),
    owner_user_id TEXT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
        'DISCOVERED', 'EXTRACTED', 'MAPPED', 'CALCULATED', 'VALIDATED',
        'STAGING', 'SHADOW_ELIGIBLE', 'PROMOTABLE', 'REJECTED',
        'QUARANTINED', 'DEPRECATED', 'REVOKED'
    )),
    title TEXT NOT NULL,
    candidate_payload JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    quality_score NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (trust_domain = 'PERSONAL_RECIPE' AND owner_user_id IS NOT NULL)
        OR (trust_domain <> 'PERSONAL_RECIPE')
    )
);

CREATE INDEX IF NOT EXISTS nutrition_recipe_candidates_n3_domain_status_idx
    ON nutrition_recipe_candidates_n3 (trust_domain, lifecycle_status, created_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_recipe_candidate_versions_n3 (
    candidate_id UUID NOT NULL REFERENCES nutrition_recipe_candidates_n3(id) ON DELETE RESTRICT,
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    lifecycle_status TEXT NOT NULL,
    candidate_payload JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    change_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (candidate_id, version_number)
);

CREATE TABLE IF NOT EXISTS nutrition_recipe_feedback_n3 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    candidate_id UUID REFERENCES nutrition_recipe_candidates_n3(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'SHOWN', 'OPENED', 'SAVED', 'REJECTED', 'SUBSTITUTED', 'LIKED',
        'DISLIKED', 'ACTUALLY_CONSUMED', 'REPEATED'
    )),
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nutrition_recipe_feedback_n3_owner_candidate_idx
    ON nutrition_recipe_feedback_n3 (owner_user_id, candidate_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_recipe_acquisition_queue_n3 (
    id UUID PRIMARY KEY,
    queue_reason TEXT NOT NULL CHECK (queue_reason IN (
        'UNKNOWN_DISH', 'POOR_LOCAL_COVERAGE', 'LOW_DIVERSITY',
        'AMBIGUOUS_MAPPING', 'FREQUENT_PERSONAL_RECIPE'
    )),
    normalized_query TEXT NOT NULL,
    aggregate_payload JSONB NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('OPEN', 'EVIDENCE_REQUESTED', 'RESOLVED', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS nutrition_recipe_promotion_decisions_n3 (
    id UUID PRIMARY KEY,
    candidate_id UUID NOT NULL REFERENCES nutrition_recipe_candidates_n3(id) ON DELETE RESTRICT,
    decision_class TEXT NOT NULL CHECK (decision_class IN (
        'AUTO_PROMOTION_ELIGIBLE', 'REQUIRES_MORE_EVIDENCE',
        'REQUIRES_REVIEW', 'REJECTED', 'QUARANTINED'
    )),
    hard_gate_results JSONB NOT NULL,
    review_provenance JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_hash CHAR(64) NOT NULL,
    canonical_write_authorized BOOLEAN NOT NULL DEFAULT FALSE CHECK (canonical_write_authorized = FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE nutrition_recipe_candidates_n3 IS
    'N3 candidate/staging only. No LLM or candidate may directly update canonical production catalog assets.';
COMMENT ON COLUMN nutrition_recipe_promotion_decisions_n3.canonical_write_authorized IS
    'Hard-disabled for the N3 staging and shadow rollout.';
