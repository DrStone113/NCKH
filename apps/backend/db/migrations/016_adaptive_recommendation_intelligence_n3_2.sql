-- N3.2 Adaptive Recommendation Intelligence.
--
-- This schema is development/shadow learning state. It is intentionally
-- separate from canonical food/dish assets, frozen research, Plan V2, and
-- meal logs. No table here grants a canonical write capability.

CREATE TABLE IF NOT EXISTS nutrition_recommendation_memory_n3_2 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    candidate_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'LOCAL_CANONICAL', 'PERSONAL_RECIPE', 'STAGING_EXTERNAL', 'RUNTIME_EXTERNAL'
    )),
    dish_key TEXT NOT NULL,
    primary_protein_key TEXT,
    cuisine_key TEXT,
    preparation_key TEXT,
    shown_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome_status TEXT NOT NULL DEFAULT 'SHOWN' CHECK (outcome_status IN (
        'SHOWN', 'OPENED', 'SAVED', 'REJECTED', 'SUBSTITUTED', 'LIKED',
        'DISLIKED', 'ACTUALLY_CONSUMED', 'REPEATED_CONSUMPTION',
        'PORTION_CORRECTED', 'INGREDIENT_CORRECTED', 'RECIPE_CORRECTED'
    )),
    policy_version TEXT NOT NULL,
    selection_probability NUMERIC,
    context_fingerprint CHAR(24),
    CHECK (selection_probability IS NULL OR (selection_probability >= 0 AND selection_probability <= 1))
);

CREATE INDEX IF NOT EXISTS nutrition_recommendation_memory_n3_2_owner_recent_idx
    ON nutrition_recommendation_memory_n3_2 (owner_user_id, shown_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_recommendation_feedback_n3_2 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    recommendation_id UUID REFERENCES nutrition_recommendation_memory_n3_2(id) ON DELETE RESTRICT,
    candidate_id UUID NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'SHOWN', 'OPENED', 'SAVED', 'REJECTED', 'SUBSTITUTED', 'LIKED',
        'DISLIKED', 'ACTUALLY_CONSUMED', 'REPEATED_CONSUMPTION',
        'PORTION_CORRECTED', 'INGREDIENT_CORRECTED', 'RECIPE_CORRECTED'
    )),
    rejection_reason TEXT CHECK (rejection_reason IN (
        'DO_NOT_LIKE', 'NOT_TODAY', 'TOO_EXPENSIVE', 'TOO_HARD_TO_COOK',
        'INGREDIENT_UNAVAILABLE', 'TOO_REPETITIVE', 'PORTION_TOO_LARGE',
        'PORTION_TOO_SMALL', 'OTHER'
    )),
    explicit BOOLEAN NOT NULL DEFAULT FALSE,
    structured_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (event_type <> 'REJECTED' OR rejection_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS nutrition_recommendation_feedback_n3_2_owner_candidate_idx
    ON nutrition_recommendation_feedback_n3_2 (owner_user_id, candidate_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_preference_profile_n3_2 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    dimension TEXT NOT NULL CHECK (dimension IN (
        'DISH', 'INGREDIENT', 'PROTEIN', 'CUISINE', 'PREPARATION',
        'MEAL_PATTERN', 'SPICE', 'TEXTURE', 'COOKING_EFFORT', 'BUDGET'
    )),
    value_key TEXT NOT NULL,
    affinity NUMERIC NOT NULL CHECK (affinity >= -1 AND affinity <= 1),
    confidence NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_count INTEGER NOT NULL CHECK (evidence_count >= 0),
    source_type TEXT NOT NULL CHECK (source_type IN (
        'EXPLICIT_STATEMENT', 'EXPLICIT_FEEDBACK', 'ACTUAL_CONSUMPTION', 'INTERACTION'
    )),
    policy_version TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_confirmed_at TIMESTAMPTZ,
    UNIQUE (owner_user_id, dimension, value_key)
);

CREATE TABLE IF NOT EXISTS nutrition_personal_portion_observations_n3_2 (
    id UUID PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    candidate_id UUID NOT NULL,
    actual_portion_grams NUMERIC NOT NULL CHECK (actual_portion_grams > 0),
    source_event TEXT NOT NULL CHECK (source_event IN (
        'ACTUALLY_CONSUMED', 'REPEATED_CONSUMPTION'
    )),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nutrition_personal_portion_n3_2_owner_candidate_idx
    ON nutrition_personal_portion_observations_n3_2 (owner_user_id, candidate_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS nutrition_shadow_policy_logs_n3_2 (
    id UUID PRIMARY KEY,
    candidate_set_ids JSONB NOT NULL,
    selected_candidate_id UUID NOT NULL,
    policy_version TEXT NOT NULL,
    context_fingerprint CHAR(24) NOT NULL,
    selection_probability NUMERIC,
    outcome_event TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (selection_probability IS NULL OR (selection_probability >= 0 AND selection_probability <= 1))
);

CREATE TABLE IF NOT EXISTS nutrition_catalog_gaps_n3_2 (
    id UUID PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    reason_codes JSONB NOT NULL,
    aggregate_evidence JSONB NOT NULL,
    priority_score NUMERIC NOT NULL CHECK (priority_score >= 0 AND priority_score <= 1),
    lifecycle_status TEXT NOT NULL DEFAULT 'OPEN' CHECK (lifecycle_status IN (
        'OPEN', 'EVIDENCE_REQUESTED', 'RESOLVED', 'REJECTED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nutrition_catalog_evidence_tasks_n3_2 (
    id UUID PRIMARY KEY,
    gap_id UUID NOT NULL REFERENCES nutrition_catalog_gaps_n3_2(id) ON DELETE RESTRICT,
    task_type TEXT NOT NULL CHECK (task_type IN (
        'FIND_RECIPE_SOURCE', 'RESOLVE_ALIAS', 'RESOLVE_INGREDIENT_MAPPING',
        'VERIFY_SERVING', 'VERIFY_VARIANT_IDENTITY', 'COLLECT_MORE_USER_CONFIRMATION'
    )),
    lifecycle_status TEXT NOT NULL DEFAULT 'OPEN' CHECK (lifecycle_status IN (
        'OPEN', 'IN_REVIEW', 'RESOLVED', 'REJECTED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE nutrition_recommendation_memory_n3_2 IS
    'Exposure/outcome memory only. SHOWN is never a meal log or consumption evidence.';
COMMENT ON TABLE nutrition_preference_profile_n3_2 IS
    'Owner-private preference state. It cannot alter allergy, dietary, or safety facts.';
COMMENT ON TABLE nutrition_catalog_gaps_n3_2 IS
    'De-identified aggregate catalog-gap evidence only; no identity, health, weight, goal, notes, or conversation text.';
COMMENT ON TABLE nutrition_shadow_policy_logs_n3_2 IS
    'Offline evaluation telemetry only. A shadow policy cannot choose production output.';
