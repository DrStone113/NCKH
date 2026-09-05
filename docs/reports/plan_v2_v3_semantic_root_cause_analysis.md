# Plan V2 V3 Semantic Root-Cause Analysis

## 1. Executive summary

The immutable Confirmatory V3 outcome remains **FAIL**: 120 frozen cases, 60 semantic matches (50.0%), 100.0% reference-chain identity, and zero hard violations. This analysis did not execute a V3 case, alter V3 output, change thresholds, or modify the frozen V3 runner/scorer.

The 60 failures reconcile exactly with the official result. They are two systemic future-harness defects, not planner or product defects:

| Primary root cause | Cases | Share of failures | Primary owner |
| --- | ---: | ---: | --- |
| `SCORER_FALSE_NEGATIVE` | 40 | 66.67% | `SCORER_BUG` |
| `HARNESS_EXPECTATION_ERROR` | 20 | 33.33% | `HARNESS_BUG` |

The new postmortem-only evaluator replays the persisted raw results at 120/120 (100.0%). This is diagnostic evidence only; it is not a corrected V3 score.

## 2. Immutable V3 result

- Official result: `V3_RESULT = FAIL`; `P2_PLAN_ACCEPTANCE_COMPLETE = NO`.
- Official metrics: 120 cases, `REQUEST_SEMANTIC_MATCH = 50.0%`, `REFERENCE_CHAIN_IDENTITY = 100.0%`, hard violations = 0.
- The frozen holdout, oracle, and thresholds remain respectively `8256ca62b344957c6e36b2580551777092cced2b85c84a381091b715511b519b`, `bb92a47b3edc8ec8a5ce13a1fb6e30a25738651bbf1c30ff413a98f3e3eb8af5`, and `adeb1a8139c15eb619f3bc92ad89e68197aa056b61f567d3fb58379b040a5400`.
- The execution register remains complete with no infrastructure retries. The V3 harness freeze is read-only for this work.

## 3. Failure inventory and manual semantic review

`plan-v2-v3-semantic-failure-inventory-v1.json` contains all 60 reviewed records. It preserves compact frozen input, scorer decision, actual semantic summary, field-level diff, suite reference information, errors, provenance, ownership, and post-fix diagnostic for every failure without repeating full raw payloads.

| Family and failed IDs | Count | Frozen scorer requirement | Actual result | Review conclusion |
| --- | ---: | --- | --- | --- |
| `single_workout-001`–`020` | 20 | `READY`, correct period/timezone, exactly one item | `CLARIFICATION_REQUIRED` | Fixture has no authoritative `workout_profile` or safety profile; safe clarification is correct. |
| `weekly_workout-001`–`020` | 20 | `READY`, correct period/timezone, requested item count | `CLARIFICATION_REQUIRED` | Same missing authority; safe clarification is correct. |
| `combined_health-001`–`020` | 20 | `READY` combined container with two bound child revisions | `CLARIFICATION_REQUIRED` | Fixture contains only symbolic child labels; a container cannot be safely bound. |

For all 60 records, V3 did not encode a frozen expected operation, target, field, value, output, or per-case reference role in its oracle. The effective expectation came instead from the frozen V3 scorer. Every reviewed actual output had no executor errors; suite reference identity stayed 100.0%.

## 4. Root-cause taxonomy, ownership, and Pareto

All 60 cases are `MULTI_FACTOR`: the primary ownership split is 40 `SCORER_BUG` and 20 `HARNESS_BUG`; all have a documented secondary `TEST_CASE_BUG`/`CONTRACT_AMBIGUITY` factor.

1. `SCORER_FALSE_NEGATIVE` affects the 40 workout cases. The frozen scorer unconditionally rejected a non-`READY` result, even though the execution fixture omitted the authority needed to generate a safe workout. Related categories are `HARNESS_EXPECTATION_ERROR` and `DATA_FIXTURE_OR_CASE_DESIGN_ERROR`.
2. `HARNESS_EXPECTATION_ERROR` affects the 20 combined cases. The frozen scorer required real combined child bindings when the fixture supplied only `fixture-nutrition` and `fixture-workout` strings. Related categories are `DATA_FIXTURE_OR_CASE_DESIGN_ERROR` and `SCORER_FALSE_NEGATIVE`.

The first cause covers 66.67%; the first two cover 100.0%. No operation, target-entity, field, value, temporal, ordering, enum/alias, planner-reasoning, or product defect was evidenced. No category is silently treated as equivalent.

## 5. Semantic-contract findings

[Plan V2 Semantic Contract V1](../features/plan_v2_semantic_contract.md) now makes the future scoring rules explicit: exact operations, owner-scoped identity and reference roles, required/optional values, missing/null behavior, literal date/time/timezone comparison, ordering versus explicitly set-like fields, extra semantic policy, and safety-first clarification behavior.

The contract introduces no broad alias, number, date, identifier, or collection normalization. In particular, it keeps `create != update`, lifecycle targets distinct, concrete references exact, and missing authoritative safety context material. It only canonicalizes status-token formatting for comparison and reports structured operation/target/field/value/missing/extra diagnostics.

## 6. Implemented future-harness fixes

