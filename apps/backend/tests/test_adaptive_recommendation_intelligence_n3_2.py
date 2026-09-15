"""N3.2 engineering-only regression cases, not a research benchmark."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.nutrition.adaptive.contracts import (
    CandidateSource,
    CandidateStatus,
    ConstraintContext,
    FeedbackEvent,
    FeedbackEventType,
    FeedbackRejectionReason,
    IngredientScaleClass,
    RawIngredient,
    TrustDomain,
)
from modules.nutrition.adaptive.development_scenarios import development_scenarios
from modules.nutrition.adaptive.engine import (
    AdaptiveRecipeError,
    CanonicalIngredientMapper,
    RecipePortionFitter,
    build_recipe_candidate,
)
from modules.nutrition.adaptive.eligibility import CandidateEligibilityGate
from modules.nutrition.adaptive.intelligence import (
    CandidateSourceType,
    CatalogGapDetector,
    CatalogGapObservation,
    ConfirmedPreference,
    PortionLearning,
    PortionObservation,
    PreferenceDimension,
    PreferenceProfileBuilder,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    RecommendationReplayEvaluator,
    ReplayInteraction,
    ShadowBanditPolicy,
    ShadowRecommendationLog,
    calculate_learning_quality_metrics,
    classify_recipe_correction,
    features_for,
    hard_safety_invariants,
)
from modules.nutrition.adaptive.repository import AdaptiveRecipeRepository
from modules.nutrition.adaptive.delivery import canonical_catalog_reference
from modules.nutrition.canonical_foods import load_canonical_food_catalog
from modules.nutrition.catalog import load_dish_catalog
from services.agent.tools.dish import suggest_dish


def _foods():
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
        {
            "food_id": "peanut",
            "name": "Peanut",
            "energy_kcal": 567.0,
            "protein": 26.0,
            "carbohydrates": 16.0,
            "fat": 49.0,
            "allergen_ids": ["PEANUT"],
            "objective_tags": ["contains_allergen:PEANUT"],
            "canonical_description": {"state": "RAW"},
        },
    ]


def _mapper() -> CanonicalIngredientMapper:
    return CanonicalIngredientMapper(_foods())


def _candidate(
    *,
    title: str = "Chicken rice",
    protein: str = "Chicken breast",
    domain: TrustDomain = TrustDomain.STAGING_RECIPE,
    status: CandidateStatus = CandidateStatus.SHADOW_ELIGIBLE,
):
    base = build_recipe_candidate(
        trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        title=title,
        source=CandidateSource(
            source_type="CURATED_EXTERNAL",
            source_id="NIN_CURATED_RECIPE_REFERENCE",
        ),
        raw_ingredients=(
            RawIngredient(protein, 100, "g", "COOKED" if protein != "Peanut" else "RAW"),
            RawIngredient("Rice", 100, "g", "COOKED"),
        ),
        mapper=_mapper(),
    )
    return replace(base, trust_domain=domain, status=status, quality_score=1.0)


def _ranker(*candidates) -> RecommendationRankerV2:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    return RecommendationRankerV2(
        eligibility_gate=CandidateEligibilityGate(
            foods=_foods(),
            dishes=(),
            candidate_lookup=lambda candidate_id, _owner: by_id.get(candidate_id),
        )
    )


def test_feedback_taxonomy_is_strength_aware_and_explicit_conflict_wins():
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    fish = _candidate(title="Fish rice", protein="Fish fillet")
    events = [
        FeedbackEvent("u", fish.candidate_id, FeedbackEventType.SHOWN, now),
        FeedbackEvent("u", fish.candidate_id, FeedbackEventType.OPENED, now),
        FeedbackEvent("u", fish.candidate_id, FeedbackEventType.ACTUALLY_CONSUMED, now),
    ]
    profile = PreferenceProfileBuilder().build(
        owner_user_id="u",
        events=events,
        candidates={fish.candidate_id: fish},
        confirmed=(
            ConfirmedPreference(
                PreferenceDimension.INGREDIENT,
                "fish",
                -1.0,
                now,
            ),
        ),
        now=now,
    )

    affinity, explicit = profile.affinity_for(features_for(fish), now)

    assert affinity == -1.0
    assert explicit is True
    assert profile.conflict_codes == ("PREFERENCE_CONFLICT",)
    assert all(item.source.value != "INTERACTION" for item in profile.evidence)


def test_hard_constraints_filter_before_preference_and_rejection_is_contextual():
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    safe = _candidate(title="Chicken rice")
    peanut = _candidate(title="Peanut rice", protein="Peanut")
    ranker = _ranker(peanut, safe)
    profile = PreferenceProfileBuilder().build(
        owner_user_id="u",
        events=[
            FeedbackEvent("u", peanut.candidate_id, FeedbackEventType.LIKED, now, explicit=True),
            FeedbackEvent(
                "u",
                safe.candidate_id,
                FeedbackEventType.REJECTED,
                now,
                explicit=True,
                reason_code=FeedbackRejectionReason.NOT_TODAY,
            ),
        ],
        candidates={safe.candidate_id: safe, peanut.candidate_id: peanut},
        now=now,
    )
    ranked = ranker.rank(
        [peanut, safe],
        context=RecommendationContext(
            owner_user_id="u",
            constraints=ConstraintContext(allergen_exclusions=frozenset({"PEANUT"}), target_kcal=300)
        ),
        preference_profile=profile,
    )

    assert [row.candidate.candidate_id for row in ranked] == [safe.candidate_id]
    # "Not today" did not become a durable negative; any remaining small
    # affinity comes only from the shared rice ingredient in the liked meal.
    assert profile.affinity_for(features_for(safe), now)[0] >= 0.0


def test_diversity_is_soft_and_explicit_same_dish_overrides_it():
    candidate = _candidate(title="Chicken rice")
    features = features_for(candidate)
    recent = RecommendationMemoryEntry(
        recommendation_id="r1",
        owner_user_id="u",
        candidate_id=candidate.candidate_id,
        dish=candidate.title,
        source_type=CandidateSourceType.STAGING_EXTERNAL,
        shown_at=datetime.now(timezone.utc),
        primary_protein=features.primary_protein,
    )
    ranker = _ranker(candidate)

    repeated = ranker.rank(
        [candidate],
        context=RecommendationContext(
            owner_user_id="u", recent_recommendations=(recent,)
        ),
    )[0]
    requested = ranker.rank(
        [candidate],
        context=RecommendationContext(
            owner_user_id="u",
            recent_recommendations=(recent,),
            stated_dish_intent="Chicken rice",
        ),
    )[0]

    assert repeated.components.recent_repetition_penalty == 0.70
    assert requested.components.recent_repetition_penalty == 0.0


def test_source_mix_and_novelty_cannot_promote_external_only_on_novelty():
    canonical = canonical_catalog_reference(
        suggest_dish(meal_type="lunch", target_kcal=400)
    )
    runtime = _candidate(
        title="Runtime chicken rice",
        domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        status=CandidateStatus.VALIDATED,
    )
    by_id = {runtime.candidate_id: runtime}
    ranker = RecommendationRankerV2(
        eligibility_gate=CandidateEligibilityGate(
            foods=(*load_canonical_food_catalog(), *_foods()),
            dishes=load_dish_catalog(),
            candidate_lookup=lambda candidate_id, _owner: by_id.get(candidate_id),
        )
    )
    ranked = ranker.rank([runtime, canonical], context=RecommendationContext())

    assert ranked[0].candidate.candidate_id == canonical.candidate_id
    assert ranked[0].source_type == CandidateSourceType.LOCAL_CANONICAL


def test_portion_learning_uses_actual_observations_and_only_nudges_fitter():
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    candidate = _candidate()
    learning = PortionLearning()
    prior = learning.build_prior(
        owner_user_id="u",
        candidate_id=candidate.candidate_id,
        observations=(
            PortionObservation("u", candidate.candidate_id, 230, now),
            PortionObservation("u", candidate.candidate_id, 250, now + timedelta(days=1)),
        ),
    )
    assert prior is not None
    assert prior.median_observed_grams == 240
    assert prior.preferred_scale(200) == 1.2
    fitter = RecipePortionFitter(
        _mapper(), scale_classes={"chicken": IngredientScaleClass.ANCHOR, "rice": IngredientScaleClass.SCALABLE}
    )
    fit = fitter.fit(candidate, ConstraintContext(target_kcal=300), preferred_serving_scale=prior.preferred_scale(200))
    assert fit.status == "FIT"
    assert candidate.raw_ingredients[0].amount == 100
    with pytest.raises(AdaptiveRecipeError, match="INVALID_PERSONAL_PORTION_PRIOR"):
        fitter.fit(candidate, ConstraintContext(target_kcal=300), preferred_serving_scale=1.5)


def test_recommendation_memory_is_not_consumption_and_repository_stays_private():
    candidate = _candidate()
    repository = AdaptiveRecipeRepository(
        eligibility_foods=_foods(), eligibility_dishes=()
    )
    repository.save_candidate(candidate)
    shown = repository.record_recommendation(
        RecommendationMemoryEntry(
            recommendation_id="r-1",
            owner_user_id="u",
            candidate_id=candidate.candidate_id,
            dish=candidate.title,
            source_type=CandidateSourceType.STAGING_EXTERNAL,
            shown_at=datetime.now(timezone.utc),
        )
    )
    repository.record_feedback(
        FeedbackEvent(
            "u",
            candidate.candidate_id,
            FeedbackEventType.SAVED,
            datetime.now(timezone.utc),
            recommendation_id=shown.recommendation_id,
        )
    )

    assert repository.recent_recommendations(owner_user_id="u")[0].outcome_status == "SAVED"
    assert repository.portion_prior(owner_user_id="u", candidate_id=candidate.candidate_id) is None
    with pytest.raises(AdaptiveRecipeError, match="PORTION_PRIOR_REQUIRES_ACTUAL_CONSUMPTION"):
        repository.record_actual_portion(
            PortionObservation("u", candidate.candidate_id, 200, datetime.now(timezone.utc), FeedbackEventType.PORTION_CORRECTED)
        )
    with pytest.raises(AdaptiveRecipeError, match="FEEDBACK_METADATA_NOT_ALLOWED"):
        repository.record_feedback(
            FeedbackEvent(
                "u",
                candidate.candidate_id,
                FeedbackEventType.INGREDIENT_CORRECTED,
                datetime.now(timezone.utc),
                metadata={"free_text": "private note"},
            )
        )


def test_corrections_gap_queue_bandit_and_replay_are_shadow_only_and_auditable():
    candidate = _candidate()
    personal = replace(candidate, trust_domain=TrustDomain.PERSONAL_RECIPE, owner_user_id="u")
    assert classify_recipe_correction(personal).scope == "PERSONAL_RECIPE_ONLY"
    assert classify_recipe_correction(candidate).scope == "STAGING_EVIDENCE"

    detector = CatalogGapDetector()
    gap = detector.detect(
        [CatalogGapObservation("Bún cá", request_count=4, unmapped_count=2, correction_count=1, regional_relevance=1.0)]
    )[0]
    task_types = {task.task_type for task in detector.tasks_for(gap)}
    assert {"FIND_RECIPE_SOURCE", "RESOLVE_ALIAS", "RESOLVE_INGREDIENT_MAPPING", "VERIFY_SERVING"} <= task_types
    assert "user_id" not in gap.aggregate_evidence

    bandit = ShadowBanditPolicy()
    shown = FeedbackEvent("u", candidate.candidate_id, FeedbackEventType.SHOWN, datetime.now(timezone.utc))
    opened = FeedbackEvent("u", candidate.candidate_id, FeedbackEventType.OPENED, datetime.now(timezone.utc))
    assert bandit.reward_for(shown) is None
    assert bandit.reward_for(opened) is None

    replay = RecommendationReplayEvaluator().evaluate(
        [
            ReplayInteraction(
                candidates=(candidate,),
                context=RecommendationContext(),
                selected_candidate_id=candidate.candidate_id,
                outcome_event=FeedbackEventType.ACTUALLY_CONSUMED,
            )
        ]
    )
    assert replay.hard_constraint_violations == 0
    assert replay.valid_acceptance_outcome_rate == 1.0
    assert ShadowRecommendationLog(
        (candidate.candidate_id,), candidate.candidate_id, "CONTEXTUAL_BANDIT_SHADOW_V1", "fingerprint", 1.0
    ).policy_version == "CONTEXTUAL_BANDIT_SHADOW_V1"


def test_development_scenario_set_is_not_a_frozen_research_dataset():
    scenario_ids = {scenario.scenario_id for scenario in development_scenarios()}
    assert len(scenario_ids) == 15
    assert {"N32_COLD_START", "N32_WEB_UNAVAILABLE", "N32_NO_FEASIBLE"} <= scenario_ids


def test_learning_metrics_are_descriptive_and_all_hard_invariants_remain_zero():
    candidate = _candidate()
    memory = [
        RecommendationMemoryEntry(
            "r1", "u", candidate.candidate_id, candidate.title,
            CandidateSourceType.STAGING_EXTERNAL, datetime.now(timezone.utc),
            primary_protein=features_for(candidate).primary_protein,
        ),
        RecommendationMemoryEntry(
            "r2", "u", candidate.candidate_id, candidate.title,
            CandidateSourceType.STAGING_EXTERNAL, datetime.now(timezone.utc),
            primary_protein=features_for(candidate).primary_protein,
        ),
    ]
    metrics = calculate_learning_quality_metrics(
        recommendation_memory=memory,
        feedback_events=[
            FeedbackEvent("u", candidate.candidate_id, FeedbackEventType.SHOWN, datetime.now(timezone.utc)),
            FeedbackEvent("u", candidate.candidate_id, FeedbackEventType.LIKED, datetime.now(timezone.utc), explicit=True),
            FeedbackEvent("u", candidate.candidate_id, FeedbackEventType.PORTION_CORRECTED, datetime.now(timezone.utc)),
        ],
        viable_candidate_count=2,
        catalog_candidate_count=4,
        catalog_gap_count=3,
    )

    assert metrics.repeat_dish_rate == 1.0
    assert metrics.catalog_coverage == 0.5
    assert metrics.catalog_gap_detection_count == 3
    assert all(value == 0 for value in hard_safety_invariants().values())
