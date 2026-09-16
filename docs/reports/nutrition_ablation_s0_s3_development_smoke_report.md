# Nutrition Ablation S0-S3 Development Smoke Report

## Classification

```text
ARTIFACT_CLASS = DEVELOPMENT_SMOKE
CONFIRMATORY_EVIDENCE = NO
BENCHMARK_COMPARISON = NO
PRODUCTION_ROLLOUT_AUTHORITY = NO
```

This report records a live end-to-end capability smoke on 2026-09-16. The four
arms used specialized smoke cases, not the same frozen benchmark case, so their
latency, token usage, and answer content must not be compared as treatment
effects.

## Frozen execution identity

- Git commit: `74238e5` (`74238e5...` in every run record)
- Worktree: clean for every run
- Protocol: `nutrition-ablation-s0-s3-v1`
- Prompt: `nutrition-ablation-v1`
- Requested route: `chr/charm/qwen3.8-flash`
- Provider-reported model: `qwen3.8-flash`
- Temperature: `0`
- Max output tokens: `1200`
- Corpus: `offline-v1-636`
- Corpus database verification before execution: one manifest, 636 chunks, 636
  embeddings
- Canonical tool policy for S2/S3: `nutrition-policy-v1.0.1`

The original route `ram/qwen-3.8-flash` returned `503 MODEL_INACTIVE` during
development preflight. No scored run silently substituted a route.

## Run summary

| Arm | Run ID | Test case | Latency ms | Prompt / completion / total tokens | RAG chunks | Tool calls | Finish reasons | Response chars |
|---|---|---|---:|---:|---:|---:|---|---:|
| S0 | `f830557f-113f-408a-9228-9fe91e6797b1` | `phase1-smoke-001` | 12548.320 | 3072 / 549 / 3621 | 0 | 0 | `stop` | 729 |
| S1 | `afdd1575-6a30-4ce8-a1f5-dd02cf17c94d` | `phase2-c-smoke-pho-001` | 8663.008 | 4824 / 451 / 5275 | 5 | 0 | `stop` | 398 |
| S2 | `9bd76a81-1632-429a-ac20-6d80b9183732` | `s2-calculation-smoke-001` | 19525.028 | 11484 / 851 / 12335 | 5 | 1 | `tool_calls`, `stop` | 1333 |
| S3 | `eec186a3-7cc1-4713-821c-67ed69759dc6` | `s3-personalization-smoke-001` | 35566.843 | 11616 / 1666 / 13282 | 5 | 1 | `tool_calls`, `stop` | 2741 |

Configuration hashes:

- S0: `53db81f9401118174fd4f7e94619a0490cfa21f18877c9bb777b5c4d465c3107`
- S1: `d112b5bcadbe26a517555474ca0c8b8373cd80a8ba2c9423ad1988aa2d6c8c33`
- S2: `d214889b8f118ee559e9a9de1009906943f1ce045ac691af80f4e648aa61ae11`
- S3: `edb3515957385954f73c777228e8f4c9af85a837b8b7d82a6b258ec000246bb8`

## Structural checks

- All four records completed without experiment error and with
  `worktree_clean=true`.
- S0 had no profile, RAG context, or tools.
- S1 had five frozen RAG chunks and no profile or tools.
- S2 had five frozen RAG chunks, no profile snapshot, no hidden-profile sentinel
  in its rendered prompt, and one successful `calculate_tdee` call.
- S2 tool output matched the deterministic smoke expectations: BMI `22.86`, RMR
  `1649`, TDEE `2556`, target `2556`, status `READY`.
- S3 had the explicit fixture profile, five frozen RAG chunks, and one successful
  `calculate_tdee` call with policy `nutrition-policy-v1.0.1`.
- Every citation UUID emitted by S1/S2/S3 referred to a chunk present in that
  run's retrieval trace; no citation referenced outside retrieved evidence.
- The S3 answer explicitly handled the `vegetarian` restriction and peanut
  allergy. This is a smoke observation, not a validated constraint-satisfaction
  score.
- Final finish reasons were `stop`; no final response was truncated.

Response SHA-256 values for local audit:

- S0: `6d275766a3ac8104cc47a5c452ceffebb275bae33bd3170cb47c9f65adc96d9b`
- S1: `e33175622a0ce9a7db2269917c56a8936bf4d4a944a12c82e29ab2eb4e250a79`
- S2: `b045fd745ec63f2691759c7ec7b989b18d315152195e5f78c4060a5a71e684c4`
- S3: `2a86017d91c7c020f93446298f6406ffc14ed65735975790be18c07680e0654b`

## Interpretation boundary

This smoke establishes that the four treatment paths can execute end to end
with the selected provider route, frozen research corpus, canonical nutrition
tool, profile isolation, run metadata, token logging, and truncation detection.
It does not establish factual superiority, numerical-accuracy improvement,
personalization benefit, test-retest reliability, cost efficiency, statistical
significance, clinical safety, or rollout readiness.

The next research gate is a reviewed development benchmark and manifest. A
paired comparison may start only after the same cases, model controls, corpus,
prompt, run count, scoring rules, and human-review protocol are frozen.
