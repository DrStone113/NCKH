# Nutrition Calculation Candidate Authoring V1

## Status and boundary

This workflow creates a deterministic **development draft** for human review.
It does not create a frozen benchmark, approve scientific ground truth, expose
a production feature, or authorize a confirmatory run.

The 60 calculation candidates target `RQ2`: whether the canonical deterministic
tool improves numerical accuracy from S1 to S2. The protocol question mapping
is:

- `RQ1`: S0 vs S1, contribution of frozen-corpus RAG.
- `RQ2`: S1 vs S2, contribution of deterministic nutrition tools.
- `RQ3`: S2 vs S3, contribution of explicit profile personalization.

## Deterministic design

The generator creates the Cartesian product below:

- 2 sexes;
- 2 adult profile variants per sex;
- 5 activity levels;
- 3 goals.

This produces exactly `2 × 2 × 5 × 3 = 60` cases: 30 male and 30 female,
12 per activity level, and 20 per goal. All proposed cases remain in the
`development` split until review; the generator does not assign pilot or final
holdouts.

Every Vietnamese query contains all calculation inputs explicitly. This keeps
S2 independent of the hidden profile while allowing S3 to receive a matching
profile without introducing conflicting values. Each expected BMI, RMR, TDEE,
and calorie target is produced by the public canonical calculator under
`nutrition-policy-v1.0.1`. The generator does not copy formula implementations
and does not use an LLM to write reference answers.

## Generate the review pack

From `apps/backend`, with a clean Git worktree:

```powershell
python -m scripts.generate_calculation_candidates
```

The default output directory is
`data/research/benchmark_candidates/calculation_v1` and contains:

- `nutrition_calculation_candidates_v1.json`: typed candidate records, proposed
  benchmark cases, expected values, formula IDs, and canonical-output hashes;
- `nutrition_calculation_candidates_v1.manifest.json`: byte hashes for the
  LF-normalized candidate/review files, a line-ending-independent canonical
  policy-content hash, and clean-worktree Git provenance;
- `nutrition_calculation_review_template_v1.csv`: an editable review template.

The JSON file is intentionally not a `BenchmarkFile`, so the batch runner
cannot mistake unreviewed candidates for an approved benchmark. The manifest
and loader reject changes to the candidate JSON, policy file, or original CSV
template.

## Human review contract

Work on a copy of the CSV template. For every row, a reviewer must record:

- `review_decision`: `APPROVE`, `REVISE`, or `REJECT`;
- `reviewer_id`: a stable pseudonymous reviewer identifier;
- `reviewer_notes`: required for `REVISE` or `REJECT`.

Review must check input clarity, Vietnamese wording, applicability to healthy
adults, expected units/tolerances, estimate/screening qualifiers, and whether
the canonical policy is an acceptable study reference. Approval of this draft
does not automatically freeze split assignment or promote cases. A separate
promotion step must validate the completed register, assign development/pilot/
final splits, create the benchmark manifest, and record reviewer provenance.

## AI-assisted technical review

The repository includes a fail-closed technical review command. It compares
all immutable CSV fields with the hash-bound template, recalculates BMI, RMR,
TDEE, and the calorie target through an implementation that does not call the
production calculator, then verifies units, tolerances, applicability gates,
formula provenance, estimate wording, and RQ2 metadata:

```powershell
python -m scripts.review_calculation_candidates `
  --reviewer-id codex-ai-assisted-review-v1
```

The completed CSV and its manifest retain the reviewer kind, timestamp, source
pack hashes, decision counts, checks, references, limitations, and clean Git
provenance. This review may make unanimously approved cases eligible for a
later **development-only** promotion. It is explicitly not a human clinician
or independent domain-expert signature and cannot freeze pilot/final cases.

Scientific interpretation is intentionally narrow. The BMI definition and
the healthy-adult basis of the Mifflin-St Jeor equation are checked against the
WHO fact sheet and the original paper record (PMID 2305711, DOI
10.1093/ajcn/51.2.241). Activity factors and calorie adjustments are reviewed
as versioned product-policy heuristics. Therefore an `APPROVE` decision means
"correct gold under `nutrition-policy-v1.0.1` for RQ2," not universal clinical
ground truth.

## Development promotion

A unanimous, integrity-valid review can be promoted with:

```powershell
python -m scripts.promote_calculation_benchmark
```

The command creates a separate `BenchmarkFile` and standard benchmark manifest
under `data/research/benchmarks/calculation_development_v1`. Promotion is
fail-closed unless the source pack, completed review, and both manifests verify;
all 60 decisions are `APPROVE`; and the Git worktree is clean. The output uses
the immutable version `nutrition-calculation-development-v1.0.0` so later
knowledge, personalization, pilot, or final additions cannot silently change
this benchmark under the same version.

The benchmark manifest retains the candidate-manifest hash, review-manifest
hash, completed-review file hash, review protocol/status/kind, decision count,
and the explicit `DEVELOPMENT_ONLY` scope. The schema rejects moving a case to
pilot/final, while the promotion verifier rejects any change to a reviewed
case.
