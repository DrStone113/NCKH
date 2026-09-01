"""Offline-first canonical exercise catalog derived from the frozen Wger snapshot.

Wger remains the source of exercise facts.  App-derived movement, difficulty,
laterality and substitution metadata are deliberately labelled as curated
rules, and missing source facts stay missing instead of being invented.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import unicodedata
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from modules.nutrition.catalog_ingestion import research_identity


BACKEND_DIR = Path(__file__).resolve().parents[2]
# The Docker development image mounts the backend directly at ``/app`` while
# the local checkout places it at ``<repo>/apps/backend``.  Keep manifest
# provenance best-effort in the former layout instead of failing at import.
REPO_ROOT = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR
SOURCE_SNAPSHOT = BACKEND_DIR / "data" / "wger_exercises_raw.json"
E1_MANIFEST_FILE = BACKEND_DIR / "data" / "exercise_data_audit_e1_v1.json"
MANIFEST_FILE = BACKEND_DIR / "data" / "canonical_exercise_catalog_manifest_v1.json"

CATALOG_VERSION = "canonical-exercise-v1.0.0"
CURATION_POLICY_VERSION = "exercise-curation-rules-v1.0.0"
SOURCE_ID = "WGER"
SOURCE_ENDPOINT = "https://wger.de/api/v2/exerciseinfo/"
ENGLISH_LANGUAGE_ID = 2
OBSERVED_OPENAPI_VERSION = "2.7.0a2"


class CanonicalExerciseError(ValueError):
    """Raised when the source or frozen E2 catalog identity is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ascii_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char))
        .casefold()
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )


def _plain_text(source_html: str) -> str:
    text = re.sub(r"(?i)<\s*(br|/p|/li|/div)\s*/?>", "\n", source_html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_rows(path: Path = SOURCE_SNAPSHOT) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalExerciseError(f"INVALID_WGER_SNAPSHOT:{path.name}") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise CanonicalExerciseError("INVALID_WGER_SNAPSHOT_SHAPE")
    if not payload:
        raise CanonicalExerciseError("EMPTY_WGER_SNAPSHOT")
    return payload


def _english_translation(row: dict[str, Any]) -> dict[str, Any]:
    translation = next(
        (
            item
            for item in row.get("translations") or []
            if isinstance(item, dict) and item.get("language") == ENGLISH_LANGUAGE_ID
        ),
        None,
    )
    if not translation or not str(translation.get("name") or "").strip():
        raise CanonicalExerciseError(
            f"MISSING_ENGLISH_TRANSLATION:{row.get('id', 'UNKNOWN')}"
        )
    return translation


def _rule_result(
    value: str | None,
    *,
    rule_id: str,
    confidence: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "provenance": "APP_CURATED_RULE",
        "policy_version": CURATION_POLICY_VERSION,
        "rule_id": rule_id,
        "confidence": confidence,
        "rationale": rationale,
        "human_reviewed": False,
    }


_MOVEMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CARRY", ("farmer walk", "farmers walk", "suitcase carry", "loaded carry", " carry")),
    ("VERTICAL_PULL", ("pull up", "pullup", "chin up", "chinup", "lat pull", "pulldown")),
    ("VERTICAL_PUSH", ("overhead press", "shoulder press", "military press", "arnold press", "handstand push")),
    ("HORIZONTAL_PULL", (" row", "row ", "rowing", "reverse fly", "rear delt fly")),
    ("HORIZONTAL_PUSH", ("bench press", "chest press", "push up", "pushup", "chest fly", "pec deck", "dip")),
    ("HINGE", ("deadlift", "good morning", "hip thrust", "glute bridge", "pull through", "kettlebell swing")),
    ("SQUAT", ("squat", "leg press", "lunge", "split squat", "step up")),
    ("CORE_ANTI_ROTATION", ("pallof", "anti rotation", "antirotation")),
    ("CORE_ANTI_EXTENSION", ("plank", "ab wheel", "body saw", "dead bug")),
    ("CORE_FLEXION", ("crunch", "sit up", "situp", "leg raise", "knee raise", "jackknife")),
    ("ELBOW_FLEXION", ("curl", "biceps")),
    ("ELBOW_EXTENSION", ("tricep", "triceps", "skull crusher")),
    ("SHOULDER_ISOLATION", ("lateral raise", "front raise", "shoulder raise", "face pull")),
    ("KNEE_EXTENSION", ("leg extension", "knee extension")),
    ("KNEE_FLEXION", ("leg curl", "hamstring curl", "knee curl")),
    ("HIP_ABDUCTION", ("hip abduction", "abductor")),
    ("HIP_ADDUCTION", ("hip adduction", "adductor")),
    ("CALF_RAISE", ("calf raise", "heel raise")),
    ("MOBILITY", ("stretch", "mobility", "meditation", "foam roll", "yoga")),
    ("LOCOMOTION", ("walking", "running", "jogging", "sprint", "stairs", "jump rope", "burpee", "crawling")),
)


