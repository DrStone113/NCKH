# PLAN V2 SEMANTIC REMEDIATION REPORT

## Scope and immutable acceptance record

This is product-quality remediation in `C:\Project\NCKH`, not a new
qualification exercise. P2.1 and V3 remain immutable historical evidence.
No holdout, oracle, threshold, execution register, raw execution, or V3 result
was changed. The official V3 result remains **FAIL**: 120 cases, 50.0% request
semantic match, 100.0% reference-chain identity, and zero hard violations.

The following current hashes reconfirm that the frozen V3 inputs and official
execution evidence remain intact:

| Artifact | SHA-256 |
| --- | --- |
| Holdout | `8256ca62b344957c6e36b2580551777092cced2b85c84a381091b715511b519b` |
| Oracle | `bb92a47b3edc8ec8a5ce13a1fb6e30a25738651bbf1c30ff413a98f3e3eb8af5` |
| Thresholds | `adeb1a8139c15eb619f3bc92ad89e68197aa056b61f567d3fb58379b040a5400` |
| Official V3 results | `022a0ef06045f8f053bef9ea1422f19c9c7252b8cb0d437c922910de75e79b0b` |
| Official V3 raw execution | `ea9c3b29312b602059eca7ed086ed621ccd57fb372996ac263ffd6034aff844c` |
| Official V3 register | `58718243f98e95845ff2650738ee3aa87e0970ac79a127f961ac7c2ae015435c` |

The detailed, per-case machine-readable inventory remains
`apps/backend/validation/plan_tool_v2_p2/plan-v2-v3-semantic-failure-inventory-v1.json`.
It contains all 60 failures without duplicating raw request blobs here.

## V3 Failure Taxonomy

All 60 historical V3 semantic mismatches reconcile exactly with 50.0% of 120
cases. No V3 failure was an operation, target, canonical-reference, write, or
actual-observation failure.

| Primary cause | Product semantic category | Cases | Families | Ownership | Observed behavior |
| --- | --- | ---: | --- | --- | --- |
| `SCORER_FALSE_NEGATIVE` | `MISSING_CONTEXT` / `CLARIFICATION_POLICY` | 40 | 20 `single_workout`, 20 `weekly_workout` | `MULTI_FACTOR` (primary scorer) | The fixture omitted an authoritative workout profile and exercise-safety profile. Plan V2 safely returned clarification; the frozen scorer incorrectly required `READY`. |
| `HARNESS_EXPECTATION_ERROR` | `CONTEXT_PRECEDENCE` / combined-plan binding | 20 | `combined_health` | `MULTI_FACTOR` (primary harness) | The fixture supplied symbolic child labels, not concrete plan/revision/content-hash bindings. Plan V2 safely declined to fabricate a combined container; the frozen scorer required one. |

For every record, the expected frozen state, observed state, semantic diff,
reference information, warnings, and provenance are retained in the inventory.
Reference identity remained identical for every V3 record.

## Pareto Root Causes

1. Missing workout authority evaluated as a `READY` requirement: 40/60,
   66.67% cumulative.
2. Symbolic combined-child references evaluated as concrete bindings: 20/60,
   100.00% cumulative.

The smallest complete explanation of V3 is therefore two harness-side causes.
The trace is: frozen request -> V3 adapter context projection -> Plan V2 safety
gate / combined binding gate -> immutable raw result -> frozen scorer. The
divergence occurs in the fixture/scorer expectation after safe product
behavior, not in canonical reference selection or a product write.

## Root Cause Fixes

The V3 harness is frozen and was not edited. The following independent,
general product defects were found through executable natural development
flows and corrected without case IDs, holdout text, or oracle values.

| Fix | General behavior | Implementation | Regression / negative control |
| --- | --- | --- | --- |
| `SEM-PROD-001` | One typed normalization projection canonicalizes equivalent goal, weekday, equipment, date, timezone, ID, and food-exclusion representations without inventing missing facts. | `services/plan_engine/request_normalization.py`; Plan V2 tool entry points | Vietnamese weekday/equipment aliases; invalid date/timezone/weekday stays an explicit clarification. |
| `SEM-PROD-002` | An explicit one-day request takes precedence over an older weekly preference and resolves to one requested session. | `services/agent/tools/plan_v2.py` | A profile with Mon/Wed/Fri and three saved sessions still creates one requested-day session. |
| `SEM-PROD-003` | Plan goals map deterministically to E4 goals (`maintain` -> `GENERAL_FITNESS`, etc.); known E4 policy failures become typed clarifications rather than generic planner-unavailable output. | `request_normalization.py`; `services/workout_planner/integration.py`; `plan_v2.py` | Unknown explicit goals are not silently replaced by profile defaults; missing safety authority still clarifies. |
| `SEM-PROD-004` | A food exclusion is either a documented dietary/allergen alias or a separate literal ingredient exclusion. It is never passed as an invalid policy enum. Both selector and revision validation enforce the appropriate rule. | `request_normalization.py`; `services/agent/tools/dish.py`; `services/plan_engine/engine.py` | `fish` becomes canonical `no_fish`; an unrecognised literal remains literal rather than becoming a fabricated policy constraint. |
| `SEM-PROD-005` | Revision/lifecycle targets are trimmed but never inferred, retaining exact plan/revision identity. | `services/agent/tools/plan_v2.py` | Missing target IDs return typed non-persisted responses; a meal-slot revision has a new revision ID and the exact parent revision ID. |

