from __future__ import annotations

import json
from copy import deepcopy

import pytest

from modules.nutrition.canonical_foods import (
    AUTO_PUBLISH_MATCH_QUALITIES,
    MatchQuality,
    load_canonical_food_catalog,
    load_source_registry,
)
from modules.nutrition.catalog_ingestion import (
    PRODUCTION_MANIFEST_FILE,
    REVIEW_QUEUE_FILE,
    STAGING_INDEX_FILE,
    CatalogIngestionError,
    StagingState,
    build_batch_manifest,
    build_production_manifest,
    build_review_queues,
    content_sha256,
    match_food_record,
    normalize_food_record,
    raw_import_food,
    recompute_staged_dish_nutrition,
    research_identity,
    review_food_record,
    run_food_qa,
    validate_batch_size,
    validate_source_registry,
    verify_frozen_baseline,
)


def _source_record(*, source_record_id: str = "D4-TEST-001") -> dict:
    return {
        "source_record_id": source_record_id,
        "name": "Thực phẩm kiểm thử",
        "description": {
            "species_or_type": "Test species",
            "state": "RAW",
            "part_or_cut": "WHOLE",
            "processing": "NONE",
            "cooking_method": "NONE",
        },
        "nutrients": {
            "energy_kcal": {
                "value": 418.4,
                "unit": "kJ",
                "basis": {"amount": 50, "unit": "g"},
            },
            "protein": {
                "value": 5,
                "unit": "g",
                "basis": {"amount": 50, "unit": "g"},
            },
            "fat": {
                "value": 2,
                "unit": "g",
                "basis": {"amount": 50, "unit": "g"},
            },
            "carbohydrates": {
                "value": 17,
                "unit": "g",
                "basis": {"amount": 50, "unit": "g"},
            },
        },
    }


def _normalized() -> dict:
    raw = raw_import_food(
        _source_record(),
        source_id="VIETNAM_FCT",
        batch_id="D4-BATCH-TEST",
        source_snapshot="fixture.json",
    )
    return normalize_food_record(raw)


def _matched(quality: MatchQuality = MatchQuality.EXACT) -> dict:
    normalized = _normalized()
    return match_food_record(
        normalized,
        quality=quality,
        canonical_food_id="VN_FCT_99999",
        canonical_description=normalized["normalized_record"]["description"],
        justification="Manual comparison" if quality == MatchQuality.SUBSTITUTED_WITH_JUSTIFICATION else None,
    )


def test_baseline_manifest_is_frozen_and_self_verifying() -> None:
    stored = json.loads(PRODUCTION_MANIFEST_FILE.read_text(encoding="utf-8"))
    assert stored["food_count"] == 526
    assert stored["dish_count"] == 300
    assert stored["validator_version"] == "catalog-ingestion-d4.1.0"
    assert stored["manifest_hash"] == content_sha256(
        {key: value for key, value in stored.items() if key != "manifest_hash"}
    )
    assert build_production_manifest(git_commit=stored["git_commit"]) == stored
    assert verify_frozen_baseline()["ok"] is True


def test_research_corpus_and_conditions_are_separate_and_unchanged() -> None:
    identity = research_identity()
    assert identity["corpus_version"] == "offline-v1-636"
    assert identity["corpus_hash"] == "b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081"
    assert all(item["unchanged"] for item in identity["source_artifacts"])
    assert set(identity["experiment_condition_hashes"]) == {"A", "B", "C"}
    assert len(set(identity["experiment_condition_hashes"].values())) == 3
    assert identity["production_catalog_is_separate"] is True


def test_review_debt_queues_are_explicit_and_complete() -> None:
    stored = json.loads(REVIEW_QUEUE_FILE.read_text(encoding="utf-8"))
    assert stored == build_review_queues()
    assert stored["summary"] == {
        "legacy_serving_sizes": 70,
        "energy_qa_warnings": 3,
        "open": 73,
        "resolved": 0,
    }
    items = [item for queue in stored["queues"].values() for item in queue]
    assert all(
        {"reason", "severity", "source", "review_status", "resolution"} <= set(item)
        for item in items
    )
    assert all(item["review_status"] == "OPEN" and item["resolution"] is None for item in items)


