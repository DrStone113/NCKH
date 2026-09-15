"""Private-memory, staging, shadow, and promotion controls for N3."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .contracts import (
    CandidateStatus,
    FeedbackEvent,
    FeedbackRejectionReason,
    FeedbackEventType,
    PromotionClass,
    RecipeCandidate,
    TrustDomain,
)
from .engine import AdaptiveRecipeError, RecipeQualityGate, load_adaptive_source_registry
from .eligibility import CandidateEligibilityGate
from .intelligence import (
    ConfirmedPreference,
    PortionLearning,
    PortionObservation,
    PortionPrior,
    PreferenceProfileBuilder,
    RecommendationMemoryEntry,
    ShadowRecommendationLog,
    UserPreferenceProfile,
    source_type_for,
)


_ALLOWED_FEEDBACK_TYPES = frozenset(item.value for item in FeedbackEventType)
_PRIVATE_KEYS = frozenset(
    {"user_id", "owner_user_id", "health_condition", "weight", "goal", "conversation", "chat_text"}
)
_ALLOWED_FEEDBACK_METADATA_KEYS = frozenset(
    {"portion_grams", "corrected_quantity_grams", "ingredient_key", "correction_scope"}
)
_EVENT_WEIGHTS = {
    FeedbackEventType.SHOWN: 0.0,
    FeedbackEventType.OPENED: 0.0,
    FeedbackEventType.SAVED: 0.15,
    FeedbackEventType.REJECTED: -0.25,
    FeedbackEventType.SUBSTITUTED: -0.10,
    FeedbackEventType.LIKED: 0.70,
    FeedbackEventType.DISLIKED: -0.80,
    FeedbackEventType.ACTUALLY_CONSUMED: 0.25,
    FeedbackEventType.REPEATED: 0.12,
    FeedbackEventType.REPEATED_CONSUMPTION: 0.45,
    # A correction is evidence about a portion or recipe, not a preference.
    FeedbackEventType.PORTION_CORRECTED: 0.0,
    FeedbackEventType.INGREDIENT_CORRECTED: 0.0,
    FeedbackEventType.RECIPE_CORRECTED: 0.0,
}
PREFERENCE_HALF_LIFE_DAYS = 90.0


@dataclass(frozen=True)
class PersonalDishAlias:
    owner_user_id: str
    alias: str
    canonical_recipe_id: str | None
    provenance_type: str
    created_at: datetime


@dataclass(frozen=True)
class EvidenceAcquisitionQueueItem:
    queue_id: str
    reason_code: str
    normalized_query: str
    aggregate_count: int
    status: str = "OPEN"


@dataclass(frozen=True)
class EvidenceAcquisitionPriorityItem:
    queue_id: str
    reason_code: str
    normalized_query: str
    aggregate_signals: Mapping[str, int]
    priority_score: float
    status: str = "OPEN"


@dataclass(frozen=True)
class PersonalRecipeAcquisitionCandidate:
    owner_user_id: str
    normalized_dish_name: str
    observation_count: int
    status: str = "PERSONAL_RECIPE_ACQUISITION_CANDIDATE"


@dataclass(frozen=True)
class RecipePromotionDecision:
    decision_id: str
    candidate_id: str
    decision_class: PromotionClass
    hard_gate_codes: tuple[str, ...]
    evidence_hash: str
    canonical_write_authorized: bool
    rationale: str


@dataclass(frozen=True)
class PromotionEvidenceScorecard:
    """Transparent eligibility evidence, separate from release authorization."""

    candidate_id: str
    evidence_hash: str
    eligibility_class: str
    source_policy_pass: bool
    mapping_complete: bool
    nutrition_complete: bool
    allergen_validation_pass: bool
    duplicate_resolved: bool
    source_nutrition_conflict: bool
    runtime_stability_pass: bool
    shadow_evidence_present: bool
    explicit_usage_events: int
    correction_events: int
    score: float
    reasons: tuple[str, ...]


class CanonicalRecipeWriter:
    """A deliberately closed canonical boundary for N3.1.

    N3.1 has no database/catalog writer implementation.  This object makes
    every attempted release validate its evidence first and then rejects it
    because the feature flag is off.  An LLM cannot turn a scorecard or a
    candidate into an INSERT/UPDATE operation.
    """

    auto_promotion_enabled: bool = False

    def write(self, decision: RecipePromotionDecision, candidate: RecipeCandidate) -> None:
        if not decision.evidence_hash or decision.evidence_hash != candidate.evidence.evidence_hash:
            raise AdaptiveRecipeError("CANONICAL_WRITE_EVIDENCE_HASH_MISMATCH")
        if not RecipeQualityGate.hard_pass(candidate.validation_codes):
            raise AdaptiveRecipeError("CANONICAL_WRITE_FAILED_HARD_GATE")
        if not decision.canonical_write_authorized or not self.auto_promotion_enabled:
            raise AdaptiveRecipeError("CANONICAL_AUTO_PROMOTION_DISABLED")
        # Defensive terminal boundary: this phase has no canonical writer.
        raise AdaptiveRecipeError("CANONICAL_WRITER_NOT_AVAILABLE_IN_N3_1")


@dataclass(frozen=True)
class PromotionPolicy:
    """N3 rollout policy. Canonical auto-promotion is intentionally off."""

    canonical_auto_promotion_enabled: bool = False
    require_shadow_evidence: bool = True

    def decide(
        self,
        candidate: RecipeCandidate,
        *,
        automated_reviews: Iterable[Mapping[str, Any]] = (),
    ) -> RecipePromotionDecision:
        codes = tuple(sorted(set(candidate.validation_codes)))
        if not RecipeQualityGate.hard_pass(codes):
            decision = (
                PromotionClass.QUARANTINED
                if "UNTRUSTED_CONTENT_QUARANTINED" in codes
                else PromotionClass.REJECTED
            )
            return self._decision(candidate, decision, codes, "FAILED_HARD_GATE")
        if candidate.status != CandidateStatus.SHADOW_ELIGIBLE:
            return self._decision(
                candidate,
                PromotionClass.REQUIRES_MORE_EVIDENCE,
                codes,
                "SHADOW_EVIDENCE_REQUIRED",
            )
        reviews = list(automated_reviews)
        if any(str(review.get("verdict") or "").upper() == "REJECT" for review in reviews):
            return self._decision(candidate, PromotionClass.REJECTED, codes, "AUTOMATED_REVIEW_REJECTED")
        # Auto promotion cannot be inferred from a model verdict or a quality
        # score. The policy remains disabled even when all evidence is clean.
        if not self.canonical_auto_promotion_enabled:
            return self._decision(
                candidate,
                PromotionClass.REQUIRES_REVIEW,
                codes,
                "CANONICAL_AUTO_PROMOTION_DISABLED",
            )
        return self._decision(
            candidate,
            PromotionClass.REQUIRES_REVIEW,
            codes,
            "EXPLICIT_RELEASE_APPROVAL_REQUIRED",
        )

    @staticmethod
    def _decision(
        candidate: RecipeCandidate,
        decision_class: PromotionClass,
        codes: tuple[str, ...],
        rationale: str,
    ) -> RecipePromotionDecision:
        return RecipePromotionDecision(
            decision_id=str(uuid4()),
            candidate_id=candidate.candidate_id,
            decision_class=decision_class,
            hard_gate_codes=codes,
            evidence_hash=candidate.evidence.evidence_hash,
            canonical_write_authorized=False,
            rationale=rationale,
        )

    @staticmethod
    def authorize_canonical_write(_: RecipePromotionDecision) -> None:
        raise AdaptiveRecipeError("CANONICAL_AUTO_PROMOTION_DISABLED")


def build_promotion_evidence_scorecard(
    candidate: RecipeCandidate,
    *,
    runtime_stability_pass: bool,
    explicit_usage_events: int = 0,
    correction_events: int = 0,
    source_policies: Mapping[str, Mapping[str, Any]] | None = None,
) -> PromotionEvidenceScorecard:
    """Calculate a non-opaque promotion eligibility scorecard.

    ``AUTO_PROMOTION_ELIGIBLE`` is only an evidence state.  It cannot grant a
    write, change the disabled feature flag, or bypass a release reviewer.
    """

    if explicit_usage_events < 0 or correction_events < 0:
        raise AdaptiveRecipeError("INVALID_PROMOTION_EVIDENCE_COUNTS")
    policies = source_policies or load_adaptive_source_registry()
    policy = policies.get(candidate.source.source_id)
    source_policy_pass = bool(policy and policy.get("promotion_eligible"))
    codes = set(candidate.validation_codes)
    hard_pass = RecipeQualityGate.hard_pass(codes)
    mapping_complete = not any(code.startswith("MAPPING_COVERAGE_INCOMPLETE") for code in codes)
    nutrition_complete = candidate.canonical_nutrition is not None and not any(
        code.startswith("CANONICAL_NUTRITION_UNAVAILABLE") for code in codes
    )
    allergen_validation_pass = not any(code.startswith("ALLERGEN_VIOLATION") for code in codes)
    duplicate_resolved = not any(code.startswith("DUPLICATE_RECIPE_CANDIDATE") for code in codes)
    source_nutrition_conflict = "SOURCE_NUTRITION_CONFLICT" in codes
    shadow_evidence_present = candidate.status == CandidateStatus.SHADOW_ELIGIBLE
    reasons: list[str] = []
    if not hard_pass:
        eligibility = "QUARANTINED" if "UNTRUSTED_CONTENT_QUARANTINED" in codes else "REJECTED"
        reasons.append("FAILED_DETERMINISTIC_HARD_GATE")
    elif not shadow_evidence_present:
        eligibility = "MORE_EVIDENCE_REQUIRED"
        reasons.append("SHADOW_EVIDENCE_REQUIRED")
    elif not source_policy_pass:
        eligibility = "REQUIRES_REVIEW"
        reasons.append("SOURCE_POLICY_MANUAL_REVIEW_REQUIRED")
    elif not runtime_stability_pass:
        eligibility = "MORE_EVIDENCE_REQUIRED"
        reasons.append("SOURCE_RUNTIME_STABILITY_REQUIRED")
    elif source_nutrition_conflict or correction_events:
        eligibility = "REQUIRES_REVIEW"
        reasons.append("CONFLICT_OR_CORRECTION_REVIEW_REQUIRED")
    else:
        eligibility = "AUTO_PROMOTION_ELIGIBLE"
        reasons.append("EVIDENCE_ELIGIBLE_RELEASE_REVIEW_STILL_REQUIRED")
    score = (
        0.15 * float(source_policy_pass)
        + 0.20 * float(mapping_complete)
        + 0.20 * float(nutrition_complete)
        + 0.15 * float(allergen_validation_pass)
        + 0.10 * float(duplicate_resolved)
        + 0.10 * float(runtime_stability_pass)
        + 0.05 * float(shadow_evidence_present)
        + 0.03 * min(explicit_usage_events, 3) / 3
        + 0.02 * float(correction_events == 0)
    )
    return PromotionEvidenceScorecard(
        candidate_id=candidate.candidate_id,
        evidence_hash=candidate.evidence.evidence_hash,
        eligibility_class=eligibility,
        source_policy_pass=source_policy_pass,
        mapping_complete=mapping_complete,
        nutrition_complete=nutrition_complete,
        allergen_validation_pass=allergen_validation_pass,
        duplicate_resolved=duplicate_resolved,
        source_nutrition_conflict=source_nutrition_conflict,
        runtime_stability_pass=runtime_stability_pass,
        shadow_evidence_present=shadow_evidence_present,
        explicit_usage_events=explicit_usage_events,
        correction_events=correction_events,
        score=round(score, 4),
        reasons=tuple(reasons),
    )


class AdaptiveRecipeRepository:
    """In-process reference repository for N3 orchestration and tests.

    Deployment persistence is represented by migration 014. This repository is
    deliberately owner-scoped for personal data and has no canonical writer.
    """

    def __init__(
        self,
        *,
        promotion_policy: PromotionPolicy | None = None,
        max_candidates_per_source: int = 100,
        eligibility_foods: Iterable[Mapping[str, Any]] | None = None,
        eligibility_dishes: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        if max_candidates_per_source < 1:
            raise AdaptiveRecipeError("INVALID_CANDIDATE_SOURCE_LIMIT")
        self._policy = promotion_policy or PromotionPolicy()
        self._max_candidates_per_source = max_candidates_per_source
        # Explicitly injected authority is reserved for isolated development
        # fixtures. Production leaves both values unset and always resolves
        # identities against the canonical live catalogs.
        self._eligibility_foods = (
            tuple(eligibility_foods) if eligibility_foods is not None else None
        )
        self._eligibility_dishes = (
            tuple(eligibility_dishes) if eligibility_dishes is not None else None
        )
        self._candidates: dict[str, RecipeCandidate] = {}
        # Canonical catalog entries are registered here only as read-only
        # delivery references. They never pass through ``save_candidate`` and
        # therefore cannot become a canonical write surface.
        self._trusted_delivery_references: dict[str, RecipeCandidate] = {}
        self._candidate_versions: dict[str, list[RecipeCandidate]] = {}
        self._feedback: list[FeedbackEvent] = []
        self._aliases: list[PersonalDishAlias] = []
        self._reviews: dict[str, list[dict[str, Any]]] = {}
        self._queue: dict[str, EvidenceAcquisitionQueueItem] = {}
        self._priority_queue: dict[str, EvidenceAcquisitionPriorityItem] = {}
        self._personal_unknown_dishes: dict[tuple[str, str], int] = {}
        # Recommendation exposure is kept separate from actual meal evidence.
        self._recommendation_memory: list[RecommendationMemoryEntry] = []
        self._portion_observations: list[PortionObservation] = []
        self._feedback_idempotency: dict[tuple[str, str], FeedbackEvent] = {}
        self._shadow_bandit_logs: list[ShadowRecommendationLog] = []
        # Aggregate-only signals for the catalog-gap detector.  No owner id,
        # health data or free text is carried into this collection.
        self._catalog_gap_feedback: dict[str, dict[str, int]] = {}

    def save_candidate(self, candidate: RecipeCandidate) -> RecipeCandidate:
        if candidate.trust_domain in {
            TrustDomain.CANONICAL_PRODUCTION_RECIPE,
            TrustDomain.FROZEN_RESEARCH_RECIPE,
        }:
            raise AdaptiveRecipeError("CANDIDATE_DOMAIN_WRITE_FORBIDDEN")
        if candidate.trust_domain == TrustDomain.PERSONAL_RECIPE and not candidate.owner_user_id:
            raise AdaptiveRecipeError("PERSONAL_RECIPE_REQUIRES_OWNER")
        if self._source_candidate_count(candidate) >= self._max_candidates_per_source:
            raise AdaptiveRecipeError("CANDIDATE_INGESTION_RATE_LIMITED")
        duplicate_ids = self._duplicate_candidate_ids(candidate)
        if duplicate_ids:
            validation_codes = tuple(
                sorted(set(candidate.validation_codes) | {"DUPLICATE_RECIPE_CANDIDATE"})
            )
            evidence = replace(
                candidate.evidence,
                duplicate_candidates=duplicate_ids,
                validation_codes=validation_codes,
            ).with_hash()
            candidate = replace(
                candidate,
                evidence=evidence,
                validation_codes=validation_codes,
                status=CandidateStatus.QUARANTINED,
                lifecycle_history=candidate.lifecycle_history
                + (CandidateStatus.QUARANTINED.value,),
                quality_score=None,
            )
        self._store(candidate)
        return candidate

    def create_personal_alias(
        self,
        *,
        owner_user_id: str,
        alias: str,
        provenance_type: str,
        canonical_recipe_id: str | None = None,
    ) -> PersonalDishAlias:
        if not owner_user_id.strip() or not alias.strip():
            raise AdaptiveRecipeError("PERSONAL_ALIAS_REQUIRES_OWNER_AND_ALIAS")
        if provenance_type not in {
            "EXPLICIT_USER_STATEMENT",
            "CONFIRMED_RECIPE",
            "ACTUAL_MEAL_LOG",
            "EXPLICIT_FEEDBACK",
            "IMPLICIT_INTERACTION",
        }:
            raise AdaptiveRecipeError("INVALID_PERSONAL_PROVENANCE")
        record = PersonalDishAlias(
            owner_user_id=owner_user_id,
            alias=alias.strip(),
            canonical_recipe_id=canonical_recipe_id,
            provenance_type=provenance_type,
            created_at=datetime.now(timezone.utc),
        )
        self._aliases.append(record)
        return record

    def create_personal_recipe(self, candidate_id: str, owner_user_id: str) -> RecipeCandidate:
        candidate = self._candidate_for_owner(candidate_id, owner_user_id)
        if not RecipeQualityGate.hard_pass(candidate.validation_codes):
            raise AdaptiveRecipeError("PERSONAL_RECIPE_FAILED_HARD_GATE")
        if candidate.trust_domain not in {
            TrustDomain.PERSONAL_RECIPE,
            TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        }:
            raise AdaptiveRecipeError("PERSONAL_RECIPE_INVALID_SOURCE_DOMAIN")
        personal = replace(
            candidate,
            trust_domain=TrustDomain.PERSONAL_RECIPE,
            owner_user_id=owner_user_id,
            status=CandidateStatus.STAGING,
            lifecycle_history=candidate.lifecycle_history + (CandidateStatus.STAGING.value,),
        )
        self._store(personal)
        return personal

    def stage(self, candidate_id: str) -> RecipeCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.status != CandidateStatus.VALIDATED:
            raise AdaptiveRecipeError("STAGING_REQUIRES_VALIDATED_CANDIDATE")
        staged = replace(
            candidate,
            trust_domain=TrustDomain.STAGING_RECIPE,
            status=CandidateStatus.STAGING,
            lifecycle_history=candidate.lifecycle_history + (CandidateStatus.STAGING.value,),
        )
        self._store(staged)
        return staged

    def mark_shadow_eligible(self, candidate_id: str) -> RecipeCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.status != CandidateStatus.STAGING:
            raise AdaptiveRecipeError("SHADOW_REQUIRES_STAGING_CANDIDATE")
        if not RecipeQualityGate.hard_pass(candidate.validation_codes):
            raise AdaptiveRecipeError("SHADOW_REQUIRES_HARD_GATE_PASS")
        shadow = replace(
            candidate,
            status=CandidateStatus.SHADOW_ELIGIBLE,
            lifecycle_history=candidate.lifecycle_history + (CandidateStatus.SHADOW_ELIGIBLE.value,),
        )
        self._store(shadow)
        return shadow

    def shadow_candidates(self) -> list[RecipeCandidate]:
        return [
            candidate
            for candidate in self._candidates.values()
            if candidate.status == CandidateStatus.SHADOW_ELIGIBLE
            and candidate.trust_domain == TrustDomain.STAGING_RECIPE
        ]

    def revoke(self, candidate_id: str, *, reason_code: str) -> RecipeCandidate:
        """Revoke a staging/shadow candidate without touching canonical data."""

        candidate = self._candidate(candidate_id)
        if not reason_code.strip():
            raise AdaptiveRecipeError("REVOCATION_REASON_REQUIRED")
        if candidate.status == CandidateStatus.REVOKED:
            return candidate
        revoked = replace(
            candidate,
            status=CandidateStatus.REVOKED,
            lifecycle_history=candidate.lifecycle_history + (CandidateStatus.REVOKED.value,),
        )
        self._store(revoked)
        return revoked

    def record_automated_review(
        self,
        *,
        candidate_id: str,
        judge_run_id: str,
        judge_model: str,
        verdict: str,
        reason: str,
        rubric_hash: str = "n3-semantic-suitability-rubric-v1",
    ) -> dict[str, Any]:
        self._candidate(candidate_id)
        if not judge_run_id.strip() or not judge_model.strip() or not rubric_hash.strip():
            raise AdaptiveRecipeError("AUTOMATED_REVIEW_PROVENANCE_REQUIRED")
        normalized_verdict = verdict.strip().upper()
        if normalized_verdict not in {"ACCEPT", "REJECT", "REVIEW"}:
            raise AdaptiveRecipeError("INVALID_AUTOMATED_REVIEW_VERDICT")
        record = {
            "review_source": "AUTOMATED",
            "judge_run_id": judge_run_id,
            "judge_model": judge_model,
            "rubric_hash": rubric_hash,
            "verdict": normalized_verdict,
            "reason": reason.strip(),
            "consensus": None,
            "automated_adjudication": None,
        }
        self._reviews.setdefault(candidate_id, []).append(record)
        return dict(record)

    def automated_adjudication(self, candidate_id: str) -> dict[str, Any]:
        """Create transparent consensus metadata without a fake human reviewer."""

        reviews = list(self._reviews.get(candidate_id, ()))
        if not reviews:
            raise AdaptiveRecipeError("AUTOMATED_REVIEW_REQUIRED")
        verdicts = [str(item["verdict"]) for item in reviews]
        consensus = "REJECT" if "REJECT" in verdicts else "ACCEPT" if all(
            verdict == "ACCEPT" for verdict in verdicts
        ) else "REVIEW"
        adjudication = {
            "review_source": "AUTOMATED",
            "consensus": consensus,
            "automated_adjudication": "UNANIMOUS" if len(set(verdicts)) == 1 else "DISAGREEMENT_REQUIRES_EVIDENCE",
            "judge_run_ids": tuple(item["judge_run_id"] for item in reviews),
            "same_model_multi_pass": len({item["judge_model"] for item in reviews}) == 1 and len(reviews) > 1,
        }
        for review in reviews:
            review["consensus"] = consensus
            review["automated_adjudication"] = adjudication["automated_adjudication"]
        return adjudication

    def promotion_decision(self, candidate_id: str) -> RecipePromotionDecision:
        candidate = self._candidate(candidate_id)
        return self._policy.decide(
            candidate,
            automated_reviews=self._reviews.get(candidate_id, ()),
        )

    def record_feedback(self, event: FeedbackEvent) -> tuple[FeedbackEvent, bool]:
        """Record a private feedback event exactly once for its owner key."""

        # Historical repository callers may carry only a recommendation
        # reference. The public N3.2.1 endpoint always supplies the complete
        # triple below; once policy/idempotency is present it must be exact.
        has_delivery_identity = bool(event.policy_version or event.idempotency_key)
        if has_delivery_identity and (
            not event.recommendation_id or not event.policy_version or not event.idempotency_key
        ):
            raise AdaptiveRecipeError("RECOMMENDATION_FEEDBACK_IDENTITY_REQUIRED")
        if event.idempotency_key:
            idempotency_identity = (event.owner_user_id, event.idempotency_key)
            previous = self._feedback_idempotency.get(idempotency_identity)
            if previous is not None:
                if (
                    previous.recommendation_id != event.recommendation_id
                    or previous.candidate_id != event.candidate_id
                    or previous.event_type != event.event_type
                    or previous.policy_version != event.policy_version
                ):
                    raise AdaptiveRecipeError("FEEDBACK_IDEMPOTENCY_KEY_REUSED")
                return previous, True
        event = self.validate_feedback_event(event)
        candidate = self._candidate_visible_to_owner(event.candidate_id, event.owner_user_id)
        if candidate.status in {CandidateStatus.REVOKED, CandidateStatus.REJECTED}:
            raise AdaptiveRecipeError("FEEDBACK_FOR_INELIGIBLE_CANDIDATE")
        self._feedback.append(event)
        if event.idempotency_key:
            self._feedback_idempotency[(event.owner_user_id, event.idempotency_key)] = event
        if event.recommendation_id:
            self._set_recommendation_outcome(event)
            self._set_shadow_outcome(event)
        return event, False

    @staticmethod
    def validate_feedback_event(event: FeedbackEvent) -> FeedbackEvent:
        """Validate the safe, typed feedback envelope without changing state.

        The SQL store calls this before opening its transaction so a malformed
        or privacy-unsafe envelope can never become a durable partial write.
        """

        if event.event_type.value not in _ALLOWED_FEEDBACK_TYPES:
            raise AdaptiveRecipeError("INVALID_FEEDBACK_EVENT")
        if event.reason_code is not None and event.event_type not in {
            FeedbackEventType.REJECTED,
            FeedbackEventType.SUBSTITUTED,
            FeedbackEventType.DISLIKED,
            FeedbackEventType.PORTION_CORRECTED,
        }:
            raise AdaptiveRecipeError("FEEDBACK_REASON_NOT_APPLICABLE")
        if event.event_type == FeedbackEventType.REJECTED and event.reason_code is None:
            # Older records without a reason remain readable, but new writes
            # must not silently turn every rejection into a dislike.
            event = replace(event, reason_code=FeedbackRejectionReason.OTHER)
        forbidden_metadata = _PRIVATE_KEYS & set(event.metadata)
        if forbidden_metadata:
            raise AdaptiveRecipeError(
                f"PRIVATE_DATA_IN_FEEDBACK:{','.join(sorted(forbidden_metadata))}"
            )
        unsupported_metadata = set(event.metadata) - _ALLOWED_FEEDBACK_METADATA_KEYS
        if unsupported_metadata:
            raise AdaptiveRecipeError(
                f"FEEDBACK_METADATA_NOT_ALLOWED:{','.join(sorted(unsupported_metadata))}"
            )
        if any(isinstance(value, (dict, list, tuple, set)) for value in event.metadata.values()):
            raise AdaptiveRecipeError("FEEDBACK_METADATA_MUST_BE_SCALAR")
        return event

    def candidate_visible_to_owner(self, *, candidate_id: str, owner_user_id: str) -> RecipeCandidate:
        """Read a candidate for shadow delivery without exposing private recipes."""

        return self._candidate_visible_to_owner(candidate_id, owner_user_id)

    def ranking_eligibility_gate(self) -> CandidateEligibilityGate:
        """Resolve source identities through this owner's live candidate view."""
        return CandidateEligibilityGate(
            foods=self._eligibility_foods,
            dishes=self._eligibility_dishes,
            candidate_lookup=self._candidate_visible_to_owner,
        )

    def register_trusted_delivery_reference(self, candidate: RecipeCandidate) -> RecipeCandidate:
        """Register a read-only canonical reference for one shadow event.

        This is intentionally not candidate ingestion: the canonical catalog
        is read elsewhere and this repository has no catalog writer.
        """

        if candidate.trust_domain != TrustDomain.CANONICAL_PRODUCTION_RECIPE:
            raise AdaptiveRecipeError("TRUSTED_DELIVERY_REFERENCE_MUST_BE_CANONICAL")
        if candidate.status != CandidateStatus.VALIDATED or not RecipeQualityGate.hard_pass(
            candidate.validation_codes
        ):
            raise AdaptiveRecipeError("TRUSTED_DELIVERY_REFERENCE_FAILED_HARD_GATE")
        self._trusted_delivery_references[candidate.candidate_id] = candidate
        return candidate

    def recommendation_for_owner(
        self, *, recommendation_id: str, owner_user_id: str
    ) -> RecommendationMemoryEntry:
        for entry in self._recommendation_memory:
            if entry.recommendation_id == recommendation_id and entry.owner_user_id == owner_user_id:
                return entry
        raise AdaptiveRecipeError("UNKNOWN_RECOMMENDATION_MEMORY")

    def record_recommendation(self, entry: RecommendationMemoryEntry) -> RecommendationMemoryEntry:
        """Persist a recommendation exposure, never a meal-consumption claim."""

        candidate = self._candidate_visible_to_owner(entry.candidate_id, entry.owner_user_id)
        self.ranking_eligibility_gate().require(candidate, owner_user_id=entry.owner_user_id)
        if entry.outcome_status != "SHOWN":
            raise AdaptiveRecipeError("RECOMMENDATION_MEMORY_MUST_START_AS_SHOWN")
        if entry.source_type != source_type_for(candidate):
            raise AdaptiveRecipeError("RECOMMENDATION_SOURCE_TYPE_MISMATCH")
        self._recommendation_memory.append(entry)
        return entry

    def recent_recommendations(
        self, *, owner_user_id: str, limit: int = 20
    ) -> tuple[RecommendationMemoryEntry, ...]:
        if limit < 1:
            raise AdaptiveRecipeError("INVALID_RECOMMENDATION_HISTORY_LIMIT")
        rows = [row for row in self._recommendation_memory if row.owner_user_id == owner_user_id]
        rows.sort(key=lambda row: row.shown_at, reverse=True)
        return tuple(rows[:limit])

    def record_shadow_bandit_log(self, record: ShadowRecommendationLog) -> None:
        """Store shadow-only comparison telemetry; it cannot select delivery."""

        if not record.candidate_set_ids or not record.context_fingerprint:
            raise AdaptiveRecipeError("SHADOW_BANDIT_LOG_IDENTITY_REQUIRED")
        if record.selection_probability is not None and not 0 <= record.selection_probability <= 1:
            raise AdaptiveRecipeError("INVALID_SHADOW_BANDIT_PROPENSITY")
        self._shadow_bandit_logs.append(record)

    def shadow_bandit_logs(self) -> tuple[ShadowRecommendationLog, ...]:
        return tuple(self._shadow_bandit_logs)

    def feedback_events(self, *, owner_user_id: str) -> tuple[FeedbackEvent, ...]:
        """Owner-scoped feedback for private profile building only."""

        return tuple(item for item in self._feedback if item.owner_user_id == owner_user_id)

    def feedback_for_recommendation(
        self, *, owner_user_id: str, recommendation_id: str
    ) -> tuple[FeedbackEvent, ...]:
        """Read an owner's exact feedback identity after reconnecting."""

        self.recommendation_for_owner(
            recommendation_id=recommendation_id, owner_user_id=owner_user_id
        )
        return tuple(
            item
            for item in self._feedback
            if item.owner_user_id == owner_user_id
            and item.recommendation_id == recommendation_id
        )

    def record_catalog_gap_feedback(self, event: FeedbackEvent) -> bool:
        """Aggregate eligible feedback without exporting personal behavior.

        Only non-personal staging/runtime candidates can add a compact signal.
        This creates evidence for review, never a recipe/canonical write.
        """

        candidate = self._candidate_visible_to_owner(event.candidate_id, event.owner_user_id)
        if candidate.owner_user_id is not None or candidate.trust_domain not in {
            TrustDomain.STAGING_RECIPE,
            TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
        }:
            return False
        query = _normalise_query(candidate.title)
        if not query:
            return False
        signal: str | None = None
        if (
            event.event_type == FeedbackEventType.REJECTED
            and event.reason_code == FeedbackRejectionReason.INGREDIENT_UNAVAILABLE
        ):
            signal = "request_count"
        elif event.event_type in {
            FeedbackEventType.INGREDIENT_CORRECTED,
            FeedbackEventType.RECIPE_CORRECTED,
        }:
            signal = "correction_count"
        if signal is None:
            return False
        counters = self._catalog_gap_feedback.setdefault(
            query, {"request_count": 0, "correction_count": 0}
        )
        counters[signal] += 1
        return True

    def catalog_gap_feedback_observations(self):
        """Return de-identified detector inputs; never raw feedback rows."""

        from .intelligence import CatalogGapObservation

        return tuple(
            CatalogGapObservation(
                normalized_query=query,
                request_count=counters["request_count"],
                correction_count=counters["correction_count"],
            )
            for query, counters in sorted(self._catalog_gap_feedback.items())
        )

    def build_preference_profile(
        self,
        *,
        owner_user_id: str,
        confirmed: Iterable[ConfirmedPreference] = (),
        now: datetime | None = None,
    ) -> UserPreferenceProfile:
        return PreferenceProfileBuilder().build(
            owner_user_id=owner_user_id,
            events=self.feedback_events(owner_user_id=owner_user_id),
            candidates={**self._candidates, **self._trusted_delivery_references},
            confirmed=confirmed,
            now=now,
        )

    def record_actual_portion(self, observation: PortionObservation) -> None:
        """Accept only actual meal evidence; correction alone is not a meal."""

        self._candidate_visible_to_owner(observation.candidate_id, observation.owner_user_id)
        if observation.source_event not in {
            FeedbackEventType.ACTUALLY_CONSUMED,
            FeedbackEventType.REPEATED_CONSUMPTION,
        }:
            raise AdaptiveRecipeError("PORTION_PRIOR_REQUIRES_ACTUAL_CONSUMPTION")
        if observation.actual_portion_grams <= 0:
            raise AdaptiveRecipeError("INVALID_ACTUAL_PORTION")
        self._portion_observations.append(observation)

    def record_portion_correction(self, observation: PortionObservation) -> None:
        """Record owner-private serving evidence without creating a meal log.

        A user correcting an adapted serving is useful to the bounded portion
        fitter, but it says nothing about whether the meal was consumed. This
        separate writer prevents a UI feedback gesture from becoming nutrition
        history by accident.
        """

        self._candidate_visible_to_owner(observation.candidate_id, observation.owner_user_id)
        if observation.source_event != FeedbackEventType.PORTION_CORRECTED:
            raise AdaptiveRecipeError("PORTION_CORRECTION_EVENT_REQUIRED")
        if observation.actual_portion_grams <= 0:
            raise AdaptiveRecipeError("INVALID_CORRECTED_PORTION")
        self._portion_observations.append(observation)

    def portion_prior(
        self, *, owner_user_id: str, candidate_id: str
    ) -> PortionPrior | None:
        self._candidate_visible_to_owner(candidate_id, owner_user_id)
        return PortionLearning().build_prior(
            owner_user_id=owner_user_id,
            candidate_id=candidate_id,
            observations=self._portion_observations,
        )

    def preference_score(
        self,
        *,
        owner_user_id: str,
        candidate_id: str,
        now: datetime | None = None,
    ) -> float:
        self._candidate_visible_to_owner(candidate_id, owner_user_id)
        return compute_preference_score(
            (
                item
                for item in self._feedback
                if item.owner_user_id == owner_user_id and item.candidate_id == candidate_id
            ),
            now=now,
        )

    def enqueue_evidence_acquisition(
        self, *, reason_code: str, normalized_query: str, aggregate_count: int
    ) -> EvidenceAcquisitionQueueItem:
        if reason_code not in {
            "UNKNOWN_DISH",
            "POOR_LOCAL_COVERAGE",
            "LOW_DIVERSITY",
            "AMBIGUOUS_MAPPING",
            "FREQUENT_PERSONAL_RECIPE",
        }:
            raise AdaptiveRecipeError("INVALID_ACQUISITION_REASON")
        if not normalized_query.strip() or aggregate_count < 1:
            raise AdaptiveRecipeError("INVALID_ACQUISITION_REQUEST")
        item = EvidenceAcquisitionQueueItem(
            queue_id=str(uuid4()),
            reason_code=reason_code,
            normalized_query=_normalise_query(normalized_query),
            aggregate_count=aggregate_count,
        )
        self._queue[item.queue_id] = item
        return item

    def record_unknown_dish_for_owner(
        self, *, owner_user_id: str, dish_name: str
    ) -> PersonalRecipeAcquisitionCandidate | None:
        """Track repeated unknown dishes only inside the owner's personal scope."""

        if not owner_user_id.strip() or not dish_name.strip():
            raise AdaptiveRecipeError("PERSONAL_UNKNOWN_DISH_REQUIRES_OWNER_AND_NAME")
        normalized = _normalise_query(dish_name)
        key = (owner_user_id, normalized)
        self._personal_unknown_dishes[key] = self._personal_unknown_dishes.get(key, 0) + 1
        count = self._personal_unknown_dishes[key]
        if count < 2:
            return None
        return PersonalRecipeAcquisitionCandidate(owner_user_id, normalized, count)

    def enqueue_active_learning(
        self,
        *,
        reason_code: str,
        normalized_query: str,
        aggregate_signals: Mapping[str, int],
    ) -> EvidenceAcquisitionPriorityItem:
        """Queue an aggregate knowledge gap; never accept user-level payloads."""

        allowed_reasons = {
            "FREQUENTLY_REQUESTED_UNKNOWN_DISH",
            "FREQUENTLY_CONSUMED_PERSONAL_DISH",
            "HIGH_SEARCH_FREQUENCY",
            "UNMAPPED_INGREDIENT_CLUSTER",
            "REGIONAL_DISH_GAP",
            "USER_CORRECTION_CLUSTER",
        }
        allowed_signals = {
            "request_count",
            "consumption_count",
            "search_count",
            "unmapped_count",
            "regional_gap_count",
            "correction_count",
        }
        if reason_code not in allowed_reasons or not normalized_query.strip():
            raise AdaptiveRecipeError("INVALID_ACTIVE_LEARNING_REQUEST")
        if set(aggregate_signals) - allowed_signals:
            raise AdaptiveRecipeError("PRIVATE_DATA_GLOBAL_PROMOTION")
        normalized_signals: dict[str, int] = {}
        for key, value in aggregate_signals.items():
            if not isinstance(value, int) or value < 0:
                raise AdaptiveRecipeError("INVALID_ACTIVE_LEARNING_SIGNAL")
            normalized_signals[key] = value
        if not any(normalized_signals.values()):
            raise AdaptiveRecipeError("EMPTY_ACTIVE_LEARNING_SIGNAL")
        weights = {
            "request_count": 0.25,
            "consumption_count": 0.20,
            "search_count": 0.15,
            "unmapped_count": 0.20,
            "regional_gap_count": 0.10,
            "correction_count": 0.10,
        }
        score = min(
            1.0,
            sum(min(normalized_signals.get(key, 0), 10) / 10 * weight for key, weight in weights.items()),
        )
        item = EvidenceAcquisitionPriorityItem(
            queue_id=str(uuid4()),
            reason_code=reason_code,
            normalized_query=_normalise_query(normalized_query),
            aggregate_signals=normalized_signals,
            priority_score=round(score, 4),
        )
        self._priority_queue[item.queue_id] = item
        return item

    def active_learning_queue(self) -> tuple[EvidenceAcquisitionPriorityItem, ...]:
        return tuple(
            sorted(
                self._priority_queue.values(),
                key=lambda item: (-item.priority_score, item.queue_id),
            )
        )

    @staticmethod
    def aggregate_for_global_learning(payload: Mapping[str, Any]) -> dict[str, Any]:
        forbidden = _PRIVATE_KEYS & set(payload)
        if forbidden:
            raise AdaptiveRecipeError(f"PRIVATE_DATA_GLOBAL_PROMOTION:{','.join(sorted(forbidden))}")
        allowed = {"normalized_recipe_structure", "canonical_ingredients", "serving_distribution", "usage_count", "rating_count"}
        return {key: value for key, value in payload.items() if key in allowed}

    def _candidate(self, candidate_id: str) -> RecipeCandidate:
        try:
            return self._candidates.get(candidate_id) or self._trusted_delivery_references[candidate_id]
        except KeyError as exc:
            raise AdaptiveRecipeError("UNKNOWN_RECIPE_CANDIDATE") from exc

    def candidate_versions(self, candidate_id: str) -> tuple[RecipeCandidate, ...]:
        self._candidate(candidate_id)
        return tuple(self._candidate_versions.get(candidate_id, ()))

    def _store(self, candidate: RecipeCandidate) -> None:
        self._candidates[candidate.candidate_id] = candidate
        self._candidate_versions.setdefault(candidate.candidate_id, []).append(candidate)

    def _duplicate_candidate_ids(self, candidate: RecipeCandidate) -> tuple[str, ...]:
        title_key = _normalise_recipe_identity(candidate.title)
        duplicate_ids: list[str] = []
        for existing in self._candidates.values():
            if existing.candidate_id == candidate.candidate_id:
                continue
            # Personal data must not expose whether another user has a recipe
            # with the same title.  Global/staging records are compared only
            # against other non-personal records.
            same_scope = (
                existing.owner_user_id == candidate.owner_user_id
                if candidate.owner_user_id is not None
                else existing.owner_user_id is None
            )
            if not same_scope:
                continue
            same_recipe_structure = (
                _ingredient_signature(existing) == _ingredient_signature(candidate)
            )
            if existing.evidence.evidence_hash == candidate.evidence.evidence_hash or (
                _normalise_recipe_identity(existing.title) == title_key and same_recipe_structure
            ):
                duplicate_ids.append(existing.candidate_id)
        return tuple(sorted(duplicate_ids))

    def _source_candidate_count(self, candidate: RecipeCandidate) -> int:
        return sum(
            1
            for existing in self._candidates.values()
            if existing.source.source_id == candidate.source.source_id
            and existing.owner_user_id == candidate.owner_user_id
        )

    def _candidate_for_owner(self, candidate_id: str, owner_user_id: str) -> RecipeCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.owner_user_id != owner_user_id:
            raise AdaptiveRecipeError("PERSONAL_DATA_SCOPE_VIOLATION")
        return candidate

    def _candidate_visible_to_owner(self, candidate_id: str, owner_user_id: str) -> RecipeCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.owner_user_id is not None and candidate.owner_user_id != owner_user_id:
            raise AdaptiveRecipeError("PERSONAL_DATA_SCOPE_VIOLATION")
        return candidate

    def _set_recommendation_outcome(self, event: FeedbackEvent) -> None:
        """Keep exposure/outcome memory separate from meal history."""

        for index, record in enumerate(self._recommendation_memory):
            if record.recommendation_id != event.recommendation_id:
                continue
            if record.owner_user_id != event.owner_user_id or record.candidate_id != event.candidate_id:
                raise AdaptiveRecipeError("RECOMMENDATION_FEEDBACK_SCOPE_VIOLATION")
            self._recommendation_memory[index] = replace(
                record,
                outcome_status=event.event_type.value,
            )
            return
        raise AdaptiveRecipeError("UNKNOWN_RECOMMENDATION_MEMORY")

    def _set_shadow_outcome(self, event: FeedbackEvent) -> None:
        """Attach an observed outcome to a matching baseline comparison only."""

        for index, record in enumerate(self._shadow_bandit_logs):
            if (
                record.outcome_event is None
                and record.production_selected_candidate_id == event.candidate_id
            ):
                self._shadow_bandit_logs[index] = replace(
                    record, outcome_event=event.event_type
                )


