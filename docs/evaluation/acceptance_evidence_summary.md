# Acceptance evidence summary

## Evidence retained

- `docs/evaluation/rag_research_audit_v2.md`: database/wiring root-cause audit.
- `evaluation/results/engineering-eval-v1-api-firstpass/`: historical invalid V1 first pass, preserved.
- `evaluation/results/v1-frozen-provider-retrieval-20260921-r3/`: corrected frozen V1 retrieval raw results, empty failures file, metrics, and metadata.
- `apps/backend/data/research_v2/`: source registry, raw archive hash, normalized projections, and V2 manifest.
- `evaluation/v2/`: pre-scoring V2 candidate/final artifacts with explicit contamination limitation.
- `evaluation/v2/safety/` and `evaluation/v2/e2e/`: 80 safety cases and 16 E2E scenarios, defined but not executed.

## Acceptance decision

`READY_FOR_RESEARCH_REPORT=NO` and `READY_FOR_ACCEPTANCE_DEMO=NO` for the complete requested package. V1 retrieval infrastructure is repaired and evidenced, but V1 answer/safety/E2E are incomplete. V2 must be rebuilt as a new version after deduplication and completed contamination control. No clinical validation was performed.
