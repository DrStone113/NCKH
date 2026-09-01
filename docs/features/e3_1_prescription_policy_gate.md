# EXERCISE E3.1 — Prescription Policy Semantic & Reproducibility Gate

## Outcome

E3.1 corrects material semantics in the original E3 policy without modifying
E2, `suggest_workout`, research A/B/C or `nutrition-policy-v1.0.1`. Because the
meaning changed, it creates `exercise-prescription-policy-v1.1.0` in a new
artifact instead of overwriting `v1.0.0`.

## Experience semantics

`NOVICE`, `EXPERIENCED` and `UNKNOWN` are preserved as user-experience values.
Missing local history never turns a user into a novice. `UNKNOWN` may select
`CONSERVATIVE_DEFAULT` operational bounds, while its output and provenance
remain `UNKNOWN_NOT_INFERRED`.

The resolver exposes separately:

- explicit experience and `USER_REPORTED`/`UNKNOWN_NOT_INFERRED` provenance;
- whether local history is available;
- the independent history signal;
- `CONFLICTING_SIGNALS` without silently reclassifying the user.

Progression remains unavailable without actual prior prescription/result data,
even when the user explicitly reports being experienced.

## Goal taxonomy

Resistance `MUSCULAR_ENDURANCE` and aerobic `AEROBIC_ENDURANCE` are different
domains. The generic goal `ENDURANCE` is prohibited. Ambiguous phrases such as
“sức bền”, “tăng endurance” and “endurance” return
`CLARIFICATION_REQUIRED` unless resistance or aerobic context is explicit.

## Weight-management semantics

The resistance profile does not claim that higher repetitions increase fat
loss or that shorter rest is better for weight loss. Its rep and rest defaults
match the general-fitness profile. Product-specific load, repetition, set,
volume, rest, RIR, duration, ordering and selection conventions are labelled
`PRODUCT_HEURISTIC`.

## Mobility provenance

Every mobility field has one of:

- `EVIDENCE_BASED_POLICY`
- `PRODUCT_HEURISTIC`
- `REQUIRES_DECISION`

No mobility field inherits the ACSM resistance-training citation implicitly.
Undefined load, repetitions, weekly muscle sets and RIR remain null and
`REQUIRES_DECISION`.

## Power eligibility

Power eligibility is explicit:

| Experience | Decision |
|---|---|
| `NOVICE` | `REQUIRES_COACHING_OR_SKILL_ASSESSMENT` |
| `EXPERIENCED` | `ELIGIBLE_AFTER_SAFETY_AND_TECHNIQUE_SCREEN` |
| `UNKNOWN` | `REQUIRES_EXPERIENCE_CONFIRMATION` |

Unknown experience therefore cannot receive high-technical-complexity
explosive work automatically.

## Catalog eligibility

E3.1 classifies the frozen 885-record E2 catalog without filling missing data:

| Status | Records |
|---|---:|
| `PRESCRIPTION_ELIGIBLE` | 430 |
| `SEARCH_ONLY` | 455 |
| `INSTRUCTION_INCOMPLETE` | 29 |
| `MUSCLE_UNKNOWN` | 194 |
| `MOVEMENT_UNKNOWN` | 320 |
| `SUBSTITUTION_UNAVAILABLE` | 438 |
| `REQUIRES_EXPERIENCE_CONFIRMATION` | 878 |

Statuses are composable. For example, a structurally eligible exercise can
still require experience confirmation. `PRESCRIPTION_ELIGIBLE` is structural
eligibility only; it does not override E2 review status, user safety,
experience or preference checks.

## Movement and muscle balance

Major-muscle exposure is a `SOFT_PLANNING_TARGET`. The exact squat/hinge/push/
pull/core taxonomy is a `PRODUCT_HEURISTIC`, not a universal medically perfect
balance. Safety and equipment constraints are `HARD_CONSTRAINT` and always
take precedence.

## Progression semantics

Double progression is frozen as rule
`E3_1_DOUBLE_PROGRESSION_LOAD` under policy v1.1.0. It exposes:

- `rule_id` and `policy_version`;
- `evidence_status=PRODUCT_HEURISTIC`;
- required observations;
- failure behavior;
- `uniquely_optimal_claim=false`.

With no prior prescription/result history it returns
`PROGRESSION_UNAVAILABLE`, `previous_load_kg=null` and no load change. It never
invents a previous load.

## MET mapping provenance

Activity-to-Compendium mapping is explicit:

- `DIRECT_SUPPORTED_MAPPING`: description directly matches a Compendium code;
- `APP_CURATED_MAPPING`: app maps confirmed Wger session context to a code;
- `UNMAPPED_ACTIVITY`: no approved mapping.

Wger provides exercise metadata, not MET. An unrecognized exercise/activity
returns `NO_CALORIE_ESTIMATE`; absence of a Compendium code never falls back to
an invented kcal value.

## Policy identity

- policy version: `exercise-prescription-policy-v1.1.0`
- semantic content SHA-256:
  `b25bee0f3cfda41f6a457cac18e0e1191f212ad6f048d8863ec03c7cb1cc8a01`
- manifest SHA-256:
  `7b9143056af26a2ae458677a223d99e28b77464a9772d544335ceba109f0c0ed`
- creation commit: recorded in the artifact
- source registry: five evidence sources plus frozen E2 manifest/content hash

The original `exercise_prescription_policy_v1.json` remains byte-for-byte
available and is referenced through `supersedes` metadata.

## Phase boundary

E3.1 does not implement E4 and does not connect policy v1.1.0 to
`suggest_workout`. The runtime chatbot remains on its previous path until the
personalized planner has its own implementation and gate.

## Regression status

- E3.1 semantic tests: 17 passed.
- E1–E3, nutrition and research direct gate: 134 passed.
- Full backend suite: 727 passed, 1 skipped.
- E1, E2, E3.1 and D4.1 frozen verifiers: passed.
- Food catalog validator, compileall and `git diff --check`: passed.
- E2 manifest, `nutrition-policy-v1.0.1`, research manifest, source artifacts
  and experiment-condition hashes A/B/C match their frozen identities.

The original workstation Python 3.10.0 patch exposed a
`dataclasses(slots=True, init=False)`/Hypothesis incompatibility during the
E3.1 run. E4 verification upgraded within the supported 3.10 line to CPython
3.10.21, where all 16 property tests pass with the normal pytest command. No
compatibility shim exists in the repository and no Python 3.11 migration is
required. Exact versions are recorded in the E4 runtime artifact and lock.

`E3_BASELINE_READY_FOR_E4 = YES`. E4.0 now consumes this baseline in a separate
deterministic shadow planner. E3.1 itself still does not change production
workout behavior or authorize E4.1 chatbot integration.

## Verification

```powershell
cd apps/backend
py -3.10 scripts/manage_exercise_prescription_policy.py --verify
py -3.10 -m pytest -q tests/test_exercise_prescription_policy_e3_1.py
```