def compute_preference_score(
    events: Iterable[FeedbackEvent], *, now: datetime | None = None
) -> float:
    """Return a bounded, time-decayed soft-ranking signal.

    Exposure and opens have zero influence. This score is deliberately not a
    nutrition, safety, allergy, or hard-constraint decision.
    """

    observed_at = now or datetime.now(timezone.utc)
    total = 0.0
    for event in events:
        occurred = event.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        age_days = max((observed_at - occurred).total_seconds() / 86_400.0, 0.0)
        decay = math.pow(0.5, age_days / PREFERENCE_HALF_LIFE_DAYS)
        weight = _EVENT_WEIGHTS[event.event_type]
        if event.event_type == FeedbackEventType.REJECTED:
            # Contextual rejection reasons influence only the matching soft
            # component.  The aggregate candidate score is deliberately mild
            # except for an explicit "do not like" statement.
            if event.reason_code == FeedbackRejectionReason.DO_NOT_LIKE:
                weight = -0.65
            elif event.reason_code in {
                FeedbackRejectionReason.NOT_TODAY,
                FeedbackRejectionReason.INGREDIENT_UNAVAILABLE,
            }:
                weight = -0.05
            elif event.reason_code in {
                FeedbackRejectionReason.TOO_EXPENSIVE,
                FeedbackRejectionReason.TOO_HARD_TO_COOK,
            }:
                weight = -0.10
        total += weight * decay
    return round(max(-1.0, min(1.0, total)), 6)


