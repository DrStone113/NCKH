"""MemoryService — long-term memory for the agent (rolling summary + facts).

Implements the core surface of §4.5 of
``backend/.kiro/specs/chatbot-redesign/design.md`` (task 5.1) and the context
loader / RAG delegation of §8.1 / §9.6 (task 5.3):

- ``getRollingSummary(session_id)`` / ``saveRollingSummary(session_id, summary)``
  read / upsert ``chat_session_memory.rolling_summary`` for one session.
- ``getPinnedFacts(session_id)`` returns ``user_facts`` rows belonging to the
  user that owns the session, filtered to ``status='confirmed'``.
- ``proposeFact(session_id, fact_text, category, source_msg_id)`` inserts a new
  ``user_facts`` row with ``status='pending'`` for that user.
- ``confirmFact(fact_id)`` / ``rejectFact(fact_id)`` flip the ``status`` column.
- ``queryRag(query, top_k)`` delegates to :class:`RAGService` (task 4.8). When
  no ``RAGService`` is wired in (e.g. unit tests, embeddings disabled) it
  returns ``[]`` so callers can compose without a None-check.
- ``loadContext(session_id, user_text)`` aggregates the four pieces the agent
  orchestrator needs to build the system prompt: the last N raw turns, the
  rolling summary, the confirmed pinned facts, and the top-k RAG chunks
  relevant to ``user_text``.
- ``updateRollingSummary(session_id, llm_client)`` (task 5.2) re-summarises
  the old turns once the session exceeds :data:`config.settings.summary_threshold`
  and proposes new pinned facts via the LLM.

Validates Requirements 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 7.5.

Schema deviation note
---------------------
Migration ``001_chatbot_redesign.sql`` creates ``user_facts`` keyed by
``user_id`` (a per-user list of preferences / allergies / goals), not by
``session_id``. To keep the design-level signature
``getPinnedFacts(session_id)`` while staying faithful to the schema, this
service joins through ``chat_sessions`` to resolve the owner ``user_id``
before reading ``user_facts``. The same join is used by ``proposeFact``.
``confirmFact`` and ``rejectFact`` operate on a ``fact_id`` directly because
moderation is per-fact rather than per-session.

Implementation notes
--------------------
- All SQL uses :func:`sqlalchemy.text` with bound parameters; no string
  interpolation of caller input.
- The service does NOT commit on its own. The caller (the orchestrator or a
  FastAPI dependency such as :func:`db.database.get_db`) controls the
  transaction boundary.
- Methods are ``async`` so they compose with the existing ``AsyncSession``
  used everywhere else in the backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.agent.scope_guard import SCOPE_GUARD_HISTORY_MARKERS
from db.db_status import is_db_offline, mark_db_offline
from models.schemas import (
    ChatTurn,
    Fact,
    KnowledgeChunk,
    FactCategoryLiteral,
    FactStatusLiteral,
    ChatRoleLiteral,
)

if TYPE_CHECKING:  # pragma: no cover - import only used for type hints
    from services.agent.rag_service import RAGService


class _LLMChatProtocol(Protocol):
    """Minimal ``LLMClient`` surface used by :meth:`updateRollingSummary`.

    Declared as a protocol so unit tests can pass any object exposing
    ``async def chat(messages, tools=None, stream=False)`` without importing
    the concrete client. Mirrors
    :meth:`services.agent.llm_client.LLMClient.chat`.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = ...,
        stream: bool = ...,
    ) -> Any:  # pragma: no cover - protocol definition
        ...

logger = logging.getLogger(__name__)


@dataclass
class Context:
    """Bundle of memory pieces consumed by ``buildSystemPrompt``.

    Mirrors the four arguments the orchestrator threads into the system
    prompt (``design.md`` §8.1):

    - ``history``: the last N raw chat turns from ``chat_messages``.
    - ``rolling_summary``: the cumulative summary kept in
      ``chat_session_memory.rolling_summary``.
    - ``pinned_facts``: confirmed ``user_facts`` rows for the owning user.
    - ``rag_chunks``: top-k knowledge chunks retrieved for the current
      ``user_text``.

    Using a dataclass (rather than a ``BaseModel``) keeps the type lightweight
    and avoids the validation overhead — every field is already produced by a
    typed accessor. Defaults are empty so partial construction in tests does
    not require passing every argument.
    """

    history: list[ChatTurn] = field(default_factory=list)
    rolling_summary: str = ""
    pinned_facts: list[Fact] = field(default_factory=list)
    rag_chunks: list[KnowledgeChunk] = field(default_factory=list)
    relevant_history: list[ChatTurn] = field(default_factory=list)
    rag_requested: bool = False
    rag_result_status: str = "NOT_REQUESTED"


# Categories accepted on ``proposeFact``. Matches the design.md §6 description
# of pinned facts ("preference / allergy / goal / constraint"). ``other`` is
# kept as an escape hatch so the LLM can still propose facts that don't slot
# cleanly into one of the canonical buckets — the moderation step
# (``confirmFact`` / ``rejectFact``) is the gate that protects the prompt.
_ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"preference", "allergy", "goal", "constraint", "other"}
)


