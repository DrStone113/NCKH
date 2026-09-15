# P2.1 ACCEPTANCE CLOSURE REPORT

## Infrastructure Repairs

- Added an oracle-firewalled P2.1A execution/scoring harness outside the frozen Plan V2 source set.
- Repaired the project-local Flutter cache through official bootstrap; no SDK source or version changed.
- Bootstrapped isolated PostgreSQL `16.15`, applied migrations `001` through `016` (39 public tables), and recorded checksums in the first-pass register.
- Kept historical V1 contamination distinct from the frozen P2.1A state.

## Acceptance Harness and Oracle Firewall

Development harness tests passed (`9 passed`). Execution receives only an `ExecutionCaseView`; its projection excludes oracle profile/check fields. Static tests prevent executor imports of scoring/oracle code, and an impossible development oracle did not affect execution output. The immutable raw artifact was written before scoring and declares `contains_oracle_fields=false`.

Legacy nutrition/workout execution calls the genuine legacy header path inside an acceptance-owned transaction and rolls it back. It captured 90 intended legacy inserts and left zero `p2-1a-*` legacy plan rows. Plan V2 invokes frozen public entrypoints directly, captured zero writes, and left zero `p2-1a-*` Plan V2 revision rows.

## Toolchain and PostgreSQL

- CPython `3.10.21`; `pip check` and `compileall` passed.
- Flutter `3.44.8`, Dart `3.12.2`; analyze exits 0 with 10 pre-existing INFO messages, and all 132 Flutter tests pass.
- The release web build completed successfully.
- PostgreSQL is `16.15 (Debian 16.15-1.pgdg12+2)` on an isolated test database.

The base live repository test passed save/read-back/hash/idempotency/owner-read evidence. The expanded lifecycle matrix discovered a frozen product failure: `PAUSED -> ACTIVE` rejects with `INVALID_PLAN_LIFECYCLE_TRANSITION`. It was not repaired.

## Freeze and First-Pass Register

Immediately before the atomic start, frozen Plan V2 sources, holdout, oracle, comparator, thresholds, exclusion index, and dedup protocol all matched. Flutter/Dart and PostgreSQL preflight also matched.

- Started: `2026-09-03T12:16:33.460063+00:00`
- Completed: `2026-09-03T12:16:34.071154+00:00`
- Result: `FAIL`
- Raw execution SHA-256: `e2944ad6b11a5285b76f0414b52160242ffc1d0071e9ed35ddd06ef63205fb9b`
- Score SHA-256: `6a87aa68e82ead5cdae4613dfc03f27da953055ca12943905778471299191239`

The two failed runner launches occurred before the atomic register update (direct-script package path, then Windows diff-byte decoding). Register state remained false and no raw artifact existed; both defects were repaired before the successful start.

## 120-Case Execution and Comparator Results

All 120 frozen cases executed exactly once. No case was skipped, replaced, or rerun.

| Category | N | Semantic pass | Semantic fail | V2 outcome |
| --- | ---: | ---: | ---: | --- |
| Nutrition | 30 | 12 | 18 | clarification required: 30 |
| Single workout | 30 | 27 | 3 | clarification required: 30 |
| Weekly workout | 30 | 6 | 24 | clarification required: 30 |
| Combined health | 15 | 7 | 8 | not found: 15 |
| Revision/lifecycle | 15 | 5 | 10 | not found: 15 |

Verdicts are `V2_BETTER=90`, `V2_EQUIVALENT=30`, `V2_ACCEPTABLE_DIFFERENCE=0`, `V2_REGRESSION=0`.

The raw executor correctly reports legacy combined/lifecycle cases as `NOT_COMPARABLE`; however the normalization adapter still lets the frozen comparator emit `V2_EQUIVALENT` for those 30 records. This makes reported `comparable_case_count=120` over-inclusive. It is a post-run harness reporting defect; this first-pass artifact will not be overwritten or rescored.

## Hard Invariants

Measured frozen hard-gate counts are zero for hard constraints, planned-to-actual leakage, unintended writes, invalid canonical references, cross-user access and policy hard-rule failures. Deterministic fixture match is `100%`. The run fails because request semantic match is `47.5%` (required `95%`) and reference-chain identity is `0%` (required `100%`). There are 63 semantic failures; complete immutable case detail is in the score artifact.

## Flutter / Edge Smoke

Microsoft Edge `152.0.4191.62`, driven by Playwright, loaded the release build at `http://127.0.0.1:4173` with HTTP 200 and no console/page errors. The public demo action opened the real health-profile onboarding flow. The smoke stopped there rather than bypassing authentication/onboarding, so authenticated dashboard Plan entry, plan detail, and chatbot deep-link browser evidence remains outstanding.

## Regression and Research Invariance

- Focused P1/P2/P2.1, N3/N3.1/N3.2 and research selection: `140 passed, 2 skipped`.
- Full backend: `895 passed, 3 skipped, 1 failed`; the only failure is a stale test assertion that still requires `first_pass_started=false` after a completed first pass. No post-score edit was made.
- `git diff --check` still finds three pre-existing whitespace errors in `bento_card.dart` and `docs/troubleshooting.md`; untouched.
- Research corpus tests: `16 passed`. Identity remains `offline-v1-636`, corpus hash `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`, manifest hash `5ed75adc4885b3b3b4f01554a4789605299dca965794819a76c81fc3e892afb1`.

## Remaining Product Work

1. Preserve this first-pass failure, then address prompt-to-bounded-request dispatch, combined/lifecycle execution, weekly scheduling request handling, reference-chain identity, and resume.
2. Repair the `NOT_COMPARABLE` normalization only in a later harness version; never modify this run.
3. Obtain authenticated Edge proof for dashboard Plan entry, plan detail, planned nutrition/workout, and exact chatbot revision deep-link.

```text
ACCEPTANCE_HARNESS_READY = NO
FLUTTER_PINNED_BASELINE_READY = YES
POSTGRESQL16_ACCEPTANCE_READY = YES

FIRST_PASS_STARTED = YES
FIRST_PASS_COMPLETED = YES
FIRST_PASS_RESULT = FAIL

P2_1_ACCEPTANCE_COMPLETE = NO
```
