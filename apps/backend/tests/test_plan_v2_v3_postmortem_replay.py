from __future__ import annotations

from pathlib import Path

from scripts.build_plan_v2_v3_semantic_postmortem import build_postmortem


def test_v3_postmortem_replay_reconciles_immutable_history() -> None:
    evidence = Path(__file__).resolve().parents[1] / "validation" / "plan_tool_v2_p2"
    inventory, root_causes, replay = build_postmortem(evidence)
    assert inventory["official_v3_failure_count"] == 60
    assert len(inventory["records"]) == 60
    assert root_causes["official_v3_reconciliation"]["semantic_match_percent"] == 50.0
    assert replay["execution_performed"] is False
    assert replay["official_v3_result_retained"] == "FAIL"
    assert replay["postmortem_replay_semantic_match_percent"] == 100.0
