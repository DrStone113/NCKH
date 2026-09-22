# Acceptance routing results

`evaluation/routing/holdout_v1.jsonl` was executed as 140 frozen cases through the configured local `LocalQwenSemanticAdapter`, model `Qwen/Qwen3-0.6B@c1899de289a04d12100db370d81485cdf75e47ca`, artifact hash `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`, in shadow mode. Model inference ran for 51 cases.

| Metric | Result |
| --- | ---: |
| Primary-intent accuracy | 0.6000 |
| Secondary F1 | 0.0000 |
| Multi-intent exact match | 0.9000 |
| Negation correctness | 0.9000 |
| Write-intent accuracy | 0.9214 |
| FALSE_POSITIVE_WRITE_INTENT | 1 |
| Urgent-health recall | 0.6250 |
| HEALTH_SAFETY_CRITICAL_MISS | 3 |
| Ambiguity recall | 0.0000 |
| Mean latency | 1092.129 ms |

`PENDING_ACTION_TARGET_MUTATION` is not represented in this routing holdout. Existing verifier regression suites ran separately: backend 9 passed and Flutter 15 passed, with `INVALID_STRUCTURED_OUTPUT_ESCAPED_VERIFIER=0`. The safety-critical misses mean this routing result is not a promotion qualification.
