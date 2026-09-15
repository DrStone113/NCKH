"""Focused N3.2.1 delivery/feedback regressions for development shadow only."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from modules.nutrition.adaptive.contracts import (
    CandidateSource,
    CandidateStatus,
    ConstraintContext,
    FeedbackEventType,
    RawIngredient,
    TrustDomain,
)
from modules.nutrition.adaptive.engine import CanonicalIngredientMapper, build_recipe_candidate
from modules.nutrition.adaptive.intelligence import (
    CatalogGapDetector,
    RecommendationContext,
    RecommendationRankerV2,
)
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from modules.nutrition.adaptive.sql_store import InMemoryAdaptiveFeedbackStore
from modules.nutrition.adaptive_router import router
from services.agent.orchestrator import AgentOrchestrator
from services.agent.tools.dish import suggest_dish


@pytest.fixture(autouse=True)
def _strong_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep JWT fixtures deterministic without depending on a developer .env."""

    monkeypatch.setattr(
        settings,
        "jwt_secret",
        "n3-2-1-test-secret-with-at-least-32-bytes",
    )


def _token(owner: str) -> str:
    return jwt.encode({"sub": owner}, settings.jwt_secret, algorithm="HS256")


def _headers(owner: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(owner)}"}


def _foods() -> list[dict[str, object]]:
    return [
            {
                "food_id": "rice",
                "name": "Rice",
                "energy_kcal": 130.0,
                "protein": 2.5,
                "carbohydrates": 28.0,
                "fat": 0.3,
                "allergen_ids": [],
                "objective_tags": [],
                "canonical_description": {"state": "COOKED"},
            },
            {
                "food_id": "chicken",
                "name": "Chicken breast",
                "energy_kcal": 165.0,
                "protein": 31.0,
                "carbohydrates": 0.0,
                "fat": 3.6,
                "allergen_ids": [],
                "objective_tags": ["contains_land_meat"],
                "canonical_description": {"state": "COOKED"},
            },
            {
                "food_id": "fish",
                "name": "Fish fillet",
                "energy_kcal": 120.0,
                "protein": 24.0,
                "carbohydrates": 0.0,
                "fat": 2.0,
                "allergen_ids": ["FISH"],
                "objective_tags": ["contains_fish", "contains_seafood"],
                "canonical_description": {"state": "COOKED"},
            },
        ]


def _mapper() -> CanonicalIngredientMapper:
    return CanonicalIngredientMapper(_foods())


def _repository() -> AdaptiveRecipeRepository:
    return AdaptiveRecipeRepository(
        eligibility_foods=_foods(),
        eligibility_dishes=(),
    )


def _candidate(title: str, protein: str = "Chicken breast"):
    candidate = build_recipe_candidate(
        trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        title=title,
        source=CandidateSource("CURATED_EXTERNAL", "NIN_CURATED_RECIPE_REFERENCE"),
        raw_ingredients=(
            RawIngredient(protein, 100, "g", "COOKED"),
            RawIngredient("Rice", 100, "g", "COOKED"),
        ),
        mapper=_mapper(),
    )
    return replace(
        candidate,
        trust_domain=TrustDomain.STAGING_RECIPE,
        status=CandidateStatus.SHADOW_ELIGIBLE,
        quality_score=1.0,
    )


def _app(repository: AdaptiveRecipeRepository) -> FastAPI:
    app = FastAPI()
    app.state.adaptive_recipe_repository = repository
    app.state.adaptive_feedback_store = InMemoryAdaptiveFeedbackStore()
    app.include_router(router)
    return app


