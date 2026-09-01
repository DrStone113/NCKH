# Research Corpus Verifier R1

The frozen research manifest remains immutable and continues to verify its own
full `manifest_hash`. Verifier R1 does not rebuild the corpus, update that
manifest, or alter any experiment A/B/C configuration.

## Scientific identity

`research-corpus-identity-v1` is a canonical projection used to decide whether
a database materialization is valid for the frozen experiment. It strictly
includes corpus version/content hash, record/embedding/dynamic counts, source
dataset hashes and counts, embedding model/revision/version/dimension,
normalization, chunking, ingestion-code version, and frozen RAG top-k/threshold
configuration. Its SHA-256 is reported as `scientific_identity_hash`.

## Operational provenance

`created_at`, `ingestion_git_commit`, `ingestion_worktree_clean`, and the full
`manifest_hash` remain recorded and are compared separately. A difference is
reported as `OPERATIONAL_PROVENANCE_DIFFERENCE`; it cannot mask any scientific
identity mismatch, but it also does not falsely claim that matching corpus
content was changed.

## Outcomes

The verifier prints explicit statuses:

- `SCIENTIFIC_IDENTITY_MATCH` or `SCIENTIFIC_IDENTITY_MISMATCH`
- `OPERATIONAL_PROVENANCE_MATCH` or `OPERATIONAL_PROVENANCE_DIFFERENCE`

It exits non-zero for a scientific mismatch or for invalid self-integrity of
either manifest. A provenance-only difference remains valid for the frozen
experiment and reports both historical and operational full-manifest hashes.
