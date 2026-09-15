# Backend Optimization V2

The implementation is rollout-gated. `BACKEND_COST_MODE=observe` is the
default: hard scope/safety rules, DB/network improvements and aggregate
instrumentation run normally, while inference prefetch, validators and
lexical early-exit are recorded without changing the answer path. Set
`BACKEND_COST_MODE=enforce` only after the checked-in policy artifact has been
qualified and approved.

## Implemented path

- Versioned `InferenceDecisionV2` plus a constrained LinUCB recommender that
  is recommendation-only and has no online update path.
- One active WebSocket turn per connection, FIFO size four in enforce mode,
  structured `CHAT_QUEUE_FULL`/`SERVER_BUSY`, weighted admission and a safety
  reserved slot. AIMD stays between 2 and 16 and observes queue, timeout and DB
  pool pressure.
- Qualified read-only prefetch, parallel independent reads and deterministic
  typed-response exits. Writes remain ordered and require persistence
  confirmation.
- Deterministic answer validators for numeric grounding, evidence, freshness,
  dietary/allergy flags, plan conflicts and persistence claims.
- One-statement chat context read, one-statement owner/session claim, one audit
  insert for reads, durable claim/finalize for writes, and online indexes in
  migration `019`.
- Exact/lexical-first RAG, trusted-shadow thresholds, weighted RRF,
  near-duplicate suppression, 8-query/10-ms dense batching, BGE lazy loading,
  two CPU threads and one concurrent inference batch.
- HMAC owner/session typed snapshot cache with mandatory revision/freshness,
  post-write invalidation, plus bounded 24-hour public single-flight cache and
  stale-if-error.
- A lifespan-owned keep-alive HTTP pool with per-origin circuit breaker;
  pre-serialized catalog ETags, 304 and GZip; deterministic proactive messages
  by default with opt-in 96-token personalization once per time window.
- Developer/admin-only aggregate `/internal/backend-cost`; no prompt, chat,
  profile, owner ID or secret is accepted as a metric label.
- Python 3.10.21 multi-stage image. Production installs only
  `requirements-runtime.txt`; tests live in `requirements-dev.txt`.

## Qualification boundary

Passing component tests is not rollout acceptance. Before `enforce`, run a
human-labelled Vietnamese holdout and the same-machine load protocol from the
approved plan. Update the versioned artifact manually only if all hard gates
and quality/cost/latency targets pass. Synthetic fixtures must remain labelled
development evidence and policy promotion is never automatic.

Fit a candidate lexical policy from an offline labelled ranking export with:

```powershell
python scripts/fit_retrieval_policy_v2.py input.jsonl output-policy.json --dense-budget 0.40
```

The output remains `OFFLINE_EVALUATED_REQUIRES_HUMAN_APPROVAL` and is not read
by production automatically.
