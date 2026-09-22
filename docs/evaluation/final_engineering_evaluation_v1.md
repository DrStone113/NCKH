# Final engineering evaluation V1 status

## Corrected retrieval result

The frozen V1 research corpus was present and verified: scientific identity match, 636 chunks, 636 embeddings, zero dynamic rows, expected BGE-M3 model/revision/dimension, and L2-normalized build contract. The corrected retrieval-only run is `evaluation/results/v1-frozen-provider-retrieval-20260921-r3/`.

| Metric | Result |
|---|---:|
| Cases | 80 (60 evidence-present, 20 no-evidence) |
| Hit@1 / Hit@3 / Hit@5 | 1.0000 / 1.0000 / 1.0000 |
| MRR | 1.0000 |
| No-evidence correctness | 1.0000 |
| False-evidence retrieval rate | 0.0000 |
| p50 / p95 retrieval latency | 128.736 / 149.334 ms |

This confirms the frozen corpus/provider path and frozen oracle trace. The V1 oracle was automatically derived from the same frozen corpus and retrieval convention, so this is not an independent clinical or real-world effectiveness estimate.

## Historical invalid result retained

`engineering-eval-v1-api-firstpass` is preserved. Its 0% retrieval is `INVALID_DUE_TO_WRONG_OR_EMPTY_RUNTIME_RAG_STORE`: it queried empty production tables through `RAGService` instead of V1 research tables through `PostgresFrozenRagProvider`.

Routing V1 remains unchanged: A = 64.29%, B = 64.29%, false-positive write intent = 1, urgent-health routing misses = 3, pending-action target mutation = 0. V1 answer generation (31/80 checkpointed), health safety, and authenticated E2E are not complete and are not promoted by corrected retrieval.
