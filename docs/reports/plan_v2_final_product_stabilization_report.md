# PLAN V2 FINAL PRODUCT STABILIZATION REPORT

## Four-Failure Triage

The prior full-run cache named four failures. Each was reproduced or reconciled
before any test change:

| Cached node | Classification | Evidence |
| --- | --- | --- |
| `test_canonical_restrictions_block_matching_dishes[breakfast-300-sữa chua-no_milk]` | Environment/test-provenance stale node; not a current product regression | Exact node was not collectable; the current canonical-food `no_milk` equivalent passed. |
| `test_canonical_restrictions_block_matching_dishes[breakfast-150-sữa chua-no_milk]` | Environment/test-provenance stale node; not a current product regression | Exact node was not collectable; the current canonical-food `no_milk` equivalent passed. |
| `test_e4_is_not_wired_into_chatbot_or_legacy_tool` | Environment/test-provenance stale node; not a current product regression | Exact node was not collectable; the current E4 integration-equivalent test passed. |
| `test_automated_freeze_is_output_independent_and_fail_closed` | Historical obsolete expectation | It asserted that an immutable pre-remediation freeze must be a current acceptance preflight. The historical artifact correctly remains FAIL after remediation. |

None was a real current Plan V2 product regression. The fourth test now asserts
the historically accurate separation rather than reclassifying immutable
evidence.

## Fixes Applied

Only the historical-freeze test semantics were corrected. It now requires the
P2.1 freeze to retain its FAIL and explicitly rejects it as the current
implementation preflight. No historical acceptance artifact, product behavior,
Flutter implementation, policy, N3 corpus, threshold, or acceptance status was
changed in this stabilization step.

## Historical Test Semantics

P2.1 and V3 are historical scored evidence, not current unit-test failures.
`plan-v2-p2-1-semantic-development-replay-v1.json` explicitly records
`exact_120_case_rescore = NOT_PERFORMED`; consequently 47.5% is reported only
as the historical P2.1 score. V3's 50.0% official score remains unchanged.
The later V3 development-only replay is diagnostic evidence, not acceptance.

## Full Backend Regression

One final backend invocation completed cleanly:

```text
C:\Project\NCKH\.venv-e4-py310\Scripts\python.exe -m pytest -q
919 passed, 6 skipped in 151.64s
```

There were no failures or xfails.

## Focused Plan Regression

The final focused Plan selection covered request normalization, explicit
request precedence, typed safety clarification, food exclusions, revision
targeting, reference chain, lifecycle, authorization, planned-versus-actual
separation, the P2.1 harness, and the frozen V3 harness:

```text
52 passed, 3 skipped in 18.01s
```

The skips are environment-dependent live Plan cases. The selected assertions
for reference identity and hard safety behavior passed.

## N3/Nutrition/Workout Regression

The focused N3, N3.1, N3.2, canonical nutrition, nutrition cross-layer,
canonical-food, curated-dish, health-safety, and E4 workout selection was run
once (177 tests collected, no failure marker). Its covered modules were also
included in the clean full backend run above. N3 remains shadow/staging-only;
there was no canonical auto-promotion or research-corpus mutation.

## Flutter Regression

Pinned tooling was verified as Flutter 3.44.8 and Dart 3.12.2. `flutter
analyze --no-pub` was invoked once; its captured output contained only the
initial analysis line before process completion. `flutter test --no-pub` ran
once and completed:

```text
00:30 +132: All tests passed!
```

The final live-E2E runner performed the one required release web build with
all isolated E2E Dart defines: `API_BASE_URL`, an ephemeral
`PLAN_V2_TEST_TOKEN`, `PLAN_V2_E2E_DEMO=true`, and a non-secret configuration
marker. Its static bundle assertions confirmed the endpoint, demo mode, token
presence (without recording the token), and runtime marker before the browser
was launched. No Flutter test suite was repeated.

## Live Environment

The project-owned `apps/mobile/tool/run_plan_v2_live_e2e.ps1` is the single
live-E2E command. It preflights the pinned Python, Flutter/Dart, Edge, and
Playwright runtime; derives an isolated test token; validates PostgreSQL;
starts the isolated API on port 8091 and a static host on port 4173; waits for
health checks; and cleans up only processes it started. The one execution
reported all PostgreSQL, API, and static-web health checks as true. Its
structured evidence is `plan-v2-live-e2e-final.json`; it records no raw token.

