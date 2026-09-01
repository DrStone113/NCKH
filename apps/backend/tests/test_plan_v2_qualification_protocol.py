from __future__ import annotations

from scripts.verify_plan_v2_qualification import evaluate


def test_qualification_protocol_preserves_v1_and_blocks_scoring_pending_human_review():
    result = evaluate(None)

    assert result["flags"]["ACCEPTANCE_V1_STATUS_CONTAMINATED"]
    assert result["flags"]["P1_DEVELOPMENT_CASE_COUNT"]
    assert result["flags"]["CANDIDATE_COUNT_SUFFICIENT"]
    assert result["flags"]["CANDIDATE_UNIQUE"]
    assert result["flags"]["NO_CONFIRMED_DEVELOPMENT_OVERLAP"]
    assert result["flags"]["NO_TEMPLATE_DEVELOPMENT_OVERLAP"]
    assert result["flags"]["IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE"]
    assert result["flags"]["ORACLE_FROZEN"] is False
    assert result["flags"]["HOLDOUT_V2_FROZEN"] is False
    assert result["READY_TO_RUN_P2_1_ACCEPTANCE"] is False
