"""Authenticated, development/shadow N3.2.1 recommendation delivery.

This surface records typed exposure and feedback events only. It neither
creates meal logs nor changes canonical recipes, constraints, or production
ranking.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from config import settings
from modules.nutrition.adaptive.contracts import (
    CandidateStatus,
    ConstraintContext,
    FeedbackEvent,
    FeedbackEventType,
    FeedbackRejectionReason,
)
from modules.nutrition.adaptive.engine import AdaptiveRecipeError
from modules.nutrition.adaptive.delivery import validate_candidate_for_exposure
from modules.nutrition.adaptive.request_policy import CurrentRequest, request_from_current_text
from modules.nutrition.adaptive.intelligence import (
    PortionObservation,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    ShadowBanditPolicy,
    ShadowRecommendationLog,
    classify_recipe_correction,
    features_for,
)
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from modules.nutrition.adaptive.sql_store import (
    AdaptiveFeedbackIdentityError,
    AdaptiveFeedbackNotFound,
    AdaptiveFeedbackStoreError,
)
from modules.plans.v2_router import PlanApiPrincipal, require_plan_principal


router = APIRouter(prefix="/api/nutrition/adaptive", tags=["nutrition-adaptive-shadow"])


class RecommendationDeliveryRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=20)
    meal_type: str | None = Field(default=None, max_length=32)
    target_kcal: float | None = Field(default=None, gt=0, le=5000)
    allergen_exclusions: list[str] = Field(default_factory=list, max_length=30)
    dietary_exclusions: list[str] = Field(default_factory=list, max_length=30)
    stated_dish_intent: str | None = Field(default=None, max_length=120)
    current_request: CurrentRequest | None = None


class RecommendationFeedbackRequest(BaseModel):
    recommendation_event_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    policy_version: str = Field(min_length=1, max_length=160)
    event_type: FeedbackEventType
    idempotency_key: str = Field(min_length=8, max_length=200)
    reason_code: FeedbackRejectionReason | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _repository(request: Request) -> AdaptiveRecipeRepository:
    repository = getattr(request.app.state, "adaptive_recipe_repository", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="ADAPTIVE_RECOMMENDATION_SHADOW_UNAVAILABLE")
    return repository


def _feedback_store(request: Request) -> Any:
    """Return the authoritative N3.2.1 event store, never a best-effort cache."""

    store = getattr(request.app.state, "adaptive_feedback_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="ADAPTIVE_FEEDBACK_PERSISTENCE_UNAVAILABLE")
    return store


def _feature_payload(row: Any) -> dict[str, Any]:
    features = features_for(row.candidate)
    return {
        "dish": features.dish,
        "ingredients": list(features.ingredients),
        "primary_protein": features.primary_protein,
        "cuisine": features.cuisine,
        "preparation": features.preparation,
        "cooking_effort": features.cooking_effort,
        "budget_band": features.budget_band,
    }


def _shadow_enabled() -> None:
    if not settings.adaptive_recommendation_shadow_enabled:
        raise HTTPException(status_code=404, detail="ADAPTIVE_RECOMMENDATION_SHADOW_DISABLED")


def _public_candidate_payload(row: Any, recommendation_event_id: str) -> dict[str, Any]:
    candidate = row.candidate
    nutrition = candidate.canonical_nutrition
    return {
        "recommendation_event_id": recommendation_event_id,
        "candidate_id": candidate.candidate_id,
        "candidate_source_type": row.source_type.value,
        "title": candidate.title,
        "ingredients": [
            mapping.canonical_food_name
            or mapping.raw_ingredient.ingredient_name
            or mapping.raw_ingredient.raw_text
            for mapping in candidate.mappings
        ],
        "calculated_nutrition": {
            "energy_kcal": nutrition.energy_kcal,
            "protein_g": nutrition.protein_g,
            "carbohydrate_g": nutrition.carbohydrate_g,
            "fat_g": nutrition.fat_g,
        },
        "reason_codes": [reason.value for reason in row.reason_codes],
        "feedback_eligible": True,
        "policy_version": row.policy_version,
        "provenance_category": row.source_type.value,
    }


def _structured_chat_payload(
    row: Any, recommendation_event_id: str, *, meal_type: str | None
) -> dict[str, Any]:
    """Project a trusted delivery into the existing structured-chat contract.

    The projection contains only the card fields that Flutter needs. In
    particular it omits rank scores, feature weights, raw source material and
    all private profile/context values.
    """

    candidate = row.candidate
    nutrition = candidate.canonical_nutrition
    assert nutrition is not None  # enforced by RecommendationRankerV2 hard gate
    serving_grams = sum(
        mapping.grams or 0.0
        for mapping in candidate.mappings
        if isinstance(mapping.grams, (int, float)) and mapping.grams > 0
    )
    serving_grams = serving_grams if serving_grams > 0 else 100.0
    per_100g = 100.0 / serving_grams
    return {
        "type": "structured",
        "text": "Đây là gợi ý dinh dưỡng ở chế độ thử nghiệm.",
        "meal_name": candidate.title,
        "actions": [
            {
                "kind": "food",
                "wger_id": 0,
                "name": candidate.title,
                "details": {
                    "dish_name": candidate.title,
                    "meal_type": meal_type or "lunch",
                    "serving_grams": round(serving_grams, 2),
                    "calories": round(nutrition.energy_kcal * per_100g, 4),
                    "protein": round(nutrition.protein_g * per_100g, 4),
                    "carbs": round(nutrition.carbohydrate_g * per_100g, 4),
                    "fat": round(nutrition.fat_g * per_100g, 4),
                    "display_ingredients": [
                        mapping.canonical_food_name
                        or mapping.raw_ingredient.ingredient_name
                        or mapping.raw_ingredient.raw_text
                        for mapping in candidate.mappings
                    ],
                    "recommendation_candidate_id": candidate.candidate_id,
                    "recommendation_event_id": recommendation_event_id,
                    "recommendation_policy_version": row.policy_version,
                    "recommendation_reason_codes": list(row.public_reason_codes()),
                    "recommendation_source_type": row.source_type.value,
                    "feedback_eligible": True,
                    "delivery_mode": "DEVELOPMENT_SHADOW",
                },
            }
        ],
    }


def _assert_trusted_delivery_candidate(candidate: Any) -> None:
    """Keep delivery behind the same typed trust and validation boundary."""

    trusted_statuses = {
        CandidateStatus.VALIDATED,
        CandidateStatus.STAGING,
        CandidateStatus.SHADOW_ELIGIBLE,
    }
    if candidate.status not in trusted_statuses:
        raise AdaptiveRecipeError("CANDIDATE_NOT_VALIDATED_FOR_SHADOW_DELIVERY")
    if candidate.trust_domain.value not in {
        "CANONICAL_PRODUCTION_RECIPE",
        "PERSONAL_RECIPE",
        "STAGING_RECIPE",
        "RUNTIME_EXTERNAL_CANDIDATE",
    }:
        raise AdaptiveRecipeError("CANDIDATE_TRUST_DOMAIN_NOT_DELIVERABLE")


@router.post("/recommendations/deliver")
async def deliver_shadow_recommendation(
    body: RecommendationDeliveryRequest,
    request: Request,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    """Rank trusted repository candidates and record one SHOWN event."""

    _shadow_enabled()
    repository = _repository(request)
    store = _feedback_store(request)
    try:
        candidates = tuple(
            repository.candidate_visible_to_owner(
                candidate_id=candidate_id, owner_user_id=principal.user_id
            )
            for candidate_id in dict.fromkeys(body.candidate_ids)
        )
        context = RecommendationContext(
            owner_user_id=principal.user_id,
            current_request=body.current_request or request_from_current_text(body.stated_dish_intent),
            baseline_ranked_candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
            constraints=ConstraintContext(
                allergen_exclusions=frozenset(body.allergen_exclusions),
                dietary_exclusions=frozenset(body.dietary_exclusions),
                target_kcal=body.target_kcal,
            ),
            meal_type=body.meal_type,
            stated_dish_intent=body.stated_dish_intent,
            recent_recommendations=await store.recent_recommendations(
                owner_user_id=principal.user_id
            ),
        )
        eligibility = repository.ranking_eligibility_gate()
        outcome = RecommendationRankerV2(eligibility_gate=eligibility).rank_with_diagnostics(
            candidates,
            context=context,
            preference_profile=await store.preference_profile(owner_user_id=principal.user_id),
        )
        ranked = outcome.ranked
        if not ranked:
            raise AdaptiveRecipeError(outcome.status)
        # Baseline RankerV2 remains the delivered result. The bandit is logged
        # purely for later shadow analysis and has no control path here.
        selected = ranked[0]
        validate_candidate_for_exposure(selected, owner_user_id=principal.user_id,
                                        gate=eligibility, constraints=context.constraints)
        shadow_decision = ShadowBanditPolicy().choose_shadow(ranked, await store.shadow_bandit_logs())
        candidate_set_ids = tuple(sorted(row.candidate.candidate_id for row in ranked))
        candidate_set_fingerprint = hashlib.sha256(
            "|".join(candidate_set_ids).encode("utf-8")
        ).hexdigest()[:24]
        recommendation_event_id = str(uuid4())
        entry = RecommendationMemoryEntry(
            recommendation_id=recommendation_event_id,
            owner_user_id=principal.user_id,
            candidate_id=selected.candidate.candidate_id,
            dish=selected.candidate.title,
            source_type=selected.source_type,
            shown_at=datetime.now(timezone.utc),
            selected_policy=selected.policy_version,
            context_fingerprint=context.fingerprint(),
            feature_payload=_feature_payload(selected),
        )
        shadow_log = (
            ShadowRecommendationLog(
                candidate_set_ids=candidate_set_ids,
                selected_candidate_id=shadow_decision.selected.candidate.candidate_id,
                policy_version=shadow_decision.policy_version,
                context_fingerprint=candidate_set_fingerprint,
                # The current deterministic policy has no sampled propensity.
                selection_probability=None,
                production_selected_candidate_id=selected.candidate.candidate_id,
                recommendation_event_id=recommendation_event_id,
            )
            if shadow_decision is not None
            else None
        )
        persisted_entry = await store.persist_delivery(entry, shadow_log=shadow_log)
        # Candidate repository is a process-local candidate/cache layer only;
        # no card is emitted until the durable store has read back the event.
        repository.record_recommendation(persisted_entry)
        if shadow_log is not None:
            repository.record_shadow_bandit_log(shadow_log)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdaptiveFeedbackNotFound as exc:
        raise HTTPException(status_code=404, detail="RECOMMENDATION_EVENT_NOT_FOUND") from exc
    except AdaptiveFeedbackIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdaptiveFeedbackStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "DELIVERED_FOR_DEVELOPMENT_SHADOW",
        "recommendation": _public_candidate_payload(selected, recommendation_event_id),
        "structured": _structured_chat_payload(
            selected, recommendation_event_id, meal_type=body.meal_type
        ),
        "production_adaptive_ranking": False,
        "canonical_auto_promotion": False,
        "shadow_bandit_observation_logged": shadow_decision is not None,
    }


@router.post("/recommendations/feedback")
async def record_recommendation_feedback(
    body: RecommendationFeedbackRequest,
    request: Request,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    _shadow_enabled()
    repository = _repository(request)
    store = _feedback_store(request)
    if body.event_type is FeedbackEventType.SHOWN:
        raise HTTPException(status_code=409, detail="EXPOSURE_EVENT_SERVER_ONLY")
    if body.event_type is FeedbackEventType.ACTUALLY_CONSUMED:
        # Consumption must go through the existing explicit meal-log contract;
        # feedback itself never creates actual nutrition history.
        raise HTTPException(status_code=409, detail="ACTUAL_MEAL_LOG_REQUIRED")
    try:
        recommendation = await store.recommendation_for_owner(
            recommendation_id=body.recommendation_event_id,
            owner_user_id=principal.user_id,
        )
        if recommendation is None:
            raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
        if recommendation.candidate_id != body.candidate_id or recommendation.selected_policy != body.policy_version:
            raise AdaptiveRecipeError("RECOMMENDATION_FEEDBACK_IDENTITY_MISMATCH")
        event = repository.validate_feedback_event(
            FeedbackEvent(
                owner_user_id=principal.user_id,
                candidate_id=body.candidate_id,
                event_type=body.event_type,
                occurred_at=datetime.now(timezone.utc),
                explicit=body.event_type in {
                    FeedbackEventType.LIKED,
                    FeedbackEventType.DISLIKED,
                    FeedbackEventType.REJECTED,
                },
                reason_code=body.reason_code,
                metadata=body.metadata,
                recommendation_id=body.recommendation_event_id,
                policy_version=body.policy_version,
                idempotency_key=body.idempotency_key,
            )
        )
        corrected_grams: float | None = None
        if body.event_type == FeedbackEventType.PORTION_CORRECTED:
            grams = body.metadata.get("corrected_quantity_grams") or body.metadata.get("portion_grams")
            try:
                corrected_grams = float(grams)
            except (TypeError, ValueError) as exc:
                raise AdaptiveRecipeError("PORTION_CORRECTION_GRAMS_REQUIRED") from exc
        persisted = await store.record_feedback(event, corrected_portion_grams=corrected_grams)
        event = persisted.feedback
        idempotent = persisted.idempotent
        # Keep the process-local candidate cache coherent for the current
        # request, but it is never the transaction authority or read-back API.
        cache_available = True
        try:
            _, cache_idempotent = repository.record_feedback(event)
            if not idempotent and cache_idempotent:
                raise AdaptiveRecipeError("ADAPTIVE_FEEDBACK_CACHE_IDEMPOTENCY_MISMATCH")
        except AdaptiveRecipeError as cache_error:
            # A process restarted between card display and feedback has no
            # candidate cache.  The durable event/owner binding above remains
            # authoritative, so do not turn a cache miss into false failure.
            if str(cache_error) not in {
                "UNKNOWN_RECIPE_CANDIDATE",
                "PERSONAL_RECIPE_ACCESS_DENIED",
            }:
                raise
            cache_available = False
        catalog_gap_signal_recorded = persisted.catalog_gap_signal_recorded
        if cache_available and not idempotent:
            # This cache powers only in-process development diagnostics. The
            # durable de-identified evidence was already inserted atomically.
            repository.record_catalog_gap_feedback(event)
        correction_route: dict[str, str] | None = None
        if not idempotent and cache_available and body.event_type == FeedbackEventType.PORTION_CORRECTED:
            repository.record_portion_correction(
                PortionObservation(
                    owner_user_id=principal.user_id,
                    candidate_id=body.candidate_id,
                    actual_portion_grams=corrected_grams,
                    occurred_at=event.occurred_at,
                    source_event=FeedbackEventType.PORTION_CORRECTED,
                )
            )
        elif not idempotent and cache_available and body.event_type in {
            FeedbackEventType.INGREDIENT_CORRECTED,
            FeedbackEventType.RECIPE_CORRECTED,
        }:
            candidate = repository.candidate_visible_to_owner(
                candidate_id=body.candidate_id, owner_user_id=principal.user_id
            )
            disposition = classify_recipe_correction(candidate)
            correction_route = {
                "scope": disposition.scope,
                "reason_code": disposition.reason_code,
            }
    except AdaptiveRecipeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdaptiveFeedbackNotFound as exc:
        raise HTTPException(status_code=404, detail="RECOMMENDATION_EVENT_NOT_FOUND") from exc
    except AdaptiveFeedbackIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdaptiveFeedbackStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "RECORDED_FOR_DEVELOPMENT_SHADOW",
        "recommendation_event_id": event.recommendation_id,
        "candidate_id": event.candidate_id,
        "event_type": event.event_type.value,
        "feedback_event_id": event.feedback_event_id,
        "idempotent": idempotent,
        "correction_route": correction_route,
        "catalog_gap_signal_recorded": catalog_gap_signal_recorded,
        "production_adaptive_ranking": False,
        "canonical_auto_promotion": False,
    }


@router.get("/recommendations/{recommendation_event_id}")
async def read_recommendation_feedback_state(
    recommendation_event_id: str,
    request: Request,
    principal: PlanApiPrincipal = Depends(require_plan_principal),
) -> dict[str, Any]:
    """Owner-bound reconnect read; no candidate search or 'latest' fallback."""

    _shadow_enabled()
    _repository(request)  # service availability only; SQL is authoritative below.
    store = _feedback_store(request)
    try:
        recommendation = await store.recommendation_for_owner(
            recommendation_id=recommendation_event_id,
            owner_user_id=principal.user_id,
        )
        if recommendation is None:
            raise AdaptiveFeedbackNotFound("RECOMMENDATION_EVENT_NOT_FOUND")
        events = await store.feedback_for_recommendation(
            owner_user_id=principal.user_id,
            recommendation_id=recommendation_event_id,
        )
    except (AdaptiveRecipeError, AdaptiveFeedbackNotFound) as exc:
        # Do not reveal whether a foreign recommendation id exists.
        raise HTTPException(status_code=404, detail="RECOMMENDATION_EVENT_NOT_FOUND") from exc
    except AdaptiveFeedbackStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "recommendation_event_id": recommendation.recommendation_id,
        "candidate_id": recommendation.candidate_id,
        "policy_version": recommendation.selected_policy,
        "outcome_status": recommendation.outcome_status,
        "feedback_events": [
            {
                "event_type": event.event_type.value,
                "feedback_event_id": event.feedback_event_id,
                "occurred_at": event.occurred_at.isoformat(),
                "reason_code": event.reason_code.value if event.reason_code else None,
            }
            for event in events
        ],
        "production_adaptive_ranking": False,
        "canonical_auto_promotion": False,
    }


__all__ = ["router"]
