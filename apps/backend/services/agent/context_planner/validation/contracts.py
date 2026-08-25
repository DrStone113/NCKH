"""Immutable contracts for independently identified validation datasets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..contracts import Intent, RagPolicy, SourceId, ValidatorId


VALIDATION_SCHEMA_VERSION = "context-planner-validation-v1"


class DatasetType(str, Enum):
    REGRESSION = "REGRESSION"
    NATURAL_SHADOW = "NATURAL_SHADOW"
    ADVERSARIAL_HOLDOUT = "ADVERSARIAL_HOLDOUT"


class DatasetLifecycle(str, Enum):
    COLLECTING = "COLLECTING"
    CANDIDATE = "CANDIDATE"
    FROZEN = "FROZEN"
    USED_FOR_TUNING = "USED_FOR_TUNING"


class OracleReviewStatus(str, Enum):
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    LEGACY_ENGINEERING_ORACLE = "LEGACY_ENGINEERING_ORACLE"


class FailureCategory(str, Enum):
    INTENT_MISCLASSIFICATION = "INTENT_MISCLASSIFICATION"
    MISSING_REQUIRED_SOURCE = "MISSING_REQUIRED_SOURCE"
    UNNECESSARY_SOURCE = "UNNECESSARY_SOURCE"
    FORBIDDEN_SOURCE_SELECTED = "FORBIDDEN_SOURCE_SELECTED"
    MISSING_TOOL = "MISSING_TOOL"
    UNNECESSARY_TOOL = "UNNECESSARY_TOOL"
    WRITE_PERMISSION_ERROR = "WRITE_PERMISSION_ERROR"
    RAG_UNDER_RETRIEVAL = "RAG_UNDER_RETRIEVAL"
    RAG_OVER_RETRIEVAL = "RAG_OVER_RETRIEVAL"
    MEMORY_ROUTING_ERROR = "MEMORY_ROUTING_ERROR"
    FRESHNESS_ERROR = "FRESHNESS_ERROR"
    FOLLOWUP_CONTEXT_ERROR = "FOLLOWUP_CONTEXT_ERROR"
    SAFETY_POLICY_ERROR = "SAFETY_POLICY_ERROR"
    CLARIFICATION_ERROR = "CLARIFICATION_ERROR"


@dataclass(frozen=True, slots=True)
class DatasetIdentity:
    dataset_type: DatasetType
    dataset_version: str
    created_at: str
    case_count: int
    content_sha256: str | None
    oracle_version: str
    oracle_sha256: str | None
    oracle_review_status: OracleReviewStatus
    used_for_tuning: bool
    lifecycle: DatasetLifecycle
    planner_version: str
    planner_commit: str
    planner_content_sha256: str

    def __post_init__(self) -> None:
        if self.used_for_tuning and self.lifecycle != DatasetLifecycle.USED_FOR_TUNING:
            raise ValueError("used_for_tuning datasets must use USED_FOR_TUNING lifecycle")
        if self.dataset_type == DatasetType.ADVERSARIAL_HOLDOUT and self.used_for_tuning:
            raise ValueError("a tuning dataset may no longer be called ADVERSARIAL_HOLDOUT")
        if self.lifecycle == DatasetLifecycle.FROZEN:
            if not self.content_sha256 or not self.oracle_sha256:
                raise ValueError("frozen datasets require content and oracle hashes")
            allowed_regression = (
                self.dataset_type == DatasetType.REGRESSION
                and self.oracle_review_status == OracleReviewStatus.LEGACY_ENGINEERING_ORACLE
            )
            if self.oracle_review_status != OracleReviewStatus.HUMAN_REVIEWED and not allowed_regression:
                raise ValueError("frozen validation requires human-reviewed oracle labels")

    @property
    def eligible_for_independent_evaluation(self) -> bool:
        return (
            self.lifecycle == DatasetLifecycle.FROZEN
            and self.oracle_review_status == OracleReviewStatus.HUMAN_REVIEWED
            and not self.used_for_tuning
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_schema_version": VALIDATION_SCHEMA_VERSION,
            "dataset_type": self.dataset_type.value,
            "dataset_version": self.dataset_version,
            "created_at": self.created_at,
            "case_count": self.case_count,
            "content_sha256": self.content_sha256,
            "oracle_version": self.oracle_version,
            "oracle_sha256": self.oracle_sha256,
            "oracle_review_status": self.oracle_review_status.value,
            "used_for_tuning": self.used_for_tuning,
            "lifecycle": self.lifecycle.value,
            "planner_version": self.planner_version,
            "planner_commit": self.planner_commit,
            "planner_content_sha256": self.planner_content_sha256,
            "eligible_for_independent_evaluation": self.eligible_for_independent_evaluation,
        }


@dataclass(frozen=True, slots=True)
class OracleCase:
    case_id: str
    query: str
    conversational_context: tuple[str, ...]
    primary_intent: Intent
    secondary_intents: tuple[Intent, ...]
    required_sources: tuple[SourceId, ...]
    optional_sources: tuple[SourceId, ...]
    forbidden_sources: tuple[SourceId, ...]
    rag_policy: RagPolicy
    permitted_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    validators: tuple[ValidatorId, ...]
    memory_policy: str
    clarification_required: bool
    write_permitted: bool
    source_statuses: tuple[tuple[SourceId, str], ...]
    expected_missing_actions: tuple[tuple[SourceId, str], ...]
    oracle_reviewer: str
    oracle_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "query": self.query,
            "conversational_context": list(self.conversational_context),
            "primary_intent": self.primary_intent.value,
            "secondary_intents": [item.value for item in self.secondary_intents],
            "required_sources": [item.value for item in self.required_sources],
            "optional_sources": [item.value for item in self.optional_sources],
            "forbidden_sources": [item.value for item in self.forbidden_sources],
            "rag_policy": self.rag_policy.value,
            "permitted_tools": list(self.permitted_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "validators": [item.value for item in self.validators],
            "memory_policy": self.memory_policy,
            "clarification_required": self.clarification_required,
            "write_permitted": self.write_permitted,
            "source_statuses": {source.value: status for source, status in self.source_statuses},
            "expected_missing_actions": {source.value: action for source, action in self.expected_missing_actions},
            "oracle_reviewer": self.oracle_reviewer,
            "oracle_version": self.oracle_version,
        }


__all__ = [
    "DatasetIdentity", "DatasetLifecycle", "DatasetType", "FailureCategory",
    "OracleCase", "OracleReviewStatus", "VALIDATION_SCHEMA_VERSION",
]
