"""Auditable production-catalog ingestion gates for DEVELOPMENT D4.1.

Staging artifacts are deliberately separate from the runtime catalog.  This
module can normalize, match and review imported records, but it never writes to
``vietnamese_foods.json`` or any other frozen research input.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from copy import deepcopy
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from modules.nutrition.canonical_foods import (
    MatchQuality,
    energy_consistency,
    load_canonical_food_catalog,
    load_source_registry,
)
from modules.nutrition.catalog import load_dish_catalog
from services.experiment.config import ExperimentConfig


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
# In local development the backend lives at ``<repo>/apps/backend``; the
# development container mounts that same directory directly at ``/app``.
# Derive a best-effort repository root without indexing beyond ``/`` so merely
# importing the runtime catalog never fails inside the container.
REPO_ROOT = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR
SOURCE_REGISTRY_FILE = DATA_DIR / "food_source_registry_v1.json"
RESEARCH_MANIFEST_FILE = DATA_DIR / "research_corpus_manifest.json"
PRODUCTION_MANIFEST_FILE = DATA_DIR / "production_catalog_manifest_v1.json"
REVIEW_QUEUE_FILE = DATA_DIR / "catalog_review_queues_v1.json"
STAGING_INDEX_FILE = DATA_DIR / "catalog_staging_index_v1.json"

CATALOG_VERSION = "production-catalog-v1.0.0"
VALIDATOR_VERSION = "catalog-ingestion-d4.1.0"
STAGING_SCHEMA_VERSION = "food-staging-v1.0.0"
MAX_FOODS_PER_BATCH = 50
MAX_DISHES_PER_BATCH = 30

REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "publisher",
        "edition",
        "access_url",
        "license_reuse_status",
        "redistribution_status",
        "nutrient_import_allowed",
        "matching_priority",
        "review_date",
        "approval_status",
    }
)
PROTECTED_MATCH_FIELDS = (
    "species_or_type",
    "state",
    "part_or_cut",
    "processing",
    "cooking_method",
)
BLOCKING_QA_CODES = frozenset(
    {
        "NEGATIVE_VALUE",
        "UNIT_ANOMALY",
        "EXTREME_OUTLIER",
        "DUPLICATE_CANONICAL_ID",
        "DUPLICATE_SOURCE_ID",
        "RAW_COOKED_MISMATCH",
    }
)

_CANONICAL_UNITS = {
    "energy_kcal": "kcal",
    "protein": "g",
    "fat": "g",
    "carbohydrates": "g",
    "fiber": "g",
    "calcium": "mg",
    "iron": "mg",
    "magnesium": "mg",
    "phosphorus": "mg",
    "potassium": "mg",
    "sodium": "mg",
    "zinc": "mg",
    "vitamin_c": "mg",
}
_MASS_TO_G = {"g": 1.0, "mg": 0.001, "ug": 0.000001, "µg": 0.000001}
_OUTLIER_MAX = {
    "energy_kcal": 1000.0,
    "protein": 100.0,
    "fat": 100.0,
    "carbohydrates": 100.0,
    "fiber": 100.0,
    "calcium": 10000.0,
    "iron": 1000.0,
    "magnesium": 10000.0,
    "phosphorus": 10000.0,
    "potassium": 100000.0,
    "sodium": 100000.0,
    "zinc": 1000.0,
    "vitamin_c": 10000.0,
}


class CatalogIngestionError(ValueError):
    """Raised when an ingestion or release invariant is violated."""


class StagingState(str, Enum):
    RAW_IMPORTED = "RAW_IMPORTED"
    NORMALIZED = "NORMALIZED"
    MATCHED = "MATCHED"
    QA_REVIEW = "QA_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


_ALLOWED_TRANSITIONS = {
    StagingState.RAW_IMPORTED: {StagingState.NORMALIZED, StagingState.REJECTED},
    StagingState.NORMALIZED: {StagingState.MATCHED, StagingState.REJECTED},
    StagingState.MATCHED: {StagingState.QA_REVIEW, StagingState.REJECTED},
    StagingState.QA_REVIEW: {StagingState.APPROVED, StagingState.REJECTED},
    StagingState.APPROVED: set(),
    StagingState.REJECTED: set(),
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogIngestionError(f"INVALID_JSON:{path.name}") from exc


def _source_by_id(source_id: str) -> dict[str, Any]:
    registry = validate_source_registry(load_source_registry())
    for source in registry["sources"]:
        if source["source_id"] == source_id:
            return source
    raise CatalogIngestionError(f"UNKNOWN_SOURCE:{source_id}")


def validate_source_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Validate complete source approval metadata and locked-source gates."""

    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise CatalogIngestionError("INVALID_SOURCE_REGISTRY")
    source_ids: list[str] = []
    priorities: list[int] = []
    for source in sources:
        missing = REQUIRED_SOURCE_FIELDS - set(source)
        if missing:
            raise CatalogIngestionError(
                f"SOURCE_METADATA_MISSING:{source.get('source_id')}:{','.join(sorted(missing))}"
            )
        source_id = str(source["source_id"])
        source_ids.append(source_id)
        priorities.append(int(source["matching_priority"]))
        try:
            date.fromisoformat(str(source["review_date"]))
        except ValueError as exc:
            raise CatalogIngestionError(f"INVALID_SOURCE_REVIEW_DATE:{source_id}") from exc
        approved = source["approval_status"] == "APPROVED"
        if bool(source["nutrient_import_allowed"]) != approved:
            raise CatalogIngestionError(f"SOURCE_APPROVAL_GATE_MISMATCH:{source_id}")
        if source["ingestion_status"] != "ACTIVE" and source["nutrient_import_allowed"]:
            raise CatalogIngestionError(f"LOCKED_SOURCE_IMPORT_ENABLED:{source_id}")
    if len(source_ids) != len(set(source_ids)):
        raise CatalogIngestionError("DUPLICATE_SOURCE_ID")
    if priorities != list(range(len(priorities))):
        raise CatalogIngestionError("INVALID_MATCHING_PRIORITY")
    return deepcopy(registry)