def test_source_registry_has_complete_approval_metadata_and_locked_fallbacks() -> None:
    registry = validate_source_registry(load_source_registry())
    allowed = [source["source_id"] for source in registry["sources"] if source["nutrient_import_allowed"]]
    assert allowed == ["VIETNAM_FCT"]
    assert all(
        source["approval_status"] == "LOCKED"
        for source in registry["sources"]
        if source["source_id"] != "VIETNAM_FCT"
    )
    with pytest.raises(CatalogIngestionError, match="SOURCE_LOCKED:USDA_FDC"):
        raw_import_food(
            _source_record(),
            source_id="USDA_FDC",
            batch_id="LOCKED",
            source_snapshot="fixture.json",
        )


def test_only_exact_is_auto_publishable() -> None:
    assert AUTO_PUBLISH_MATCH_QUALITIES == {"EXACT"}
    exact = _matched()
    close = _matched(MatchQuality.CLOSE_VARIANT)
    assert exact["match"]["automatic_approval_eligible"] is True
    assert close["match"]["automatic_approval_eligible"] is False
    assert close["match"]["review_status"] == "HUMAN_REVIEW_REQUIRED"


def test_lifecycle_normalization_preserves_original_values_and_missing_nulls() -> None:
    normalized = _normalized()
    assert normalized["lifecycle_history"] == ["RAW_IMPORTED", "NORMALIZED"]
    energy = normalized["normalized_record"]["nutrients_per_100g"]["energy_kcal"]
    assert energy["original_value"] == 418.4
    assert energy["original_unit"] == "kJ"
    assert energy["original_basis"] == {"amount": 50, "unit": "g"}
    assert energy["normalized_value"] == 200.0
    assert energy["normalized_unit"] == "kcal"
    assert energy["normalization_rule"] == "KJ_TO_KCAL_DIVIDE_4_184;SCALE_50G_TO_100G"
    calcium = normalized["normalized_record"]["nutrients_per_100g"]["calcium"]
    assert calcium["original_value"] is None
    assert calcium["normalized_value"] is None
    assert calcium["normalization_rule"] == "MISSING_PRESERVED_AS_NULL"


@pytest.mark.parametrize("field", ["species_or_type", "state", "part_or_cut", "processing", "cooking_method"])
def test_exact_match_never_changes_protected_descriptors(field: str) -> None:
    normalized = _normalized()
    description = deepcopy(normalized["normalized_record"]["description"])
    description[field] = "DIFFERENT"
    with pytest.raises(CatalogIngestionError, match="PROTECTED_DESCRIPTOR_MISMATCH"):
        match_food_record(
            normalized,
            quality=MatchQuality.EXACT,
            canonical_food_id="VN_FCT_99999",
            canonical_description=description,
        )


def test_qa_is_engineering_signal_and_exact_record_can_be_reviewed() -> None:
    qa = run_food_qa(_matched())
    assert qa["lifecycle_state"] == StagingState.QA_REVIEW.value
    assert qa["qa_summary"]["energy_4_4_9_is_ground_truth"] is False
    assert qa["qa_summary"]["blocking_count"] == 0
    approved = review_food_record(
        qa, decision="APPROVE", reviewer="D4 reviewer", resolution="Source and identity checked"
    )
    assert approved["lifecycle_state"] == StagingState.APPROVED.value
    assert approved["review"]["production_written"] is False


def test_non_exact_record_requires_documented_human_approval() -> None:
    qa = run_food_qa(_matched(MatchQuality.CLOSE_VARIANT))
    with pytest.raises(CatalogIngestionError, match="NON_EXACT_REQUIRES_DOCUMENTED_APPROVAL"):
        review_food_record(
            qa, decision="APPROVE", reviewer="Reviewer", resolution="Not exact"
        )
    approved = review_food_record(
        qa,
        decision="APPROVE",
        reviewer="Reviewer",
        resolution="Human compared both food descriptions",
        non_exact_match_approval="Approved as a close source variant; no identity facet differs",
    )
    assert approved["review"]["approval_mode"] == "MANUAL_NON_EXACT"
    assert approved["review"]["production_written"] is False


