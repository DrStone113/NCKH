"""Typed, auditable N3 contracts.

No type in this module represents a direct canonical-catalog write. Candidate
nutrition is always supplied by deterministic canonical composition arithmetic
and any source-reported values are reference-only evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


class TrustDomain(str, Enum):
    PERSONAL_MEMORY = "PERSONAL_MEMORY"
    PERSONAL_RECIPE = "PERSONAL_RECIPE"
    RUNTIME_EXTERNAL_CANDIDATE = "RUNTIME_EXTERNAL_CANDIDATE"
    STAGING_RECIPE = "STAGING_RECIPE"
    CANONICAL_PRODUCTION_RECIPE = "CANONICAL_PRODUCTION_RECIPE"
    FROZEN_RESEARCH_RECIPE = "FROZEN_RESEARCH_RECIPE"


class CandidateStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    EXTRACTED = "EXTRACTED"
    MAPPED = "MAPPED"
    CALCULATED = "CALCULATED"
    VALIDATED = "VALIDATED"
    STAGING = "STAGING"
    SHADOW_ELIGIBLE = "SHADOW_ELIGIBLE"
    PROMOTABLE = "PROMOTABLE"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"


class MappingStatus(str, Enum):
    EXACT = "EXACT"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"


class IngredientScaleClass(str, Enum):
    ANCHOR = "ANCHOR"
    SCALABLE = "SCALABLE"
    LIMITED_SCALABLE = "LIMITED_SCALABLE"
    FLAVOR_BOUNDED = "FLAVOR_BOUNDED"
    OPTIONAL = "OPTIONAL"
    FIXED = "FIXED"


class FeedbackEventType(str, Enum):
    SHOWN = "SHOWN"
    OPENED = "OPENED"
    SAVED = "SAVED"
    REJECTED = "REJECTED"
    SUBSTITUTED = "SUBSTITUTED"
    LIKED = "LIKED"
    DISLIKED = "DISLIKED"
    ACTUALLY_CONSUMED = "ACTUALLY_CONSUMED"
    # Kept for backwards-compatible reads of N3 records.  New writers must
    # use the more precise REPEATED_CONSUMPTION name below.
    REPEATED = "REPEATED"
    REPEATED_CONSUMPTION = "REPEATED_CONSUMPTION"
    PORTION_CORRECTED = "PORTION_CORRECTED"
    INGREDIENT_CORRECTED = "INGREDIENT_CORRECTED"
    RECIPE_CORRECTED = "RECIPE_CORRECTED"


class FeedbackRejectionReason(str, Enum):
    """Why a negative interaction happened.

    A rejection is not synonymous with a stable dislike.  These values are
    deliberately compact so they can be used in private learning and in
    de-identified aggregate gap counts without sending conversation text.
    """

    DO_NOT_LIKE = "DO_NOT_LIKE"
    NOT_TODAY = "NOT_TODAY"
    TOO_EXPENSIVE = "TOO_EXPENSIVE"
    TOO_HARD_TO_COOK = "TOO_HARD_TO_COOK"
    INGREDIENT_UNAVAILABLE = "INGREDIENT_UNAVAILABLE"
    TOO_REPETITIVE = "TOO_REPETITIVE"
    PORTION_TOO_LARGE = "PORTION_TOO_LARGE"
    PORTION_TOO_SMALL = "PORTION_TOO_SMALL"
    OTHER = "OTHER"


class PromotionClass(str, Enum):
    AUTO_PROMOTION_ELIGIBLE = "AUTO_PROMOTION_ELIGIBLE"
    REQUIRES_MORE_EVIDENCE = "REQUIRES_MORE_EVIDENCE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class NutrientTotals:
    energy_kcal: float = 0.0
    protein_g: float = 0.0
    carbohydrate_g: float = 0.0
    fat_g: float = 0.0

    def rounded(self) -> "NutrientTotals":
        return NutrientTotals(
            energy_kcal=round(self.energy_kcal, 2),
            protein_g=round(self.protein_g, 2),
            carbohydrate_g=round(self.carbohydrate_g, 2),
            fat_g=round(self.fat_g, 2),
        )

    def plus(self, other: "NutrientTotals") -> "NutrientTotals":
        return NutrientTotals(
            energy_kcal=self.energy_kcal + other.energy_kcal,
            protein_g=self.protein_g + other.protein_g,
            carbohydrate_g=self.carbohydrate_g + other.carbohydrate_g,
            fat_g=self.fat_g + other.fat_g,
        )


@dataclass(frozen=True)
class RawIngredient:
    """An ingredient exactly as acquired, plus a deliberately conservative parse.

    ``amount`` is nullable because expressions such as ``salt to taste`` and
    ``a little oil`` are evidence, not a licence to invent grams.  A nullable
    amount must consequently fail canonical nutrition verification unless a
    user supplies a supported quantity later.
    """

    raw_text: str
    amount: float | None
    unit: str
    declared_state: str | None = None
    ingredient_name: str | None = None
    preparation_state: str | None = None
    optional: bool = False
    quantity_uncertain: bool = False


@dataclass(frozen=True)
class CanonicalIngredientMapping:
    raw_ingredient: RawIngredient
    canonical_food_id: str | None
    canonical_food_name: str | None
    grams: float | None
    status: MappingStatus
    confidence: str
    canonical_state: str | None = None
    reason_code: str | None = None
    allergen_ids: tuple[str, ...] = ()
    candidate_food_ids: tuple[str, ...] = ()
    candidate_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateSource:
    source_type: str
    source_id: str
    source_url: str | None = None
    fetched_at: str | None = None
    license_status: str | None = None
    source_recipe_id: str | None = None
    source_last_modified: str | None = None
    content_fingerprint: str | None = None
    cache_status: str | None = None
    fetch_strategy: str | None = None


@dataclass(frozen=True)
class RecipeEvidenceBundle:
    source: CandidateSource
    raw_source_text: str
    raw_ingredients: tuple[RawIngredient, ...]
    mappings: tuple[CanonicalIngredientMapping, ...]
    calculated_nutrition: NutrientTotals | None
    source_reported_nutrition: NutrientTotals | None
    derived_allergen_ids: tuple[str, ...]
    duplicate_candidates: tuple[str, ...]
    validation_codes: tuple[str, ...]
    automated_review: tuple[Mapping[str, Any], ...] = ()
    calculation_version: str = "canonical-ingredient-sum-v1"
    extraction_method: str | None = None
    structured_data_present: bool | None = None
    mapping_count_coverage: float | None = None
    mapping_mass_coverage: float | None = None
    evidence_hash: str = ""

    def with_hash(self) -> "RecipeEvidenceBundle":
        payload = asdict(self)
        payload["evidence_hash"] = ""
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
        return replace(self, evidence_hash=digest)


@dataclass(frozen=True)
class RecipeCandidate:
    candidate_id: str
    trust_domain: TrustDomain
    title: str
    aliases: tuple[str, ...]
    source: CandidateSource
    raw_ingredients: tuple[RawIngredient, ...]
    mappings: tuple[CanonicalIngredientMapping, ...]
    canonical_nutrition: NutrientTotals | None
    source_reported_nutrition: NutrientTotals | None
    allergen_ids: tuple[str, ...]
    dietary_tags: tuple[str, ...]
    evidence: RecipeEvidenceBundle
    status: CandidateStatus
    # This is an immutable audit trail of the candidate lifecycle.  A storage
    # adapter persists each state as a new version; it is never a catalog-write
    # instruction.
    lifecycle_history: tuple[str, ...] = ()
    validation_codes: tuple[str, ...] = ()
    owner_user_id: str | None = None
    recipe_origin: str = "SOURCE_RECIPE"
    quality_score: float | None = None
    runtime_recipe_identity: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def draft(
        cls,
        *,
        trust_domain: TrustDomain,
        title: str,
        source: CandidateSource,
        raw_ingredients: tuple[RawIngredient, ...],
        aliases: tuple[str, ...] = (),
        raw_source_text: str = "",
        source_reported_nutrition: NutrientTotals | None = None,
        owner_user_id: str | None = None,
        recipe_origin: str = "SOURCE_RECIPE",
    ) -> "RecipeCandidate":
        evidence = RecipeEvidenceBundle(
            source=source,
            raw_source_text=raw_source_text,
            raw_ingredients=raw_ingredients,
            mappings=(),
            calculated_nutrition=None,
            source_reported_nutrition=source_reported_nutrition,
            derived_allergen_ids=(),
            duplicate_candidates=(),
            validation_codes=(),
        ).with_hash()
        return cls(
            candidate_id=str(uuid4()),
            trust_domain=trust_domain,
            title=title.strip(),
            aliases=aliases,
            source=source,
            raw_ingredients=raw_ingredients,
            mappings=(),
            canonical_nutrition=None,
            source_reported_nutrition=source_reported_nutrition,
            allergen_ids=(),
            dietary_tags=(),
            evidence=evidence,
            status=CandidateStatus.EXTRACTED,
            lifecycle_history=(
                CandidateStatus.DISCOVERED.value,
                CandidateStatus.EXTRACTED.value,
            ),
            owner_user_id=owner_user_id,
            recipe_origin=recipe_origin,
        )


@dataclass(frozen=True)
class ConstraintContext:
    allergen_exclusions: frozenset[str] = frozenset()
    dietary_exclusions: frozenset[str] = frozenset()
    target_kcal: float | None = None
    target_protein_g: float | None = None


@dataclass(frozen=True)
class PortionFitResult:
    status: str
    ingredient_grams: Mapping[str, float]
    nutrition: NutrientTotals | None
    reason_codes: tuple[str, ...]
    objective_score: float | None = None


@dataclass(frozen=True)
class FeedbackEvent:
    owner_user_id: str
    candidate_id: str
    event_type: FeedbackEventType
    occurred_at: datetime
    explicit: bool = False
    reason_code: FeedbackRejectionReason | None = None
    # This payload remains owner-scoped.  Only structured correction fields
    # are accepted by the repository; it is never a path for conversation or
    # private health text into shared catalog evidence.
    metadata: Mapping[str, Any] = field(default_factory=dict)
    recommendation_id: str | None = None
    policy_version: str | None = None
    idempotency_key: str | None = None
    # Generated server-side and persisted as the immutable feedback-event
    # identity.  It is deliberately distinct from recommendation and meal-log
    # identities: submitting feedback is never an assertion of consumption.
    feedback_event_id: str | None = None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"UNSUPPORTED_EVIDENCE_VALUE:{type(value).__name__}")


__all__ = [
    "CandidateSource",
    "CandidateStatus",
    "CanonicalIngredientMapping",
    "ConstraintContext",
    "FeedbackEvent",
    "FeedbackEventType",
    "FeedbackRejectionReason",
    "IngredientScaleClass",
    "MappingStatus",
    "NutrientTotals",
    "PortionFitResult",
    "PromotionClass",
    "RawIngredient",
    "RecipeCandidate",
    "RecipeEvidenceBundle",
    "TrustDomain",
]