No planner prompt wording, V3 case ID, fixture name, frozen request string, or
expected result is present in the production paths above.

## Request Normalization

`NormalizedPlanRequest` is the authoritative structured representation for
Plan V2 tool inputs. It records intent/domain/operation; exact period and
timezone; goal and source; meal and nutrition constraints; session count,
weekdays, duration, equipment; revision targets; and clarification needs.
Missing data remains missing. Exact dates and a valid timezone are required
for planning; missing workout authority, exercise safety, or multi-day
frequency produces a deterministic clarification requirement instead of a
guess.

## Clarification Improvements

Clarification is now specific where safety authority is absent
(`WORKOUT_PROFILE_REQUIRED` or `EXERCISE_SAFETY_CONTEXT_REQUIRED`) and for
invalid/missing mandatory structured inputs. Optional plan details remain
optional. Symbolic combined child references and plain prose item replacement
remain non-executable by design: the system asks for concrete canonical
references rather than fabricating a plan item.

## Context Precedence

The applied precedence is explicit current request > confirmed user facts >
authoritative persisted state > older observations > candidates/inferences.
The one-day workout regression proves a current date-bound request cannot be
blocked by a stale persisted weekly preference. Candidate facts are not
promoted into constraints.

## Nutrition Fixes

The three-day nutrition flow returns nine planned meals with canonical dish and
food references, recalculated nutrition, and no consumption observation. A
temporary `fish` exclusion is now represented as `no_fish`, while an arbitrary
ingredient stays a literal exclusion and is checked against canonical dish
facts. `nutrition-policy-v1.0.1` was not changed.

## Workout Fixes

The weekly flow produces three non-empty E4 sessions on the requested
Mon/Wed/Fri dates, each within the 45-minute bound and with no performed
observation. Vietnamese weekday/equipment forms normalize deterministically.
The Plan-to-E4 goal vocabulary mismatch and one-day scheduling-precedence bug
are fixed at the typed boundary, not by prompt instructions. Catalog coverage
can still legitimately produce a clarification when a very restrictive
equipment/time combination has insufficient eligible exercises.

## Combined Plan Fixes

No combined-plan product behavior was changed. The V3 combined failures had
only symbolic child labels; requiring concrete child revision identities and
cross-domain provenance is the correct behavior. No exercise-calorie
compensation or fabricated child plan was introduced.

## Revision/Lifecycle Fixes

The natural nutrition flow creates a child revision for a concrete meal-slot
change, preserves the parent revision identity, then saves, activates, pauses,
and resumes that exact child revision. The plan remains planned-only
throughout. Target identity normalization cannot create an ID that was not
supplied.

## Failure Regression

Development-only regression coverage is in:

- `tests/test_plan_v2_request_normalization.py`
- `tests/test_plan_v2_semantic_product_scenarios.py`

Focused runs passed:

- `33 passed` — request normalization, natural nutrition/revision/lifecycle,
  natural workout, Plan Engine, and lifecycle tests.
- `47 passed` — dish catalog/canonical food/safety plus the new product tests.
- `18 passed, 3 skipped` — reference-chain, Plan API (live cases skipped),
  P2.1 harness, frozen V3 harness, semantic-contract, and postmortem tests.

The negative controls retain meaningful distinctions: invalid dates/timezones
do not acquire defaults; unknown goals do not become profile defaults; missing
safety authority cannot create a workout; and literal exclusions are not
rewritten as arbitrary policy enums.

## P2.1 Historical Scored Evidence

`plan-v2-p2-1-semantic-development-replay-v1.json` records
`exact_120_case_rescore = NOT_PERFORMED`.  Its 47.5% value is the immutable
historical P2.1 scored result, not a current-code development replay.  No
current implementation was executed across the P2.1 corpus merely to replace
that historical number.

## V3 Development Replay

`plan-v2-v3-semantic-development-replay-v1.json` is likewise
`DEVELOPMENT_ONLY_KNOWN_DATA`. It replayed 120 known V3 inputs under the
corrected semantic contract: historical 50.0%, development replay 100.0%, and
zero hard violations, leakage, unintended writes, and cross-user access. This
is diagnostic evidence only; it does not alter official V3 FAIL.

