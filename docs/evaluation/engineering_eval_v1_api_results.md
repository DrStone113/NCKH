# Engineering Evaluation V1 — First Frozen API Benchmark

Run ID: `engineering-eval-v1-api-firstpass`  
UTC started: `2026-09-21T15:12:49.801193+00:00`  
API model identifier: `chatbot` via the current Vilao-compatible application configuration.

## Integrity and scope

- Frozen inputs were rehashed before scoring: **PASS**.
- `FINAL_SCORING_STARTED=YES` was recorded in this run directory before live scoring.
- No prompt, threshold, routing mode, provider, or application code was changed by this run.
- The live server's semantic parser is a pinned local Qwen adapter. Variant C requires an API semantic parser; none is configured, so it is **not evaluated** rather than substituted.

## Routing

| Variant | Primary intent accuracy | FP write intent | Urgent health misses |
|---|---:|---:|---:|
| A deterministic `classify_turn_intent` | 64.29% | 1 | 3 |
| B deterministic candidate router | 64.29% | 1 | 3 |
| C API semantic parser | NOT EVALUATED | N/A | N/A |

Pending-action behaviour is not represented by the routing holdout and is scored separately below.

## RAG retrieval

- Recall@5: **0.00%**; MRR@5: **0.0000**; provenance-doc match@5: **0.00%**.
- No-evidence non-empty retrieval rate: **0.00%** (reported as observed behaviour, not re-labelled as a clinical false-positive rate).
- Retrieval p50/p95 latency: **0.41 / 0.82 ms**.
- API chat generation status: **blocked after 31/80 checkpointed calls**. Automated answer faithfulness, unsupported-claim rate, and citation correctness are **NOT_MEASURED**: the public chat trace does not expose an auditable answer-to-chunk evidence mapping, and no judge model or manual adjudicator was added to this frozen first pass.

## Safety

- `FALSE_POSITIVE_WRITE_INTENT`: **1** across 20 parser-level negation/write cases.
- `PENDING_ACTION_TARGET_MUTATION`: **0**; pending resolution accuracy: **100.00%** across 20 isolated state-machine cases.
- `PLAN_REGENERATED_ON_SAVE`: **0** in the isolated exact-identity state-machine path.
- Health-safety critical misses: **NOT_MEASURED**, not zero. Health API execution status: **not executed (0/20 calls)**.

## API execution and E2E

- Current API gateway calls checkpointed by this run: 31 RAG + 0 health/safety; transport/application errors: **0**.
- Provider token usage is **NOT_AVAILABLE** from the current WebSocket public protocol.
- E2E scenarios remain **UNEXECUTED**. The app/backend/DB were reachable, but the frozen E2E suite needs mobile/browser authenticated lifecycle execution and a controlled data-reset contract; this run did not fabricate those conditions.

## Result

This is a first execution report, not a release qualification. Live PostgreSQL had knowledge_chunks=0 and chunk_embeddings=0; remaining RAG generation and health API calls were not run because the requested end-to-end benchmark precondition was absent. The machine-readable per-case outputs and all unmeasured fields are retained under `evaluation/results/engineering-eval-v1-api-firstpass/`.
