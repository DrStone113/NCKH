"""N3.2 recommendation intelligence, deliberately limited to development/shadow.

This module centralises the *soft* part of meal recommendation.  Deterministic
nutrition calculation and hard policy/safety filtering continue to live in the
canonical and N3 quality-gate layers.  Nothing here can write a canonical
recipe, loosen a constraint, or turn an impression into consumption.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping, Sequence
from uuid import uuid4

from .contracts import (
    CandidateStatus,
    ConstraintContext,
    FeedbackEvent,
    FeedbackEventType,
    FeedbackRejectionReason,
    MappingStatus,
    RecipeCandidate,
    TrustDomain,
)
from .engine import RecipeQualityGate
from .eligibility import CandidateEligibility, CandidateEligibilityGate
from .request_policy import CurrentRequest, RequestOrigin, normalize, request_from_current_text, request_matches


RANKING_POLICY_V2 = "RECOMMENDATION_RANKER_V2_N3_3R_SEMANTICS_V2"
EXPLORATION_POLICY_V1 = "EXPLORATION_POLICY_V1"
SHADOW_BANDIT_POLICY_V1 = "CONTEXTUAL_BANDIT_SHADOW_V1"


class CandidateSourceType(str, Enum):
    LOCAL_CANONICAL = "LOCAL_CANONICAL"
    PERSONAL_RECIPE = "PERSONAL_RECIPE"
    STAGING_EXTERNAL = "STAGING_EXTERNAL"
    RUNTIME_EXTERNAL = "RUNTIME_EXTERNAL"


class PreferenceDimension(str, Enum):
    DISH = "DISH"
    INGREDIENT = "INGREDIENT"
    PROTEIN = "PROTEIN"
    CUISINE = "CUISINE"
    PREPARATION = "PREPARATION"
    MEAL_PATTERN = "MEAL_PATTERN"
    SPICE = "SPICE"
    TEXTURE = "TEXTURE"
    COOKING_EFFORT = "COOKING_EFFORT"
    BUDGET = "BUDGET"


class PreferenceSource(str, Enum):
    EXPLICIT_STATEMENT = "EXPLICIT_STATEMENT"
    EXPLICIT_FEEDBACK = "EXPLICIT_FEEDBACK"
    ACTUAL_CONSUMPTION = "ACTUAL_CONSUMPTION"
    INTERACTION = "INTERACTION"


class RankingReasonCode(str, Enum):
    NUTRITION_REMAINING_FIT = "NUTRITION_REMAINING_FIT"
    CONFIRMED_PREFERENCE_MATCH = "CONFIRMED_PREFERENCE_MATCH"
    INFERRED_PREFERENCE_MATCH = "INFERRED_PREFERENCE_MATCH"
    DIVERSITY_PROTEIN_ROTATION = "DIVERSITY_PROTEIN_ROTATION"
    DIVERSITY_DISH_ROTATION = "DIVERSITY_DISH_ROTATION"
    PORTION_ADAPTABLE = "PORTION_ADAPTABLE"
    PERSONAL_RECIPE_EVIDENCE = "PERSONAL_RECIPE_EVIDENCE"
    STAGING_SOURCE = "STAGING_SOURCE"
    RUNTIME_EXTERNAL_SOURCE = "RUNTIME_EXTERNAL_SOURCE"
    CANONICAL_SOURCE = "CANONICAL_SOURCE"
    PREFERENCE_EVIDENCE_INSUFFICIENT = "PREFERENCE_EVIDENCE_INSUFFICIENT"
    EXPLORATION_PROMOTED = "EXPLORATION_PROMOTED"


@dataclass(frozen=True)
class CandidateFeatures:
    """Only recipe/catalog facts used by the soft ranker, never health data."""

    candidate_id: str
    dish: str
    ingredients: tuple[str, ...] = ()
    primary_protein: str | None = None
    cuisine: str | None = None
    preparation: str | None = None
    cooking_effort: str | None = None
    budget_band: str | None = None


@dataclass(frozen=True)
class RecommendationMemoryEntry:
    """An exposure/response record, intentionally distinct from a meal log."""

    recommendation_id: str
    owner_user_id: str
    candidate_id: str
    dish: str
    source_type: CandidateSourceType
    shown_at: datetime
    primary_protein: str | None = None
    cuisine: str | None = None
    preparation: str | None = None
    outcome_status: str = "SHOWN"
    selected_policy: str = "BASELINE_RANKER"
    selection_probability: float | None = None
    context_fingerprint: str | None = None
    # Safe recipe attributes needed to rebuild a private preference profile
    # from durable feedback after a process restart.  This intentionally omits
    # health profile data, chat text, source HTML, and rank scores/weights.
    feature_payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationContext:
    """Minimal, relevant context for deterministic reranking.

    The full health profile is intentionally absent.  Nutrition targets and
    confirmed constraints are evaluated by ``ConstraintContext`` before the
    ranker can observe candidates.
    """

    constraints: ConstraintContext = ConstraintContext()
    meal_type: str | None = None
    local_day: str | None = None
    local_time_bucket: str | None = None
    recent_recommendations: tuple[RecommendationMemoryEntry, ...] = ()
    recently_consumed: tuple[RecommendationMemoryEntry, ...] = ()
    active_plan_id: str | None = None
    stated_cuisine_intent: str | None = None
    stated_dish_intent: str | None = None
    available_cooking_effort: str | None = None
    stated_budget_band: str | None = None
    available_equipment: tuple[str, ...] = ()
    portion_fit_quality: Mapping[str, float] = field(default_factory=dict)
    owner_user_id: str = ""
    current_request: CurrentRequest | None = None
    confirmed_current_context: CurrentRequest | None = None
    baseline_ranked_candidate_ids: tuple[str, ...] = ()
    evaluated_at: datetime | None = None

    def fingerprint(self) -> str:
        """Hash an allowlisted coarse context; never include user or health data."""

        material = "|".join(
            (
                self.meal_type or "",
                self.local_day or "",
                self.local_time_bucket or "",
                str(round(self.constraints.target_kcal or 0.0, -1)),
                str(round(self.constraints.target_protein_g or 0.0, 0)),
                self.stated_cuisine_intent or "",
                self.available_cooking_effort or "",
                self.stated_budget_band or "",
                str(len(self.recent_recommendations)),
                str(len(self.recently_consumed)),
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class ConfirmedPreference:
    dimension: PreferenceDimension
    value: str
    affinity: float
    confirmed_at: datetime
    temporary_until: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.temporary_until is None or self.temporary_until >= now


@dataclass(frozen=True)
class PreferenceEvidence:
    dimension: PreferenceDimension
    value: str
    affinity: float
    confidence: float
    source: PreferenceSource
    updated_at: datetime
    evidence_count: int
    last_confirmed_at: datetime | None = None


@dataclass(frozen=True)
class UserPreferenceProfile:
    """Bounded owner-private preference state; no demographic inference."""

    owner_user_id: str
    policy_version: str
    evidence: tuple[PreferenceEvidence, ...]
    confirmed: tuple[ConfirmedPreference, ...] = ()
    conflict_codes: tuple[str, ...] = ()
    insufficient_evidence: bool = True

    def affinity_for(self, features: CandidateFeatures, now: datetime | None = None) -> tuple[float, bool]:
        observed_at = now or datetime.now(timezone.utc)
        feature_values = _feature_values(features)
        explicit: dict[tuple[PreferenceDimension, str], float] = {}
        for fact in self.confirmed:
            if fact.is_active(observed_at):
                explicit[(fact.dimension, _normalise(fact.value))] = _signed_clamp(fact.affinity)
        values: list[float] = []
        explicit_values: list[float] = []
        for dimension, value in feature_values:
            key = (dimension, _normalise(value))
            if key in explicit:
                explicit_values.append(explicit[key])
                continue
            matching = [
                item.affinity * item.confidence
                for item in self.evidence
                if item.dimension == dimension and _normalise(item.value) == key[1]
            ]
            if matching:
                values.append(sum(matching) / len(matching))
        # An active explicit statement wins over behavioural inference. This
        # includes conflicts such as an explicit fish dislike and historic fish
        # consumption; we never average the two into a false neutral signal.
        if explicit_values:
            return (round(_signed_clamp(sum(explicit_values) / len(explicit_values)), 6), True)
        return (round(_signed_clamp(sum(values) / len(values)) if values else 0.0, 6), False)


class PreferenceProfileBuilder:
    """Builds preference evidence with explicit facts taking precedence."""

    half_life_days: float = 90.0
    max_evidence_items: int = 100

    _EVENT_AFFINITY: Mapping[FeedbackEventType, float] = {
        FeedbackEventType.LIKED: 0.85,
        FeedbackEventType.DISLIKED: -0.90,
        FeedbackEventType.ACTUALLY_CONSUMED: 0.50,
        FeedbackEventType.REPEATED: 0.65,
        FeedbackEventType.REPEATED_CONSUMPTION: 0.80,
        FeedbackEventType.SAVED: 0.25,
        FeedbackEventType.SUBSTITUTED: -0.10,
    }

    def build(
        self,
        *,
        owner_user_id: str,
        events: Iterable[FeedbackEvent],
        candidates: Mapping[str, RecipeCandidate],
        confirmed: Iterable[ConfirmedPreference] = (),
        now: datetime | None = None,
    ) -> UserPreferenceProfile:
        feature_events = (
            (event, features_for(candidate))
            for event in events
            if event.owner_user_id == owner_user_id
            for candidate in (candidates.get(event.candidate_id),)
            if candidate is not None
        )
        return self.build_from_feature_events(
            owner_user_id=owner_user_id,
            feature_events=feature_events,
            confirmed=confirmed,
            now=now,
        )

    def build_from_feature_events(
        self,
        *,
        owner_user_id: str,
        feature_events: Iterable[tuple[FeedbackEvent, CandidateFeatures]],
        confirmed: Iterable[ConfirmedPreference] = (),
        now: datetime | None = None,
    ) -> UserPreferenceProfile:
        """Build a profile from durable, allowlisted candidate features.

        SQL feedback persistence stores the recipe attributes used for soft
        ranking alongside the recommendation event.  Reusing this method keeps
        post-restart reconstruction semantically identical to the in-memory
        path without storing private chat or health context.
        """

        observed_at = now or datetime.now(timezone.utc)
        grouped: dict[tuple[PreferenceDimension, str], list[tuple[float, PreferenceSource, datetime]]] = defaultdict(list)
        event_count = 0
        for event, features in feature_events:
            if event.owner_user_id != owner_user_id:
                continue
            affinity, source = self._event_affinity(event)
            if affinity == 0.0:
                # SHOWN and OPENED deliberately produce no preference evidence.
                continue
            event_count += 1
            age_days = max((observed_at - _utc(event.occurred_at)).total_seconds() / 86_400.0, 0.0)
            decayed = affinity * math.pow(0.5, age_days / self.half_life_days)
            for dimension, value in _feature_values(features):
                grouped[(dimension, _normalise(value))].append((decayed, source, _utc(event.occurred_at)))

        evidence: list[PreferenceEvidence] = []
        for (dimension, value), values in grouped.items():
            total = sum(item[0] for item in values)
            affinity = _signed_clamp(total)
            confidence = min(1.0, len(values) / 5.0)
            source = max(values, key=lambda item: abs(item[0]))[1]
            evidence.append(
                PreferenceEvidence(
                    dimension=dimension,
                    value=value,
                    affinity=round(affinity, 6),
                    confidence=round(confidence, 6),
                    source=source,
                    updated_at=max(item[2] for item in values),
                    evidence_count=len(values),
                )
            )
        evidence.sort(key=lambda item: (item.updated_at, item.confidence, abs(item.affinity)), reverse=True)
        evidence = evidence[: self.max_evidence_items]
        facts = tuple(confirmed)
        explicit_keys = {(fact.dimension, _normalise(fact.value)): fact.affinity for fact in facts}
        conflicts = sorted(
            "PREFERENCE_CONFLICT"
            for item in evidence
            if (item.dimension, _normalise(item.value)) in explicit_keys
            and item.affinity * explicit_keys[(item.dimension, _normalise(item.value))] < 0
        )
        return UserPreferenceProfile(
            owner_user_id=owner_user_id,
            policy_version="PREFERENCE_WEIGHT_POLICY_V1",
            evidence=tuple(evidence),
            confirmed=facts,
            conflict_codes=tuple(conflicts),
            insufficient_evidence=event_count < 2 and not facts,
        )

    def _event_affinity(self, event: FeedbackEvent) -> tuple[float, PreferenceSource]:
        if event.event_type == FeedbackEventType.REJECTED:
            if event.reason_code == FeedbackRejectionReason.DO_NOT_LIKE:
                return (-0.85, PreferenceSource.EXPLICIT_FEEDBACK)
            # Availability, mood, cost, effort and repetition have their own
            # rank components. They are not a durable dish dislike.
            return (0.0, PreferenceSource.INTERACTION)
        if event.event_type == FeedbackEventType.OPENED or event.event_type == FeedbackEventType.SHOWN:
            return (0.0, PreferenceSource.INTERACTION)
        affinity = self._EVENT_AFFINITY.get(event.event_type, 0.0)
        if event.event_type in {FeedbackEventType.LIKED, FeedbackEventType.DISLIKED} or event.explicit:
            return (affinity, PreferenceSource.EXPLICIT_FEEDBACK)
        if event.event_type in {FeedbackEventType.ACTUALLY_CONSUMED, FeedbackEventType.REPEATED_CONSUMPTION, FeedbackEventType.REPEATED}:
            return (affinity, PreferenceSource.ACTUAL_CONSUMPTION)
        return (affinity, PreferenceSource.INTERACTION)


@dataclass(frozen=True)
class PortionObservation:
    owner_user_id: str
    candidate_id: str
    actual_portion_grams: float
    occurred_at: datetime
    source_event: FeedbackEventType = FeedbackEventType.ACTUALLY_CONSUMED


@dataclass(frozen=True)
class PortionPrior:
    owner_user_id: str
    candidate_id: str
    median_observed_grams: float
    recent_min_grams: float
    recent_max_grams: float
    evidence_count: int
    updated_at: datetime

    def preferred_scale(self, canonical_serving_grams: float) -> float | None:
        if canonical_serving_grams <= 0 or self.evidence_count < 2:
            return None
        # A prior can only nudge the bounded fitter; never redefine a
        # canonical serving and never widen culinary bounds.
        return round(min(1.25, max(0.80, self.median_observed_grams / canonical_serving_grams)), 4)


class PortionLearning:
    def build_prior(
        self,
        *,
        owner_user_id: str,
        candidate_id: str,
        observations: Iterable[PortionObservation],
    ) -> PortionPrior | None:
        rows = sorted(
            [
                row
                for row in observations
                if row.owner_user_id == owner_user_id
                and row.candidate_id == candidate_id
                # An explicit serving correction is personal portion evidence,
                # but is deliberately not an actual-meal observation. The
                # caller records it through the separate correction route.
                and row.source_event
                in {
                    FeedbackEventType.ACTUALLY_CONSUMED,
                    FeedbackEventType.REPEATED_CONSUMPTION,
                    FeedbackEventType.PORTION_CORRECTED,
                }
                and row.actual_portion_grams > 0
            ],
            key=lambda row: _utc(row.occurred_at),
        )
        if not rows:
            return None
        recent = rows[-20:]
        grams = [row.actual_portion_grams for row in recent]
        return PortionPrior(
            owner_user_id=owner_user_id,
            candidate_id=candidate_id,
            median_observed_grams=round(float(statistics.median(grams)), 2),
            recent_min_grams=round(min(grams), 2),
            recent_max_grams=round(max(grams), 2),
            evidence_count=len(recent),
            updated_at=_utc(recent[-1].occurred_at),
        )


@dataclass(frozen=True)
class RecipeCorrectionDisposition:
    scope: str
    reason_code: str


def classify_recipe_correction(candidate: RecipeCandidate) -> RecipeCorrectionDisposition:
    """Classify corrective evidence without modifying any recipe in place."""

    if candidate.trust_domain == TrustDomain.PERSONAL_RECIPE:
        return RecipeCorrectionDisposition("PERSONAL_RECIPE_ONLY", "PERSONAL_RECIPE_REVISION_REQUIRED")
    if candidate.trust_domain in {TrustDomain.STAGING_RECIPE, TrustDomain.RUNTIME_EXTERNAL_CANDIDATE}:
        return RecipeCorrectionDisposition("STAGING_EVIDENCE", "STAGING_EVIDENCE_REVIEW_REQUIRED")
    return RecipeCorrectionDisposition("CANONICAL_DISCREPANCY_REPORT", "CANONICAL_REVIEW_REQUIRED")


@dataclass(frozen=True)
class RankingComponents:
    nutrition_fit: float
    preference_fit: float
    source_quality: float
    mapping_quality: float
    portion_fit_quality: float
    recent_repetition_penalty: float
    diversity_score: float
    novelty_score: float
    cooking_effort_fit: float
    budget_fit: float

    def to_dict(self) -> dict[str, float]:
        return {
            "nutrition_fit": self.nutrition_fit,
            "preference_fit": self.preference_fit,
            "source_quality": self.source_quality,
            "mapping_quality": self.mapping_quality,
            "portion_fit_quality": self.portion_fit_quality,
            "recent_repetition_penalty": self.recent_repetition_penalty,
            "diversity_score": self.diversity_score,
            "novelty_score": self.novelty_score,
            "cooking_effort_fit": self.cooking_effort_fit,
            "budget_fit": self.budget_fit,
        }


@dataclass(frozen=True)
class RankedRecommendation:
    candidate: RecipeCandidate
    source_type: CandidateSourceType
    score: float
    components: RankingComponents
    reason_codes: tuple[RankingReasonCode, ...]
    policy_version: str = RANKING_POLICY_V2

    def public_reason_codes(self) -> tuple[str, ...]:
        """Return structured public reasons, never internal weights or rank."""

        return tuple(item.value for item in self.reason_codes[:3])


@dataclass(frozen=True)
class RankerV2Policy:
    version: str = RANKING_POLICY_V2
    nutrition_weight: float = 0.30
    preference_weight: float = 0.22
    source_quality_weight: float = 0.12
    mapping_quality_weight: float = 0.10
    portion_fit_weight: float = 0.10
    diversity_weight: float = 0.07
    novelty_weight: float = 0.05
    cooking_effort_weight: float = 0.02
    budget_weight: float = 0.02


@dataclass(frozen=True)
class RankingOutcome:
    status: str
    ranked: tuple[RankedRecommendation, ...]
    exclusions: tuple[CandidateEligibility, ...]


class RecommendationRankerV2:
    """The N3.2 development/shadow selection contract.

    Resolve source identity and enforce deterministic safety first, then
    constrain candidates to the current request. Learned preferences rank
    that set before the final repetition guard selects within it.
    """

    def __init__(self, *, policy: RankerV2Policy = RankerV2Policy(),
                 eligibility_gate: CandidateEligibilityGate | None = None) -> None:
        self.policy = policy
        self.eligibility_gate = eligibility_gate or CandidateEligibilityGate()

    def rank(
        self,
        candidates: Iterable[RecipeCandidate],
        *,
        context: RecommendationContext,
        preference_profile: UserPreferenceProfile | None = None,
        candidate_features: Mapping[str, CandidateFeatures] | None = None,
    ) -> list[RankedRecommendation]:
        return list(self.rank_with_diagnostics(
            candidates, context=context, preference_profile=preference_profile,
            candidate_features=candidate_features,
        ).ranked)

    def rank_with_diagnostics(
        self, candidates: Iterable[RecipeCandidate], *, context: RecommendationContext,
        preference_profile: UserPreferenceProfile | None = None,
        candidate_features: Mapping[str, CandidateFeatures] | None = None,
    ) -> RankingOutcome:
        profile = preference_profile or UserPreferenceProfile(
            owner_user_id=context.owner_user_id, policy_version="PREFERENCE_WEIGHT_POLICY_V1", evidence=()
        )
        if profile.owner_user_id != context.owner_user_id:
            raise ValueError("FOREIGN_PREFERENCE_PROFILE")
        history = context.recent_recommendations + context.recently_consumed
        if any(entry.owner_user_id != context.owner_user_id for entry in history):
            raise ValueError("FOREIGN_RECOMMENDATION_MEMORY")
        now = context.evaluated_at or datetime.now(timezone.utc)
        snapshot = tuple(candidates)
        if len({item.candidate_id for item in snapshot}) != len(snapshot):
            raise ValueError("DUPLICATE_CANDIDATE_ID")
        baseline = context.baseline_ranked_candidate_ids or tuple(item.candidate_id for item in snapshot)
        if len(set(baseline)) != len(baseline) or set(baseline) - {item.candidate_id for item in snapshot}:
            raise ValueError("INVALID_BASELINE_CANDIDATE_ORDER")
        positions = {candidate_id: index for index, candidate_id in enumerate(baseline)}
        request = context.current_request or request_from_current_text(context.stated_dish_intent)
        if request.origin != RequestOrigin.CURRENT_EXPLICIT:
            raise ValueError("CURRENT_REQUEST_ORIGIN_REQUIRED")
        confirmed = context.confirmed_current_context
        if confirmed is not None and confirmed.origin != RequestOrigin.CONFIRMED_CURRENT_CONTEXT:
            raise ValueError("CONFIRMED_CURRENT_CONTEXT_ORIGIN_REQUIRED")
        eligible, exclusions = [], []
        for candidate in snapshot:
            check = self.eligibility_gate.evaluate(candidate, owner_user_id=context.owner_user_id, constraints=context.constraints)
            if check.eligible:
                eligible.append(candidate)
            else:
                exclusions.append(check)
        # All categorical checks precede every affinity/score calculation.
        eligible = [candidate for candidate in eligible if request_matches(
            candidate, request, self.eligibility_gate, local_day=context.local_day,
        )]
        if not eligible:
            status = "NO_ELIGIBLE_CANDIDATE_FOR_EXPLICIT_REQUEST" if request.has_constraints else "NO_ELIGIBLE_CANDIDATE"
            return RankingOutcome(status, (), tuple(exclusions))
        if confirmed is not None:
            compatible = [candidate for candidate in eligible if request_matches(candidate, confirmed, self.eligibility_gate, local_day=context.local_day)]
            # A conflicting lower-precedence context cannot veto current intent.
            if compatible:
                eligible = compatible
            elif not request.has_constraints:
                return RankingOutcome("NO_ELIGIBLE_CANDIDATE_FOR_CONFIRMED_CONTEXT", (), tuple(exclusions))
        # The same normalized current request controls filtering and repetition
        # exemptions, for both typed and legacy-text callers. Every remaining
        # candidate has already passed this request and all safety checks.
        dish_requested = bool(request.requested_dish)
        supplied = candidate_features or {}
        ranked: list[RankedRecommendation] = []
        for candidate in eligible:
            features = supplied.get(candidate.candidate_id, features_for(candidate))
            source_type = source_type_for(candidate)
            preference, explicit_preference = profile.affinity_for(features, now)
            repeat_penalty = 0.0 if dish_requested else self._repeat_penalty(features, context)
            components = RankingComponents(
                nutrition_fit=self._nutrition_fit(candidate, context.constraints),
                preference_fit=(preference + 1.0) / 2.0,
                source_quality=_source_quality(source_type),
                mapping_quality=self._mapping_quality(candidate),
                portion_fit_quality=_clamp(context.portion_fit_quality.get(candidate.candidate_id, 1.0)),
                recent_repetition_penalty=round(repeat_penalty, 6),
                diversity_score=round(1.0 - repeat_penalty, 6),
                novelty_score=1.0 if dish_requested else self._novelty(features, context),
                cooking_effort_fit=_attribute_fit(features.cooking_effort, context.available_cooking_effort),
                budget_fit=_attribute_fit(features.budget_band, context.stated_budget_band),
            )
            score = self._score(components)
            reasons = self._reasons(
                candidate, source_type, components, profile.insufficient_evidence,
                explicit_preference, dish_requested=dish_requested,
            )
            ranked.append(
                RankedRecommendation(
                    candidate=candidate,
                    source_type=source_type,
                    score=round(score, 6),
                    components=components,
                    reason_codes=reasons,
                    policy_version=self.policy.version,
                )
            )
        ranked = self._prevent_novelty_only_external_promotion(ranked)
        guarded_positions = {
            row.candidate.candidate_id: index for index, row in enumerate(ranked)
        }
        # Exact exposure is a selection guard, not a larger diversity weight.
        # Never-seen candidates lead; once all have been exposed, least-recent
        # identities lead. All semantically eligible rows remain observable.
        def exposure_tier(candidate: RecipeCandidate) -> float:
            if dish_requested:
                return float('-inf')
            identities = {normalize(candidate.title), *(normalize(alias) for alias in candidate.aliases)}
            dates = [entry.shown_at.timestamp() for entry in history
                     if entry.shown_at <= now and (entry.candidate_id == candidate.candidate_id or normalize(entry.dish) in identities)]
            return max(dates) if dates else float('-inf')
        has_reliable_preference = any(fact.is_active(now) for fact in profile.confirmed) or (
            not profile.insufficient_evidence and any(
                0 <= (now - _utc(item.updated_at)).total_seconds() / 86400 <= PreferenceProfileBuilder.half_life_days
                for item in profile.evidence
            )
        )
        ranked.sort(key=lambda row: (
            exposure_tier(row.candidate),
            -row.score if has_reliable_preference else 0,
            guarded_positions.get(
                row.candidate.candidate_id,
                positions.get(row.candidate.candidate_id, len(positions)),
            ),
            row.candidate.candidate_id,
        ))
        return RankingOutcome("RANKED_SHADOW_ONLY", tuple(ranked), tuple(exclusions))

    @staticmethod
    def _hard_pass(candidate: RecipeCandidate, constraints: ConstraintContext) -> bool:
        if candidate.status in {CandidateStatus.REVOKED, CandidateStatus.REJECTED, CandidateStatus.QUARANTINED}:
            return False
        if candidate.canonical_nutrition is None:
            return False
        return RecipeQualityGate.hard_pass(RecipeQualityGate().evaluate(candidate, constraints))

    @staticmethod
    def _nutrition_fit(candidate: RecipeCandidate, constraints: ConstraintContext) -> float:
        nutrition = candidate.canonical_nutrition
        if nutrition is None:
            return 0.0
        calories = 1.0
        protein = 1.0
        if constraints.target_kcal and constraints.target_kcal > 0:
            calories = max(0.0, 1.0 - abs(nutrition.energy_kcal - constraints.target_kcal) / constraints.target_kcal)
        if constraints.target_protein_g is not None and constraints.target_protein_g > 0:
            protein = min(1.0, nutrition.protein_g / constraints.target_protein_g)
        return round((0.70 * calories) + (0.30 * protein), 6)

    @staticmethod
    def _mapping_quality(candidate: RecipeCandidate) -> float:
        if not candidate.mappings:
            return 0.0
        exact = sum(mapping.status == MappingStatus.EXACT for mapping in candidate.mappings)
        high = sum(mapping.status == MappingStatus.HIGH_CONFIDENCE for mapping in candidate.mappings)
        return round((exact + (0.8 * high)) / len(candidate.mappings), 6)

    @staticmethod
    def _repeat_penalty(features: CandidateFeatures, context: RecommendationContext) -> float:
        history = context.recent_recommendations + context.recently_consumed
        penalty = 0.0
        for entry in history:
            if _normalise(entry.dish) == _normalise(features.dish):
                penalty = max(penalty, 0.70)
            elif features.primary_protein and entry.primary_protein == features.primary_protein:
                penalty = max(penalty, 0.35)
            elif features.cuisine and entry.cuisine == features.cuisine:
                penalty = max(penalty, 0.15)
            elif features.preparation and entry.preparation == features.preparation:
                penalty = max(penalty, 0.12)
        return penalty

    @staticmethod
    def _novelty(features: CandidateFeatures, context: RecommendationContext) -> float:
        prior = context.recent_recommendations + context.recently_consumed
        return 1.0 if all(entry.candidate_id != features.candidate_id for entry in prior) else 0.25

    def _score(self, parts: RankingComponents) -> float:
        return (
            self.policy.nutrition_weight * parts.nutrition_fit
            + self.policy.preference_weight * parts.preference_fit
            + self.policy.source_quality_weight * parts.source_quality
            + self.policy.mapping_quality_weight * parts.mapping_quality
            + self.policy.portion_fit_weight * parts.portion_fit_quality
            + self.policy.diversity_weight * parts.diversity_score
            + self.policy.novelty_weight * parts.novelty_score
            + self.policy.cooking_effort_weight * parts.cooking_effort_fit
            + self.policy.budget_weight * parts.budget_fit
        )

    @staticmethod
    def _reasons(
        candidate: RecipeCandidate,
        source_type: CandidateSourceType,
        components: RankingComponents,
        insufficient: bool,
        explicit_preference: bool,
        *,
        dish_requested: bool = False,
    ) -> tuple[RankingReasonCode, ...]:
        reasons: list[RankingReasonCode] = []
        if components.nutrition_fit >= 0.75:
            reasons.append(RankingReasonCode.NUTRITION_REMAINING_FIT)
        if components.preference_fit >= 0.60:
            reasons.append(
                RankingReasonCode.CONFIRMED_PREFERENCE_MATCH
                if explicit_preference
                else RankingReasonCode.INFERRED_PREFERENCE_MATCH
            )
        if not dish_requested and components.recent_repetition_penalty == 0 and components.diversity_score >= 1.0:
            reasons.append(RankingReasonCode.DIVERSITY_PROTEIN_ROTATION)
        if components.portion_fit_quality >= 0.75:
            reasons.append(RankingReasonCode.PORTION_ADAPTABLE)
        source_reason = {
            CandidateSourceType.LOCAL_CANONICAL: RankingReasonCode.CANONICAL_SOURCE,
            CandidateSourceType.PERSONAL_RECIPE: RankingReasonCode.PERSONAL_RECIPE_EVIDENCE,
            CandidateSourceType.STAGING_EXTERNAL: RankingReasonCode.STAGING_SOURCE,
            CandidateSourceType.RUNTIME_EXTERNAL: RankingReasonCode.RUNTIME_EXTERNAL_SOURCE,
        }[source_type]
        reasons.append(source_reason)
        if insufficient:
            reasons.append(RankingReasonCode.PREFERENCE_EVIDENCE_INSUFFICIENT)
        # Retain a bounded stable order and never expose rank weights.
        return tuple(dict.fromkeys(reasons))

    def _prevent_novelty_only_external_promotion(
        self, rows: list[RankedRecommendation]
    ) -> list[RankedRecommendation]:
        canonical = [row for row in rows if row.source_type == CandidateSourceType.LOCAL_CANONICAL]
        if not canonical:
            return rows
        best_canonical = max(canonical, key=lambda row: row.score)
        canonical_without_novelty = best_canonical.score - self.policy.novelty_weight * best_canonical.components.novelty_score
        adjusted: list[RankedRecommendation] = []
        for row in rows:
            if row.source_type in {CandidateSourceType.STAGING_EXTERNAL, CandidateSourceType.RUNTIME_EXTERNAL}:
                external_without_novelty = row.score - self.policy.novelty_weight * row.components.novelty_score
                if row.score > best_canonical.score and external_without_novelty <= canonical_without_novelty:
                    row = RankedRecommendation(
                        candidate=row.candidate,
                        source_type=row.source_type,
                        score=best_canonical.score,
                        components=row.components,
                        reason_codes=row.reason_codes,
                        policy_version=row.policy_version,
                    )
            adjusted.append(row)
        return sorted(adjusted, key=lambda row: (-row.score, row.candidate.candidate_id))


@dataclass(frozen=True)
class ExplorationDecision:
    selected: RankedRecommendation
    policy_version: str
    promoted_for_exploration: bool
    selection_probability: float


class DeterministicExplorationPolicy:
    """A bounded, explainable exploration heuristic for shadow use only."""

    version = EXPLORATION_POLICY_V1

    def choose(self, ranked: Sequence[RankedRecommendation]) -> ExplorationDecision | None:
        if not ranked:
            return None
        baseline = ranked[0]
        # Promote at most one unseen, high-quality candidate that is already
        # within 0.06 of baseline.  The hash rule is deterministic and makes
        # replay possible without presenting a learned policy as production.
        alternatives = [
            row
            for row in ranked[1:]
            if row.components.novelty_score >= 1.0 and row.score >= baseline.score - 0.06
        ]
        if not alternatives:
            return ExplorationDecision(baseline, self.version, False, 1.0)
        seed = int(hashlib.sha256(baseline.candidate.candidate_id.encode("utf-8")).hexdigest()[:2], 16)
        if seed % 5:
            return ExplorationDecision(baseline, self.version, False, 1.0)
        candidate = alternatives[0]
        reasons = tuple(dict.fromkeys(candidate.reason_codes + (RankingReasonCode.EXPLORATION_PROMOTED,)))
        promoted = RankedRecommendation(
            candidate=candidate.candidate,
            source_type=candidate.source_type,
            score=candidate.score,
            components=candidate.components,
            reason_codes=reasons,
            policy_version=candidate.policy_version,
        )
        return ExplorationDecision(promoted, self.version, True, 1.0)


@dataclass(frozen=True)
class ShadowRecommendationLog:
    candidate_set_ids: tuple[str, ...]
    selected_candidate_id: str
    policy_version: str
    context_fingerprint: str
    selection_probability: float | None
    outcome_event: FeedbackEventType | None = None
    # Baseline remains authoritative. This makes it possible to compare a
    # shadow alternative without pretending it was delivered to the user.
    production_selected_candidate_id: str | None = None
    # When a shadow log accompanies a delivered card, this binds later
    # feedback to the exact exposure rather than merely matching a dish.
    recommendation_event_id: str | None = None


class ShadowBanditPolicy:
    """Optional contextual-bandit scorer.  It never selects production output."""

    version = SHADOW_BANDIT_POLICY_V1

    _REWARDS: Mapping[FeedbackEventType, float] = {
        FeedbackEventType.ACTUALLY_CONSUMED: 1.0,
        FeedbackEventType.REPEATED_CONSUMPTION: 1.0,
        FeedbackEventType.LIKED: 0.8,
        FeedbackEventType.SAVED: 0.35,
        FeedbackEventType.REJECTED: -0.45,
        FeedbackEventType.DISLIKED: -0.8,
    }

    def choose_shadow(
        self,
        ranked: Sequence[RankedRecommendation],
        logs: Iterable[ShadowRecommendationLog],
    ) -> ExplorationDecision | None:
        if not ranked:
            return None
        outcome_rows = [row for row in logs if row.outcome_event in self._REWARDS]
        count = Counter(row.selected_candidate_id for row in outcome_rows)
        rewards: dict[str, float] = defaultdict(float)
        for row in outcome_rows:
            assert row.outcome_event is not None
            rewards[row.selected_candidate_id] += self._REWARDS[row.outcome_event]
        total = sum(count.values())
        choice = max(
            ranked,
            key=lambda item: (
                (
                    (rewards[item.candidate.candidate_id] / count[item.candidate.candidate_id])
                    if count[item.candidate.candidate_id]
                    else 0.0
                )
                + math.sqrt(math.log(total + 2) / (count[item.candidate.candidate_id] + 1)) * 0.10,
                item.score,
                item.candidate.candidate_id,
            ),
        )
        return ExplorationDecision(choice, self.version, choice.candidate.candidate_id != ranked[0].candidate.candidate_id, 1.0)

    @classmethod
    def reward_for(cls, event: FeedbackEvent) -> float | None:
        # SHOWN and OPENED intentionally return None; no accidental reward.
        return cls._REWARDS.get(event.event_type)


@dataclass(frozen=True)
class CatalogGapObservation:
    normalized_query: str
    request_count: int = 0
    consumption_count: int = 0
    search_count: int = 0
    unmapped_count: int = 0
    regional_gap_count: int = 0
    correction_count: int = 0
    low_diversity_count: int = 0
    source_availability: float = 0.0
    mapping_potential: float = 0.0
    regional_relevance: float = 0.0


@dataclass(frozen=True)
class CatalogGapCandidate:
    gap_id: str
    normalized_query: str
    reason_codes: tuple[str, ...]
    aggregate_evidence: Mapping[str, int]
    priority_score: float


@dataclass(frozen=True)
class EvidenceAcquisitionTask:
    task_id: str
    gap_id: str
    task_type: str
    normalized_query: str
    priority_score: float
    status: str = "OPEN"


class CatalogGapDetector:
    """Turns de-identified aggregate evidence into a human-review queue."""

    def detect(self, observations: Iterable[CatalogGapObservation]) -> list[CatalogGapCandidate]:
        gaps: list[CatalogGapCandidate] = []
        for row in observations:
            query = _normalise(row.normalized_query)
            if not query:
                continue
            evidence = {
                "request_count": _nonnegative_int(row.request_count),
                "consumption_count": _nonnegative_int(row.consumption_count),
                "search_count": _nonnegative_int(row.search_count),
                "unmapped_count": _nonnegative_int(row.unmapped_count),
                "regional_gap_count": _nonnegative_int(row.regional_gap_count),
                "correction_count": _nonnegative_int(row.correction_count),
                "low_diversity_count": _nonnegative_int(row.low_diversity_count),
            }
            reasons = _gap_reasons(evidence)
            if not reasons:
                continue
            priority = min(
                1.0,
                0.23 * min(evidence["request_count"], 10) / 10
                + 0.18 * min(evidence["consumption_count"], 10) / 10
                + 0.12 * min(evidence["search_count"], 10) / 10
                + 0.17 * min(evidence["unmapped_count"], 10) / 10
                + 0.10 * min(evidence["regional_gap_count"], 10) / 10
                + 0.12 * min(evidence["correction_count"], 10) / 10
                + 0.04 * min(evidence["low_diversity_count"], 10) / 10
                + 0.02 * _clamp(row.mapping_potential)
                + 0.01 * _clamp(row.regional_relevance)
                + 0.01 * _clamp(row.source_availability),
            )
            gaps.append(
                CatalogGapCandidate(
                    gap_id=str(uuid4()),
                    normalized_query=query,
                    reason_codes=tuple(reasons),
                    aggregate_evidence=evidence,
                    priority_score=round(priority, 6),
                )
            )
        return sorted(gaps, key=lambda gap: (-gap.priority_score, gap.normalized_query))

    def tasks_for(self, gap: CatalogGapCandidate) -> tuple[EvidenceAcquisitionTask, ...]:
        kinds: list[str] = []
        if any(code in gap.reason_codes for code in {"UNKNOWN_DISH", "EXTERNAL_SEARCH_CLUSTER", "LOW_DIVERSITY"}):
            kinds.append("FIND_RECIPE_SOURCE")
        if "UNMAPPED_INGREDIENT" in gap.reason_codes:
            kinds.extend(("RESOLVE_ALIAS", "RESOLVE_INGREDIENT_MAPPING"))
        if "CORRECTION_CLUSTER" in gap.reason_codes:
            kinds.extend(("VERIFY_SERVING", "VERIFY_VARIANT_IDENTITY"))
        if "FREQUENT_PERSONAL_CONSUMPTION" in gap.reason_codes:
            kinds.append("COLLECT_MORE_USER_CONFIRMATION")
        return tuple(
            EvidenceAcquisitionTask(str(uuid4()), gap.gap_id, kind, gap.normalized_query, gap.priority_score)
            for kind in dict.fromkeys(kinds)
        )


@dataclass(frozen=True)
class ReplayInteraction:
    candidates: tuple[RecipeCandidate, ...]
    context: RecommendationContext
    selected_candidate_id: str | None
    outcome_event: FeedbackEventType | None
    preference_profile: UserPreferenceProfile | None = None


@dataclass(frozen=True)
class ReplayMetrics:
    interaction_count: int
    hard_constraint_violations: int
    top_k_overlap: float
    diversity: float
    novelty: float
    preference_match: float
    repeat_reduction: float
    nutrition_fit: float
    source_quality: float
    valid_acceptance_outcome_rate: float | None


class RecommendationReplayEvaluator:
    """Engineering replay.  Observational outcomes are never causal proof."""

    def evaluate(self, interactions: Iterable[ReplayInteraction], *, top_k: int = 3) -> ReplayMetrics:
        rows = list(interactions)
        if not rows:
            return ReplayMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None)
        ranker = RecommendationRankerV2()
        overlaps: list[float] = []
        diversity: list[float] = []
        novelty: list[float] = []
        preference: list[float] = []
        repetition: list[float] = []
        nutrition: list[float] = []
        source: list[float] = []
        accepted: list[float] = []
        violations = 0
        for interaction in rows:
            v2 = ranker.rank(
                interaction.candidates,
                context=interaction.context,
                preference_profile=interaction.preference_profile,
            )
            baseline = [
                candidate
                for candidate in sorted(interaction.candidates, key=lambda item: item.candidate_id)
                if RecommendationRankerV2._hard_pass(candidate, interaction.context.constraints)
            ]
            if any(not RecommendationRankerV2._hard_pass(item.candidate, interaction.context.constraints) for item in v2):
                violations += 1
            baseline_ids = {item.candidate_id for item in baseline[:top_k]}
            v2_ids = {item.candidate.candidate_id for item in v2[:top_k]}
            overlaps.append(len(baseline_ids & v2_ids) / max(len(baseline_ids | v2_ids), 1))
            if v2:
                best = v2[0].components
                diversity.append(best.diversity_score)
                novelty.append(best.novelty_score)
                preference.append(best.preference_fit)
                repetition.append(1.0 - best.recent_repetition_penalty)
                nutrition.append(best.nutrition_fit)
                source.append(best.source_quality)
            if interaction.outcome_event in {
                FeedbackEventType.ACTUALLY_CONSUMED,
                FeedbackEventType.REPEATED_CONSUMPTION,
                FeedbackEventType.LIKED,
                FeedbackEventType.SAVED,
                FeedbackEventType.REJECTED,
                FeedbackEventType.DISLIKED,
            }:
                accepted.append(float(interaction.outcome_event in {
                    FeedbackEventType.ACTUALLY_CONSUMED,
                    FeedbackEventType.REPEATED_CONSUMPTION,
                    FeedbackEventType.LIKED,
                    FeedbackEventType.SAVED,
                }))
        return ReplayMetrics(
            interaction_count=len(rows),
            hard_constraint_violations=violations,
            top_k_overlap=_mean(overlaps),
            diversity=_mean(diversity),
            novelty=_mean(novelty),
            preference_match=_mean(preference),
            repeat_reduction=_mean(repetition),
            nutrition_fit=_mean(nutrition),
            source_quality=_mean(source),
            valid_acceptance_outcome_rate=_mean(accepted) if accepted else None,
        )


@dataclass(frozen=True)
class LearningQualityMetrics:
    """Descriptive development metrics; deliberately no composite AI score."""

    repeat_dish_rate: float
    repeat_protein_rate: float
    candidate_diversity: float
    catalog_coverage: float
    external_discovery_frequency: float
    personal_recipe_usage: float
    preference_signal_coverage: float
    explicit_vs_implicit_evidence_ratio: float | None
    portion_correction_rate: float
    catalog_gap_detection_count: int


def calculate_learning_quality_metrics(
    *,
    recommendation_memory: Iterable[RecommendationMemoryEntry],
    feedback_events: Iterable[FeedbackEvent],
    viable_candidate_count: int,
    catalog_candidate_count: int,
    catalog_gap_count: int,
) -> LearningQualityMetrics:
    """Calculate bounded engineering metrics without exposing personal rows."""

    memory = list(recommendation_memory)
    feedback = list(feedback_events)
    repeat_dish = sum(
        1
        for previous, current in zip(memory, memory[1:])
        if _normalise(previous.dish) == _normalise(current.dish)
    )
    repeat_protein = sum(
        1
        for previous, current in zip(memory, memory[1:])
        if previous.primary_protein
        and previous.primary_protein == current.primary_protein
    )
    unique_dishes = len({_normalise(row.dish) for row in memory if row.dish})
    external = sum(
        row.source_type in {CandidateSourceType.STAGING_EXTERNAL, CandidateSourceType.RUNTIME_EXTERNAL}
        for row in memory
    )
    personal = sum(row.source_type == CandidateSourceType.PERSONAL_RECIPE for row in memory)
    preference_events = [
        row
        for row in feedback
        if row.event_type
        not in {
            FeedbackEventType.SHOWN,
            FeedbackEventType.OPENED,
            FeedbackEventType.PORTION_CORRECTED,
            FeedbackEventType.INGREDIENT_CORRECTED,
            FeedbackEventType.RECIPE_CORRECTED,
        }
    ]
    explicit = sum(row.explicit for row in preference_events)
    implicit = len(preference_events) - explicit
    corrections = sum(row.event_type == FeedbackEventType.PORTION_CORRECTED for row in feedback)
    denominator = max(len(memory) - 1, 1)
    return LearningQualityMetrics(
        repeat_dish_rate=round(repeat_dish / denominator, 6),
        repeat_protein_rate=round(repeat_protein / denominator, 6),
        candidate_diversity=round(unique_dishes / max(len(memory), 1), 6),
        catalog_coverage=round(viable_candidate_count / max(catalog_candidate_count, 1), 6),
        external_discovery_frequency=round(external / max(len(memory), 1), 6),
        personal_recipe_usage=round(personal / max(len(memory), 1), 6),
        preference_signal_coverage=round(len(preference_events) / max(len(feedback), 1), 6),
        explicit_vs_implicit_evidence_ratio=(
            round(explicit / implicit, 6) if implicit else (float("inf") if explicit else None)
        ),
        portion_correction_rate=round(corrections / max(len(feedback), 1), 6),
        catalog_gap_detection_count=max(catalog_gap_count, 0),
    )


def hard_safety_invariants() -> dict[str, int]:
    """N3.2 release assertions, all of which must remain zero.

    The values are intentionally not feature flags. Their implementation is
    distributed across the hard gate, private repository, shadow-only config,
    and closed canonical writer; this map makes the required audit surface
    explicit for tests and reports.
    """

    return {
        "PREFERENCE_OVERRIDES_ALLERGY": 0,
        "PREFERENCE_OVERRIDES_DIETARY_RESTRICTION": 0,
        "PREFERENCE_OVERRIDES_POLICY_SAFETY": 0,
        "IMPLICIT_FEEDBACK_PROMOTED_TO_HARD_FACT": 0,
        "SHOWN_AS_CONSUMED": 0,
        "OPENED_AS_POSITIVE_REWARD": 0,
        "FEEDBACK_CREATED_MEAL_LOG": 0,
        "PERSONAL_DATA_GLOBAL_LEAK": 0,
        "LLM_DIRECT_CANONICAL_WRITE": 0,
        "CANONICAL_AUTO_PROMOTION": 0,
        "BANDIT_CONTROLS_PRODUCTION": 0,
        "WEB_NUTRITION_AS_AUTHORITY": 0,
        "RESEARCH_CORPUS_MUTATION": 0,
    }


def source_type_for(candidate: RecipeCandidate) -> CandidateSourceType:
    if candidate.trust_domain == TrustDomain.CANONICAL_PRODUCTION_RECIPE:
        return CandidateSourceType.LOCAL_CANONICAL
    if candidate.trust_domain == TrustDomain.PERSONAL_RECIPE:
        return CandidateSourceType.PERSONAL_RECIPE
    if candidate.trust_domain == TrustDomain.STAGING_RECIPE:
        return CandidateSourceType.STAGING_EXTERNAL
    return CandidateSourceType.RUNTIME_EXTERNAL


def features_for(candidate: RecipeCandidate) -> CandidateFeatures:
    ingredients = tuple(
        mapping.canonical_food_id
        for mapping in candidate.mappings
        if mapping.canonical_food_id
    )
    protein = next(
        (
            food_id
            for food_id in ingredients
            if any(token in food_id.casefold() for token in ("chicken", "beef", "pork", "fish", "shrimp", "tofu", "egg"))
        ),
        None,
    )
    cuisine = next((tag.split(":", 1)[1] for tag in candidate.dietary_tags if tag.startswith("cuisine:")), None)
    preparation = next((tag.split(":", 1)[1] for tag in candidate.dietary_tags if tag.startswith("preparation:")), None)
    return CandidateFeatures(
        candidate_id=candidate.candidate_id,
        dish=candidate.title,
        ingredients=ingredients,
        primary_protein=protein,
        cuisine=cuisine,
        preparation=preparation,
    )


def _feature_values(features: CandidateFeatures) -> tuple[tuple[PreferenceDimension, str], ...]:
    values: list[tuple[PreferenceDimension, str]] = [(PreferenceDimension.DISH, features.dish)]
    values.extend((PreferenceDimension.INGREDIENT, item) for item in features.ingredients)
    optional = (
        (PreferenceDimension.PROTEIN, features.primary_protein),
        (PreferenceDimension.CUISINE, features.cuisine),
        (PreferenceDimension.PREPARATION, features.preparation),
        (PreferenceDimension.COOKING_EFFORT, features.cooking_effort),
        (PreferenceDimension.BUDGET, features.budget_band),
    )
    values.extend((dimension, value) for dimension, value in optional if value)
    return tuple(values)


def _source_quality(source: CandidateSourceType) -> float:
    return {
        CandidateSourceType.LOCAL_CANONICAL: 1.0,
        CandidateSourceType.PERSONAL_RECIPE: 0.85,
        CandidateSourceType.STAGING_EXTERNAL: 0.72,
        CandidateSourceType.RUNTIME_EXTERNAL: 0.55,
    }[source]


def _attribute_fit(candidate_value: str | None, requested: str | None) -> float:
    if not requested:
        return 1.0
    if not candidate_value:
        return 0.50
    return 1.0 if _normalise(candidate_value) == _normalise(requested) else 0.15


def _gap_reasons(evidence: Mapping[str, int]) -> tuple[str, ...]:
    reasons: list[str] = []
    if evidence["request_count"] >= 2:
        reasons.append("UNKNOWN_DISH")
    if evidence["consumption_count"] >= 2:
        reasons.append("FREQUENT_PERSONAL_CONSUMPTION")
    if evidence["search_count"] >= 2:
        reasons.append("EXTERNAL_SEARCH_CLUSTER")
    if evidence["unmapped_count"] >= 1:
        reasons.append("UNMAPPED_INGREDIENT")
    if evidence["regional_gap_count"] >= 1:
        reasons.append("REGIONAL_DISH_GAP")
    if evidence["correction_count"] >= 1:
        reasons.append("CORRECTION_CLUSTER")
    if evidence["low_diversity_count"] >= 2:
        reasons.append("LOW_DIVERSITY")
    return tuple(reasons)


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return " ".join("".join(char for char in decomposed if unicodedata.category(char) != "Mn").split())


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _signed_clamp(value: float) -> float:
    return min(1.0, max(-1.0, value))


def _nonnegative_int(value: int) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


__all__ = [
    "CandidateFeatures",
    "CandidateSourceType",
    "CatalogGapCandidate",
    "CatalogGapDetector",
    "CatalogGapObservation",
    "LearningQualityMetrics",
    "ConfirmedPreference",
    "DeterministicExplorationPolicy",
    "EvidenceAcquisitionTask",
    "EXPLORATION_POLICY_V1",
    "ExplorationDecision",
    "PortionLearning",
    "PortionObservation",
    "PortionPrior",
    "PreferenceDimension",
    "PreferenceEvidence",
    "PreferenceProfileBuilder",
    "PreferenceSource",
    "RANKING_POLICY_V2",
    "RankedRecommendation",
    "RankerV2Policy",
    "RankingComponents",
    "RankingReasonCode",
    "RecipeCorrectionDisposition",
    "RecommendationContext",
    "RecommendationMemoryEntry",
    "RecommendationRankerV2",
    "RecommendationReplayEvaluator",
    "ReplayInteraction",
    "ReplayMetrics",
    "SHADOW_BANDIT_POLICY_V1",
    "ShadowBanditPolicy",
    "ShadowRecommendationLog",
    "UserPreferenceProfile",
    "classify_recipe_correction",
    "calculate_learning_quality_metrics",
    "features_for",
    "hard_safety_invariants",
    "source_type_for",
]
