"""Durable PostgreSQL state for N3.2.1 development/shadow feedback.

This module owns the transaction boundary between a shown recommendation and
the owner-private feedback it later receives.  It deliberately does not know
how to create a meal log, mutate a canonical recipe, or promote a candidate.
The in-memory adaptive repository remains a candidate/cache boundary; this
store is the authoritative persistence/read-back boundary for recommendation
events, feedback and derived private learning state.
"""

from __future__ import annotations

import asyncio
import json
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.database import AsyncSessionLocal

from .contracts import FeedbackEvent, FeedbackEventType, FeedbackRejectionReason
from .intelligence import (
    CandidateFeatures,
    CandidateSourceType,
    CatalogGapObservation,
    PortionLearning,
    PortionObservation,
    PortionPrior,
    PreferenceDimension,
    PreferenceEvidence,
    PreferenceProfileBuilder,
    PreferenceSource,
    RecommendationMemoryEntry,
    ShadowRecommendationLog,
    UserPreferenceProfile,
)


class AdaptiveFeedbackStoreError(RuntimeError):
    """A stable fail-closed error for the N3.2.1 feedback boundary."""


class AdaptiveFeedbackNotFound(AdaptiveFeedbackStoreError):
    """Owner-scoped lookup failure; callers must not reveal foreign state."""


class AdaptiveFeedbackIdentityError(AdaptiveFeedbackStoreError):
    """The event does not belong to the recommendation event supplied."""


@dataclass(frozen=True)
class FeedbackPersistenceResult:
    feedback: FeedbackEvent
    recommendation: RecommendationMemoryEntry
    idempotent: bool
    catalog_gap_signal_recorded: bool
    portion_evidence_recorded: bool


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _normalise_catalog_key(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().strip().split()
    )


