"""Deterministic hybrid retrieval over the frozen research-only corpus."""

from __future__ import annotations

import asyncio
import importlib.metadata
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import asyncpg

from services.experiment.config import ExperimentConfig
from services.experiment.corpus import (
    APPROVED_EMBEDDING_DIMENSION,
    APPROVED_EMBEDDING_MODEL,
    APPROVED_EMBEDDING_REVISION,
    APPROVED_SENTENCE_TRANSFORMERS_VERSION,
    NORMALIZATION_BEHAVIOR,
    ResearchCorpusManifest,
    discover_embedding_revision,
    embedding_dimension,
    verify_research_corpus,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.models import FrozenRagChunk, RetrievalTrace

RRF_K = 60
HYBRID_CANDIDATE_LIMIT = 100


class ResearchRagProvider(Protocol):
    async def prewarm(self) -> None: ...

    async def retrieve(
        self, query: str, config: ExperimentConfig
    ) -> RetrievalTrace: ...


def _row_key(row: Mapping[str, Any]) -> str:
    return str(row["chunk_id"])


def fuse_rankings(
    dense_rows: Sequence[Mapping[str, Any]],
    keyword_rows: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
    threshold: float = -1.0,
) -> tuple[FrozenRagChunk, ...]:
    """Fuse independent rankings while preserving every score's meaning."""

    candidates: dict[str, dict[str, Any]] = {}
    for dense_rank, row in enumerate(dense_rows, start=1):
        if float(row["cosine_similarity"]) < threshold:
            continue
        key = _row_key(row)
        candidates[key] = {
            "row": row,
            "dense_rank": dense_rank,
            "keyword_rank": None,
            "keyword_score": None,
        }

    for keyword_rank, row in enumerate(keyword_rows, start=1):
        # Keyword-only candidates are permitted, but only after independently
        # satisfying the same cosine threshold as dense candidates.
        if float(row["cosine_similarity"]) < threshold:
            continue
        key = _row_key(row)
        candidate = candidates.setdefault(
            key,
            {
                "row": row,
                "dense_rank": None,
                "keyword_rank": None,
                "keyword_score": None,
            },
        )
        candidate["keyword_rank"] = keyword_rank
        candidate["keyword_score"] = float(row["keyword_score"])

    fused: list[tuple[float, float, str, str, dict[str, Any]]] = []
    for chunk_id, candidate in candidates.items():
        score = 0.0
        if candidate["dense_rank"] is not None:
            score += 1.0 / (RRF_K + int(candidate["dense_rank"]))
        if candidate["keyword_rank"] is not None:
            score += 1.0 / (RRF_K + int(candidate["keyword_rank"]))
        row = candidate["row"]
        fused.append(
            (
                score,
                float(row["cosine_similarity"]),
                str(row["content_hash"]),
                chunk_id,
                candidate,
            )
        )

    # Fusion score is the primary order. Cosine is a meaningful secondary
    # order, followed by immutable content hash and UUID for total ordering.
    fused.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))

    chunks: list[FrozenRagChunk] = []
    for rank, (fusion, cosine, content_hash, chunk_id, candidate) in enumerate(
        fused[:top_k], start=1
    ):
        row = candidate["row"]
        chunks.append(
            FrozenRagChunk(
                chunk_id=chunk_id,
                rank=rank,
                title=str(row["title"]),
                content=str(row["content"]),
                content_hash=content_hash,
                source={
                    "source_type": str(row["source_type"]),
                    "source_name": str(row["source_name"]),
                    "source_url": row.get("source_url"),
                    "source_record_id": str(row["source_record_id"]),
                    "dataset_file": str(row["dataset_file"]),
                    "dataset_hash": str(row["dataset_hash"]),
                },
                cosine_similarity=cosine,
                keyword_score=candidate["keyword_score"],
                fusion_score=fusion,
            )
        )
    return tuple(chunks)


