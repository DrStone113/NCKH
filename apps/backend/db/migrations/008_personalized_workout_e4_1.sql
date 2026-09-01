-- E4.1: explicit, auditable persistence for deterministic workout plans and
-- observed workout results. Legacy Firestore exercise records are not rewritten.

CREATE TABLE IF NOT EXISTS workout_plans_e4 (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'SAVED', 'ACTIVE', 'COMPLETED', 'PARTIALLY_COMPLETED', 'SKIPPED', 'CANCELLED'
    )),
    planner_version TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    exercise_policy_version TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    goal TEXT,
    duration_budget_minutes NUMERIC(8,2),
    estimated_duration_minutes NUMERIC(8,2) NOT NULL,
    exercises JSONB NOT NULL,
    reason_metadata JSONB NOT NULL,
    estimated_energy_expenditure JSONB NOT NULL,
    CONSTRAINT workout_plans_e4_idempotency_unique UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS workout_plans_e4_user_status_idx
    ON workout_plans_e4 (user_id, status, saved_at DESC);

COMMENT ON COLUMN workout_plans_e4.estimated_energy_expenditure IS
    'Compendium-derived estimate/provenance only; never a measured or reported calorie value.';

CREATE TABLE IF NOT EXISTS workout_results_e4 (
    id UUID PRIMARY KEY,
    workout_plan_id UUID NOT NULL REFERENCES workout_plans_e4(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    performed_at TIMESTAMPTZ NOT NULL,
    session_completion_status TEXT NOT NULL CHECK (session_completion_status IN (
        'COMPLETED', 'PARTIALLY_COMPLETED', 'SKIPPED', 'CANCELLED'
    )),
    exercise_results JSONB NOT NULL DEFAULT '[]'::jsonb,
    session_rpe NUMERIC(4,2),
    pain_discomfort_status TEXT NOT NULL CHECK (pain_discomfort_status IN ('YES', 'NO', 'UNKNOWN')),
    note TEXT,
    duration_minutes NUMERIC(8,2),
    reported_device_energy_kcal NUMERIC(10,2),
    user_reported_energy_kcal NUMERIC(10,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workout_results_e4_idempotency_unique UNIQUE (workout_plan_id, idempotency_key),
    CONSTRAINT workout_results_e4_session_rpe_range CHECK (session_rpe IS NULL OR (session_rpe >= 1 AND session_rpe <= 10)),
    CONSTRAINT workout_results_e4_duration_non_negative CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    CONSTRAINT workout_results_e4_device_energy_non_negative CHECK (reported_device_energy_kcal IS NULL OR reported_device_energy_kcal >= 0),
    CONSTRAINT workout_results_e4_user_energy_non_negative CHECK (user_reported_energy_kcal IS NULL OR user_reported_energy_kcal >= 0)
);

CREATE INDEX IF NOT EXISTS workout_results_e4_plan_performed_idx
    ON workout_results_e4 (workout_plan_id, performed_at DESC);

COMMENT ON COLUMN workout_results_e4.exercise_results IS
    'Only user-observed actual values: target prescription values must not be copied here automatically.';

COMMENT ON COLUMN workout_results_e4.reported_device_energy_kcal IS
    'Energy reported by a device; separate from the plan Compendium estimate.';

COMMENT ON COLUMN workout_results_e4.user_reported_energy_kcal IS
    'Energy self-reported by the user; separate from device reports and plan estimates.';