def test_unit_anomaly_is_preserved_for_blocking_qa() -> None:
    source = _source_record(source_record_id="BAD-UNIT")
    source["nutrients"]["protein"]["unit"] = "tablespoon"
    raw = raw_import_food(
        source,
        source_id="VIETNAM_FCT",
        batch_id="D4-UNIT",
        source_snapshot="fixture.json",
    )
    normalized = normalize_food_record(raw)
    protein = normalized["normalized_record"]["nutrients_per_100g"]["protein"]
    assert protein["original_unit"] == "tablespoon"
    assert protein["normalized_value"] is None
    assert protein["normalization_rule"] == "NORMALIZATION_FAILED"
    matched = match_food_record(
        normalized,
        quality=MatchQuality.EXACT,
        canonical_food_id="VN_FCT_99998",
        canonical_description=normalized["normalized_record"]["description"],
    )
    qa = run_food_qa(matched)
    assert any(signal["code"] == "UNIT_ANOMALY" for signal in qa["qa_signals"])
    assert qa["qa_summary"]["blocking_count"] == 1


def test_qa_flags_negative_duplicate_and_raw_cooked_mismatch() -> None:
    source = _source_record(source_record_id="DUPLICATE")
    source["nutrients"]["protein"]["value"] = -1
    raw = raw_import_food(
        source,
        source_id="VIETNAM_FCT",
        batch_id="D4-QA",
        source_snapshot="fixture.json",
    )
    normalized = normalize_food_record(raw)
    canonical_description = deepcopy(normalized["normalized_record"]["description"])
    canonical_description["state"] = "COOKED"
    matched = match_food_record(
        normalized,
        quality=MatchQuality.CLOSE_VARIANT,
        canonical_food_id="VN_FCT_00001",
        canonical_description=canonical_description,
    )
    qa = run_food_qa(
        matched,
        existing_canonical_ids={"VN_FCT_00001"},
        batch_source_ids={"VIETNAM_FCT:DUPLICATE"},
    )
    codes = {signal["code"] for signal in qa["qa_signals"]}
    assert {"NEGATIVE_VALUE", "DUPLICATE_CANONICAL_ID", "DUPLICATE_SOURCE_ID", "RAW_COOKED_MISMATCH"} <= codes
    assert qa["qa_summary"]["blocking_count"] >= 4


def test_batch_limits_and_manifest_counts() -> None:
    validate_batch_size(food_count=50, dish_count=30)
    with pytest.raises(CatalogIngestionError, match="SMALL_BATCH_LIMIT_EXCEEDED"):
        validate_batch_size(food_count=51, dish_count=0)
    rejected = run_food_qa(_matched())
    rejected = review_food_record(
        rejected, decision="REJECT", reviewer="Reviewer", resolution="Fixture rejection"
    )
    manifest = build_batch_manifest(
        batch_id="BATCH-001",
        source_id="VIETNAM_FCT",
        source_snapshot="snapshot.json",
        source_hash="a" * 64,
        staged_records=[rejected],
        manual_reviewers=["Reviewer"],
    )
    assert manifest["records_imported"] == 1
    assert manifest["records_rejected"] == 1
    assert manifest["records_approved"] == 0
    assert len(manifest["output_hash"]) == 64


def test_new_dish_requires_canonical_ids_and_recomputes_nutrition() -> None:
    food = load_canonical_food_catalog()[0]
    with pytest.raises(CatalogIngestionError, match="FREE_TEXT_OR_UNKNOWN_DISH_INGREDIENT"):
        recompute_staged_dish_nutrition(
            {"name": "Free text", "ingredients": [{"name": food["name"], "grams": 100}]}
        )
    dish = recompute_staged_dish_nutrition(
        {
            "name": "Canonical dish",
            "estimated_calories": 999,
            "ingredients": [{"food_id": food["food_id"], "grams": 100}],
        }
    )
    assert dish["nutrition"]["energy_kcal"] == food["energy_kcal"]
    assert dish["nutrition"]["method"] == "CANONICAL_INGREDIENT_SUM"
    assert dish["nutrition"]["legacy_estimated_calories_reference_only"] == 999


def test_staging_index_is_empty_and_not_a_production_input() -> None:
    staging = json.loads(STAGING_INDEX_FILE.read_text(encoding="utf-8"))
    assert staging["batches"] == []
    assert staging["policy"]["production_loader_reads_staging"] is False