def _normalise_query(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return " ".join(
        "".join(char for char in normalized if unicodedata.category(char) != "Mn").split()
    )


def _normalise_recipe_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    ascii_text = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _ingredient_signature(candidate: RecipeCandidate) -> tuple[tuple[str, str, str], ...]:
    """Stable identity for duplicate protection while permitting true variants."""

    rows: list[tuple[str, str, str]] = []
    for mapping in candidate.mappings:
        ingredient = mapping.raw_ingredient
        identity = mapping.canonical_food_id or _normalise_recipe_identity(ingredient.raw_text)
        quantity = (
            f"{mapping.grams:.4f}"
            if mapping.grams is not None
            else f"{ingredient.amount:.4f}"
            if ingredient.amount is not None
            else "UNRESOLVED"
        )
        rows.append(
            (
                identity,
                quantity,
                str(mapping.canonical_state or ingredient.declared_state or "UNKNOWN").upper(),
            )
        )
    return tuple(sorted(rows))


__all__ = [
    "AdaptiveRecipeRepository",
    "CanonicalRecipeWriter",
    "EvidenceAcquisitionQueueItem",
    "EvidenceAcquisitionPriorityItem",
    "PREFERENCE_HALF_LIFE_DAYS",
    "PersonalDishAlias",
    "PersonalRecipeAcquisitionCandidate",
    "PromotionEvidenceScorecard",
    "PromotionPolicy",
    "PortionObservation",
    "RecommendationMemoryEntry",
    "RecipePromotionDecision",
    "build_promotion_evidence_scorecard",
    "compute_preference_score",
]
