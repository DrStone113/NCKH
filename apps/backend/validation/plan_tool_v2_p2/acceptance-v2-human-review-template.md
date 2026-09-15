# Plan V2 Acceptance V2 Human Review Register

Status: `PENDING_HUMAN_REVIEW`; this document is not evidence of completed
review.

P2.1H provides the reviewer-only pack
`p2-1h-human-review-pack-v1.json` and blank JSON/CSV registers named
`p2-1h-human-review-register-template-v1.*`. The pack contains all 150
candidates, including the 120 proposed final cases and 30 preselected-out
candidates; it contains no runtime result.

Before freezing `PLAN_V2_ACCEPTANCE_V2`, reviewers must record, for each
candidate they review:

1. Reviewer identity and review date.
2. Whether the Vietnamese prompt has an unambiguous user intent.
3. Whether the referenced oracle profile is sufficient, including acceptable
   outcomes, forbidden outcomes, and required clarification.
4. A disposition: `ACCEPT`, `REVISE_BEFORE_FREEZE`, `REJECT_AMBIGUOUS`,
   `REJECT_DUPLICATE`, `REJECT_LEAKAGE`, or `REJECT_OUT_OF_SCOPE`.
5. Any semantic/template candidate disposition from the leakage report.

Two independent reviewers are preferred for semantic or safety-sensitive
cases. A single completed reviewer record is not to be represented as
two-person review. The validator computes coverage, reviewer disagreement,
percent agreement and, when pairs are available, Cohen's kappa; these are
engineering review quality indicators, not research results. After every
proposed case and every flagged pair is reviewed, create a separate immutable
review register with a content hash, change the oracle status to
`FROZEN`/`HUMAN_REVIEWED`, and create the final 120+ case acceptance dataset.
Do not edit these candidates and relabel them as an independent holdout without
that review trail.
