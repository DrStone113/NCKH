# Engineering Evaluation Protocol V1

Frozen at: `2026-09-21T13:42:14+00:00`

## Scope and non-goals

This phase creates evaluation data and automated oracles only. It does not run A/B/C routing, retrieval, answer grading, safety execution, or authenticated E2E. It does not tune production behavior and does not change the frozen research corpus.

`FINAL_SCORING_STARTED=NO`

## Actual product contracts

- Routing targets the ten values in `TurnIntent` (`MEAL_SUGGESTION, MENU_SCHEDULE, WORKOUT_SCHEDULE, COMBINED_PLAN, PLAN_EDIT, PLAN_LIFECYCLE, OBSERVATION_LOG, HEALTH_QUERY, PROFILE_UPDATE, GENERAL_WELLNESS`) and the decision fields carried by `SemanticParseResult`.
- `PendingUserAction` is a separate deterministic state machine, not an invented routing intent. Its confirmation, owner, expiry, idempotency, and immutable target behavior are evaluated in the safety set.
- Planned meals/workouts remain separate from actual observations. Saving a Plan must preserve `plan_id + revision_id + revision_content_hash` and must not create actual logs.

## Public seed sources

- [MASSIVE_vi-VN](https://github.com/alexa/massive): Vietnamese NLU phrasing and action/query structures only; terms recorded as `CC-BY-4.0 dataset`; copied records: 0.
- [PhoATIS_Disfluency](https://github.com/VinAIResearch/PhoATIS_Disfluency): disfluency categories only; no dataset record downloaded or copied; terms recorded as `research/education only; no redistribution of original or modified records`; copied records: 0.
- [Vietnamese_Medical_QA](https://huggingface.co/datasets/hungnm/vietnamese-medical-qa): health-question structure only; no answer treated as gold; terms recorded as `Apache-2.0 per dataset card`; copied records: 0.
- [MedSafetyBench](https://github.com/AI4LIFE-GROUP/med-safety-bench): medical-risk category design only; terms recorded as `MIT repository; research-use warning for benchmark content`; copied records: 0.
- [HealthBench](https://openai.com/index/healthbench/): rubric structure only; no examples copied; terms recorded as `methodology reference; source asks not to publish examples`; copied records: 0.
- [MIRAGE_Medical_RAG](https://github.com/gzxiong/MIRAGE): retrieval/generation metric design only; terms recorded as `methodology reference; component datasets retain their own terms`; copied records: 0.

Public records and public labels were not imported. Sources informed linguistic variation, risk categories, and evaluation structure only. The final oracle uses this project's taxonomy, policies, and frozen corpus.

## Contamination control

- Scanned files: 318
- Indexed utterance-like entries: 9105
- Candidate pool written: 251
- Final routing holdout: 140
- Final exact/normalized overlap: 0 by construction
- Final near-duplicate overlap: 0 by rejection before selection
- Semantic check executed: `True` with `BAAI/bge-m3 (local cached)` over 2500 prioritized entries; threshold `0.985`.

The normalized form is NFKD/case-folded, maps `đ` to `d`, removes combining marks, and collapses non-alphanumeric separators. Template similarity uses token prefiltering plus sequence similarity. Semantic similarity, when executed, uses only the cached local encoder and never invokes the routing model.

## Routing freeze

The candidate pool is generated before product execution. Every final case has an automated spec-derived oracle. No claim of human labeling, human review, human adjudication, or inter-rater agreement is made. Final scoring must use the frozen files byte-for-byte. Seeing holdout output forbids tuning against V1; an implementation change requires an invalidated run and a newly versioned evaluation.

Prepared metrics: primary-intent accuracy, secondary-intent micro/macro F1, false ambiguity rate, false-positive write intent, negation recall, and health-safety critical miss count.

## RAG freeze

The RAG set has 60 evidence-present and 20 no-evidence cases. Gold IDs come from `offline-v1-636` source coordinates and its deterministic UUID5 chunk convention. No gold evidence comes from a model answer. No-evidence terms are checked as absent from all four frozen source files before freeze.

Prepared metrics: Hit@1, Hit@3, Hit@5, MRR, no-evidence correctness, evidence use, faithfulness, and unsupported-claim rate. Answer-level fields are rubric inputs only; no answer grading has started.

## Safety/write freeze

The 60 cases are balanced across negation/write, health/scope/safety, and PendingAction/Plan identity. The mandatory zero-tolerance invariants are:

- `FALSE_POSITIVE_WRITE_INTENT = 0`
- `PENDING_ACTION_TARGET_MUTATION = 0`
- `PLAN_REGENERATED_ON_SAVE = 0`
- `HEALTH_SAFETY_CRITICAL_MISS = 0`

Short confirmation primitives such as `ok`, `đồng ý`, and `không lưu` are deliberately retained in the stateful suite because the production confirmation grammar is a finite allowlist. They are not part of the fresh routing holdout.

## E2E qualification

There are 12 defined scenarios. Their status is `DEFINED_NOT_EXECUTED`. Qualification requires Flutter Web, real Firebase authentication, real backend routes, PostgreSQL readback, and no mocks. Scenario definitions are not evidence that E2E passed.

## Freeze rules

1. Verify hashes in each manifest before any scorer starts.
2. Record implementation version and run ID separately from these datasets.
3. Do not edit V1 after observing outputs.
4. If any evaluation artifact changes, create a new version and mark prior runs invalid for comparison.
5. Never describe automated oracles as human-reviewed.

## Status

```text
ROUTING_HOLDOUT_FROZEN=YES
ROUTING_ORACLE_PROVENANCE=AUTOMATED
RAG_EVAL_FROZEN=YES
SAFETY_EVAL_FROZEN=YES
E2E_SCENARIOS=12
FINAL_SCORING_STARTED=NO
```
