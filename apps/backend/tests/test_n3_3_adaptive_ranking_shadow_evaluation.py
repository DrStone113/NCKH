"""N3.3 focused synthetic shadow regressions, not a research benchmark."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from modules.nutrition.adaptive.contracts import (
    CandidateSource,
    CandidateStatus,
    ConstraintContext,
    FeedbackEvent,
    FeedbackEventType,
    FeedbackRejectionReason,
    RawIngredient,
    TrustDomain,
)
from modules.nutrition.adaptive.engine import CanonicalIngredientMapper, RecipePortionFitter, build_recipe_candidate
from modules.nutrition.adaptive.eligibility import CandidateEligibilityGate
from modules.nutrition.adaptive.intelligence import (
    CandidateSourceType,
    ConfirmedPreference,
    PortionLearning,
    PortionObservation,
    PreferenceDimension,
    PreferenceProfileBuilder,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    features_for,
)
from modules.nutrition.adaptive.shadow_evaluation import (
    BASELINE_RANKER_VERSION,
    N3_3_DEVELOPMENT_LABEL,
    ComparisonStatus,
    ShadowComparisonScenario,
    evaluate_shadow_comparison as _evaluate_shadow_comparison,
    frozen_ranking_baselines,
    n3_3_development_scenarios,
    observed_feedback_metrics,
    OBSERVED_USER,
    SYNTHETIC_DEVELOPMENT,
)


def _foods() -> tuple[dict[str, object], ...]:
    return (
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
                "food_id": "tofu",
                "name": "Tofu",
                "energy_kcal": 76.0,
                "protein": 8.0,
                "carbohydrates": 1.9,
                "fat": 4.8,
                "allergen_ids": [],
                "objective_tags": [],
                "canonical_description": {"state": "COOKED"},
            },
        )


def _mapper() -> CanonicalIngredientMapper:
    return CanonicalIngredientMapper(_foods())


def _candidate(title: str, protein: str = "Chicken breast", *, include_rice: bool = True):
    state = "COOKED"
    ingredients = (RawIngredient(protein, 100, "g", state),)
    if include_rice:
        ingredients += (RawIngredient("Rice", 100, "g", state),)
    base = build_recipe_candidate(
        trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        title=title,
        source=CandidateSource("CURATED_EXTERNAL", "NIN_CURATED_RECIPE_REFERENCE"),
        raw_ingredients=ingredients,
        mapper=_mapper(),
    )
    return replace(base, candidate_id=str(uuid5(NAMESPACE_URL, f"n33-synthetic:{title}")), created_at="2026-09-07T00:00:00+00:00", trust_domain=TrustDomain.STAGING_RECIPE, status=CandidateStatus.SHADOW_ELIGIBLE, quality_score=1.0)


def _profile(*events: FeedbackEvent, confirmed: tuple[ConfirmedPreference, ...] = ()):
    candidates = {event.candidate_id: _CANDIDATES[event.candidate_id] for event in events}
    return PreferenceProfileBuilder().build(
        owner_user_id="owner",
        events=events,
        candidates=candidates,
        confirmed=confirmed,
        now=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


_CHICKEN = _candidate("Chicken rice")
_FISH = _candidate("Fish rice", "Fish fillet")
_TOFU = _candidate("Tofu bowl", "Tofu", include_rice=False)
_CANDIDATES = {item.candidate_id: item for item in (_CHICKEN, _FISH, _TOFU)}
_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _ranker_for(candidates) -> RecommendationRankerV2:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    return RecommendationRankerV2(
        eligibility_gate=CandidateEligibilityGate(
            foods=_foods(),
            dishes=(),
            candidate_lookup=lambda candidate_id, _owner: by_id.get(candidate_id),
        )
    )


def evaluate_shadow_comparison(scenario):
    owned = replace(scenario, owner_user_id="owner")
    return _evaluate_shadow_comparison(
        owned,
        ranker=_ranker_for(owned.candidates),
    )


def test_n3_3_freezes_the_existing_components_without_creating_a_new_authority():
    inventory = {item.component: item for item in frozen_ranking_baselines()}

    assert tuple(inventory) == (
        "BASELINE_RANKER",
        "ADAPTIVE_RANKER",
        "DIVERSITY_RERANKER",
        "SHADOW_BANDIT_POLICY",
    )
    assert inventory["BASELINE_RANKER"].version == BASELINE_RANKER_VERSION
    assert inventory["BASELINE_RANKER"].configuration["adaptive_authoritative"] is False
    assert inventory["SHADOW_BANDIT_POLICY"].configuration["controls_production"] is False
    assert inventory["SHADOW_BANDIT_POLICY"].configuration["counterfactual_policy_evaluation"] == "NOT_SUPPORTED_WITHOUT_VALID_PROPENSITIES"


def test_n3_3_development_set_is_focused_synthetic_and_not_an_acceptance_benchmark():
    scenarios = n3_3_development_scenarios()

    assert len(scenarios) == 12
    assert {scenario.label for scenario in scenarios} == {N3_3_DEVELOPMENT_LABEL}
    assert {scenario.scenario_id for scenario in scenarios} == {
        "N33_STRONG_LIKE",
        "N33_STRONG_DISLIKE",
        "N33_NOT_TODAY",
        "N33_COLD_START",
        "N33_CONFLICTING_PREFERENCES",
        "N33_EXPLICIT_CURRENT_REQUEST",
        "N33_DIVERSITY_PRESSURE",
        "N33_ALLERGY_CONFLICT",
        "N33_DIET_RESTRICTION_CONFLICT",
        "N33_PORTION_CORRECTION",
        "N33_CANDIDATE_UNAVAILABLE",
        "N33_STALE_PREFERENCE",
    }


def test_strong_like_and_dislike_are_compared_as_distinct_soft_signals():
    liked_profile = _profile(
        *(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True) for _ in range(5))
    )
    like_result = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_STRONG_LIKE",
            candidates=(_TOFU, _FISH),
            context=RecommendationContext(),
            baseline_ranked_candidate_ids=(_TOFU.candidate_id, _FISH.candidate_id),
            preference_profile=liked_profile,
            preferred_candidate_id=_FISH.candidate_id,
        )
    )
    disliked_profile = _profile(
        *(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.DISLIKED, _NOW, explicit=True) for _ in range(5))
    )
    dislike_result = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_STRONG_DISLIKE",
            candidates=(_TOFU, _FISH),
            context=RecommendationContext(),
            baseline_ranked_candidate_ids=(_FISH.candidate_id, _TOFU.candidate_id),
            preference_profile=disliked_profile,
            disliked_candidate_id=_FISH.candidate_id,
        )
    )

    assert like_result.preferred_candidate_promotion is ComparisonStatus.IMPROVED
    assert like_result.status is ComparisonStatus.IMPROVED
    assert dislike_result.disliked_candidate_demotion is ComparisonStatus.IMPROVED
    assert dislike_result.status is ComparisonStatus.IMPROVED


def test_negative_feedback_keeps_not_today_and_unavailable_out_of_durable_dislike():
    not_today = FeedbackEvent(
        "owner",
        _FISH.candidate_id,
        FeedbackEventType.REJECTED,
        _NOW,
        explicit=True,
        reason_code=FeedbackRejectionReason.NOT_TODAY,
    )
    unavailable = FeedbackEvent(
        "owner",
        _FISH.candidate_id,
        FeedbackEventType.REJECTED,
        _NOW,
        explicit=True,
        reason_code=FeedbackRejectionReason.INGREDIENT_UNAVAILABLE,
    )

    for event in (not_today, unavailable):
        profile = _profile(event)
        assert profile.evidence == ()
        assert profile.insufficient_evidence is True


def test_cold_start_conflict_and_stale_evidence_degrade_without_fabricated_preferences():
    cold = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_COLD_START",
            candidates=(_CHICKEN, _FISH),
            context=RecommendationContext(),
            baseline_ranked_candidate_ids=(_CHICKEN.candidate_id, _FISH.candidate_id),
        )
    )
    conflicting = _profile(
        FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True),
        confirmed=(ConfirmedPreference(PreferenceDimension.DISH, _FISH.title, -1.0, _NOW),),
    )
    stale = _profile(
        FeedbackEvent(
            "owner",
            _FISH.candidate_id,
            FeedbackEventType.LIKED,
            _NOW - timedelta(days=180),
            explicit=True,
        )
    )

    assert cold.status is ComparisonStatus.NOT_APPLICABLE
    assert conflicting.conflict_codes == ("PREFERENCE_CONFLICT",)
    assert conflicting.affinity_for(features_for(_FISH), _NOW) == (-1.0, True)
    assert 0.0 < stale.affinity_for(features_for(_FISH), _NOW)[0] < 0.1


def test_current_request_remediation_is_verified_without_rewriting_history():
    profile = _profile(
        *(
            FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True)
            for _ in range(5)
        )
    )
    result = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_EXPLICIT_CURRENT_REQUEST",
            candidates=(_TOFU, _FISH),
            context=RecommendationContext(stated_dish_intent=_TOFU.title),
            baseline_ranked_candidate_ids=(_TOFU.candidate_id, _FISH.candidate_id),
            preference_profile=profile,
            explicit_request_candidate_id=_TOFU.candidate_id,
            expected_valid_candidate_ids=frozenset({_TOFU.candidate_id}),
            canonical_food_ids=frozenset({"rice", "chicken", "fish", "tofu"}),
        )
    )

    assert result.explicit_request_precedence is ComparisonStatus.UNCHANGED
    assert result.adaptive_top_candidate_id == _TOFU.candidate_id

    historical = development_evidence()
    historical_by_id = {
        row["scenario_id"]: row for row in historical["comparisons"]
    }
    assert (
        historical_by_id["N33_EXPLICIT_CURRENT_REQUEST"][
            "explicit_request_precedence"
        ]
        == ComparisonStatus.REGRESSED
    )
    assert result.status is ComparisonStatus.UNCHANGED


def test_diversity_hard_constraints_and_portion_evidence_remain_scoped():
    recent = RecommendationMemoryEntry(
        recommendation_id="recent-chicken",
        owner_user_id="owner",
        candidate_id=_CHICKEN.candidate_id,
        dish=_CHICKEN.title,
        source_type=CandidateSourceType.STAGING_EXTERNAL,
        shown_at=_NOW,
        primary_protein=features_for(_CHICKEN).primary_protein,
    )
    diversity = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_DIVERSITY_PRESSURE",
            candidates=(_CHICKEN, _FISH),
            context=RecommendationContext(recent_recommendations=(recent,)),
            baseline_ranked_candidate_ids=(_CHICKEN.candidate_id, _FISH.candidate_id),
        )
    )
    allergy = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_ALLERGY_CONFLICT",
            candidates=(_CHICKEN, _FISH),
            context=RecommendationContext(constraints=ConstraintContext(allergen_exclusions=frozenset({"FISH"}))),
            baseline_ranked_candidate_ids=(_CHICKEN.candidate_id, _FISH.candidate_id),
            preference_profile=_profile(
                FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True)
            ),
        )
    )
    restriction = evaluate_shadow_comparison(
        ShadowComparisonScenario(
            scenario_id="N33_DIET_RESTRICTION_CONFLICT",
            candidates=(_CHICKEN, _TOFU),
            context=RecommendationContext(constraints=ConstraintContext(dietary_exclusions=frozenset({"vegetarian"}))),
            baseline_ranked_candidate_ids=(_TOFU.candidate_id, _CHICKEN.candidate_id),
        )
    )
    prior = PortionLearning().build_prior(
        owner_user_id="owner",
        candidate_id=_CHICKEN.candidate_id,
        observations=(
            PortionObservation("owner", _CHICKEN.candidate_id, 220, _NOW),
            PortionObservation("owner", _CHICKEN.candidate_id, 240, _NOW + timedelta(days=1)),
        ),
    )

    assert diversity.recent_repeat_reduction is ComparisonStatus.IMPROVED
    assert diversity.diversity_change is not None and diversity.diversity_change > 0
    assert allergy.adaptive_ranked_candidate_ids == (_CHICKEN.candidate_id,)
    assert allergy.hard_constraint_violations == 0
    assert restriction.adaptive_ranked_candidate_ids == (_TOFU.candidate_id,)
    assert prior is not None and prior.preferred_scale(200) == 1.15


def test_observed_metrics_require_provenance_identity_and_a_reporting_minimum():
    empty = observed_feedback_metrics((), ())
    memory = (
        RecommendationMemoryEntry("r1", "owner-a", _CHICKEN.candidate_id, _CHICKEN.title, CandidateSourceType.STAGING_EXTERNAL, _NOW),
        RecommendationMemoryEntry("r2", "owner-a", _FISH.candidate_id, _FISH.title, CandidateSourceType.STAGING_EXTERNAL, _NOW + timedelta(minutes=1)),
    )
    feedback = (
        FeedbackEvent("owner-a", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True),
        FeedbackEvent(
            "owner-a",
            _FISH.candidate_id,
            FeedbackEventType.REJECTED,
            _NOW,
            reason_code=FeedbackRejectionReason.INGREDIENT_UNAVAILABLE,
        ),
        FeedbackEvent("owner-a", _FISH.candidate_id, FeedbackEventType.PORTION_CORRECTED, _NOW),
    )
    # These are synthetic metric-plumbing tests, never observed evidence.
    bound_feedback = tuple(replace(
        event, recommendation_id="r2", policy_version="BASELINE_RANKER",
        feedback_event_id=f"f{i}", occurred_at=_NOW + timedelta(minutes=2),
    ) for i, event in enumerate(feedback))
    origins = dict.fromkeys(("r1", "r2"), OBSERVED_USER)
    unknown = observed_feedback_metrics(memory, bound_feedback)
    assert unknown.feedback_event_count == 0
    assert unknown.excluded_feedback_count == 3
    assert unknown.excluded_recommendations_by_origin == {"UNVERIFIED": 2}
    assert observed_feedback_metrics(memory, bound_feedback, provenance_by_recommendation=origins).like_rate is None
    assert observed_feedback_metrics(memory, bound_feedback, provenance_by_recommendation=origins, minimum_reporting_denominator=30).like_rate is None
    metrics = observed_feedback_metrics(memory, bound_feedback, provenance_by_recommendation=origins, minimum_reporting_denominator=2)

    assert empty.like_rate is None
    assert empty.candidate_diversity is None
    assert empty.dish_concentration is None
    assert empty.users_with_feedback == 0
    assert metrics.recommendation_exposure_count == 2
    assert metrics.feedback_event_count == 3
    assert metrics.users_with_feedback == 1
    assert metrics.like_rate == 0.5
    assert metrics.reject_rate == 0.5
    assert metrics.catalog_gap_rate == 0.5
    assert metrics.portion_correction_frequency == 0.5
    assert metrics.dish_concentration == 0.5
    duplicate = observed_feedback_metrics(memory, bound_feedback * 3, provenance_by_recommendation=origins, minimum_reporting_denominator=2)
    assert duplicate.like_rate == 0.5 and duplicate.feedback_event_count == 3
    mixed = observed_feedback_metrics(memory, bound_feedback, provenance_by_recommendation={"r1": OBSERVED_USER, "r2": SYNTHETIC_DEVELOPMENT}, minimum_reporting_denominator=2)
    assert mixed.recommendation_exposure_count == 1 and mixed.feedback_event_count == 0
    assert mixed.like_rate is None


@pytest.mark.parametrize("field,value", [
    ("owner_user_id", "foreign"), ("candidate_id", "foreign"),
    ("policy_version", "wrong"), ("recommendation_id", "missing"),
    ("feedback_event_id", None), ("occurred_at", _NOW - timedelta(days=1)),
])
def test_feedback_metrics_exclude_wrong_or_future_exposure_binding(field, value):
    entry = RecommendationMemoryEntry("r", "owner", _FISH.candidate_id, "Fish", CandidateSourceType.STAGING_EXTERNAL, _NOW)
    event = FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, recommendation_id="r", policy_version=entry.selected_policy, feedback_event_id="f")
    result = observed_feedback_metrics((entry,), (replace(event, **{field: value}),), provenance_by_recommendation={"r": OBSERVED_USER})
    assert result.feedback_event_count == 0 and result.excluded_feedback_count == 1


def test_shadow_evaluator_rejects_foreign_owner_learning_and_personal_candidates():
    scenario = ShadowComparisonScenario("privacy", (_FISH,), RecommendationContext(), (_FISH.candidate_id,), owner_user_id="owner")
    foreign = replace(_profile(), owner_user_id="foreign")
    with pytest.raises(ValueError, match="FOREIGN_PREFERENCE_PROFILE"):
        _evaluate_shadow_comparison(replace(scenario, preference_profile=foreign))
    with pytest.raises(ValueError, match="FOREIGN_PERSONAL_CANDIDATE"):
        _evaluate_shadow_comparison(replace(scenario, candidates=(replace(_FISH, owner_user_id="foreign", trust_domain=TrustDomain.PERSONAL_RECIPE),)))
    memory = RecommendationMemoryEntry("private", "foreign", _FISH.candidate_id, _FISH.title, CandidateSourceType.STAGING_EXTERNAL, _NOW)
    with pytest.raises(ValueError, match="FOREIGN_RECOMMENDATION_MEMORY"):
        _evaluate_shadow_comparison(replace(scenario, context=RecommendationContext(recent_recommendations=(memory,))))


def _legacy_recompute_development_evidence():
    """Original builder retained for forensic review; not current qualification."""
    fish_likes = _profile(*(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW, explicit=True) for _ in range(5)))
    fish_dislikes = _profile(*(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.DISLIKED, _NOW, explicit=True) for _ in range(5)))
    not_today = _profile(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.REJECTED, _NOW, reason_code=FeedbackRejectionReason.NOT_TODAY))
    unavailable = _profile(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.REJECTED, _NOW, reason_code=FeedbackRejectionReason.INGREDIENT_UNAVAILABLE))
    recent = RecommendationMemoryEntry("recent", "owner", _CHICKEN.candidate_id, _CHICKEN.title, CandidateSourceType.STAGING_EXTERNAL, _NOW, primary_protein="chicken")
    conflict = _profile(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW), confirmed=(ConfirmedPreference(PreferenceDimension.DISH, _FISH.title, -1, _NOW),))
    stale = _profile(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW - timedelta(days=180)))
    scenarios = []

    def add(key, candidates, baseline, profile=None, context=RecommendationContext(), valid=None, **expectations):
        scenarios.append(ShadowComparisonScenario(
            key, candidates, context, tuple(item.candidate_id for item in baseline),
            preference_profile=profile, owner_user_id="owner", evaluated_at=_NOW,
            expected_valid_candidate_ids=frozenset(item.candidate_id for item in (valid if valid is not None else candidates)),
            canonical_food_ids=frozenset({"rice", "chicken", "fish", "tofu"}), **expectations,
        ))

    add("N33_STRONG_LIKE", (_TOFU, _FISH), (_TOFU, _FISH), fish_likes, preferred_candidate_id=_FISH.candidate_id)
    add("N33_STRONG_DISLIKE", (_TOFU, _FISH), (_FISH, _TOFU), fish_dislikes, disliked_candidate_id=_FISH.candidate_id)
    add("N33_NOT_TODAY", (_TOFU, _FISH), (_FISH, _TOFU), not_today)
    add("N33_COLD_START", (_CHICKEN, _FISH), (_CHICKEN, _FISH))
    add("N33_CONFLICTING_PREFERENCES", (_TOFU, _FISH), (_FISH, _TOFU), conflict, disliked_candidate_id=_FISH.candidate_id)
    # Interpreted current intent from: "Tôi muốn ăn gà hôm nay".
    add("N33_EXPLICIT_CURRENT_REQUEST", (_CHICKEN, _FISH), (_CHICKEN, _FISH), fish_likes, RecommendationContext(stated_dish_intent=_CHICKEN.title), explicit_request_candidate_id=_CHICKEN.candidate_id)
    add("N33_DIVERSITY_PRESSURE", (_CHICKEN, _FISH), (_CHICKEN, _FISH), context=RecommendationContext(recent_recommendations=(recent,)))
    add("N33_ALLERGY_CONFLICT", (_CHICKEN, _FISH), (_CHICKEN,), fish_likes, RecommendationContext(constraints=ConstraintContext(allergen_exclusions=frozenset({"FISH"}))), valid=(_CHICKEN,))
    add("N33_DIET_RESTRICTION_CONFLICT", (_CHICKEN, _TOFU), (_TOFU,), context=RecommendationContext(constraints=ConstraintContext(dietary_exclusions=frozenset({"vegetarian"}))), valid=(_TOFU,))
    add("N33_PORTION_CORRECTION", (_CHICKEN, _FISH), (_CHICKEN, _FISH), context=RecommendationContext(portion_fit_quality={_CHICKEN.candidate_id: 1, _FISH.candidate_id: .5}))
    add("N33_CANDIDATE_UNAVAILABLE", (_TOFU, _FISH), (_FISH, _TOFU), unavailable)
    add("N33_STALE_PREFERENCE", (_TOFU, _FISH), (_TOFU, _FISH), stale)
    comparisons = [asdict(evaluate_shadow_comparison(scenario)) for scenario in scenarios]

    # Test the requirement independently of the comparator's relative status.
    replay_ranker = _ranker_for((_TOFU, _FISH))
    profile_rows = replay_ranker.rank(
        (_TOFU, _FISH),
        context=RecommendationContext(owner_user_id="owner", evaluated_at=_NOW),
        preference_profile=not_today,
    )
    neutral_rows = replay_ranker.rank(
        (_TOFU, _FISH),
        context=RecommendationContext(owner_user_id="owner", evaluated_at=_NOW),
    )
    recent_dislike = _profile(
        *(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW - timedelta(days=60)) for _ in range(5)),
        FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.DISLIKED, _NOW, explicit=True),
    )
    persisted_affinity_now = fish_likes.affinity_for(features_for(_FISH), _NOW)[0]
    persisted_affinity_later = fish_likes.affinity_for(features_for(_FISH), _NOW + timedelta(days=365))[0]

    # Twenty deterministic stress contexts. This is a counterexample search,
    # not a statistical usage sample or an ideal diversity target.
    baseline_tops, adaptive_tops, b_history = [], [], []
    stress_profile = fish_likes
    for step in range(20):
        baseline_candidate = _TOFU if baseline_tops and baseline_tops[-1] == _FISH.candidate_id else _FISH
        b = replay_ranker.rank(
            (_TOFU, _FISH),
            context=RecommendationContext(
                owner_user_id="owner",
                recent_recommendations=tuple(b_history[-1:]),
                evaluated_at=_NOW + timedelta(minutes=step),
            ),
            preference_profile=stress_profile,
        )[0]
        baseline_tops.append(baseline_candidate.candidate_id)
        adaptive_tops.append(b.candidate.candidate_id)
        b_history.append(RecommendationMemoryEntry(f"stress-{step}", "owner", b.candidate.candidate_id, b.candidate.title, b.source_type, _NOW + timedelta(minutes=step)))
    def concentration(ids):
        return max(Counter(ids).values()) / len(ids)

    observations = tuple(PortionObservation("owner", _CHICKEN.candidate_id, grams, _NOW + timedelta(minutes=i), FeedbackEventType.PORTION_CORRECTED) for i, grams in enumerate((220, 240)))
    prior = PortionLearning().build_prior(owner_user_id="owner", candidate_id=_CHICKEN.candidate_id, observations=observations)
    foreign_prior = PortionLearning().build_prior(owner_user_id="foreign", candidate_id=_CHICKEN.candidate_id, observations=observations)
    before = asdict(_CHICKEN)
    fit = RecipePortionFitter(_mapper()).fit(_CHICKEN, ConstraintContext(target_kcal=300), preferred_serving_scale=prior.preferred_scale(200))
    # A forged exact mapping probes a missing registry check at the ranker
    # boundary. It is never inserted into the canonical catalog or storage.
    invalid = replace(_FISH, mappings=(replace(_FISH.mappings[0], canonical_food_id="N33_UNKNOWN_CANONICAL_ID"),) + _FISH.mappings[1:])
    invalid_probe = evaluate_shadow_comparison(ShadowComparisonScenario(
        "N33_INVALID_REFERENCE_PROBE", (_CHICKEN, invalid), RecommendationContext(), (_CHICKEN.candidate_id,),
        owner_user_id="owner", expected_valid_candidate_ids=frozenset({_CHICKEN.candidate_id}), canonical_food_ids=frozenset({"rice", "chicken", "fish", "tofu"}),
    ))
    probes = {
        "not_today_durable_dislike_created": bool(not_today.evidence),
        "not_today_changes_contextual_ranking": [(r.candidate.candidate_id, r.score) for r in profile_rows] != [(r.candidate.candidate_id, r.score) for r in neutral_rows],
        "unavailable_durable_dislike_created": bool(unavailable.evidence),
        "recent_dislike_against_five_older_likes_affinity": recent_dislike.affinity_for(features_for(_FISH), _NOW)[0],
        "stored_profile_affinity_now": persisted_affinity_now,
        "stored_profile_affinity_after_365_days_without_rebuild": persisted_affinity_later,
        "portion_scale": prior.preferred_scale(200),
        "portion_fit_status": fit.status,
        "canonical_candidate_unchanged": before == asdict(_CHICKEN),
        "foreign_owner_portion_prior": foreign_prior,
    }
    return {
        "label": N3_3_DEVELOPMENT_LABEL, "evidence_origin": SYNTHETIC_DEVELOPMENT,
        "clock": _NOW.isoformat(), "baseline_origin": "SYNTHETIC_ORDER_WITH_SCENARIO_GROUND_TRUTH_NOT_PRODUCTION_CAPTURE",
        "comparisons": comparisons, "requirement_probes": probes,
        "invalid_reference_probe": asdict(invalid_probe),
        "diversity_stress": {
            "contexts": 20, "baseline_policy": "SYNTHETIC_NON_REPEAT_REFERENCE", "baseline_top_ids": baseline_tops,
            "adaptive_top_ids": adaptive_tops, "baseline_dish_concentration": concentration(baseline_tops),
            "adaptive_dish_concentration": concentration(adaptive_tops),
            "baseline_main_protein_concentration": concentration(baseline_tops),
            "adaptive_main_protein_concentration": concentration(adaptive_tops),
            "family_and_cuisine": "NOT_AVAILABLE_IN_FIXTURES",
            "major_regression": len(set(adaptive_tops)) == 1 and len(set(baseline_tops)) > 1,
        },
    }


def development_evidence():
    """Read preserved N3.3 evidence without replaying it through new code."""

    artifact = (
        Path(__file__).resolve().parents[1]
        / "validation"
        / "n3_3"
        / "n3-3-shadow-development-v1.json"
    )
    frozen = json.loads(artifact.read_text(encoding="utf-8"))
    frozen.pop("canonical_catalog_replays", None)
    return frozen


def test_development_replay_is_deterministic_and_exposes_requirement_failures():
    first = development_evidence()
    assert first == development_evidence()
    assert len(first["comparisons"]) == 12
    by_id = {row["scenario_id"]: row for row in first["comparisons"]}
    assert by_id["N33_EXPLICIT_CURRENT_REQUEST"]["explicit_request_precedence"] == ComparisonStatus.REGRESSED
    assert first["requirement_probes"]["not_today_durable_dislike_created"] is False
    assert first["requirement_probes"]["not_today_changes_contextual_ranking"] is False
    assert first["requirement_probes"]["canonical_candidate_unchanged"] is True
    assert first["requirement_probes"]["foreign_owner_portion_prior"] is None
    assert first["invalid_reference_probe"]["hard_constraint_violations"] == 1
    assert first["diversity_stress"]["major_regression"] is True


@pytest.mark.parametrize("kind,expected", [
    (FeedbackEventType.LIKED, .17), (FeedbackEventType.SAVED, .05),
    (FeedbackEventType.ACTUALLY_CONSUMED, .10), (FeedbackEventType.REPEATED_CONSUMPTION, .16),
    (FeedbackEventType.SHOWN, 0), (FeedbackEventType.OPENED, 0),
])
def test_positive_signals_keep_distinct_affinities_and_exposure_is_not_reward(kind, expected):
    profile = _profile(FeedbackEvent("owner", _FISH.candidate_id, kind, _NOW))
    assert profile.affinity_for(features_for(_FISH), _NOW)[0] == expected
    assert profile.insufficient_evidence is True


def test_expired_temporary_fact_uses_replay_time_and_explicit_intent_cannot_override_allergy():
    fact = ConfirmedPreference(PreferenceDimension.DISH, _FISH.title, 1, _NOW, _NOW + timedelta(hours=1))
    scenario = ShadowComparisonScenario(
        "expiry", (_TOFU, _FISH), RecommendationContext(), (_TOFU.candidate_id, _FISH.candidate_id),
        preference_profile=_profile(confirmed=(fact,)), owner_user_id="owner",
    )
    active = evaluate_shadow_comparison(scenario)
    expired = evaluate_shadow_comparison(
        replace(scenario, evaluated_at=_NOW + timedelta(days=1))
    )
    neutral = evaluate_shadow_comparison(replace(scenario, preference_profile=None))
    assert active.adaptive_top_candidate_id == _FISH.candidate_id
    assert expired.adaptive_ranked_candidate_ids == neutral.adaptive_ranked_candidate_ids
    allergy = evaluate_shadow_comparison(replace(scenario, context=RecommendationContext(
        constraints=ConstraintContext(allergen_exclusions=frozenset({"FISH"})), stated_dish_intent=_FISH.title,
    )))
    assert allergy.adaptive_ranked_candidate_ids == ()


@pytest.mark.parametrize("mutation", ["revoked", "missing_nutrition", "incomplete_mapping", "negative_nutrition"])
def test_invalid_candidates_cannot_be_rescued_by_a_strong_preference(mutation):
    invalid = {
        "revoked": replace(_FISH, status=CandidateStatus.REVOKED),
        "missing_nutrition": replace(_FISH, canonical_nutrition=None),
        "incomplete_mapping": replace(_FISH, mappings=()),
        "negative_nutrition": replace(_FISH, canonical_nutrition=replace(_FISH.canonical_nutrition, protein_g=-1)),
    }[mutation]
    profile = _profile(*(FeedbackEvent("owner", _FISH.candidate_id, FeedbackEventType.LIKED, _NOW) for _ in range(5)))
    result = evaluate_shadow_comparison(ShadowComparisonScenario(
        mutation, (_CHICKEN, invalid), RecommendationContext(), (_CHICKEN.candidate_id,),
        preference_profile=profile, expected_valid_candidate_ids=frozenset({_CHICKEN.candidate_id}),
        canonical_food_ids=frozenset({"rice", "chicken", "fish", "tofu"}),
    ))
    assert result.adaptive_ranked_candidate_ids == (_CHICKEN.candidate_id,)
    assert result.hard_constraint_violations == 0