def _deliver(client: TestClient, owner: str, candidate_ids: list[str]) -> dict:
    response = client.post(
        "/api/nutrition/adaptive/recommendations/deliver",
        headers=_headers(owner),
        json={"candidate_ids": candidate_ids, "meal_type": "dinner", "target_kcal": 350},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _feedback_body(delivery: dict, event_type: str, *, metadata: dict | None = None) -> dict:
    recommendation = delivery["recommendation"]
    return {
        "recommendation_event_id": recommendation["recommendation_event_id"],
        "candidate_id": recommendation["candidate_id"],
        "policy_version": recommendation["policy_version"],
        "event_type": event_type,
        "idempotency_key": f"{recommendation['recommendation_event_id']}:{event_type}",
        **({"metadata": metadata} if metadata else {}),
    }


def test_trusted_delivery_has_one_safe_structured_chat_contract():
    repository = _repository()
    candidate = repository.save_candidate(_candidate("Shadow chicken rice"))
    with TestClient(_app(repository)) as client:
        delivered = _deliver(client, "shadow-owner", [candidate.candidate_id])

    recommendation = delivered["recommendation"]
    structured = delivered["structured"]
    action = structured["actions"][0]
    details = action["details"]
    assert delivered["status"] == "DELIVERED_FOR_DEVELOPMENT_SHADOW"
    assert recommendation["candidate_source_type"] == "STAGING_EXTERNAL"
    assert recommendation["feedback_eligible"] is True
    assert {"recommendation_candidate_id", "recommendation_event_id", "recommendation_policy_version"} <= set(details)
    assert details["recommendation_candidate_id"] == recommendation["candidate_id"]
    assert details["display_ingredients"]
    assert "score" not in str(structured).lower()
    assert "raw_source_text" not in str(structured).lower()
    assert repository.recent_recommendations(owner_user_id="shadow-owner")[0].outcome_status == "SHOWN"
    assert repository.feedback_events(owner_user_id="shadow-owner") == ()
    logs = repository.shadow_bandit_logs()
    assert len(logs) == 1
    assert logs[0].production_selected_candidate_id == recommendation["candidate_id"]
    assert logs[0].selection_probability is None


def test_authenticated_chat_tool_result_emits_same_feedback_card_contract():
    repository = AdaptiveRecipeRepository()
    gateway = SimpleNamespace(
        authenticated_principal=True,
        websocket=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    adaptive_recipe_repository=repository,
                    adaptive_feedback_store=InMemoryAdaptiveFeedbackStore(),
                )
            )
        ),
    )
    suggestion = suggest_dish(meal_type="dinner", target_kcal=300)

    structured = asyncio.run(
        AgentOrchestrator._maybe_create_n3_shadow_delivery(
            gateway=gateway,
            owner_user_id="chat-owner",
            suggestion=suggestion,
            arguments={"meal_type": "dinner", "target_kcal": 300},
        )
    )

    assert structured is not None
    details = structured["actions"][0]["details"]
    assert details["recommendation_source_type"] == "LOCAL_CANONICAL"
    assert details["recommendation_event_id"]
    assert details["feedback_eligible"] is True
    assert repository.recent_recommendations(owner_user_id="chat-owner")[0].outcome_status == "SHOWN"


def test_feedback_is_owner_bound_idempotent_and_never_creates_consumption():
    repository = _repository()
    candidate = repository.save_candidate(_candidate("Owner chicken rice"))
    with TestClient(_app(repository)) as client:
        delivered = _deliver(client, "owner-a", [candidate.candidate_id])
        body = _feedback_body(delivered, "LIKED")
        first = client.post(
            "/api/nutrition/adaptive/recommendations/feedback", headers=_headers("owner-a"), json=body
        )
        repeated = client.post(
            "/api/nutrition/adaptive/recommendations/feedback", headers=_headers("owner-a"), json=body
        )
        recovered = client.get(
            f"/api/nutrition/adaptive/recommendations/{body['recommendation_event_id']}",
            headers=_headers("owner-a"),
        )
        foreign = client.post(
            "/api/nutrition/adaptive/recommendations/feedback", headers=_headers("owner-b"), json=body
        )

    assert first.status_code == 200, first.text
    assert first.json()["idempotent"] is False
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert recovered.status_code == 200
    assert recovered.json()["candidate_id"] == candidate.candidate_id
    assert recovered.json()["outcome_status"] == "LIKED"
    assert [event["event_type"] for event in recovered.json()["feedback_events"]] == ["LIKED"]
    # An owner mismatch is deliberately indistinguishable from a missing
    # recommendation event; the API must not disclose another user's card.
    assert foreign.status_code == 404
    events = repository.feedback_events(owner_user_id="owner-a")
    assert len(events) == 1
    assert events[0].event_type == FeedbackEventType.LIKED
    assert repository.recent_recommendations(owner_user_id="owner-a")[0].outcome_status == "LIKED"
    assert repository.shadow_bandit_logs()[0].outcome_event == FeedbackEventType.LIKED
    assert repository.portion_prior(owner_user_id="owner-a", candidate_id=candidate.candidate_id) is None


