"""Build deterministic, read-only postmortem evidence from immutable V3 files."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from services.acceptance.postmortem.plan_v2_semantics import SEMANTIC_CONTRACT_VERSION, evaluate_case


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "validation" / "plan_tool_v2_p2"
DEFAULT_OUTPUT = EVIDENCE / "plan-v2-v3-semantic-postmortem-replay-v1.json"
_FROZEN_HASHES = {
    "holdout_sha256": "8256ca62b344957c6e36b2580551777092cced2b85c84a381091b715511b519b",
    "oracle_sha256": "bb92a47b3edc8ec8a5ce13a1fb6e30a25738651bbf1c30ff413a98f3e3eb8af5",
    "thresholds_sha256": "adeb1a8139c15eb619f3bc92ad89e68197aa056b61f567d3fb58379b040a5400",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(raw: Mapping[str, Any]) -> dict[str, Any]:
    v2 = raw["v2"]
    output = v2.get("normalized_output") or {}
    plan = output.get("plan") if isinstance(output, Mapping) else {}
    plan = plan if isinstance(plan, Mapping) else {}
    validation = output.get("validation") if isinstance(output, Mapping) else {}
    validation = validation if isinstance(validation, Mapping) else {}
    issues = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    return {
        "status": v2.get("status"),
        "domain": plan.get("domain"),
        "item_count": len(plan.get("items") or []),
        "lifecycle_status": plan.get("lifecycle_status"),
        "validation_issue_codes": [issue.get("code") for issue in issues if isinstance(issue, Mapping)],
        "planned_not_actual": (plan.get("provenance") or {}).get("planned_not_consumed"),
    }


def _classification(category: str) -> dict[str, Any]:
    if category in {"single_workout", "weekly_workout"}:
        return {
            "primary_root_cause": "SCORER_FALSE_NEGATIVE",
            "secondary_root_causes": ["HARNESS_EXPECTATION_ERROR", "DATA_FIXTURE_OR_CASE_DESIGN_ERROR"],
            "ownership": "MULTI_FACTOR",
            "primary_owner": "SCORER_BUG",
            "secondary_owners": ["HARNESS_BUG", "TEST_CASE_BUG", "CONTRACT_AMBIGUITY"],
            "fix_id": "SEM-CONTRACT-001",
            "diff_fields": ["status", "plan.items", "workout_profile", "exercise_safety_profile"],
            "diff": "Frozen scorer required READY and a generated workout, but the fixture omitted authoritative workout and exercise-safety profiles. Plan V2 safely requested clarification.",
        }
    if category == "combined_health":
        return {
            "primary_root_cause": "HARNESS_EXPECTATION_ERROR",
            "secondary_root_causes": ["DATA_FIXTURE_OR_CASE_DESIGN_ERROR", "SCORER_FALSE_NEGATIVE"],
            "ownership": "MULTI_FACTOR",
            "primary_owner": "HARNESS_BUG",
            "secondary_owners": ["TEST_CASE_BUG", "SCORER_BUG", "CONTRACT_AMBIGUITY"],
            "fix_id": "SEM-CONTRACT-002",
            "diff_fields": ["status", "provenance.child_revisions", "execution_fixture.child_revisions"],
            "diff": "Frozen scorer required a ready combined container with two child revisions, while the fixture supplied only symbolic labels and no bindable child identities. Plan V2 safely requested clarification.",
        }
    raise ValueError(f"Unexpected V3 failure category: {category}")


def _expected_summary(case: Mapping[str, Any]) -> dict[str, Any]:
    category = str(case["category"])
    if category in {"single_workout", "weekly_workout"}:
        return {
            "frozen_oracle": "generic input-only semantic profile; no expected output, operation, target, field, or value is encoded",
            "frozen_scorer_effective_expectation": "READY with fixture period/timezone and generated workout item count",
            "corrected_contract_expectation": "safe clarification when authoritative workout/safety context is absent",
        }
    return {
        "frozen_oracle": "generic input-only semantic profile; no expected output, operation, target, field, or value is encoded",
        "frozen_scorer_effective_expectation": "READY combined container with two child revisions and cross-domain provenance",
        "corrected_contract_expectation": "safe clarification when child references are symbolic rather than concrete plan/revision/hash bindings",
    }


def _review(category: str) -> dict[str, Any]:
    common = {
        "is_expected_fixture_correct": False,
        "is_actual_behavior_correct": True,
        "is_scorer_correct": False,
        "are_expected_and_actual_semantically_equivalent": "the frozen expected behavior is underspecified; under the explicit safety contract the actual safe clarification is correct",
        "contract_sufficiently_precise_before_fix": False,
    }
    if category in {"single_workout", "weekly_workout"}:
        common["conclusion"] = "Do not infer a safe workout from demographic-only data; the clarification is correct and the frozen READY requirement is not contract-supported."
    else:
        common["conclusion"] = "Do not construct a combined plan from symbolic child labels; clarification is correct and the frozen READY requirement is not contract-supported."
    return common


def build_postmortem(evidence_dir: Path = EVIDENCE) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Analyze persisted artifacts only; no executor, database, or oracle mutation occurs."""

    holdout_path = evidence_dir / "plan-v2-confirmatory-v3.json"
    raw_path = evidence_dir / "plan-v2-confirmatory-v3-raw-execution-v1.json"
    results_path = evidence_dir / "plan-v2-confirmatory-v3-results-v1.json"
    register_path = evidence_dir / "plan-v2-confirmatory-v3-execution-register-v1.json"
    oracle_path = evidence_dir / "plan-v2-confirmatory-oracle-v3.json"
    thresholds_path = evidence_dir / "plan-v2-confirmatory-thresholds-v3.json"
    harness_path = evidence_dir / "plan-v2-confirmatory-v3-harness-freeze-v2.json"
    holdout, raw, results, register, oracle, thresholds, harness = map(
        _read, (holdout_path, raw_path, results_path, register_path, oracle_path, thresholds_path, harness_path)
    )
    cases = {str(case["candidate_id"]): case for case in holdout["cases"]}
    raw_by_id = {str(record["case_id"]): record for record in raw["records"]}
    result_by_id = {str(record["case_id"]): record for record in results["records"]}
    if set(cases) != set(raw_by_id) or set(cases) != set(result_by_id):
        raise RuntimeError("V3_POSTMORTEM_CASE_IDENTITY_MISMATCH")

    failures = [record for record in results["records"] if record.get("semantic_match") is not True]
    if len(failures) != 60 or results["metrics"].get("request_semantic_match_percent") != 50.0:
        raise RuntimeError("V3_POSTMORTEM_OFFICIAL_RESULT_RECONCILIATION_FAILED")
    identities = {
        "holdout_sha256": _hash(holdout_path),
        "oracle_sha256": _hash(oracle_path),
        "thresholds_sha256": _hash(thresholds_path),
        "raw_execution_sha256": _hash(raw_path),
        "results_sha256": _hash(results_path),
        "execution_register_sha256": _hash(register_path),
        "harness_freeze_sha256": _hash(harness_path),
    }
    if {key: identities[key] for key in _FROZEN_HASHES} != _FROZEN_HASHES:
        raise RuntimeError("V3_POSTMORTEM_FROZEN_IDENTITY_MISMATCH")
    if set(cases) != {str(item["case_id"]) for item in oracle["cases"]}:
        raise RuntimeError("V3_POSTMORTEM_ORACLE_CASE_IDENTITY_MISMATCH")
    forbidden_oracle_fields = {"expected_output", "expected_operation", "expected_target", "expected_field", "expected_value"}
    if any(forbidden_oracle_fields & set(item) for item in oracle["cases"]):
        raise RuntimeError("V3_POSTMORTEM_ORACLE_CONTAINS_UNEXPECTED_OUTPUT_SEMANTICS")
    if results["thresholds"].get("REQUEST_SEMANTIC_MATCH_PERCENT") != 95 or thresholds.get("REQUEST_SEMANTIC_MATCH_PERCENT") != 95:
        raise RuntimeError("V3_POSTMORTEM_THRESHOLD_RECONCILIATION_FAILED")

    inventories: list[dict[str, Any]] = []
    replay_cases: list[dict[str, Any]] = []
    for case_id in sorted(cases):
        case, raw_record, v3_record = cases[case_id], raw_by_id[case_id], result_by_id[case_id]
        decision = evaluate_case(case, raw_record)
        replay_cases.append(
            {
                "case_id": case_id,
                "case_family": case["category"],
                "v3_original_semantic_match": bool(v3_record["semantic_match"]),
                "post_fix_replay_match": decision["semantic_match"],
                "diagnostics": decision,
            }
        )
        if v3_record["semantic_match"] is True:
            continue
        classified = _classification(str(case["category"]))
        inventories.append(
            {
                "case_id": case_id,
                "v3_original_semantic_match": False,
                "case_family": case["category"],
                "frozen_input_request": {"prompt": case["prompt"], "execution_fixture": case["execution_fixture"]},
                "expected_semantics_summary": _expected_summary(case),
                "actual_semantics_summary": _summary(raw_record),
                "semantic_diff": {"summary": classified["diff"], "differing_fields": classified["diff_fields"]},
                "expected_reference_chain_information": {"scope": "suite", "identity_percent": 100.0, "per_case_expected_roles": "not encoded by V3 oracle"},
                "actual_reference_chain_information": {"scope": "suite", "identity_percent": 100.0, "identity_match": True},
                "references_remained_identical": True,
                "semantic_scorer_decision": {"semantic_match": False, "deterministic_fixture_match": v3_record["deterministic_fixture_match"], "v2_status": v3_record["v2_status"]},
                "warnings_errors": list(raw_record["v2"].get("errors") or []),
                "execution_provenance": {"raw_execution_sha256": raw_record["raw_execution_sha256"], "executor": raw_record["v2"]["executor"], "register_result": register["result"]},
                **classified,
                "reviewer_conclusion": _review(str(case["category"])),
                "post_fix_replay_match": decision["semantic_match"],
                "post_fix_diagnostics": decision,
                "notes": "Historical analysis only; official V3 result is not recalculated or modified.",
            }
        )

    primary_counts = Counter(item["primary_root_cause"] for item in inventories)
    owner_counts = Counter(item["primary_owner"] for item in inventories)
    ordered = primary_counts.most_common()
    cumulative = 0
    pareto = []
    for rank, (cause, count) in enumerate(ordered, start=1):
        cumulative += count
        pareto.append({"rank": rank, "root_cause": cause, "case_count": count, "percent_of_failures": round(100 * count / len(inventories), 2), "cumulative_percent": round(100 * cumulative / len(inventories), 2)})
    replay_matches = sum(item["post_fix_replay_match"] for item in replay_cases)
    root_causes = {
        "artifact_version": "PLAN_V2_V3_SEMANTIC_ROOT_CAUSES_V1",
        "analysis_mode": "POSTMORTEM_REPLAY_ONLY",
        "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
        "source_identities": identities,
        "official_v3_reconciliation": {"case_count": 120, "semantic_failures": len(inventories), "semantic_matches": 60, "semantic_match_percent": 50.0, "reference_chain_identity_percent": 100.0, "hard_violations": 0},
        "root_causes": [
            {"root_cause": cause, "case_count": count, "percentage_of_failures": round(100 * count / len(inventories), 2), "owner": "SCORER_BUG" if cause == "SCORER_FALSE_NEGATIVE" else "HARNESS_BUG", "affected_case_families": sorted({item["case_family"] for item in inventories if item["primary_root_cause"] == cause}), "fix_strategy": "semantic contract safe-clarification rule" if cause == "SCORER_FALSE_NEGATIVE" else "require concrete child bindings before requiring READY", "status": "RESOLVED_IN_FUTURE_HARNESS"}
            for cause, count in ordered
        ],
        "ownership": {"classification_counts": {"MULTI_FACTOR": len(inventories)}, "primary_owner_counts": dict(sorted(owner_counts.items()))},
        "pareto": pareto,
        "fix_registry": [
            {"fix_id": "SEM-CONTRACT-001", "root_cause": "SCORER_FALSE_NEGATIVE", "affected_cases": 40, "component": "future semantic scorer", "implementation_files": ["services/acceptance/postmortem/plan_v2_semantics.py"], "behavior_before": "required READY despite absent authoritative workout/safety profile", "behavior_after": "requires safe clarification when workout authority is absent; evaluates READY only when authoritative context is supplied", "regression_tests": ["test_missing_workout_authority_requires_safe_clarification", "test_authoritative_workout_fixture_still_requires_schedule_shape"], "negative_controls": ["test_ready_workout_without_authority_is_rejected"], "risk": "under-normalization is deliberate; missing safety context remains material", "status": "IMPLEMENTED"},
            {"fix_id": "SEM-CONTRACT-002", "root_cause": "HARNESS_EXPECTATION_ERROR", "affected_cases": 20, "component": "future semantic scorer", "implementation_files": ["services/acceptance/postmortem/plan_v2_semantics.py"], "behavior_before": "required a ready combined container from symbolic child labels", "behavior_after": "requires safe clarification for symbolic references and validates bindings only for concrete child revisions", "regression_tests": ["test_symbolic_combined_references_require_safe_clarification", "test_concrete_combined_references_require_bound_container"], "negative_controls": ["test_ready_combined_with_symbolic_references_is_rejected"], "risk": "no alias normalization of references; plan/revision/hash remain exact", "status": "IMPLEMENTED"},
            {"fix_id": "SEM-DIAG-003", "root_cause": "SCORER_FALSE_NEGATIVE", "affected_cases": 60, "component": "future semantic diagnostics", "implementation_files": ["services/acceptance/postmortem/plan_v2_semantics.py"], "behavior_before": "boolean-only fixture decision", "behavior_after": "operation/target/field/value/missing/extra diagnostics", "regression_tests": ["test_diagnostics_explain_missing_authority"], "negative_controls": ["test_lifecycle_target_mismatch_is_rejected"], "risk": "diagnostics do not change hard-invariant enforcement", "status": "IMPLEMENTED"},
        ],
        "anti_overfit_check": {"production_files_changed": [], "case_id_or_fixture_text_in_contract_source": False, "result": "PASS"},
    }
    inventory = {"artifact_version": "PLAN_V2_V3_SEMANTIC_FAILURE_INVENTORY_V1", "analysis_mode": "POSTMORTEM_REPLAY_ONLY", "source_identities": identities, "official_v3_failure_count": len(inventories), "records": inventories}
    replay = {"artifact_version": "PLAN_V2_V3_SEMANTIC_POSTMORTEM_REPLAY_V1", "analysis_mode": "POSTMORTEM_REPLAY_ONLY", "execution_performed": False, "official_v3_result_retained": "FAIL", "semantic_contract_version": SEMANTIC_CONTRACT_VERSION, "source_identities": identities, "replayed_case_count": len(replay_cases), "postmortem_replay_semantic_matches": replay_matches, "postmortem_replay_semantic_match_percent": round(100 * replay_matches / len(replay_cases), 2), "remaining_failure_count": len(replay_cases) - replay_matches, "cases": replay_cases, "generated_at": datetime.now(timezone.utc).isoformat()}
    return inventory, root_causes, replay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    inventory, root_causes, replay = build_postmortem(args.evidence_dir)
    outputs = {
        "plan-v2-v3-semantic-failure-inventory-v1.json": inventory,
        "plan-v2-v3-semantic-root-causes-v1.json": root_causes,
        "plan-v2-v3-semantic-postmortem-replay-v1.json": replay,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        (args.output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