def derive_movement_pattern(name: str, category: str) -> dict[str, Any]:
    key = f" {_ascii_key(name)} "
    for movement, signals in _MOVEMENT_RULES:
        if any(signal in key for signal in signals):
            return _rule_result(
                movement,
                rule_id=f"MOVEMENT_NAME_{movement}",
                confidence="MEDIUM",
                rationale="Matched a versioned English-name movement signal.",
            )
    if category.casefold() == "cardio":
        return _rule_result(
            "CARDIO_OTHER",
            rule_id="MOVEMENT_CATEGORY_CARDIO_FALLBACK",
            confidence="LOW",
            rationale="Wger category is Cardio but the movement was not more specific.",
        )
    return _rule_result(
        "UNKNOWN",
        rule_id="MOVEMENT_NO_RULE_MATCH",
        confidence="NONE",
        rationale="No reviewed rule matched; the source does not provide movement pattern.",
    )


def derive_difficulty(name: str) -> dict[str, Any]:
    key = f" {_ascii_key(name)} "
    advanced = (
        "muscle up",
        "planche",
        "front lever",
        "back lever",
        "dragon flag",
        "pistol squat",
        "one arm pull",
        "one arm push",
        "handstand push",
        "clean and jerk",
        " snatch ",
    )
    beginner = ("beginner", "assisted", "wall push", "chair squat", "box squat")
    if any(signal in key for signal in advanced):
        return _rule_result(
            "ADVANCED",
            rule_id="DIFFICULTY_EXPLICIT_ADVANCED_NAME",
            confidence="MEDIUM",
            rationale="The exercise name contains a versioned high-skill signal.",
        )
    if any(signal in key for signal in beginner):
        return _rule_result(
            "BEGINNER",
            rule_id="DIFFICULTY_EXPLICIT_SCALED_NAME",
            confidence="MEDIUM",
            rationale="The exercise name explicitly signals a scaled or beginner variation.",
        )
    return _rule_result(
        "UNSPECIFIED",
        rule_id="DIFFICULTY_NOT_IN_WGER_SOURCE",
        confidence="NONE",
        rationale="Difficulty is not supplied by Wger and cannot be inferred safely.",
    )


def derive_laterality(name: str) -> dict[str, Any]:
    key = f" {_ascii_key(name)} "
    unilateral = (
        "single arm",
        "single leg",
        "one arm",
        "one leg",
        "unilateral",
        "alternating",
        "bulgarian",
        "split squat",
        "lunge",
    )
    bilateral = ("bilateral", "two arm", "two leg")
    if any(signal in key for signal in unilateral):
        return _rule_result(
            "UNILATERAL",
            rule_id="LATERALITY_EXPLICIT_UNILATERAL_NAME",
            confidence="MEDIUM",
            rationale="The exercise name contains a unilateral signal.",
        )
    if any(signal in key for signal in bilateral):
        return _rule_result(
            "BILATERAL",
            rule_id="LATERALITY_EXPLICIT_BILATERAL_NAME",
            confidence="MEDIUM",
            rationale="The exercise name contains a bilateral signal.",
        )
    return _rule_result(
        "UNSPECIFIED",
        rule_id="LATERALITY_NOT_IN_WGER_SOURCE",
        confidence="NONE",
        rationale="Laterality is not supplied by Wger and the name is not explicit.",
    )