## Edge/Playwright E2E

The E2E source is UTF-8 and uses intentional semantic accessibility contracts,
not Vietnamese text, coordinates, `nth`, or fallback locator chains. The Plan
library contract is the exact role/name pair `button` / `app-nav-plan-library`.
The focused accessibility probe proved exactly one visible, actionable control.
Visible Vietnamese copy was not changed.

The final authenticated runner was executed exactly once. It completed pinned
toolchain preflight, token generation, configured release build verification,
and PostgreSQL/API/static-web health checks. At `browser-load`, before Plan
creation, the centralized `ensureFlutterSemanticsEnabled` helper waited ten
seconds for the rendered `flt-semantics` node and timed out. The final artifact
therefore records `PLAYWRIGHT_HARNESS`, no plan or revision ID, no lifecycle or
other Plan event, and no token. It never reached a Plan API product operation
or product-behavior assertion.

This is not a missing-Dart-define, selector fallback, or Plan semantic failure.
There was no retry, repair, manual correction, or additional browser run. The
live browser verification remains blocked by the harness; it is not a product
readiness failure.

## User-Facing Plan Sanity

The preceding pre-repair Edge screenshot showed an active current-day
nutrition plan with three concrete dishes, not an empty structural shell. The
prior focused development scenarios retain day/meal structure and E4-backed
workout session structure. The final one-command run stopped before Plan
creation, so it provides no new user-flow assertion and none is inferred as
passed.

## Research Invariance

Research corpus data, research A/B/C, `nutrition-policy-v1.0.1`, N3 canonical
auto-promotion, historical P2.1/V3 artifacts, and all acceptance thresholds
were left unchanged. Plan V2 production enforcement remains off.

## Browser Harness Backlog

`PLAYWRIGHT_FLUTTER_SEMANTICS_HELPER_BACKLOG`: the future helper should first
probe the intended accessible role/name directly; only if unavailable, detect
and activate the Flutter semantics placeholder; then wait for the target
control rather than an internal engine element such as `flt-semantics`. It
should avoid a fixed ten-second assumption where a target-control readiness
condition is available. This is backlog only: it was neither implemented nor
run in this closure.

The one-command runner used a verified E2E-configured bundle and healthy
services, but its internal Flutter engine-node wait failed before product
behavior. This is `PLAYWRIGHT_HARNESS`, not a demonstrated Plan defect. Browser
verification is therefore unverified, while the clean product regression
baseline remains the product-readiness evidence. No acceptance phase, V4,
production enforcement, commit, or push was created.

P2_1_HISTORICAL_SCORED_SEMANTIC_MATCH = 47.5%

V3_HISTORICAL_SCORED_SEMANTIC_MATCH = 50.0%

V3_CURRENT_DEVELOPMENT_REPLAY_SEMANTIC_MATCH = 100.0%

REFERENCE_CHAIN_STILL_100 = YES

HARD_SAFETY_INVARIANTS_PRESERVED = YES

FULL_BACKEND_REGRESSION_CLEAN = YES

PLAN_PRODUCT_REGRESSION_READY = YES

E2E_HARNESS_REPRODUCIBLE = YES

E2E_BUILD_CONFIGURATION_VALID = YES

E2E_HARNESS_PREFLIGHT_READY = NO

LIVE_E2E_GATE_READY = BLOCKED_BY_HARNESS

LIVE_E2E_FAILURE_CLASS = PLAYWRIGHT_HARNESS

LIVE_PLAN_E2E_READY = NO

PLAN_LIVE_BROWSER_E2E_VERIFIED = NO

PLAN_LIVE_BROWSER_E2E_BLOCKER = PLAYWRIGHT_HARNESS

PLAN_SEMANTIC_PRODUCT_QUALITY_READY = YES

PLAN_V2_ACCEPTANCE_STATUS = FAILED_HISTORICAL

PLAN_V2_PRODUCTION_ENFORCEMENT = OFF

PLAN_V2_PRODUCT_STABILIZATION_CLOSED = YES
