"""Versioned source and validator registries for D3.0 shadow planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .contracts import SOURCE_REGISTRY_VERSION, VALIDATOR_REGISTRY_VERSION, SourceId, ValidatorId


class Availability(str, Enum):
    USER_CONTEXT = "USER_CONTEXT"
    BACKEND_READ = "BACKEND_READ"
    STATIC_DATABASE = "STATIC_DATABASE"
    RETRIEVAL = "RETRIEVAL"
    DERIVED = "DERIVED"


class SourceCost(str, Enum):
    ZERO = "ZERO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PrivacyClass(str, Enum):
    PUBLIC = "PUBLIC"
    USER_PRIVATE = "USER_PRIVATE"
    HEALTH_SENSITIVE = "HEALTH_SENSITIVE"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_id: SourceId
    authoritative_backend: str
    availability: Availability
    freshness_capability: tuple[str, ...]
    cost: SourceCost
    privacy_class: PrivacyClass
    failure_semantics: str
    estimated_characters: int
    priority: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id.value,
            "authoritative_backend": self.authoritative_backend,
            "availability": self.availability.value,
            "freshness_capability": list(self.freshness_capability),
            "cost": self.cost.value,
            "privacy_class": self.privacy_class.value,
            "failure_semantics": self.failure_semantics,
            "estimated_characters": self.estimated_characters,
            "estimated_tokens": (self.estimated_characters + 3) // 4,
            "priority": self.priority,
        }


def _source(
    source_id: SourceId,
    backend: str,
    availability: Availability,
    freshness: tuple[str, ...],
    cost: SourceCost,
    privacy: PrivacyClass,
    failure: str,
    chars: int,
    priority: int,
) -> SourceDefinition:
    return SourceDefinition(
        source_id, backend, availability, freshness, cost, privacy, failure, chars, priority
    )


SOURCE_REGISTRY: Mapping[SourceId, SourceDefinition] = MappingProxyType({
    SourceId.PROFILE: _source(SourceId.PROFILE, "Firestore users/get_user_profile", Availability.BACKEND_READ, ("LIVE", "ANY"), SourceCost.LOW, PrivacyClass.USER_PRIVATE, "Preserve MISSING/ERROR/STALE; never invent profile values", 700, 90),
    SourceId.NUTRITION_SAFETY: _source(SourceId.NUTRITION_SAFETY, "Firestore explicit self-report", Availability.USER_CONTEXT, ("LIVE", "ANY"), SourceCost.ZERO, PrivacyClass.HEALTH_SENSITIVE, "UNKNOWN and NOT_PROVIDED remain distinct from NO", 320, 100),
    SourceId.DAILY_NUTRITION: _source(SourceId.DAILY_NUTRITION, "authoritative consumed meal diary", Availability.BACKEND_READ, ("LIVE", "TODAY"), SourceCost.LOW, PrivacyClass.HEALTH_SENSITIVE, "Known zero is valid; read errors and stale snapshots are unavailable", 850, 100),
    SourceId.TODAY_EXERCISE: _source(SourceId.TODAY_EXERCISE, "authoritative exercise diary", Availability.BACKEND_READ, ("LIVE", "TODAY"), SourceCost.LOW, PrivacyClass.HEALTH_SENSITIVE, "Known zero is valid; do not promote stale snapshots", 650, 85),
    SourceId.MEAL_HISTORY: _source(SourceId.MEAL_HISTORY, "meal diary date-range read", Availability.BACKEND_READ, ("RECENT", "ANY"), SourceCost.MEDIUM, PrivacyClass.HEALTH_SENSITIVE, "Unavailable range requires explicit read/missing action", 1800, 45),
    SourceId.EXERCISE_HISTORY: _source(SourceId.EXERCISE_HISTORY, "exercise diary date-range read", Availability.BACKEND_READ, ("RECENT", "ANY"), SourceCost.MEDIUM, PrivacyClass.HEALTH_SENSITIVE, "Unavailable range requires explicit read/missing action", 1500, 45),
    SourceId.WEIGHT_HISTORY: _source(SourceId.WEIGHT_HISTORY, "weight measurement history", Availability.BACKEND_READ, ("LIVE", "RECENT"), SourceCost.LOW, PrivacyClass.HEALTH_SENSITIVE, "Missing series is not a flat trend; conflicts remain explicit", 900, 95),
    SourceId.LIFESTYLE: _source(SourceId.LIFESTYLE, "lifestyle logs", Availability.BACKEND_READ, ("LIVE", "TODAY", "RECENT"), SourceCost.LOW, PrivacyClass.HEALTH_SENSITIVE, "Missing/not-loaded/error retain D1 status semantics", 700, 70),
    SourceId.ACTIVE_PLAN: _source(SourceId.ACTIVE_PLAN, "plans API/get_active_plan", Availability.BACKEND_READ, ("LIVE",), SourceCost.LOW, PrivacyClass.USER_PRIVATE, "NO_PLAN and READ_ERROR are distinct", 1400, 90),
    SourceId.SAVED_MEALS: _source(SourceId.SAVED_MEALS, "saved meal collection", Availability.BACKEND_READ, ("RECENT", "ANY"), SourceCost.MEDIUM, PrivacyClass.USER_PRIVATE, "Unavailable collection does not imply no preferences", 1200, 35),
    SourceId.CONFIRMED_MEMORY: _source(SourceId.CONFIRMED_MEMORY, "confirmed user_facts", Availability.BACKEND_READ, ("ANY",), SourceCost.LOW, PrivacyClass.HEALTH_SENSITIVE, "Only confirmed facts may be treated as durable constraints", 650, 95),
    SourceId.RECENT_CONVERSATION: _source(SourceId.RECENT_CONVERSATION, "chat session turns", Availability.BACKEND_READ, ("RECENT",), SourceCost.MEDIUM, PrivacyClass.USER_PRIVATE, "Absence requires clarification for provenance-dependent follow-ups", 2200, 40),
    SourceId.FOOD_DATABASE: _source(SourceId.FOOD_DATABASE, "approved food database/search_food_nutrition", Availability.STATIC_DATABASE, ("ANY",), SourceCost.LOW, PrivacyClass.PUBLIC, "No match must be reported; never fabricate nutrients", 900, 80),
    SourceId.DISH_DATABASE: _source(SourceId.DISH_DATABASE, "approved dish catalog/suggest_dish", Availability.STATIC_DATABASE, ("ANY",), SourceCost.LOW, PrivacyClass.PUBLIC, "No match must be reported; never fabricate a dish", 1100, 75),
    SourceId.RAG: _source(SourceId.RAG, "approved nutrition knowledge corpus", Availability.RETRIEVAL, ("ANY",), SourceCost.HIGH, PrivacyClass.PUBLIC, "Retrieval failure means evidence unavailable, not permission to improvise", 2000, 70),
    SourceId.MEDICAL_EVIDENCE: _source(SourceId.MEDICAL_EVIDENCE, "evidence-oriented medical search", Availability.RETRIEVAL, ("RECENT",), SourceCost.HIGH, PrivacyClass.PUBLIC, "Must remain grounded and non-prescriptive when safety disallows", 2400, 100),
    SourceId.CANONICAL_NUTRITION: _source(SourceId.CANONICAL_NUTRITION, "nutrition-policy-v1.0.1 calculator", Availability.DERIVED, ("LIVE", "TODAY", "ANY"), SourceCost.ZERO, PrivacyClass.HEALTH_SENSITIVE, "Never convert unsupported/unavailable state into an ordinary target", 1100, 100),
})


VALIDATOR_REGISTRY: Mapping[ValidatorId, str] = MappingProxyType({
    ValidatorId.NUMERIC_CONSISTENCY: "Derived and reported numeric values agree with canonical state.",
    ValidatorId.DIETARY_CONSTRAINT: "Recommendations retain known dietary restrictions.",
    ValidatorId.ALLERGY_CONSTRAINT: "Recommendations never remove or violate a known allergy.",
    ValidatorId.PERSISTENCE_CONFIRMATION: "A write is reported successful only after persistence confirmation.",
    ValidatorId.EVIDENCE_GROUNDING: "Evidence claims are supported by the planned evidence route.",
    ValidatorId.CURRENT_STATE_FRESHNESS: "Required current state is not stale, errored, conflicted, or silently substituted.",
    ValidatorId.PLAN_CONSISTENCY: "Plan actions remain consistent with active-plan and canonical policy state.",
})


def source_registry_payload() -> dict[str, object]:
    return {
        "registry_version": SOURCE_REGISTRY_VERSION,
        "sources": [SOURCE_REGISTRY[item].to_dict() for item in SourceId],
    }


def validator_registry_payload() -> dict[str, object]:
    return {
        "registry_version": VALIDATOR_REGISTRY_VERSION,
        "validators": {key.value: value for key, value in VALIDATOR_REGISTRY.items()},
    }


__all__ = [
    "Availability",
    "PrivacyClass",
    "SOURCE_REGISTRY",
    "SourceCost",
    "SourceDefinition",
    "VALIDATOR_REGISTRY",
    "source_registry_payload",
    "validator_registry_payload",
]
