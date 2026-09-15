from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_plan_v2_qualification import evaluate


def test_qualification_protocol_keeps_historical_v1_separate_from_frozen_p2_1a():
    result = evaluate(None)

    assert result["flags"]["ACCEPTANCE_V1_STATUS_CONTAMINATED"]
    assert result["flags"]["P1_DEVELOPMENT_CASE_COUNT"]
    assert result["flags"]["CANDIDATE_COUNT_SUFFICIENT"]
    assert result["flags"]["CANDIDATE_UNIQUE"]
    assert result["flags"]["NO_CONFIRMED_DEVELOPMENT_OVERLAP"]
    assert result["flags"]["NO_TEMPLATE_DEVELOPMENT_OVERLAP"]
    # P2.1's source set is historical first-pass evidence.  P2.2 deliberately
    # repairs product code into a separately named baseline, so the old
    # preflight must report a mismatch rather than pretending the old source
    # identity is still current.
    assert result["flags"]["IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE"] is False
    # These are current P2.1A facts. They do not rewrite the contaminated V1
    # corpus and must not be inverted merely to satisfy an archival assertion.
    assert result["flags"]["ORACLE_FROZEN"] is True
    assert result["flags"]["HOLDOUT_V2_FROZEN"] is True

    root = Path(__file__).resolve().parents[1] / "validation" / "plan_tool_v2_p2"
    register = json.loads((root / "p2-1-first-scored-acceptance-register-v1.json").read_text(encoding="utf-8"))
    assert register["historical_scope"]["HISTORICAL_V1_CONTAMINATED"] is True
    # P2.1 is immutable first-pass evidence now.  Its historical qualification
    # state remains separate from the post-failure remediation baseline.
    assert register["first_pass_started"] is True
    assert register["first_pass_completed"] is True
    assert register["first_pass_result"] == "FAIL"