def test_portion_correction_updates_private_prior_not_actual_meal_state():
    repository = _repository()
    candidate = repository.save_candidate(_candidate("Portion chicken rice"))
    with TestClient(_app(repository)) as client:
        delivered = _deliver(client, "portion-owner", [candidate.candidate_id])
        body = _feedback_body(
            delivered, "PORTION_CORRECTED", metadata={"corrected_quantity_grams": 230}
        )
        first = client.post(
            "/api/nutrition/adaptive/recommendations/feedback", headers=_headers("portion-owner"), json=body
        )
        repeated = client.post(
            "/api/nutrition/adaptive/recommendations/feedback", headers=_headers("portion-owner"), json=body
        )

    assert first.status_code == 200, first.text
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    prior = repository.portion_prior(owner_user_id="portion-owner", candidate_id=candidate.candidate_id)
    assert prior is not None
    assert prior.evidence_count == 1
    assert prior.median_observed_grams == 230
    assert all(
        event.event_type != FeedbackEventType.ACTUALLY_CONSUMED
        for event in repository.feedback_events(owner_user_id="portion-owner")
    )


def test_staging_corrections_create_only_deidentified_catalog_gap_evidence():
    repository = _repository()
    candidate = repository.save_candidate(_candidate("Gap candidate chicken rice"))
    with TestClient(_app(repository)) as client:
        first = _deliver(client, "gap-owner", [candidate.candidate_id])
        corrected = client.post(
            "/api/nutrition/adaptive/recommendations/feedback",
            headers=_headers("gap-owner"),
            json=_feedback_body(first, "RECIPE_CORRECTED"),
        )

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["catalog_gap_signal_recorded"] is True
    assert corrected.json()["correction_route"] == {
        "scope": "STAGING_EVIDENCE",
        "reason_code": "STAGING_EVIDENCE_REVIEW_REQUIRED",
    }
    gaps = CatalogGapDetector().detect(repository.catalog_gap_feedback_observations())
    assert len(gaps) == 1
    assert gaps[0].reason_codes == ("CORRECTION_CLUSTER",)
    assert "owner" not in str(gaps[0].aggregate_evidence).lower()


def test_dislike_changes_future_ranking_but_not_today_and_hard_gate_wins():
    repository = _repository()
    chicken = repository.save_candidate(_candidate("Chicken rank candidate"))
    fish = repository.save_candidate(_candidate("Fish rank candidate", "Fish fillet"))
    with TestClient(_app(repository)) as client:
        first = _deliver(client, "rank-owner", [chicken.candidate_id])
        disliked = client.post(
            "/api/nutrition/adaptive/recommendations/feedback",
            headers=_headers("rank-owner"),
            json=_feedback_body(first, "DISLIKED"),
        )
        assert disliked.status_code == 200, disliked.text
        second = _deliver(client, "rank-owner", [chicken.candidate_id, fish.candidate_id])

    assert second["recommendation"]["candidate_id"] == fish.candidate_id
    profile = repository.build_preference_profile(owner_user_id="rank-owner")
    ranked = RecommendationRankerV2(
        eligibility_gate=repository.ranking_eligibility_gate()
    ).rank(
        [chicken, fish],
        context=RecommendationContext(
            owner_user_id="rank-owner",
            constraints=ConstraintContext(allergen_exclusions=frozenset({"FISH"}))
        ),
        preference_profile=profile,
    )
    assert [row.candidate.candidate_id for row in ranked] == [chicken.candidate_id]
