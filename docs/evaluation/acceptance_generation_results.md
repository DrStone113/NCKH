# Acceptance full-pipeline generation result

The 200 frozen cases, expected-channel projection, and deterministic/semantic grading rubric were preflighted. Projection SHA-256: `d28e3e308b3b5c98c489a5e00a536ba63ff447bbb01db6188fde6844dd00638e`; rubric SHA-256: `87ac24dcf4e123285d81f7d8ebafdc30d03d4bd376aab9b44c7c38870a87a1f9`.

`GENERATION_STATUS=BLOCKED_CREDENTIAL_ROTATION_REQUIRED`. A provider credential is configured, but no generation or judge request was sent because the workflow requires rotation attestation for the previously exposed credential. Therefore answer relevance, faithfulness, unsupported-claim rate, no-evidence handling, provenance correctness, expected-channel accuracy, tool-call count, and per-domain success are all `NOT_MEASURED`. This is not a zero score and no retries were made.

The evaluation-only adapter has been added to expose only the frozen research corpus when the isolated harness sets `ACCEPTANCE_EVALUATION_CORPUS_VERSION` and `ACCEPTANCE_EVALUATION_CORPUS_HASH`. It does not copy the corpus, mutate production RAG tables, or change the normal server default.
