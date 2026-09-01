# Plan Tool V2 (P1)

Plan V2 changes the agent-facing plan flow from raw list assembly into a
versioned, auditable state machine.  It is intentionally independent of the
legacy `plans` and `plan_items` tables and does not alter frozen nutrition,
exercise, catalog, or research artifacts.

## Public tool surface

The agent catalog exposes `build_nutrition_plan`, `build_workout_schedule`,
`get_plan`, `get_active_plan_v2`, `revise_plan`, `save_plan`, and
`set_plan_status`.  Legacy `create_plan`, `append_plan_items`,
`create_long_term_plan`, `get_active_plan`, and `mark_plan_item_complete` are
not public agent tools.  Their historical REST/client paths remain readable.

`PlanRequest` is immutable and accepts only period, IANA timezone, bounded
constraints/preferences, and a goal override.  Calorie formulas, macro
formulas, exercise dosage, canonical totals, and policy metadata are resolved
by the nutrition/E4 domain layers instead of the LLM.

## State, revisions, and actual data

`PlanRevision` records plan/revision identity, parent revision, local period,
lifecycle, validation, policy/catalog provenance, snapshots, structured items,
summary, explanations, and a deterministic content hash.  The lifecycle is
`DRAFT → PENDING_CONFIRMATION → SAVED/ACTIVE`, with pause, completion,
cancellation, and supersession states.

Plan items are always `PLANNED` or cancelled.  Validator checks reject
`consumed_at`, `logged_at`, `performed_at`, and `actual_reps` in plan content.
Planned meals do not enter nutrition totals and planned workouts do not enter
training history.  A meal/workout observation still requires its own explicit
log/result action.

Edits create a new draft revision; no active or saved revision is mutated.
Optimistic revision checks reject stale branches.  Activation supersedes an
overlapping active revision of the same user/domain.  Scheduling uses local
dates plus an IANA timezone, including `Asia/Ho_Chi_Minh` through the explicit
cross-platform `tzdata` dependency.

## Domain delegation

Nutrition drafts call the existing canonical nutrition calculation and the
canonical dish selector.  Constraint metadata and canonical dish/food
references are retained on each meal.  The validator independently checks
stored allergen/tag facts against hard exclusions.

Workout drafts only wrap an E4-produced session and canonical exercise IDs;
P1 never makes a second resistance-prescription algorithm.  A multi-session
week is deliberately returned as a clarification until E4 offers a weekly
scheduler, rather than duplicating a single session or inventing recovery and
volume rules.  A `COMBINED_HEALTH` plan is a reference-only container over
child revisions and never adjusts food calories using exercise energy.

## Confirmation and shadow mode

After a ready preview, `PendingUserAction` stores the exact plan ID, revision
ID, and content hash.  Confirmation dispatches the stored `save_plan` payload
without asking the LLM again.  Save read-back must match the three values;
network retries reuse the same owner-bound action key.

`PLAN_TOOL_MODE=shadow` is the default.  It uses the thread-safe isolated V2
revision repository, never writes legacy plan rows or observations, and labels
the result `SHADOW_SAVED` in the UI.  SQL migration `010_plan_tool_v2.sql`
provides the future V2 schema, active-period exclusion constraint, idempotency
actions, and legacy classification table.  `enforced` deliberately fails
closed until an SQL repository and database read-back gate are wired.

## Presentation and tracing

The backend emits a `versioned_plan` structured payload with local-day cards,
canonical references, summary, reason codes, revision, and planned-state
boundary.  Flutter renders it with `VersionedPlanCard`; the LLM is not used to
recreate a markdown schedule.  Public trace events describe plan read,
validation, revision, and persistence without IDs.  Developer traces retain
only allowlisted IDs/statuses and redact sensitive context.

## Verification

`services/plan_engine/development_scenarios.py` has 103 named development
scenarios for nutrition, workout, combined, revision, lifecycle, persistence,
timezone, planned/actual boundaries, legacy, validator, and invariant cases.
They are engineering fixtures, not research outcomes.  The backend tests
cover revision immutability, hash confirmation, idempotency, stale-write and
cross-user rejection, overlap semantics, nested Intake V2 context, allergen
constraints, and planned-to-actual leakage.

Current gate: `PLAN_TOOL_V2_SHADOW_READY=NO` until a side-by-side legacy/V2
development comparator and its acceptance threshold are added.  The isolated
shadow implementation and its invariant suite are ready for that gate; it is
not represented as a production replacement.

Current gate: `PLAN_TOOL_V2_ENFORCEMENT_READY=NO` (SQL repository/read-back
and E4 weekly schedule are intentionally not claimed as complete).
