# Acceptance RAG component diagnostic

This is a frozen retrieval-component diagnostic, not chatbot end-to-end accuracy. Source: `evaluation/results/acceptance_vn/metrics.json`, corpus `offline-acceptance-vn-4954`, corpus hash `f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a`, top-k 10, threshold 0.6.

| Metric | Value |
| --- | ---: |
| Hit@1 | 0.3943 |
| Hit@3 | 0.4286 |
| Hit@5 / Recall@5 | 0.4286 |
| Hit@10 | 0.4286 |
| MRR | 0.4105 |
| Sequential latency p50 / p95 | 63.167 / 82.997 ms |

The architecture-required RAG subset contains 55 cases; the preserved component result is 31/55 Hit@5 = 0.5636. Do not interpret the old `VN_FOOD` Hit@5 = 0.0 (60 cases) as chatbot failure: its expected channel is `FOOD_TOOL`, where RAG is forbidden. Other component domains remain: VN_DISH 0.85, VN_NORMATIVE 0.30, VN_MICRONUTRIENT 1.00, VN_PHYSICAL_ACTIVITY 0.50, VN_BODY_METRIC 0.00, GLOBAL_HEALTH 0.9333, FOREIGN_FOOD 0.2667, and NO_EVIDENCE correctness 1.00.

During adapter smoke verification, an existing VN normative query produced no result at the frozen 0.6 threshold under the current embedding runtime, despite the preserved score containing a hit. No corpus, embeddings, index, or threshold was changed. This is a reproducibility/failure-analysis finding, not a replacement score.
