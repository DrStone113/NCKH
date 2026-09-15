"""Focused PostgreSQL evidence for durable N3.2.1 feedback.

This is deliberately skipped unless an explicit PostgreSQL 16 development URL
is supplied.  SQLite is not a substitute for this persistence gate.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from modules.nutrition.adaptive.contracts import (
    CandidateSource,
    CandidateStatus,
    FeedbackEvent,
    FeedbackEventType,
    RawIngredient,
    TrustDomain,
)
from modules.nutrition.adaptive.engine import CanonicalIngredientMapper, build_recipe_candidate
from modules.nutrition.adaptive.intelligence import CandidateSourceType, RecommendationMemoryEntry
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from modules.nutrition.adaptive.sql_store import (
    AdaptiveFeedbackIdentityError,
    AdaptiveShadowSqlStore,
)
from modules.nutrition.adaptive_router import router


_LIVE_URL = os.getenv("N3_2_1_LIVE_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not _LIVE_URL, reason="N3_2_1_LIVE_POSTGRES_URL is not configured"
)


def _entry(owner: str, *, candidate_id: str | None = None) -> RecommendationMemoryEntry:
    return RecommendationMemoryEntry(
        recommendation_id=str(uuid4()),
        owner_user_id=owner,
        candidate_id=candidate_id or str(uuid4()),
        dish="Durable chicken rice",
        source_type=CandidateSourceType.STAGING_EXTERNAL,
        shown_at=datetime.now(timezone.utc),
        primary_protein="chicken",
        selected_policy="RECOMMENDATION_RANKER_V2_WEIGHT_POLICY_V1",
        context_fingerprint="123456789012345678901234",
        feature_payload={
            "dish": "Durable chicken rice",
            "ingredients": ["chicken", "rice"],
            "primary_protein": "chicken",
        },
    )


def _event(entry: RecommendationMemoryEntry, *, event_type: FeedbackEventType = FeedbackEventType.DISLIKED) -> FeedbackEvent:
    return FeedbackEvent(
        owner_user_id=entry.owner_user_id,
        candidate_id=entry.candidate_id,
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        explicit=event_type in {FeedbackEventType.DISLIKED, FeedbackEventType.LIKED},
        recommendation_id=entry.recommendation_id,
        policy_version=entry.selected_policy,
        idempotency_key=f"n3-2-1-live-{entry.recommendation_id}-{event_type.value}",
    )


def _headers(owner: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt.encode({'sub': owner}, settings.jwt_secret, algorithm='HS256')}"}


def _api_candidate():
    mapper = CanonicalIngredientMapper(
        [
            {
                "food_id": "api-rice",
                "name": "API rice",
                "energy_kcal": 130.0,
                "protein": 2.5,
                "carbohydrates": 28.0,
                "fat": 0.3,
                "allergen_ids": [],
                "objective_tags": [],
                "canonical_description": {"state": "COOKED"},
            },
            {
                "food_id": "api-chicken",
                "name": "API chicken",
                "energy_kcal": 165.0,
                "protein": 31.0,
                "carbohydrates": 0.0,
                "fat": 3.6,
                "allergen_ids": [],
                "objective_tags": ["contains_land_meat"],
                "canonical_description": {"state": "COOKED"},
            },
        ]
    )
    candidate = build_recipe_candidate(
        trust_domain=TrustDomain.STAGING_RECIPE,
        title="PostgreSQL API chicken rice",
        source=CandidateSource("N3_2_1_TEST", "POSTGRES_API_CONTRACT"),
        raw_ingredients=(
            RawIngredient("API chicken", 100, "g", "COOKED"),
            RawIngredient("API rice", 100, "g", "COOKED"),
        ),
        mapper=mapper,
    )
    return replace(candidate, status=CandidateStatus.SHADOW_ELIGIBLE, quality_score=1.0)


def _api_app(repository: AdaptiveRecipeRepository, store: AdaptiveShadowSqlStore) -> FastAPI:
    app = FastAPI()
    app.state.adaptive_recipe_repository = repository
    app.state.adaptive_feedback_store = store
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_postgres_migration_durable_idempotency_readback_and_owner_boundary():
    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_store = AdaptiveShadowSqlStore(factory)
    second_store = AdaptiveShadowSqlStore(factory)
    owner = f"n3-2-1-durable-{uuid4()}"
    entry = _entry(owner)
    try:
        async with factory() as session:
            migration = await session.execute(
                text(
                    """
                    SELECT 1 FROM schema_migrations
                    WHERE version = '017_adaptive_feedback_persistence_n3_2_1'
                    """
                )
            )
            assert migration.first() is not None
            schema = await session.execute(
                text("SELECT to_regclass('nutrition_personal_portion_corrections_n3_2')")
            )
            assert schema.scalar() == "nutrition_personal_portion_corrections_n3_2"

        await first_store.persist_delivery(entry)
        event = _event(entry)
        results = await asyncio.gather(
            first_store.record_feedback(event),
            second_store.record_feedback(event),
        )
        assert sorted(result.idempotent for result in results) == [False, True]
        feedback = await second_store.feedback_for_recommendation(
            owner_user_id=owner, recommendation_id=entry.recommendation_id
        )
        assert len(feedback) == 1
        assert feedback[0].feedback_event_id
        assert (await second_store.recommendation_for_owner(
            owner_user_id=owner, recommendation_id=entry.recommendation_id
        )).outcome_status == "DISLIKED"
        profile = await second_store.preference_profile(owner_user_id=owner)
        assert any(item.affinity < 0 for item in profile.evidence)
        assert await second_store.recommendation_for_owner(
            owner_user_id="foreign-owner", recommendation_id=entry.recommendation_id
        ) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_portion_catalog_and_rollback_are_transactional():
    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = AdaptiveShadowSqlStore(factory)
    owner = f"n3-2-1-portion-{uuid4()}"
    entry = _entry(owner)
    try:
        await store.persist_delivery(entry)
        portion = _event(entry, event_type=FeedbackEventType.PORTION_CORRECTED)
        portion = FeedbackEvent(
            **{**portion.__dict__, "metadata": {"corrected_quantity_grams": 215}}
        )
        recorded = await store.record_feedback(portion, corrected_portion_grams=215)
        assert recorded.portion_evidence_recorded is True
        prior = await store.portion_prior(owner_user_id=owner, candidate_id=entry.candidate_id)
        assert prior is not None and prior.median_observed_grams == 215

        invalid = _event(_entry(owner), event_type=FeedbackEventType.REJECTED)
        await store.persist_delivery(
            RecommendationMemoryEntry(
                recommendation_id=invalid.recommendation_id or "",
                owner_user_id=owner,
                candidate_id=invalid.candidate_id,
                dish="Rollback candidate",
                source_type=CandidateSourceType.STAGING_EXTERNAL,
                shown_at=datetime.now(timezone.utc),
                selected_policy=invalid.policy_version or "",
            )
        )
        # The legacy schema rule rejects a reason-less rejection. The store
        # must roll back the feedback insert rather than report false success.
        with pytest.raises(Exception):
            await store.record_feedback(invalid)
        assert await store.feedback_for_recommendation(
            owner_user_id=owner, recommendation_id=invalid.recommendation_id or ""
        ) == ()
    finally:
        await engine.dispose()


def test_postgres_authenticated_feedback_api_persists_exact_owner_bound_event():
    """Exercise the production router with PostgreSQL as its event authority."""

    assert _LIVE_URL
    engine = create_async_engine(_LIVE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = AdaptiveShadowSqlStore(factory)
    repository = AdaptiveRecipeRepository()
    candidate = repository.save_candidate(_api_candidate())
    owner = f"n3-2-1-api-{uuid4()}"
    try:
        with TestClient(_api_app(repository, store)) as client:
            delivery = client.post(
                "/api/nutrition/adaptive/recommendations/deliver",
                headers=_headers(owner),
                json={"candidate_ids": [candidate.candidate_id], "meal_type": "dinner", "target_kcal": 350},
            )
            assert delivery.status_code == 200, delivery.text
            recommendation = delivery.json()["recommendation"]
            body = {
                "recommendation_event_id": recommendation["recommendation_event_id"],
                "candidate_id": recommendation["candidate_id"],
                "policy_version": recommendation["policy_version"],
                "event_type": "LIKED",
                "idempotency_key": f"{recommendation['recommendation_event_id']}:LIKED",
            }
            first = client.post("/api/nutrition/adaptive/recommendations/feedback", headers=_headers(owner), json=body)
            repeated = client.post("/api/nutrition/adaptive/recommendations/feedback", headers=_headers(owner), json=body)
            read_back = client.get(
                f"/api/nutrition/adaptive/recommendations/{recommendation['recommendation_event_id']}",
                headers=_headers(owner),
            )
            foreign = client.get(
                f"/api/nutrition/adaptive/recommendations/{recommendation['recommendation_event_id']}",
                headers=_headers("n3-2-1-api-foreign"),
            )

        assert first.status_code == 200, first.text
        assert first.json()["idempotent"] is False
        assert first.json()["feedback_event_id"]
        assert repeated.status_code == 200 and repeated.json()["idempotent"] is True
        assert read_back.status_code == 200
        assert read_back.json()["candidate_id"] == candidate.candidate_id
        assert [event["event_type"] for event in read_back.json()["feedback_events"]] == ["LIKED"]
        assert foreign.status_code == 404
    finally:
        asyncio.run(engine.dispose())
