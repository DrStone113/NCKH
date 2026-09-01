# D4.1 AUDITABLE CATALOG INGESTION REPORT

## Baseline Manifest

Production is frozen as `production-catalog-v1.0.0` in
`apps/backend/data/production_catalog_manifest_v1.json`.

- Git base commit: `5c5f5a8425886a9454e73c1c3d7e79769364c4bd`
- Canonical foods: 526
- Live dishes: 300
- Food content SHA-256: `361a385b5613358a56198f90e94f038f92bee36e7076d412fd1d4049cbfa2fa5`
- Dish content SHA-256: `cdc827c30b6613baca784d5f3ac689f20340fc46087d3dae01e47de0406c520d`
- Validator: `catalog-ingestion-d4.1.0`

Hashes of the registry, research identity and QA summary are stored in the
same self-hashed manifest. `--write-baseline` is an explicit release action;
ordinary validation is read-only.

## Research Isolation

The production manifest records and verifies the separate research identity:

- corpus: `offline-v1-636`
- corpus hash: `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`
- research manifest hash: `5ed75adc4885b3b3b4f01554a4789605299dca965794819a76c81fc3e892afb1`
- the four frozen inputs retain their recorded hashes
- A/B/C configuration hashes are frozen independently in the production manifest

No D4.1 loader writes to `vietnamese_foods.json`, `vietnamese_dishes.json`,
`nutrition.json`, `exercises.json`, the research manifest, or an A/B/C artifact.

## Review Debt

`catalog_review_queues_v1.json` contains 73 open, explicit queue items:

- 70 legacy serving definitions
- 3 source-food energy QA warnings

Every item has a reason, severity, source, review status, resolution and QA
evidence. Resolution starts as `null`; the queue never silently changes source
nutrients or serving estimates.

## Source Approval Registry

Every registered source now declares publisher, edition/version, access URL,
license/reuse status, redistribution status, nutrient import permission,
matching priority and review date. Only `VIETNAM_FCT` is approved for nutrient
import. Every fallback remains locked even when its reuse terms are permissive.

## Staging Model

The staging lifecycle is monotonic:

`RAW_IMPORTED → NORMALIZED → MATCHED → QA_REVIEW → APPROVED | REJECTED`

The staging index explicitly declares that the production loader does not read
staging. An approved staging record still has `production_written=false`; a
separate, reviewed catalog release is required to change production.

## Matching Rules

The five states are `EXACT`, `CLOSE_VARIANT`, `GENERIC_PARENT`,
`SUBSTITUTED_WITH_JUSTIFICATION`, and `UNRESOLVED`.

Only `EXACT` is automatically eligible. Every other resolved state requires a
named human reviewer and a documented non-exact approval. Differences in
species/type, raw/cooked state, cut/part, processing or cooking method require
an explicit reason for each differing field. `UNRESOLVED` cannot be approved.

## Nutrient Normalization

Staging preserves the full source record and normalizes supported nutrients to
per-100 g edible portion. It supports mass-unit conversion and kJ-to-kcal
conversion. Missing values stay `null`; an unsupported unit is preserved as an
original value and becomes a blocking QA signal instead of zero.

## Provenance

Every canonical and staged nutrient contains source ID, source record ID,
source edition, original value/unit/basis, normalized value/unit/basis,
normalization rule and review status. Compatibility fields remain available to
existing API clients.

## QA Rules

Engineering QA covers:

- energy versus 4/4/9 macro consistency, explicitly not ground truth
- negative and non-finite values
- unit anomalies
- conservative extreme-value thresholds
- duplicate canonical IDs and source IDs
- raw/cooked descriptor mismatches

Blocking signals prevent approval until resolved. Source nutrient numbers are
never automatically rewritten.

## Batch Manifest

Each batch manifest records batch ID, source snapshot, source hash, imported,
approved, rejected and unresolved counts, manual reviewers, output hash and a
self-hash. Default limits are 50 foods or 30 dishes; exceeding either requires
an explicit override recorded in the manifest.

## Tests

Run:

```powershell
cd apps/backend
py -3.10 scripts/manage_catalog_ingestion.py --verify
py -3.10 scripts/validate_dish_catalog.py
py -3.10 -m pytest -q tests/test_catalog_ingestion_d4_1.py
```

The D4.1 suite covers baseline hashing, research isolation, review queues,
locked sources, lifecycle transitions, unit normalization, missing-value
preservation, protected matching descriptors, manual non-exact approval, QA,
batch limits and canonical-only dish ingredients.

## First Recommended Import Batch

Do not ingest a nutrient batch yet. First select a concrete source snapshot,
record its SHA-256, assign human reviewers and explicitly approve that source.
The preferred first production-growth batch is no more than 30 sourced
Vietnamese dishes whose ingredients all already resolve to the 526 canonical
food IDs. This grows dish coverage without unlocking a fallback nutrient table.

## Ready for Batch 001?

NO

The code path is ready, but no new source snapshot/reviewer set has been
approved. Keeping the answer `NO` prevents a locked fallback or unsourced dish
batch from entering production by implication.
