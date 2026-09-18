# Nutrition Ablation S0-S3 V1

## Status

This document defines the implementation boundary for
`nutrition-ablation-s0-s3-v1`. It is a development-ready experiment protocol,
not evidence that the benchmark, human review, or statistical analysis has
already been completed.

## Why this is a new protocol

The repository already contains a frozen A-D experiment family:

| Historical condition | Profile | RAG | Nutrition tool |
|---|---:|---:|---:|
| A | no | no | no |
| B | yes | no | no |
| C | yes | yes | no |
| D | yes | yes | legacy tool |

That family adds profile before RAG and therefore cannot answer the new
incremental research questions by renaming its conditions. Its configuration
hashes, historical records, frozen corpus, and legacy condition-D calculator
remain unchanged.

The new protocol adds independent arm names with the requested order:

| Arm | Profile | RAG | Canonical nutrition tool | Primary comparison |
|---|---:|---:|---:|---|
| S0 | no | no | no | baseline LLM |
| S1 | no | yes | no | S0 vs S1: contribution of RAG |
| S2 | no | yes | yes | S1 vs S2: contribution of deterministic tools |
| S3 | yes | yes | yes | S2 vs S3: contribution of personalization |

All arms use the same isolated runner, fixed model controls, frozen time,
single-turn request shape, logging path, and prompt version
`nutrition-ablation-v1`. The S0-S3 CLI default is pinned to
`chr/charm/qwen3.8-flash`; an actual run must record the provider-returned model and
must fail rather than substitute another model. Only the three treatment flags
differ within a comparison.

## Isolation and safety contracts

- The experiment package does not import the production chat orchestrator,
  memory, live Firebase profile, production router, or production tool registry.
- Profile data comes only from an explicit immutable fixture and appears only in
  S3.
- RAG uses only the versioned frozen research corpus and appears only in S1-S3.
- The only tool available in S2-S3 is the idempotent `calculate_tdee` adapter.
- S2-S3 delegate calculations to canonical `nutrition-policy-v1.0.1`; formulas
  are not copied into the experiment package.
- Safety, allergy, and dietary constraints remain deterministic benchmark
  requirements. Personalization never authorizes a canonical write, meal log,
  plan mutation, adaptive-ranking promotion, or web nutrition source.
- A missing RAG result or tool failure is recorded as an explicit experiment
  error. It does not silently fall back to a different treatment.

## Run contract

From `apps/backend`, one smoke case can be run with:

```powershell
python -m scripts.run_experiment `
  --condition S0 `
  --case tests/fixtures/example_experiment_case.json `
  --experiment-id nutrition-ablation-smoke
```

Repeat with S1, S2, and S3 using the same model and non-treatment settings.
For S0-S3, the CLI selects `nutrition-ablation-v1` unless an explicit prompt
version is supplied, and selects `chr/charm/qwen3.8-flash` unless an explicit model
is supplied. Every record contains the protocol ID, full serialized
configuration and hash, requested/actual model, exact prompt, retrieval trace,
tool calls, aggregated provider token usage when available, latency, Git commit,
dirty-worktree state, and every provider completion finish reason. A final
`finish_reason=length` is retained for audit but marks the run as
`EXPERIMENT_OUTPUT_TRUNCATED`; it must not be scored as a successful response.

For a reviewed benchmark plus its integrity manifest, validate the complete
paired schedule without making API or database calls:

```powershell
python -m scripts.run_benchmark `
  --benchmark path/to/nutrition-benchmark-v1.json `
  --manifest path/to/nutrition-benchmark-v1.manifest.json `
  --split development `
  --repetitions 2 `
  --plan-only
```

Remove `--plan-only` to execute the schedule. The batch runner reuses one
fixed-model client and one frozen-corpus provider, varies only the S0-S3
treatment condition, and appends each result immediately to
`logs/nutrition-ablation-results.jsonl` by default. Every record includes the
benchmark file hash, manifest hash, case hash, split, deterministic schedule
seed, repetition index, and schedule index. A provider or corpus error remains
a failed durable record and makes the command exit non-zero after the schedule
finishes.

For a long development run interrupted between records, rerun the identical
command with `--resume`. Resume accepts only an exact prefix of the deterministic
schedule with the same experiment ID, benchmark/manifest hashes, configuration,
model route, Git commit, clean-worktree state, repetitions, and seed. Existing
failed rows remain immutable and are not retried. Without `--resume`, an
existing output file is rejected to prevent accidental duplicate appends.

The SHA-256 schedule order is reproducible from the same benchmark, selected
arms, repetition count, and schedule seed. A `final` split additionally
requires a clean Git worktree and an output path outside the repository or
ignored by Git, preventing result writes from invalidating later run metadata.

After a batch completes, export only integrity-checked deterministic metrics:

