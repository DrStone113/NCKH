"""Deterministic E1 audit of the Wger exercise-data and agent paths.

This module is intentionally read-only.  It inventories the bundled snapshot,
the reduced agent representation, API surfaces and workout-log contract; it
does not promote Wger rows into a canonical exercise catalog.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from modules.nutrition.catalog_ingestion import research_identity
from services.agent.tools import workout


BACKEND_DIR = Path(__file__).resolve().parents[2]
# Docker mounts the backend directly at ``/app``; tolerate that layout for the
# read-only audit helpers while retaining the checkout root locally.
REPO_ROOT = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR
BACKEND_SNAPSHOT = BACKEND_DIR / "data" / "wger_exercises_raw.json"
MOBILE_SNAPSHOT = REPO_ROOT / "apps" / "mobile" / "assets" / "data" / "wger_exercises_raw.json"
FETCH_SCRIPT = BACKEND_DIR / "scripts" / "fetch_wger_exercises.py"
MANIFEST_FILE = BACKEND_DIR / "data" / "exercise_data_audit_e1_v1.json"

AUDIT_VERSION = "exercise-data-audit-e1-v1.0.0"
SOURCE_ID = "WGER_EXERCISEINFO"
SOURCE_BASE_URL = "https://wger.de/api/v2"
SOURCE_ENDPOINT = "/exerciseinfo/"
SNAPSHOT_QUERY = "format=json&language=2&limit=100"
LIVE_OBSERVED_AT = "2026-08-30"
LIVE_SCHEMA_VERSION = "2.7.0a2"
LIVE_EXERCISE_COUNT = 862
ENGLISH_LANGUAGE_ID = 2


class ExerciseDataAuditError(ValueError):
    """Raised when the frozen E1 audit identity no longer matches local data."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_rows(path: Path = BACKEND_SNAPSHOT) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExerciseDataAuditError(f"INVALID_WGER_SNAPSHOT:{path.name}") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ExerciseDataAuditError(f"INVALID_WGER_SNAPSHOT_SHAPE:{path.name}")
    return payload


def _coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    count = sum(bool(row.get(field)) for row in rows)
    return {"count": count, "percent": round(count * 100.0 / len(rows), 2)}


def _english_translation(row: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in row.get("translations") or []
            if isinstance(item, dict) and item.get("language") == ENGLISH_LANGUAGE_ID
        ),
        None,
    )


