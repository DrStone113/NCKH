-- N3.2.1 durable, owner-private recommendation feedback.
--
-- This migration extends the development/shadow N3.2 state only.  It does
-- not modify canonical foods/dishes, meal logs, Plan V2, or frozen research.
-- Recommendation exposure, feedback, personal learning evidence and actual
-- meal logging intentionally remain different concepts.

ALTER TABLE nutrition_recommendation_memory_n3_2
    ADD COLUMN IF NOT EXISTS feature_payload JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE nutrition_recommendation_feedback_n3_2
    ADD COLUMN IF NOT EXISTS policy_version TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- 016 predated the backwards-compatible REPEATED value.  New N3.2.1 writes
-- remain precise; this only permits durable reading/writing of that legacy
-- event name where the typed contract accepts it.
ALTER TABLE nutrition_recommendation_feedback_n3_2
    DROP CONSTRAINT IF EXISTS nutrition_recommendation_feedback_n3_2_event_type_check;
ALTER TABLE nutrition_recommendation_feedback_n3_2
    ADD CONSTRAINT nutrition_recommendation_feedback_n3_2_event_type_check CHECK (event_type IN (
        'SHOWN', 'OPENED', 'SAVED', 'REJECTED', 'SUBSTITUTED', 'LIKED',
        'DISLIKED', 'ACTUALLY_CONSUMED', 'REPEATED', 'REPEATED_CONSUMPTION',
        'PORTION_CORRECTED', 'INGREDIENT_CORRECTED', 'RECIPE_CORRECTED'
    ));

CREATE UNIQUE INDEX IF NOT EXISTS nutrition_recommendation_feedback_n3_2_owner_idempotency_idx
    ON nutrition_recommendation_feedback_n3_2 (owner_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Explicit serving corrections are private evidence for RecipePortionFitter.
-- They are not `nutrition_personal_portion_observations_n3_2`, whose source
-- contract is actual consumption only.
CREATE TABLE IF NOT EXISTS nutrition_personal_portion_corrections_n3_2 (
    id UUID PRIMARY KEY,
    feedback_event_id UUID NOT NULL UNIQUE REFERENCES nutrition_recommendation_feedback_n3_2(id) ON DELETE RESTRICT,
    owner_user_id TEXT NOT NULL,
    recommendation_id UUID NOT NULL REFERENCES nutrition_recommendation_memory_n3_2(id) ON DELETE RESTRICT,
    candidate_id UUID NOT NULL,
    corrected_portion_grams NUMERIC NOT NULL CHECK (corrected_portion_grams > 0),
    policy_version TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nutrition_personal_portion_corrections_n3_2_owner_candidate_idx
    ON nutrition_personal_portion_corrections_n3_2 (owner_user_id, candidate_id, occurred_at DESC);

-- Compact, de-identified catalog-gap evidence.  No owner id, conversation,
-- health fact, goal, weight or raw web material is copied into this table.
CREATE TABLE IF NOT EXISTS nutrition_catalog_gap_feedback_evidence_n3_2 (
    feedback_event_id UUID PRIMARY KEY REFERENCES nutrition_recommendation_feedback_n3_2(id) ON DELETE RESTRICT,
    normalized_candidate_key TEXT NOT NULL,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('INGREDIENT_UNAVAILABLE', 'CORRECTION')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE nutrition_shadow_policy_logs_n3_2
    ADD COLUMN IF NOT EXISTS production_selected_candidate_id UUID,
    ADD COLUMN IF NOT EXISTS recommendation_event_id UUID REFERENCES nutrition_recommendation_memory_n3_2(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX IF NOT EXISTS nutrition_shadow_policy_logs_n3_2_recommendation_idx
    ON nutrition_shadow_policy_logs_n3_2 (recommendation_event_id)
    WHERE recommendation_event_id IS NOT NULL;

COMMENT ON TABLE nutrition_personal_portion_corrections_n3_2 IS
    'Owner-private portion correction evidence. It is not a meal or consumption record.';
COMMENT ON TABLE nutrition_catalog_gap_feedback_evidence_n3_2 IS
    'De-identified feedback-derived catalog-gap evidence only; never a canonical promotion command.';
