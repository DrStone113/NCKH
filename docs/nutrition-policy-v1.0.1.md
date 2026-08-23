# nutrition-policy-v1.0.1 compatibility patch

This patch preserves every mathematical constant and equation from
`nutrition-policy-v1`. It does not replace or rewrite the v1 policy artifact.

The only applicability changes are:

- BMI below 18.5 remains calculable and may produce informational estimated RMR
  and TDEE, but ordinary calorie and macronutrient targets are withheld with
  `REQUIRES_SPECIALIST_GUIDANCE`.
- Six self-reported safety/applicability fields use `YES`, `NO`, `UNKNOWN`, or
  `NOT_PROVIDED`. A `YES` makes the ordinary calculator unsupported. Unknown
  answers remain unknown; they do not silently become `NO`, and targets remain
  available with `SAFETY_SCREENING_INCOMPLETE` when all other inputs are valid.
- Every canonical derived result, including daily summaries, carries policy and
  formula provenance.

These rules are product applicability safeguards, not diagnoses. The frozen
research calculator remains `research-legacy-v1`.
