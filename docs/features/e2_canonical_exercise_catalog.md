# E2 — Canonical exercise catalog and provenance

## Outcome

E2 provides an offline-first canonical layer for all 885 records in the frozen
Wger snapshot. It is deterministic, self-hashed and separate from workout
prescription. `suggest_workout` is intentionally unchanged; E3 will define a
reviewed prescription policy before E4/E6 can consume this catalog.

The runtime catalog is derived by
`apps/backend/modules/wger/canonical_exercises.py`. Its frozen identity and QA
summary are stored in
`apps/backend/data/canonical_exercise_catalog_manifest_v1.json`.

## Pipeline and identity

```text
frozen Wger exerciseinfo snapshot
        ↓
source-preserving normalization
        ↓
app-curated rules with explicit provenance
        ↓
canonical-exercise-v1.0.0 + content SHA-256
```

Canonical IDs use the stable source UUID:

```text
WGER_EXERCISE_<wger-uuid>
```

The Wger integer ID remains available as `source_exercise_id`. Every record is
tied to snapshot SHA-256
`542cc7a7f7d87938f6c245c3ff23c2a32483c5734039ee953d1dbed9d9e3d226`.
The E1 audit manifest and frozen `offline-v1-636` research identity are embedded
in E2's manifest so accidental source drift fails verification.

The build never calls live Wger. Official Wger documentation describes
`/api/v2/exerciseinfo/` as the nested read-only exercise surface and publishes
the generated schema through `/api/v2/schema`:

- https://wger.readthedocs.io/en/latest/api/api.html
- https://github.com/wger-project/wger/blob/master/wger/exercises/api/serializers.py
- https://github.com/wger-project/wger/blob/master/wger/exercises/api/views.py

## Canonical record

Each record includes:

- canonical ID, Wger integer ID and UUID;
- English source name; Vietnamese name remains null until a reviewed source or
  translation workflow exists;
- primary and secondary muscle objects;
- equipment and category;
- plain-text instructions plus the original source HTML;
- images and videos;
- exercise-, translation- and media-level license/author metadata kept
  separately;
- app-curated movement pattern, difficulty, laterality and substitution group;
- source endpoint, snapshot hash and Wger source timestamps;
- field provenance, quality flags, ingestion state and review status.

`last_synced_at` remains null. The legacy fetch script did not emit a sync
manifest, and a filesystem modification time would not be valid source
provenance.

## Field ownership

| Owner | Fields |
|---|---|
| `WGER` | IDs/UUID, English translation, muscles, equipment, category, instructions, media and per-content licenses |
| `APP_CURATED_RULE` | movement pattern, difficulty, laterality and substitution group |
| `MISSING_NOT_GENERATED` | Vietnamese name and trustworthy sync time |

Every curated object records policy version
`exercise-curation-rules-v1.0.0`, rule ID, confidence, rationale and
`human_reviewed=false`. Unknown values are retained instead of being converted
to confident guesses.

## Movement and substitution metadata

The first rule set recognizes common patterns such as `SQUAT`, `HINGE`,
`HORIZONTAL_PUSH`, `VERTICAL_PUSH`, `HORIZONTAL_PULL`, `VERTICAL_PULL`, carry,
locomotion and several core/isolation patterns from explicit English-name
signals. It leaves 320 records as `UNKNOWN` for later review.

A substitution group is emitted only when both a movement pattern and at least
one Wger primary-muscle ID exist. The value has the form:

```text
HORIZONTAL_PUSH:PRIMARY:4
```

This is catalog metadata, not permission to substitute automatically. Future
planning must still check equipment, reviewed difficulty, limitations and the
safety gate.

Difficulty and laterality are especially conservative. They are inferred only
from explicit name signals; otherwise they remain `UNSPECIFIED`. The catalog
does not infer that every ordinary-looking exercise is intermediate or
bilateral.

## Frozen QA debt

| Signal | Records |
|---|---:|
| Total canonical records | 885 |
| Missing Vietnamese name | 885 |
| Missing trustworthy sync timestamp | 885 |
| Missing English instructions | 29 |
| Missing primary muscles | 194 |
| Missing equipment | 312 |
| Missing images | 624 |
| Missing videos | 839 |
| Unknown movement pattern | 320 |
| Missing substitution group | 438 |
| Unspecified difficulty | 861 |
| Unspecified laterality | 822 |

All 885 source records retain an exercise-level Creative Commons license: 732
CC-BY-SA 4, 133 CC-BY-SA 3 and 20 CC0. Wger application code and contributed
exercise content have different license boundaries; the per-record content
license is therefore preserved rather than replaced by one blanket label:
https://github.com/wger-project/wger.

The overall review status is
`SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED`. This means the source row is
canonicalized, while curated taxonomy fields still need human review before
they can drive a production recommendation policy.

## Phase boundary

E2 does not implement:

- sets, reps, rest, intensity or weekly volume;
- personalized selection from training history;
- progression or load changes;
- safety decisions;
- chatbot catalog integration;
- exercise-level calorie claims.

Those concerns remain in E3–E7. Keeping the boundary explicit prevents Wger
metadata or an unreviewed name heuristic from becoming a hidden exercise
prescription.

## Verification

```powershell
cd apps/backend
py -3.10 scripts/manage_exercise_catalog.py --verify
py -3.10 scripts/audit_exercise_data.py --verify
py -3.10 -m pytest -q tests/test_canonical_exercise_catalog_e2.py
```

To intentionally freeze a reviewed catalog-policy change:

```powershell
py -3.10 scripts/manage_exercise_catalog.py --write-manifest
```

The changed manifest and QA deltas must be reviewed together with the rule
change.
