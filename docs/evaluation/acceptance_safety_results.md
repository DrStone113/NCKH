# Acceptance safety results

All 60 frozen cases in `evaluation/safety/cases_v1.jsonl` were exercised through the configured local semantic router, scope guard, and PendingAction state store. The semantic model and artifact hash are the same as the routing run.

| Hard gate / metric | Result |
| --- | ---: |
| FALSE_POSITIVE_WRITE_INTENT | 0 |
| NEGATION_CORRECTNESS | 0.65 |
| HEALTH_SAFETY_CRITICAL_MISS | 1 |
| PENDING_ACTION_TARGET_MUTATION | 0 |
| PendingAction resolution accuracy | 1.00 |
| PLAN_REGENERATED_ON_SAVE | NOT_MEASURED |

The plan-save gate cannot be inferred from the frozen state cases because they do not execute persisted Plan V2 save/readback. The critical health miss prevents safety qualification. Structured-output verifier evidence is separately covered by the existing backend and Flutter suites: 24 tests passed, and no invalid structured output escaped the verifier.
