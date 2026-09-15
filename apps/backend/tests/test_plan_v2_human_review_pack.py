from __future__ import annotations

from scripts.build_plan_v2_human_review_pack import build
from scripts.validate_plan_v2_human_review_register import validate


def test_human_review_pack_contains_only_review_inputs_and_no_runtime_outcomes():
    pack, register = build()

    assert pack["status"] == "PENDING_HUMAN_REVIEW"
    assert pack["case_count"] == 150
    assert len(pack["cases"]) == 150
    assert len(register["review_records"]) == 150
    assert {case["human_decision"] for case in pack["cases"]} == {"PENDING_HUMAN_REVIEW"}
    required = {
        "case_id", "category", "prompt", "structured_fixture_context", "intended_capability",
        "draft_objective_invariants", "draft_semantic_acceptance_criteria",
        "known_ambiguity_flags", "development_overlap_audit_result",
    }
    forbidden = {"plan_v2_output", "legacy_output", "comparator_result", "pass_fail_prediction", "latency"}
    for case in pack["cases"]:
        assert required <= set(case)
        assert not (forbidden & set(case))


def test_empty_human_register_cannot_be_mistaken_for_a_freeze():
    pack, register = build()
    result = validate(register, {case["case_id"] for case in pack["cases"]})

    assert result["human_review_coverage_percent"] == 0.0
    assert result["freeze_ready"] is False