class MemoryService:
    """Persistence surface for rolling summaries and pinned facts.

    Parameters
    ----------
    db_session:
        Active SQLAlchemy :class:`AsyncSession`. The service holds a reference
        to one session for its lifetime; callers wanting transaction
        isolation should construct a fresh ``MemoryService`` per request /
        per turn (matching the ``get_db`` dependency pattern).
    rag_service:
        Optional :class:`RAGService` used by :meth:`queryRag` and
        :meth:`loadContext`. When ``None`` the RAG retrieval becomes a no-op
        that returns an empty list — useful for unit tests, environments
        where the embedding model is not available, or while the RAG corpus
        is being populated.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        rag_service: "RAGService | None" = None,
    ) -> None:
        self._session = db_session
        self._rag_service = rag_service
        # Process-local watermark prevents the same old transcript from
        # buying two background completions after every user turn. It carries
        # no content and is owner/session scoped.
        self._last_consolidated_turn_count: dict[str, int] = {}

    # ------------------------------------------------------------------ summary
    async def getRollingSummary(self, session_id: str) -> str:
        """Return the rolling summary for ``session_id``.

        Returns an empty string when the session has no summary row yet —
        this matches the ``DEFAULT ''`` of the ``rolling_summary`` column and
        lets callers concatenate the result into a system prompt without a
        ``None`` check.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if is_db_offline():
            return ""

        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT rolling_summary
                    FROM chat_session_memory
                    WHERE session_id = :sid
                    """
                ),
                {"sid": session_id},
            )
            row = result.first()
            if row is None:
                return ""
            return row[0] or ""
        except Exception as e:
            mark_db_offline(60.0)
            logger.warning("Database unavailable in getRollingSummary: %s", e)
            return ""

    async def saveRollingSummary(self, session_id: str, summary: str) -> None:
        """Upsert ``summary`` for ``session_id``.

        Uses ``INSERT ... ON CONFLICT (session_id) DO UPDATE`` so the call is
        safe whether or not a row already exists. The ``updated_at`` column
        is bumped on every write.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if not isinstance(summary, str):
            raise ValueError("INVALID_SUMMARY")

        try:
            await self._session.execute(
                text(
                    """
                    INSERT INTO chat_session_memory (session_id, rolling_summary, updated_at)
                    VALUES (:sid, :summary, NOW())
                    ON CONFLICT (session_id) DO UPDATE
                        SET rolling_summary = EXCLUDED.rolling_summary,
                            updated_at      = NOW()
                    """
                ),
                {"sid": session_id, "summary": summary},
            )
        except Exception as e:
            logger.warning("Database unavailable in saveRollingSummary: %s", e)

    # -------------------------------------------------------------------- facts
    async def getPinnedFacts(self, session_id: str) -> list[Fact]:
        """Return confirmed pinned facts for the user that owns ``session_id``.

        Joins ``chat_sessions`` to resolve ``user_id`` from the session id and
        returns only rows with ``status = 'confirmed'`` (Requirement 5.4).

        Returns an empty list when the session does not exist or the user has
        no confirmed facts yet.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if is_db_offline():
            return []

        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT
                        f.id,
                        f.user_id,
                        f.category,
                        f.fact,
                        f.status,
                        f.source_msg_id,
                        f.created_at
                    FROM user_facts AS f
                    JOIN chat_sessions AS s ON s.user_id = f.user_id
                    WHERE s.id = :sid
                      AND f.status = 'confirmed'
                    ORDER BY f.created_at ASC
                    """
                ),
                {"sid": session_id},
            )
            rows = result.all()
            return [self._row_to_fact(row) for row in rows]
        except Exception as e:
            mark_db_offline(60.0)
            logger.warning("Database unavailable in getPinnedFacts: %s", e)
            return []

    async def proposeFact(
        self,
        session_id: str,
        fact_text: str,
        category: str,
        source_msg_id: str | None,
        status: str = "pending",
    ) -> str:
        """Insert a new ``user_facts`` row.

        ``status`` defaults to ``'pending'`` (the original behaviour), but
        :meth:`updateRollingSummary` passes ``'confirmed'`` for high-confidence
        facts. Rationale: ``getPinnedFacts`` only reads confirmed rows, and no
        moderation UI ever existed, so every extracted fact used to sit in
        ``pending`` forever — the bot extracted memories it could never read
        back, which is why it kept re-asking things the user had already said.

        Resolves the owning ``user_id`` from ``chat_sessions`` so the fact is
        attached to the correct user rather than the session. Returns the
        UUID string of the freshly inserted row, suitable as a tool result.

        Parameters
        ----------
        session_id:
            Session that the LLM was reasoning about when it proposed the
            fact. Used only to look up the owning ``user_id``.
        fact_text:
            Natural-language fact, e.g. ``"dị ứng hải sản"``.
        category:
            One of ``{"preference", "allergy", "goal", "constraint", "other"}``.
        source_msg_id:
            Optional ``chat_messages.id`` that triggered the proposal. Stored
            for later auditing; ``NULL`` is acceptable when the proposal does
            not correspond to a single message (e.g. it was distilled from
            the rolling summary update).

        Raises
        ------
        ValueError
            ``"INVALID_SESSION_ID"``, ``"INVALID_FACT_TEXT"``,
            ``"INVALID_CATEGORY"``, or ``"SESSION_NOT_FOUND"`` when the
            session id does not exist.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if not isinstance(fact_text, str) or not fact_text.strip():
            raise ValueError("INVALID_FACT_TEXT")
        if not isinstance(category, str) or category not in _ALLOWED_CATEGORIES:
            raise ValueError("INVALID_CATEGORY")
        if source_msg_id is not None and (
            not isinstance(source_msg_id, str) or not source_msg_id
        ):
            raise ValueError("INVALID_SOURCE_MSG_ID")
        if status not in {"pending", "confirmed"}:
            raise ValueError("INVALID_STATUS")

        owner = await self._session.execute(
            text("SELECT user_id FROM chat_sessions WHERE id = :sid"),
            {"sid": session_id},
        )
        owner_row = owner.first()
        if owner_row is None:
            raise ValueError("SESSION_NOT_FOUND")
        user_id = owner_row[0]

        fact_id = str(uuid4())
        await self._session.execute(
            text(
                """
                INSERT INTO user_facts (
                    id, user_id, category, fact, status, source_msg_id
                )
                VALUES (
                    :id, :user_id, :category, :fact, :status, :source
                )
                """
            ),
            {
                "id": fact_id,
                "user_id": user_id,
                "category": category,
                "fact": fact_text.strip(),
                "status": status,
                "source": source_msg_id,
            },
        )
        logger.info(
            "proposeFact inserted fact id=%s user=%s category=%s status=%s",
            fact_id,
            user_id,
            category,
            status,
        )
        return fact_id

    async def confirmFact(self, fact_id: str) -> None:
        """Flip ``user_facts.status`` to ``'confirmed'`` for ``fact_id``."""
        await self._set_fact_status(fact_id, status="confirmed")

    async def rejectFact(self, fact_id: str) -> None:
        """Flip ``user_facts.status`` to ``'rejected'`` for ``fact_id``."""
        await self._set_fact_status(fact_id, status="rejected")

    # ------------------------------------------------------------ summarisation
    async def updateRollingSummary(
        self,
        session_id: str,
        llm_client: _LLMChatProtocol,
    ) -> None:
        """Cô đặc các turn cũ vào ``rolling_summary`` và đề xuất pinned facts.

        Triển khai pseudocode §8.4 của ``design.md`` (task 5.2):

        1. Đếm số turn trong ``chat_messages`` cho ``session_id``. Nếu không
           vượt :data:`config.settings.summary_threshold` → return ngay (không
           có gì để cô đặc).
        2. Load các turn cũ (tất cả trừ :data:`config.settings.keep_raw_turns`
           turn gần nhất) cùng với rolling summary hiện tại.
        3. Gọi ``llm_client.chat(buildSummaryPrompt(turns_text, prior_summary))``
           với ``stream=False`` và ``tools=None``. Lấy ``full_text`` làm
           summary mới và lưu qua :meth:`saveRollingSummary`.
        4. Gọi ``llm_client.chat(buildFactExtractionPrompt(turns_text))`` để
           trích ``candidate_facts`` (một mảng JSON ``[{category, fact}, ...]``).
           Với mỗi fact chưa tồn tại (so sánh case-insensitive với toàn bộ
           ``user_facts`` của user) → :meth:`proposeFact` với
           ``status='pending'``.

        Best-effort. Mọi exception từ LLM (``LLMUnavailableError``,
        ``GarbledOutputError``, JSON parse fail, …) đều được nuốt và log
        warning để cập nhật memory không làm hỏng turn chat đang chạy
        (Requirement 5.2 / 5.3).

        Parameters
        ----------
        session_id:
            Session cần cập nhật rolling summary.
        llm_client:
            Đối tượng có method ``async def chat(messages, tools=None,
            stream=False)`` (xem
            :class:`services.agent.llm_client.LLMClient`). Tools không cần
            khi gọi summarisation, chỉ cần text completion.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if llm_client is None:
            raise ValueError("INVALID_LLM_CLIENT")

        threshold = settings.summary_threshold
        keep = settings.keep_raw_turns
        # Defensive: a misconfigured ``keep_raw_turns >= summary_threshold``
        # would cause us to load zero turns. Bail out cleanly so a config
        # mistake doesn't silently kill summarisation.
        if keep < 0 or threshold <= keep:
            logger.warning(
                "updateRollingSummary skipped: invalid config "
                "(summary_threshold=%d, keep_raw_turns=%d)",
                threshold,
                keep,
            )
            return

        total = await self._count_turns(session_id)
        if total <= threshold:
            logger.debug(
                "updateRollingSummary skipped: total=%d ≤ threshold=%d",
                total,
                threshold,
            )
            return

        previous_total = self._last_consolidated_turn_count.get(session_id)
        if (
            previous_total is not None
            and total - previous_total < settings.summary_min_new_turns
        ):
            logger.debug(
                "updateRollingSummary batched: new_turns=%d required=%d",
                total - previous_total,
                settings.summary_min_new_turns,
            )
            return
        # Reserve the batch before paid work begins. Concurrent background
        # tasks and repeated provider failures therefore cannot create a cost
        # storm; a later batch may try again after enough genuinely new turns.
        self._last_consolidated_turn_count[session_id] = total

        old_count = total - keep
        old_turns = await self._load_oldest_turns(session_id, limit=old_count)
        old_turns = [
            turn
            for turn in old_turns
            if turn.tool_name not in SCOPE_GUARD_HISTORY_MARKERS
        ]
        if not old_turns:
            return

        prior_summary = await self.getRollingSummary(session_id)
        turns_text = _format_turns_for_prompt(old_turns)

        # 1) Re-summarise. If this fails, we still attempt fact extraction
        #    on the same turns since the two LLM calls are independent.
        new_summary: str | None = None
        try:
            summary_messages = buildSummaryPrompt(turns_text, prior_summary)
            response = await llm_client.chat(
                summary_messages,
                tools=None,
                stream=False,
                max_tokens=settings.llm_memory_summary_max_output_tokens,
            )
            new_summary = (getattr(response, "full_text", "") or "").strip()
        except Exception as exc:  # noqa: BLE001 - best-effort summarisation
            logger.warning(
                "updateRollingSummary: summary LLM call failed for session=%s: %s",
                session_id,
                exc,
            )

        if new_summary:
            try:
                await self.saveRollingSummary(session_id, new_summary)
            except Exception as exc:  # noqa: BLE001 - best-effort
                logger.warning(
                    "updateRollingSummary: saveRollingSummary failed "
                    "for session=%s: %s",
                    session_id,
                    exc,
                )

        # 2) Extract candidate facts from the same turns and propose those
        #    that the user does not already have. Failures here are also
        #    best-effort — the rolling summary update is the primary goal.
        try:
            existing_facts = await self.getPinnedFacts(session_id)
            fact_messages = buildFactExtractionPrompt(turns_text, existing_facts=existing_facts)
            response = await llm_client.chat(
                fact_messages,
                tools=None,
                stream=False,
                max_tokens=settings.llm_memory_fact_max_output_tokens,
            )
            raw_text = getattr(response, "full_text", "") or ""
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning(
                "updateRollingSummary: fact extraction LLM call failed "
                "for session=%s: %s",
                session_id,
                exc,
            )
            return

        candidates = _parse_fact_candidates(raw_text)
        if not candidates:
            return

        existing_texts = {f.fact.strip().casefold() for f in existing_facts}

        for cand in candidates:
            action = cand.get("action", "add")
            fact_text = cand.get("fact", "").strip()
            target_fact = cand.get("target_fact", "").strip()
            category = cand.get("category", "").strip().lower()
            if category not in _ALLOWED_CATEGORIES:
                category = "other"

            if action == "add":
                if not fact_text:
                    continue
                normalised = fact_text.casefold()
                if normalised in existing_texts:
                    continue
                status = self._fact_status_for(cand, category)
                try:
                    await self.proposeFact(
                        session_id=session_id,
                        fact_text=fact_text,
                        category=category,
                        source_msg_id=None,
                        status=status,
                    )
                    existing_texts.add(normalised)
                except ValueError as exc:
                    logger.debug(
                        "updateRollingSummary: skipping invalid fact candidate "
                        "(%s): %r",
                        exc,
                        cand,
                    )

            elif action == "update":
                if not fact_text or not target_fact:
                    continue
                target_normalised = target_fact.casefold()
                matching_fact = None
                for f in existing_facts:
                    f_text = f.fact.strip().casefold()
                    if f_text == target_normalised or target_normalised in f_text or f_text in target_normalised:
                        matching_fact = f
                        break
                
                if matching_fact:
                    try:
                        await self._set_fact_status(matching_fact.id, status="rejected")
                        existing_texts.discard(matching_fact.fact.strip().casefold())
                        existing_facts.remove(matching_fact)
                    except Exception as exc:
                        logger.warning("Failed to deactivate fact %s: %s", matching_fact.id, exc)

                normalised = fact_text.casefold()
                if normalised not in existing_texts:
                    status = self._fact_status_for(cand, category)
                    try:
                        await self.proposeFact(
                            session_id=session_id,
                            fact_text=fact_text,
                            category=category,
                            source_msg_id=None,
                            status=status,
                        )
                        existing_texts.add(normalised)
                    except ValueError as exc:
                        logger.debug(
                            "updateRollingSummary: skipping invalid fact candidate "
                            "(%s): %r",
                            exc,
                            cand,
                        )

            elif action == "remove":
                if not target_fact:
                    continue
                target_normalised = target_fact.casefold()
                matching_fact = None
                for f in existing_facts:
                    f_text = f.fact.strip().casefold()
                    if f_text == target_normalised or target_normalised in f_text or f_text in target_normalised:
                        matching_fact = f
                        break
                
                if matching_fact:
                    try:
                        await self._set_fact_status(matching_fact.id, status="rejected")
                        existing_texts.discard(matching_fact.fact.strip().casefold())
                        existing_facts.remove(matching_fact)
                    except Exception as exc:
                        logger.warning("Failed to deactivate fact %s: %s", matching_fact.id, exc)

    @staticmethod
    def _fact_status_for(candidate: dict[str, str], category: str) -> str:
        """Decide whether an extracted fact goes straight into the prompt.

        Auto-confirmation is deliberately narrow. A fact only skips the
        (nonexistent) moderation queue when the model marked it ``high``
        confidence *and* it falls in a category the user states about
        themselves in plain words — allergies, goals, preferences, physical
        constraints. Everything else stays ``pending``: it is recorded for
        later review but never injected into the system prompt, so a
        hallucinated "fact" cannot quietly poison every future turn.
        """
        auto_confirm_categories = {"allergy", "goal", "preference", "constraint"}
        if (
            candidate.get("confidence") == "high"
            and category in auto_confirm_categories
        ):
            return "confirmed"
        return "pending"

    async def _set_fact_status(self, fact_id: str, *, status: str) -> None:
        if not isinstance(fact_id, str) or not fact_id:
            raise ValueError("INVALID_FACT_ID")
        # ``status`` is internal-only (set by ``confirmFact`` / ``rejectFact``)
        # and never accepts caller input, but we still defend the check
        # constraint at the column level to fail fast in tests if someone
        # introduces a typo.
        if status not in {"pending", "confirmed", "rejected"}:
            raise ValueError("INVALID_STATUS")

        result = await self._session.execute(
            text(
                """
                UPDATE user_facts
                   SET status = :status
                 WHERE id = :id
                """
            ),
            {"id": fact_id, "status": status},
        )
        # ``rowcount`` may be -1 when the driver does not report it; treat
        # zero as "fact not found" so callers see a deterministic error.
        rowcount = getattr(result, "rowcount", -1)
        if rowcount == 0:
            raise ValueError("FACT_NOT_FOUND")

    async def _count_turns(self, session_id: str) -> int:
        """Return the total number of ``chat_messages`` rows for a session."""
        result = await self._session.execute(
            text(
                """
                SELECT COUNT(*) FROM chat_messages WHERE session_id = :sid
                """
            ),
            {"sid": session_id},
        )
        row = result.first()
        if row is None:
            return 0
        return int(row[0] or 0)

    async def _load_oldest_turns(
        self, session_id: str, *, limit: int
    ) -> list[ChatTurn]:
        """Load the oldest ``limit`` turns of ``session_id`` (chronological).

        Used by :meth:`updateRollingSummary` to feed the summariser with the
        turns that fall outside the ``KEEP_RAW_TURNS`` recency window.
        """
        if limit <= 0:
            return []
        result = await self._session.execute(
            text(
                """
                SELECT id, session_id, role, content,
                       tool_call_id, tool_name, created_at
                FROM chat_messages
                WHERE session_id = :sid
                ORDER BY created_at ASC, id ASC
                LIMIT :lim
                """
            ),
            {"sid": session_id, "lim": limit},
        )
        return [self._row_to_chat_turn(row) for row in result.all()]

    async def _load_existing_fact_texts(self, session_id: str) -> set[str]:
        """Return the case-folded set of every existing fact text for owner.

        Used to dedupe candidate facts emitted by the LLM. Includes facts in
        any status (pending / confirmed / rejected) — proposing the same
        text again would just clutter the moderation queue.
        """
        result = await self._session.execute(
            text(
                """
                SELECT f.fact
                FROM user_facts AS f
                JOIN chat_sessions AS s ON s.user_id = f.user_id
                WHERE s.id = :sid
                """
            ),
            {"sid": session_id},
        )
        return {
            (row[0] or "").strip().casefold()
            for row in result.all()
            if row[0]
        }

    @staticmethod
    def _row_to_fact(row: Any) -> Fact:
        """Convert a SQLAlchemy ``Row`` for ``user_facts`` to a :class:`Fact`."""
        # Row exposes both index and attribute access. Use index to be
        # compatible with the lightweight fakes used in unit tests.
        return Fact(
            id=str(row[0]),
            user_id=str(row[1]),
            category=cast(FactCategoryLiteral, str(row[2])),
            fact=str(row[3]),
            status=cast(FactStatusLiteral, str(row[4])),
            source_msg_id=str(row[5]) if row[5] is not None else None,
            created_at=row[6],
        )

    # ------------------------------------------------------------------- RAG
    async def queryRag(
        self, query: str, top_k: int
    ) -> list[KnowledgeChunk]:
        """Delegate to :class:`RAGService` to retrieve top-k knowledge chunks.

        Returns an empty list when no ``RAGService`` is wired in. The
        underlying ``RAGService`` itself returns ``[]`` when
        ``chunk_embeddings`` is empty (Requirement 5.8); this wrapper keeps
        the same contract at the memory-service surface so the orchestrator
        can call ``memory.queryRag`` unconditionally.

        Parameters
        ----------
        query:
            Non-empty natural-language string. Validation (empty / wrong
            type) is delegated to :meth:`RAGService.query`, which raises
            ``ValueError("INVALID_QUERY")``.
        top_k:
            Strictly positive integer; same delegation applies.
        """
        if self._rag_service is None or is_db_offline():
            logger.debug("queryRag: rag_service not configured or DB offline, returning []")
            return []
        try:
            return await self._rag_service.query(query, top_k, db=self._session)
        except Exception as e:
            mark_db_offline(60.0)
            logger.warning("queryRag failed (DB unavailable?): %s", e)
            return []

    # --------------------------------------------------------------- context
    async def _search_contextual_history(
        self, session_id: str, query: str, limit: int = 20
    ) -> list[ChatTurn]:
        """Search the database for dialogue windows matching the FTS query.

        Uses PostgreSQL window functions to pull matches along with their
        immediate preceding and succeeding turns, deduplicating and merging
        overlapping ranges.
        """
        if not query.strip() or is_db_offline():
            return []

        sql = text(
            """
            WITH numbered AS (
                SELECT id, session_id, role, content, tool_call_id, tool_name, created_at,
                       ROW_NUMBER() OVER (ORDER BY created_at ASC, id ASC) as rn
                FROM chat_messages
                WHERE session_id = :sid
            ),
            matches AS (
                SELECT rn 
                FROM numbered 
                WHERE to_tsvector('simple', content) @@ websearch_to_tsquery('simple', :query)
            )
            SELECT DISTINCT n.id, n.session_id, n.role, n.content, n.tool_call_id, n.tool_name, n.created_at, n.rn
            FROM numbered n
            JOIN matches m ON n.rn >= m.rn - 2 AND n.rn <= m.rn + 2
            ORDER BY n.rn ASC
            LIMIT :lim
            """
        )
        try:
            result = await self._session.execute(
                sql, {"sid": session_id, "query": query, "lim": limit}
            )
            return [self._row_to_chat_turn(row) for row in result.all()]
        except Exception as e:
            logger.warning("Database search failed in _search_contextual_history: %s", e)
            return []

    async def loadContext(
        self,
        session_id: str,
        user_text: str,
        *,
        include_rag: bool = True,
        include_relevant_history: bool = True,
    ) -> Context:
        """Aggregate the four pieces needed to build the system prompt.

        Returns a :class:`Context` containing:

        - ``history``: last :data:`config.settings.max_history_turns` turns
          from ``chat_messages`` for ``session_id`` (chronological,
          oldest-first), as :class:`models.schemas.ChatTurn` objects.
        - ``rolling_summary``: stored in ``chat_session_memory`` (empty
          string when there is no row yet).
        - ``pinned_facts``: confirmed facts for the session's owning user
          (Requirement 5.4).
        - ``rag_chunks``: result of :meth:`queryRag` on ``user_text`` with
          :data:`config.settings.rag_top_k`. Empty when no RAGService is
          wired, when the corpus is empty, or when ``user_text`` is blank.

        Validates Requirements 5.5, 5.6, 5.8.

        Parameters
        ----------
        session_id:
            Session whose history / memory should be loaded.
        user_text:
            The just-arrived user message. Used as the RAG query. A blank
            string skips RAG retrieval (no useful query to embed).
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("INVALID_SESSION_ID")
        if not isinstance(user_text, str):
            raise ValueError("INVALID_USER_TEXT")

        can_parallelize = bool(
            getattr(self._session, "supports_concurrent_statements", False)
        )
        combined_loader = getattr(self._session, "fetch_chat_context", None)
        if callable(combined_loader) and not is_db_offline():
            try:
                raw_history, rolling_summary, raw_facts = await combined_loader(
                    session_id, settings.max_history_turns
                )
                history = [self._chat_turn_from_mapping(item) for item in raw_history]
                pinned_facts = [self._fact_from_mapping(item) for item in raw_facts]
            except Exception as exc:
                logger.warning(
                    "Combined context read failed; using compatible fallback: %s", exc
                )
                history, rolling_summary, pinned_facts = await asyncio.gather(
                    self._load_recent_turns(session_id, limit=settings.max_history_turns),
                    self.getRollingSummary(session_id),
                    self.getPinnedFacts(session_id),
                )
        elif can_parallelize:
            history, rolling_summary, pinned_facts = await asyncio.gather(
                self._load_recent_turns(
                    session_id, limit=settings.max_history_turns
                ),
                self.getRollingSummary(session_id),
                self.getPinnedFacts(session_id),
            )
        else:
            # A raw AsyncSession cannot overlap statements on one connection.
            history = await self._load_recent_turns(
                session_id, limit=settings.max_history_turns
            )
            rolling_summary = await self.getRollingSummary(session_id)
            pinned_facts = await self.getPinnedFacts(session_id)

        # Scope-gate messages remain visible in chat history but never become
        # model context, RAG query-expansion input, summaries, or user facts.
        history = [
            turn
            for turn in history
            if turn.tool_name not in SCOPE_GUARD_HISTORY_MARKERS
        ]

        rag_chunks: list[KnowledgeChunk] = []
        relevant_history: list[ChatTurn] = []
        rag_requested = False
        rag_result_status = "NOT_REQUESTED"

        # Skip FTS / RAG when the message is blank or a simple greeting/chitchat
        if (
            (include_rag or include_relevant_history)
            and user_text.strip()
            and not is_simple_greeting_or_chitchat(user_text)
        ):
            rag_query = user_text
            if include_rag and self._rag_service is not None:
                rag_requested = True
                # Query expansion for reference/pronouns to improve pgvector search accuracy
                if history:
                    last_user_turn = None
                    for turn in reversed(history):
                        if turn.role == "user":
                            last_user_turn = turn
                            break
                    if last_user_turn and last_user_turn.content:
                        pronouns = ["nó", "đấy", "đó", "này", "thêm", "bổ sung", "món đó", "món này", "bài đó", "bài này", "ăn lúc"]
                        if any(p in user_text.lower() for p in pronouns):
                            rag_query = f"{last_user_turn.content} {user_text}"
                            logger.info("Expanded RAG query: %r", rag_query)

            async def _load_rag() -> tuple[list[KnowledgeChunk], str]:
                if not include_rag:
                    return [], "NOT_REQUESTED"
                if self._rag_service is None:
                    return [], "NOT_CONFIGURED"
                try:
                    chunks = await asyncio.wait_for(
                        self.queryRag(rag_query, top_k=settings.rag_top_k),
                        timeout=1.0,
                    )
                    return chunks, "RESULTS_FOUND" if chunks else "NO_RESULTS"
                except asyncio.TimeoutError:
                    logger.warning("queryRag timed out (>1.0s) for session=%s, skipping RAG context", session_id)
                    return [], "TIMEOUT"
                except ValueError as exc:
                    logger.warning(
                        "queryRag rejected rag_query for session=%s: %s",
                        session_id,
                        exc,
                    )
                    return [], "ERROR"

            async def _load_relevant_history() -> list[ChatTurn]:
                if not include_relevant_history:
                    return []
                return await self._search_contextual_history(
                    session_id, user_text, limit=20
                )

            if can_parallelize:
                relevant_history, rag_outcome = await asyncio.gather(
                    _load_relevant_history(),
                    _load_rag(),
                )
            else:
                relevant_history = await _load_relevant_history()
                rag_outcome = await _load_rag()
            rag_chunks, rag_result_status = rag_outcome

            # Filter out duplicates that are already inside history window.
            history_ids = {t.id for t in history}
            relevant_history = [
                turn
                for turn in relevant_history
                if turn.id not in history_ids
                and turn.tool_name not in SCOPE_GUARD_HISTORY_MARKERS
            ]

        return Context(
            history=history,
            rolling_summary=rolling_summary,
            pinned_facts=pinned_facts,
            rag_chunks=rag_chunks,
            relevant_history=relevant_history,
            rag_requested=rag_requested,
            rag_result_status=rag_result_status,
        )

    @staticmethod
    def _chat_turn_from_mapping(value: Any) -> ChatTurn:
        item = dict(value)
        for key in ("id", "session_id", "tool_call_id", "tool_name"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        item["content"] = str(item.get("content") or "")
        return ChatTurn.model_validate(item)

    @staticmethod
    def _fact_from_mapping(value: Any) -> Fact:
        item = dict(value)
        for key in ("id", "user_id", "source_msg_id"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return Fact.model_validate(item)

    async def loadContextCostOptimized(
        self,
        session_id: str,
        user_text: str,
        *,
        include_rag: bool,
        include_relevant_history: bool,
    ) -> Context:
        """Explicit policy-aware entrypoint used by the cost governor."""

        return await self.loadContext(
            session_id,
            user_text,
            include_rag=include_rag,
            include_relevant_history=include_relevant_history,
        )

    async def _load_recent_turns(
        self, session_id: str, *, limit: int
    ) -> list[ChatTurn]:
        """Return the last ``limit`` chat turns for ``session_id``.

        Pulls rows from ``chat_messages`` ordered by ``created_at DESC``
        (with ``id`` as a tiebreaker so two turns inserted in the same
        millisecond keep a deterministic order), then reverses to
        chronological order before returning. The reverse step matters for
        the orchestrator: the LLM expects user / assistant / tool turns in
        the order they happened.

        Sub-1 ``limit`` short-circuits to ``[]`` so callers don't pay for a
        round-trip to the DB just to throw the result away.
        """
        if limit <= 0:
            return []

        from db.session_store import session_store
        from datetime import datetime, timezone
        mem_turns = session_store.get_history(session_id, max_turns=limit)
        converted_mem = [
            ChatTurn(
                id=str(uuid4()),
                session_id=session_id,
                role=cast(ChatRoleLiteral, t.role),
                content=t.content,
                tool_call_id=t.tool_call_id,
                tool_name=t.tool_name,
                created_at=datetime.now(timezone.utc),
            )
            for t in mem_turns
        ]

        if is_db_offline():
            return converted_mem

        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT id, session_id, role, content,
                           tool_call_id, tool_name, created_at
                    FROM chat_messages
                    WHERE session_id = :sid
                    ORDER BY created_at DESC, id DESC
                    LIMIT :lim
                    """
                ),
                {"sid": session_id, "lim": limit},
            )
            rows = result.all()
            db_turns = [self._row_to_chat_turn(row) for row in reversed(rows)]
            return db_turns if db_turns else converted_mem
        except Exception as e:
            mark_db_offline(60.0)
            logger.warning("Database unavailable in _load_recent_turns: %s", e)
            return converted_mem

    @staticmethod
    def _row_to_chat_turn(row: Any) -> ChatTurn:
        """Convert a ``chat_messages`` row to :class:`ChatTurn`."""
        return ChatTurn(
            id=str(row[0]),
            session_id=str(row[1]),
            role=cast(ChatRoleLiteral, str(row[2])),
            content=str(row[3]) if row[3] is not None else "",
            tool_call_id=str(row[4]) if row[4] is not None else None,
            tool_name=str(row[5]) if row[5] is not None else None,
            created_at=row[6],
        )


