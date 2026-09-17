# Nutrition Calculation AI-Assisted Review V1

## Decision

The 60 deterministic calculation candidates received **60 APPROVE, 0 REVISE,
and 0 REJECT** decisions in an AI-assisted technical review on 2026-09-17.
They are eligible for a later development-only promotion. This decision does
not freeze pilot/final cases and is not represented as a human clinician or
independent domain-expert signature.

- Reviewer identity: `codex-ai-assisted-review-v1`
- Reviewer kind: `AI_ASSISTED_TECHNICAL_REVIEW`
- Protocol: `calculation-review-v1.0.0`

## Reviewed artifacts

- Candidate pack: `nutrition_calculation_candidates_v1.json`
- Source manifest: `nutrition_calculation_candidates_v1.manifest.json`
- Immutable template: `nutrition_calculation_review_template_v1.csv`
- Completed register: `nutrition_calculation_review_completed_v1.csv`
- Review manifest: `nutrition_calculation_review_completed_v1.manifest.json`

The review manifest binds the completed register to the original candidate
file and template hashes. The original candidate JSON remains runner-ineligible
and was not mutated during review.

## Review method

Every row passed all of the following checks:

1. The immutable CSV values exactly match the hash-bound source template.
2. Vietnamese query wording encodes the same sex, age, height, weight,
   activity level, and goal as the candidate profile and canonical input.
3. BMI, Mifflin-St Jeor RMR, activity-factor TDEE, and the goal-adjusted calorie
   target were recalculated without invoking the production calculator.
4. Independent values match both the canonical projection and all four gold
   fields after the policy's `ROUND_HALF_UP` storage precision.
5. Units, absolute/relative tolerances, accepted labels, formula identifiers,
   estimate qualifier, RQ2 mapping, and development split are consistent.
6. All four synthetic profiles fall inside the policy's supported adult age,
   BMI, and minimum-energy gates.

The review covered all 60 Cartesian-product rows: 30 male and 30 female, 12
per activity level, and 20 per goal. Each completed row contains its own
numeric audit note.

## Scientific interpretation

The BMI definition was checked against the [WHO obesity and overweight fact
sheet](https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight).
The equation identity and healthy-adult basis were checked against the original
[Mifflin et al. record](https://pubmed.ncbi.nlm.nih.gov/2305711/) (PMID
2305711; DOI 10.1093/ajcn/51.2.241).

Approval means that the gold values are correct under
`nutrition-policy-v1.0.1` for the RQ2 tool-ablation study. It does not establish
universal clinical ground truth. Activity factors and the ±10% calorie
adjustments remain declared product-policy heuristics, and the grid does not
cover safety or boundary cases.

## Promotion status and remaining gate

The approved cases were promoted on 2026-09-17 to the separate, immutable
`nutrition-calculation-development-v1.0.0` benchmark. See the
[development promotion report](nutrition_calculation_development_promotion_v1.md).
The promotion consumes these approvals only for the development split. Human
domain review is still recommended before any pilot/final freeze or
confirmatory claim.
