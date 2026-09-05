from __future__ import annotations

from services.acceptance.postmortem.plan_v2_semantics import evaluate_case


def _raw(status: str, *, plan: dict | None = None) -> dict:
    return {"v2": {"status": status, "normalized_output": {"status": status, "plan": plan or {}}}}


def test_missing_workout_authority_requires_safe_clarification() -> None:
    case = {"category": "single_workout", "execution_fixture": {"profile": {"age": 35}}}
    decision = evaluate_case(case, _raw("CLARIFICATION_REQUIRED"))
    assert decision["semantic_match"] is True
    assert decision["normalization_notes"]


def test_ready_workout_without_authority_is_rejected() -> None:
    case = {"category": "weekly_workout", "execution_fixture": {"profile": {}, "number_of_sessions": 2}}
    decision = evaluate_case(case, _raw("READY", plan={"items": [{}, {}]}))
    assert decision["semantic_match"] is False
    assert decision["extra_semantics"] == ["generated_workout_without_authoritative_safety_profile"]


def test_authoritative_workout_fixture_still_requires_schedule_shape() -> None:
    case = {
        "category": "weekly_workout",
        "execution_fixture": {
            "profile": {"workout_profile": {"injury_status": "none", "exercise_safety_profile": {"acute_injury": False}}},
            "period": ["2031-01-01", "2031-01-07"],
            "timezone": "Asia/Ho_Chi_Minh",
            "number_of_sessions": 2,
        },
    }
    decision = evaluate_case(case, _raw("READY", plan={"request": {"period_start": "2031-01-01", "period_end": "2031-01-07", "timezone": "Asia/Ho_Chi_Minh"}, "items": [{}]}))
    assert decision["semantic_match"] is False
    assert decision["target_match"] is False


def test_symbolic_combined_references_require_safe_clarification() -> None:
    case = {"category": "combined_health", "execution_fixture": {"child_revisions": ["nutrition", "workout"]}}
    assert evaluate_case(case, _raw("CLARIFICATION_REQUIRED"))["semantic_match"] is True


def test_ready_combined_with_symbolic_references_is_rejected() -> None:
    case = {"category": "combined_health", "execution_fixture": {"child_revisions": ["nutrition", "workout"]}}
    assert evaluate_case(case, _raw("READY"))["semantic_match"] is False


def test_concrete_combined_references_require_bound_container() -> None:
    fixture = {"child_revisions": [{"plan_id": "p1", "revision_id": "r1", "revision_content_hash": "h1"}, {"plan_id": "p2", "revision_id": "r2", "revision_content_hash": "h2"}]}
    decision = evaluate_case(case={"category": "combined_health", "execution_fixture": fixture}, raw=_raw("READY", plan={"provenance": {"child_revisions": [{}, {}], "no_cross_domain_energy_compensation": True}}))
    assert decision["semantic_match"] is True


def test_lifecycle_target_mismatch_is_rejected() -> None:
    case = {"category": "revision_lifecycle", "execution_fixture": {"operation": "pause"}}
    decision = evaluate_case(case, _raw("READY", plan={"lifecycle_status": "ACTIVE"}))
    assert decision["semantic_match"] is False
    assert decision["field_match"] is False
