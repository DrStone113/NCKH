-- ``plan_v2_items.id`` was a P1 physical row key.  P2 revisions may retain a
-- logical plan-item reference across immutable snapshots, so preserve it in a
-- separate column and let each revision own a distinct storage row id.
ALTER TABLE plan_v2_items
    ADD COLUMN IF NOT EXISTS plan_item_id UUID;

UPDATE plan_v2_items
SET plan_item_id = id
WHERE plan_item_id IS NULL;

ALTER TABLE plan_v2_items
    ALTER COLUMN plan_item_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS plan_v2_items_revision_logical_item_idx
    ON plan_v2_items (revision_id, plan_item_id);

COMMENT ON COLUMN plan_v2_items.plan_item_id IS
    'Stable logical item identity retained across immutable plan revisions.';
