"""Selection order through real catalog projections; development/shadow only."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.nutrition.adaptive.contracts import ConstraintContext
from modules.nutrition.adaptive.delivery import canonical_catalog_reference
from modules.nutrition.adaptive.eligibility import CandidateEligibilityGate, ExclusionReason
from modules.nutrition.adaptive.intelligence import (
    CandidateSourceType,
    PreferenceDimension,
    PreferenceEvidence,
    PreferenceSource,
    RankingReasonCode,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    UserPreferenceProfile,
)
from modules.nutrition.adaptive.request_policy import CurrentRequest
from services.agent.tools.dish import suggest_dish


OWNER = "selection-order-test-owner"
NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def candidates():
    return {
        name: canonical_catalog_reference(
            suggest_dish(meal_type=meal, target_kcal=400, query=query)
        )
        for name, meal, query in (
            ("chicken", "breakfast", "pho ga"),
            ("beef", "breakfast", "pho bo"),
            ("fish", "dinner", "ca kho"),
        )
    }


def context(**kwargs):
    return RecommendationContext(owner_user_id=OWNER, evaluated_at=NOW, **kwargs)


def history(candidate):
    return (
        RecommendationMemoryEntry(
            recommendation_id="selection-order-test-exposure",
            owner_user_id=OWNER,
            candidate_id=candidate.candidate_id,
            dish=candidate.title,
            source_type=CandidateSourceType.LOCAL_CANONICAL,
            shown_at=NOW - timedelta(hours=1),
        ),
    )


def profile(liked, disliked):
    return UserPreferenceProfile(
        owner_user_id=OWNER,
        policy_version="PREFERENCE_WEIGHT_POLICY_V1",
        evidence=tuple(
            PreferenceEvidence(
                dimension=PreferenceDimension.DISH,
                value=candidate.title,
                affinity=affinity,
                confidence=1.0,
                source=PreferenceSource.EXPLICIT_FEEDBACK,
                updated_at=NOW,
                evidence_count=5,
            )
            for candidate, affinity in ((liked, 1.0), (disliked, -1.0))
        ),
        insufficient_evidence=False,
    )


def test_valid_catalog_allergen_labels_reach_the_allergy_filter(candidates):
    fish = candidates["fish"]
    gate = CandidateEligibilityGate()
    assert gate.evaluate(fish, owner_user_id=OWNER).eligible
    rejected = gate.evaluate(
        fish,
        owner_user_id=OWNER,
        constraints=ConstraintContext(allergen_exclusions=frozenset({"FISH"})),
    )
    assert rejected.reasons == (ExclusionReason.ALLERGY_VIOLATION,)


@pytest.mark.parametrize("missing_field", ["allergen_ids", "dietary_tags"])
def test_missing_canonical_safety_metadata_is_still_rejected(candidates, missing_field):
    fish = replace(candidates["fish"], **{missing_field: ()})
    result = CandidateEligibilityGate().evaluate(fish, owner_user_id=OWNER)
    assert result.reasons == (ExclusionReason.INVALID_CANONICAL_REFERENCE,)


@pytest.mark.parametrize("request_format", ["typed", "legacy_title", "current_sentence"])
def test_current_dish_overrides_learned_dislike_and_repetition(candidates, request_format):
    chicken, beef = candidates["chicken"], candidates["beef"]
    request_fields = {
        "typed": {"current_request": CurrentRequest(requested_dish=chicken.title)},
        "legacy_title": {"stated_dish_intent": chicken.title},
        "current_sentence": {"stated_dish_intent": f"Hôm nay tôi muốn ăn lại {chicken.title}"},
    }[request_format]
    ranker = RecommendationRankerV2()
    preference = profile(beef, chicken)
    unseen = ranker.rank(
        (beef, chicken), context=context(**request_fields), preference_profile=preference
    )
    repeated = ranker.rank(
        (beef, chicken),
        context=context(recent_recommendations=history(chicken), **request_fields),
        preference_profile=preference,
    )
    assert [row.candidate.candidate_id for row in repeated] == [chicken.candidate_id]
    assert repeated[0].components.recent_repetition_penalty == 0
    assert repeated[0].score == unseen[0].score
    assert RankingReasonCode.DIVERSITY_PROTEIN_ROTATION not in repeated[0].reason_codes


def test_preferences_rank_eligible_candidates_before_final_rotation(candidates):
    chicken, beef = candidates["chicken"], candidates["beef"]
    ranker = RecommendationRankerV2()
    preference = profile(beef, chicken)
    initial = ranker.rank(
        (chicken, beef), context=context(), preference_profile=preference
    )
    assert initial[0].candidate.candidate_id == beef.candidate_id
    rotated = ranker.rank(
        (chicken, beef),
        context=context(recent_recommendations=history(beef)),
        preference_profile=preference,
    )
    assert rotated[0].candidate.candidate_id == chicken.candidate_id


def test_current_food_exclusion_wins_over_a_strong_learned_like(candidates):
    chicken, beef = candidates["chicken"], candidates["beef"]
    ranked = RecommendationRankerV2().rank(
        (beef, chicken),
        context=context(current_request=CurrentRequest(avoid_foods=("beef",))),
        preference_profile=profile(beef, chicken),
    )
    assert [row.candidate.candidate_id for row in ranked] == [chicken.candidate_id]


@pytest.mark.parametrize(
    ("constraints", "reason"),
    [
        (ConstraintContext(allergen_exclusions=frozenset({"FISH"})), ExclusionReason.ALLERGY_VIOLATION),
        (ConstraintContext(dietary_exclusions=frozenset({"no_fish"})), ExclusionReason.RESTRICTION_VIOLATION),
    ],
)
def test_explicit_request_cannot_bypass_safety_or_silently_substitute(candidates, constraints, reason):
    fish, chicken = candidates["fish"], candidates["chicken"]
    result = RecommendationRankerV2().rank_with_diagnostics(
        (fish, chicken),
        context=context(
            constraints=constraints,
            current_request=CurrentRequest(requested_dish=fish.title),
        ),
        preference_profile=profile(fish, chicken),
    )
    assert result.status == "NO_ELIGIBLE_CANDIDATE_FOR_EXPLICIT_REQUEST"
    assert result.ranked == ()
    assert result.exclusions[0].reasons == (reason,)


@pytest.mark.parametrize("invalid_kind", ["identity", "source", "nutrition", "restriction"])
def test_identity_and_safety_are_checked_before_any_preference_scoring(
    candidates, monkeypatch, invalid_kind
):
    beef, chicken = candidates["beef"], candidates["chicken"]
    constraints = ConstraintContext()
    if invalid_kind == "identity":
        beef = replace(beef, candidate_id="invalid-candidate-id")
    elif invalid_kind == "source":
        beef = replace(beef, source=replace(beef.source, source_recipe_id="unknown-dish"))
    elif invalid_kind == "nutrition":
        nutrition = replace(beef.canonical_nutrition, energy_kcal=-1)
        beef = replace(
            beef,
            canonical_nutrition=nutrition,
            evidence=replace(beef.evidence, calculated_nutrition=nutrition).with_hash(),
        )
    else:
        constraints = ConstraintContext(dietary_exclusions=frozenset({"no_beef"}))

    scored = []
    original_affinity = UserPreferenceProfile.affinity_for

    def observe_affinity(self, features, now=None):
        scored.append(features.candidate_id)
        return original_affinity(self, features, now)

    monkeypatch.setattr(UserPreferenceProfile, "affinity_for", observe_affinity)
    result = RecommendationRankerV2().rank_with_diagnostics(
        (beef, chicken),
        context=context(constraints=constraints),
        preference_profile=profile(beef, chicken),
    )
    assert [row.candidate.candidate_id for row in result.ranked] == [chicken.candidate_id]
    assert scored == [chicken.candidate_id]
    assert result.exclusions[0].candidate_id == beef.candidate_id
