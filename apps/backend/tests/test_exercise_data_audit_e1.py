from __future__ import annotations

import json

from modules.wger.exercise_data_audit import (
    BACKEND_SNAPSHOT,
    MANIFEST_FILE,
    MOBILE_SNAPSHOT,
    agent_path_statistics,
    build_audit_manifest,
    content_sha256,
    file_sha256,
    snapshot_statistics,
    verify_audit_manifest,
)
from services.agent.context_planner.contracts import Intent, SourceId
from services.agent.context_planner.matrix import INTENT_SOURCE_MATRIX
from services.agent.tools import workout


def _manifest() -> dict:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def test_e1_manifest_is_self_hashed_and_reproducible() -> None:
    manifest = _manifest()
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    assert manifest["manifest_hash"] == content_sha256(unsigned)
    assert build_audit_manifest(git_commit=manifest["git_commit"]) == manifest
    assert verify_audit_manifest()["ok"] is True


def test_backend_and_mobile_snapshots_are_identical_and_frozen() -> None:
    manifest = _manifest()
    snapshot = manifest["snapshot"]
    expected = "542cc7a7f7d87938f6c245c3ff23c2a32483c5734039ee953d1dbed9d9e3d226"
    assert file_sha256(BACKEND_SNAPSHOT) == expected
    assert file_sha256(MOBILE_SNAPSHOT) == expected
    assert snapshot["backend_sha256"] == expected
    assert snapshot["mobile_sha256"] == expected
    assert snapshot["byte_identical"] is True


def test_snapshot_field_coverage_and_record_level_licenses_are_explicit() -> None:
    stats = snapshot_statistics()
    assert stats["record_count"] == 885
    assert stats["unique_id_count"] == 885
    assert stats["unique_uuid_count"] == 885
    assert stats["duplicate_id_count"] == 0
    assert stats["field_coverage"]["muscles"] == {"count": 691, "percent": 78.08}
    assert stats["field_coverage"]["equipment"] == {"count": 573, "percent": 64.75}
    assert stats["field_coverage"]["images"] == {"count": 261, "percent": 29.49}
    assert stats["field_coverage"]["videos"] == {"count": 46, "percent": 5.2}
    assert {item["short_name"]: item["count"] for item in stats["license_counts"]} == {
        "CC-BY-SA 3": 133,
        "CC-BY-SA 4": 732,
        "CC0": 20,
    }


def test_nested_translation_and_media_provenance_is_audited() -> None:
    stats = snapshot_statistics()["nested_content_provenance"]
    assert stats["translation_count"] > 885
    assert stats["translations_with_license"] == stats["translation_count"]
    assert stats["image_count"] == 345
    assert stats["images_with_license"] == 345
    assert stats["images_marked_ai_generated"] == 0
    assert stats["video_count"] == 78
    assert stats["videos_with_license"] == 78


def test_english_filter_still_returns_nested_multilingual_payload() -> None:
    stats = snapshot_statistics()
    assert stats["english_translation"] == {
        "language_id": 2,
        "records": 885,
        "name_present": 885,
        "description_present": 856,
        "note": "The source still returns nested translations in multiple languages; language=2 does not flatten the payload.",
    }
    assert len(stats["translation_language_counts"]) > 1


def test_agent_reduces_885_source_rows_to_884_six_field_records() -> None:
    audit = agent_path_statistics()
    assert audit["bundled_rows_loaded_at_import"] == len(workout._EXERCISES) == 884
    assert audit["agent_record_fields"] == [
        "id",
        "name",
        "category",
        "equipment",
        "is_bodyweight",
        "derived_level",
    ]
    assert audit["excluded_rows"] == [
        {"source_exercise_id": 1592, "name": "Meditación guiada o libre"}
    ]
    assert audit["training_history_used_by_suggest_workout"] is False
    assert audit["live_wger_used_by_suggest_workout"] is False
    assert "muscles" in audit["source_fields_not_retained_by_agent"]
    assert "license" in audit["source_fields_not_retained_by_agent"]


def test_context_planner_marks_history_optional_but_cannot_fetch_it() -> None:
    policy = INTENT_SOURCE_MATRIX[Intent.WORKOUT_RECOMMENDATION]
    assert SourceId.EXERCISE_HISTORY in policy.optional
    assert policy.tools == (
        "get_user_profile",
        "get_today_exercises",
        "suggest_workout",
    )
    assert "get_exercise_log_range" not in policy.tools


def test_live_api_breakage_is_recorded_without_affecting_local_verification() -> None:
    live = _manifest()["live_api_observation"]
    assert live["openapi_schema_version"] == "2.7.0a2"
    assert live["exerciseinfo_count"] == 862
    assert live["exerciseinfo_in_openapi"] is True
    assert live["exercise_search_status"] == 404
    assert live["exercise_search_in_openapi"] is False
    assert live["volatile_not_used_for_local_manifest_verification"] is True


def test_workout_log_audit_exposes_adaptation_gaps() -> None:
    contract = _manifest()["workout_log_contract"]
    assert "exerciseTemplateId" in contract["persisted_fields"]
    assert "per_set_load_kg" in contract["missing_for_adaptation"]
    assert "per_set_rpe_or_rir" in contract["missing_for_adaptation"]
    assert "pain_or_discomfort" in contract["missing_for_adaptation"]
    assert "session_rpe" in contract["missing_for_adaptation"]


def test_e1_does_not_change_frozen_research_identity() -> None:
    identity = _manifest()["research_identity"]
    assert identity["corpus_version"] == "offline-v1-636"
    assert identity["corpus_hash"] == "b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081"
    assert all(item["unchanged"] for item in identity["source_artifacts"])