def assert_source_approved(source_id: str) -> dict[str, Any]:
    source = _source_by_id(source_id)
    if not source["nutrient_import_allowed"] or source["approval_status"] != "APPROVED":
        raise CatalogIngestionError(f"SOURCE_LOCKED:{source_id}")
    return source


def transition(record: dict[str, Any], target: StagingState) -> dict[str, Any]:
    """Apply a monotonic, audited staging lifecycle transition."""

    try:
        current = StagingState(record["lifecycle_state"])
    except (KeyError, ValueError) as exc:
        raise CatalogIngestionError("INVALID_STAGING_STATE") from exc
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise CatalogIngestionError(f"INVALID_TRANSITION:{current.value}->{target.value}")
    updated = deepcopy(record)
    updated["lifecycle_state"] = target.value
    updated.setdefault("lifecycle_history", []).append(target.value)
    return updated


def raw_import_food(
    record: dict[str, Any], *, source_id: str, batch_id: str, source_snapshot: str
) -> dict[str, Any]:
    """Place one approved-source record in staging without altering production."""

    source = assert_source_approved(source_id)
    source_record_id = str(record.get("source_record_id") or "").strip()
    if not source_record_id:
        raise CatalogIngestionError("MISSING_SOURCE_RECORD_ID")
    if not batch_id.strip() or not source_snapshot.strip():
        raise CatalogIngestionError("MISSING_BATCH_PROVENANCE")
    return {
        "schema_version": STAGING_SCHEMA_VERSION,
        "record_type": "FOOD",
        "batch_id": batch_id,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "source_edition": source["edition"],
        "source_snapshot": source_snapshot,
        "lifecycle_state": StagingState.RAW_IMPORTED.value,
        "lifecycle_history": [StagingState.RAW_IMPORTED.value],
        "original_record": deepcopy(record),
        "normalized_record": None,
        "match": None,
        "qa_signals": [],
        "review": {"status": "PENDING", "reviewer": None, "resolution": None},
    }


def _normalize_value(
    nutrient: str, value: float, original_unit: str, basis_amount_g: float
) -> tuple[float, str, str]:
    canonical_unit = _CANONICAL_UNITS[nutrient]
    unit = original_unit.strip()
    if nutrient == "energy_kcal":
        if unit == "kcal":
            converted = value
            rule = "IDENTITY_KCAL"
        elif unit == "kJ":
            converted = value / 4.184
            rule = "KJ_TO_KCAL_DIVIDE_4_184"
        else:
            raise CatalogIngestionError(f"UNSUPPORTED_UNIT:{nutrient}:{unit}")
    else:
        if unit not in _MASS_TO_G or canonical_unit not in _MASS_TO_G:
            raise CatalogIngestionError(f"UNSUPPORTED_UNIT:{nutrient}:{unit}")
        converted = value * _MASS_TO_G[unit] / _MASS_TO_G[canonical_unit]
        rule = f"{unit.upper()}_TO_{canonical_unit.upper()}"
    basis_factor = 100.0 / basis_amount_g
    return converted * basis_factor, canonical_unit, f"{rule};SCALE_{basis_amount_g:g}G_TO_100G"


