# Nutrition calculation ablation — development analysis

## Classification

```text
ARTIFACT_CLASS = DEVELOPMENT_ONLY
CONFIRMATORY_EVIDENCE = NO
CLINICAL_VALIDATION = NO
PRODUCTION_ROLLOUT_AUTHORITY = NO
```

This report is a deterministic aggregate of the complete paired calculation
batch. Raw provider responses remain in ignored local logs and are not copied
into this tracked artifact.

## Frozen execution identity

- Experiment: `nutrition-calculation-development-v1-minimax-r1c-20260918`
- Benchmark: `nutrition-calculation-development-v1.0.0` (60 cases)
- Runs: `240`
- Requested model route: `mn/MiniMax-M2.7`
- Provider-reported model: `MiniMax-M2.7`
- Execution commit: `154398a472b5621de485fce0a548d1d5ed283152`
- Protocol / prompt: `nutrition-ablation-s0-s3-v1` / `nutrition-ablation-v1`
- Temperature / max tokens: `0.0` / `4000`
- RAG: top-k `5`, threshold `0.5`
- Corpus: `offline-v1-636` / `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`
- Records SHA-256: `b1ac8060b75fc6a2d42d4273a745001238e19f017652204fbbd9b4ab84d17098`

## Answer accuracy

Missing values count as incorrect. A value is correct when it meets its
predeclared absolute or relative tolerance.

| Arm | All 4 correct | BMI | RMR | TDEE | Target | Median latency | Mean tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| S0 | 11.7% | 96.7% | 83.3% | 50.0% | 13.3% | 15253 ms | 1921 |
| S1 | 18.3% | 100.0% | 86.7% | 63.3% | 25.0% | 17168 ms | 3959 |
| S2 | 71.7% | 100.0% | 96.7% | 73.3% | 81.7% | 14032 ms | 9024 |
| S3 | 73.3% | 98.3% | 98.3% | 76.7% | 90.0% | 14791 ms | 9319 |

## RQ2 development contrast: S1 → S2

- Correct on all four values: `11/60` → `43/60`.
- Absolute paired rate difference: `53.3` percentage points.
- Improved / worsened pairs: `34` / `2`.
- Exact two-sided McNemar p-value: `1.94123e-08`.

## Tool-path audit

| Arm | Invoked | Successful | Exact arguments | All 4 structured values correct |
|---|---:|---:|---:|---:|
| S2 | 98.3% | 98.3% | 84.7% | 83.3% |
| S3 | 98.3% | 98.3% | 91.5% | 90.0% |

Tool correctness is reported separately from answer correctness. A valid
deterministic calculation is still counted wrong against the benchmark when
the model supplied the wrong activity level or goal.

## Interpretation boundary

- This benchmark supports only a development-stage RQ2 analysis.
- It does not test RQ1 because calculation cases have no source-linked knowledge gold.
- It does not isolate RQ3 because the same profile facts are explicit in each query.
- It is not confirmatory, clinically validated, or authority for production rollout.
- Pilot/final claims require separately frozen cases and genuine independent human/domain review.
