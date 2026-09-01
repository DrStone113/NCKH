-- P2 content hashes include ordered immutable items.  JSONB has no implicit
-- array row order, so persistence stores the preview order explicitly.
ALTER TABLE plan_v2_items
    ADD COLUMN IF NOT EXISTS item_order INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS plan_v2_items_revision_order_idx
    ON plan_v2_items (revision_id, item_order, id);

COMMENT ON COLUMN plan_v2_items.item_order IS
    'Immutable preview item position used to reconstruct the exact revision hash.';
