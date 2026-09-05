"""Structural guardrails for the unexecuted independent P2.2 holdout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"


def _read(name: str):
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


def _sha(name: str) -> str:
    return hashlib.sha256((VALIDATION / name).read_bytes()).hexdigest()


def test_confirmatory_v3_is_balanced_independent_and_unexecuted():
    pool = _read("p2-2-confirmatory-v3-candidate-pool-v1.json")
    audit = _read("p2-2-confirmatory-v3-exclusion-audit-v1.json")
    holdout = _read("plan-v2-confirmatory-v3.json")
    oracle = _read("plan-v2-confirmatory-oracle-v3.json")
    thresholds = _read("plan-v2-confirmatory-thresholds-v3.json")

    assert len(pool["candidates"]) == 180
    assert holdout["status"] == "FROZEN_UNEXECUTED"
    assert holdout["case_count"] == 120
    assert holdout["distribution"] == {
        "nutrition": 20,
        "single_workout": 20,
        "weekly_workout": 20,
        "combined_health": 20,
        "revision_lifecycle": 20,
        "adversarial_safety": 20,
    }
    assert audit["confirmed_overlap_count"] == 0
    assert audit["normalized_duplicate_count"] == 0
    assert audit["template_duplicate_count"] == 0
    assert oracle["status"] == "FROZEN_UNEXECUTED"
    assert len(oracle["cases"]) == 120
    assert thresholds["frozen_before_execution"] is True


def test_confirmatory_v3_manifest_hashes_frozen_artifacts():
    manifest = _read("plan-v2-confirmatory-v3-freeze-manifest-v1.json")
    assert manifest["status"] == "FROZEN_UNEXECUTED"
    assert manifest["execution_policy"] == "DO_NOT_EXECUTE_IN_P2_2"
    for name, expected in manifest["artifacts"].items():
        assert _sha(name) == expected