## Natural Product Scenarios

Development scenarios cover the intended Vietnamese flows at the structured
boundary: a three-day menu with a fish exclusion, three weekly workouts on
Monday/Wednesday/Friday, a one-day workout despite older weekly preferences, a
concrete meal-time revision, and pause/resume of the exact revision. A request
to replace a meal by prose alone is deliberately not accepted until a domain
resolver supplies a canonical replacement.

## Plan Usefulness

The tested nutrition output contains nine real canonical dishes with day/meal
structure. The tested workout output contains three E4-backed sessions with
real exercises and bounded duration. Both remain drafts/plans rather than
actual meal or workout records.

## N3 Integration

No new N3/N3.1/N3.2 production path was added in this remediation. Plan V2
continues to select from canonical dish facts; external candidates remain
staging-only and no canonical auto-promotion, web nutrition authority, or
research-corpus mutation occurred. A separately scoped integration is still
needed before Plan V2 can use an expanded N3 candidate pool while retaining
canonical recalculation and `RecipePortionFitter` guarantees.

## Fixed Invariant Verification

The immutable V3 evidence retains 100.0% reference-chain identity and zero
hard violations. Focused identity/harness tests pass. Development replays show
zero planned-to-actual leakage, unintended writes, and cross-user access; the
natural scenarios assert planned-only content. No fabricated recovery or
history behavior was introduced.

`settings.plan_tool_mode` remains `shadow` in the current development
environment. Production enforcement is not enabled.

## Edge Product QA

The historical authenticated Edge evidence remains PASS and unchanged.  The
final live product invocation restored the minimum local services, created and
activated an authoritative nutrition plan, then reached the rendered Plan
library after its lifecycle/readback steps. Its screenshot shows a current-day
nutrition plan with three real dishes. The run failed only when the harness
looked up the Nutrition tab with a mojibake text literal; the visible UI label
was present. This is a browser-harness selector/encoding defect, not evidence
of a Plan V2 product regression. Per the no selector-polish-loop rule, it was
not patched or rerun. The initial PostgreSQL-unavailable failure is separately
preserved as environment evidence. Flutter widget tests passed 132 tests.

## Regression

Commands run with the pinned Python 3.10 environment:

```text
python -m pytest -q tests/test_plan_v2_request_normalization.py tests/test_plan_v2_semantic_product_scenarios.py tests/test_plan_engine_p2.py tests/test_plan_lifecycle_p2_2.py
python -m pytest -q tests/test_curated_dish_catalog.py tests/test_canonical_food_provenance.py tests/test_health_safety_eval.py tests/test_plan_v2_request_normalization.py tests/test_plan_v2_semantic_product_scenarios.py
python -m pytest -q tests/test_plan_reference_chain_live.py tests/test_plan_v2_api_live.py tests/test_plan_v2_p2_1_execution_harness.py tests/test_plan_v2_confirmatory_v3_runner.py tests/test_plan_v2_confirmatory_v3_freeze.py tests/test_plan_v2_semantic_contract.py tests/test_plan_v2_v3_postmortem_replay.py
python -m pytest -q
flutter test --no-pub
```

The one final full backend run was clean: `919 passed, 6 skipped` in 151.64s.
The three cached node identifiers formerly reported for canonical-food/E4 tests
were no longer collectable; their current equivalents pass. The historical
freeze test was updated to assert the correct distinction: its immutable
historical FAIL must not be treated as the current acceptance preflight. The
focused Plan suite passed `52 passed, 3 skipped`; Flutter passed all 132 tests.

`git diff --check` reports pre-existing trailing whitespace in
`apps/mobile/lib/widgets/bento_card.dart` and `docs/troubleshooting.md`.
No commit or push was performed for this task. The two preceding scoped commits
remain `b831071` and `054491d`.

## Remaining Known Limitations

Plan semantic product quality is not marked ready because the required final
live authenticated Edge gate did not pass. Its sole remaining blocker is the
known browser-harness Nutrition-tab text encoding/selector defect; no product
failure was established. N3 candidate-pool/portion-fitter integration remains
separately scoped. Neither fact changes historical acceptance evidence or
authorizes V4.

REFERENCE_CHAIN_STILL_100 = YES

HARD_SAFETY_INVARIANTS_PRESERVED = YES

P2_1_HISTORICAL_SCORED_SEMANTIC_MATCH = 47.5%

V3_DEVELOPMENT_REPLAY_SEMANTIC_MATCH = 100.0%

PLAN_SEMANTIC_PRODUCT_QUALITY_READY = NO

PLAN_V2_ACCEPTANCE_STATUS = FAILED_HISTORICAL

PLAN_V2_PRODUCTION_ENFORCEMENT = OFF