```powershell
python -m scripts.evaluate_benchmark `
  --benchmark path/to/nutrition-benchmark-v1.json `
  --manifest path/to/nutrition-benchmark-v1.manifest.json `
  --records logs/nutrition-ablation-results.jsonl `
  --split development `
  --repetitions 2
```

The evaluator requires the full `case × arm × repetition` product, contiguous
schedule indices, one Git commit, one requested/actual model identity, equal
non-treatment controls, and matching benchmark, manifest, case, config, corpus,
profile, and tool metadata. It refuses a tampered or incomplete batch. Failed
provider/corpus/truncated runs remain in the evaluation export as `run_error`
with no metrics, so partial text cannot be scored as a successful answer.

Free-text judgments are not inferred automatically. Optional blinded human
annotations can be supplied as JSONL with `--annotations`:

```json
{"run_id":"...","annotations":{"observed_values":{},"satisfied_constraint_ids":[],"violated_constraint_ids":[],"cited_source_ids":[]}}
```

Without an annotation, metrics that require human judgment are explicitly
marked `requires_annotation`. The default evaluation output is the ignored
file `logs/nutrition-ablation-evaluations.jsonl`; an existing output is not
overwritten unless `--overwrite` is given.

### Provider preflight on 2026-09-16

This is operational development evidence only, not a scored benchmark result.
The configured Vilao endpoint authenticated successfully. The originally
requested route `ram/qwen-3.8-flash` returned `503 MODEL_INACTIVE`. Short
availability probes showed that `wen/qwen3.8-flash` reported a different actual
model identity and `heg/qwen3.8-flash` omitted model identity/token usage. The
selected route `chr/charm/qwen3.8-flash` completed successfully and reported
`qwen3.8-flash`, so it is the pinned S0-S3 route until the confirmatory protocol
is frozen. Provider availability must be rechecked without substituting another
route inside a scored run.

## Benchmark design boundary

The existing versioned benchmark schema already supports required facts,
immutable sources, numerical expected values, dietary/allergy constraints,
retrieval recall/MRR, citations, latency, token usage, and human annotations.
It does not yet contain a frozen 300-case benchmark file.

The deterministic 60-case calculation draft and review workflow are documented
in [Nutrition Calculation Candidate Authoring V1](nutrition_calculation_candidate_authoring_v1.md).
An [AI-assisted technical review](../reports/nutrition_calculation_ai_assisted_review_v1.md)
approved all 60 cases on 2026-09-17, with its non-human reviewer kind and
development-only boundary recorded in a hash-bound manifest. The candidate
file remains runner-ineligible. A separate
[calculation development benchmark](../reports/nutrition_calculation_development_promotion_v1.md)
was promoted and accepted by the standard batch planner as a 240-run S0-S3
schedule. Human domain signoff remains outstanding for any pilot/final freeze.

Before collecting final responses:

1. Build and review a development/pilot/final benchmark with no LLM-generated
   answer used as ground truth.
2. Keep calculation cases and personalization cases distinct. S2 calculation
   prompts must contain their explicit numeric inputs; S2 personalization
   prompts must not receive the hidden fixture profile.
3. Use paired profile cases for S2 vs S3 and annotate goal, activity, allergy,
   dietary, and safety requirements separately.
4. Freeze the benchmark file, manifest, prompt, model identifier, corpus hash,
   canonical nutrition policy version, run count, and evaluator rubric before
   the confirmatory run.
5. Keep development/tuning responses separate from confirmatory evidence.

## Evaluation boundary

Use deterministic scoring where possible and explicit blinded human annotation
where free text requires judgment. LLM-as-a-judge may be reported as a secondary
analysis but is not the sole ground truth.

For paired binary outcomes use an overall repeated-measures test followed by
predeclared adjacent comparisons with multiple-comparison correction. For
ordinal human scores use the corresponding paired non-parametric analysis.
Report effect sizes and confidence intervals in addition to p-values. Final test
selection must be reviewed against the actual endpoint distribution; this file
does not pre-register a completed statistical analysis.

## Not yet complete

- No frozen 300-case benchmark or completed human domain-review pack exists
  yet; the 60 calculation cases have only a completed AI-assisted technical
  review for development promotion.
- A clean-worktree S0-S3 development smoke completed on 2026-09-16; it is not
  a scored benchmark or confirmatory result.
- Retrieval quality, response quality, cost, test-retest reliability, and
  statistical significance have not been established.
- Multi-turn and the eight-arm full factorial remain later protocols.
- No production capability or adaptive-ranking flag is enabled by this work.

The tracked S2/S3 smoke fixtures follow this separation: the S2 calculation
query contains every numeric/tool input while its profile is a hidden sentinel;
the S3 query omits those values and receives them only through the explicit
fixture profile.
