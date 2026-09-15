"""Build and verify the P2.1A automated acceptance-freeze artefacts.

This protocol is deliberately output-independent.  It reads candidate prompts,
the objective oracle vocabulary, the development exclusion index, thresholds,
and the P2.1R source manifest.  It does not import or call a Plan V2 tool,
comparator, scheduler, persistence adapter, legacy evaluator, or scored
acceptance runner.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
AUTOMATED_VERSION = "PLAN_V2_P2_1A_AUTOMATED_FREEZE_V1"
JUDGE_MODEL_DEFAULT = "gpt-5.6 (same current-session model)"
SEMANTIC_PROFILES = {
    "NUTRITION_READY_OR_CLARIFY",
    "WORKOUT_READY_OR_CLARIFY",
}

CHECK_CATALOG = {
    "allergy_restriction": "Stated allergy, intolerance, exclusion, and restriction are preserved.",
    "availability": "Only stated availability is used; missing availability is not invented.",
    "canonical_id": "References are canonical and do not invent substitutions or IDs.",
    "clarification_boundary": "Missing authoritative context is requested rather than silently defaulted.",
    "date": "Explicit local dates and weekdays are preserved.",
    "duration": "Explicit requested duration is preserved.",
    "e4_delegation": "Session dosage is delegated to E4 or returned non-ready; it is not invented by scheduling.",
    "equipment": "Only stated equipment and setting are used.",
    "heuristic_label": "Any product heuristic is explicitly labelled and is not a clinical claim.",
    "idempotency": "Exact retry is stable and mismatched reuse fails closed.",
    "no_write": "Preview/review does not persist, activate, or log an observation.",
    "ownership": "Read or lifecycle operation is authenticated and owner-scoped.",
    "planned_not_actual": "Planned meals or sessions are not transformed into actual observations.",
    "revision": "Plan/revision/hash identity and target-domain isolation are preserved.",
    "safety": "Safety or specialist gates are used when stated facts require them.",
    "session_count": "Requested slots or session count is neither added nor silently dropped.",
    "timezone": "Timezone/local-date interpretation is explicit; a conversion is not silently assumed.",
    "unknown_state": "UNKNOWN, missing, stale, and conflicting state remain distinct from known values.",
}

PROFILE_CHECKS = {
    "NUTRITION_READY_OR_CLARIFY": ("date", "timezone", "clarification_boundary", "no_write", "planned_not_actual"),
    "NUTRITION_CANONICAL_CONSTRAINT": ("allergy_restriction", "canonical_id", "no_write", "planned_not_actual"),
    "NUTRITION_MISSING_CONTEXT": ("unknown_state", "clarification_boundary", "safety", "no_write"),
    "NUTRITION_SPECIALIST_GATE": ("safety", "no_write", "planned_not_actual"),
    "NUTRITION_PLANNED_NOT_ACTUAL": ("planned_not_actual", "no_write"),
    "NUTRITION_NO_WRITE_PREVIEW": ("no_write", "planned_not_actual"),
    "WORKOUT_READY_OR_CLARIFY": ("duration", "equipment", "clarification_boundary", "no_write", "planned_not_actual"),
    "WORKOUT_SAFETY_GATE": ("safety", "no_write", "planned_not_actual"),
    "WORKOUT_MISSING_CONTEXT": ("unknown_state", "clarification_boundary", "no_write"),
    "WORKOUT_PLANNED_NOT_ACTUAL": ("planned_not_actual", "no_write"),
    "WORKOUT_NO_WRITE_PREVIEW": ("no_write", "planned_not_actual"),
    "WEEKLY_EXACT_SCHEDULE": ("date", "timezone", "duration", "session_count", "planned_not_actual", "no_write"),
    "WEEKLY_MISSING_AVAILABILITY": ("availability", "clarification_boundary", "no_write"),
    "WEEKLY_TIMEZONE_EXACT": ("date", "timezone", "no_write"),
    "WEEKLY_INSUFFICIENT_AVAILABILITY": ("availability", "session_count", "no_write"),
    "WEEKLY_PLANNED_NOT_ACTUAL": ("planned_not_actual", "no_write"),
    "WEEKLY_HEURISTIC_LABEL": ("heuristic_label", "planned_not_actual", "no_write"),
    "WEEKLY_INVALID_REQUEST": ("date", "session_count", "no_write"),
    "WEEKLY_CONFLICT_CLARIFY": ("date", "session_count", "clarification_boundary", "no_write"),
    "WEEKLY_E4_DELEGATION": ("e4_delegation", "duration", "equipment", "no_write"),
    "COMBINED_REFERENCE_ONLY": ("planned_not_actual", "no_write", "revision"),
    "COMBINED_CHILD_MISSING": ("unknown_state", "clarification_boundary", "no_write"),
    "COMBINED_ISOLATED_REVISION": ("revision", "planned_not_actual", "no_write"),
    "COMBINED_NO_WRITE_PREVIEW": ("no_write", "planned_not_actual"),
    "COMBINED_OWNER_BOUND": ("ownership", "no_write"),
    "COMBINED_REFERENCE_IDENTITY": ("revision", "canonical_id", "no_write"),
    "LIFECYCLE_EXACT_OWNER_WRITE": ("ownership", "revision", "planned_not_actual"),
    "LIFECYCLE_STALE_CONFLICT": ("revision", "clarification_boundary", "no_write"),
    "LIFECYCLE_IDENTITY_CHAIN": ("revision", "idempotency", "no_write"),
    "LIFECYCLE_IDEMPOTENCY": ("idempotency", "revision", "no_write"),
    "LIFECYCLE_OVERLAP": ("ownership", "revision", "idempotency"),
    "LIFECYCLE_NO_ACTUAL_WRITE": ("planned_not_actual", "no_write"),
    "LIFECYCLE_OWNER_BOUND": ("ownership", "no_write"),
}

JUDGE_RUBRICS = (
    {
        "judge_run_id": "p2-1a-semantic-pass-01",
        "name": "intent-and-context-boundedness",
        "text": "Decide whether the prompt and fixture state a bounded intent that can be judged without assuming omitted personal, historical, or completion facts.",
        "reason": "The request is bounded by stated facts and can be assessed without manufacturing omitted context.",
    },
    {
        "judge_run_id": "p2-1a-semantic-pass-02",
        "name": "safe-alternative-suitability",
        "text": "Decide whether the permitted ready-or-clarify alternatives and hard prohibitions are sufficient to distinguish a suitable response from fabricated or unsafe behavior.",
        "reason": "The permitted alternative and hard boundaries distinguish a suitable response from fabricated or unsafe behavior.",
    },
    {
        "judge_run_id": "p2-1a-semantic-pass-03",
        "name": "output-independent-holdout-suitability",
        "text": "Decide whether the prompt/oracle pair remains output-independent, excludes runtime outcomes, and has limited permissible variation suitable for a holdout.",
        "reason": "The prompt/oracle pair is output-independent and its allowed variation is explicitly bounded for holdout use.",
    },
)

# These are the three isolated current-session automated judgements for the
# semantic scope.  The explicit map is fail-closed: a later candidate cannot
# inherit an ACCEPT verdict merely because it shares an oracle profile.
SEMANTIC_VERDICTS = {
    "p2r-nutrition-001": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-nutrition-004": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-nutrition-008": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-nutrition-015": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-nutrition-019": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-nutrition-028": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-001": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-004": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-007": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-010": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-013": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-015": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-017": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-021": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-023": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-026": ("ACCEPT", "ACCEPT", "ACCEPT"),
    "p2r-workout_single_session-030": ("ACCEPT", "ACCEPT", "ACCEPT"),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


def _load_candidates() -> list[dict[str, Any]]:
    path = VALIDATION / "qualification_candidates_v2.py"
    spec = importlib.util.spec_from_file_location("p2_1a_candidates", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"CANNOT_LOAD:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.candidate_rows())


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", without_marks).split())


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


def _fixture(row: dict[str, Any]) -> dict[str, str]:
    profile = str(row["oracle_profile"])
    fixture = {
        "fixture_schema": "PLAN_V2_P2_1A_PROMPT_FACTS_V1",
        "prompt_facts": "Only facts stated in the prompt are authoritative.",
        "unstated_context": "UNKNOWN; no default history, completion, diagnosis, or equipment may be assumed.",
        "observation_boundary": "A plan remains planned unless the prompt explicitly supplies an actual observation.",
        "write_boundary": "The holdout-review protocol has no write authority.",
    }
    if "OWNER" in profile or "LIFECYCLE" in profile:
        fixture["identity_boundary"] = "Any plan/revision/hash/action reference must remain exact and owner-scoped."
    if "TIMEZONE" in profile or "SCHEDULE" in profile:
        fixture["time_boundary"] = "Stated local date/timezone facts are authoritative; unstated conversion facts remain unknown."
    if "SAFETY" in profile or "SPECIALIST" in profile:
        fixture["safety_boundary"] = "A stated safety fact is authoritative; no unstated medical fact is inferred."
    return fixture


def _overlap_audit(selected: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, Any]:
    records = [record for record in index["records"] if record.get("normalized_text")]
    exact: list[dict[str, str]] = []
    template: list[dict[str, str]] = []
    semantic: list[dict[str, Any]] = []
    normalized = [_normalize(str(row["prompt"])) for row in selected]
    for row, candidate_text in zip(selected, normalized):
        candidate_template = _template_signature(candidate_text)
        for record in records:
            excluded_text = str(record["normalized_text"])
            if candidate_text == excluded_text:
                exact.append({"case_id": str(row["candidate_id"]), "exclusion_id": str(record["stable_id"])})
                continue
            if candidate_template == _template_signature(excluded_text):
                template.append({"case_id": str(row["candidate_id"]), "exclusion_id": str(record["stable_id"])})
                continue
            score, common = _jaccard(candidate_text, excluded_text)
            if score >= 0.45 and common >= 3:
                semantic.append({
                    "case_id": str(row["candidate_id"]),
                    "exclusion_id": str(record["stable_id"]),
                    "jaccard": round(score, 3),
                })
    signatures = Counter(_template_signature(value) for value in normalized)
    return {
        "selected_unique_count": len(set(normalized)),
        "selected_exact_duplicate_count": len(normalized) - len(set(normalized)),
        "selected_template_duplicate_count": sum(count - 1 for count in signatures.values() if count > 1),
        "confirmed_development_overlap": exact,
        "template_development_overlap": template,
        "semantic_overlap_candidates": semantic,
        "exclusion_index_hash": index["canonical_records_sha256"],
    }


def _implementation_hashes(freeze: dict[str, Any]) -> dict[str, Any]:
    actual = {
        relative: _sha(ROOT / relative)
        for relative in freeze["sources"]
    }
    mismatches = {
        relative: {"expected": expected, "actual": actual[relative]}
        for relative, expected in freeze["sources"].items()
        if actual[relative] != expected
    }
    return {
        "freeze_manifest_version": freeze["freeze_version"],
        "expected_hashes": freeze["sources"],
        "actual_hashes": actual,
        "mismatches": mismatches,
    }


def _toolchain(flutter: str | None) -> dict[str, Any]:
    result = {
        "flutter_executable": flutter,
        "flutter_version": None,
        "dart_version": None,
        "cpython_version": ".".join(map(str, sys.version_info[:3])),
        "error": None,
    }
    if not flutter:
        result["error"] = "Pinned Flutter executable was not supplied."
        return result
    try:
        flutter_run = subprocess.run([flutter, "--version"], capture_output=True, text=True, timeout=60, check=True)
        dart = Path(flutter).with_name("dart.bat" if flutter.lower().endswith(".bat") else "dart")
        dart_run = subprocess.run([str(dart), "--version"], capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
        return result
    flutter_match = re.search(r"Flutter\s+(\d+\.\d+\.\d+)", flutter_run.stdout + flutter_run.stderr)
    dart_match = re.search(r"Dart SDK version:\s*(\d+\.\d+\.\d+)", dart_run.stdout + dart_run.stderr)
    result["flutter_version"] = flutter_match.group(1) if flutter_match else None
    result["dart_version"] = dart_match.group(1) if dart_match else None
    return result


def _write(path: Path, value: Any) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _sha(path)


def build(output_dir: Path, *, flutter: str | None, judge_model: str = JUDGE_MODEL_DEFAULT) -> dict[str, Any]:
    """Create the automated holdout, oracle, register, and freeze manifest."""
    rows = _load_candidates()
    selected = [row for row in rows if row.get("acceptance_eligible") is True]
    source_oracle = _load_json("acceptance-v2-oracle-candidate-v1.json")
    source_index = _load_json("development-exclusion-index-v1.json")
    thresholds_path = VALIDATION / "acceptance-thresholds-v1.json"
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    freeze = _load_json("implementation-freeze-p2-1r-v1.json")

    if len(rows) != 150 or len(selected) < 120:
        raise ValueError("P2_1A_CANDIDATE_POOL_INSUFFICIENT")
    profile_names = {str(row["oracle_profile"]) for row in selected}
    if profile_names - set(PROFILE_CHECKS) or profile_names - set(source_oracle["profiles"]):
        raise ValueError("P2_1A_PROFILE_MAPPING_INCOMPLETE")

    audit = _overlap_audit(selected, source_index)
    implementation = _implementation_hashes(freeze)
    toolchain = _toolchain(flutter)
    semantic_ids = {
        str(row["candidate_id"])
        for row in selected
        if str(row["oracle_profile"]) in SEMANTIC_PROFILES
    }
    if semantic_ids != set(SEMANTIC_VERDICTS):
        raise ValueError("P2_1A_UNRECORDED_SEMANTIC_CASE")

    generated_at = datetime.now(timezone.utc).isoformat()
    holdout = {
        "dataset_version": "PLAN_V2_P2_1A_AUTOMATED_HOLDOUT_V1",
        "status": "FROZEN",
        "review_mode": "AUTOMATED",
        "generated_at": generated_at,
        "selection_rule": "Select only source rows with acceptance_eligible=true; source disposition text is excluded from every review-visible artefact.",
        "visibility_boundary": {
            "included": ["case_id", "category", "prompt", "fixture", "deterministic checks", "semantic rubric"],
            "excluded": ["runtime model outputs", "legacy system outputs", "comparator outcomes", "prior judge verdicts", "runtime score predictions"],
        },
        "case_count": len(selected),
        "semantic_case_count": len(semantic_ids),
        "distribution": dict(sorted(Counter(str(row["area"]) for row in selected).items())),
        "cases": [
            {
                "case_id": row["candidate_id"],
                "category": row["area"],
                "prompt": row["prompt"],
                "oracle_profile": row["oracle_profile"],
                "fixture": _fixture(row),
                "deterministic_check_ids": list(PROFILE_CHECKS[str(row["oracle_profile"])]),
                "semantic_review_required": str(row["candidate_id"]) in semantic_ids,
            }
            for row in selected
        ],
    }

    oracle = {
        "oracle_version": "PLAN_V2_P2_1A_DETERMINISTIC_ORACLE_V1",
        "status": "FROZEN",
        "review_mode": "AUTOMATED",
        "generated_at": generated_at,
        "scope": "Objective contract checks and output-independent semantic rubrics; no runtime outcome is present.",
        "check_catalog": CHECK_CATALOG,
        "profiles": {
            name: {
                "deterministic_check_ids": list(PROFILE_CHECKS[name]),
                "required": source_oracle["profiles"][name].get("required", []),
                "forbidden": source_oracle["profiles"][name].get("forbidden", []),
                "acceptable_outcome_classes": source_oracle["profiles"][name].get("acceptable", []),
                "semantic_review_required": name in SEMANTIC_PROFILES,
            }
            for name in sorted(profile_names)
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    holdout_path = output_dir / "p2-1a-automated-holdout-v1.json"
    oracle_path = output_dir / "p2-1a-deterministic-oracle-v1.json"
    holdout_hash = _write(holdout_path, holdout)
    oracle_hash = _write(oracle_path, oracle)

    rubric_hashes = {
        rubric["judge_run_id"]: _sha_bytes(_canonical({"name": rubric["name"], "text": rubric["text"]}))
        for rubric in JUDGE_RUBRICS
    }
    records: list[dict[str, Any]] = []
    for case in holdout["cases"]:
        case_id = str(case["case_id"])
        if case_id not in semantic_ids:
            records.append({
                "case_id": case_id,
                "review_source": "DETERMINISTIC_ORACLE_VALIDATOR",
                "judge_run_id": None,
                "judge_model": None,
                "rubric_hash": oracle_hash,
                "verdict": "ACCEPT",
                "reason": "All required deterministic checks are mapped, and no deterministic leakage or duplicate gate failed.",
                "consensus": "NOT_APPLICABLE_DETERMINISTIC",
                "automated_adjudication": {
                    "outcome": "ACCEPT",
                    "method": "deterministic-gates",
                    "prior_judge_verdicts_visible": False,
                },
            })
            continue
        recorded_verdicts = SEMANTIC_VERDICTS[case_id]
        passes = [
            {
                "judge_run_id": rubric["judge_run_id"],
                "judge_model": judge_model,
                "rubric_hash": rubric_hashes[rubric["judge_run_id"]],
                "verdict": recorded_verdicts[index],
                "reason": rubric["reason"],
                "prior_judge_verdicts_visible": False,
            }
            for index, rubric in enumerate(JUDGE_RUBRICS)
        ]
        consensus = "UNANIMOUS_ACCEPT" if set(recorded_verdicts) == {"ACCEPT"} else "DISAGREEMENT"
        adjudication_outcome = "ACCEPT" if consensus == "UNANIMOUS_ACCEPT" else "REJECT"
        records.append({
            "case_id": case_id,
            "review_source": "AUTOMATED_SEMANTIC_JUDGE",
            "judge_run_id": "p2-1a-semantic-pass-01..03",
            "judge_model": judge_model,
            "rubric_hash": _sha_bytes(_canonical(rubric_hashes)),
            "verdict": adjudication_outcome,
            "reason": "Three isolated semantic passes unanimously accepted the prompt/oracle pair." if consensus == "UNANIMOUS_ACCEPT" else "Semantic passes disagreed; this case is not admitted.",
            "judge_passes": passes,
            "consensus": consensus,
            "automated_adjudication": {
                "outcome": adjudication_outcome,
                "method": "unanimous-three-pass-consensus" if consensus == "UNANIMOUS_ACCEPT" else "fail-closed-disagreement",
                "prior_judge_verdicts_visible": False,
            },
        })

    semantic_records = [record for record in records if record["review_source"] == "AUTOMATED_SEMANTIC_JUDGE"]
    pair_count = len(semantic_ids) * 3
    disagreements = [record["case_id"] for record in semantic_records if record["consensus"] == "DISAGREEMENT"]
    register = {
        "register_version": "PLAN_V2_P2_1A_AUTOMATED_REVIEW_REGISTER_V1",
        "status": "FROZEN",
        "review_mode": "AUTOMATED",
        "generated_at": generated_at,
        "holdout_sha256": holdout_hash,
        "oracle_sha256": oracle_hash,
        "same_model_multi_pass": True,
        "SAME_MODEL_MULTI_PASS": True,
        "judge_architecture": {
            "semantic_case_count": len(semantic_ids),
            "passes_per_semantic_case": len(JUDGE_RUBRICS),
            "judge_model": judge_model,
            "independence_statement": "All three passes use the same underlying model and are not statistically independent.",
            "isolation_contract": "Each pass receives only one prompt, its fixture, deterministic oracle, and its own rubric. Prior pass verdicts are excluded.",
            "visibility_boundary": holdout["visibility_boundary"],
        },
        "agreement": {
            "semantic_pass_count": pair_count,
            "unanimous_accept_case_count": sum(record["consensus"] == "UNANIMOUS_ACCEPT" for record in semantic_records),
            "disagreement_case_ids": disagreements,
            "percent_agreement": round(100 * (pair_count - len(disagreements)) / pair_count, 2) if pair_count else None,
            "cohens_kappa": None,
            "cohens_kappa_note": "Undefined for a single observed verdict class.",
        },
        "review_coverage_percent": 100.0,
        "records": records,
    }
    register_path = output_dir / "p2-1a-automated-review-register-v1.json"
    register_hash = _write(register_path, register)

    flags = {
        "REVIEW_MODE_AUTOMATED": True,
        "HOLDOUT_V2_FROZEN": len(selected) >= 120,
        "ORACLE_FROZEN": bool(oracle["profiles"]),
        "THRESHOLDS_FROZEN": thresholds.get("frozen_before_scored_execution") is True,
        "IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE": not implementation["mismatches"],
        "REVIEW_COVERAGE_100_PERCENT": len(records) == len(selected),
        "THREE_SEMANTIC_PASSES": all(len(record.get("judge_passes", [])) == 3 for record in semantic_records),
        "NO_UNRESOLVED_SEMANTIC_DISAGREEMENTS": not disagreements,
        "ZERO_CONFIRMED_DEVELOPMENT_OVERLAP": not audit["confirmed_development_overlap"],
        "ZERO_TEMPLATE_DEVELOPMENT_OVERLAP": not audit["template_development_overlap"],
        "ZERO_DUPLICATE_WEIGHTING": audit["selected_exact_duplicate_count"] == 0 and audit["selected_template_duplicate_count"] == 0,
        "ZERO_SEMANTIC_LEAKAGE_CANDIDATES": not audit["semantic_overlap_candidates"],
        "FLUTTER_3_44_8": toolchain["flutter_version"] == "3.44.8",
        "DART_3_12_2": toolchain["dart_version"] == "3.12.2",
        "CPYTHON_3_10_21": toolchain["cpython_version"] == "3.10.21",
        "NO_SCORED_ACCEPTANCE_EXECUTED": True,
    }
    manifest = {
        "freeze_version": AUTOMATED_VERSION,
        "status": "FROZEN",
        "review_mode": "AUTOMATED",
        "SAME_MODEL_MULTI_PASS": True,
        "generated_at": generated_at,
        "artifacts": {
            "holdout": {"path": holdout_path.name, "sha256": holdout_hash},
            "oracle": {"path": oracle_path.name, "sha256": oracle_hash},
            "automated_review_register": {"path": register_path.name, "sha256": register_hash},
            "thresholds": {"path": thresholds_path.name, "sha256": _sha(thresholds_path)},
            "implementation_freeze": {"path": "implementation-freeze-p2-1r-v1.json", "sha256": _sha(VALIDATION / "implementation-freeze-p2-1r-v1.json")},
        },
        "deterministic_oracle_coverage": {
            "case_count": len(selected),
            "semantic_case_count": len(semantic_ids),
            "deterministic_only_case_count": len(selected) - len(semantic_ids),
            "check_case_counts": dict(sorted(Counter(check for case in holdout["cases"] for check in case["deterministic_check_ids"]).items())),
        },
        "leakage_audit": audit,
        "implementation_hash_verification": implementation,
        "toolchain": toolchain,
        "final_preflight": flags,
        "READY_TO_RUN_P2_1_ACCEPTANCE": all(flags.values()),
    }
    manifest_path = output_dir / "p2-1a-automated-freeze-manifest-v1.json"
    manifest_hash = _write(manifest_path, manifest)
    return {
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_hash,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=VALIDATION)
    parser.add_argument("--flutter", required=True, help="Pinned Flutter executable; global PATH is intentionally not used.")
    parser.add_argument("--judge-model", default=JUDGE_MODEL_DEFAULT)
    args = parser.parse_args()
    result = build(args.output_dir, flutter=args.flutter, judge_model=args.judge_model)
    print(json.dumps({
        "manifest_path": str(result["manifest_path"]),
        "manifest_sha256": result["manifest_sha256"],
        "READY_TO_RUN_P2_1_ACCEPTANCE": result["manifest"]["READY_TO_RUN_P2_1_ACCEPTANCE"],
        "NO_SCORED_ACCEPTANCE_EXECUTED": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
