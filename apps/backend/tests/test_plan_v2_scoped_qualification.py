from __future__ import annotations

from scripts.verify_plan_v2_scoped_qualification import evaluate_scoped


def test_scoped_verifier_preserves_historical_v1_and_reports_current_p2_1a_scope():
    result = evaluate_scoped()

    assert result["HISTORICAL_V1_CONTAMINATED"] is True
    assert result["diagnostics"]["historical_v1_rewritten"] is False
    assert result["CURRENT_SCOPE"] == "P2_1A_AUTOMATED_FREEZE"
    assert result["CURRENT_ACCEPTANCE_QUALIFICATION_STATUS"] in {
        "READY_FOR_FIRST_SCORED_ACCEPTANCE",
        "NOT_READY_FOR_FIRST_SCORED_ACCEPTANCE",
    }
    assert result["diagnostics"]["release_qualification_claimed"] is False
    assert result["diagnostics"]["scored_acceptance_executed"] is False
