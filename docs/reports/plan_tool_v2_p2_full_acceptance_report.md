# PLAN TOOL V2 P2 FULL ACCEPTANCE REPORT

## Baseline Snapshot

- Baseline commit: `5c5f5a8 feat: expand Vietnamese dishes and workout planning`.
- The worktree was already dirty (P1 and unrelated work); it was preserved and never reset or cleaned.
- P1 baseline hashes recorded before P2 edits:
  - `plan_engine/contracts.py`: `936ff8e65fb77bb775a33dfe888564b6d868033515b7725822cea013bd6356f2`
  - `plan_engine/engine.py`: `8f7ee27297b7c9b02dbad9cce49f2abd74d23ca8a35e622603528ed069d9a7ba`
  - `agent/tools/plan_v2.py`: `93894ab184ad711a123f24aa3398b63153e207da4c3d4c6ba887e5f3636223d0`
  - `workout_planner/integration.py`: `9979407cf18aa56cb84969d6e31372d9e7e784fc7d0a0e94a586ea848307f25c`
  - `nutrition/catalog.py`: `1d0f75daec6286a843019cba5e6812007605ada1d5fd14d71c57c68105714c08`
  - Flutter `versioned_plan_card.dart`: `cc41b778dbddec89ae18f34479632871c0b3bf0ee99c260b13ca06a03d36c8fe`

## Runtime

- CPython `3.10.21` was used for backend validation through `.venv-e4-py310`.
- Shell default Python is `3.11.0` and was not used for the backend gate.
- Installed Flutter is `3.47.1`, not the requested `3.44.8`; Flutter results below are accurately labelled with 3.47.1.

## Comparator Architecture

`PlanV2Comparator` compares normalized semantic dimensions, distinguishes `NOT_COMPARABLE`, produces reason-coded per-case results, and treats a safe V2 rejection of a legacy hard violation as `V2_BETTER`.

## Comparator Acceptance Dataset

Frozen before execution: `apps/backend/validation/plan_tool_v2_p2/acceptance-v1.json`.

- Version: `plan-tool-v2-p2-acceptance-v1`
- SHA-256: `6e5a24ef394eaefd6e254c2155e10dc002763fad21e32056f88c327890b0a712`
- Oracle version: `p2-engineering-oracle-v1`
- Distribution: 30 nutrition, 30 single-session workout, 30 weekly scheduling, 15 combined, 15 lifecycle/adversarial.
- A distinct controlled natural-language development set contains 50 prompts and is explicitly not research evidence.

## Comparator Results

No real legacy read-only adapter or side-by-side shadow telemetry source exists yet. The frozen corpus was not represented as an executed legacy-versus-V2 result.

## Legacy Regressions

Known legacy auto-active/planned-as-actual behavior is deliberately not treated as a V2 mismatch. No new legacy behavior was modified.

## V2 Improvements

- Reason-coded semantic comparator.
- No planned-to-actual fields allowed at any nested plan-content depth.
- Save and activation are separate; pending "Lưu" actions now pass `activate=false`.

## Weekly Workout Scheduler

`WeeklyWorkoutScheduler` deterministically allocates requested dates, honors exact Vietnamese/ISO days, respects unavailable days, and labels count-only spacing as `PRODUCT_SCHEDULING_HEURISTIC`.

## PlanningHorizonState

`PlanningHorizonState` contains authoritative actual training-state availability plus planned E4 exposures only. It stores planned exercise/muscle/movement exposure and duration, never actual completion, recovery, fatigue, performance, RPE/RIR, or load.

## E4 Delegation

One E4 `READY` payload is required for every scheduled slot. The scheduler contains no exercise, sets, reps, rest, effort, volume, safety, or time prescription constants.

## Weekly Workout Validation

Dedicated unit coverage verifies 2/3/4 sessions, 30/45/60 minute budgets, exact days, count-only scheduling, consecutive days, uneven availability, E4-per-slot wrapping, and planned-state separation. Full 120-case acceptance execution is still pending the comparator/shadow harness.

## Nutrition Multi-Day Hardening

`NutritionPlanningHorizonState` keeps planned daily totals separate from consumed state. Existing nutrition policy/canonical selector remains authoritative; no second calculator was added.

## Nutrition Variety

Deterministic variety output records dish, primary-protein, and dish-pattern repetition as `SOFT_PLANNING_TARGET`; it never fabricates substitutions and a user preference may override it.

## SQL Repository

`PlanSqlRepository` is a real async PostgreSQL repository for enforced mode, separate from the memory shadow repository.

## Database Migration

Added migrations `011`–`013` for operation-scoped idempotency, immutable item ordering, and logical item identity across revision snapshots. A disposable live PostgreSQL 16 database successfully applied migrations `001`–`013` from the current project schema.

## Authentication / Ownership

Enforced mode requires a dispatcher-supplied `AuthenticatedPrincipal`; it rejects anonymous/client-supplied identity. SQL reads and writes are owner-scoped; a live cross-user read was rejected.

## Transactions

