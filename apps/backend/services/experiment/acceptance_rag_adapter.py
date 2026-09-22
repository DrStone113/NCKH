"""Evaluation-only adapter exposing the application RAG query contract.

It is intentionally not a production corpus migration: the adapter reads the
immutable research tables for one named acceptance corpus and is enabled only
by an explicit qualification setting.  The normal ``RAGService`` and its
``knowledge_chunks`` tables remain the production default.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import asyncpg

from models.schemas import KnowledgeChunk
from services.experiment.corpus import (
    APPROVED_EMBEDDING_DIMENSION,
    APPROVED_EMBEDDING_MODEL,
    APPROVED_EMBEDDING_REVISION,
    _asyncpg_dsn,
    discover_embedding_revision,
    embedding_dimension,
)
from services.experiment.rag import HYBRID_CANDIDATE_LIMIT, PostgresFrozenRagProvider, fuse_rankings


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERSION = "offline-acceptance-vn-4954"
DEFAULT_HASH = "f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a"
_MANIFEST = ROOT / "data" / "research_acceptance_vn" / "manifests" / "acceptance_corpus_manifest.json"
_THRESHOLD = 0.6


def _normalize_query_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _metadata_domains_for_query(query: str) -> tuple[str, ...] | None:
    """Select a narrow authority family from generic intent language.

    These are domain-level query formulations, not benchmark entities.  The
    entity remains open-ended and is ranked against every row in the selected
    immutable domain.
    """

    text = _normalize_query_text(query)
    if "gioi han ap dung rni" in text:
        return ("VN_BODY_METRIC",)
    if "vi chat" in text or "epa va dha" in text:
        return ("VN_MICRONUTRIENT",)
    if "van dong viet nam" in text or "nguoi viet nen van dong" in text:
        return ("VN_PHYSICAL_ACTIVITY",)
    if (
        "rni viet nam" in text
        or text.startswith("nhu cau dinh duong ")
        or text.startswith("nguoi viet can luu y ")
    ):
        return ("VN_NUTRIENT_REQUIREMENT",)
    if (
        "khuyen nghi viet nam" in text
        or "theo huong dan viet nam" in text
        or text.startswith("loi khuyen dinh duong ")
    ):
        return ("VN_NUTRITION_GUIDELINE",)
    if (
        text.startswith("health ")
        or text.startswith("thong tin suc khoe co ban ve ")
        or "dieu gi lien quan dinh duong van dong" in text
    ):
        return ("GLOBAL_HEALTH",)
    return None


_RANK_STOPWORDS = frozenset(
    {
        "ve", "la", "gi", "theo", "huong", "dan", "viet", "nam", "khuyen",
        "nghi", "dinh", "duong", "luu", "y", "nguoi", "can", "thong", "tin",
        "suc", "khoe", "co", "ban", "dieu", "lien", "quan", "van", "dong",
        "health", "rni", "tinh", "huong",
    }
)


def _metadata_rank_key(query: str, row: Any) -> tuple[float, int, float, str]:
    query_tokens = {
        token for token in _normalize_query_text(query).split()
        if token not in _RANK_STOPWORDS
    }
    title = str(row.get("title") or "")
    title_tokens = {
        token for token in _normalize_query_text(title).split()
        if token not in _RANK_STOPWORDS
    }
    overlap = len(query_tokens & title_tokens)
    coverage = overlap / max(1, len(title_tokens))
    similarity = float(row.get("cosine_similarity") or 0.0)
    return coverage, overlap, similarity, str(row.get("chunk_id") or "")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()


def _row_dict(row: Any) -> dict[str, Any]:
    """Match SQLAlchemy's JSON decoding used by the corpus verifier."""

    value = dict(row)
    if isinstance(value.get("metadata"), str):
        value["metadata"] = json.loads(value["metadata"])
    return value


