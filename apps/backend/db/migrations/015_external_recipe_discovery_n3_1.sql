-- N3.1 Controlled External Recipe Discovery.
--
-- This migration stores only source-approved metadata/evidence. It contains
-- no raw HTML, no browser state, no credentials, no meal logs, no research
-- corpus rows, and no path to the canonical production catalog.

CREATE TABLE IF NOT EXISTS nutrition_external_recipe_cache_n3_1 (
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_recipe_id TEXT,
    content_fingerprint CHAR(64) NOT NULL,
    extracted_metadata JSONB NOT NULL,
    source_last_modified TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, source_url),
    CHECK (source_url !~* '://[^/]*@')
);

CREATE INDEX IF NOT EXISTS nutrition_external_recipe_cache_n3_1_expiry_idx
    ON nutrition_external_recipe_cache_n3_1 (expires_at);

CREATE TABLE IF NOT EXISTS nutrition_external_recipe_source_health_n3_1 (
    source_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fetch_strategy TEXT NOT NULL CHECK (fetch_strategy IN (
        'API_FETCH', 'HTTP_FETCH', 'PLAYWRIGHT_FETCH'
    )),
    success BOOLEAN NOT NULL,
    structured_extraction BOOLEAN,
    blocked_response BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms NUMERIC,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS nutrition_external_recipe_source_health_n3_1_source_idx
    ON nutrition_external_recipe_source_health_n3_1 (source_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_recipe_acquisition_priority_n3_1 (
    id UUID PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'FREQUENTLY_REQUESTED_UNKNOWN_DISH', 'FREQUENTLY_CONSUMED_PERSONAL_DISH',
        'HIGH_SEARCH_FREQUENCY', 'UNMAPPED_INGREDIENT_CLUSTER',
        'REGIONAL_DISH_GAP', 'USER_CORRECTION_CLUSTER'
    )),
    aggregate_evidence JSONB NOT NULL,
    priority_score NUMERIC NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
        'OPEN', 'EVIDENCE_REQUESTED', 'RESOLVED', 'REJECTED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS nutrition_recipe_acquisition_priority_n3_1_open_idx
    ON nutrition_recipe_acquisition_priority_n3_1 (lifecycle_status, priority_score DESC, created_at);

CREATE TABLE IF NOT EXISTS nutrition_recipe_promotion_scorecards_n3_1 (
    id UUID PRIMARY KEY,
    candidate_id UUID NOT NULL REFERENCES nutrition_recipe_candidates_n3(id) ON DELETE RESTRICT,
    evidence_hash CHAR(64) NOT NULL,
    scorecard JSONB NOT NULL,
    eligibility_class TEXT NOT NULL CHECK (eligibility_class IN (
        'NOT_ELIGIBLE', 'MORE_EVIDENCE_REQUIRED', 'AUTO_PROMOTION_ELIGIBLE',
        'REQUIRES_REVIEW', 'QUARANTINED', 'REJECTED'
    )),
    canonical_write_authorized BOOLEAN NOT NULL DEFAULT FALSE CHECK (canonical_write_authorized = FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE nutrition_external_recipe_cache_n3_1 IS
    'N3.1 source-approved structured metadata cache only; raw pages and credentials are prohibited.';
COMMENT ON TABLE nutrition_recipe_promotion_scorecards_n3_1 IS
    'Eligibility evidence only. canonical_write_authorized is hard-disabled for N3.1.';