def normalize_food_record(staged: dict[str, Any]) -> dict[str, Any]:
    """Normalize source nutrients to per-100g while retaining the originals."""

    if staged.get("lifecycle_state") != StagingState.RAW_IMPORTED.value:
        raise CatalogIngestionError("NORMALIZATION_REQUIRES_RAW_IMPORTED")
    original = staged["original_record"]
    name = str(original.get("name") or "").strip()
    description = deepcopy(original.get("description") or {})
    if not name:
        raise CatalogIngestionError("MISSING_FOOD_NAME")
    nutrients = original.get("nutrients") or {}
    normalized_nutrients: dict[str, dict[str, Any]] = {}
    normalization_issues: list[dict[str, Any]] = []
    for nutrient, canonical_unit in _CANONICAL_UNITS.items():
        source_value = nutrients.get(nutrient)
        if source_value is None or source_value.get("value") is None:
            normalized_nutrients[nutrient] = {
                "source_id": staged["source_id"],
                "source_record_id": staged["source_record_id"],
                "source_edition": staged["source_edition"],
                "original_value": None,
                "original_unit": source_value.get("unit") if source_value else None,
                "original_basis": deepcopy(source_value.get("basis")) if source_value else None,
                "normalized_value": None,
                "normalized_unit": canonical_unit,
                "normalized_basis": "PER_100G_EDIBLE_PORTION",
                "normalization_rule": "MISSING_PRESERVED_AS_NULL",
                "review_status": "MISSING",
            }
            continue
        try:
            value = float(source_value["value"])
            basis = source_value.get("basis") or {}
            basis_amount = float(basis["amount"])
            basis_unit = str(basis["unit"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogIngestionError(f"INVALID_NUTRIENT_VALUE:{nutrient}") from exc
        if basis_unit != "g" or basis_amount <= 0:
            raise CatalogIngestionError(f"UNSUPPORTED_BASIS:{nutrient}")
        try:
            normalized_value, normalized_unit, rule = _normalize_value(
                nutrient, value, str(source_value.get("unit") or ""), basis_amount
            )
            review_status = "NORMALIZED_UNREVIEWED"
        except CatalogIngestionError as exc:
            normalized_value = None
            normalized_unit = canonical_unit
            rule = "NORMALIZATION_FAILED"
            review_status = "QA_REVIEW_REQUIRED"
            normalization_issues.append(
                _qa_signal("UNIT_ANOMALY", "BLOCKING", nutrient, str(exc))
            )
        normalized_nutrients[nutrient] = {
            "source_id": staged["source_id"],
            "source_record_id": staged["source_record_id"],
            "source_edition": staged["source_edition"],
            "original_value": value,
            "original_unit": source_value.get("unit"),
            "original_basis": deepcopy(basis),
            "normalized_value": (
                round(normalized_value, 8) if normalized_value is not None else None
            ),
            "normalized_unit": normalized_unit,
            "normalized_basis": "PER_100G_EDIBLE_PORTION",
            "normalization_rule": rule,
            "review_status": review_status,
        }
    updated = transition(staged, StagingState.NORMALIZED)
    updated["normalized_record"] = {
        "name": name,
        "description": {
            field: description.get(field) for field in PROTECTED_MATCH_FIELDS
        },
        "nutrients_per_100g": normalized_nutrients,
    }
    updated["normalization_issues"] = normalization_issues
    return updated


def match_food_record(
    staged: dict[str, Any],
    *,
    quality: MatchQuality,
    canonical_food_id: str | None,
    canonical_description: dict[str, Any] | None,
    justification: str | None = None,
) -> dict[str, Any]:
    """Record a match without weakening identity-critical descriptors."""

    if staged.get("lifecycle_state") != StagingState.NORMALIZED.value:
        raise CatalogIngestionError("MATCHING_REQUIRES_NORMALIZED")
    if quality == MatchQuality.UNRESOLVED:
        canonical_food_id = None
    elif not canonical_food_id:
        raise CatalogIngestionError("MATCH_REQUIRES_CANONICAL_ID")
    incoming = staged["normalized_record"]["description"]
    canonical = canonical_description or {}
    mismatches = [
        field
        for field in PROTECTED_MATCH_FIELDS
        if incoming.get(field) != canonical.get(field)
    ]
    if quality == MatchQuality.EXACT and mismatches:
        raise CatalogIngestionError(f"PROTECTED_DESCRIPTOR_MISMATCH:{','.join(mismatches)}")
    if quality == MatchQuality.SUBSTITUTED_WITH_JUSTIFICATION and not (justification or "").strip():
        raise CatalogIngestionError("SUBSTITUTION_REQUIRES_JUSTIFICATION")
    updated = transition(staged, StagingState.MATCHED)
    updated["match"] = {
        "quality": quality.value,
        "canonical_food_id": canonical_food_id,
        "protected_descriptor_mismatches": mismatches,
        "justification": justification,
        "automatic_approval_eligible": quality == MatchQuality.EXACT and not mismatches,
        "review_status": "HUMAN_REVIEW_REQUIRED" if quality != MatchQuality.EXACT else "PENDING_QA",
    }
    return updated


def _qa_signal(code: str, severity: str, field: str | None, detail: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "field": field, "detail": detail}


def run_food_qa(
    staged: dict[str, Any],
    *,
    existing_canonical_ids: Iterable[str] = (),
    batch_source_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Calculate engineering signals; source energy always remains authoritative."""

    if staged.get("lifecycle_state") != StagingState.MATCHED.value:
        raise CatalogIngestionError("QA_REQUIRES_MATCHED")
    signals: list[dict[str, Any]] = deepcopy(staged.get("normalization_issues") or [])
    nutrients = staged["normalized_record"]["nutrients_per_100g"]
    for nutrient, item in nutrients.items():
        value = item["normalized_value"]
        if value is None:
            continue
        if not math.isfinite(value):
            signals.append(_qa_signal("UNIT_ANOMALY", "BLOCKING", nutrient, "Non-finite value"))
        elif value < 0:
            signals.append(_qa_signal("NEGATIVE_VALUE", "BLOCKING", nutrient, str(value)))
        elif value > _OUTLIER_MAX[nutrient]:
            signals.append(_qa_signal("EXTREME_OUTLIER", "BLOCKING", nutrient, str(value)))
        if item["normalized_unit"] != _CANONICAL_UNITS[nutrient]:
            signals.append(_qa_signal("UNIT_ANOMALY", "BLOCKING", nutrient, item["normalized_unit"]))
    values = {key: value["normalized_value"] or 0.0 for key, value in nutrients.items()}
    energy_qa = energy_consistency(
        values["energy_kcal"], values["protein"], values["carbohydrates"], values["fat"]
    )
    if energy_qa["status"] in {"REVIEW", "FAIL"}:
        signals.append(
            _qa_signal(
                "ENERGY_MACRO_INCONSISTENCY",
                "REVIEW",
                "energy_kcal",
                json.dumps(energy_qa, sort_keys=True),
            )
        )
    canonical_id = (staged.get("match") or {}).get("canonical_food_id")
    if canonical_id and canonical_id in set(existing_canonical_ids):
        signals.append(_qa_signal("DUPLICATE_CANONICAL_ID", "BLOCKING", None, canonical_id))
    source_key = f"{staged['source_id']}:{staged['source_record_id']}"
    if source_key in set(batch_source_ids):
        signals.append(_qa_signal("DUPLICATE_SOURCE_ID", "BLOCKING", None, source_key))
    mismatches = (staged.get("match") or {}).get("protected_descriptor_mismatches") or []
    if any(field in {"state", "cooking_method"} for field in mismatches):
        signals.append(_qa_signal("RAW_COOKED_MISMATCH", "BLOCKING", None, ",".join(mismatches)))
    updated = transition(staged, StagingState.QA_REVIEW)
    updated["qa_signals"] = signals
    updated["qa_summary"] = {
        "blocking_count": sum(item["code"] in BLOCKING_QA_CODES for item in signals),
        "review_count": sum(item["severity"] == "REVIEW" for item in signals),
        "energy_4_4_9_is_ground_truth": False,
    }
    return updated


def review_food_record(
    staged: dict[str, Any],
    *,
    decision: str,
    reviewer: str,
    resolution: str,
    non_exact_match_approval: str | None = None,
    protected_descriptor_approvals: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Approve or reject a QA-reviewed staging record; never publish it directly."""

    if staged.get("lifecycle_state") != StagingState.QA_REVIEW.value:
        raise CatalogIngestionError("REVIEW_REQUIRES_QA_REVIEW")
    if not reviewer.strip() or not resolution.strip():
        raise CatalogIngestionError("REVIEWER_AND_RESOLUTION_REQUIRED")
    if decision not in {"APPROVE", "REJECT"}:
        raise CatalogIngestionError("INVALID_REVIEW_DECISION")
    quality = staged.get("match", {}).get("quality")
    descriptor_approvals = protected_descriptor_approvals or {}
    mismatches = staged.get("match", {}).get("protected_descriptor_mismatches") or []
    unresolved_descriptors = [
        field for field in mismatches if not str(descriptor_approvals.get(field) or "").strip()
    ]
    blocking_signals = [
        signal
        for signal in staged.get("qa_signals", [])
        if signal["code"] in BLOCKING_QA_CODES
        and not (
            signal["code"] == "RAW_COOKED_MISMATCH" and not unresolved_descriptors
        )
    ]
    if decision == "APPROVE" and blocking_signals:
        raise CatalogIngestionError("BLOCKING_QA_UNRESOLVED")
    if decision == "APPROVE" and quality == MatchQuality.UNRESOLVED.value:
        raise CatalogIngestionError("UNRESOLVED_MATCH_CANNOT_BE_APPROVED")
    if decision == "APPROVE" and quality != MatchQuality.EXACT.value:
        if not (non_exact_match_approval or "").strip():
            raise CatalogIngestionError("NON_EXACT_REQUIRES_DOCUMENTED_APPROVAL")
        if unresolved_descriptors:
            raise CatalogIngestionError(
                f"PROTECTED_DESCRIPTOR_APPROVAL_REQUIRED:{','.join(unresolved_descriptors)}"
            )
    target = StagingState.APPROVED if decision == "APPROVE" else StagingState.REJECTED
    updated = transition(staged, target)
    updated["review"] = {
        "status": target.value,
        "reviewer": reviewer,
        "resolution": resolution,
        "approval_mode": (
            "MANUAL_NON_EXACT"
            if decision == "APPROVE" and quality != MatchQuality.EXACT.value
            else "MANUAL_EXACT"
            if decision == "APPROVE"
            else "MANUAL_REJECTION"
        ),
        "non_exact_match_approval": non_exact_match_approval,
        "protected_descriptor_approvals": deepcopy(descriptor_approvals),
        "production_written": False,
    }
    return updated


def validate_batch_size(
    *, food_count: int, dish_count: int, explicit_override: bool = False
) -> None:
    if food_count < 0 or dish_count < 0:
        raise CatalogIngestionError("NEGATIVE_BATCH_COUNT")
    if not explicit_override and (
        food_count > MAX_FOODS_PER_BATCH or dish_count > MAX_DISHES_PER_BATCH
    ):
        raise CatalogIngestionError("SMALL_BATCH_LIMIT_EXCEEDED")


def recompute_staged_dish_nutrition(
    dish: dict[str, Any], canonical_foods: Iterable[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Require canonical IDs for every ingredient and recompute dish nutrition."""

    foods = list(canonical_foods) if canonical_foods is not None else load_canonical_food_catalog()
    foods_by_id = {food["food_id"]: food for food in foods}
    totals = {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbohydrate_g": 0.0}
    ingredients = dish.get("ingredients") or []
    if not ingredients:
        raise CatalogIngestionError("DISH_REQUIRES_INGREDIENTS")
    for ingredient in ingredients:
        food_id = str(ingredient.get("food_id") or "")
        if not food_id or food_id not in foods_by_id:
            raise CatalogIngestionError("FREE_TEXT_OR_UNKNOWN_DISH_INGREDIENT")
        try:
            grams = float(ingredient["grams"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogIngestionError("INVALID_DISH_INGREDIENT_WEIGHT") from exc
        if grams <= 0:
            raise CatalogIngestionError("INVALID_DISH_INGREDIENT_WEIGHT")
        food = foods_by_id[food_id]
        factor = grams / 100.0
        totals["energy_kcal"] += float(food.get("energy_kcal") or 0.0) * factor
        totals["protein_g"] += float(food.get("protein") or 0.0) * factor
        totals["fat_g"] += float(food.get("fat") or 0.0) * factor
        totals["carbohydrate_g"] += float(food.get("carbohydrates") or 0.0) * factor
    normalized = deepcopy(dish)
    normalized["nutrition"] = {
        key: round(value, 2) for key, value in totals.items()
    }
    normalized["nutrition"].update(
        {
            "method": "CANONICAL_INGREDIENT_SUM",
            "legacy_estimated_calories_reference_only": dish.get("estimated_calories"),
            "source_ids": sorted({foods_by_id[item["food_id"]]["source"]["dataset"] for item in ingredients}),
        }
    )
    return normalized


def build_review_queues() -> dict[str, Any]:
    foods = load_canonical_food_catalog()
    dishes = load_dish_catalog()
    serving_items = []
    for dish in dishes:
        if dish["quality"]["review_status"] != "LEGACY_SERVING_REVIEW_REQUIRED":
            continue
        alignment = dish["quality"]["catalog_energy_alignment"]
        serving_items.append(
            {
                "queue_item_id": f"SERVING-{int(dish['id']):04d}",
                "entity_type": "DISH",
                "entity_id": dish["id"],
                "name": dish["name"],
                "reason": "Legacy estimated calories differ from canonical ingredient-sum nutrition; serving definition needs human review.",
                "severity": "HIGH" if alignment["status"] == "FAIL" else "MEDIUM",
                "source": deepcopy(dish.get("provenance") or {"dataset": "vietnamese_dishes.json"}),
                "review_status": "OPEN",
                "resolution": None,
                "qa_evidence": alignment,
            }
        )
    energy_items = []
    for food in foods:
        qa = food["verification"]["energy_qa"]
        if qa["status"] not in {"REVIEW", "FAIL"}:
            continue
        energy_items.append(
            {
                "queue_item_id": f"ENERGY-{food['food_id']}",
                "entity_type": "FOOD",
                "entity_id": food["food_id"],
                "name": food["name"],
                "reason": "Engineering 4/4/9 signal differs from source energy; review source conventions without overwriting nutrient values.",
                "severity": "HIGH" if (qa.get("relative_delta") or 0.0) > 0.5 else "MEDIUM",
                "source": deepcopy(food["source"]),
                "review_status": "OPEN",
                "resolution": None,
                "qa_evidence": qa,
            }
        )
    return {
        "schema_version": "catalog-review-queue-v1.0.0",
        "generated_for_catalog_version": CATALOG_VERSION,
        "policy": "Review queues never mutate source nutrient values.",
        "queues": {
            "legacy_serving_sizes": serving_items,
            "energy_qa_warnings": energy_items,
        },
        "summary": {
            "legacy_serving_sizes": len(serving_items),
            "energy_qa_warnings": len(energy_items),
            "open": len(serving_items) + len(energy_items),
            "resolved": 0,
        },
    }


def research_identity() -> dict[str, Any]:
    manifest = _read_json(RESEARCH_MANIFEST_FILE)
    sources = []
    for item in manifest["source_dataset_files"]:
        path = DATA_DIR / item["dataset_file"]
        actual = file_sha256(path)
        sources.append(
            {
                "dataset_file": item["dataset_file"],
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "unchanged": actual == item["sha256"],
            }
        )
    return {
        "corpus_version": manifest["corpus_version"],
        "corpus_hash": manifest["corpus_hash"],
        "research_manifest_hash": manifest["manifest_hash"],
        "research_manifest_file_sha256": file_sha256(RESEARCH_MANIFEST_FILE),
        "source_artifacts": sources,
        "experiment_condition_hashes": {
            condition: ExperimentConfig(condition=condition).config_hash()
            for condition in ("A", "B", "C")
        },
        "production_catalog_is_separate": True,
    }


def current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CatalogIngestionError("GIT_COMMIT_UNAVAILABLE") from exc


def build_production_manifest(*, git_commit: str | None = None) -> dict[str, Any]:
    foods = load_canonical_food_catalog()
    dishes = load_dish_catalog()
    queues = build_review_queues()
    manifest = {
        "schema_version": "production-catalog-manifest-v1.0.0",
        "catalog_version": CATALOG_VERSION,
        "git_commit": git_commit or current_git_commit(),
        "food_count": len(foods),
        "dish_count": len(dishes),
        "food_content_hash": content_sha256(foods),
        "dish_content_hash": content_sha256(dishes),
        "source_registry_hash": file_sha256(SOURCE_REGISTRY_FILE),
        "hash_algorithm": "SHA-256 over canonical UTF-8 JSON unless a file hash is named",
        "validator_version": VALIDATOR_VERSION,
        "qa_summary": {
            "validator_errors": 0,
            "exact_dish_ingredient_matches": all(
                dish["quality"]["ingredient_match_complete"]
                and dish["quality"]["match_quality_counts"]["EXACT"] == len(dish["ingredients"])
                for dish in dishes
            ),
            "legacy_serving_review_open": queues["summary"]["legacy_serving_sizes"],
            "energy_qa_review_open": queues["summary"]["energy_qa_warnings"],
        },
        "research_identity": research_identity(),
    }
    manifest["manifest_hash"] = content_sha256(manifest)
    return manifest


def build_batch_manifest(
    *,
    batch_id: str,
    source_id: str,
    source_snapshot: str,
    source_hash: str,
    staged_records: list[dict[str, Any]],
    manual_reviewers: list[str],
    explicit_size_override: bool = False,
) -> dict[str, Any]:
    food_count = sum(item.get("record_type") == "FOOD" for item in staged_records)
    dish_count = sum(item.get("record_type") == "DISH" for item in staged_records)
    validate_batch_size(
        food_count=food_count,
        dish_count=dish_count,
        explicit_override=explicit_size_override,
    )
    states = [item.get("lifecycle_state") for item in staged_records]
    manifest = {
        "schema_version": "catalog-batch-manifest-v1.0.0",
        "batch_id": batch_id,
        "source_id": source_id,
        "source_snapshot": source_snapshot,
        "source_hash": source_hash,
        "records_imported": len(staged_records),
        "records_approved": states.count(StagingState.APPROVED.value),
        "records_rejected": states.count(StagingState.REJECTED.value),
        "records_unresolved": sum(
            (item.get("match") or {}).get("quality") == MatchQuality.UNRESOLVED.value
            for item in staged_records
        ),
        "manual_reviewers": sorted(set(manual_reviewers)),
        "small_batch_override": explicit_size_override,
        "output_hash": content_sha256(staged_records),
    }
    manifest["manifest_hash"] = content_sha256(manifest)
    return manifest


def verify_frozen_baseline(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = manifest or _read_json(PRODUCTION_MANIFEST_FILE)
    actual = build_production_manifest(git_commit=expected["git_commit"])
    checked_fields = (
        "catalog_version",
        "food_count",
        "dish_count",
        "food_content_hash",
        "dish_content_hash",
        "source_registry_hash",
        "validator_version",
        "qa_summary",
        "research_identity",
        "manifest_hash",
    )
    mismatches = [field for field in checked_fields if actual.get(field) != expected.get(field)]
    if mismatches:
        raise CatalogIngestionError(f"BASELINE_MISMATCH:{','.join(mismatches)}")
    if not all(item["unchanged"] for item in actual["research_identity"]["source_artifacts"]):
        raise CatalogIngestionError("FROZEN_RESEARCH_ARTIFACT_CHANGED")
    return {
        "ok": True,
        "catalog_version": expected["catalog_version"],
        "food_count": expected["food_count"],
        "dish_count": expected["dish_count"],
        "research_corpus": expected["research_identity"]["corpus_version"],
    }


__all__ = [
    "BLOCKING_QA_CODES",
    "CATALOG_VERSION",
    "MAX_DISHES_PER_BATCH",
    "MAX_FOODS_PER_BATCH",
    "PRODUCTION_MANIFEST_FILE",
    "REVIEW_QUEUE_FILE",
    "STAGING_INDEX_FILE",
    "STAGING_SCHEMA_VERSION",
    "VALIDATOR_VERSION",
    "CatalogIngestionError",
    "StagingState",
    "assert_source_approved",
    "build_batch_manifest",
    "build_production_manifest",
    "build_review_queues",
    "content_sha256",
    "file_sha256",
    "match_food_record",
    "normalize_food_record",
    "raw_import_food",
    "recompute_staged_dish_nutrition",
    "research_identity",
    "review_food_record",
    "run_food_qa",
    "transition",
    "validate_batch_size",
    "validate_source_registry",
    "verify_frozen_baseline",
]