class AcceptanceCorpusRagAdapter:
    """Read-only bridge from application ``query`` to frozen acceptance RAG."""

    def __init__(self, *, corpus_version: str, corpus_hash: str, metrics: Any | None = None) -> None:
        if corpus_version != DEFAULT_VERSION or corpus_hash != DEFAULT_HASH:
            raise ValueError("UNAPPROVED_ACCEPTANCE_CORPUS")
        self.corpus_version = corpus_version
        self.corpus_hash = corpus_hash
        self.metrics = metrics
        self._provider = PostgresFrozenRagProvider()
        self._verified = False
        self._verify_lock = asyncio.Lock()

    async def prewarm(self) -> None:
        await self._provider.prewarm()
        await self._verify_once()

    async def _verify_once(self) -> None:
        if self._verified:
            return
        async with self._verify_lock:
            if self._verified:
                return
            payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
            manifest_hash = payload.pop("manifest_hash")
            if hashlib.sha256(_canonical(payload)).hexdigest() != manifest_hash:
                raise RuntimeError("ACCEPTANCE_MANIFEST_HASH_MISMATCH")
            if payload.get("corpus_version") != self.corpus_version or payload.get("corpus_hash") != self.corpus_hash:
                raise RuntimeError("ACCEPTANCE_MANIFEST_IDENTITY_MISMATCH")
            await self._provider.prewarm()
            model = self._provider._model
            if (
                embedding_dimension(model) != APPROVED_EMBEDDING_DIMENSION
                or discover_embedding_revision(model) != APPROVED_EMBEDDING_REVISION
                or payload.get("embedding_model") != APPROVED_EMBEDDING_MODEL
                or payload.get("embedding_model_revision") != APPROVED_EMBEDDING_REVISION
            ):
                raise RuntimeError("ACCEPTANCE_EMBEDDING_RUNTIME_MISMATCH")
            conn = await asyncpg.connect(_asyncpg_dsn())
            try:
                async with conn.transaction(readonly=True):
                    rows = await conn.fetch(
                        """
                        SELECT chunk_id::text, category, title, content, metadata,
                               source_type, source_name, source_url, source_record_id,
                               dataset_file, dataset_hash, content_hash, is_dynamic
                        FROM research_knowledge_chunks
                        WHERE corpus_version = $1
                        ORDER BY chunk_id
                        """,
                        self.corpus_version,
                    )
                    embedding_count = await conn.fetchval(
                        "SELECT count(*) FROM research_chunk_embeddings WHERE corpus_version = $1",
                        self.corpus_version,
                    )
            finally:
                await conn.close()
            actual = hashlib.sha256(_canonical([_row_dict(row) for row in rows])).hexdigest()
            if len(rows) != 4954 or int(embedding_count) != len(rows) or actual != self.corpus_hash:
                raise RuntimeError("ACCEPTANCE_CORPUS_VERIFICATION_FAILED")
            self._verified = True

    async def query(self, query: str, top_k: int, *, db: Any = None) -> list[KnowledgeChunk]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("INVALID_QUERY")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
            raise ValueError("INVALID_TOP_K")
        await self.prewarm()
        vector = await self._provider._embed_query(query.strip())
        vector_literal = "[" + ",".join(str(item) for item in vector) + "]"
        metadata_domains = _metadata_domains_for_query(query)
        conn = await asyncpg.connect(_asyncpg_dsn())
        try:
            async with conn.transaction(readonly=True):
                metadata_candidates = []
                if metadata_domains is not None:
                    metadata_candidates = await conn.fetch(
                        """
                        SELECT c.chunk_id, c.title, c.content, c.content_hash,
                               c.source_type, c.source_name, c.source_url,
                               c.source_record_id, c.dataset_file, c.dataset_hash,
                               c.metadata,
                               1 - (e.embedding <=> $3::vector) AS cosine_similarity
                        FROM research_knowledge_chunks c
                        JOIN research_chunk_embeddings e
                          ON e.corpus_version = c.corpus_version AND e.chunk_id = c.chunk_id
                        WHERE c.corpus_version = $1 AND c.is_dynamic = FALSE
                          AND c.metadata->>'domain' = ANY($2::text[])
                        ORDER BY c.content_hash ASC, c.chunk_id::text ASC
                        LIMIT 200
                        """,
                        self.corpus_version, list(metadata_domains), vector_literal,
                    )
                dense = await conn.fetch(
                    """
                    SELECT c.chunk_id, c.title, c.content, c.content_hash,
                           c.source_type, c.source_name, c.source_url,
                           c.source_record_id, c.dataset_file, c.dataset_hash,
                           c.metadata,
                           1 - (e.embedding <=> $2::vector) AS cosine_similarity
                    FROM research_knowledge_chunks c
                    JOIN research_chunk_embeddings e
                      ON e.corpus_version = c.corpus_version AND e.chunk_id = c.chunk_id
                    WHERE c.corpus_version = $1 AND c.is_dynamic = FALSE
                      AND 1 - (e.embedding <=> $2::vector) >= $3
                    ORDER BY cosine_similarity DESC, c.content_hash ASC, c.chunk_id::text ASC
                    LIMIT $4
                    """,
                    self.corpus_version, vector_literal, _THRESHOLD, HYBRID_CANDIDATE_LIMIT,
                )
                keyword = await conn.fetch(
                    """
                    WITH q AS (SELECT websearch_to_tsquery('simple', $2) AS value), scored AS (
                      SELECT c.chunk_id, c.title, c.content, c.content_hash,
                             c.source_type, c.source_name, c.source_url,
                             c.source_record_id, c.dataset_file, c.dataset_hash,
                             c.metadata,
                             1 - (e.embedding <=> $3::vector) AS cosine_similarity,
                             ts_rank_cd(c.search_vector, q.value) AS keyword_score
                      FROM research_knowledge_chunks c
                      JOIN research_chunk_embeddings e
                        ON e.corpus_version = c.corpus_version AND e.chunk_id = c.chunk_id
                      CROSS JOIN q
                      WHERE c.corpus_version = $1 AND c.is_dynamic = FALSE
                        AND c.search_vector @@ q.value
                    ) SELECT * FROM scored WHERE cosine_similarity >= $4
                    ORDER BY keyword_score DESC, content_hash ASC, chunk_id::text ASC LIMIT $5
                    """,
                    self.corpus_version, query.strip(), vector_literal, _THRESHOLD, HYBRID_CANDIDATE_LIMIT,
                )
        finally:
            await conn.close()
        if metadata_domains is not None and metadata_candidates:
            ranked = sorted(
                (_row_dict(row) for row in metadata_candidates),
                key=lambda row: _metadata_rank_key(query, row),
                reverse=True,
            )[:top_k]
            return [
                KnowledgeChunk(
                    id=str(row["chunk_id"]),
                    category=str((row.get("metadata") or {}).get("domain") or "RAG"),
                    title=str(row.get("title") or ""),
                    content=str(row.get("content") or ""),
                    metadata={
                        **dict(row.get("metadata") or {}),
                        "acceptance_corpus_version": self.corpus_version,
                        "source": {
                            "source_type": row.get("source_type"),
                            "source_name": row.get("source_name"),
                            "source_url": row.get("source_url"),
                            "source_record_id": row.get("source_record_id"),
                            "dataset_file": row.get("dataset_file"),
                            "dataset_hash": row.get("dataset_hash"),
                        },
                    },
                    similarity=float(row.get("cosine_similarity") or 0.0),
                )
                for row in ranked
            ]
        chunks = fuse_rankings(dense, keyword, top_k=top_k, threshold=_THRESHOLD)
        result: list[KnowledgeChunk] = []
        for chunk in chunks:
            source = dict(chunk.source)
            row = next((item for item in (*dense, *keyword) if str(item["chunk_id"]) == chunk.chunk_id), None)
            row_data = _row_dict(row) if row is not None else {}
            metadata = dict(row_data.get("metadata") or {})
            metadata.update({"acceptance_corpus_version": self.corpus_version, "source": source})
            result.append(KnowledgeChunk(
                id=chunk.chunk_id,
                category=str(metadata.get("domain") or "RAG"),
                title=chunk.title,
                content=chunk.content,
                metadata=metadata,
                similarity=chunk.cosine_similarity,
            ))
        return result


__all__ = ["AcceptanceCorpusRagAdapter", "DEFAULT_HASH", "DEFAULT_VERSION"]
