# Nutrition Calculation Development Promotion V1

## Outcome

The 60 unanimously approved calculation cases were promoted on 2026-09-17 to
the runnable, immutable development benchmark
`nutrition-calculation-development-v1.0.0`.

- Cases: 60
- Category: `energy_calculation` (60)
- Split: `development` (60)
- Promotion scope: `DEVELOPMENT_ONLY`
- S0-S3 runs per repetition: 240
- Human domain signoff: `false`

No case was assigned to pilot or final. The source candidate file remains an
unmodified, runner-ineligible review artifact; the promoted benchmark is a
separate `BenchmarkFile`.

## Integrity chain

The benchmark manifest records and verifies this chain:

```text
candidate manifest
  -> completed review CSV + review manifest
  -> promoted benchmark JSON + benchmark manifest
```

The recorded identifiers are:

- Candidate manifest hash:
  `12fa73b085a4a0fefbc3e2ba62c344fc82eab11edfa23af7f3d132da3dcad83e`
- Completed review SHA-256:
  `3a86dd85960d99ee0b1da6b2e653b074f90393144c80746e335d7778bfd00e28`
- Review manifest hash:
  `f1a5a59aeb98e17e12643e66e114d62f2efe4cfeec14c824938ea617997a4c66`
- Benchmark file SHA-256:
  `e65a0d1c6bf72fe138db3c46175a0189fdcccdec881ee917226d475e1658b262`
- Benchmark manifest hash:
  `a367c70a3b2006c8aadda716cacd9000cf826dfd4078e6e8172d562667ff5787`

The promotion was generated from clean commit
`a039fb0b4e10daa57fb8ac3198d6fe2de8c25001`. The manifest preserves the
non-human reviewer kind instead of presenting the technical review as an
independent clinician signature.

## Runner acceptance

The standard batch CLI loaded and verified the promoted benchmark and manifest
in plan-only mode with schedule seed 42. It produced indices 1 through 240 for
60 unique cases across `S0,S1,S2,S3`, with no API or database call:

```powershell
python -m scripts.run_benchmark `
  --benchmark data/research/benchmarks/calculation_development_v1/nutrition_calculation_development_v1.json `
  --manifest data/research/benchmarks/calculation_development_v1/nutrition_calculation_development_v1.manifest.json `
  --split development `
  --repetitions 1 `
  --schedule-seed 42 `
  --plan-only
```

## Remaining boundary

This artifact is suitable for development runs of the RQ2 calculation
comparison. It does not complete the planned multi-category benchmark, supply
human domain signoff, authorize pilot/final assignment, or constitute a
confirmatory result. Knowledge/RAG and personalization cases require their own
source-grounded authoring and review before a broader benchmark version can be
created.
