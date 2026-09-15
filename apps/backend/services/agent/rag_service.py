"""``query_rag`` server-side tool and ``RAGService`` for the chatbot agent.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §9.6 (``MemoryService.queryRag`` formal contract).
- Requirements 5.6, 5.8 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract (Requirement 5.6 / 5.8)
--------------------------------
``RAGService.query(query: str, top_k: int) -> list[KnowledgeChunk]``

- ``query`` non-empty, ``top_k > 0``.
- If ``chunk_embeddings`` has no rows → return ``[]`` (Requirement 5.8).
- Embeds ``query`` using ``sentence-transformers`` (lazily loaded — does not
  block startup), runs a cosine-similarity search against ``chunk_embeddings``
  via pgvector, filters out hits below
  :data:`config.settings.rag_similarity_threshold`, sorts by similarity
  descending and truncates to ``top_k``.
- ``len(result) ≤ top_k``, every ``chunk.similarity ≥
  RAG_SIMILARITY_THRESHOLD``.

The tool descriptor :data:`QUERY_RAG_DESCRIPTOR` is exported but **NOT**
auto-registered. ``register_server_tools`` (task 12.1) is responsible for
binding the bare ``RAGService`` instance to a live ``AsyncSession`` provider
before passing a populated descriptor to
:class:`~services.agent.tool_registry.ToolRegistry`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.schemas import KnowledgeChunk
from services.agent.tool_registry import ToolDescriptor

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# JSON Schema (Ollama function calling)
# --------------------------------------------------------------------------- #

QUERY_RAG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Câu truy vấn ngôn ngữ tự nhiên dùng để tìm chunks kiến thức "
                "liên quan trong cơ sở dữ liệu RAG."
            ),
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
            "description": (
                "Số chunk tối đa trả về. Kết quả luôn có "
                "``len(result) ≤ top_k`` và mọi chunk có similarity ≥ "
                "RAG_SIMILARITY_THRESHOLD."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------- #
# RAGService
# --------------------------------------------------------------------------- #


# Reciprocal Rank Fusion constant. 60 is the value from the original RRF paper
# (Cormack et al. 2009) and the de-facto default: large enough that the top few
# ranks stay close together, small enough that rank 1 still clearly beats rank
# 10. Score for a document at rank r in a list is 1 / (k + r).
RRF_K = 60

# Weight applied to each retriever before fusion. Vector search leads because
# it handles paraphrase and intent; keyword search is the corrective signal for
# rare proper nouns, so it gets a smaller but non-trivial share.
VECTOR_WEIGHT = 1.0
KEYWORD_WEIGHT = 0.7

# How many candidates each retriever contributes before fusion. Over-fetching
# matters: a chunk ranked 8th by vector and 2nd by keyword should still win,
# which is impossible if each list is truncated to top_k first.
CANDIDATE_MULTIPLIER = 4


class RAGService:
    """Hybrid RAG retrieval over ``knowledge_chunks``.

    Combines two retrievers and fuses them with Reciprocal Rank Fusion:

    - **Dense** — cosine similarity over ``chunk_embeddings`` (pgvector).
      Strong on paraphrase and intent ("đồ ăn nhiều đạm ít béo").
    - **Sparse** — Postgres full-text search over a generated ``search_vector``
      column. Strong on the exact rare tokens embeddings smear together: dish
      names, exercise names, micronutrient names.

    Dense-only retrieval was the previous behaviour and it silently missed
    keyword-shaped queries. If the ``search_vector`` column is absent (the
    ``002_hybrid_search`` migration has not run yet) the service degrades to
    dense-only rather than failing.

    The embedding model is loaded lazily on first use to avoid blocking
    application startup.
    """

    def __init__(self, *, metrics: Any | None = None) -> None:
        self._model: Any = None  # lazily-loaded SentenceTransformer
        # None = not yet probed; True/False = cached probe result.
        self._keyword_available: bool | None = None
        self._provenance_available: bool | None = None
        self._inference_semaphore = asyncio.Semaphore(
            max(1, settings.rag_inference_concurrency)
        )
        self._embedding_batch_lock = asyncio.Lock()
        self._embedding_pending: list[
            tuple[str, asyncio.Future[list[float]]]
        ] = []
        self._embedding_batch_task: asyncio.Task[None] | None = None
        self.metrics = metrics

    # ----------------------------------------------------------- model loader
    def _get_model(self) -> Any:
        """Load the embedding model on first call. Idempotent."""
        if self._model is None:
            import torch
            num_threads = max(1, settings.rag_cpu_threads)
            with contextlib.suppress(Exception):
                torch.set_num_threads(num_threads)
            from sentence_transformers import SentenceTransformer
            logger.info(
                "Init local embedding model %s (threads=%d)",
                settings.embedding_model,
                num_threads,
            )
            self._model = SentenceTransformer(settings.embedding_model)
        return self._model

    def embed(self, text_input: str) -> list[float]:
        """Encode ``text_input`` to a unit-normalised embedding vector."""
        model = self._get_model()
        embedding = model.encode(text_input).tolist()
        return embedding

    async def _embed_batched(self, query: str) -> list[float]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[float]] = loop.create_future()
        async with self._embedding_batch_lock:
            self._embedding_pending.append((query, future))
            if self._embedding_batch_task is None or self._embedding_batch_task.done():
                self._embedding_batch_task = asyncio.create_task(
                    self._flush_embedding_batches()
                )
        return await future

    async def _flush_embedding_batches(self) -> None:
        while True:
            await asyncio.sleep(0.010)
            async with self._embedding_batch_lock:
                batch = self._embedding_pending[:8]
                del self._embedding_pending[:8]
            if not batch:
                return
            try:
                async with self._inference_semaphore:
                    vectors = await asyncio.to_thread(
                        self._embed_many_sync, [query for query, _ in batch]
                    )
                for (_, future), vector in zip(batch, vectors, strict=True):
                    if not future.done():
                        future.set_result(vector)
            except Exception as exc:
                for _, future in batch:
                    if not future.done():
                        future.set_exception(exc)
            async with self._embedding_batch_lock:
                if not self._embedding_pending:
                    return

    def _embed_many_sync(self, queries: list[str]) -> list[list[float]]:
        if "embed" in self.__dict__:
            return [self.embed(query) for query in queries]
        model = self._get_model()
        encoded = model.encode(
            queries,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in encoded]

    # ------------------------------------------------------------------ query
    async def query(
        self,
        query: str,
        top_k: int,
        *,
        db: AsyncSession,
    ) -> list[KnowledgeChunk]:
        """Return up to ``top_k`` knowledge chunks most similar to ``query``.

        Parameters
        ----------
        query:
            Non-empty natural-language string. Empty / non-string inputs
            raise ``ValueError("INVALID_QUERY")``.
        top_k:
            Strictly positive integer; raises ``ValueError("INVALID_TOP_K")``
            otherwise.
        db:
            Active ``AsyncSession`` provided by the dispatcher / startup
            wiring (passed by keyword to keep the JSON-schema-facing
            arguments clean).

        Returns
        -------
        list[KnowledgeChunk]
            Sorted descending by ``similarity``. ``len(result) ≤ top_k`` and
            every entry satisfies ``similarity >=
            settings.rag_similarity_threshold``. Returns ``[]`` if
            ``chunk_embeddings`` is empty (Requirement 5.8).
        """
        # --- input validation --------------------------------------------------
        if not isinstance(query, str) or not query.strip():
            raise ValueError("INVALID_QUERY")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("INVALID_TOP_K")

        # --- short-circuit when corpus empty (Requirement 5.8) ----------------
        # A SELECT 1 LIMIT 1 is cheaper than running the cosine-distance query
        # against an empty table; it also keeps the embedding model out of the
        # critical path when there is nothing to score against.
        empty_check = await db.execute(
            text("SELECT 1 FROM chunk_embeddings LIMIT 1")
        )
        if empty_check.first() is None:
            logger.debug("chunk_embeddings empty - returning []")
            return []

        # --- lexical-first cascade -------------------------------------------
        candidate_n = max(top_k * CANDIDATE_MULTIPLIER, top_k)
        provenance = await self._has_provenance(db)
        sparse_rows: list[Any] = []
        if await self._has_keyword_index(db):
            sparse_rows = await self._sparse_search(
                query, candidate_n, db=db, provenance=provenance
            )

        if sparse_rows and bool(getattr(sparse_rows[0], "exact_match", False)):
            if self.metrics is not None:
                self.metrics.increment(
                    "retrieval.exact_exit"
                    if settings.backend_cost_mode == "enforce"
                    else "retrieval.shadow_exact_exit"
                )
            if settings.backend_cost_mode == "enforce":
                return [self._to_chunk(sparse_rows[0], 1.0)]

        if self._lexical_is_confident(sparse_rows):
            if self.metrics is not None:
                self.metrics.increment(
                    "retrieval.lexical_exit"
                    if settings.backend_cost_mode == "enforce"
                    else "retrieval.shadow_lexical_exit"
                )
            if settings.backend_cost_mode == "enforce":
                lexical_k = min(top_k, 3)
                chunks = [
                    self._to_chunk(row, self._lexical_similarity(row))
                    for row in sparse_rows
                ]
                return self._deduplicate(chunks, lexical_k)

        if self.metrics is not None:
            self.metrics.increment("retrieval.dense_calls")
        dense_rows = await self._dense_search(
            query, candidate_n, db=db, provenance=provenance
        )

        if not sparse_rows:
            # Dense-only path: preserve the original threshold semantics.
            threshold = float(settings.rag_similarity_threshold)
            chunks = [
                self._to_chunk(row, float(row.similarity))
                for row in dense_rows
                if float(row.similarity) >= threshold
            ]
            chunks.sort(key=lambda c: c.similarity, reverse=True)
            return self._deduplicate(chunks, top_k)

        if self.metrics is not None:
            self.metrics.increment("retrieval.hybrid")
        return self._deduplicate(self._fuse(dense_rows, sparse_rows, top_k), top_k)

    # ------------------------------------------------------------ retrievers
    async def _dense_search(
        self, query: str, limit: int, *, db: AsyncSession, provenance: bool = False
    ) -> list[Any]:
        """Cosine-similarity search over pgvector.

        No threshold filter is applied here — fusion needs the full ranked
        candidate list, and filtering a chunk out at this stage would hide it
        from the keyword retriever's vote too.
        """
        query_vec = await self._embed_batched(query)
        # pgvector accepts the textual ``[v1,v2,...]`` representation.
        query_vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

        sql = text(
            f"""
            SELECT kc.id, kc.category, kc.title, kc.content, kc.metadata,
                   {self._provenance_select(provenance)},
                   1 - (ce.embedding <=> CAST(:query_vec AS vector)) AS similarity
            FROM chunk_embeddings ce
            JOIN knowledge_chunks kc ON kc.id = ce.chunk_id
            ORDER BY ce.embedding <=> CAST(:query_vec AS vector)
            LIMIT :limit
            """
        )
        result = await db.execute(sql, {"query_vec": query_vec_str, "limit": limit})
        return list(result.fetchall())

    async def _sparse_search(
        self, query: str, limit: int, *, db: AsyncSession, provenance: bool = False
    ) -> list[Any]:
        """Full-text search over the generated ``search_vector`` column.

        ``websearch_to_tsquery`` is used because it never raises on malformed
        input — a user typing ``"giảm cân & (protein"`` would make
        ``to_tsquery`` throw a syntax error mid-request.
        """
        sql = text(
            f"""
            SELECT kc.id, kc.category, kc.title, kc.content, kc.metadata,
                   {self._provenance_select(provenance)},
                   ts_rank(kc.search_vector, q) AS rank,
                   (
                       lower(btrim(kc.title)) = lower(btrim(:query))
                       OR kc.metadata->>'canonical_id' = :query
                   ) AS exact_match
            FROM knowledge_chunks kc,
                 websearch_to_tsquery('simple', :query) AS q
            WHERE kc.search_vector @@ q
               OR lower(btrim(kc.title)) = lower(btrim(:query))
               OR kc.metadata->>'canonical_id' = :query
            ORDER BY exact_match DESC, rank DESC
            LIMIT :limit
            """
        )
        try:
            result = await db.execute(sql, {"query": query, "limit": limit})
            return list(result.fetchall())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Keyword search failed, falling back to dense-only: %s", exc)
            await db.rollback()
            self._keyword_available = False
            return []

    @staticmethod
    def _lexical_similarity(row: Any) -> float:
        rank = max(0.0, float(getattr(row, "rank", 0.0) or 0.0))
        return rank / (rank + 0.10) if rank else float(settings.rag_similarity_threshold)

    @staticmethod
    def _lexical_is_confident(rows: list[Any]) -> bool:
        if not rows:
            return False
        first = float(getattr(rows[0], "rank", 0.0) or 0.0)
        second = float(getattr(rows[1], "rank", 0.0) or 0.0) if len(rows) > 1 else 0.0
        if first < settings.rag_lexical_confidence_threshold:
            return False
        return second <= 0.0 or first / second >= settings.rag_lexical_margin_ratio

    @classmethod
    def _deduplicate(
        cls, chunks: list[KnowledgeChunk], top_k: int
    ) -> list[KnowledgeChunk]:
        """MMR-style near-duplicate suppression without another embedding call."""

        selected: list[KnowledgeChunk] = []
        selected_terms: list[set[str]] = []
        for chunk in chunks:
            terms = cls._terms(f"{chunk.title} {chunk.content}")
            if any(cls._jaccard(terms, prior) >= 0.82 for prior in selected_terms):
                continue
            selected.append(chunk)
            selected_terms.append(terms)
            if len(selected) >= top_k:
                break
        return selected

    @staticmethod
    def _terms(value: str) -> set[str]:
        decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
        folded = "".join(
            char for char in decomposed if unicodedata.category(char) != "Mn"
        )
        return set(re.findall(r"[a-z0-9]{2,}", folded))

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 1.0

    async def _has_column(self, db: AsyncSession, column: str) -> bool:
        """Return whether ``knowledge_chunks`` has ``column``."""
        try:
            result = await db.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'knowledge_chunks'
                      AND column_name = :column
                    """
                ),
                {"column": column},
            )
            return result.first() is not None
        except Exception:  # pragma: no cover - defensive
            return False

    async def _has_keyword_index(self, db: AsyncSession) -> bool:
        """Probe once whether the 002 migration created ``search_vector``."""
        if self._keyword_available is not None:
            return self._keyword_available
        self._keyword_available = await self._has_column(db, "search_vector")
        if not self._keyword_available:
            logger.info(
                "knowledge_chunks.search_vector missing - hybrid search disabled "
                "(run migration 002_hybrid_search)"
            )
        return self._keyword_available

    async def _has_provenance(self, db: AsyncSession) -> bool:
        """Probe once whether the 003 migration added ``source_url``.

        Provenance columns only exist after web-knowledge ingestion is enabled.
        Selecting a missing column would fail the whole retrieval, so the
        column list is built from this probe rather than assumed.
        """
        if self._provenance_available is not None:
            return self._provenance_available
        self._provenance_available = await self._has_column(db, "source_url")
        return self._provenance_available

    @staticmethod
    def _provenance_select(enabled: bool) -> str:
        """SQL fragment adding provenance columns when they exist."""
        if not enabled:
            return "NULL AS source_url, NULL AS source_tier"
        return "kc.source_url, kc.source_tier"

    # ----------------------------------------------------------------- fusion
    def _fuse(
        self, dense_rows: list[Any], sparse_rows: list[Any], top_k: int
    ) -> list[KnowledgeChunk]:
        """Merge two ranked lists with weighted Reciprocal Rank Fusion.

        RRF is used rather than score normalisation because cosine similarity
        and ``ts_rank`` live on incomparable scales; ranks are the only signal
        the two retrievers share. A chunk found by *both* retrievers
        accumulates both scores and therefore outranks a chunk that only one
        of them liked — which is exactly the desired behaviour.
        """
        scores: dict[str, float] = {}
        rows_by_id: dict[str, Any] = {}
        dense_similarity: dict[str, float] = {}

        for rank, row in enumerate(dense_rows, start=1):
            key = str(row.id)
            rows_by_id[key] = row
            dense_similarity[key] = float(row.similarity)
            scores[key] = scores.get(key, 0.0) + VECTOR_WEIGHT / (RRF_K + rank)

        for rank, row in enumerate(sparse_rows, start=1):
            key = str(row.id)
            rows_by_id.setdefault(key, row)
            scores[key] = scores.get(key, 0.0) + KEYWORD_WEIGHT / (RRF_K + rank)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

        chunks: list[KnowledgeChunk] = []
        for key, _score in ranked:
            row = rows_by_id[key]
            # Report the dense cosine similarity when known so downstream
            # consumers keep a meaningful, comparable number. Keyword-only hits
            # get the configured threshold as a floor — they earned their place
            # on lexical evidence, not on cosine distance.
            similarity = dense_similarity.get(
                key, float(settings.rag_similarity_threshold)
            )
            chunks.append(self._to_chunk(row, similarity))
        return chunks

    @staticmethod
    def _to_chunk(row: Any, similarity: float) -> KnowledgeChunk:
        # Provenance is folded into ``metadata`` so the prompt builder and any
        # downstream consumer can cite a source without knowing whether it came
        # from a dedicated column or from the JSON blob.
        metadata = dict(row.metadata or {})
        source_url = getattr(row, "source_url", None)
        if source_url:
            metadata["source_url"] = source_url
        source_tier = getattr(row, "source_tier", None)
        if source_tier is not None:
            metadata["source_tier"] = source_tier
        return KnowledgeChunk(
            id=str(row.id),
            category=row.category,
            title=row.title,
            content=row.content,
            metadata=metadata,
            similarity=similarity,
        )


# --------------------------------------------------------------------------- #
# Module-level descriptor (NOT auto-registered)
# --------------------------------------------------------------------------- #

QUERY_RAG_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="query_rag",
    description=(
        "Tìm các knowledge chunks gần nhất với câu truy vấn dùng cosine "
        "similarity trên pgvector. Trả về danh sách (đã lọc theo "
        "RAG_SIMILARITY_THRESHOLD và sắp xếp giảm dần theo similarity). "
        "Trả về [] nếu chunk_embeddings rỗng."
    ),
    parameters_schema=QUERY_RAG_SCHEMA,
    side="server",
    fn=None,  # Bound by register_server_tools (task 12.1) with a RAGService + AsyncSession.
    idempotent=True,
)


__all__ = [
    "QUERY_RAG_DESCRIPTOR",
    "QUERY_RAG_SCHEMA",
    "RAGService",
]
