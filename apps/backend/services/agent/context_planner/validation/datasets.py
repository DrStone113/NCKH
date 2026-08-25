"""Dataset snapshots without mutating the frozen D3.0 regression corpus."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess
from typing import Any, Iterable

from ..contracts import PLAN_VERSION
from ..development_scenarios import DEVELOPMENT_SCENARIOS, SCENARIO_SET_VERSION
from .adversarial_candidates import (
    ADVERSARIAL_CANDIDATE_VERSION, ADVERSARIAL_ORACLE_VERSION,
    adversarial_candidates, oracle_review_template,
)
from .contracts import (
    DatasetIdentity, DatasetLifecycle, DatasetType, OracleCase, OracleReviewStatus,
)
from .hashing import content_sha256, files_sha256


SNAPSHOT_CREATED_AT = "2026-08-25T19:38:29+07:00"
REGRESSION_ORACLE_VERSION = "context-planner-development-oracle-v1"
NATURAL_DATASET_VERSION = "context-planner-natural-shadow-v1"
NATURAL_ORACLE_VERSION = "context-planner-natural-oracle-v1"


def planner_snapshot() -> dict[str, str]:
    planner_dir = Path(__file__).resolve().parents[1]
    paths = [planner_dir / name for name in ("classifier.py", "contracts.py", "matrix.py", "planner.py", "registry.py")]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=planner_dir, text=True,
            stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except Exception:  # pragma: no cover - source archive without git metadata
        commit = "UNKNOWN"
    return {
        "planner_version": PLAN_VERSION,
        "planner_commit": commit,
        "planner_content_sha256": files_sha256(paths),
    }


def regression_payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = [
        {
            "case_id": item.scenario_id,
            "query": item.query,
            "source_statuses": {source.value: status.value for source, status in item.source_statuses},
        }
        for item in DEVELOPMENT_SCENARIOS
    ]
    oracles = [
        {
            "case_id": item.scenario_id,
            "primary_intent": item.expected_primary_intent.value,
            "secondary_intents": [value.value for value in item.expected_secondary_intents],
            "required_sources": [value.value for value in item.expected_required_sources],
            "forbidden_sources": [value.value for value in item.expected_forbidden_sources],
            "rag_policy": item.expected_rag_policy.value,
            "minimum_tools": list(item.expected_tools),
            "validators": [value.value for value in item.expected_validators],
        }
        for item in DEVELOPMENT_SCENARIOS
    ]
    return cases, oracles


def regression_identity() -> DatasetIdentity:
    cases, oracles = regression_payloads()
    return DatasetIdentity(
        dataset_type=DatasetType.REGRESSION, dataset_version=SCENARIO_SET_VERSION,
        created_at=SNAPSHOT_CREATED_AT, case_count=len(cases),
        content_sha256=content_sha256(cases), oracle_version=REGRESSION_ORACLE_VERSION,
        oracle_sha256=content_sha256(oracles),
        oracle_review_status=OracleReviewStatus.LEGACY_ENGINEERING_ORACLE,
        used_for_tuning=True, lifecycle=DatasetLifecycle.USED_FOR_TUNING,
        **planner_snapshot(),
    )


def adversarial_candidate_identity() -> DatasetIdentity:
    cases = [item.content_dict() for item in adversarial_candidates()]
    template = oracle_review_template()
    return DatasetIdentity(
        dataset_type=DatasetType.ADVERSARIAL_HOLDOUT,
        dataset_version=ADVERSARIAL_CANDIDATE_VERSION,
        created_at=SNAPSHOT_CREATED_AT, case_count=len(cases),
        content_sha256=content_sha256(cases), oracle_version=ADVERSARIAL_ORACLE_VERSION,
        oracle_sha256=content_sha256(template),
        oracle_review_status=OracleReviewStatus.PENDING_HUMAN_REVIEW,
        used_for_tuning=False, lifecycle=DatasetLifecycle.CANDIDATE,
        **planner_snapshot(),
    )


def load_natural_records(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).exists():
        return []
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def natural_collecting_identity(path: str | Path | None = None) -> DatasetIdentity:
    records = load_natural_records(path)
    return DatasetIdentity(
        dataset_type=DatasetType.NATURAL_SHADOW,
        dataset_version=NATURAL_DATASET_VERSION,
        created_at=str(records[0].get("collected_at")) if records else SNAPSHOT_CREATED_AT,
        case_count=len(records),
        content_sha256=content_sha256(records), oracle_version=NATURAL_ORACLE_VERSION,
        oracle_sha256=content_sha256([]),
        oracle_review_status=OracleReviewStatus.PENDING_HUMAN_REVIEW,
        used_for_tuning=False, lifecycle=DatasetLifecycle.COLLECTING,
        **planner_snapshot(),
    )


def oracle_case_from_dict(value: dict[str, Any]) -> OracleCase:
    from ..contracts import Intent, RagPolicy, SourceId, ValidatorId

    required_fields = (
        "case_id", "query", "primary_intent", "secondary_intents", "required_sources",
        "optional_sources", "forbidden_sources", "rag_policy", "permitted_tools",
        "forbidden_tools", "validators", "memory_policy", "clarification_required",
        "write_permitted", "source_statuses", "expected_missing_actions",
        "oracle_reviewer", "oracle_version",
    )
    if any(value.get(field) is None for field in required_fields):
        raise ValueError("oracle contains unreviewed/null fields")
    reviewer = str(value["oracle_reviewer"])
    if not reviewer.startswith("reviewer-") or any(ch.isspace() for ch in reviewer):
        raise ValueError("oracle_reviewer must be a pseudonymous reviewer-* ID")
    return OracleCase(
        case_id=str(value["case_id"]), query=str(value["query"]),
        conversational_context=tuple(str(item) for item in value.get("conversational_context", ())),
        primary_intent=Intent(str(value["primary_intent"])),
        secondary_intents=tuple(Intent(str(item)) for item in value["secondary_intents"]),
        required_sources=tuple(SourceId(str(item)) for item in value["required_sources"]),
        optional_sources=tuple(SourceId(str(item)) for item in value["optional_sources"]),
        forbidden_sources=tuple(SourceId(str(item)) for item in value["forbidden_sources"]),
        rag_policy=RagPolicy(str(value["rag_policy"])),
        permitted_tools=tuple(str(item) for item in value["permitted_tools"]),
        forbidden_tools=tuple(str(item) for item in value["forbidden_tools"]),
        validators=tuple(ValidatorId(str(item)) for item in value["validators"]),
        memory_policy=str(value["memory_policy"]),
        clarification_required=bool(value["clarification_required"]),
        write_permitted=bool(value["write_permitted"]),
        source_statuses=tuple((SourceId(str(key)), str(status)) for key, status in value["source_statuses"].items()),
        expected_missing_actions=tuple((SourceId(str(key)), str(action)) for key, action in value["expected_missing_actions"].items()),
        oracle_reviewer=reviewer, oracle_version=str(value["oracle_version"]),
    )


def dataset_identity_from_dict(value: dict[str, Any]) -> DatasetIdentity:
    return DatasetIdentity(
        dataset_type=DatasetType(str(value["dataset_type"])),
        dataset_version=str(value["dataset_version"]), created_at=str(value["created_at"]),
        case_count=int(value["case_count"]), content_sha256=value.get("content_sha256"),
        oracle_version=str(value["oracle_version"]), oracle_sha256=value.get("oracle_sha256"),
        oracle_review_status=OracleReviewStatus(str(value["oracle_review_status"])),
        used_for_tuning=bool(value["used_for_tuning"]),
        lifecycle=DatasetLifecycle(str(value["lifecycle"])),
        planner_version=str(value["planner_version"]),
        planner_commit=str(value["planner_commit"]),
        planner_content_sha256=str(value["planner_content_sha256"]),
    )


def freeze_reviewed_dataset(
    *, dataset_type: DatasetType, dataset_version: str,
    case_payloads: list[dict[str, Any]], oracle_payloads: list[dict[str, Any]],
    created_at: str,
) -> tuple[DatasetIdentity, tuple[OracleCase, ...]]:
    if dataset_type == DatasetType.REGRESSION:
        raise ValueError("the legacy regression identity is already frozen/used for tuning")
    if len(case_payloads) < 100:
        raise ValueError("natural/adversarial validation requires at least 100 cases")
    oracles = tuple(oracle_case_from_dict(item) for item in oracle_payloads)
    if len(oracles) != len(case_payloads):
        raise ValueError("case and oracle counts differ")
    case_ids = {str(item.get("case_id") or item.get("record_id")) for item in case_payloads}
    if case_ids != {item.case_id for item in oracles}:
        raise ValueError("case and oracle IDs differ")
    oracle_versions = {item.oracle_version for item in oracles}
    if len(oracle_versions) != 1:
        raise ValueError("all oracle labels must use one version")
    identity = DatasetIdentity(
        dataset_type=dataset_type, dataset_version=dataset_version,
        created_at=created_at, case_count=len(case_payloads),
        content_sha256=content_sha256(case_payloads), oracle_version=oracle_versions.pop(),
        oracle_sha256=content_sha256([item.to_dict() for item in oracles]),
        oracle_review_status=OracleReviewStatus.HUMAN_REVIEWED,
        used_for_tuning=False, lifecycle=DatasetLifecycle.FROZEN,
        **planner_snapshot(),
    )
    return identity, oracles


def mark_used_for_tuning(identity: DatasetIdentity) -> DatasetIdentity:
    """Irreversibly remove independent/holdout status after routing changes."""

    return replace(
        identity,
        dataset_type=(
            DatasetType.REGRESSION
            if identity.dataset_type == DatasetType.ADVERSARIAL_HOLDOUT
            else identity.dataset_type
        ),
        dataset_version=f"{identity.dataset_version}-used-for-tuning",
        used_for_tuning=True,
        lifecycle=DatasetLifecycle.USED_FOR_TUNING,
    )


__all__ = [
    "NATURAL_DATASET_VERSION", "NATURAL_ORACLE_VERSION", "REGRESSION_ORACLE_VERSION",
    "adversarial_candidate_identity", "load_natural_records", "natural_collecting_identity",
    "dataset_identity_from_dict", "freeze_reviewed_dataset", "mark_used_for_tuning",
    "oracle_case_from_dict", "planner_snapshot",
    "regression_identity", "regression_payloads",
]
