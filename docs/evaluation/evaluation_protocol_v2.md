# Engineering Evaluation Protocol V2

## Intended design

The V2 RAG candidate pool contains 260 new cases and its first frozen selection contains 160 cases: 136 evidence-present and 24 true no-evidence cases. Gold evidence consists of frozen chunk and source-record IDs, never an LLM answer. Retrieval scoring is intended to measure Hit@1/3/5, MRR, recall, no-evidence correctness, and false-evidence retrieval rate.

## Freeze-integrity limitation

`evaluation/v2/rag/manifest.json` records `V2_FINAL_SCORING_STARTED=NO`. Its exact V1-artifact scan found `EXACT_OVERLAP=0`, but the separate exclusion index records `FINAL_CONTAMINATION_STATUS=PARTIAL_EXACT_SCAN_PASS_SEMANTIC_REVIEW_PENDING`. Repository-wide semantic and template contamination screening was not completed before this first freeze.

The V2 corpus audit also found 65 exact duplicate contents after technical freeze. Therefore this V2 evaluation must not start final scoring. It remains an auditable draft artifact, not an uncontaminated final holdout.

Any next qualification must create a new corpus version and a new evaluation version after: (1) deduplication before embedding, (2) complete exact/normalized/template/semantic contamination review, (3) all manifest hashes written, and (4) an explicit scoring-start record.

The V2 safety draft has 80 deterministic cases and the E2E draft has 16 real-flow scenarios. Both are `DEFINED_NOT_EXECUTED`, not zero-failure results; their draft status is intentionally separate from the incomplete RAG evaluation freeze.
