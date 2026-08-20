-- Frozen, offline-only corpus used exclusively by research conditions C/D.
-- It is physically separate from production knowledge_chunks so runtime web
-- ingestion cannot change the experimental treatment.

CREATE TABLE IF NOT EXISTS research_corpus_manifests (
    corpus_version TEXT PRIMARY KEY,
    corpus_hash CHAR(64) NOT NULL UNIQUE,
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research_knowledge_chunks (
    corpus_version TEXT NOT NULL
        REFERENCES research_corpus_manifests(corpus_version) ON DELETE CASCADE,
    chunk_id UUID NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('food', 'exercise')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    source_record_id TEXT NOT NULL,
    dataset_file TEXT NOT NULL,
    dataset_hash CHAR(64) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    is_dynamic BOOLEAN NOT NULL DEFAULT FALSE CHECK (is_dynamic = FALSE),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'B')
    ) STORED,
    PRIMARY KEY (corpus_version, chunk_id),
    UNIQUE (corpus_version, content_hash)
);

CREATE TABLE IF NOT EXISTS research_chunk_embeddings (
    corpus_version TEXT NOT NULL,
    chunk_id UUID NOT NULL,
    embedding VECTOR(1024) NOT NULL,
    PRIMARY KEY (corpus_version, chunk_id),
    FOREIGN KEY (corpus_version, chunk_id)
        REFERENCES research_knowledge_chunks(corpus_version, chunk_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS research_chunks_search_vector_idx
    ON research_knowledge_chunks USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS research_chunks_source_record_idx
    ON research_knowledge_chunks (corpus_version, dataset_file, source_record_id);

-- Deliberately no approximate vector index. The approved Phase 2 corpus is
-- small (636 rows), and exact scans plus stable tie-breaking are preferable
-- for reproducibility.

GRANT ALL PRIVILEGES ON research_corpus_manifests TO health;
GRANT ALL PRIVILEGES ON research_knowledge_chunks TO health;
GRANT ALL PRIVILEGES ON research_chunk_embeddings TO health;