def feature_payload_for_entry(
    entry: RecommendationMemoryEntry,
    *,
    ingredients: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return only recipe attributes that are admissible for private ranking."""

    supplied = dict(entry.feature_payload)
    return {
        "dish": str(supplied.get("dish") or entry.dish),
        "ingredients": [str(value) for value in supplied.get("ingredients", ingredients) if str(value)],
        "primary_protein": supplied.get("primary_protein") or entry.primary_protein,
        "cuisine": supplied.get("cuisine") or entry.cuisine,
        "preparation": supplied.get("preparation") or entry.preparation,
        "cooking_effort": supplied.get("cooking_effort"),
        "budget_band": supplied.get("budget_band"),
    }


def _features(candidate_id: str, dish: str, payload: Mapping[str, Any]) -> CandidateFeatures:
    values = _as_mapping(payload)
    raw_ingredients = values.get("ingredients")
    ingredients = tuple(str(item) for item in raw_ingredients if str(item)) if isinstance(raw_ingredients, list) else ()
    return CandidateFeatures(
        candidate_id=candidate_id,
        dish=str(values.get("dish") or dish),
        ingredients=ingredients,
        primary_protein=_string_or_none(values.get("primary_protein")),
        cuisine=_string_or_none(values.get("cuisine")),
        preparation=_string_or_none(values.get("preparation")),
        cooking_effort=_string_or_none(values.get("cooking_effort")),
        budget_band=_string_or_none(values.get("budget_band")),
    )


def _string_or_none(value: Any) -> str | None:
    rendered = str(value).strip() if value is not None else ""
    return rendered or None


def _memory_from_row(row: Mapping[str, Any]) -> RecommendationMemoryEntry:
    return RecommendationMemoryEntry(
        recommendation_id=str(row["recommendation_id"]),
        owner_user_id=str(row["owner_user_id"]),
        candidate_id=str(row["candidate_id"]),
        dish=str(row["dish_key"]),
        source_type=CandidateSourceType(str(row["source_type"])),
        shown_at=_as_datetime(row["shown_at"]),
        primary_protein=_string_or_none(row.get("primary_protein_key")),
        cuisine=_string_or_none(row.get("cuisine_key")),
        preparation=_string_or_none(row.get("preparation_key")),
        outcome_status=str(row["outcome_status"]),
        selected_policy=str(row["policy_version"]),
        selection_probability=float(row["selection_probability"])
        if row.get("selection_probability") is not None
        else None,
        context_fingerprint=_string_or_none(row.get("context_fingerprint")),
        feature_payload=_as_mapping(row.get("feature_payload")),
    )


def _feedback_from_row(row: Mapping[str, Any]) -> FeedbackEvent:
    reason = row.get("rejection_reason")
    return FeedbackEvent(
        owner_user_id=str(row["owner_user_id"]),
        candidate_id=str(row["candidate_id"]),
        event_type=FeedbackEventType(str(row["event_type"])),
        occurred_at=_as_datetime(row["occurred_at"]),
        explicit=bool(row["explicit"]),
        reason_code=FeedbackRejectionReason(str(reason)) if reason else None,
        metadata=_as_mapping(row.get("structured_payload")),
        recommendation_id=str(row["recommendation_id"]),
        policy_version=_string_or_none(row.get("policy_version")),
        idempotency_key=_string_or_none(row.get("idempotency_key")),
        feedback_event_id=str(row["feedback_event_id"]),
    )


def _same_intended_feedback(stored: FeedbackEvent, requested: FeedbackEvent) -> bool:
    return (
        stored.owner_user_id == requested.owner_user_id
        and stored.recommendation_id == requested.recommendation_id
        and stored.candidate_id == requested.candidate_id
        and stored.event_type == requested.event_type
        and stored.policy_version == requested.policy_version
        and stored.reason_code == requested.reason_code
        and dict(stored.metadata) == dict(requested.metadata)
    )


def _catalog_gap_signal(entry: RecommendationMemoryEntry, event: FeedbackEvent) -> tuple[str, str] | None:
    if entry.source_type not in {
        CandidateSourceType.STAGING_EXTERNAL,
        CandidateSourceType.RUNTIME_EXTERNAL,
    }:
        return None
    key = _normalise_catalog_key(entry.dish)
    if not key:
        return None
    if (
        event.event_type is FeedbackEventType.REJECTED
        and event.reason_code is FeedbackRejectionReason.INGREDIENT_UNAVAILABLE
    ):
        return key, "INGREDIENT_UNAVAILABLE"
    if event.event_type in {FeedbackEventType.INGREDIENT_CORRECTED, FeedbackEventType.RECIPE_CORRECTED}:
        return key, "CORRECTION"
    return None


class AdaptiveShadowSqlStore:
    """PostgreSQL source of truth for N3.2.1 shadow feedback.

    A real session factory is required because a feedback write spans immutable
    feedback, derived profile, optional portion evidence and catalog-gap
    evidence in a single transaction.  ``ScopedSession`` is deliberately not
    accepted here because it commits statement-by-statement.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession] = AsyncSessionLocal,
    ) -> None:
        self._session_factory = session_factory

    async def persist_delivery(
        self,
        entry: RecommendationMemoryEntry,
        *,
        shadow_log: ShadowRecommendationLog | None = None,
    ) -> RecommendationMemoryEntry:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing = await self._recommendation_in_session(
                        session, entry.owner_user_id, entry.recommendation_id, for_update=True
                    )
                    if existing is not None:
                        if (
                            existing.candidate_id != entry.candidate_id
                            or existing.selected_policy != entry.selected_policy
                        ):
                            raise AdaptiveFeedbackIdentityError("RECOMMENDATION_EVENT_ID_REUSED")
                        return existing
                    await session.execute(
                        text(
                            """
                            INSERT INTO nutrition_recommendation_memory_n3_2 (
                                id, owner_user_id, candidate_id, source_type, dish_key,
                                primary_protein_key, cuisine_key, preparation_key, shown_at,
                                outcome_status, policy_version, selection_probability,
                                context_fingerprint, feature_payload
                            ) VALUES (
                                CAST(:recommendation_id AS uuid), :owner, CAST(:candidate_id AS uuid),
                                :source_type, :dish_key, :primary_protein, :cuisine, :preparation,
                                :shown_at, 'SHOWN', :policy_version, :selection_probability,
                                :context_fingerprint, CAST(:feature_payload AS jsonb)
                            )
                            """
                        ),
                        {
                            "recommendation_id": entry.recommendation_id,
                            "owner": entry.owner_user_id,
                            "candidate_id": entry.candidate_id,
                            "source_type": entry.source_type.value,
                            "dish_key": entry.dish,
                            "primary_protein": entry.primary_protein,
                            "cuisine": entry.cuisine,
                            "preparation": entry.preparation,
                            "shown_at": entry.shown_at,
                            "policy_version": entry.selected_policy,
                            "selection_probability": entry.selection_probability,
                            "context_fingerprint": entry.context_fingerprint,
                            "feature_payload": _json(feature_payload_for_entry(entry)),
                        },
                    )
                    if shadow_log is not None:
                        await self._insert_shadow_log(session, entry.recommendation_id, shadow_log)
        except AdaptiveFeedbackStoreError:
            raise
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_DELIVERY_PERSISTENCE_FAILED") from exc
        read_back = await self.recommendation_for_owner(
            owner_user_id=entry.owner_user_id, recommendation_id=entry.recommendation_id
        )
        if read_back is None or read_back.candidate_id != entry.candidate_id:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_DELIVERY_READBACK_FAILED")
        return read_back

    async def record_feedback(
        self,
        event: FeedbackEvent,
        *,
        corrected_portion_grams: float | None = None,
    ) -> FeedbackPersistenceResult:
        if not event.recommendation_id or not event.policy_version or not event.idempotency_key:
            raise AdaptiveFeedbackIdentityError("RECOMMENDATION_FEEDBACK_IDENTITY_REQUIRED")
        if event.event_type is FeedbackEventType.SHOWN:
            raise AdaptiveFeedbackIdentityError("EXPOSURE_EVENT_SERVER_ONLY")
        if event.event_type is FeedbackEventType.ACTUALLY_CONSUMED:
            raise AdaptiveFeedbackIdentityError("ACTUAL_MEAL_LOG_REQUIRED")
        if event.event_type is FeedbackEventType.PORTION_CORRECTED:
            if corrected_portion_grams is None or corrected_portion_grams <= 0:
                raise AdaptiveFeedbackIdentityError("PORTION_CORRECTION_GRAMS_REQUIRED")
        elif corrected_portion_grams is not None:
            raise AdaptiveFeedbackIdentityError("PORTION_CORRECTION_EVENT_REQUIRED")
        event = replace(event, feedback_event_id=event.feedback_event_id or str(uuid4()))
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    recommendation = await self._recommendation_in_session(
                        session, event.owner_user_id, event.recommendation_id, for_update=True
                    )
                    if recommendation is None:
                        raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
                    if (
                        recommendation.candidate_id != event.candidate_id
                        or recommendation.selected_policy != event.policy_version
                    ):
                        raise AdaptiveFeedbackIdentityError("RECOMMENDATION_FEEDBACK_IDENTITY_MISMATCH")
                    duplicate = await self._feedback_by_idempotency_in_session(
                        session, event.owner_user_id, event.idempotency_key, for_update=True
                    )
                    if duplicate is not None:
                        if not _same_intended_feedback(duplicate, event):
                            raise AdaptiveFeedbackIdentityError("FEEDBACK_IDEMPOTENCY_KEY_REUSED")
                        return FeedbackPersistenceResult(
                            feedback=duplicate,
                            recommendation=recommendation,
                            idempotent=True,
                            catalog_gap_signal_recorded=False,
                            portion_evidence_recorded=False,
                        )

                    await session.execute(
                        text(
                            """
                            INSERT INTO nutrition_recommendation_feedback_n3_2 (
                                id, owner_user_id, recommendation_id, candidate_id, event_type,
                                rejection_reason, explicit, structured_payload, occurred_at,
                                policy_version, idempotency_key
                            ) VALUES (
                                CAST(:feedback_id AS uuid), :owner, CAST(:recommendation_id AS uuid),
                                CAST(:candidate_id AS uuid), :event_type, :reason_code, :explicit,
                                CAST(:metadata AS jsonb), :occurred_at, :policy_version, :idempotency_key
                            )
                            """
                        ),
                        {
                            "feedback_id": event.feedback_event_id,
                            "owner": event.owner_user_id,
                            "recommendation_id": event.recommendation_id,
                            "candidate_id": event.candidate_id,
                            "event_type": event.event_type.value,
                            "reason_code": event.reason_code.value if event.reason_code else None,
                            "explicit": event.explicit,
                            "metadata": _json(event.metadata),
                            "occurred_at": event.occurred_at,
                            "policy_version": event.policy_version,
                            "idempotency_key": event.idempotency_key,
                        },
                    )
                    await session.execute(
                        text(
                            """
                            UPDATE nutrition_recommendation_memory_n3_2
                            SET outcome_status = :event_type
                            WHERE id = CAST(:recommendation_id AS uuid) AND owner_user_id = :owner
                            """
                        ),
                        {
                            "event_type": event.event_type.value,
                            "recommendation_id": event.recommendation_id,
                            "owner": event.owner_user_id,
                        },
                    )
                    portion_recorded = False
                    if corrected_portion_grams is not None:
                        await session.execute(
                            text(
                                """
                                INSERT INTO nutrition_personal_portion_corrections_n3_2 (
                                    id, feedback_event_id, owner_user_id, recommendation_id,
                                    candidate_id, corrected_portion_grams, policy_version, occurred_at
                                ) VALUES (
                                    CAST(:id AS uuid), CAST(:feedback_id AS uuid), :owner,
                                    CAST(:recommendation_id AS uuid), CAST(:candidate_id AS uuid),
                                    :grams, :policy_version, :occurred_at
                                )
                                """
                            ),
                            {
                                "id": str(uuid4()), "feedback_id": event.feedback_event_id,
                                "owner": event.owner_user_id,
                                "recommendation_id": event.recommendation_id,
                                "candidate_id": event.candidate_id,
                                "grams": corrected_portion_grams,
                                "policy_version": event.policy_version,
                                "occurred_at": event.occurred_at,
                            },
                        )
                        portion_recorded = True
                    gap = _catalog_gap_signal(recommendation, event)
                    if gap is not None:
                        await session.execute(
                            text(
                                """
                                INSERT INTO nutrition_catalog_gap_feedback_evidence_n3_2 (
                                    feedback_event_id, normalized_candidate_key, signal_type, occurred_at
                                ) VALUES (CAST(:feedback_id AS uuid), :key, :signal, :occurred_at)
                                """
                            ),
                            {
                                "feedback_id": event.feedback_event_id,
                                "key": gap[0], "signal": gap[1], "occurred_at": event.occurred_at,
                            },
                        )
                    await self._rebuild_profile_in_session(session, event.owner_user_id)
                    await self._set_shadow_outcome_in_session(session, event)
        except (AdaptiveFeedbackStoreError, AdaptiveFeedbackIdentityError):
            raise
        except IntegrityError as exc:
            # The unique durable owner/idempotency index is the concurrency
            # authority. A competing identical request reads that row back;
            # a different payload with the same key fails closed.
            duplicate = await self._idempotent_read_after_conflict(event)
            if duplicate is not None:
                return duplicate
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_TRANSACTION_FAILED") from exc
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_TRANSACTION_FAILED") from exc

        feedback = await self.feedback_by_id(
            owner_user_id=event.owner_user_id, feedback_event_id=event.feedback_event_id
        )
        recommendation = await self.recommendation_for_owner(
            owner_user_id=event.owner_user_id, recommendation_id=event.recommendation_id
        )
        if feedback is None or recommendation is None or recommendation.outcome_status != event.event_type.value:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_READBACK_FAILED")
        return FeedbackPersistenceResult(
            feedback=feedback,
            recommendation=recommendation,
            idempotent=False,
            catalog_gap_signal_recorded=_catalog_gap_signal(recommendation, feedback) is not None,
            portion_evidence_recorded=corrected_portion_grams is not None,
        )

    async def recommendation_for_owner(
        self, *, owner_user_id: str, recommendation_id: str
    ) -> RecommendationMemoryEntry | None:
        try:
            async with self._session_factory() as session:
                return await self._recommendation_in_session(session, owner_user_id, recommendation_id)
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_RECOMMENDATION_READ_FAILED") from exc

    async def feedback_for_recommendation(
        self, *, owner_user_id: str, recommendation_id: str
    ) -> tuple[FeedbackEvent, ...]:
        recommendation = await self.recommendation_for_owner(
            owner_user_id=owner_user_id, recommendation_id=recommendation_id
        )
        if recommendation is None:
            raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT id::text AS feedback_event_id, owner_user_id,
                                   recommendation_id::text AS recommendation_id,
                                   candidate_id::text AS candidate_id, event_type,
                                   rejection_reason, explicit, structured_payload, occurred_at,
                                   policy_version, idempotency_key
                            FROM nutrition_recommendation_feedback_n3_2
                            WHERE owner_user_id = :owner
                              AND recommendation_id = CAST(:recommendation_id AS uuid)
                            ORDER BY occurred_at, id
                            """
                        ),
                        {"owner": owner_user_id, "recommendation_id": recommendation_id},
                    )
                ).mappings().all()
            return tuple(_feedback_from_row(row) for row in rows)
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_READ_FAILED") from exc

    async def recent_recommendations(
        self, *, owner_user_id: str, limit: int = 20
    ) -> tuple[RecommendationMemoryEntry, ...]:
        if limit < 1:
            raise AdaptiveFeedbackIdentityError("INVALID_RECOMMENDATION_HISTORY_LIMIT")
        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT id::text AS recommendation_id, owner_user_id,
                                   candidate_id::text AS candidate_id, source_type, dish_key,
                                   primary_protein_key, cuisine_key, preparation_key, shown_at,
                                   outcome_status, policy_version, selection_probability,
                                   context_fingerprint, feature_payload
                            FROM nutrition_recommendation_memory_n3_2
                            WHERE owner_user_id = :owner
                            ORDER BY shown_at DESC, id DESC
                            LIMIT :limit
                            """
                        ),
                        {"owner": owner_user_id, "limit": limit},
                    )
                ).mappings().all()
            return tuple(_memory_from_row(row) for row in rows)
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_RECOMMENDATION_READ_FAILED") from exc

    async def preference_profile(self, *, owner_user_id: str) -> UserPreferenceProfile:
        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT dimension, value_key, affinity, confidence, source_type,
                                   updated_at, evidence_count, last_confirmed_at
                            FROM nutrition_preference_profile_n3_2
                            WHERE owner_user_id = :owner
                            ORDER BY updated_at DESC, dimension, value_key
                            """
                        ),
                        {"owner": owner_user_id},
                    )
                ).mappings().all()
            evidence = tuple(
                PreferenceEvidence(
                    dimension=PreferenceDimension(str(row["dimension"])),
                    value=str(row["value_key"]),
                    affinity=float(row["affinity"]),
                    confidence=float(row["confidence"]),
                    source=PreferenceSource(str(row["source_type"])),
                    updated_at=_as_datetime(row["updated_at"]),
                    evidence_count=int(row["evidence_count"]),
                    last_confirmed_at=_as_datetime(row["last_confirmed_at"])
                    if row["last_confirmed_at"] is not None
                    else None,
                )
                for row in rows
            )
            return UserPreferenceProfile(
                owner_user_id=owner_user_id,
                policy_version="PREFERENCE_WEIGHT_POLICY_V1",
                evidence=evidence,
                insufficient_evidence=len(evidence) == 0,
            )
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_PREFERENCE_READ_FAILED") from exc

    async def portion_prior(
        self, *, owner_user_id: str, candidate_id: str
    ) -> PortionPrior | None:
        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT candidate_id::text AS candidate_id,
                                   corrected_portion_grams AS grams, occurred_at,
                                   'PORTION_CORRECTED' AS source_event
                            FROM nutrition_personal_portion_corrections_n3_2
                            WHERE owner_user_id = :owner AND candidate_id = CAST(:candidate_id AS uuid)
                            UNION ALL
                            SELECT candidate_id::text AS candidate_id,
                                   actual_portion_grams AS grams, occurred_at, source_event
                            FROM nutrition_personal_portion_observations_n3_2
                            WHERE owner_user_id = :owner AND candidate_id = CAST(:candidate_id AS uuid)
                            ORDER BY occurred_at
                            """
                        ),
                        {"owner": owner_user_id, "candidate_id": candidate_id},
                    )
                ).mappings().all()
            observations = tuple(
                PortionObservation(
                    owner_user_id=owner_user_id,
                    candidate_id=str(row["candidate_id"]),
                    actual_portion_grams=float(row["grams"]),
                    occurred_at=_as_datetime(row["occurred_at"]),
                    source_event=FeedbackEventType(str(row["source_event"])),
                )
                for row in rows
            )
            return PortionLearning().build_prior(
                owner_user_id=owner_user_id, candidate_id=candidate_id, observations=observations
            )
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_PORTION_READ_FAILED") from exc

    async def catalog_gap_observations(self) -> tuple[CatalogGapObservation, ...]:
        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT normalized_candidate_key,
                                   COUNT(*) FILTER (WHERE signal_type = 'INGREDIENT_UNAVAILABLE') AS request_count,
                                   COUNT(*) FILTER (WHERE signal_type = 'CORRECTION') AS correction_count
                            FROM nutrition_catalog_gap_feedback_evidence_n3_2
                            GROUP BY normalized_candidate_key
                            ORDER BY normalized_candidate_key
                            """
                        )
                    )
                ).mappings().all()
            return tuple(
                CatalogGapObservation(
                    normalized_query=str(row["normalized_candidate_key"]),
                    request_count=int(row["request_count"]),
                    correction_count=int(row["correction_count"]),
                )
                for row in rows
            )
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_CATALOG_GAP_READ_FAILED") from exc

    async def shadow_bandit_logs(self) -> tuple[ShadowRecommendationLog, ...]:
        """Read shadow-only telemetry; this is never a delivery control path."""

        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT candidate_set_ids, selected_candidate_id::text AS selected_candidate_id,
                                   policy_version, context_fingerprint, selection_probability,
                                   outcome_event, production_selected_candidate_id::text AS production_selected_candidate_id,
                                   recommendation_event_id::text AS recommendation_event_id
                            FROM nutrition_shadow_policy_logs_n3_2
                            ORDER BY occurred_at DESC, id DESC
                            LIMIT 500
                            """
                        )
                    )
                ).mappings().all()
            logs: list[ShadowRecommendationLog] = []
            for row in rows:
                raw_ids = row["candidate_set_ids"]
                if isinstance(raw_ids, str):
                    raw_ids = json.loads(raw_ids)
                outcome = row["outcome_event"]
                logs.append(
                    ShadowRecommendationLog(
                        candidate_set_ids=tuple(str(item) for item in raw_ids or ()),
                        selected_candidate_id=str(row["selected_candidate_id"]),
                        policy_version=str(row["policy_version"]),
                        context_fingerprint=str(row["context_fingerprint"]),
                        selection_probability=float(row["selection_probability"])
                        if row["selection_probability"] is not None
                        else None,
                        outcome_event=FeedbackEventType(str(outcome)) if outcome else None,
                        production_selected_candidate_id=_string_or_none(row["production_selected_candidate_id"]),
                        recommendation_event_id=_string_or_none(row["recommendation_event_id"]),
                    )
                )
            return tuple(logs)
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_SHADOW_LOG_READ_FAILED") from exc

    async def feedback_by_id(
        self, *, owner_user_id: str, feedback_event_id: str | None
    ) -> FeedbackEvent | None:
        if not feedback_event_id:
            return None
        try:
            async with self._session_factory() as session:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT id::text AS feedback_event_id, owner_user_id,
                                   recommendation_id::text AS recommendation_id,
                                   candidate_id::text AS candidate_id, event_type,
                                   rejection_reason, explicit, structured_payload, occurred_at,
                                   policy_version, idempotency_key
                            FROM nutrition_recommendation_feedback_n3_2
                            WHERE owner_user_id = :owner AND id = CAST(:feedback_id AS uuid)
                            """
                        ),
                        {"owner": owner_user_id, "feedback_id": feedback_event_id},
                    )
                ).mappings().first()
            return _feedback_from_row(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_READ_FAILED") from exc

    async def _recommendation_in_session(
        self, session: AsyncSession, owner_user_id: str, recommendation_id: str, *, for_update: bool = False
    ) -> RecommendationMemoryEntry | None:
        lock = " FOR UPDATE" if for_update else ""
        row = (
            await session.execute(
                text(
                    """
                    SELECT id::text AS recommendation_id, owner_user_id,
                           candidate_id::text AS candidate_id, source_type, dish_key,
                           primary_protein_key, cuisine_key, preparation_key, shown_at,
                           outcome_status, policy_version, selection_probability,
                           context_fingerprint, feature_payload
                    FROM nutrition_recommendation_memory_n3_2
                    WHERE owner_user_id = :owner AND id = CAST(:recommendation_id AS uuid)
                    """ + lock
                ),
                {"owner": owner_user_id, "recommendation_id": recommendation_id},
            )
        ).mappings().first()
        return _memory_from_row(row) if row is not None else None

    async def _feedback_by_idempotency_in_session(
        self, session: AsyncSession, owner_user_id: str, idempotency_key: str, *, for_update: bool = False
    ) -> FeedbackEvent | None:
        lock = " FOR UPDATE" if for_update else ""
        row = (
            await session.execute(
                text(
                    """
                    SELECT id::text AS feedback_event_id, owner_user_id,
                           recommendation_id::text AS recommendation_id,
                           candidate_id::text AS candidate_id, event_type,
                           rejection_reason, explicit, structured_payload, occurred_at,
                           policy_version, idempotency_key
                    FROM nutrition_recommendation_feedback_n3_2
                    WHERE owner_user_id = :owner AND idempotency_key = :idempotency_key
                    """ + lock
                ),
                {"owner": owner_user_id, "idempotency_key": idempotency_key},
            )
        ).mappings().first()
        return _feedback_from_row(row) if row is not None else None

    async def _rebuild_profile_in_session(self, session: AsyncSession, owner_user_id: str) -> None:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT f.id::text AS feedback_event_id, f.owner_user_id,
                           f.recommendation_id::text AS recommendation_id,
                           f.candidate_id::text AS candidate_id, f.event_type,
                           f.rejection_reason, f.explicit, f.structured_payload,
                           f.occurred_at, f.policy_version, f.idempotency_key,
                           m.dish_key, m.feature_payload
                    FROM nutrition_recommendation_feedback_n3_2 f
                    JOIN nutrition_recommendation_memory_n3_2 m ON m.id = f.recommendation_id
                    WHERE f.owner_user_id = :owner AND m.owner_user_id = :owner
                    ORDER BY f.occurred_at, f.id
                    """
                ),
                {"owner": owner_user_id},
            )
        ).mappings().all()
        feature_events = tuple(
            (
                _feedback_from_row(row),
                _features(str(row["candidate_id"]), str(row["dish_key"]), _as_mapping(row["feature_payload"])),
            )
            for row in rows
        )
        profile = PreferenceProfileBuilder().build_from_feature_events(
            owner_user_id=owner_user_id, feature_events=feature_events
        )
        await session.execute(
            text("DELETE FROM nutrition_preference_profile_n3_2 WHERE owner_user_id = :owner"),
            {"owner": owner_user_id},
        )
        for evidence in profile.evidence:
            await session.execute(
                text(
                    """
                    INSERT INTO nutrition_preference_profile_n3_2 (
                        id, owner_user_id, dimension, value_key, affinity, confidence,
                        evidence_count, source_type, policy_version, updated_at, last_confirmed_at
                    ) VALUES (
                        CAST(:id AS uuid), :owner, :dimension, :value_key, :affinity,
                        :confidence, :evidence_count, :source_type,
                        'PREFERENCE_WEIGHT_POLICY_V1', :updated_at, :last_confirmed_at
                    )
                    """
                ),
                {
                    "id": str(uuid5(NAMESPACE_URL, f"n3-2-1-preference:{owner_user_id}:{evidence.dimension.value}:{evidence.value}")),
                    "owner": owner_user_id,
                    "dimension": evidence.dimension.value,
                    "value_key": evidence.value,
                    "affinity": evidence.affinity,
                    "confidence": evidence.confidence,
                    "evidence_count": evidence.evidence_count,
                    "source_type": evidence.source.value,
                    "updated_at": evidence.updated_at,
                    "last_confirmed_at": evidence.last_confirmed_at,
                },
            )

    async def _insert_shadow_log(
        self, session: AsyncSession, recommendation_id: str, record: ShadowRecommendationLog
    ) -> None:
        await session.execute(
            text(
                """
                INSERT INTO nutrition_shadow_policy_logs_n3_2 (
                    id, candidate_set_ids, selected_candidate_id, policy_version,
                    context_fingerprint, selection_probability,
                    production_selected_candidate_id, recommendation_event_id, occurred_at
                ) VALUES (
                    CAST(:id AS uuid), CAST(:candidate_set_ids AS jsonb),
                    CAST(:selected_candidate_id AS uuid), :policy_version,
                    :context_fingerprint, :selection_probability,
                    CAST(:production_selected_candidate_id AS uuid),
                    CAST(:recommendation_event_id AS uuid), :occurred_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "candidate_set_ids": json.dumps(list(record.candidate_set_ids)),
                "selected_candidate_id": record.selected_candidate_id,
                "policy_version": record.policy_version,
                "context_fingerprint": record.context_fingerprint,
                "selection_probability": record.selection_probability,
                "production_selected_candidate_id": record.production_selected_candidate_id,
                "recommendation_event_id": recommendation_id,
                "occurred_at": datetime.now(timezone.utc),
            },
        )

    async def _set_shadow_outcome_in_session(self, session: AsyncSession, event: FeedbackEvent) -> None:
        if not event.recommendation_id:
            return
        await session.execute(
            text(
                """
                UPDATE nutrition_shadow_policy_logs_n3_2
                SET outcome_event = :event_type
                WHERE recommendation_event_id = CAST(:recommendation_id AS uuid)
                """
            ),
            {"event_type": event.event_type.value, "recommendation_id": event.recommendation_id},
        )

    async def _idempotent_read_after_conflict(
        self, event: FeedbackEvent
    ) -> FeedbackPersistenceResult | None:
        try:
            async with self._session_factory() as session:
                stored = await self._feedback_by_idempotency_in_session(
                    session, event.owner_user_id, event.idempotency_key or ""
                )
                recommendation = await self._recommendation_in_session(
                    session, event.owner_user_id, event.recommendation_id or ""
                )
            if stored is None or recommendation is None:
                return None
            if not _same_intended_feedback(stored, event):
                raise AdaptiveFeedbackIdentityError("FEEDBACK_IDEMPOTENCY_KEY_REUSED")
            return FeedbackPersistenceResult(stored, recommendation, True, False, False)
        except AdaptiveFeedbackStoreError:
            raise
        except SQLAlchemyError as exc:
            raise AdaptiveFeedbackStoreError("ADAPTIVE_FEEDBACK_READ_FAILED") from exc


class InMemoryAdaptiveFeedbackStore:
    """Small contract-equivalent test double; it is never wired by ``main``."""

    def __init__(self) -> None:
        self._recommendations: dict[tuple[str, str], RecommendationMemoryEntry] = {}
        self._feedback: list[FeedbackEvent] = []
        self._idempotency: dict[tuple[str, str], FeedbackEvent] = {}
        self._portion: list[PortionObservation] = []
        self._catalog: dict[str, dict[str, int]] = {}
        self._shadow_logs: list[ShadowRecommendationLog] = []
        self._lock = asyncio.Lock()

    async def persist_delivery(
        self, entry: RecommendationMemoryEntry, *, shadow_log: ShadowRecommendationLog | None = None
    ) -> RecommendationMemoryEntry:
        async with self._lock:
            key = (entry.owner_user_id, entry.recommendation_id)
            existing = self._recommendations.get(key)
            if existing is not None:
                if existing.candidate_id != entry.candidate_id or existing.selected_policy != entry.selected_policy:
                    raise AdaptiveFeedbackIdentityError("RECOMMENDATION_EVENT_ID_REUSED")
                return existing
            stored = replace(entry, feature_payload=feature_payload_for_entry(entry))
            self._recommendations[key] = stored
            if shadow_log is not None:
                self._shadow_logs.append(replace(shadow_log, recommendation_event_id=entry.recommendation_id))
            return stored

    async def record_feedback(
        self, event: FeedbackEvent, *, corrected_portion_grams: float | None = None
    ) -> FeedbackPersistenceResult:
        if not event.recommendation_id or not event.policy_version or not event.idempotency_key:
            raise AdaptiveFeedbackIdentityError("RECOMMENDATION_FEEDBACK_IDENTITY_REQUIRED")
        if event.event_type is FeedbackEventType.SHOWN:
            raise AdaptiveFeedbackIdentityError("EXPOSURE_EVENT_SERVER_ONLY")
        if event.event_type is FeedbackEventType.ACTUALLY_CONSUMED:
            raise AdaptiveFeedbackIdentityError("ACTUAL_MEAL_LOG_REQUIRED")
        if event.event_type is FeedbackEventType.PORTION_CORRECTED and (
            corrected_portion_grams is None or corrected_portion_grams <= 0
        ):
            raise AdaptiveFeedbackIdentityError("PORTION_CORRECTION_GRAMS_REQUIRED")
        async with self._lock:
            recommendation = self._recommendations.get((event.owner_user_id, event.recommendation_id))
            if recommendation is None:
                raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
            if recommendation.candidate_id != event.candidate_id or recommendation.selected_policy != event.policy_version:
                raise AdaptiveFeedbackIdentityError("RECOMMENDATION_FEEDBACK_IDENTITY_MISMATCH")
            previous = self._idempotency.get((event.owner_user_id, event.idempotency_key))
            if previous is not None:
                if not _same_intended_feedback(previous, event):
                    raise AdaptiveFeedbackIdentityError("FEEDBACK_IDEMPOTENCY_KEY_REUSED")
                return FeedbackPersistenceResult(previous, recommendation, True, False, False)
            stored = replace(event, feedback_event_id=event.feedback_event_id or str(uuid4()))
            self._feedback.append(stored)
            self._idempotency[(stored.owner_user_id, stored.idempotency_key)] = stored  # type: ignore[index]
            recommendation = replace(recommendation, outcome_status=stored.event_type.value)
            self._recommendations[(stored.owner_user_id, stored.recommendation_id or "")] = recommendation
            portion = corrected_portion_grams is not None
            if portion:
                self._portion.append(
                    PortionObservation(
                        owner_user_id=stored.owner_user_id, candidate_id=stored.candidate_id,
                        actual_portion_grams=corrected_portion_grams, occurred_at=stored.occurred_at,
                        source_event=FeedbackEventType.PORTION_CORRECTED,
                    )
                )
            gap = _catalog_gap_signal(recommendation, stored)
            if gap is not None:
                counters = self._catalog.setdefault(gap[0], {"request_count": 0, "correction_count": 0})
                counters["request_count" if gap[1] == "INGREDIENT_UNAVAILABLE" else "correction_count"] += 1
            return FeedbackPersistenceResult(stored, recommendation, False, gap is not None, portion)

    async def recommendation_for_owner(self, *, owner_user_id: str, recommendation_id: str) -> RecommendationMemoryEntry | None:
        return self._recommendations.get((owner_user_id, recommendation_id))

    async def feedback_for_recommendation(self, *, owner_user_id: str, recommendation_id: str) -> tuple[FeedbackEvent, ...]:
        if await self.recommendation_for_owner(owner_user_id=owner_user_id, recommendation_id=recommendation_id) is None:
            raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
        return tuple(
            row for row in self._feedback
            if row.owner_user_id == owner_user_id and row.recommendation_id == recommendation_id
        )

    async def recent_recommendations(self, *, owner_user_id: str, limit: int = 20) -> tuple[RecommendationMemoryEntry, ...]:
        rows = [row for (owner, _), row in self._recommendations.items() if owner == owner_user_id]
        rows.sort(key=lambda row: row.shown_at, reverse=True)
        return tuple(rows[:limit])

    async def preference_profile(self, *, owner_user_id: str) -> UserPreferenceProfile:
        events = [row for row in self._feedback if row.owner_user_id == owner_user_id]
        feature_events = []
        for event in events:
            recommendation = self._recommendations.get((owner_user_id, event.recommendation_id or ""))
            if recommendation is not None:
                feature_events.append((event, _features(event.candidate_id, recommendation.dish, recommendation.feature_payload)))
        return PreferenceProfileBuilder().build_from_feature_events(
            owner_user_id=owner_user_id, feature_events=feature_events
        )

    async def portion_prior(self, *, owner_user_id: str, candidate_id: str) -> PortionPrior | None:
        return PortionLearning().build_prior(
            owner_user_id=owner_user_id, candidate_id=candidate_id, observations=self._portion
        )

    async def catalog_gap_observations(self) -> tuple[CatalogGapObservation, ...]:
        return tuple(
            CatalogGapObservation(
                normalized_query=key, request_count=values["request_count"], correction_count=values["correction_count"]
            )
            for key, values in sorted(self._catalog.items())
        )

    async def shadow_bandit_logs(self) -> tuple[ShadowRecommendationLog, ...]:
        return tuple(self._shadow_logs)


__all__ = [
    "AdaptiveFeedbackIdentityError",
    "AdaptiveFeedbackNotFound",
    "AdaptiveFeedbackStoreError",
    "AdaptiveShadowSqlStore",
    "FeedbackPersistenceResult",
    "InMemoryAdaptiveFeedbackStore",
    "feature_payload_for_entry",
]
