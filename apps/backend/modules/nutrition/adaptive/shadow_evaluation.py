"""N3.3 deterministic shadow-comparison helpers.

This is a product-engineering evaluation surface, not an online policy and not
a research benchmark.  It receives the authorised baseline order as evidence;
it does not invent or replace the production ``suggest_dish`` decision.  The
adaptive ranker is evaluated read-only against that order and all output is
aggregate-safe.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .contracts import CandidateStatus, FeedbackEvent, FeedbackEventType, RecipeCandidate
from .engine import RecipeQualityGate
from .intelligence import (
    RANKING_POLICY_V2,
    SHADOW_BANDIT_POLICY_V1,
    RankedRecommendation,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    ShadowBanditPolicy,
    UserPreferenceProfile,
    features_for,
)


N3_3_DEVELOPMENT_LABEL = "N3_3_SHADOW_DEVELOPMENT"
SYNTHETIC_DEVELOPMENT = "SYNTHETIC_DEVELOPMENT"
OBSERVED_USER = "VERIFIED_OBSERVED_USER"
BASELINE_RANKER_VERSION = "SUGGEST_DISH_DETERMINISTIC_BASELINE"
DIVERSITY_RERANKER_VERSION = "RECOMMENDATION_RANKER_V2_DIVERSITY_COMPONENT_V1"


class ComparisonStatus(str, Enum):
    IMPROVED = "IMPROVED"
    UNCHANGED = "UNCHANGED"
    REGRESSED = "REGRESSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class FrozenRankingBaseline:
    """Identifies a ranking component without mutating its configuration."""

    component: str
    version: str
    configuration: Mapping[str, object]
    source_paths: tuple[str, ...]
    feature_set: tuple[str, ...]


def frozen_ranking_baselines() -> tuple[FrozenRankingBaseline, ...]:
    """Return the N3.3 baseline inventory in deterministic display order.

    Source digests are intentionally captured by the report-generation step,
    not calculated here: a digest is evidence tied to a checkout, while this
    helper describes the versioned code contract being replayed.
    """

    policy = RecommendationRankerV2().policy
    return (
        FrozenRankingBaseline(
            component="BASELINE_RANKER",
            version=BASELINE_RANKER_VERSION,
            configuration={
                "authoritative_path": "services.agent.tools.dish.suggest_dish",
                "comparison_input": "authorised_baseline_ranked_candidate_ids",
                "adaptive_authoritative": False,
                "order": "preferred_non_recent_pool_else_fallback; region_priority_then_abs_scale_minus_one_then_abs_kcal_error_then_catalog_id",
                "kcal_bounds": [0.7, 1.5],
                "portion_scale_bounds": [0.65, 1.60],
                "delivery_path_caveat": "dedicated N3.2.1 development endpoint already delivers RankerV2; chat preserves suggest_dish",
            },
            source_paths=("apps/backend/services/agent/tools/dish.py",),
            feature_set=("canonical_catalog_filter", "deterministic_portion_scaling"),
        ),
        FrozenRankingBaseline(
            component="ADAPTIVE_RANKER",
            version=RANKING_POLICY_V2,
            configuration={
                "nutrition_weight": policy.nutrition_weight,
                "preference_weight": policy.preference_weight,
                "source_quality_weight": policy.source_quality_weight,
                "mapping_quality_weight": policy.mapping_quality_weight,
                "portion_fit_weight": policy.portion_fit_weight,
                "diversity_weight": policy.diversity_weight,
                "novelty_weight": policy.novelty_weight,
                "cooking_effort_weight": policy.cooking_effort_weight,
                "budget_weight": policy.budget_weight,
                "hard_filter_before_soft_ranking": True,
            },
            source_paths=("apps/backend/modules/nutrition/adaptive/intelligence.py",),
            feature_set=(
                "canonical_nutrition",
                "owner_private_preference_evidence",
                "source_and_mapping_quality",
                "owner_private_portion_fit",
                "recent_recommendation_memory",
                "explicit_dish_intent",
                "effort_and_budget",
            ),
        ),
        FrozenRankingBaseline(
            component="DIVERSITY_RERANKER",
            version=DIVERSITY_RERANKER_VERSION,
            configuration={
                "exact_dish_penalty": 0.70,
                "primary_protein_penalty": 0.35,
                "cuisine_penalty": 0.15,
                "preparation_penalty": 0.12,
                "explicit_same_dish_clears_all_repeat_penalties": True,
                "hard_constraint_bypass": False,
            },
            source_paths=("apps/backend/modules/nutrition/adaptive/intelligence.py",),
            feature_set=("dish", "primary_protein", "cuisine", "preparation", "recent_memory"),
        ),
        FrozenRankingBaseline(
            component="SHADOW_BANDIT_POLICY",
            version=SHADOW_BANDIT_POLICY_V1,
            configuration={
                "observation_only": True,
                "controls_production": False,
                "shown_and_opened_reward": None,
                "counterfactual_policy_evaluation": "NOT_SUPPORTED_WITHOUT_VALID_PROPENSITIES",
            },
            source_paths=(
                "apps/backend/modules/nutrition/adaptive/intelligence.py",
                "apps/backend/modules/nutrition/adaptive_router.py",
            ),
            feature_set=("ranked_valid_candidates", "bound_feedback_outcome", "candidate_set_fingerprint"),
        ),
    )


@dataclass(frozen=True)
class ShadowComparisonScenario:
    """One replayable N3.3 comparison with optional objective expectations.

    ``baseline_ranked_candidate_ids`` must come from the authorised baseline
    capture.  It is deliberately not reconstructed from adaptive scores.
    """

    scenario_id: str
    candidates: tuple[RecipeCandidate, ...]
    context: RecommendationContext
    baseline_ranked_candidate_ids: tuple[str, ...]
    preference_profile: UserPreferenceProfile | None = None
    preferred_candidate_id: str | None = None
    disliked_candidate_id: str | None = None
    explicit_request_candidate_id: str | None = None
    label: str = N3_3_DEVELOPMENT_LABEL
    owner_user_id: str = ""
    evaluated_at: datetime = datetime(2026, 9, 7, tzinfo=timezone.utc)
    expected_valid_candidate_ids: frozenset[str] | None = None
    canonical_food_ids: frozenset[str] | None = None


@dataclass(frozen=True)
class ShadowComparisonResult:
    scenario_id: str
    label: str
    baseline_ranked_candidate_ids: tuple[str, ...]
    adaptive_ranked_candidate_ids: tuple[str, ...]
    baseline_invalid_or_unknown_candidate_ids: tuple[str, ...]
    top_1_identity_change: bool | None
    top_k_overlap: float | None
    preferred_candidate_promotion: ComparisonStatus
    disliked_candidate_demotion: ComparisonStatus
    recent_repeat_reduction: ComparisonStatus
    explicit_request_precedence: ComparisonStatus
    diversity_change: float | None
    constraint_valid_candidate_retention: float
    portion_fit_compatibility: float | None
    hard_constraint_violations: int
    status: ComparisonStatus
    evidence_origin: str
    candidate_set_fingerprint: str
    baseline_top_candidate_id: str | None
    adaptive_top_candidate_id: str | None
    shadow_bandit_candidate_id: str | None
    policy_version: str
    shadow_bandit_policy_version: str
    outcome_binding: str | None
    independent_validity_checked: bool
    baseline_portion_fit: float | None
    portion_fit_change: float | None
    top_k_diversity: Mapping[str, object]


def evaluate_shadow_comparison(
    scenario: ShadowComparisonScenario,
    *,
    top_k: int = 3,
    ranker: RecommendationRankerV2 | None = None,
) -> ShadowComparisonResult:
    """Replay A (captured baseline) against B (adaptive) without selection.

    A candidate absent from B is either unknown or failed the deterministic
    hard gate.  This is disclosed separately instead of silently omitting it
    from the comparison.  A zero hard-violation count means only that the
    adaptive output did not return an invalid candidate in this replay.
    """

    if top_k < 1:
        raise ValueError("top_k must be positive")
    if scenario.label != N3_3_DEVELOPMENT_LABEL:
        raise ValueError("N3_3_SHADOW_DEVELOPMENT_LABEL_REQUIRED")
    candidate_ids = tuple(item.candidate_id for item in scenario.candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("DUPLICATE_CANDIDATE_ID")
    if len(set(scenario.baseline_ranked_candidate_ids)) != len(scenario.baseline_ranked_candidate_ids):
        raise ValueError("DUPLICATE_BASELINE_ID")
    if set(scenario.baseline_ranked_candidate_ids) - set(candidate_ids):
        raise ValueError("BASELINE_CANDIDATE_SNAPSHOT_MISSING")
    if scenario.evaluated_at.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    if scenario.preference_profile and scenario.preference_profile.owner_user_id != scenario.owner_user_id:
        raise ValueError("FOREIGN_PREFERENCE_PROFILE")
    if any(entry.owner_user_id != scenario.owner_user_id for entry in
           scenario.context.recent_recommendations + scenario.context.recently_consumed):
        raise ValueError("FOREIGN_RECOMMENDATION_MEMORY")
    if any(item.owner_user_id and item.owner_user_id != scenario.owner_user_id for item in scenario.candidates):
        raise ValueError("FOREIGN_PERSONAL_CANDIDATE")

    profile = scenario.preference_profile
    if profile is not None:
        # Resolve expiry at the replay clock without changing the frozen ranker.
        profile = replace(profile, confirmed=tuple(
            replace(fact, temporary_until=None) for fact in profile.confirmed
            if fact.is_active(scenario.evaluated_at)
        ))

    active_ranker = ranker or RecommendationRankerV2()
    evaluation_context = replace(
        scenario.context,
        owner_user_id=scenario.owner_user_id,
        evaluated_at=scenario.evaluated_at,
    )
    adaptive_rows = active_ranker.rank(
        scenario.candidates,
        context=evaluation_context,
        preference_profile=profile,
    )
    adaptive_ids = tuple(row.candidate.candidate_id for row in adaptive_rows)
    adaptive_by_id = {row.candidate.candidate_id: row for row in adaptive_rows}
    baseline_ids = tuple(scenario.baseline_ranked_candidate_ids)
    baseline_eligible_ids = tuple(candidate_id for candidate_id in baseline_ids if candidate_id in adaptive_by_id)
    baseline_invalid = tuple(candidate_id for candidate_id in baseline_ids if candidate_id not in adaptive_by_id)
    baseline_top = baseline_ids[0] if baseline_ids else None
    adaptive_top = adaptive_ids[0] if adaptive_ids else None

    baseline_top_k = set(baseline_ids[:top_k])
    adaptive_top_k = set(adaptive_ids[:top_k])
    overlap = (
        round(len(baseline_top_k & adaptive_top_k) / len(baseline_top_k | adaptive_top_k), 6)
        if baseline_top_k or adaptive_top_k
        else None
    )
    def independently_valid(candidate: RecipeCandidate) -> bool:
        return (
            candidate.status not in {CandidateStatus.REVOKED, CandidateStatus.REJECTED, CandidateStatus.QUARANTINED}
            and RecipeQualityGate.hard_pass(RecipeQualityGate().evaluate(candidate, scenario.context.constraints))
            and (scenario.canonical_food_ids is None or all(
                mapping.canonical_food_id in scenario.canonical_food_ids for mapping in candidate.mappings
            ))
            and (scenario.expected_valid_candidate_ids is None or
                 candidate.candidate_id in scenario.expected_valid_candidate_ids)
        )
    hard_violations = sum(not independently_valid(row.candidate) for row in adaptive_rows)

    preferred = _movement_status(
        scenario.preferred_candidate_id, baseline_eligible_ids, adaptive_ids, promote=True
    )
    disliked = _movement_status(
        scenario.disliked_candidate_id, baseline_eligible_ids, adaptive_ids, promote=False
    )
    repeated = _repeat_reduction_status(
        baseline_top, adaptive_top, adaptive_by_id, scenario.context
    )
    explicit = _explicit_request_status(
        scenario.explicit_request_candidate_id, baseline_top, adaptive_top
    )
    diversity_change = _component_change(
        baseline_top, adaptive_top, adaptive_by_id, attribute="diversity_score"
    )
    portion_fit = (
        adaptive_by_id[adaptive_top].components.portion_fit_quality if adaptive_top is not None else None
    )
    valid_ids = {item.candidate_id for item in scenario.candidates if independently_valid(item)}
    retention = round(len(set(adaptive_ids) & valid_ids) / len(valid_ids), 6) if valid_ids else 1.0
    status = _scenario_status(
        hard_violations=hard_violations,
        preferred=preferred,
        disliked=disliked,
        repeated=repeated,
        explicit=explicit,
    )
    if retention < 1.0:
        status = ComparisonStatus.REGRESSED
    candidates_by_id = {item.candidate_id: item for item in scenario.candidates}
    def diversity_summary(ids: Sequence[str]) -> dict[str, object]:
        features = [features_for(candidates_by_id[candidate_id]) for candidate_id in ids[:top_k]]
        summary: dict[str, object] = {"candidate_count": len(features)}
        for dimension, attribute in (("dish", "dish"), ("main_protein", "primary_protein"), ("cuisine", "cuisine")):
            values = [getattr(item, attribute) for item in features if getattr(item, attribute)]
            summary[dimension] = {"known_count": len(values), "unique_count": len(set(values)), "max_share": _max_concentration(values)}
        summary["recipe_family"] = {"known_count": 0, "unique_count": None, "max_share": None}
        return summary
    return ShadowComparisonResult(
        scenario_id=scenario.scenario_id,
        label=scenario.label,
        baseline_ranked_candidate_ids=baseline_ids,
        adaptive_ranked_candidate_ids=adaptive_ids,
        baseline_invalid_or_unknown_candidate_ids=baseline_invalid,
        top_1_identity_change=(baseline_top != adaptive_top) if baseline_top or adaptive_top else None,
        top_k_overlap=overlap,
        preferred_candidate_promotion=preferred,
        disliked_candidate_demotion=disliked,
        recent_repeat_reduction=repeated,
        explicit_request_precedence=explicit,
        diversity_change=diversity_change,
        constraint_valid_candidate_retention=retention,
        portion_fit_compatibility=portion_fit,
        hard_constraint_violations=hard_violations,
        status=status,
        evidence_origin=SYNTHETIC_DEVELOPMENT,
        candidate_set_fingerprint=hashlib.sha256("|".join(sorted(candidate_ids)).encode()).hexdigest(),
        baseline_top_candidate_id=baseline_top,
        adaptive_top_candidate_id=adaptive_top,
        shadow_bandit_candidate_id=(
            ShadowBanditPolicy().choose_shadow(adaptive_rows, ()).selected.candidate.candidate_id
            if adaptive_rows else None
        ),
        policy_version=active_ranker.policy.version,
        shadow_bandit_policy_version=SHADOW_BANDIT_POLICY_V1,
        outcome_binding=None,
        independent_validity_checked=scenario.expected_valid_candidate_ids is not None and scenario.canonical_food_ids is not None,
        baseline_portion_fit=(adaptive_by_id[baseline_top].components.portion_fit_quality if baseline_top in adaptive_by_id else None),
        portion_fit_change=_component_change(baseline_top, adaptive_top, adaptive_by_id, attribute="portion_fit_quality"),
        top_k_diversity={"baseline": diversity_summary(baseline_ids), "adaptive": diversity_summary(adaptive_ids)},
    )


@dataclass(frozen=True)
class ObservedFeedbackMetrics:
    """Descriptive aggregate counts from genuine, durable event rows only."""

    recommendation_exposure_count: int
    feedback_event_count: int
    users_with_feedback: int
    event_counts: Mapping[str, int]
    like_rate: float | None
    dislike_rate: float | None
    save_rate: float | None
    reject_rate: float | None
    repeat_recommendation_rate: float | None
    candidate_diversity: float | None
    dish_concentration: float | None
    primary_protein_concentration: float | None
    cuisine_concentration: float | None
    recipe_family_concentration: float | None
    catalog_gap_rate: float | None
    portion_correction_frequency: float | None
    excluded_recommendations_by_origin: Mapping[str, int]
    excluded_feedback_count: int
    rejection_reason_counts: Mapping[str, int]
    minimum_reporting_denominator: int | None
    metric_limitations: tuple[str, ...]


def observed_feedback_metrics(
    recommendations: Iterable[RecommendationMemoryEntry],
    feedback_events: Iterable[FeedbackEvent],
    *,
    provenance_by_recommendation: Mapping[str, str] | None = None,
    minimum_reporting_denominator: int | None = None,
) -> ObservedFeedbackMetrics:
    """Summarise supplied durable rows without returning owner-level data.

    Unknown provenance and development records are excluded, never relabelled
    as observed users. Rates require a separately chosen reporting minimum
    (at least two); the minimum does not establish rollout sufficiency. Without
    one, only counts are reported. Identity is exact, owner/candidate/policy
    bound, and counts deduplicate immutable event IDs and exposure outcomes.
    """

    if minimum_reporting_denominator is not None and minimum_reporting_denominator < 2:
        raise ValueError("REPORTING_DENOMINATOR_TOO_SMALL")
    origins = provenance_by_recommendation or {}
    supplied_memory = tuple(recommendations)
    by_id = {entry.recommendation_id: entry for entry in supplied_memory}
    if len(by_id) != len(supplied_memory):
        raise ValueError("DUPLICATE_EXPOSURE_ID")
    memory = tuple(entry for entry in supplied_memory if origins.get(entry.recommendation_id) == OBSERVED_USER)
    eligible = {entry.recommendation_id: entry for entry in memory}
    supplied_feedback = tuple(feedback_events)
    bound: dict[str, FeedbackEvent] = {}
    for event in supplied_feedback:
        exposure = eligible.get(event.recommendation_id or "")
        if (exposure is None or not event.feedback_event_id or
            event.owner_user_id != exposure.owner_user_id or
            event.candidate_id != exposure.candidate_id or
            event.policy_version != exposure.selected_policy or
            event.occurred_at < exposure.shown_at):
            continue
        previous = bound.get(event.feedback_event_id)
        if previous is not None and previous != event:
            raise ValueError("CONFLICTING_FEEDBACK_ID")
        bound[event.feedback_event_id] = event
    feedback = tuple(bound.values())
    def rate(numerator: int, denominator: int) -> float | None:
        return _rate(numerator, denominator) if minimum_reporting_denominator is not None and denominator >= minimum_reporting_denominator else None
    def outcome_rate(event_type: FeedbackEventType) -> float | None:
        return rate(len({event.recommendation_id for event in feedback if event.event_type == event_type}), len(memory))
    def concentration(values: Sequence[str]) -> float | None:
        return _max_concentration(values) if minimum_reporting_denominator is not None and len(values) >= minimum_reporting_denominator else None
    counts = Counter(event.event_type.value for event in feedback)
    exposures = len(memory)
    grouped: dict[str, list[RecommendationMemoryEntry]] = defaultdict(list)
    for entry in memory:
        grouped[entry.owner_user_id].append(entry)
    sequential_pairs = 0
    repeats = 0
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: item.shown_at)
        for previous, current in zip(ordered, ordered[1:]):
            sequential_pairs += 1
            if previous.candidate_id == current.candidate_id:
                repeats += 1
    dish_values = tuple(entry.dish for entry in memory if entry.dish)
    protein_values = tuple(entry.primary_protein for entry in memory if entry.primary_protein)
    cuisine_values = tuple(entry.cuisine for entry in memory if entry.cuisine)
    recipe_family_values = tuple(
        str(entry.feature_payload["recipe_family"])
        for entry in memory
        if entry.feature_payload.get("recipe_family")
    )
    return ObservedFeedbackMetrics(
        recommendation_exposure_count=exposures,
        feedback_event_count=len(feedback),
        users_with_feedback=len({event.owner_user_id for event in feedback}),
        event_counts=dict(sorted(counts.items())),
        like_rate=outcome_rate(FeedbackEventType.LIKED),
        dislike_rate=outcome_rate(FeedbackEventType.DISLIKED),
        save_rate=outcome_rate(FeedbackEventType.SAVED),
        reject_rate=outcome_rate(FeedbackEventType.REJECTED),
        repeat_recommendation_rate=rate(repeats, sequential_pairs),
        candidate_diversity=rate(len({entry.candidate_id for entry in memory}), exposures),
        dish_concentration=concentration(dish_values),
        primary_protein_concentration=concentration(protein_values),
        cuisine_concentration=concentration(cuisine_values),
        recipe_family_concentration=concentration(recipe_family_values),
        catalog_gap_rate=rate(
            len({event.recommendation_id for event in feedback if
                event.event_type is FeedbackEventType.REJECTED
                and getattr(event.reason_code, "value", None) == "INGREDIENT_UNAVAILABLE"
            }),
            exposures,
        ),
        portion_correction_frequency=outcome_rate(FeedbackEventType.PORTION_CORRECTED),
        excluded_recommendations_by_origin=dict(Counter(origins.get(entry.recommendation_id, "UNVERIFIED") for entry in supplied_memory if entry.recommendation_id not in eligible)),
        excluded_feedback_count=len(supplied_feedback) - len(feedback),
        rejection_reason_counts=dict(Counter(event.reason_code.value for event in feedback if event.event_type is FeedbackEventType.REJECTED and event.reason_code)),
        minimum_reporting_denominator=minimum_reporting_denominator,
        metric_limitations=("OBSERVATIONAL_EXPOSURE_BIAS", "NO_CAUSAL_UPLIFT", "REPORTING_MINIMUM_IS_NOT_ROLLOUT_SUFFICIENCY", "PREFERENCE_AGREEMENT_REQUIRES_PRE_EXPOSURE_SNAPSHOT", "GAP_RATE_IS_UNAVAILABLE_REJECTION_PROXY_ONLY"),
    )


@dataclass(frozen=True)
class N33DevelopmentScenario:
    scenario_id: str
    focus: str
    expected_invariants: tuple[str, ...]
    label: str = N3_3_DEVELOPMENT_LABEL


def n3_3_development_scenarios() -> tuple[N33DevelopmentScenario, ...]:
    """Focused synthetic regressions; not a research or acceptance benchmark."""

    return (
        N33DevelopmentScenario("N33_STRONG_LIKE", "strong like", ("PREFERRED_CANDIDATE_PROMOTED",)),
        N33DevelopmentScenario("N33_STRONG_DISLIKE", "strong dislike", ("DISLIKED_CANDIDATE_DEMOTED",)),
        N33DevelopmentScenario("N33_NOT_TODAY", "temporary rejection", ("NOT_PERMANENT_DISLIKE",)),
        N33DevelopmentScenario("N33_COLD_START", "no feedback", ("BASELINE_GRACEFUL_DEGRADATION",)),
        N33DevelopmentScenario("N33_CONFLICTING_PREFERENCES", "conflicting evidence", ("EXPLICIT_FACT_WINS",)),
        N33DevelopmentScenario("N33_EXPLICIT_CURRENT_REQUEST", "current dish request", ("EXPLICIT_REQUEST_PRECEDENCE",)),
        N33DevelopmentScenario("N33_DIVERSITY_PRESSURE", "recent repetition", ("SOFT_DIVERSITY_ROTATION",)),
        N33DevelopmentScenario("N33_ALLERGY_CONFLICT", "allergy exclusion", ("ALLERGY_HARD_GATE",)),
        N33DevelopmentScenario("N33_DIET_RESTRICTION_CONFLICT", "dietary exclusion", ("RESTRICTION_HARD_GATE",)),
        N33DevelopmentScenario("N33_PORTION_CORRECTION", "personal serving correction", ("OWNER_PRIVATE_PORTION_ONLY",)),
        N33DevelopmentScenario("N33_CANDIDATE_UNAVAILABLE", "unavailable rejection", ("CATALOG_EVIDENCE_NOT_DISLIKE",)),
        N33DevelopmentScenario("N33_STALE_PREFERENCE", "aged evidence", ("STALE_EVIDENCE_DECAYS",)),
    )


def _movement_status(
    candidate_id: str | None,
    baseline_ids: Sequence[str],
    adaptive_ids: Sequence[str],
    *,
    promote: bool,
) -> ComparisonStatus:
    if not candidate_id or candidate_id not in baseline_ids or candidate_id not in adaptive_ids:
        return ComparisonStatus.NOT_APPLICABLE
    baseline_position = baseline_ids.index(candidate_id)
    adaptive_position = adaptive_ids.index(candidate_id)
    if adaptive_position == baseline_position:
        return ComparisonStatus.UNCHANGED
    improved = adaptive_position < baseline_position if promote else adaptive_position > baseline_position
    return ComparisonStatus.IMPROVED if improved else ComparisonStatus.REGRESSED


def _repeat_reduction_status(
    baseline_top: str | None,
    adaptive_top: str | None,
    rows_by_id: Mapping[str, RankedRecommendation],
    context: RecommendationContext,
) -> ComparisonStatus:
    if baseline_top not in rows_by_id or adaptive_top not in rows_by_id:
        return ComparisonStatus.NOT_APPLICABLE
    if not context.recent_recommendations and not context.recently_consumed:
        return ComparisonStatus.NOT_APPLICABLE
    baseline_repeat = _is_recent_repeat(rows_by_id[baseline_top], context)
    adaptive_repeat = _is_recent_repeat(rows_by_id[adaptive_top], context)
    if baseline_repeat == adaptive_repeat:
        return ComparisonStatus.UNCHANGED
    return ComparisonStatus.IMPROVED if baseline_repeat and not adaptive_repeat else ComparisonStatus.REGRESSED


def _explicit_request_status(
    requested_candidate_id: str | None, baseline_top: str | None, adaptive_top: str | None
) -> ComparisonStatus:
    if requested_candidate_id is None or baseline_top is None or adaptive_top is None:
        return ComparisonStatus.NOT_APPLICABLE
    baseline_matches = baseline_top == requested_candidate_id
    adaptive_matches = adaptive_top == requested_candidate_id
    if baseline_matches == adaptive_matches:
        return ComparisonStatus.UNCHANGED
    return ComparisonStatus.IMPROVED if adaptive_matches else ComparisonStatus.REGRESSED


def _is_recent_repeat(row: RankedRecommendation, context: RecommendationContext) -> bool:
    features = features_for(row.candidate)
    for entry in context.recent_recommendations + context.recently_consumed:
        if entry.candidate_id == row.candidate.candidate_id or entry.dish.casefold() == features.dish.casefold():
            return True
    return False


def _component_change(
    baseline_top: str | None,
    adaptive_top: str | None,
    rows_by_id: Mapping[str, RankedRecommendation],
    *,
    attribute: str,
) -> float | None:
    if baseline_top not in rows_by_id or adaptive_top not in rows_by_id:
        return None
    before = getattr(rows_by_id[baseline_top].components, attribute)
    after = getattr(rows_by_id[adaptive_top].components, attribute)
    return round(float(after) - float(before), 6)


def _scenario_status(
    *,
    hard_violations: int,
    preferred: ComparisonStatus,
    disliked: ComparisonStatus,
    repeated: ComparisonStatus,
    explicit: ComparisonStatus,
) -> ComparisonStatus:
    relevant = (preferred, disliked, repeated, explicit)
    if hard_violations or ComparisonStatus.REGRESSED in relevant:
        return ComparisonStatus.REGRESSED
    if ComparisonStatus.IMPROVED in relevant:
        return ComparisonStatus.IMPROVED
    if any(item is not ComparisonStatus.NOT_APPLICABLE for item in relevant):
        return ComparisonStatus.UNCHANGED
    return ComparisonStatus.NOT_APPLICABLE


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _max_concentration(values: Sequence[str]) -> float | None:
    if not values:
        return None
    return round(max(Counter(values).values()) / len(values), 6)


__all__ = [
    "BASELINE_RANKER_VERSION",
    "DIVERSITY_RERANKER_VERSION",
    "N3_3_DEVELOPMENT_LABEL",
    "ComparisonStatus",
    "FrozenRankingBaseline",
    "N33DevelopmentScenario",
    "ObservedFeedbackMetrics",
    "ShadowComparisonResult",
    "ShadowComparisonScenario",
    "evaluate_shadow_comparison",
    "frozen_ranking_baselines",
    "n3_3_development_scenarios",
    "observed_feedback_metrics",
]
