# PLAN TOOL V2 P2.1R QUALIFICATION REPAIR REPORT

## Invalidated Acceptance V1

`plan-tool-v2-p2-acceptance-v1` is preserved unchanged and permanently
reclassified as `CONTAMINATED_DEVELOPMENT`, not acceptance-eligible.

- Original content SHA-256: `6e5a24ef394eaefd6e254c2155e10dc002763fad21e32056f88c327890b0a712`
- Rows: 120; unique prompts: 50; duplicate rows beyond the first: 70.
- Exact overlap with `development_only` natural prompts: 120/120.
- Status artefact SHA-256: `16e4cba11dc8229c7fd5f3732ddf85b29555e4abc8c7d24c0a5ca63632649322`.

It may be used only for regression/leakage detection, never for independent
acceptance, release qualification, or threshold tuning.

## P1 Inventory Reconciliation

`P1_DEVELOPMENT_V2_INVENTORY` freezes the truthful inventory at **106** valid
scenario IDs, all `USED_FOR_DEVELOPMENT`.

- Historical/documented count: 103; actual source count: 106.
- Source: `services/plan_engine/development_scenarios.py`
  (`ce8591b853be3aa63ba2c6227a0e5303c52cb9cea974804db094e9dabab2b368`).
- The available Git history introduces this file in one commit
  (`32abb17`, 2026-09-01); it has no per-scenario creation/order history.
  The three-case delta is therefore recorded as `UNATTRIBUTED_DELTA`, not
  erased or guessed.

## Development Exclusion Index

Generated `PLAN_V2_DEVELOPMENT_EXCLUSION_INDEX_V1` contains **605** stable
records (499 with normalized text): all 106 P1 IDs, 50 P2 natural-development
prompts, 120 contaminated V1 rows, and Plan V2 regression-fixture literals.

- Canonical record SHA-256: `925b15d808bafa9f8ddadcc75168231371347a48601effe9a49e54c058723681`.
- Stored index SHA-256: `42b3da22815ed1c996930a0803d707be33f03851476fd8f06ef220beebaa9ced`.
- Rebuild from current inputs matched at verification time.

## Dedup Protocol

`DEDUP_PROTOCOL_V1` is frozen before candidate review
(`b6da80f22b1796dd21a6147eeca8c412645f43648cfc22413a8e3db39bbd5236`).
It checks normalized/casefold/punctuation duplicates, parameter-only template
duplicates, entity-substitution scenario structure, and lexical semantic
candidates; embeddings alone are explicitly insufficient. Flagged semantic
pairs require human disposition.

## Acceptance V2 Authoring

`qualification_candidates_v2.py` contains a newly authored, unexecuted
Vietnamese candidate pool (`75df6acfbe5bf8fb5015b3674de4c66dd2bb644af6350bfaf0d9ec3b7f85f8a2`).

- 150 candidate prompts, all unique.
- 120 proposed cases: nutrition 30, single-session workout 30, weekly 30,
  combined-health 15, revision/lifecycle/concurrency/adversarial 15.
- 30 candidates were explicitly not selected because their intent/oracle was
  ambiguous or unsafe to freeze.
- No candidate was executed against Plan V2 while being authored.

## Leakage Audit

Against the current exclusion index, the pre-freeze verifier found:

- exact/normalized development overlaps: **0**;
- template/structure overlaps: **0**;
- semantic candidates requiring human disposition: **0**;
- duplicate proposed prompts: **0**.

This is a pre-freeze automated audit, not evidence that human review has
occurred.

## Oracle

The candidate oracle defines outcome profiles with acceptable, forbidden, and
required invariants independent of Plan V2 output. Every proposed case maps to
one defined profile.

Its status is deliberately `CANDIDATE_NOT_FROZEN` and
`PENDING_HUMAN_REVIEW` (`7d83c540472a00f88782a312ade6289fdd7b3d53d625c781d2e521293d5b4a59`).
The review template records the necessary per-case human disposition and
optional two-person review. No human review is claimed or fabricated.

## Dataset Freeze

No final `PLAN_V2_ACCEPTANCE_V2` has been created. The 120 cases are proposed
candidates only, all `acceptance_eligible=false`, until human review and an
immutable review register are completed. Therefore no scored acceptance metric
exists.

