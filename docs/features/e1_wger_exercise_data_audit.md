# E1 — Wger and exercise-data audit

## Outcome

E1 is complete as a read-only, reproducible audit. It does not turn Wger into a
prescription engine and does not change `suggest_workout` behavior. The frozen
machine-readable result is
`apps/backend/data/exercise_data_audit_e1_v1.json`.

## Source and live API verification

The local importer uses Wger's nested `/api/v2/exerciseinfo/` resource. This is
the endpoint that the current Wger source calls the recommended read-only
exercise data surface. Wger publishes a generated OpenAPI schema at
`/api/v2/schema`; E1 checks the schema instead of assuming endpoint names.

Official references:

- API and OpenAPI discovery: https://wger.readthedocs.io/en/latest/api/api.html
- Exercise info serializer and its fields: https://github.com/wger-project/wger/blob/master/wger/exercises/api/serializers.py
- Exercise info view: https://github.com/wger-project/wger/blob/master/wger/exercises/api/views.py
- Wger repository and license boundaries: https://github.com/wger-project/wger
- Wger 2.5/2.6 releases: https://github.com/wger-project/wger/releases

Live observation on 2026-08-30:

| Check | Result |
|---|---:|
| OpenAPI version | `2.7.0a2` |
| `/api/v2/exerciseinfo/` | 200 |
| Live exercise count | 862 |
| `/api/v2/exercise/search/` in OpenAPI | No |
| Old search endpoint response | 404 |

The app's `/wger/search/exercise` proxy still targets the removed search
endpoint. Wger's 2.5 release notes explicitly direct search clients to the
filterable `/exerciseinfo/` resource. This proxy is not used by the current
agent recommendation path, so E1 records it for the adapter phase instead of
silently changing a response contract.

## Snapshot identity

Backend and mobile bundle the same byte-identical snapshot:

- records: 885
- SHA-256: `542cc7a7f7d87938f6c245c3ff23c2a32483c5734039ee953d1dbed9d9e3d226`
- duplicate integer IDs: 0
- duplicate UUIDs: 0
- latest `last_update_global` in the snapshot: 2026-04-21

The difference between the 885-row snapshot and the 862-row live result shows
that a future adapter must reconcile upstream deletions/merges and cannot treat
integer IDs alone as an eternal catalog identity.

## Field coverage

| Source field | Rows | Coverage |
|---|---:|---:|
| category | 885 | 100% |
| equipment | 573 | 64.75% |
| primary muscles | 691 | 78.08% |
| secondary muscles | 321 | 36.27% |
| images | 261 | 29.49% |
| videos | 46 | 5.20% |
| exercise license | 885 | 100% |
| license author | 794 | 89.72% |
| English translation | 885 | 100% |
| English description | 856 | 96.72% |

The snapshot contains 345 images and 78 videos. All have a license ID, but
author coverage is incomplete. License/author metadata exists independently at
exercise, translation and media levels and must not be collapsed into one
blanket Wger license.

Exercise-level license distribution is 732 CC-BY-SA 4, 133 CC-BY-SA 3 and 20
CC0 records. Wger application code is AGPL-3.0-or-later; exercise content is
Creative Commons per individual record.

## Actual agent path

`suggest_workout` eagerly loads the bundled snapshot and reduces it to 884
records. One mislabeled-language meditation record is intentionally excluded.

The internal agent record retains only:

`id, name, category, equipment, is_bodyweight, derived_level`

It discards UUID, primary/secondary muscles, descriptions, media, licenses,
authors, variation group and source timestamps. Difficulty is app-derived from
equipment and name heuristics; it is not a Wger difficulty field.

Selection currently depends on category, inferred equipment, heuristic level,
requested muscle group/duration/goal and optional fatigue. It uses fixed
five-minute blocks and deterministic category/id order. Live Wger is not called
by this path.

## Profile and training state audit

The dispatcher automatically injects only weight and a mapping from
`health_goal` to workout goal. Fatigue and warning symptoms affect the tool only
when supplied in `user_state`.

For `WORKOUT_RECOMMENDATION`, Context Planner declares exercise history,
lifestyle and active plan optional, but its allowed tool list is only:

`get_user_profile, get_today_exercises, suggest_workout`

`get_exercise_log_range` is not allowed for this intent. Therefore the planner
cannot deterministically fetch a 7/28-day history before recommending.

## Workout log audit

The persisted mobile log has duration, estimated calories, type, coarse
intensity and a completed boolean. Chat context exposes still fewer fields.

Missing adaptive inputs include canonical exercise ID, per-set load, reps,
RPE/RIR, set completion, pain/discomfort, session RPE and partial completion
status. The workout player tracks completed sets in UI state, but those details
are flattened when the session is persisted.

## Energy audit

Wger does not supply the energy values used by the planner. Backend and mobile
assign MET values from app name/category heuristics. Backend then estimates
energy using `MET × 3.5 × kg / 200 × minutes`, but currently applies this to
each fixed five-minute exercise block.

The 2024 Adult Compendium is an appropriate activity-level source:
https://pacompendium.com/adult-compendium/. E2/E3 should map versioned session
or activity types to Compendium codes and label the result
`estimated_energy_expenditure`; resistance-set kcal must not be presented as an
exact measurement.

## Cache and sync audit

- The agent reads the backend JSON once at module import.
- Mobile's default catalog path reads the bundled asset through
  `LocalExerciseService`/`WgerCacheService`.
- Backend list/detail proxies call live Wger; only image/SVG proxies have a
  bounded in-memory LRU and 24-hour HTTP cache header.
- The manual fetch script paginates `/exerciseinfo/`, deduplicates integer IDs
  and atomically overwrites both bundles.
- The fetch script does not currently emit snapshot time, source schema,
  source hash, deletion/merge reconciliation or a batch manifest.

## Risks ranked for E2

1. High: training history cannot influence the current recommendation tool.
2. High: no canonical exercise identity/provenance survives into agent output.
3. High: workout logs cannot support safe progression decisions.
4. Medium: muscles and movement patterns are absent from ranking and balance.
5. Medium: fixed five-minute exercise duration distorts prescription and MET estimates.
6. Medium: snapshot/live drift is not reconciled.
7. Low but broken: legacy live search proxy calls a removed endpoint.

## E2 entry criteria

Before changing recommendation behavior, E2 should define a versioned
canonical exercise record and preserve Wger ID/UUID, snapshot hash, field-level
source ownership and per-content license. App-curated movement pattern,
difficulty and substitution group must be labeled as curated rather than Wger
data. The canonical build should remain offline-first and must not call live
Wger per chatbot request.

## Verification

```powershell
cd apps/backend
py -3.10 scripts/audit_exercise_data.py --verify
py -3.10 scripts/audit_exercise_data.py --live-check
py -3.10 -m pytest -q tests/test_exercise_data_audit_e1.py
```

The local manifest verifier does not require a stable live record count. Live
observations are volatile evidence and are deliberately separate from the
frozen snapshot identity.