def is_simple_greeting_or_chitchat(text: str) -> bool:
    """Skip semantic retrieval for pure chitchat or bare control replies.

    Chitchat classification is delegated to the production turn router so
    prompt routing and context retrieval cannot drift apart.
    """
    if not isinstance(text, str):
        return False
    if not text.strip():
        return True
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[!?.,:;~\-_*#\"']+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip()
    # Punctuation-only text may refer to the prior answer (for example "?").
    # Keep semantic history available instead of treating it as small talk.
    if not cleaned:
        return False
    from services.agent.turn_router import classify_turn

    if classify_turn(text).is_chitchat:
        return True
    control_replies = {
        "có", "có chứ", "có nhé", "dạ có", "đồng ý", "ghi đi", "ghi lại",
        "ghi nhé", "lưu đi", "lưu lại", "không", "không cần", "không nhé",
        "không nha", "không đồng ý", "hủy", "thôi", "bỏ qua", "no", "nop",
        "nope",
    }
    return cleaned in control_replies


__all__ = [
    "Context",
    "MemoryService",
    "buildFactExtractionPrompt",
    "buildSummaryPrompt",
    "is_simple_greeting_or_chitchat",
]


# --------------------------------------------------------------------------- #
# Module-level prompt builders + helpers
# --------------------------------------------------------------------------- #


# Cap how much old-turn text we feed into a single LLM call to bound the
# context length. The agent's qwen2.5:7b deployment has plenty of headroom but
# truncating prevents pathological memory growth.
_MAX_TURNS_TEXT_CHARS = 6000

# Recognise ```json … ``` and ``` … ``` fences so the parser can recover the
# inner JSON when the model emits markdown.
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _format_turns_for_prompt(turns: list[ChatTurn]) -> str:
    """Render a list of :class:`ChatTurn` as plain text for the LLM.

    Output format::

        user: ...
        assistant: ...
        tool[get_weight_history]: ...

    Tool turns include ``tool_name`` to give the summariser context. Empty
    contents (rare but possible for tool turns) are skipped to keep the
    prompt compact.
    """
    if not turns:
        return ""
    lines: list[str] = []
    for turn in turns:
        if not turn.content:
            continue
        if turn.role == "tool":
            label = (
                f"tool[{turn.tool_name}]" if turn.tool_name else "tool"
            )
        else:
            label = turn.role
        lines.append(f"{label}: {turn.content.strip()}")
    rendered = "\n".join(lines)
    if len(rendered) > _MAX_TURNS_TEXT_CHARS:
        # Keep the most recent portion of the old-turns window — a long-tail
        # session is more likely to have relevant facts in the recent past.
        rendered = rendered[-_MAX_TURNS_TEXT_CHARS:]
    return rendered


def buildSummaryPrompt(
    turns_text: str, prior_summary: str
) -> list[dict[str, Any]]:
    """Return the ``messages`` payload for the rolling-summary LLM call.

    Format matches what
    :meth:`services.agent.llm_client.LLMClient.chat` expects: a list of
    ``{"role", "content"}`` dicts. The system prompt is short and Vietnamese
    (the chatbot's primary language) and explicitly asks for a single
    paragraph so we don't store sprawling text in
    ``chat_session_memory.rolling_summary``.

    Parameters
    ----------
    turns_text:
        Output of :func:`_format_turns_for_prompt` for the old turns.
    prior_summary:
        Existing ``rolling_summary`` content. May be empty for the first
        run; included in the prompt so the LLM can extend rather than
        replace.
    """
    system = (
        "Bạn đang viết ghi chú hồ sơ cho một huấn luyện viên sức khỏe, để buổi "
        "tư vấn sau họ đọc là nối tiếp được ngay mà không cần đọc lại hội thoại.\n"
        "Gộp phần tóm tắt trước (nếu có) với các turn mới thành MỘT đoạn tiếng "
        "Việt ≤ 8 câu. Ưu tiên giữ, theo đúng thứ tự này:\n"
        "1. Mục tiêu người dùng đang theo đuổi và deadline nếu có.\n"
        "2. Ràng buộc lâu dài: dị ứng, bệnh nền, thiết bị tập, lịch sinh hoạt.\n"
        "3. Lời khuyên đã đưa ra và người dùng phản ứng thế nào (đồng ý, từ chối, "
        "đã thử rồi không hợp) — để lần sau không lặp lại đề xuất họ đã bác.\n"
        "4. Con số quan trọng kèm mốc thời gian (cân nặng, TDEE, calo mục tiêu).\n"
        "5. Việc còn dang dở hoặc câu hỏi chưa trả lời xong.\n"
        "Bỏ qua chào hỏi, cảm ơn, và chi tiết vụn vặt. Không bịa thông tin không "
        "có trong input. Chỉ trả về đoạn tóm tắt, không tiêu đề, không giải thích."
    )
    user_parts: list[str] = []
    if prior_summary.strip():
        user_parts.append(f"Tóm tắt trước đây:\n{prior_summary.strip()}")
    user_parts.append(f"Các turn cũ cần cô đặc:\n{turns_text}")
    user_content = "\n\n".join(user_parts)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


def buildFactExtractionPrompt(
    turns_text: str, existing_facts: list[Any] | None = None
) -> list[dict[str, Any]]:
    """Return the ``messages`` payload for the fact-extraction LLM call.

    The LLM is instructed to emit a JSON array of operations:
    ``{"action": ..., "category": ..., "fact": ..., "target_fact": ..., "confidence": ...}``.
    """
    allowed = ", ".join(sorted(_ALLOWED_CATEGORIES))
    system = (
        "Bạn là module trích xuất và cập nhật pinned facts về user từ hội thoại sức khỏe.\n"
        "Đọc danh sách sự thật hiện tại đã biết (nếu có) và các turn hội thoại mới dưới đây. "
        "Quyết định hành động cần thực hiện đối với bộ nhớ:\n"
        "- \"add\": Thêm sự thật mới chưa từng có trước đây.\n"
        "- \"update\": Cập nhật một sự thật cũ bằng nội dung mới (khi người dùng thay đổi thông tin cũ hoặc thông tin mới chính xác hơn). "
        "Bạn phải chỉ định rõ nội dung sự thật cũ cần thay thế ở trường \"target_fact\".\n"
        "- \"remove\": Xóa một sự thật cũ không còn đúng nữa. Bạn phải chỉ định rõ sự thật cũ cần xóa ở trường \"target_fact\".\n\n"
        "Chỉ trích xuất các sự thật ổn định lâu dài (sở thích ăn uống, dị ứng, mục tiêu, ràng buộc lối sống, bệnh nền, thiết bị tập, lịch sinh hoạt). "
        "KHÔNG trích xuất các sự kiện ngắn hạn (bữa ăn hôm nay, cân nặng hôm nay, tâm trạng hôm nay).\n"
        "Viết nội dung sự thật ở ngôi thứ ba, ngắn gọn, tự đứng độc lập được (vd: \"Dị ứng hải sản\", \"Mục tiêu giảm 5kg trong 3 tháng\").\n"
        "\"confidence\" = \"high\" khi người dùng khẳng định rõ ràng; \"low\" khi bạn đang tự suy diễn.\n\n"
        "Trả về DUY NHẤT một mảng JSON (không kèm markdown khác) theo cấu trúc:\n"
        "[\n"
        "  {\n"
        "    \"action\": \"add|update|remove\",\n"
        "    \"category\": \"<một trong: " + allowed + ">\",\n"
        "    \"fact\": \"<nội dung sự thật mới hoặc sự thật cần cập nhật>\",\n"
        "    \"target_fact\": \"<nội dung sự thật cũ bị thay thế/xóa (chỉ dùng cho update/remove)>\",\n"
        "    \"confidence\": \"high|low\"\n"
        "  }, ...\n"
        "]\n"
        "Nếu không cần thay đổi gì, trả về [] (mảng rỗng)."
    )
    
    existing_text = ""
    if existing_facts:
        existing_lines = []
        for f in existing_facts:
            cat = getattr(f, "category", "")
            text_val = getattr(f, "fact", "")
            existing_lines.append(f"- [{cat}] {text_val}")
        existing_text = "\n\nCác sự thật hiện tại đã biết:\n" + "\n".join(existing_lines)

    user_content = f"Các turn cần phân tích:\n{turns_text}{existing_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


def _parse_fact_candidates(raw_text: str) -> list[dict[str, Any]]:
    """Best-effort parse the LLM's fact-extraction response.

    Each candidate is normalised to:
    {
      "action": "add|update|remove",
      "category": str,
      "fact": str,
      "target_fact": str,
      "confidence": "high|low"
    }
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []

    candidate_blobs: list[str] = []
    fence = _JSON_FENCE_RE.search(raw_text)
    if fence is not None:
        candidate_blobs.append(fence.group("body").strip())

    # Always include the first balanced top-level array as a fallback.
    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate_blobs.append(raw_text[start : end + 1])

    parsed: Any = None
    for blob in candidate_blobs:
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            break
        parsed = None
    if not isinstance(parsed, list):
        return []

    results: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        
        action = item.get("action", "add")
        if not isinstance(action, str) or action.strip().lower() not in {"add", "update", "remove"}:
            action = "add"
        action = action.strip().lower()

        fact = item.get("fact")
        fact = fact.strip() if isinstance(fact, str) else ""

        target_fact = item.get("target_fact")
        target_fact = target_fact.strip() if isinstance(target_fact, str) else ""

        # Validate that we have the required fields based on action
        if action == "add" and not fact:
            continue
        if action == "update" and (not fact or not target_fact):
            continue
        if action == "remove" and not target_fact:
            continue

        category = item.get("category")
        if not isinstance(category, str):
            category = "other"
        category = category.strip().lower()

        confidence = item.get("confidence")
        if not isinstance(confidence, str) or confidence.strip().lower() not in {"high", "low"}:
            confidence = "low"
        confidence = confidence.strip().lower()

        results.append({
            "action": action,
            "category": category,
            "fact": fact,
            "target_fact": target_fact,
            "confidence": confidence
        })
    return results