## Toolchain Installation

The existing `apps/mobile/.fvmrc` already pins `3.44.8`. A project-scoped,
ignored SDK was installed at:

`C:\Project\NCKH\apps\mobile\.fvm\flutter_sdk\bin\flutter.bat`

This leaves global Flutter untouched. `apps/mobile/.gitignore` ignores only
the SDK directory; `pubspec.yaml` was not changed. `pub get` temporarily
resolved four older compatible transitives for Dart 3.12.2; the generated
`pubspec.lock` change was reverted after smoke, so P2.1R leaves no application
dependency change.

## Flutter 3.44.8 Verification

Pinned executable result:

- Flutter `3.44.8`, Dart `3.12.2`.
- `flutter pub get`: passed.
- `flutter analyze`: `No issues found!`.
- `flutter test`: 119/119 passed.
- `flutter build web --release --no-tree-shake-icons`: passed.

## Flutter 3.47.1 Compatibility

Global PATH remains the optional runtime: Flutter `3.47.1`, Dart `3.13.1`.
It was version-checked only in P2.1R and is not the acceptance authority.

## Implementation Source Freeze

`PLAN_V2_IMPLEMENTATION_FREEZE_P2_1R_V1`
(`58abdea52c9466e25dd9b71e8e50dc7e588ea52d46b74937b6a50c6f5ff993f8`)
freezes P1 inventory plus Plan Engine, validator, comparator, weekly
scheduler, nutrition horizon, SQL repository, pending-action integration, and
high-level Plan V2 tools. The verifier found no source-hash mismatch.

## Qualification Verifier

`scripts/verify_plan_v2_qualification.py` is a non-scoring fail-closed
preflight. It verifies pinned Flutter/Dart, frozen protocol inputs, candidate
counts/uniqueness, exclusion-index currency, leakage/dedup checks, oracle
state, and implementation hashes. The reserved acceptance entry point invokes
the preflight first and returned exit code 2 (`PLAN_V2_ACCEPTANCE_BLOCKED`).
There is no bypass flag.

The preflight currently reports all automatic gates green except
`ORACLE_FROZEN=NO` and `HOLDOUT_V2_FROZEN=NO`; it therefore correctly returns
`READY_TO_RUN_P2_1_ACCEPTANCE=NO`.

## Regression Smoke

- Backend CPython 3.10.21: **841 passed, 2 skipped**.
- Protocol-focused tests: **23 passed**.
- `git diff --check`: passed.

No comparator, weekly, multi-day nutrition, database, chatbot, or staged
acceptance case was scored in this phase.

## Research Invariance

The research verifier passed with scientific identity match:

- `offline-v1-636`;
- frozen manifest `5ed75adc4885b3b3b4f01554a4789605299dca965794819a76c81fc3e892afb1`;
- corpus `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`;
- scientific identity `e549043d7f56431ab76cf6ce3015044d8f33aca1b743780212d97c12dcc0451a`.

No research pilot or final was run.

## Remaining Issues

1. The proposed V2 cases and oracle require actual human review and an
   immutable review register before they can become a holdout.
2. Only after that review may `PLAN_V2_ACCEPTANCE_V2` be frozen and P2.1 first
   scored acceptance begin.
3. The P1 103-to-106 delta has no attributable per-scenario history in the
   available repository; its truthful 106-case inventory is preserved.

## P1_DEVELOPMENT_CASE_COUNT

106

## ACCEPTANCE_V1_STATUS

CONTAMINATED

## ACCEPTANCE_V2_CASE_COUNT

0 (not frozen; 120 proposed candidates)

## ACCEPTANCE_V2_UNIQUE_COUNT

0 (not frozen; 120 proposed candidates are unique)

## CONFIRMED_DEVELOPMENT_OVERLAP

0 (automated pre-freeze audit)

## TOOLCHAIN_BASELINE_VERIFIED

YES

## HOLDOUT_V2_FROZEN

NO

## ORACLE_FROZEN

NO

## IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE

YES

## READY_TO_RUN_P2_1_ACCEPTANCE

NO
