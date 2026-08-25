# Context Planner v1 — D3.0.1 robust shadow validation

This phase does not change routing rules and does not enable enforcement. It
separates `REGRESSION`, `NATURAL_SHADOW`, and `ADVERSARIAL_HOLDOUT` identities,
including lifecycle, hashes, oracle review state, and tuning history.

## Natural collection

Natural collection is disabled unless both conditions are true:

1. `CONTEXT_PLANNER_MODE=shadow`
2. `CONTEXT_PLANNER_NATURAL_COLLECTION_PATH` points to an authorized JSONL artifact

The collector stores redacted query text, up to four redacted prior user turns,
a random process-local sequence identifier, source statuses, the structural
shadow plan, planner version, and token measurements. It never accepts the raw
health profile, authentication metadata, user/session identifiers, treatment
metadata, or research metadata.

Exact token counts are used only when the configured LLM exposes its tokenizer
or an already-installed tokenizer recognizes the model. Otherwise records are
marked `UTF8_BYTES_CEIL4_APPROXIMATION`; approximate values must not be reported
as actual tokenizer measurements.

## Review and freezing workflow

Export the candidate and review artifacts:

```powershell
$env:PYTHONPATH='apps/backend'
python apps/backend/scripts/export_context_planner_validation_candidates.py apps/backend/validation/context_planner_d3_0_1 --natural-jsonl <authorized-natural.jsonl>
```

An independent human reviewer fills every oracle field and uses a pseudonymous
identifier such as `reviewer-001`. An LLM-produced label is not an authoritative
oracle. Freeze only after review and only when the dataset has at least 100
cases:

```powershell
python apps/backend/scripts/freeze_context_planner_validation_dataset.py --dataset-type ADVERSARIAL_HOLDOUT --dataset-version <version> --cases <cases.json> --oracles <reviewed-oracles.json> --manifest <manifest.json>
```

The evaluator verifies the case and oracle hashes before classification:

```powershell
python apps/backend/scripts/evaluate_robust_context_planner_dataset.py --manifest <manifest.json> --cases <cases.json> --oracles <reviewed-oracles.json>
```

If any case from a holdout is used to change routing, mark the dataset as used
for tuning. The implementation changes its identity to `REGRESSION`; it cannot
subsequently be presented as an independent holdout.

## Current status

The development PostgreSQL store contained zero genuine user turns at the
D3.0.1 snapshot. Natural collection therefore remains `COLLECTING`. The 100
adversarial turns are `CANDIDATE` and `PENDING_HUMAN_REVIEW`. Neither has been
evaluated, and D3.1 acceptance is unavailable/fail-closed.
