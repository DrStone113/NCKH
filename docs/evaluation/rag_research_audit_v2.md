# RAG research audit V2

Audited: 2026-09-21 (Asia/Ho_Chi_Minh)  
Repository revision: `4fabdfcf494d360dc831d71b2d1c12f9ac57f89c` on `main`  
Worktree: dirty before this audit; pre-existing application, mobile, Plan, report, and evaluation changes were present. They were not normalized, staged, committed, or discarded.

## Scope and freeze boundary

This audit treats the V1 evaluation inputs and the V1 research-manifest file as frozen. The existing first-pass result directory is historical evidence and is not overwritten. The production RAG store (`knowledge_chunks`, `chunk_embeddings`) and the versioned research RAG store (`research_corpus_manifests`, `research_knowledge_chunks`, `research_chunk_embeddings`) are separate schemas and have separate providers.

The expected V1 research identity, read from repository artifacts rather than inferred from this audit, is:

| Field | Value |
|---|---|
| Corpus version | `offline-v1-636` |
| Corpus hash | `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081` |
| Expected chunks / embeddings | 636 / 636 |
| Embedding model / revision | `BAAI/bge-m3` / `5617a9f61b028005a4858fdac845db406aefb181` |
| Dimension / normalization | 1024 / L2 via `normalize_embeddings=True` |

## Runtime and database audit

The running `health_backend` and `health_postgres` containers were healthy. The host and the project virtual environments use Python 3.10.21; the backend reports `sentence-transformers==5.6.1`.

Read-only SQL-equivalent counts against the database used by the backend were:

| Store | Count / rows |
|---|---:|
| `knowledge_chunks` | 0 |
| `chunk_embeddings` | 0 |
| `research_corpus_manifests` | 1: `offline-v1-636` with the expected corpus hash |
| `research_knowledge_chunks` | 636 for `offline-v1-636` |
| `research_chunk_embeddings` | 636 for `offline-v1-636` |

`PYTHONPATH=/app python scripts/verify_research_corpus.py` in the backend container passed. It reported `SCIENTIFIC_IDENTITY_MATCH`, 636 chunks, 636 embeddings, zero dynamic rows, and the expected corpus hash. Operational provenance differs only in materialization metadata (`created_at`, ingestion Git state, and full-manifest hash); the verifier explicitly separates that from scientific identity.

The verifier initially failed when invoked without `PYTHONPATH=/app`. This was a command-environment issue, not a corpus failure. The exact BGE-M3 revision is cached on the host but not in the backend container's Hugging Face volume; frozen retrieval is therefore run from the pinned host Python environment against the same PostgreSQL target unless the container cache is deliberately provisioned.

## Root cause of the historical 0% retrieval score

`ROOT_CAUSE_OF_ZERO_RAG=The first-pass V1 runner invoked services.agent.rag_service.RAGService against production knowledge_chunks/chunk_embeddings. Both production tables were empty. The frozen V1 corpus was present and verified in research_knowledge_chunks/research_chunk_embeddings, but that provider was bypassed.`

Evidence:

1. `scripts/run_engineering_eval_v1_api_firstpass.py` imports `RAGService` and calls `service.query(...)` for each V1 RAG case.
2. `RAGService.query` explicitly returns an empty result when `chunk_embeddings` is empty.
3. `services.experiment.rag.PostgresFrozenRagProvider` instead validates the frozen manifest and queries the versioned `research_*` tables using `ExperimentConfig(condition="C")`.
4. A direct frozen-provider check for V1 case `RAG-001` returned its gold chunk at rank 1 without modifying data.

Accordingly, the existing first-pass retrieval output remains preserved and is classified as `INVALID_DUE_TO_WRONG_OR_EMPTY_RUNTIME_RAG_STORE`; it is not evidence that V1 RAG quality is zero.

## Required corrective path

The V1 retrieval evaluator must use `PostgresFrozenRagProvider` and the frozen `ExperimentConfig(condition="C")`. It must not call the production provider, alter thresholds, regenerate V1 cases/oracles, or overwrite the historical first-pass output. A corrected retrieval-only run must be written to a distinct results directory, with raw case results and derived metrics retained together.

Answer-generation, safety, and authenticated E2E remain separate phases. The frozen V1 API run contains 31 checkpointed answer calls, zero health/safety API calls, and defined-but-unexecuted E2E scenarios; none are promoted by this audit.

## V2 readiness observations

The repository already contains a 885-record Wger-derived exercise snapshot with record-level Creative Commons metadata (20 CC0, 133 CC-BY-SA 3, and 732 CC-BY-SA 4 according to the canonical exercise manifest). It is suitable only as a read-only, attribution-preserving research projection after license handling and quality exclusions. It is not a competing production truth source.

The catalog manifests also show 526 Vietnamese foods and 300 production dishes, but V1 uses a smaller frozen source projection. Any V2 corpus must be new, versioned, provenance-complete, and stored alongside—not in place of—V1.
