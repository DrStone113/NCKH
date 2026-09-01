# Plan V2 Acceptance V2 Human Review Register

Status: `PENDING_HUMAN_REVIEW`; this document is not evidence of completed
review.

Before freezing `PLAN_V2_ACCEPTANCE_V2`, reviewers must record, for each of
the 120 proposed cases in `qualification_candidates_v2.py`:

1. Reviewer identity and review date.
2. Whether the Vietnamese prompt has an unambiguous user intent.
3. Whether the referenced oracle profile is sufficient, including acceptable
   outcomes, forbidden outcomes, and required clarification.
4. A disposition: `ACCEPT`, `REJECT`, or `REWRITE_BEFORE_FREEZE`.
5. Any semantic/template candidate disposition from the leakage report.

Two independent reviewers are preferred for semantic or safety-sensitive
cases. A single completed reviewer record is not to be represented as
two-person review. After every proposed case and every flagged pair is
reviewed, create a separate immutable review register with a content hash,
change the oracle status to `FROZEN`/`HUMAN_REVIEWED`, and create the final
120+ case acceptance dataset. Do not edit these candidates and relabel them as
an independent holdout without that review trail.
