# P2.1A AUTOMATED FREEZE REPORT

## Review Mode

The review mode is `AUTOMATED`. The protocol only evaluates candidate prompt,
fixture, deterministic oracle, and isolated semantic-rubric suitability. It
does not invoke a Plan V2 tool, comparator, scheduler, persistence adapter,
legacy evaluator, or a scored acceptance runner.

Every record uses an automated `review_source`; no reviewer identity field is
present. The review-visible artefacts exclude runtime model outputs, legacy
system outputs, comparator outcomes, runtime score predictions, and prior
judge verdicts.

## Deterministic Oracle Coverage

The frozen deterministic oracle covers all 120 selected cases. 103 cases have
only machine-checkable gates; 17 `READY_OR_CLARIFY` cases also receive semantic
review. The oracle maps the objective checks below to applicable cases:

| Objective check | Cases |
| --- | ---: |
| Allergy/restriction | 10 |
| Canonical ID/reference | 11 |
| Date and timezone | 25 / 22 |
| Duration and session count | 25 / 17 |
| Equipment | 13 |
| No-write | 115 |
| Planned != actual | 81 |
| Ownership | 9 |
| Revision | 20 |
| Idempotency | 5 |
| Safety | 18 |
| E4 delegation | 2 |

Additional machine gates cover missing/unknown state (13), availability (4),
clarification boundary (37), and heuristic labelling (2).

## Semantic Judge Coverage

17 prompt/oracle pairs require semantic suitability review. Each received
three isolated automated passes, for 51 verdicts total. Each pass was given
only the case's prompt, fixture, deterministic oracle, and its own rubric.
No previous pass verdict was supplied.

## Judge Architecture

The three rubrics assess, independently:

- Intent and context boundedness.
- Safe alternative suitability.
- Output-independent holdout suitability.

All rubric input is output-independent. The register asserts
`prior_judge_verdicts_visible = false` for every semantic pass.

## Judge Model Independence

`SAME_MODEL_MULTI_PASS = true`.

All three passes used `gpt-5.6 (same current-session model)`. They are
isolated with respect to inputs and verdict visibility, but are not
statistically independent.

## Automated Agreement

- Semantic verdicts: 51
- Unanimous ACCEPT cases: 17
- Percent agreement: 100.0%
- Cohen's kappa: not defined because only one verdict class was observed

## Disagreements

None. `disagreement_case_ids` is empty.

## Automated Adjudication

103 deterministic-only cases were accepted through deterministic gates. The
17 semantic cases were accepted only after unanimous three-pass consensus.
The protocol is fail-closed: an unrecorded semantic case or a disagreement
cannot inherit an ACCEPT disposition.

## Final Holdout

The holdout is frozen with 120 unique ACCEPT cases:

- Nutrition: 30
- Single-session workout: 30
- Weekly workout scheduling: 30
- Combined health: 15
- Revision/lifecycle/concurrency adversarial: 15

There are zero exact duplicates and zero template duplicates, so no case has
duplicate weighting.

## Leakage Audit

- Confirmed development overlap: 0
- Template development overlap: 0
- Semantic leakage candidates: 0

The exclusion index is checked deterministically before the automated register
is admitted.

## Dataset Hash

`92936175ad58a3ef99cbce617f3522d2e677dd46af1df368e992238c9dd75a1a`

Artifact: `p2-1a-automated-holdout-v1.json`.

## Oracle Hash

`49e1302bf6c9d5f78e1a04ca551bd66589f066035a4e655ed4514eaa237c16b8`

Artifact: `p2-1a-deterministic-oracle-v1.json`.

## Review Register Hash

`185d20362032c2746d572e940d506c9d9569beee7b6dffee0f8223b78e8ec1fc`

Artifact: `p2-1a-automated-review-register-v1.json`.

## Threshold Hash

`e6002d52ddd849f4f434c8a56ba1af2e6659ca6b8abddf0f8b5dd1adcff15df0`

Artifact: `acceptance-thresholds-v1.json`.

## Implementation Hash Verification

All nine sources in `implementation-freeze-p2-1r-v1.json` match their
recorded SHA-256 values. No P2.1R frozen implementation source was modified.
The implementation-freeze manifest hash is:

`58abdea52c9466e25dd9b71e8e50dc7e588ea52d46b74937b6a50c6f5ff993f8`

## Toolchain

- Flutter 3.44.8
- Dart 3.12.2
- CPython 3.10.21

## Backend Runtime Verification

The P2.1A generator ran successfully with CPython 3.10.21 and the P2.1A
validator test passed (`1 passed`). The generator verified the source hashes,
candidate uniqueness, overlap gates, artefact hashes, toolchain, and review
coverage without executing scored acceptance.

An older qualification test in the existing worktree has a stale expectation
about an earlier artefact state and is outside P2.1A; it was not changed. This
does not participate in the P2.1A preflight.

## Final Preflight

All required P2.1A preflight gates are true:

- Review mode is automated.
- Holdout, deterministic oracle, thresholds, and implementation hash set are frozen.
- Review coverage is 100%.
- Development overlap, template overlap, semantic leakage candidates, and duplicate weighting are zero.
- Flutter, Dart, and CPython match the required versions.
- No scored Plan V2 acceptance was executed.

`REVIEW_MODE = AUTOMATED`

`HOLDOUT_V2_FROZEN = YES`

`ORACLE_FROZEN = YES`

`IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE = YES`

`READY_TO_RUN_P2_1_ACCEPTANCE = YES`

The scored acceptance run is intentionally not started by this task.
