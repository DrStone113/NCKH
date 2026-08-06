"""Persist retrieved web knowledge into the RAG corpus.

The point of writing search results back into ``knowledge_chunks`` is that the
bot gets cheaper and faster the longer it runs: the second person to ask about
creatine loading is answered from pgvector in milliseconds instead of two
network round-trips. The corpus grows toward the questions users actually ask,
rather than toward whatever the initial dataset happened to contain.

Safety properties this module is responsible for
------------------------------------------------
- **Provenance is mandatory.** Nothing lands without ``source_url``,
  ``source_tier`` and ``fetched_at``. A nutrition figure with no citation is
  worse than no figure at all in a research context.
- **Idempotent.** ``source_url`` carries a partial unique index and inserts use
  ``ON CONFLICT DO NOTHING``, so re-asking a question does not duplicate rows
  or re-run the embedding model.
- **Never fatal.** Ingestion runs after the user already has their answer.
  Every failure is logged and swallowed; a full disk must not surface as a chat
  error.
- **Tier-gated.** Only tier 1 and 2 sources are persisted. Tier 3 (Vietnamese
  commercial health publishers) is good enough to quote once, with the URL
  visible, but not good enough to become permanent "knowledge" the bot repeats
  without attribution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from services.agent.web_search import WebResult

logger = logging.getLogger(__name__)

# Results at or below this tier get persisted. See module docstring.
MAX_PERSISTED_TIER = 2

# Below this length a snippet is a headline, not knowledge worth embedding.
MIN_CONTENT_CHARS = 120

_CATEGORY_BY_SOURCE = {
    "pubmed": "medical_literature",
    "web": "web_health",
}


class KnowledgeIngestService:
    """Writes :class:`WebResult` objects into ``knowledge_chunks``."""

    def __init__(self, db_session: Any, rag_service: Any | None = None) -> None:
        self._session = db_session
        self._rag = rag_service

    async def ingest(self, results: list[WebResult]) -> int:
        """Persist eligible ``results``. Returns the number of new rows.

        Safe to call with an empty list, with duplicates, or with no RAG
        service wired in (the chunk is stored without an embedding and simply
        won't be retrievable by vector search until backfilled — keyword search
        still finds it).
        """
        if not results or self._session is None:
            return 0

        inserted = 0
        for result in results:
            if not self._is_eligible(result):
                continue
            try:
                if await self._insert(result):
                    inserted += 1
            except Exception as exc:  # noqa: BLE001 - best effort by design
                logger.warning(
                    "Knowledge ingest failed for %s: %s", result.url[:80], exc
                )
                try:
                    await self._session.rollback()
                except Exception:  # pragma: no cover - defensive
                    pass

        if inserted:
            try:
                await self._session.commit()
                logger.info("Ingested %d new knowledge chunk(s) from web", inserted)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Knowledge ingest commit failed: %s", exc)
                await self._session.rollback()
                return 0
        return inserted

    # ------------------------------------------------------------- internals
    @staticmethod
    def _is_eligible(result: WebResult) -> bool:
        if not isinstance(result, WebResult):
            return False
        if not result.url or not result.title:
            return False
        if result.tier > MAX_PERSISTED_TIER:
            return False
        if len(result.snippet or "") < MIN_CONTENT_CHARS:
            return False
        return result.source in _CATEGORY_BY_SOURCE

    async def _insert(self, result: WebResult) -> bool:
        """Insert one chunk plus its embedding. Returns False if it existed."""
        chunk_id = str(uuid4())
        category = _CATEGORY_BY_SOURCE[result.source]
        metadata: dict[str, Any] = dict(result.metadata or {})
        if result.published:
            metadata["published"] = result.published
        metadata["retrieved_by"] = "web_search"

        import json

        row = await self._session.execute(
            text(
                """
                INSERT INTO knowledge_chunks
                    (id, category, title, content, metadata,
                     source_url, source_tier, fetched_at)
                VALUES
                    (:id, :category, :title, :content, CAST(:metadata AS jsonb),
                     :source_url, :source_tier, :fetched_at)
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL
                DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": chunk_id,
                "category": category,
                "title": result.title[:500],
                "content": result.snippet,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "source_url": result.url,
                "source_tier": result.tier,
                "fetched_at": datetime.now(timezone.utc),
            },
        )
        if row.first() is None:
            # Already present — not an error, just nothing new to embed.
            return False

        await self._embed(chunk_id, result)
        return True

    async def _embed(self, chunk_id: str, result: WebResult) -> None:
        """Compute and store the embedding for a freshly inserted chunk."""
        if self._rag is None:
            logger.debug("No RAG service wired; chunk %s stored unembedded", chunk_id)
            return
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            # Embedding the title alongside the body matters: the title carries
            # the topic, the body carries the detail, and queries can match
            # either.
            payload = f"{result.title}. {result.snippet}"
            vector = await loop.run_in_executor(None, self._rag.embed, payload)
            vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
            await self._session.execute(
                text(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding)
                    VALUES (:chunk_id, CAST(:embedding AS vector))
                    ON CONFLICT (chunk_id) DO NOTHING
                    """
                ),
                {"chunk_id": chunk_id, "embedding": vector_literal},
            )
        except Exception as exc:  # noqa: BLE001 - chunk is still usable via FTS
            logger.warning("Embedding failed for chunk %s: %s", chunk_id, exc)


__all__ = ["KnowledgeIngestService", "MAX_PERSISTED_TIER", "MIN_CONTENT_CHARS"]