Save, active-overlap supersession, idempotency claim, item snapshot persistence, and in-transaction verification are one database transaction. Transaction exceptions return `PLAN_PERSISTENCE_TRANSACTION_FAILED` rather than a success result.

## Read-Back Verification

The repository verifies plan/revision/owner/hash/lifecycle/policy/catalog/items in transaction and again after commit. Tool success is returned only after this succeeds.

## Content Hash Identity

Preview, persisted, and read-back hashes matched in the live PostgreSQL save and revision test. Immutable item order and logical item identity are stored explicitly to preserve the hash across revisions.

## Idempotency

The SQL ledger is scoped by `(authenticated owner, operation, action id)`. A duplicate live save produced one revision.

## Optimistic Concurrency

New persisted revisions validate parent revision ID and revision number under lock; stale parents yield `PLAN_REVISION_CONFLICT`.

## Active Plan Overlap

The existing PostgreSQL exclusion constraint remains active. Activation transactionally supersedes an overlapping active plan for the same owner/domain; `COMBINED_HEALTH` remains a reference container.

## PendingAction Integration

`SAVE_PLAN_REVISION` binds the displayed plan/revision/hash exactly and now saves without activation. Status transitions remain explicit commands.

## Confirmation Integrity

The identity chain remains `preview = pending action = persisted = read-back`; the Flutter card renders the returned revision without internal UUIDs.

## Shadow Mode

Default remains `PLAN_TOOL_MODE=shadow`. Shadow retains isolated memory persistence and cannot mutate legacy plan/observation records.

## Shadow Acceptance

Not complete: side-by-side legacy adapter/telemetry and the frozen 120-case comparator run are still required.

## Enforced Staging

Not run. Enforced mode is blocked in production by the tool path and requires an authenticated principal in a non-production environment.

## Chatbot E2E

Not run against a staging chatbot. No legacy fallback was added to the enforced repository path.

## Flutter Plan UX

`VersionedPlanCard` now shows friendly lifecycle labels, revision, planned labels, valid lifecycle action affordances, and a non-destructive revision-conflict message.

## Public Trace

Added allowlisted plan/weekly trace events for schedule checking, scheduled sessions, and confirmed version identity. They are fixed copy, not model reasoning.

## Debug Trace

Existing debug isolation remains in force; repository failures are stable reason codes and no raw chain-of-thought was added.

## Failure Injection

Fail-closed repository paths exist for hash mismatch, transaction error, read-back mismatch, idempotency-key reuse, stale parent, authorization failure, and lifecycle conflict. A complete injected failure matrix and staging chatbot execution remain pending.

## Live PostgreSQL

PASS on disposable PostgreSQL 16 container: migration, save, read-back, duplicate retry, activate, cross-user denial, and revision-2 persistence all passed. The container is disposable and no project/production DB was modified.

## Performance

No acceptance performance distribution was reported: an end-to-end comparator/staging harness is required to provide meaningful nutrition, E4, weekly, SQL, revision, and combined p50/p95/max figures.

## Legacy Deprecation Plan

- Legacy read paths: `modules/plans/router.py`, legacy REST consumers, and historical `plans`/`plan_items` records remain readable.
- Legacy migration path: `legacy_plan_v2_classification` remains append-only.
- Legacy LLM write exposure: zero (`create_plan`/`append_plan_items` are not registered in the server tool catalog).
- Legacy writes remain relevant only to historical/off flows.
- Removal requires comparator acceptance, staging enforced E2E, retained-data migration/read audit, production security review, and rollback rehearsal.

## Full Regression

- Backend CPython 3.10.21: `840 passed, 2 skipped`.
- Live PostgreSQL test: `1 passed`.
- Flutter 3.47.1: `flutter pub get`, `flutter analyze`, `flutter test` (`119` passed), and `flutter build web --release` passed.
- `compileall`, `pip check`, and `git diff --check` passed.

## Research Invariance

Verified unchanged/valid:

- `offline-v1-636`
- Frozen research manifest `5ed75adc4885b3b3b4f01554a4789605299dca965794819a76c81fc3e892afb1`
- Corpus `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`
- Nutrition policy, E2 catalog, and exercise policy verifier all passed.
- No research pilot/final was run and no engineering metric is called a research outcome.

## Remaining Issues

1. No genuine read-only legacy adapter/telemetry has executed the frozen 120-case comparator corpus.
2. No 50-prompt chatbot shadow run or controlled enforced staging E2E was run.
3. Failure-injection and performance distribution gates are incomplete.
4. Flutter 3.44.8 was unavailable; validation used installed Flutter 3.47.1.

## PLAN_V2_COMPARATOR_READY

NO

## WEEKLY_WORKOUT_SCHEDULER_READY

NO

## NUTRITION_MULTIDAY_PLANNER_READY

NO

## PLAN_SQL_PERSISTENCE_READY

YES

## PLAN_AUTHORIZATION_READY

YES

## PLAN_V2_SHADOW_READY

NO

## PLAN_V2_ENFORCEMENT_READY

NO

## PLAN_V2_PRODUCTION_ROLLOUT_READY

NO
