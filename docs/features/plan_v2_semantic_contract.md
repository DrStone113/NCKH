# Plan V2 Semantic Contract V1

This contract defines future Plan V2 semantic scoring. It does not alter the immutable V3 result or replace its oracle.

## Core semantics

- Operations are exact: `create`, `update`, `activate`, `pause`, `resume`, `cancel`, and `read_exact` are distinct.
- Entity bindings are exact owner-scoped plan/revision identities. A symbolic label is not a plan reference.
- Required request fields (domain, period, timezone, lifecycle target, concrete references, and safety authority when applicable) must agree exactly. Missing required context requires a safe clarification or specialist response; it is never silently filled in.
- Values are exact except for trimming surrounding whitespace and uppercasing status tokens. No numeric, identifier, date, time, enum, or alias equivalence is inferred without an explicit contract amendment.
- Dates and timezones use the frozen literal values. Relative-time expressions must be resolved from an explicit frozen clock before scoring; wall-clock time is forbidden.
- Ordered action sequences remain ordered. A collection is treated as a set only where the field contract explicitly marks it set-like; no global list sorting is permitted.
- `null`, absent, and an empty value are distinct when a field is required. Optional representation metadata may be ignored only when it adds no user-visible plan behavior.

## Domain rules

- Nutrition requires a `READY` plan whose period/timezone match the request and whose generated items carry canonical references.
- Workout requires authoritative `workout_profile` and exercise-safety context for a generated session. Without that authority, a safe clarification or specialist response is the only accepted semantic outcome; a fabricated ready workout is rejected.
- A combined-health container requires two concrete child bindings (`plan_id`, `revision_id`, and `revision_content_hash`). Symbolic fixture names require a safe clarification; they cannot be treated as an executable reference chain.
- Lifecycle commands require the exact target state and owner-scoped revision binding.
- Unknown or unsafe context requires a clarification or specialist response and no generated ready plan.

## Reference and safety boundary

Reference identity, role, and ordering remain exact wherever the operation requires them. These rules do not relax planned-to-actual separation, write protections, canonical-reference checks, owner scope, or any hard safety gate. Diagnostics report operation, target, field, value, missing, and extra semantics without accepting a mismatch.
