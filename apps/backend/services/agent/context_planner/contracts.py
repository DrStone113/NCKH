"""Immutable, serializable contracts for ``context-plan-v1``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


PLAN_VERSION = "context-plan-v1"
INTENT_VERSION = "context-intent-v1"
SOURCE_REGISTRY_VERSION = "context-source-registry-v1"
MATRIX_VERSION = "context-source-matrix-v1"
VALIDATOR_REGISTRY_VERSION = "context-validator-v1"
BUNDLE_VERSION = "context-bundle-v1"


class Intent(str, Enum):
    DAILY_NUTRITION_STATUS = "DAILY_NUTRITION_STATUS"
    MEAL_RECOMMENDATION = "MEAL_RECOMMENDATION"
    FOOD_NUTRITION_LOOKUP = "FOOD_NUTRITION_LOOKUP"
    MEAL_OR_DIET_EVALUATION = "MEAL_OR_DIET_EVALUATION"
    WEIGHT_PROGRESS = "WEIGHT_PROGRESS"
    EXERCISE_RECOVERY = "EXERCISE_RECOVERY"
    WORKOUT_RECOMMENDATION = "WORKOUT_RECOMMENDATION"
    PLAN_MANAGEMENT = "PLAN_MANAGEMENT"
    PROFILE_OR_CONSTRAINT_UPDATE = "PROFILE_OR_CONSTRAINT_UPDATE"
    GENERAL_NUTRITION_KNOWLEDGE = "GENERAL_NUTRITION_KNOWLEDGE"
    EVIDENCE_HEALTH_QUESTION = "EVIDENCE_HEALTH_QUESTION"
    FOLLOWUP_EXPLANATION = "FOLLOWUP_EXPLANATION"
    APP_ACTION = "APP_ACTION"
    SMALLTALK_OR_OTHER = "SMALLTALK_OR_OTHER"


class SourceId(str, Enum):
    PROFILE = "PROFILE"
    NUTRITION_SAFETY = "NUTRITION_SAFETY"
    DAILY_NUTRITION = "DAILY_NUTRITION"
    TODAY_EXERCISE = "TODAY_EXERCISE"
    MEAL_HISTORY = "MEAL_HISTORY"
    EXERCISE_HISTORY = "EXERCISE_HISTORY"
    WEIGHT_HISTORY = "WEIGHT_HISTORY"
    LIFESTYLE = "LIFESTYLE"
    ACTIVE_PLAN = "ACTIVE_PLAN"
    SAVED_MEALS = "SAVED_MEALS"
    CONFIRMED_MEMORY = "CONFIRMED_MEMORY"
    RECENT_CONVERSATION = "RECENT_CONVERSATION"
    FOOD_DATABASE = "FOOD_DATABASE"
    DISH_DATABASE = "DISH_DATABASE"
    RAG = "RAG"
    MEDICAL_EVIDENCE = "MEDICAL_EVIDENCE"
    CANONICAL_NUTRITION = "CANONICAL_NUTRITION"


class Freshness(str, Enum):
    LIVE = "LIVE"
    TODAY = "TODAY"
    RECENT = "RECENT"
    ANY = "ANY"


class RagPolicy(str, Enum):
    REQUIRED = "RAG_REQUIRED"
    OPTIONAL = "RAG_OPTIONAL"
    FORBIDDEN = "RAG_FORBIDDEN"


class MemoryPolicy(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    FORBIDDEN = "FORBIDDEN"


class EvidenceRequirement(str, Enum):
    NONE = "NONE"
    GROUNDED = "GROUNDED_EVIDENCE"
    SAFETY_GROUNDED = "SAFETY_GROUNDED_EVIDENCE"


class ValidatorId(str, Enum):
    NUMERIC_CONSISTENCY = "NUMERIC_CONSISTENCY"
    DIETARY_CONSTRAINT = "DIETARY_CONSTRAINT"
    ALLERGY_CONSTRAINT = "ALLERGY_CONSTRAINT"
    PERSISTENCE_CONFIRMATION = "PERSISTENCE_CONFIRMATION"
    EVIDENCE_GROUNDING = "EVIDENCE_GROUNDING"
    CURRENT_STATE_FRESHNESS = "CURRENT_STATE_FRESHNESS"
    PLAN_CONSISTENCY = "PLAN_CONSISTENCY"


class DataStatus(str, Enum):
    KNOWN = "KNOWN"
    MISSING = "MISSING"
    NOT_LOADED = "NOT_LOADED"
    ERROR = "ERROR"
    CONFLICT = "CONFLICT"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class FreshnessRequirement:
    source_id: SourceId
    freshness: Freshness

    def to_dict(self) -> dict[str, str]:
        return {"source_id": self.source_id.value, "freshness": self.freshness.value}


@dataclass(frozen=True, slots=True)
class ContextPlan:
    plan_version: str
    primary_intent: Intent
    secondary_intents: tuple[Intent, ...]
    required_sources: tuple[SourceId, ...]
    optional_sources: tuple[SourceId, ...]
    forbidden_sources: tuple[SourceId, ...]
    freshness_requirements: tuple[FreshnessRequirement, ...]
    required_calculations: tuple[str, ...]
    permitted_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    rag_policy: RagPolicy
    memory_policy: MemoryPolicy
    evidence_requirement: EvidenceRequirement
    required_validators: tuple[ValidatorId, ...]
    clarification_required: bool
    planner_reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "primary_intent": self.primary_intent.value,
            "secondary_intents": [item.value for item in self.secondary_intents],
            "required_sources": [item.value for item in self.required_sources],
            "optional_sources": [item.value for item in self.optional_sources],
            "forbidden_sources": [item.value for item in self.forbidden_sources],
            "freshness_requirements": [item.to_dict() for item in self.freshness_requirements],
            "required_calculations": list(self.required_calculations),
            "permitted_tools": list(self.permitted_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "rag_policy": self.rag_policy.value,
            "memory_policy": self.memory_policy.value,
            "evidence_requirement": self.evidence_requirement.value,
            "required_validators": [item.value for item in self.required_validators],
            "clarification_required": self.clarification_required,
            "planner_reason_codes": list(self.planner_reason_codes),
        }


@dataclass(frozen=True, slots=True)
class MissingDataAction:
    source_id: SourceId
    observed_status: DataStatus
    required_freshness: Freshness
    action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id.value,
            "observed_status": self.observed_status.value,
            "required_freshness": self.required_freshness.value,
            "action": self.action,
        }


@dataclass(frozen=True, slots=True)
class ContextSection:
    section_id: str
    sources: tuple[SourceId, ...]
    source_status: tuple[tuple[SourceId, DataStatus], ...]
    included_fields: tuple[str, ...]
    estimated_characters: int
    estimated_tokens: int
    priority: int
    required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "sources": [item.value for item in self.sources],
            "source_status": {
                source.value: status.value for source, status in self.source_status
            },
            "included_fields": list(self.included_fields),
            "estimated_characters": self.estimated_characters,
            "estimated_tokens": self.estimated_tokens,
            "priority": self.priority,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class ContextBundle:
    bundle_version: str
    sections: tuple[ContextSection, ...]
    missing_required_sources: tuple[SourceId, ...]
    missing_data_actions: tuple[MissingDataAction, ...]
    trimmed_optional_sources: tuple[SourceId, ...]
    planned_context_size_characters: int
    planned_context_size_tokens: int
    current_production_context_size_characters: int
    current_production_context_size_tokens: int
    budget_characters: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_version": self.bundle_version,
            "sections": [item.to_dict() for item in self.sections],
            "missing_required_sources": [item.value for item in self.missing_required_sources],
            "missing_data_actions": [item.to_dict() for item in self.missing_data_actions],
            "trimmed_optional_sources": [item.value for item in self.trimmed_optional_sources],
            "planned_context_size_characters": self.planned_context_size_characters,
            "planned_context_size_tokens": self.planned_context_size_tokens,
            "current_production_context_size_characters": self.current_production_context_size_characters,
            "current_production_context_size_tokens": self.current_production_context_size_tokens,
            "budget_characters": self.budget_characters,
        }


def immutable_mapping(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))
