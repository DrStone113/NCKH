"""Fail-closed preflight for Plan V2 scored acceptance.

This script verifies qualification artefacts only.  It never calls a Plan V2
tool, comparator, scheduler, nutrition planner, database, or chatbot.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"CANNOT_LOAD:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _template_signature(normalized: str) -> str:
    value = re.sub(r"\b\d{4}\s+\d{1,2}\s+\d{1,2}\b", " DATE ", normalized)
    value = re.sub(r"\b\d{1,2}\s+\d{1,2}\s+\d{4}\b", " DATE ", value)
    value = re.sub(r"\b\d{1,2}\s+\d{1,2}\b", " TIME_OR_DATE ", value)
    value = re.sub(r"\b\d+\b", " NUMBER ", value)
    entities = {
        "me", "lac", "dau", "nan", "sua", "trung", "thit", "ca", "tom", "bo",
        "ta", "tham", "day", "ghe", "xe", "gym", "cong", "nha", "khach", "san",
        "thu", "hai", "ba", "tu", "nam", "sau", "bay", "chu", "nhat",
    }
    return " ".join("ENTITY" if token in entities else token for token in value.split())


def _jaccard(left: str, right: str) -> tuple[float, int]:
    stop = {"toi", "hay", "cho", "va", "la", "mot", "cua", "khong", "duoc", "ke", "hoach", "ngay", "tuan"}
    a = {token for token in left.split() if token not in stop}
    b = {token for token in right.split() if token not in stop}
    common = len(a & b)
    return (common / len(a | b) if a | b else 0.0), common


def _flutter_versions(executable: str | None) -> tuple[str | None, str | None, str | None]:
    if not executable:
        return None, None, None
    try:
        flutter = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=60, check=True)
        dart = Path(executable).with_name("dart.bat" if executable.lower().endswith(".bat") else "dart")
        dart_run = subprocess.run([str(dart), "--version"], capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, None, str(exc)
    flutter_match = re.search(r"Flutter\s+(\d+\.\d+\.\d+)", flutter.stdout + flutter.stderr)
    dart_match = re.search(r"Dart SDK version:\s*(\d+\.\d+\.\d+)", dart_run.stdout + dart_run.stderr)
    return (flutter_match.group(1) if flutter_match else None, dart_match.group(1) if dart_match else None, None)


def evaluate(flutter_executable: str | None) -> dict[str, Any]:
    status_v1 = _load_json("acceptance-v1-qualification-status.json")
    inventory = _load_json("p1-development-v2-inventory.json")
    protocol = _load_json("dedup-protocol-v1.json")
    candidate_manifest = _load_json("acceptance-v2-candidate-manifest-v1.json")
    oracle = _load_json("acceptance-v2-oracle-candidate-v1.json")
    thresholds = _load_json("acceptance-thresholds-v1.json")
    freeze = _load_json("implementation-freeze-p2-1r-v1.json")
    index = _load_json("development-exclusion-index-v1.json")
    candidates_module = _load_module("plan_v2_candidates", VALIDATION / "qualification_candidates_v2.py")
    index_module = _load_module("plan_v2_exclusion_builder", ROOT / "scripts" / "build_plan_v2_exclusion_index.py")
    candidates = candidates_module.candidate_rows()
    rebuilt_index = index_module.build_index()
    normalized = index_module.normalize_text
    sys.path.insert(0, str(ROOT))
    from services.plan_engine.development_scenarios import development_scenarios
    current_scenario_ids = [scenario.scenario_id for scenario in development_scenarios()]
    proposed = [row for row in candidates if row["proposed_disposition"] == "ACCEPT_AFTER_HUMAN_REVIEW"]
    candidate_normalized = [normalized(str(row["prompt"])) for row in proposed]
    exact_duplicates = len(candidate_normalized) - len(set(candidate_normalized))
    template_counts = Counter(_template_signature(value) for value in candidate_normalized)
    template_duplicates = sum(count - 1 for count in template_counts.values() if count > 1)
    exclusion_texts = [record for record in index["records"] if record["normalized_text"]]
    exact_overlaps: list[dict[str, str]] = []
    template_overlaps: list[dict[str, str]] = []
    semantic_candidates: list[dict[str, Any]] = []
    for row, candidate_text in zip(proposed, candidate_normalized):
        candidate_template = _template_signature(candidate_text)
        for record in exclusion_texts:
            excluded_text = record["normalized_text"]
            if candidate_text == excluded_text:
                exact_overlaps.append({"candidate_id": row["candidate_id"], "exclusion_id": record["stable_id"]})
                continue
            if candidate_template == _template_signature(excluded_text):
                template_overlaps.append({"candidate_id": row["candidate_id"], "exclusion_id": record["stable_id"]})
                continue
            score, common = _jaccard(candidate_text, excluded_text)
            if score >= 0.45 and common >= 3:
                semantic_candidates.append({"candidate_id": row["candidate_id"], "exclusion_id": record["stable_id"], "jaccard": round(score, 3)})
    source_mismatches = {
        relative: {"expected": expected, "actual": _sha(ROOT / relative)}
        for relative, expected in freeze["sources"].items()
        if _sha(ROOT / relative) != expected
    }
    flutter_version, dart_version, flutter_error = _flutter_versions(flutter_executable)
    missing_oracle_profiles = sorted({str(row["oracle_profile"]) for row in proposed} - set(oracle["profiles"]))
    flags = {
        "ACCEPTANCE_V1_STATUS_CONTAMINATED": status_v1["status"] == "CONTAMINATED" and not status_v1["acceptance_eligible"],
        "P1_DEVELOPMENT_CASE_COUNT": inventory["actual_count"] == 106 and inventory["scenario_ids"] == current_scenario_ids,
        "EXCLUSION_INDEX_CURRENT": index["canonical_records_sha256"] == rebuilt_index["canonical_records_sha256"],
        "DEDUP_PROTOCOL_FROZEN": protocol["frozen_before_candidate_review"],
        "THRESHOLDS_FROZEN": thresholds["frozen_before_scored_execution"],
        "CANDIDATE_COUNT_SUFFICIENT": len(candidates) >= 150 and len(proposed) >= 120,
        "CANDIDATE_UNIQUE": len({row["prompt"] for row in candidates}) == len(candidates) and exact_duplicates == 0,
        "CANDIDATE_ORACLE_COMPLETE": not missing_oracle_profiles,
        "NO_CONFIRMED_DEVELOPMENT_OVERLAP": len(exact_overlaps) == 0,
        "NO_TEMPLATE_DEVELOPMENT_OVERLAP": len(template_overlaps) == 0,
        "TOOLCHAIN_BASELINE_VERIFIED": flutter_version == "3.44.8" and dart_version == "3.12.2",
        "ORACLE_FROZEN": oracle["review_status"] == "HUMAN_REVIEWED" and oracle["status"] == "FROZEN",
        "HOLDOUT_V2_FROZEN": candidate_manifest["status"] == "FROZEN" and all(row["acceptance_eligible"] for row in proposed),
        "IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE": not source_mismatches,
    }
    ready = all(flags.values()) and not semantic_candidates
    return {
        "flags": flags,
        "READY_TO_RUN_P2_1_ACCEPTANCE": ready,
        "diagnostics": {
            "flutter_executable": flutter_executable,
            "flutter_version": flutter_version,
            "dart_version": dart_version,
            "flutter_error": flutter_error,
            "candidate_count": len(candidates),
            "proposed_acceptance_count": len(proposed),
            "candidate_unique_count": len({row["prompt"] for row in candidates}),
            "proposed_area_counts": dict(Counter(row["area"] for row in proposed)),
            "candidate_source_hash_matches_manifest": _sha(VALIDATION / "qualification_candidates_v2.py") == candidate_manifest["candidate_source_sha256"],
            "missing_oracle_profiles": missing_oracle_profiles,
            "exact_duplicate_count": exact_duplicates,
            "template_duplicate_count": template_duplicates,
            "confirmed_development_overlap_count": len(exact_overlaps),
            "template_development_overlap_count": len(template_overlaps),
            "semantic_candidate_count": len(semantic_candidates),
            "semantic_candidate_samples": semantic_candidates[:10],
            "source_mismatches": source_mismatches,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter", help="Pinned Flutter executable; global PATH is intentionally not used.")
    parser.add_argument("--require-ready", action="store_true", help="Exit non-zero unless every hard qualification gate is green.")
    args = parser.parse_args()
    result = evaluate(args.flutter)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not args.require_ready or result["READY_TO_RUN_P2_1_ACCEPTANCE"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
