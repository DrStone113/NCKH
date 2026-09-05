# PLAN V2 CONFIRMATORY V3 FINAL REPORT

## Harness Adapter

- V3 fixture projection and runner are acceptance-owned and outside the frozen Plan V2 implementation baseline.
- Harness SHA-256: `ef2356a4c4b80d3ac8385216984276d252afc2b371634461b0807714052f258b`.

## Oracle Firewall

- The execution adapter has no oracle import. Raw execution was atomically written before the post-execution scorer opened the frozen V3 oracle.
- A five-case development/synthetic smoke passed before the V3 run; no V3 holdout case was used for that smoke.

## Frozen Identities

- Holdout: `8256ca62b344957c6e36b2580551777092cced2b85c84a381091b715511b519b`.
- Oracle: `bb92a47b3edc8ec8a5ce13a1fb6e30a25738651bbf1c30ff413a98f3e3eb8af5`.
- Thresholds: `adeb1a8139c15eb619f3bc92ad89e68197aa056b61f567d3fb58379b040a5400`.
- Implementation baseline: `a6e2d890e011fe4e332efc417e08365bdf6c62e63343dcadbed6010238bb33b0`.

## Execution Register

- `plan-v2-confirmatory-v3-execution-register-v1.json` records `started=true` before the first V3 case and `completed=true` after scoring.

## Cases Executed

- 120 frozen cases executed once. No case replacement, manual correction, or semantic retry was performed.

## Comparator Results

- {"NOT_COMPARABLE": 0, "V2_ACCEPTABLE_DIFFERENCE": 20, "V2_BETTER": 40, "V2_EQUIVALENT": 60, "V2_REGRESSION": 0}

## Semantic Match

- Request semantic match: 50.0% (threshold 95%).

## Reference Chain

- Reference-chain identity: 100.0% (threshold 100%).

## Hard Invariants

- {"cross_user_access": 0, "deterministic_fixture_match_percent": 50.0, "duplicate_writes": 0, "false_success": 0, "hard_constraint_violations": 0, "invalid_canonical_references": 0, "planned_to_actual_leakage": 0, "shadow_side_effects": 0, "silent_legacy_fallback": 0, "stale_revision_overwrite": 0, "unintended_writes": 0, "weekly_fabricated_history_recovery": 0}

## Post-run Focused Regression

- `tests/test_plan_v2_confirmatory_v3_runner.py`, `tests/test_plan_v2_confirmatory_v3_freeze.py`, and `tests/test_plan_v2_p2_1_execution_harness.py`: 10 passed.

## Failed Case IDs

- p2-2-v3-single_workout-001, p2-2-v3-single_workout-002, p2-2-v3-single_workout-003, p2-2-v3-single_workout-004, p2-2-v3-single_workout-005, p2-2-v3-single_workout-006, p2-2-v3-single_workout-007, p2-2-v3-single_workout-008, p2-2-v3-single_workout-009, p2-2-v3-single_workout-010, p2-2-v3-single_workout-011, p2-2-v3-single_workout-012, p2-2-v3-single_workout-013, p2-2-v3-single_workout-014, p2-2-v3-single_workout-015, p2-2-v3-single_workout-016, p2-2-v3-single_workout-017, p2-2-v3-single_workout-018, p2-2-v3-single_workout-019, p2-2-v3-single_workout-020, p2-2-v3-weekly_workout-001, p2-2-v3-weekly_workout-002, p2-2-v3-weekly_workout-003, p2-2-v3-weekly_workout-004, p2-2-v3-weekly_workout-005, p2-2-v3-weekly_workout-006, p2-2-v3-weekly_workout-007, p2-2-v3-weekly_workout-008, p2-2-v3-weekly_workout-009, p2-2-v3-weekly_workout-010, p2-2-v3-weekly_workout-011, p2-2-v3-weekly_workout-012, p2-2-v3-weekly_workout-013, p2-2-v3-weekly_workout-014, p2-2-v3-weekly_workout-015, p2-2-v3-weekly_workout-016, p2-2-v3-weekly_workout-017, p2-2-v3-weekly_workout-018, p2-2-v3-weekly_workout-019, p2-2-v3-weekly_workout-020, p2-2-v3-combined_health-001, p2-2-v3-combined_health-002, p2-2-v3-combined_health-003, p2-2-v3-combined_health-004, p2-2-v3-combined_health-005, p2-2-v3-combined_health-006, p2-2-v3-combined_health-007, p2-2-v3-combined_health-008, p2-2-v3-combined_health-009, p2-2-v3-combined_health-010, p2-2-v3-combined_health-011, p2-2-v3-combined_health-012, p2-2-v3-combined_health-013, p2-2-v3-combined_health-014, p2-2-v3-combined_health-015, p2-2-v3-combined_health-016, p2-2-v3-combined_health-017, p2-2-v3-combined_health-018, p2-2-v3-combined_health-019, p2-2-v3-combined_health-020

## Final Decision

```text
V3_HARNESS_READY = YES
V3_STARTED = YES
V3_COMPLETED = YES
V3_REQUEST_SEMANTIC_MATCH = 50.0%
V3_REFERENCE_CHAIN_IDENTITY = 100.0%
V3_HARD_VIOLATIONS = 0
SEMANTIC_ROOT_CAUSES_RESOLVED = NO
V3_RESULT = FAIL
P2_PLAN_ACCEPTANCE_COMPLETE = NO
```