| Fix | Scope and generalized behavior | Cases | Regression and negative control |
| --- | --- | ---: | --- |
| `SEM-CONTRACT-001` | Require a safe clarification/specialist response when a workout fixture lacks an authoritative workout profile with exercise-safety context. A ready workout in that state fails. Once authority is supplied, schedule shape and request period/timezone remain exact. | 40 | Missing-authority pass; ready-without-authority reject; wrong authorized session count reject. |
| `SEM-CONTRACT-002` | Require two concrete `(plan_id, revision_id, revision_content_hash)` child bindings before expecting a ready combined container. Symbolic labels require clarification; a ready result with those labels fails. | 20 | Symbolic-reference clarification pass; ready-with-symbolic-reference reject; concrete bound-container pass. |
| `SEM-DIAG-003` | Replace boolean-only future diagnostics with structured semantic mismatch dimensions. This changes no hard invariant. | 60 | Lifecycle target mismatch rejects and reports field mismatch. |

Implementation is limited to `services/acceptance/postmortem/plan_v2_semantics.py`, its read-only evidence builder, and tests. No product or Flutter source was changed. The contract source contains no frozen V3 case IDs, fixture names, or exact frozen prompt strings.

## 7. Regression strategy and results

The postmortem evaluator consumes saved V3 input and saved raw output; it does not call an executor, database, oracle writer, or V3 scorer. It verifies frozen input hashes, V3 result reconciliation, oracle field shape, and the 95% threshold before creating only new analysis artifacts.

Focused semantic/reference/safety/API/harness command (the test-only local database URI was constructed from the running `health_postgres` container and is not printed because it contains credentials):

```powershell
$env:PYTHONPATH='.'
& 'C:\Project\NCKH\.venv-e4-py310\Scripts\python.exe' -m pytest -q tests/test_plan_v2_semantic_contract.py tests/test_plan_v2_v3_postmortem_replay.py tests/test_plan_reference_chain_live.py tests/test_plan_lifecycle_p2_2.py tests/test_plan_v2_api_live.py tests/test_plan_v2_confirmatory_v3_runner.py tests/test_plan_v2_confirmatory_v3_freeze.py tests/test_plan_v2_p2_1_execution_harness.py
```

Result: **23 passed**, with two pre-existing JWT key-length warnings. This verifies targeted semantic behavior and negative controls, exact reference-chain preview/persist/read-back identity, owner-scoped API behavior, lifecycle resume behavior, P2.1 execution safeguards, and the frozen V3 harness tests.

Broader P2 selection command:

```powershell
$env:PYTHONPATH='.'
& 'C:\Project\NCKH\.venv-e4-py310\Scripts\python.exe' -m pytest -q tests/test_plan_engine_p2.py tests/test_plan_lifecycle_p2_2.py tests/test_plan_reference_chain_live.py tests/test_plan_sql_repository_live.py tests/test_plan_v2_api_live.py tests/test_plan_v2_confirmatory_v3_freeze.py tests/test_plan_v2_confirmatory_v3_runner.py tests/test_plan_v2_human_review_pack.py tests/test_plan_v2_p2_1a_automated_freeze.py tests/test_plan_v2_p2_1_execution_harness.py tests/test_plan_v2_qualification_protocol.py tests/test_plan_v2_scoped_qualification.py tests/test_plan_v2_semantic_contract.py tests/test_plan_v2_v3_postmortem_replay.py
```

It produced **51 passed, 1 failed**, plus the same two warnings. The sole failure is `test_plan_v2_p2_1a_automated_freeze_is_output_independent_and_fail_closed`: it expects a temporary reconstruction of the historical P2.1a freeze to report `IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE = true`. The current remediation source intentionally differs from that P2.1a baseline, so its freeze code correctly reports false. This historical-baseline assertion was not changed, and it is not a V3 semantic or product failure.

## 8. Postmortem replay

`plan-v2-v3-semantic-postmortem-replay-v1.json` is explicitly `POSTMORTEM_REPLAY_ONLY` with `execution_performed = false` and `official_v3_result_retained = FAIL`.

- Historical records inspected: 120.
- Postmortem replay semantic match: 120/120 (100.0%).
- Historical failures changed diagnostically: 60.
- Remaining replay failures: 0.

The replay shows that the acceptance target is realistically attainable under the explicit future contract. It does not amend V3, lower the 95% threshold, qualify a future holdout, or create V4.

## 9. Remaining cases, threats to validity, and V4 readiness

There are no unresolved V3 semantic cases after classification. The key validity threat is that V3’s generic input-only oracle did not encode output semantics for the 60 affected cases; the next independent harness must freeze complete authoritative workout/safety context and concrete combined child bindings before execution. A future V4 must use independently selected cases, not V3 cases with retrofitted expected outputs. If protocol requires corpus continuity, the implementation and complete semantic contract must be frozen before V4 is frozen.

| Readiness check | Result |
| --- | --- |
| `ALL_V3_MISMATCHES_CLASSIFIED` | YES |
| `ALL_CONFIRMED_HARNESS_BUGS_RESOLVED` | YES |
| `ALL_CONFIRMED_SCORER_BUGS_RESOLVED` | YES |
| `ALL_CONFIRMED_PRODUCT_BUGS_RESOLVED` | YES (none confirmed) |
| `ALL_CONFIRMED_PLANNER_BUGS_RESOLVED` | YES (none confirmed) |
| `CONTRACT_AMBIGUITIES_RESOLVED_OR_DOCUMENTED` | YES |
| `TARGETED_SEMANTIC_REGRESSION_PASS` | YES |
| `NEGATIVE_CONTROLS_PASS` | YES |
| `REFERENCE_CHAIN_REGRESSION_PASS` | YES |
| `HARD_VIOLATIONS_ZERO` | YES |
| `POSTMORTEM_REPLAY_MATCH` | 100.0% |
| `UNRESOLVED_CASE_COUNT` | 0 |
| `V4_READY` | YES |

V4 may be prepared only in a separate approved task. No V4 was created, frozen, or executed here.
