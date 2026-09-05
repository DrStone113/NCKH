from __future__ import annotations

import json
from pathlib import Path

from services.acceptance.v3.adapter import V3CaseLoader
from services.acceptance.v3.runner import oracle_firewall_evidence


def test_v3_loader_projects_only_execution_safe_fields(tmp_path: Path):
    path = tmp_path / "development-v3.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "candidate_id": "development-v3-001",
                        "category": "nutrition",
                        "prompt": "Synthetic case.",
                        "execution_fixture": {"timezone": "Asia/Ho_Chi_Minh", "period": ["2027-01-01", "2027-01-01"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    case = V3CaseLoader(str(path)).execution_cases()[0]
    assert case.view.case_id == "development-v3-001"
    assert not hasattr(case.view, "oracle_profile")
    assert "oracle" not in repr(case.view).casefold()


def test_v3_oracle_firewall_requires_raw_before_score():
    assert oracle_firewall_evidence() == {
        "adapter_has_no_oracle_import": True,
        "raw_persisted_before_scoring": True,
    }
