# Acceptance performance results

Available evidence is component-only. The preserved sequential retrieval run reports p50 63.167 ms and p95 82.997 ms; its historical mean is 81.171 ms and throughput 12.32 queries/s. The actual routing holdout reports mean semantic-routing latency 1092.129 ms.

The required separate sequential full-pipeline latency measurement (p50, p95, mean, throughput) and the quality run at concurrency 2 or 4 are `NOT_MEASURED`, because full-pipeline generation is blocked before provider use. No synthetic latency was substituted and no provider retry was made.