def _source_object(item: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(item)


def _media_item(item: dict[str, Any], *, kind: str) -> dict[str, Any]:
    common = {
        "id": item.get("id"),
        "uuid": item.get("uuid"),
        "url": item.get("image" if kind == "IMAGE" else "video"),
        "is_main": item.get("is_main"),
        "license_metadata": {
            "license_id": item.get("license"),
            "license_title": item.get("license_title"),
            "license_author": item.get("license_author"),
            "license_author_url": item.get("license_author_url"),
            "license_object_url": item.get("license_object_url"),
            "license_derivative_source_url": item.get("license_derivative_source_url"),
            "author_history": deepcopy(item.get("author_history") or []),
        },
    }
    if kind == "IMAGE":
        common.update(
            {
                "style": item.get("style"),
                "is_ai_generated": item.get("is_ai_generated"),
            }
        )
    else:
        common.update(
            {
                "duration_seconds": item.get("duration"),
                "width": item.get("width"),
                "height": item.get("height"),
                "codec": item.get("codec"),
                "size_bytes": item.get("size"),
            }
        )
    return common


def _substitution_group(
    movement_pattern: dict[str, Any], primary_muscles: list[dict[str, Any]]
) -> dict[str, Any]:
    movement = movement_pattern["value"]
    muscle_ids = sorted(int(item["id"]) for item in primary_muscles)
    if movement == "UNKNOWN" or not muscle_ids:
        return _rule_result(
            None,
            rule_id="SUBSTITUTION_INSUFFICIENT_METADATA",
            confidence="NONE",
            rationale="A movement pattern and at least one primary muscle are required.",
        )
    return _rule_result(
        f"{movement}:PRIMARY:{'-'.join(str(item) for item in muscle_ids)}",
        rule_id="SUBSTITUTION_MOVEMENT_AND_PRIMARY_MUSCLE",
        confidence="MEDIUM",
        rationale="Grouped by app-curated movement pattern and Wger primary-muscle IDs.",
    )


def normalize_exercise(row: dict[str, Any], *, snapshot_sha256: str) -> dict[str, Any]:
    translation = _english_translation(row)
    name_en = str(translation["name"]).strip()
    category = _source_object(row.get("category") or {})
    primary = [_source_object(item) for item in row.get("muscles") or []]
    secondary = [_source_object(item) for item in row.get("muscles_secondary") or []]
    movement = derive_movement_pattern(name_en, str(category.get("name") or ""))
    difficulty = derive_difficulty(name_en)
    laterality = derive_laterality(name_en)
    substitution = _substitution_group(movement, primary)
    source_html = str(translation.get("description") or "")
    quality_flags: list[str] = ["NAME_VI_MISSING", "LAST_SYNCED_AT_MISSING"]
    if not source_html.strip():
        quality_flags.append("INSTRUCTIONS_MISSING")
    if not primary:
        quality_flags.append("PRIMARY_MUSCLES_MISSING")
    if movement["value"] == "UNKNOWN":
        quality_flags.append("MOVEMENT_PATTERN_REVIEW_REQUIRED")
    if difficulty["value"] == "UNSPECIFIED":
        quality_flags.append("DIFFICULTY_REVIEW_REQUIRED")
    if laterality["value"] == "UNSPECIFIED":
        quality_flags.append("LATERALITY_REVIEW_REQUIRED")
    if substitution["value"] is None:
        quality_flags.append("SUBSTITUTION_GROUP_REVIEW_REQUIRED")

    return {
        "exercise_id": f"WGER_EXERCISE_{row['uuid']}",
        "source": SOURCE_ID,
        "source_exercise_id": int(row["id"]),
        "source_uuid": str(row["uuid"]),
        "name_vi": None,
        "name_en": name_en,
        "primary_muscles": primary,
        "secondary_muscles": secondary,
        "movement_pattern": movement,
        "equipment": [_source_object(item) for item in row.get("equipment") or []],
        "category": category,
        "difficulty": difficulty,
        "laterality": laterality,
        "instructions": {
            "language_id": ENGLISH_LANGUAGE_ID,
            "text": _plain_text(source_html),
            "source_html": source_html,
            "aliases": deepcopy(translation.get("aliases") or []),
            "notes": deepcopy(translation.get("notes") or []),
            "source_translation_id": translation.get("id"),
            "source_translation_uuid": translation.get("uuid"),
            "license_metadata": {
                "license_id": translation.get("license"),
                "license_title": translation.get("license_title"),
                "license_author": translation.get("license_author"),
                "license_author_url": translation.get("license_author_url"),
                "license_object_url": translation.get("license_object_url"),
                "license_derivative_source_url": translation.get(
                    "license_derivative_source_url"
                ),
                "author_history": deepcopy(translation.get("author_history") or []),
            },
        },
        "media": {
            "images": [
                _media_item(item, kind="IMAGE") for item in row.get("images") or []
            ],
            "videos": [
                _media_item(item, kind="VIDEO") for item in row.get("videos") or []
            ],
        },
        "substitution_group": substitution,
        "source_version": {
            "source_endpoint": SOURCE_ENDPOINT,
            "snapshot_sha256": snapshot_sha256,
            "observed_openapi_version": OBSERVED_OPENAPI_VERSION,
            "source_created_at": row.get("created"),
            "source_last_update": row.get("last_update"),
            "source_last_update_global": row.get("last_update_global"),
        },
        "source_license_metadata": {
            "license": _source_object(row.get("license") or {}),
            "license_author": row.get("license_author"),
            "author_history": deepcopy(row.get("author_history") or []),
            "total_authors_history": deepcopy(row.get("total_authors_history") or []),
        },
        "last_synced_at": None,
        "review_status": "SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED",
        "quality_flags": sorted(quality_flags),
        "field_provenance": {
            "source_exercise_id": "WGER",
            "source_uuid": "WGER",
            "name_en": "WGER_TRANSLATION_LANGUAGE_2",
            "name_vi": "MISSING_NOT_GENERATED",
            "primary_muscles": "WGER",
            "secondary_muscles": "WGER",
            "equipment": "WGER",
            "category": "WGER",
            "instructions": "WGER_TRANSLATION_LANGUAGE_2",
            "media": "WGER",
            "source_license_metadata": "WGER",
            "movement_pattern": "APP_CURATED_RULE",
            "difficulty": "APP_CURATED_RULE",
            "laterality": "APP_CURATED_RULE",
            "substitution_group": "APP_CURATED_RULE",
            "last_synced_at": "MISSING_NO_SNAPSHOT_MANIFEST",
        },
        "ingestion": {
            "state": "CANONICAL_SOURCE_RECORD",
            "source_stage": "FROZEN_WGER_SNAPSHOT",
            "normalization_policy_version": CATALOG_VERSION,
            "production_recommendation_enabled": False,
        },
    }


def _validate_catalog(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = list(records)
    exercise_ids = [item["exercise_id"] for item in catalog]
    source_ids = [item["source_exercise_id"] for item in catalog]
    source_uuids = [item["source_uuid"] for item in catalog]
    if len(exercise_ids) != len(set(exercise_ids)):
        raise CanonicalExerciseError("DUPLICATE_CANONICAL_EXERCISE_ID")
    if len(source_ids) != len(set(source_ids)):
        raise CanonicalExerciseError("DUPLICATE_WGER_EXERCISE_ID")
    if len(source_uuids) != len(set(source_uuids)):
        raise CanonicalExerciseError("DUPLICATE_WGER_EXERCISE_UUID")
    if any(item["source"] != SOURCE_ID for item in catalog):
        raise CanonicalExerciseError("INVALID_EXERCISE_SOURCE")
    if any(not item["source_license_metadata"]["license"] for item in catalog):
        raise CanonicalExerciseError("MISSING_RECORD_LICENSE")
    return sorted(catalog, key=lambda item: item["source_exercise_id"])


@lru_cache(maxsize=1)
def _load_catalog_cached() -> tuple[dict[str, Any], ...]:
    snapshot_hash = file_sha256(SOURCE_SNAPSHOT)
    records = [
        normalize_exercise(row, snapshot_sha256=snapshot_hash) for row in _read_rows()
    ]
    return tuple(_validate_catalog(records))


def load_canonical_exercise_catalog() -> list[dict[str, Any]]:
    """Return a defensive copy of the deterministic E2 catalog."""

    return deepcopy(list(_load_catalog_cached()))


def clear_canonical_exercise_cache() -> None:
    _load_catalog_cached.cache_clear()


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CanonicalExerciseError("GIT_COMMIT_UNAVAILABLE") from exc


def _qa_summary(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    flags = Counter(flag for item in catalog for flag in item["quality_flags"])
    movements = Counter(item["movement_pattern"]["value"] for item in catalog)
    difficulties = Counter(item["difficulty"]["value"] for item in catalog)
    lateralities = Counter(item["laterality"]["value"] for item in catalog)
    licenses = Counter(
        str(item["source_license_metadata"]["license"].get("short_name") or "UNKNOWN")
        for item in catalog
    )
    return {
        "record_count": len(catalog),
        "name_vi_missing": sum(item["name_vi"] is None for item in catalog),
        "instructions_missing": sum(not item["instructions"]["text"] for item in catalog),
        "primary_muscles_missing": sum(not item["primary_muscles"] for item in catalog),
        "equipment_missing": sum(not item["equipment"] for item in catalog),
        "images_missing": sum(not item["media"]["images"] for item in catalog),
        "videos_missing": sum(not item["media"]["videos"] for item in catalog),
        "last_synced_at_missing": sum(item["last_synced_at"] is None for item in catalog),
        "substitution_group_missing": sum(
            item["substitution_group"]["value"] is None for item in catalog
        ),
        "review_status_counts": dict(
            sorted(Counter(item["review_status"] for item in catalog).items())
        ),
        "quality_flag_counts": dict(sorted(flags.items())),
        "movement_pattern_counts": dict(sorted(movements.items())),
        "difficulty_counts": dict(sorted(difficulties.items())),
        "laterality_counts": dict(sorted(lateralities.items())),
        "license_counts": dict(sorted(licenses.items())),
    }


def build_catalog_manifest(*, git_commit: str | None = None) -> dict[str, Any]:
    catalog = load_canonical_exercise_catalog()
    source_hash = file_sha256(SOURCE_SNAPSHOT)
    try:
        e1 = json.loads(E1_MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalExerciseError("INVALID_E1_MANIFEST") from exc
    manifest = {
        "schema_version": CATALOG_VERSION,
        "git_commit": git_commit or _current_git_commit(),
        "scope": "E2_CANONICAL_EXERCISE_CATALOG_ONLY",
        "source": {
            "source_id": SOURCE_ID,
            "publisher": "wger project",
            "endpoint": SOURCE_ENDPOINT,
            "snapshot_path": "apps/backend/data/wger_exercises_raw.json",
            "snapshot_sha256": source_hash,
            "snapshot_record_count": len(_read_rows()),
            "source_code_license": "AGPL-3.0-or-later",
            "exercise_data_license_policy": "Creative Commons per individual record",
            "observed_openapi_version": OBSERVED_OPENAPI_VERSION,
            "last_synced_at": None,
            "last_synced_at_finding": "The legacy snapshot fetch did not write a sync manifest; filesystem timestamps are not treated as source provenance.",
        },
        "catalog": {
            "record_count": len(catalog),
            "content_sha256": content_sha256(catalog),
            "runtime_materialization": "DETERMINISTIC_FROM_FROZEN_SOURCE_SNAPSHOT",
            "production_recommendation_enabled": False,
        },
        "field_ownership": {
            "WGER": [
                "source_exercise_id",
                "source_uuid",
                "name_en",
                "primary_muscles",
                "secondary_muscles",
                "equipment",
                "category",
                "instructions",
                "media",
                "source_license_metadata",
            ],
            "APP_CURATED_RULE": [
                "movement_pattern",
                "difficulty",
                "laterality",
                "substitution_group",
            ],
            "MISSING_NOT_GENERATED": ["name_vi", "last_synced_at"],
        },
        "curation_policy": {
            "version": CURATION_POLICY_VERSION,
            "human_reviewed": False,
            "unknown_values_are_preserved": True,
            "rule_outputs_are_not_wger_facts": True,
        },
        "qa": _qa_summary(catalog),
        "e1_baseline": {
            "schema_version": e1.get("schema_version"),
            "manifest_hash": e1.get("manifest_hash"),
            "file_sha256": file_sha256(E1_MANIFEST_FILE),
            "expected_source_snapshot_sha256": e1.get("snapshot", {}).get(
                "backend_sha256"
            ),
            "unchanged": e1.get("snapshot", {}).get("backend_sha256") == source_hash,
        },
        "research_identity": research_identity(),
        "phase_boundary": {
            "current": "E2_CANONICAL_EXERCISE_CATALOG",
            "not_implemented": [
                "exercise prescription policy",
                "personalized workout planner",
                "progression engine",
                "chatbot catalog integration",
            ],
            "next": "E3_VERSIONED_EXERCISE_PRESCRIPTION_POLICY",
        },
    }
    manifest["manifest_hash"] = content_sha256(manifest)
    return manifest


def verify_catalog_manifest(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        expected = manifest or json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalExerciseError("INVALID_E2_MANIFEST") from exc
    actual = build_catalog_manifest(git_commit=expected["git_commit"])
    if actual != expected:
        differing = sorted(
            key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)
        )
        raise CanonicalExerciseError(f"E2_MANIFEST_MISMATCH:{','.join(differing)}")
    return {
        "ok": True,
        "catalog_version": expected["schema_version"],
        "records": expected["catalog"]["record_count"],
        "catalog_sha256": expected["catalog"]["content_sha256"],
        "review_required": expected["qa"]["review_status_counts"].get(
            "SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED", 0
        ),
        "research_corpus": expected["research_identity"]["corpus_version"],
    }


__all__ = [
    "CATALOG_VERSION",
    "CURATION_POLICY_VERSION",
    "MANIFEST_FILE",
    "SOURCE_SNAPSHOT",
    "CanonicalExerciseError",
    "build_catalog_manifest",
    "canonical_json_bytes",
    "clear_canonical_exercise_cache",
    "content_sha256",
    "derive_difficulty",
    "derive_laterality",
    "derive_movement_pattern",
    "file_sha256",
    "load_canonical_exercise_catalog",
    "normalize_exercise",
    "verify_catalog_manifest",
]
