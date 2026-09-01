from __future__ import annotations

import json

from modules.wger.canonical_exercises import (
    CATALOG_VERSION,
    CURATION_POLICY_VERSION,
    MANIFEST_FILE,
    SOURCE_SNAPSHOT,
    build_catalog_manifest,
    content_sha256,
    derive_difficulty,
    derive_laterality,
    derive_movement_pattern,
    file_sha256,
    load_canonical_exercise_catalog,
    verify_catalog_manifest,
)
from services.agent.tools import workout


def _manifest() -> dict:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def _by_source_id(source_id: int) -> dict:
    return next(
        item
        for item in load_canonical_exercise_catalog()
        if item["source_exercise_id"] == source_id
    )


def test_e2_manifest_is_self_hashed_and_reproducible() -> None:
    manifest = _manifest()
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    assert manifest["manifest_hash"] == content_sha256(unsigned)
    assert build_catalog_manifest(git_commit=manifest["git_commit"]) == manifest
    assert verify_catalog_manifest()["ok"] is True


def test_catalog_normalizes_all_885_unique_wger_records() -> None:
    catalog = load_canonical_exercise_catalog()
    assert len(catalog) == 885
    assert len({item["exercise_id"] for item in catalog}) == 885
    assert len({item["source_exercise_id"] for item in catalog}) == 885
    assert len({item["source_uuid"] for item in catalog}) == 885
    assert all(item["exercise_id"] == f"WGER_EXERCISE_{item['source_uuid']}" for item in catalog)


def test_catalog_identity_is_tied_to_frozen_e1_snapshot() -> None:
    manifest = _manifest()
    expected = "542cc7a7f7d87938f6c245c3ff23c2a32483c5734039ee953d1dbed9d9e3d226"
    assert file_sha256(SOURCE_SNAPSHOT) == expected
    assert manifest["source"]["snapshot_sha256"] == expected
    assert manifest["e1_baseline"]["expected_source_snapshot_sha256"] == expected
    assert manifest["e1_baseline"]["unchanged"] is True


def test_wger_facts_and_app_curated_fields_have_distinct_provenance() -> None:
    exercise = _by_source_id(73)
    assert exercise["name_en"] == "Bench Press"
    assert exercise["field_provenance"]["name_en"] == "WGER_TRANSLATION_LANGUAGE_2"
    assert exercise["field_provenance"]["primary_muscles"] == "WGER"
    assert exercise["movement_pattern"]["value"] == "HORIZONTAL_PUSH"
    assert exercise["movement_pattern"]["provenance"] == "APP_CURATED_RULE"
    assert exercise["movement_pattern"]["policy_version"] == CURATION_POLICY_VERSION
    assert exercise["movement_pattern"]["human_reviewed"] is False


def test_missing_vietnamese_name_and_sync_time_are_not_fabricated() -> None:
    catalog = load_canonical_exercise_catalog()
    assert all(item["name_vi"] is None for item in catalog)
    assert all(item["last_synced_at"] is None for item in catalog)
    assert all(item["field_provenance"]["name_vi"] == "MISSING_NOT_GENERATED" for item in catalog)
    assert all(
        item["field_provenance"]["last_synced_at"]
        == "MISSING_NO_SNAPSHOT_MANIFEST"
        for item in catalog
    )


def test_record_translation_and_media_licenses_remain_separate() -> None:
    exercise = _by_source_id(12)
    assert exercise["source_license_metadata"]["license"]["short_name"] == "CC-BY-SA 3"
    assert exercise["instructions"]["license_metadata"]["license_id"] == 1
    assert len(exercise["media"]["images"]) == 1
    assert exercise["media"]["images"][0]["license_metadata"]["license_id"] == 2
    assert len(exercise["media"]["videos"]) == 1
    assert exercise["media"]["videos"][0]["license_metadata"]["license_id"] == 2


def test_instruction_html_is_preserved_and_plain_text_is_safe_for_consumers() -> None:
    exercise = _by_source_id(31)
    assert exercise["instructions"]["source_html"].startswith("<p>")
    assert "<p>" not in exercise["instructions"]["text"]
    assert exercise["instructions"]["text"] == (
        "Grab dumbbells and extend arms to side and hold as long as you can"
    )


def test_substitution_group_requires_pattern_and_primary_muscle() -> None:
    bench = _by_source_id(73)
    swing = _by_source_id(9)
    assert bench["substitution_group"]["value"] == "HORIZONTAL_PUSH:PRIMARY:4"
    assert bench["substitution_group"]["provenance"] == "APP_CURATED_RULE"
    assert swing["movement_pattern"]["value"] == "HINGE"
    assert swing["primary_muscles"] == []
    assert swing["substitution_group"]["value"] is None
    assert "SUBSTITUTION_GROUP_REVIEW_REQUIRED" in swing["quality_flags"]


def test_curated_rules_preserve_unknowns_instead_of_guessing() -> None:
    assert derive_movement_pattern("Unclassified movement", "Arms")["value"] == "UNKNOWN"
    assert derive_difficulty("Bench Press")["value"] == "UNSPECIFIED"
    assert derive_laterality("Bench Press")["value"] == "UNSPECIFIED"
    assert derive_difficulty("Assisted Pull-up")["value"] == "BEGINNER"
    assert derive_laterality("Single Arm Row")["value"] == "UNILATERAL"


def test_manifest_exposes_quality_debt_and_phase_boundary() -> None:
    manifest = _manifest()
    qa = manifest["qa"]
    assert manifest["schema_version"] == CATALOG_VERSION
    assert qa["record_count"] == 885
    assert qa["instructions_missing"] == 29
    assert qa["primary_muscles_missing"] == 194
    assert qa["name_vi_missing"] == 885
    assert qa["last_synced_at_missing"] == 885
    assert qa["license_counts"] == {
        "CC-BY-SA 3": 133,
        "CC-BY-SA 4": 732,
        "CC0": 20,
    }
    assert manifest["catalog"]["production_recommendation_enabled"] is False
    assert "chatbot catalog integration" in manifest["phase_boundary"]["not_implemented"]


def test_catalog_is_defensively_copied_and_does_not_replace_e1_agent_path() -> None:
    first = load_canonical_exercise_catalog()
    first[0]["name_en"] = "MUTATED"
    second = load_canonical_exercise_catalog()
    assert second[0]["name_en"] != "MUTATED"
    assert len(workout._EXERCISES) == 884
    assert len(second) == 885
    assert all(item["ingestion"]["production_recommendation_enabled"] is False for item in second)
