from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.freeze_plan_v2_p2_1a_automated import SEMANTIC_VERDICTS, build


VALIDATION = Path(__file__).resolve().parents[1] / "validation" / "plan_tool_v2_p2"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_historical_p2_1a_freeze_is_output_independent_and_not_current_preflight(tmp_path):
    """The old P2.1 freeze must stay immutable after later remediation changes.

    A mismatch against its historical source manifest is evidence that it
    cannot become a current acceptance preflight, not a current product
    regression and not permission to rewrite P2.1 history.
    """

    result = build(tmp_path, flutter=None)
    manifest = result["manifest"]
    register_path = tmp_path / "p2-1a-automated-review-register-v1.json"
    holdout_path = tmp_path / "p2-1a-automated-holdout-v1.json"
    oracle_path = tmp_path / "p2-1a-deterministic-oracle-v1.json"

    assert manifest["review_mode"] == "AUTOMATED"
    assert manifest["READY_TO_RUN_P2_1_ACCEPTANCE"] is False
    assert manifest["final_preflight"]["IMPLEMENTATION_FROZEN_FOR_ACCEPTANCE"] is False
    assert manifest["implementation_hash_verification"]["mismatches"]
    assert manifest["final_preflight"]["ZERO_CONFIRMED_DEVELOPMENT_OVERLAP"]
    assert manifest["final_preflight"]["ZERO_TEMPLATE_DEVELOPMENT_OVERLAP"]
    assert manifest["final_preflight"]["ZERO_DUPLICATE_WEIGHTING"]
    assert manifest["final_preflight"]["NO_SCORED_ACCEPTANCE_EXECUTED"]
    assert manifest["deterministic_oracle_coverage"]["case_count"] == 120
    assert manifest["deterministic_oracle_coverage"]["semantic_case_count"] == len(SEMANTIC_VERDICTS)
    assert manifest["artifacts"]["holdout"]["sha256"] == _sha(holdout_path)
    assert manifest["artifacts"]["oracle"]["sha256"] == _sha(oracle_path)
    assert manifest["artifacts"]["automated_review_register"]["sha256"] == _sha(register_path)

    register = json.loads(register_path.read_text(encoding="utf-8"))
    assert register["same_model_multi_pass"] is True
    assert register["SAME_MODEL_MULTI_PASS"] is True
    assert register["review_coverage_percent"] == 100.0
    assert register["agreement"]["disagreement_case_ids"] == []
    assert len(register["records"]) == 120
    semantic = [record for record in register["records"] if record["review_source"] == "AUTOMATED_SEMANTIC_JUDGE"]
    assert len(semantic) == len(SEMANTIC_VERDICTS)
    assert all(len(record["judge_passes"]) == 3 for record in semantic)
    assert all(all(not judge["prior_judge_verdicts_visible"] for judge in record["judge_passes"]) for record in semantic)
    assert all(record["consensus"] == "UNANIMOUS_ACCEPT" for record in semantic)

    serialised = json.dumps({"holdout": json.loads(holdout_path.read_text(encoding="utf-8")), "register": register})
    assert "reviewer_type" not in serialised
    assert "HUMAN" not in serialised
    assert "plan_v2_output" not in serialised
    assert "legacy_output" not in serialised

    historical = json.loads((VALIDATION / "p2-1-first-scored-results-v1.json").read_text(encoding="utf-8"))
    assert historical["first_pass_result"] == "FAIL"
    assert historical["metrics"]["request_semantic_match_percent"] == 47.5
