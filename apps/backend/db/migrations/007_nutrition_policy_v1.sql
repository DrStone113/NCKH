-- DEVELOPMENT D2.1: provenance for newly generated nutrition plans.
-- Existing rows remain NULL and are exposed as LEGACY; they are not recalculated.

ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS nutrition_policy_version TEXT;

ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS nutrition_formula_ids JSONB;

COMMENT ON COLUMN plans.nutrition_policy_version IS
    'NULL means a pre-D2.1 LEGACY plan; new plans use the active versioned nutrition policy.';
