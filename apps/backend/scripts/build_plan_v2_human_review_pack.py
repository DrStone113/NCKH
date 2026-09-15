"""Create P2.1H human-review artefacts without invoking Plan V2.

The generated pack contains candidate prompts and draft, output-independent
oracles only.  It intentionally contains no Plan V2/legacy output, comparator
result, runtime prediction, or implementation-behaviour detail.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
DECISIONS = {
    "ACCEPT", "REVISE_BEFORE_FREEZE", "REJECT_AMBIGUOUS", "REJECT_DUPLICATE",
    "REJECT_LEAKAGE", "REJECT_OUT_OF_SCOPE",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"CANNOT_LOAD:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_for(row: dict[str, Any]) -> dict[str, str]:
    profile = str(row["oracle_profile"])
    area = str(row["area"])
    fixture = {
        "fixture_schema": "PLAN_V2_P2_1H_PROMPT_FACTS_V1",
        "planning_domain": area,
        "prompt_facts": "Only facts explicitly stated in the Vietnamese prompt are authoritative.",
        "unstated_context": "UNKNOWN; reviewers must not assume defaults, history, completion, or medical facts.",
        "actual_observations": "NOT_PROVIDED unless the prompt explicitly asks to protect planned/actual separation.",
        "write_authority": "No persistence is authorized by the review pack itself.",
    }
    if "OWNER_BOUND" in profile:
        fixture["principal_fixture"] = "Authenticated owner is required; prompt is an authorization adversarial case."
    elif "IDENTITY" in profile or "LIFECYCLE" in profile:
        fixture["identity_fixture"] = "Plan/revision/hash/action identifiers must be exact when the prompt refers to them."
    if "MISSING_CONTEXT" in profile or "CLARIFY" in profile:
        fixture["context_state"] = "A required authoritative field is MISSING, NOT_LOADED, UNKNOWN, or conflicting as stated by the prompt."
    elif "SAFETY_GATE" in profile or "SPECIALIST_GATE" in profile:
        fixture["safety_state"] = "The safety-relevant fact stated in the prompt is authoritative; no unstated diagnosis is inferred."
    elif "TIMEZONE" in profile:
        fixture["time_state"] = "The stated timezone/local-date facts are authoritative; unstated conversion details remain unknown."
    else:
        fixture["context_state"] = "Known only to the extent explicitly stated in the prompt."
    return fixture


def _intent(profile: str, area: str) -> str:
    if profile.startswith("NUTRITION"):
        return "Evaluate safe nutrition planning, a required clarification, or a policy/specialist gate without prescribing one exact menu."
    if profile.startswith("WORKOUT"):
        return "Evaluate safe single-session planning, a required clarification, or a safety gate while preserving E4 authority."
    if profile.startswith("WEEKLY"):
        return "Evaluate scheduling semantics, exact user constraints, timezone handling, or explicit heuristic/delegation boundaries."
    if profile.startswith("COMBINED"):
        return "Evaluate a reference-only combined container with isolated child identities and no cross-domain compensation."
    if profile.startswith("LIFECYCLE"):
        return "Evaluate owner-scoped revision/lifecycle, idempotency, concurrency, and identity-chain semantics."
    return f"Candidate requires human review before it may be used for {area}."


def _semantic(profile: str, oracle_profile: dict[str, Any]) -> dict[str, Any]:
    clarification = []
    if any(marker in profile for marker in ("CLARIFY", "MISSING", "CONFLICT", "STALE", "INSUFFICIENT")):
        clarification.append("Clarify or reject the stated missing, ambiguous, stale, or conflicting authoritative input.")
    if any(marker in profile for marker in ("SAFETY", "SPECIALIST")):
        clarification.append("Use a safety/specialist gate rather than a prescriptive result when the stated condition requires it.")
    return {
        "required_user_intent": _intent(profile, ""),
        "acceptable_outcome_classes": oracle_profile.get("acceptable", oracle_profile.get("required", [])),
        "unacceptable_outcome_classes": oracle_profile.get("forbidden", []),
        "required_clarification_conditions": clarification,
        "permitted_variation": "Do not require an exact dish, exercise, weekday, or schedule unless the prompt explicitly fixes it."
    }


def _ambiguity_flags(row: dict[str, Any]) -> list[str]:
    prompt = str(row["prompt"]).casefold()
    flags: list[str] = []
    if any(fragment in prompt for fragment in ("không rõ", "chưa", "cần làm rõ", "món đó", "vừa rồi", "sức bền")):
        flags.append("INTENTIONAL_CLARIFICATION_OR_REFERENCE_AMBIGUITY")
    if any(fragment in prompt for fragment in ("đau", "chấn thương", "mang thai", "bệnh", "huyết áp", "tim mạch", "rối loạn")):
        flags.append("SAFETY_SENSITIVE_SECOND_REVIEW_PREFERRED")
    if row["proposed_disposition"] == "NOT_SELECTED":
        flags.append("PRESELECTED_OUT_OF_FINAL_POOL_PENDING_HUMAN_CONFIRMATION")
    return flags


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    candidates_module = _load_module("plan_v2_candidates", VALIDATION / "qualification_candidates_v2.py")
    oracle = _load_json("acceptance-v2-oracle-candidate-v1.json")
    index = _load_json("development-exclusion-index-v1.json")
    protocol = _load_json("dedup-protocol-v1.json")
    rows = candidates_module.candidate_rows()
    pack_cases: list[dict[str, Any]] = []
    for row in rows:
        profile_name = str(row["oracle_profile"])
        profile = oracle["profiles"].get(profile_name, {})
        pack_cases.append({
            "case_id": row["candidate_id"],
            "category": row["area"],
            "prompt": row["prompt"],
            "structured_fixture_context": _fixture_for(row),
            "intended_capability": _intent(profile_name, str(row["area"])),
            "draft_objective_invariants": {
                "required": profile.get("required", []),
                "forbidden": profile.get("forbidden", []),
            },
            "draft_semantic_acceptance_criteria": _semantic(profile_name, profile),
            "known_ambiguity_flags": _ambiguity_flags(row),
            "development_overlap_audit_result": {
                "exact_normalized_overlap": "NONE_IN_P2_1R_PREFLIGHT",
                "template_overlap": "NONE_IN_P2_1R_PREFLIGHT",
                "semantic_candidate": "NONE_IN_P2_1R_PREFLIGHT",
                "exclusion_index_canonical_records_sha256": index["canonical_records_sha256"],
                "dedup_protocol_version": protocol["protocol_version"],
            },
            "ai_proposed_disposition": row["proposed_disposition"],
            "human_decision": "PENDING_HUMAN_REVIEW",
        })
    source = VALIDATION / "qualification_candidates_v2.py"
    pack = {
        "pack_version": "PLAN_V2_P2_1H_HUMAN_REVIEW_PACK_V1",
        "status": "PENDING_HUMAN_REVIEW",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_visibility_boundary": {
            "included": ["case_id", "category", "prompt", "fixture/context", "draft objective/semantic oracle", "ambiguity flags", "leakage audit"],
            "excluded": ["Plan V2 output", "legacy output", "comparator verdict", "runtime pass/fail prediction", "latency", "implementation source details"],
        },
        "candidate_source_sha256": _sha(source),
        "case_count": len(pack_cases),
        "cases": pack_cases,
    }
    register = {
        "register_version": "PLAN_V2_P2_1H_HUMAN_REVIEW_REGISTER_TEMPLATE_V1",
        "status": "PENDING_HUMAN_REVIEW",
        "allowed_decisions": sorted(DECISIONS),
        "required_completed_review_fields": ["reviewer_id", "reviewed_at", "decision", "reason"],
        "review_records": [
            {
                "case_id": case["case_id"],
                "reviews": [],
                "adjudication": {
                    "final_decision": "PENDING_HUMAN_REVIEW",
                    "adjudicator_id": None,
                    "adjudicated_at": None,
                    "reason": None,
                },
            }
            for case in pack_cases
        ],
    }
    return pack, register


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=VALIDATION)
    args = parser.parse_args()
    pack, register = build()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = args.output_dir / "p2-1h-human-review-pack-v1.json"
    register_path = args.output_dir / "p2-1h-human-review-register-template-v1.json"
    csv_path = args.output_dir / "p2-1h-human-review-register-template-v1.csv"
    manifest_path = args.output_dir / "p2-1h-human-review-pack-manifest-v1.json"
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    register_path.write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "reviewer_id", "reviewed_at", "decision", "reason", "second_reviewer_id", "second_reviewed_at", "second_decision", "second_reason", "adjudicator_id", "adjudicated_at", "final_decision", "adjudication_reason"])
        writer.writeheader()
        for record in register["review_records"]:
            writer.writerow({"case_id": record["case_id"], "decision": "PENDING_HUMAN_REVIEW", "final_decision": "PENDING_HUMAN_REVIEW"})
    manifest = {
        "pack_version": pack["pack_version"],
        "pack_path": pack_path.name,
        "pack_sha256": _sha(pack_path),
        "register_template_path": register_path.name,
        "register_template_sha256": _sha(register_path),
        "register_csv_path": csv_path.name,
        "register_csv_sha256": _sha(csv_path),
        "case_count": pack["case_count"],
        "candidate_source_sha256": pack["candidate_source_sha256"],
        "human_decisions_present": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