class PostgresFrozenRagProvider:
    """Read-only exact dense + FTS retrieval with deterministic RRF fusion."""

    def __init__(self) -> None:
        self._model: Any | None = None
        self._model_lock = asyncio.Lock()

    async def prewarm(self) -> None:
        """Load and exercise the embedder outside retrieval latency."""

        if self._model is not None:
            return
        async with self._model_lock:
            if self._model is not None:
                return

            def _load() -> Any:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    APPROVED_EMBEDDING_MODEL,
                    revision=APPROVED_EMBEDDING_REVISION,
                )
                dimension = embedding_dimension(model)
                if dimension != APPROVED_EMBEDDING_DIMENSION:
                    raise ExperimentError(
                        "EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH",
                        f"expected={APPROVED_EMBEDDING_DIMENSION}, actual={dimension}",
                    )
                model.encode(
                    ["research retrieval prewarm"], normalize_embeddings=True
                )
                return model

            try:
                self._model = await asyncio.to_thread(_load)
            except ExperimentError:
                raise
            except Exception as exc:
                raise ExperimentError(
                    "EXPERIMENT_EMBEDDING_PREWARM_FAILED", safe_error_detail(exc)
                ) from exc

    def _validate_embedding_runtime(
        self, manifest: ResearchCorpusManifest
    ) -> None:
        if manifest.embedding_model != APPROVED_EMBEDDING_MODEL:
            raise ExperimentError("EXPERIMENT_EMBEDDING_MODEL_MISMATCH")
        if manifest.embedding_model_revision != APPROVED_EMBEDDING_REVISION:
            raise ExperimentError("EXPERIMENT_EMBEDDING_REVISION_MISMATCH")
        if manifest.embedding_dimension != APPROVED_EMBEDDING_DIMENSION:
            raise ExperimentError("EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH")
        if manifest.normalization_behavior != NORMALIZATION_BEHAVIOR:
            raise ExperimentError("EXPERIMENT_EMBEDDING_NORMALIZATION_MISMATCH")
        installed = importlib.metadata.version("sentence-transformers")
        if (
            manifest.sentence_transformers_version
            != APPROVED_SENTENCE_TRANSFORMERS_VERSION
            or installed != APPROVED_SENTENCE_TRANSFORMERS_VERSION
        ):
            raise ExperimentError(
                "EXPERIMENT_SENTENCE_TRANSFORMERS_VERSION_MISMATCH",
                f"manifest={manifest.sentence_transformers_version}, runtime={installed}",
            )
        runtime_revision = discover_embedding_revision(self._model)
        if manifest.embedding_model_revision != runtime_revision:
            raise ExperimentError(
                "EXPERIMENT_EMBEDDING_REVISION_MISMATCH",
                f"manifest={manifest.embedding_model_revision}, runtime={runtime_revision}",
            )

    async def _embed_query(self, query: str) -> list[float]:
        if self._model is None:
            raise ExperimentError("EXPERIMENT_EMBEDDING_NOT_PREWARMED")

        def _encode() -> list[float]:
            vector = self._model.encode(query, normalize_embeddings=True)
            values = vector.tolist()
            if len(values) != APPROVED_EMBEDDING_DIMENSION:
                raise ExperimentError("EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH")
            return values

        return await asyncio.to_thread(_encode)

    async def retrieve(
        self, query: str, config: ExperimentConfig
    ) -> RetrievalTrace:
        query = query.strip()
        if not query:
            raise ExperimentError("EXPERIMENT_INVALID_QUERY")

        # Prewarming and full manifest validation happen before the measured
        # retrieval. There is deliberately no timeout and no no-RAG fallback.
        await self.prewarm()
        manifest = await verify_research_corpus(
            expected_version=config.corpus_version,
            expected_hash=config.corpus_hash,
        )
        self._validate_embedding_runtime(manifest)

        started = time.perf_counter()
        try:
            vector = await self._embed_query(query)
            vector_literal = "[" + ",".join(str(value) for value in vector) + "]"

            from services.experiment.corpus import _asyncpg_dsn

            conn = await asyncpg.connect(_asyncpg_dsn())
            try:
                async with conn.transaction(readonly=True):
                    dense_rows = await conn.fetch(
                        """
                        SELECT c.chunk_id, c.title, c.content, c.content_hash,
                               c.source_type, c.source_name, c.source_url,
                               c.source_record_id, c.dataset_file, c.dataset_hash,
                               1 - (e.embedding <=> $2::vector) AS cosine_similarity
                        FROM research_knowledge_chunks c
                        JOIN research_chunk_embeddings e
                          ON e.corpus_version = c.corpus_version
                         AND e.chunk_id = c.chunk_id
                        WHERE c.corpus_version = $1
                          AND c.is_dynamic = FALSE
                          AND 1 - (e.embedding <=> $2::vector) >= $3
                        ORDER BY cosine_similarity DESC,
                                 c.content_hash ASC, c.chunk_id::text ASC
                        LIMIT $4
                        """,
                        config.corpus_version,
                        vector_literal,
                        config.rag_threshold,
                        HYBRID_CANDIDATE_LIMIT,
                    )
                    keyword_rows = await conn.fetch(
                        """
                        WITH q AS (
                            SELECT websearch_to_tsquery('simple', $2) AS value
                        ), scored AS (
                            SELECT c.chunk_id, c.title, c.content, c.content_hash,
                                   c.source_type, c.source_name, c.source_url,
                                   c.source_record_id, c.dataset_file, c.dataset_hash,
                                   1 - (e.embedding <=> $3::vector)
                                       AS cosine_similarity,
                                   ts_rank_cd(c.search_vector, q.value)
                                       AS keyword_score
                            FROM research_knowledge_chunks c
                            JOIN research_chunk_embeddings e
                              ON e.corpus_version = c.corpus_version
                             AND e.chunk_id = c.chunk_id
                            CROSS JOIN q
                            WHERE c.corpus_version = $1
                              AND c.is_dynamic = FALSE
                              AND c.search_vector @@ q.value
                        )
                        SELECT * FROM scored
                        WHERE cosine_similarity >= $4
                        ORDER BY keyword_score DESC, content_hash ASC,
                                 chunk_id::text ASC
                        LIMIT $5
                        """,
                        config.corpus_version,
                        query,
                        vector_literal,
                        config.rag_threshold,
                        HYBRID_CANDIDATE_LIMIT,
                    )
            finally:
                await conn.close()
        except ExperimentError:
            raise
        except Exception as exc:
            raise ExperimentError(
                "EXPERIMENT_RAG_RETRIEVAL_FAILED", safe_error_detail(exc)
            ) from exc

        chunks = fuse_rankings(
            dense_rows,
            keyword_rows,
            top_k=config.rag_top_k,
            threshold=config.rag_threshold,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if not chunks:
            raise ExperimentError("EXPERIMENT_RAG_NO_RESULTS")
        return RetrievalTrace(
            query=query,
            expanded_query=None,
            top_k=config.rag_top_k,
            threshold=config.rag_threshold,
            retrieval_latency_ms=latency_ms,
            corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash,
            chunks=chunks,
        )


__all__ = [
    "HYBRID_CANDIDATE_LIMIT",
    "PostgresFrozenRagProvider",
    "RRF_K",
    "ResearchRagProvider",
    "fuse_rankings",
]
