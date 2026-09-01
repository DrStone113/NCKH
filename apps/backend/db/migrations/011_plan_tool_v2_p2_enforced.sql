-- P2 enforced Plan V2 persistence.  This migration extends the isolated P1
-- tables; it never alters legacy plans, plan_items, meals, or workout results.

-- P1 keyed action retries by (owner, action).  P2 makes the operation part of
-- that identity, matching the public request contract and allowing a save and
-- a later activation to use independently idempotent action ids.
ALTER TABLE plan_v2_write_actions
    DROP CONSTRAINT IF EXISTS plan_v2_write_actions_pkey;
ALTER TABLE plan_v2_write_actions
    ADD PRIMARY KEY (owner_user_id, operation, action_id);

-- A revision must belong to the same owner as its plan.  PostgreSQL cannot
-- express that through the existing single-column FK, so write code verifies
-- it transactionally and this index keeps that check cheap.
CREATE INDEX IF NOT EXISTS plan_v2_revisions_plan_owner_revision_idx
    ON plan_v2_revisions (plan_id, owner_user_id, revision_number DESC);

-- Read-back and item reconstruction are always owner-scoped.
CREATE INDEX IF NOT EXISTS plan_v2_items_revision_item_idx
    ON plan_v2_items (revision_id, id);

COMMENT ON TABLE plan_v2_write_actions IS
    'P2 idempotency ledger scoped by authenticated owner, operation and action id.';