def snapshot_statistics(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = rows if rows is not None else _read_rows()
    if not records:
        raise ExerciseDataAuditError("EMPTY_WGER_SNAPSHOT")
    ids = [row.get("id") for row in records]
    uuids = [row.get("uuid") for row in records]
    english = [_english_translation(row) for row in records]
    licenses = Counter(
        (
            str((row.get("license") or {}).get("short_name") or "UNKNOWN"),
            str((row.get("license") or {}).get("url") or ""),
        )
        for row in records
    )
    categories = Counter(
        str((row.get("category") or {}).get("name") or "UNKNOWN") for row in records
    )
    equipment = Counter(
        str(item.get("name") or "UNKNOWN")
        for row in records
        for item in row.get("equipment") or []
        if isinstance(item, dict)
    )
    languages = Counter(
        str(item.get("language"))
        for row in records
        for item in row.get("translations") or []
        if isinstance(item, dict)
    )
    translations = [
        item
        for row in records
        for item in row.get("translations") or []
        if isinstance(item, dict)
    ]
    images = [
        item
        for row in records
        for item in row.get("images") or []
        if isinstance(item, dict)
    ]
    videos = [
        item
        for row in records
        for item in row.get("videos") or []
        if isinstance(item, dict)
    ]
    return {
        "record_count": len(records),
        "unique_id_count": len(set(ids)),
        "unique_uuid_count": len(set(uuids)),
        "duplicate_id_count": len(ids) - len(set(ids)),
        "duplicate_uuid_count": len(uuids) - len(set(uuids)),
        "top_level_fields": sorted({key for row in records for key in row}),
        "field_coverage": {
            field: _coverage(records, field)
            for field in (
                "category",
                "equipment",
                "muscles",
                "muscles_secondary",
                "images",
                "videos",
                "license",
                "license_author",
                "translations",
                "variation_group",
                "author_history",
                "total_authors_history",
            )
        },
        "english_translation": {
            "language_id": ENGLISH_LANGUAGE_ID,
            "records": sum(item is not None for item in english),
            "name_present": sum(bool((item or {}).get("name", "").strip()) for item in english),
            "description_present": sum(
                bool((item or {}).get("description", "").strip()) for item in english
            ),
            "note": "The source still returns nested translations in multiple languages; language=2 does not flatten the payload.",
        },
        "category_counts": dict(sorted(categories.items())),
        "equipment_counts": dict(sorted(equipment.items())),
        "translation_language_counts": dict(sorted(languages.items(), key=lambda item: int(item[0]))),
        "license_counts": [
            {"short_name": name, "url": url, "count": count}
            for (name, url), count in sorted(licenses.items())
        ],
        "nested_content_provenance": {
            "translation_count": len(translations),
            "translations_with_license": sum(item.get("license") is not None for item in translations),
            "translations_with_license_author": sum(bool(item.get("license_author")) for item in translations),
            "image_count": len(images),
            "images_with_license": sum(item.get("license") is not None for item in images),
            "images_with_license_author": sum(bool(item.get("license_author")) for item in images),
            "images_marked_ai_generated": sum(item.get("is_ai_generated") is True for item in images),
            "video_count": len(videos),
            "videos_with_license": sum(item.get("license") is not None for item in videos),
            "videos_with_license_author": sum(bool(item.get("license_author")) for item in videos),
            "finding": "License and author metadata exist at exercise, translation and media levels and must be preserved separately.",
        },
        "created_range": {
            "minimum": min(str(row.get("created")) for row in records),
            "maximum": max(str(row.get("created")) for row in records),
        },
        "last_update_global_range": {
            "minimum": min(str(row.get("last_update_global")) for row in records),
            "maximum": max(str(row.get("last_update_global")) for row in records),
        },
    }


def agent_path_statistics(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = rows if rows is not None else _read_rows()
    raw_by_id = {int(row["id"]): row for row in records}
    agent_ids = {record.id for record in workout._EXERCISES}
    excluded = []
    for exercise_id in sorted(set(raw_by_id) - agent_ids):
        translation = _english_translation(raw_by_id[exercise_id]) or {}
        excluded.append({"source_exercise_id": exercise_id, "name": translation.get("name")})
    return {
        "bundled_rows_loaded_at_import": len(workout._EXERCISES),
        "agent_record_fields": list(workout._ExerciseRecord.__annotations__),
        "excluded_rows": excluded,
        "category_counts": dict(
            sorted(Counter(record.category for record in workout._EXERCISES).items())
        ),
        "derived_level_counts": dict(
            sorted(Counter(record.derived_level for record in workout._EXERCISES).items())
        ),
        "bodyweight_count": sum(record.is_bodyweight for record in workout._EXERCISES),
        "empty_equipment_count": sum(not record.equipment for record in workout._EXERCISES),
        "selection_inputs": [
            "category",
            "normalized_or_name_inferred_equipment",
            "name_heuristic_difficulty",
            "requested_muscle_group",
            "requested_duration",
            "requested_level",
            "requested_goal",
            "fatigue_level_if_supplied",
        ],
        "source_fields_not_retained_by_agent": [
            "uuid",
            "muscles",
            "muscles_secondary",
            "translations.description",
            "images",
            "videos",
            "license",
            "license_author",
            "variation_group",
            "created",
            "last_update_global",
        ],
        "profile_fields_auto_injected_by_dispatcher": ["weight_kg", "health_goal_as_goal"],
        "training_history_used_by_suggest_workout": False,
        "live_wger_used_by_suggest_workout": False,
        "exercise_duration_model": "FIXED_5_MINUTES_PER_EXERCISE",
        "selection_tie_break": "CATEGORY_ROUND_ROBIN_THEN_ASCENDING_WGER_ID",
    }


def current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ExerciseDataAuditError("GIT_COMMIT_UNAVAILABLE") from exc


def build_audit_manifest(*, git_commit: str | None = None) -> dict[str, Any]:
    rows = _read_rows()
    backend_hash = file_sha256(BACKEND_SNAPSHOT)
    mobile_hash = file_sha256(MOBILE_SNAPSHOT)
    manifest = {
        "schema_version": AUDIT_VERSION,
        "git_commit": git_commit or current_git_commit(),
        "scope": "E1_WGER_AND_EXERCISE_DATA_AUDIT_ONLY",
        "source": {
            "source_id": SOURCE_ID,
            "publisher": "wger project",
            "base_url": SOURCE_BASE_URL,
            "snapshot_endpoint": SOURCE_ENDPOINT,
            "snapshot_query": SNAPSHOT_QUERY,
            "source_code_license": "AGPL-3.0-or-later",
            "exercise_data_license_policy": "Creative Commons per individual record",
            "official_api_docs": "https://wger.readthedocs.io/en/latest/api/api.html",
            "official_repository": "https://github.com/wger-project/wger",
        },
        "snapshot": {
            "backend_path": "apps/backend/data/wger_exercises_raw.json",
            "mobile_path": "apps/mobile/assets/data/wger_exercises_raw.json",
            "backend_sha256": backend_hash,
            "mobile_sha256": mobile_hash,
            "byte_identical": backend_hash == mobile_hash,
            "fetch_script_sha256": file_sha256(FETCH_SCRIPT),
            "fetch_has_snapshot_manifest": False,
            "statistics": snapshot_statistics(rows),
        },
        "live_api_observation": {
            "observed_at": LIVE_OBSERVED_AT,
            "openapi_schema_version": LIVE_SCHEMA_VERSION,
            "exerciseinfo_count": LIVE_EXERCISE_COUNT,
            "exerciseinfo_list_status": 200,
            "exercise_search_status": 404,
            "exerciseinfo_in_openapi": True,
            "exercise_search_in_openapi": False,
            "finding": "The local /wger/search/exercise proxy targets a removed upstream endpoint.",
            "volatile_not_used_for_local_manifest_verification": True,
        },
        "local_api_paths": {
            "snapshot_fetch": "GET https://wger.de/api/v2/exerciseinfo/ with pagination",
            "backend_detail_proxy": "GET /wger/exercise/{id} -> /api/v2/exerciseinfo/{id}/",
            "backend_list_proxy": "GET /wger/exercises -> /api/v2/exerciseinfo/",
            "backend_search_proxy": "GET /wger/search/exercise -> /api/v2/exercise/search/ (UPSTREAM_REMOVED)",
            "mobile_catalog_default": "bundled asset via LocalExerciseService/WgerCacheService",
            "mobile_live_service": "backend /wger proxy; present but not the default agent catalog",
            "media_cache": "backend in-memory bounded LRU; Cache-Control max-age=86400",
        },
        "agent_path": agent_path_statistics(rows),
        "workout_log_contract": {
            "persisted_fields": [
                "id",
                "userId",
                "name",
                "exerciseTemplateId",
                "date",
                "duration",
                "caloriesBurned",
                "type",
                "intensity",
                "isCompleted",
                "timeOfDay",
            ],
            "chat_today_fields": ["name", "type", "duration_min", "calories_burned"],
            "chat_range_fields": [
                "date",
                "name",
                "duration_min",
                "calories_burned",
                "type",
                "intensity",
            ],
            "missing_for_adaptation": [
                "canonical_exercise_id",
                "per_set_load_kg",
                "per_set_reps",
                "per_set_rpe_or_rir",
                "per_set_completion",
                "pain_or_discomfort",
                "session_rpe",
                "completion_status_with_partial_state",
            ],
        },
        "context_planner_finding": {
            "intent": "WORKOUT_RECOMMENDATION",
            "required_slots": ["PROFILE", "TODAY_EXERCISE"],
            "optional_slots": ["EXERCISE_HISTORY", "LIFESTYLE", "ACTIVE_PLAN"],
            "allowed_tools": ["get_user_profile", "get_today_exercises", "suggest_workout"],
            "history_fetch_tool_allowed": False,
            "consequence": "The agent cannot deterministically retrieve 7/28-day training history for this intent.",
        },
        "energy_finding": {
            "wger_energy_values_used": False,
            "current_method": "Name/category heuristics assign an activity MET, then MET*3.5*kg/200*minutes.",
            "current_granularity": "Per exercise using a fixed five-minute duration",
            "limitation": "The MET mapping is app-curated and not linked to Compendium activity codes per record.",
            "recommended_boundary": "Use session/activity-level Compendium codes; label output estimated_energy_expenditure.",
        },
        "e1_gaps": [
            "No canonical exercise ID/versioned catalog or record-level provenance in agent output.",
            "No source snapshot timestamp/version/output manifest is written by the fetch script.",
            "No movement pattern, substitution group or curated-field provenance.",
            "Primary and secondary muscle metadata are discarded before recommendation.",
            "Difficulty is inferred from equipment/name without a versioned exercise policy.",
            "Training history is not consumed by suggest_workout.",
            "Workout logs lack set-level load, reps, effort, completion and pain.",
            "One local live-search proxy targets an upstream endpoint removed in Wger 2.5.",
            "Bundled snapshot has 885 rows while the live API observation has 862; deletions/merges are not reconciled.",
        ],
        "research_identity": research_identity(),
        "next_phase": {
            "phase": "E2_CANONICAL_EXERCISE_CATALOG",
            "entry_gate": "Review this E1 manifest before changing production recommendation behavior.",
            "must_preserve": [
                "per-record Wger license and author metadata",
                "source ID/UUID and snapshot hash",
                "Wger-supplied fields versus app-curated fields",
                "offline-v1-636 research identity",
            ],
        },
    }
    manifest["manifest_hash"] = content_sha256(manifest)
    return manifest


def verify_audit_manifest(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        expected = manifest or json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExerciseDataAuditError("INVALID_E1_MANIFEST") from exc
    actual = build_audit_manifest(git_commit=expected["git_commit"])
    if actual != expected:
        differing = sorted(
            key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)
        )
        raise ExerciseDataAuditError(f"E1_MANIFEST_MISMATCH:{','.join(differing)}")
    return {
        "ok": True,
        "audit_version": expected["schema_version"],
        "snapshot_records": expected["snapshot"]["statistics"]["record_count"],
        "agent_records": expected["agent_path"]["bundled_rows_loaded_at_import"],
        "research_corpus": expected["research_identity"]["corpus_version"],
    }


__all__ = [
    "AUDIT_VERSION",
    "BACKEND_SNAPSHOT",
    "MANIFEST_FILE",
    "MOBILE_SNAPSHOT",
    "ExerciseDataAuditError",
    "agent_path_statistics",
    "build_audit_manifest",
    "content_sha256",
    "file_sha256",
    "snapshot_statistics",
    "verify_audit_manifest",
]
